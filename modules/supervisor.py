"""Shack Assistant Supervisor — orchestrates Station Watch and DX Cluster Watch."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

try:
    from .station_watch.dxcluster_config import DEFAULT_DXCLUSTER_CONFIG
    from .station_watch.notifiers import DEFAULT_NOTIFICATIONS_CONFIG
    from .station_watch.watcher import DEFAULT_WATCHLIST, load_watchlist
    from .supervisor_config import (
        DEFAULT_PID_FILE,
        DEFAULT_SUPERVISOR_CONFIG,
        MAX_RAPID_FAILURES,
        RAPID_FAILURE_WINDOW_SECONDS,
        SupervisorConfig,
        load_supervisor_config,
        read_dxcluster_enabled,
        read_ntfy_enabled,
    )
except ImportError:
    from station_watch.dxcluster_config import DEFAULT_DXCLUSTER_CONFIG
    from station_watch.notifiers import DEFAULT_NOTIFICATIONS_CONFIG
    from station_watch.watcher import DEFAULT_WATCHLIST, load_watchlist
    from supervisor_config import (
        DEFAULT_PID_FILE,
        DEFAULT_SUPERVISOR_CONFIG,
        MAX_RAPID_FAILURES,
        RAPID_FAILURE_WINDOW_SECONDS,
        SupervisorConfig,
        load_supervisor_config,
        read_dxcluster_enabled,
        read_ntfy_enabled,
    )


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WSJTX_WATCHER_SCRIPT = PROJECT_ROOT / "modules" / "station_watch" / "watcher.py"

SOURCE_WSJTX = "WSJT-X"
SOURCE_DXCLUSTER = "DX Cluster"
PREFIX_SUPERVISOR = "[Supervisor]"
PREFIX_WSJTX = "[WSJT-X]"
PREFIX_DXCLUSTER = "[DX Cluster]"


class SourceState(str, Enum):
    STARTING = "Starting"
    RUNNING = "Running"
    DISABLED = "Disabled"
    RESTARTING = "Restarting"
    FAILED = "Failed"
    STOPPED = "Stopped"


@dataclass
class ManagedSource:
    key: str
    display_name: str
    prefix: str
    build_command: Callable[[], list[str]]
    enabled: bool = True
    disabled_reason: str = ""
    state: SourceState = SourceState.DISABLED
    process: Optional[subprocess.Popen] = field(default=None, repr=False)
    output_threads: list[threading.Thread] = field(default_factory=list, repr=False)
    exit_code: Optional[int] = None
    consecutive_failures: int = 0
    failure_timestamps: list[float] = field(default_factory=list)
    restart_at: float = 0.0
    rate_limited: bool = False


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    return True


def read_pid_file(path: Path) -> Optional[int]:
    if not path.exists():
        return None

    try:
        content = path.read_text(encoding="utf-8").strip()
        return int(content)
    except (OSError, ValueError):
        return None


def acquire_supervisor_lock(pid_path: Path) -> None:
    pid_path.parent.mkdir(parents=True, exist_ok=True)

    existing_pid = read_pid_file(pid_path)
    if existing_pid is not None and is_process_alive(existing_pid):
        print(
            f"{PREFIX_SUPERVISOR} Another supervisor is already running "
            f"(PID {existing_pid})."
        )
        print(f"{PREFIX_SUPERVISOR} PID file: {pid_path}")
        sys.exit(1)

    if existing_pid is not None:
        logging.warning(
            "Removing stale supervisor PID file for PID %d.", existing_pid
        )

    pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")


def release_supervisor_lock(pid_path: Path) -> None:
    if not pid_path.exists():
        return

    stored_pid = read_pid_file(pid_path)
    if stored_pid == os.getpid():
        pid_path.unlink(missing_ok=True)


def build_wsjtx_command(
    *,
    watchlist_path: Path,
    child_verbose: bool,
) -> list[str]:
    command = [sys.executable, "-u", str(WSJTX_WATCHER_SCRIPT)]

    if child_verbose:
        command.append("--verbose")

    command.extend(["--watchlist", str(watchlist_path)])
    return command


def build_dxcluster_command(
    *,
    config_path: Path,
    watchlist_path: Path,
    notifications_path: Path,
    child_verbose: bool,
) -> list[str]:
    command = [
        sys.executable,
        "-u",
        "-m",
        "modules.station_watch.dxcluster_watcher",
        "--config",
        str(config_path),
        "--watchlist",
        str(watchlist_path),
        "--notifications-config",
        str(notifications_path),
    ]

    if child_verbose:
        command.append("--verbose")

    return command


def prefix_output_line(prefix: str, line: str) -> str:
    return f"{prefix} {line}"


def stream_output(
    stream,
    prefix: str,
    emit: Callable[[str], None],
    stop_event: threading.Event,
) -> None:
    try:
        for raw_line in iter(stream.readline, b""):
            if stop_event.is_set():
                break

            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if line:
                emit(prefix_output_line(prefix, line))
    finally:
        stream.close()


def count_watchlist_stations(path: Path) -> int:
    if not path.exists():
        return 0

    return len(load_watchlist(path))


class ShackAssistantSupervisor:
    def __init__(
        self,
        config: SupervisorConfig,
        *,
        config_path: Path,
        watchlist_path: Path,
        notifications_path: Path,
        dxcluster_config_path: Path,
        pid_path: Path,
        child_verbose: bool = False,
        verbose: bool = False,
        popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
    ) -> None:
        self.config = config
        self.config_path = config_path
        self.watchlist_path = watchlist_path
        self.notifications_path = notifications_path
        self.dxcluster_config_path = dxcluster_config_path
        self.pid_path = pid_path
        self.child_verbose = child_verbose
        self.verbose = verbose
        self.popen_factory = popen_factory

        self._stopping = False
        self._stop_event = threading.Event()
        self._sources: dict[str, ManagedSource] = {}
        self._previous_states: dict[str, SourceState] = {}

        self._prepare_sources()

    def _prepare_sources(self) -> None:
        wsjtx_enabled = self.config.sources.wsjtx_enabled
        wsjtx_reason = ""

        if wsjtx_enabled and not self.watchlist_path.exists():
            wsjtx_enabled = False
            wsjtx_reason = f"watchlist not found: {self.watchlist_path}"

        dxcluster_enabled = self.config.sources.dxcluster_enabled
        dxcluster_reason = ""

        if dxcluster_enabled:
            runnable, reason = read_dxcluster_enabled(self.dxcluster_config_path)
            if not runnable:
                dxcluster_enabled = False
                dxcluster_reason = reason

        self._sources = {
            "wsjtx": ManagedSource(
                key="wsjtx",
                display_name="WSJT-X Watch",
                prefix=PREFIX_WSJTX,
                build_command=lambda: build_wsjtx_command(
                    watchlist_path=self.watchlist_path,
                    child_verbose=self.child_verbose,
                ),
                enabled=wsjtx_enabled,
                disabled_reason=wsjtx_reason,
                state=(
                    SourceState.DISABLED
                    if not wsjtx_enabled
                    else SourceState.STARTING
                ),
            ),
            "dxcluster": ManagedSource(
                key="dxcluster",
                display_name="DX Cluster Watch",
                prefix=PREFIX_DXCLUSTER,
                build_command=lambda: build_dxcluster_command(
                    config_path=self.dxcluster_config_path,
                    watchlist_path=self.watchlist_path,
                    notifications_path=self.notifications_path,
                    child_verbose=self.child_verbose,
                ),
                enabled=dxcluster_enabled,
                disabled_reason=dxcluster_reason,
                state=(
                    SourceState.DISABLED
                    if not dxcluster_enabled
                    else SourceState.STARTING
                ),
            ),
        }

    def enabled_source_count(self) -> int:
        return sum(1 for source in self._sources.values() if source.enabled)

    def print_startup_banner(self) -> None:
        station_count = count_watchlist_stations(self.watchlist_path)
        ntfy_enabled = read_ntfy_enabled(self.notifications_path)

        print("=" * 50)
        print("Shack Assistant")
        print("=" * 50)
        print(f"Watchlist        : {station_count} stations")
        print("Desktop Alerts   : Enabled")
        print(f"ntfy             : {'Enabled' if ntfy_enabled else 'Disabled'}")
        print("Sources")
        print("-------")

        for source in self._sources.values():
            if source.enabled:
                print(f"{source.display_name:<17}: {SourceState.STARTING.value}")
            else:
                print(f"{source.display_name:<17}: {SourceState.DISABLED.value}")
                if source.disabled_reason:
                    logging.debug(
                        "%s disabled: %s",
                        source.display_name,
                        source.disabled_reason,
                    )

        print()

    def _emit(self, message: str) -> None:
        print(message, flush=True)

    def _emit_supervisor(self, message: str) -> None:
        self._emit(f"{PREFIX_SUPERVISOR} {message}")

    def _update_source_status(self, source: ManagedSource) -> None:
        previous = self._previous_states.get(source.key)
        if previous == source.state:
            return

        self._previous_states[source.key] = source.state

        if source.state == SourceState.RESTARTING:
            delay = self.config.restart_delay_seconds
            self._emit_supervisor(
                f"{source.display_name} exited; restarting in {delay} seconds."
            )
            print(f"{source.display_name:<17}: Restarting in {delay} seconds")
        elif source.state == SourceState.FAILED:
            self._emit_supervisor(
                f"{source.display_name} failed and will not be restarted."
            )
            print(f"{source.display_name:<17}: {SourceState.FAILED.value}")
        elif source.state == SourceState.RUNNING:
            print(f"{source.display_name:<17}: {SourceState.RUNNING.value}")
        elif source.state == SourceState.STOPPED:
            print(f"{source.display_name:<17}: {SourceState.STOPPED.value}")

    def _child_env(self) -> dict[str, str]:
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        root = str(PROJECT_ROOT)

        if existing:
            if root not in existing.split(os.pathsep):
                env["PYTHONPATH"] = os.pathsep.join([root, existing])
        else:
            env["PYTHONPATH"] = root

        env["PYTHONUNBUFFERED"] = "1"

        return env

    def _start_source(self, source: ManagedSource) -> bool:
        if not source.enabled or self._stopping:
            return False

        command = source.build_command()
        logging.debug("Starting %s: %s", source.display_name, command)

        try:
            process = self.popen_factory(
                command,
                cwd=str(PROJECT_ROOT),
                env=self._child_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
            )
        except OSError as exc:
            source.state = SourceState.FAILED
            self._emit_supervisor(
                f"Could not start {source.display_name}: {exc}"
            )
            self._update_source_status(source)
            return False

        source.process = process
        source.state = SourceState.RUNNING
        source.exit_code = None
        self._update_source_status(source)

        for stream, _label in (
            (process.stdout, "stdout"),
            (process.stderr, "stderr"),
        ):
            if stream is None:
                continue

            thread = threading.Thread(
                target=stream_output,
                args=(stream, source.prefix, self._emit, self._stop_event),
                daemon=True,
                name=f"{source.key}-{ _label}",
            )
            thread.start()
            source.output_threads.append(thread)

        return True

    def _record_failure(self, source: ManagedSource) -> None:
        now = time.monotonic()
        source.consecutive_failures += 1
        source.failure_timestamps.append(now)
        source.failure_timestamps = [
            timestamp
            for timestamp in source.failure_timestamps
            if now - timestamp <= RAPID_FAILURE_WINDOW_SECONDS
        ]

        if len(source.failure_timestamps) >= MAX_RAPID_FAILURES:
            source.rate_limited = True

    def _handle_child_exit(self, source: ManagedSource, exit_code: int) -> None:
        source.exit_code = exit_code
        source.process = None
        source.output_threads.clear()

        self._emit_supervisor(
            f"{source.display_name} exited with code {exit_code}."
        )
        logging.warning(
            "%s exited with code %d",
            source.display_name,
            exit_code,
        )

        if self._stopping:
            source.state = SourceState.STOPPED
            self._update_source_status(source)
            return

        if not self.config.restart_failed_sources:
            source.state = SourceState.FAILED
            self._update_source_status(source)
            return

        if source.rate_limited:
            source.state = SourceState.FAILED
            self._update_source_status(source)
            return

        self._record_failure(source)
        source.state = SourceState.RESTARTING
        source.restart_at = time.monotonic() + self.config.restart_delay_seconds
        self._update_source_status(source)

    def _poll_children(self) -> None:
        for source in self._sources.values():
            if source.process is None:
                continue

            exit_code = source.process.poll()
            if exit_code is None:
                continue

            self._handle_child_exit(source, exit_code)

    def _process_restarts(self) -> None:
        if self._stopping or not self.config.restart_failed_sources:
            return

        now = time.monotonic()

        for source in self._sources.values():
            if source.state != SourceState.RESTARTING:
                continue

            if now < source.restart_at:
                continue

            if source.rate_limited:
                source.state = SourceState.FAILED
                self._update_source_status(source)
                continue

            source.state = SourceState.STARTING
            self._start_source(source)

    def _all_children_stopped(self) -> bool:
        for source in self._sources.values():
            if source.process is not None:
                return False

        return True

    def _terminate_children(self) -> None:
        for source in self._sources.values():
            process = source.process
            if process is None:
                if source.enabled and source.state not in (
                    SourceState.DISABLED,
                    SourceState.STOPPED,
                ):
                    source.state = SourceState.STOPPED
                    self._update_source_status(source)
                continue

            if process.poll() is None:
                try:
                    process.terminate()
                except OSError as exc:
                    logging.warning(
                        "Could not terminate %s: %s",
                        source.display_name,
                        exc,
                    )

        deadline = time.monotonic() + self.config.shutdown_timeout_seconds

        while time.monotonic() < deadline:
            self._poll_children()
            if self._all_children_stopped():
                break
            time.sleep(0.1)

        for source in self._sources.values():
            process = source.process
            if process is None:
                continue

            if process.poll() is None:
                logging.warning(
                    "Force killing %s after shutdown timeout.",
                    source.display_name,
                )
                try:
                    process.kill()
                except OSError as exc:
                    logging.warning(
                        "Could not kill %s: %s",
                        source.display_name,
                        exc,
                    )

        self._poll_children()

        for source in self._sources.values():
            if source.state != SourceState.DISABLED:
                source.state = SourceState.STOPPED
                self._update_source_status(source)

    def shutdown(self) -> None:
        if self._stopping:
            return

        self._stopping = True
        self._stop_event.set()
        print()
        print("Shutting down Shack Assistant...")
        self._terminate_children()

    def run(self) -> int:
        if self.enabled_source_count() == 0:
            self._emit_supervisor("No enabled sources are available to start.")
            for source in self._sources.values():
                if source.disabled_reason:
                    self._emit_supervisor(
                        f"{source.display_name}: {source.disabled_reason}"
                    )
            return 1

        acquire_supervisor_lock(self.pid_path)

        previous_sigint = signal.getsignal(signal.SIGINT)
        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def handle_signal(signum, _frame) -> None:
            logging.debug("Received signal %s", signum)
            self.shutdown()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        exit_code = 0
        lock_acquired = True

        try:
            self.print_startup_banner()

            for source in self._sources.values():
                if source.enabled:
                    if not self._start_source(source):
                        exit_code = 1

            if self.enabled_source_count() > 0 and all(
                source.process is None
                for source in self._sources.values()
                if source.enabled
            ):
                self._emit_supervisor("No child processes could be started.")
                return 1

            while not self._stopping:
                self._poll_children()
                self._process_restarts()
                time.sleep(min(self.config.status_interval_seconds, 1.0))

        except KeyboardInterrupt:
            self.shutdown()
        finally:
            signal.signal(signal.SIGINT, previous_sigint)
            signal.signal(signal.SIGTERM, previous_sigterm)
            if lock_acquired:
                release_supervisor_lock(self.pid_path)

        return exit_code


def parse_arguments(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run WSJT-X Station Watch and DX Cluster Watch from one terminal."
        )
    )

    parser.add_argument(
        "--config",
        default=DEFAULT_SUPERVISOR_CONFIG,
        help=f"Supervisor config path. Default: {DEFAULT_SUPERVISOR_CONFIG}",
    )
    parser.add_argument(
        "--watchlist",
        default=DEFAULT_WATCHLIST,
        help=f"Active watchlist CSV. Default: {DEFAULT_WATCHLIST}",
    )
    parser.add_argument(
        "--notifications-config",
        default=DEFAULT_NOTIFICATIONS_CONFIG,
        help=(
            "Notification settings path. "
            f"Default: {DEFAULT_NOTIFICATIONS_CONFIG}"
        ),
    )
    parser.add_argument(
        "--dxcluster-config",
        default=DEFAULT_DXCLUSTER_CONFIG,
        help=(
            "DX Cluster config path used for enablement checks. "
            f"Default: {DEFAULT_DXCLUSTER_CONFIG}"
        ),
    )
    parser.add_argument(
        "--pid-file",
        default=DEFAULT_PID_FILE,
        help=f"Supervisor PID file path. Default: {DEFAULT_PID_FILE}",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable supervisor debug logging.",
    )
    parser.add_argument(
        "--child-verbose",
        action="store_true",
        help="Pass --verbose to child watcher processes.",
    )
    parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Do not restart child processes after unexpected exit.",
    )
    parser.add_argument(
        "--status-interval",
        type=int,
        default=None,
        help="Seconds between supervisor health checks.",
    )

    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_arguments(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    config_path = Path(args.config).expanduser().resolve()

    try:
        config = load_supervisor_config(config_path)
    except ValueError:
        return 1

    if args.no_restart:
        config.restart_failed_sources = False

    if args.status_interval is not None:
        if args.status_interval < 1:
            logging.error("--status-interval must be at least 1 second.")
            return 1
        config.status_interval_seconds = args.status_interval

    supervisor = ShackAssistantSupervisor(
        config,
        config_path=config_path,
        watchlist_path=Path(args.watchlist).expanduser().resolve(),
        notifications_path=Path(args.notifications_config).expanduser().resolve(),
        dxcluster_config_path=Path(args.dxcluster_config).expanduser().resolve(),
        pid_path=Path(args.pid_file).expanduser().resolve(),
        child_verbose=args.child_verbose,
        verbose=args.verbose,
    )

    return supervisor.run()


if __name__ == "__main__":
    sys.exit(main())
