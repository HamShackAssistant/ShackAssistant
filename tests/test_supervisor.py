"""Unit tests for Shack Assistant Supervisor."""

from __future__ import annotations

import io
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.supervisor import (
    PREFIX_DXCLUSTER,
    PREFIX_WSJTX,
    PROJECT_ROOT,
    ShackAssistantSupervisor,
    SourceState,
    WSJTX_WATCHER_SCRIPT,
    acquire_supervisor_lock,
    build_dxcluster_command,
    build_wsjtx_command,
    is_process_alive,
    prefix_output_line,
    read_pid_file,
    release_supervisor_lock,
    stream_output,
)
from modules.supervisor_config import (
    MAX_RAPID_FAILURES,
    SupervisorConfig,
    load_supervisor_config,
    read_dxcluster_enabled,
)


class MockProcess:
    def __init__(
        self,
        *,
        stdout_lines: list[bytes] | None = None,
        stderr_lines: list[bytes] | None = None,
        exit_after_polls: int | None = None,
        exit_code: int = 0,
        fail_start: bool = False,
    ) -> None:
        self.stdout_lines = stdout_lines or []
        self.stderr_lines = stderr_lines or []
        self.exit_after_polls = exit_after_polls
        self.exit_code = exit_code
        self.fail_start = fail_start
        self.poll_count = 0
        self.terminated = False
        self.killed = False
        self.returncode: int | None = None

        self.stdout = io.BytesIO(b"".join(self.stdout_lines))
        self.stderr = io.BytesIO(b"".join(self.stderr_lines))
        self._write_stdout_done = False

        if self.stdout_lines:
            self.stdout = io.BytesIO()
            for line in self.stdout_lines:
                self.stdout.write(line)
            self.stdout.seek(0)

        if self.stderr_lines:
            self.stderr = io.BytesIO()
            for line in self.stderr_lines:
                self.stderr.write(line)
            self.stderr.seek(0)

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode

        if self.exit_after_polls is None:
            return None

        self.poll_count += 1
        if self.poll_count >= self.exit_after_polls:
            self.returncode = self.exit_code
            return self.returncode

        return None

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class SupervisorConfigTests(unittest.TestCase):
    def test_loads_defaults_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_supervisor_config(Path(tmp) / "missing.toml")

        self.assertTrue(config.restart_failed_sources)
        self.assertEqual(config.restart_delay_seconds, 10)
        self.assertTrue(config.sources.wsjtx_enabled)
        self.assertTrue(config.sources.dxcluster_enabled)

    def test_loads_supervisor_and_source_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "supervisor.toml"
            path.write_text(
                textwrap.dedent(
                    """
                    [supervisor]
                    restart_failed_sources = false
                    restart_delay_seconds = 15

                    [sources.wsjtx]
                    enabled = true

                    [sources.dxcluster]
                    enabled = false
                    """
                ).strip(),
                encoding="utf-8",
            )

            config = load_supervisor_config(path)

        self.assertFalse(config.restart_failed_sources)
        self.assertEqual(config.restart_delay_seconds, 15)
        self.assertTrue(config.sources.wsjtx_enabled)
        self.assertFalse(config.sources.dxcluster_enabled)


class SupervisorCommandTests(unittest.TestCase):
    def test_wsjtx_child_command_uses_current_interpreter_and_script(self) -> None:
        command = build_wsjtx_command(
            watchlist_path=Path("/tmp/watchlist.csv"),
            child_verbose=False,
        )

        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[1], "-u")
        self.assertEqual(command[2], str(WSJTX_WATCHER_SCRIPT))
        self.assertIn("--watchlist", command)
        self.assertEqual(command[-1], "/tmp/watchlist.csv")

    def test_dxcluster_child_command_uses_module_entry_point(self) -> None:
        command = build_dxcluster_command(
            config_path=Path("/tmp/dxcluster.toml"),
            watchlist_path=Path("/tmp/watchlist.csv"),
            notifications_path=Path("/tmp/notifications.toml"),
            child_verbose=True,
        )

        self.assertEqual(
            command[:4],
            [sys.executable, "-u", "-m", "modules.station_watch.dxcluster_watcher"],
        )
        self.assertIn("--verbose", command)
        self.assertIn("--config", command)
        self.assertIn("--notifications-config", command)

    def test_child_env_includes_pythonunbuffered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            watchlist_path = Path(tmp) / "watchlist.csv"
            watchlist_path.write_text("callsign\nVB7F\n", encoding="utf-8")

            dxcluster_path = Path(tmp) / "dxcluster.toml"
            dxcluster_path.write_text(
                "[dxcluster]\nenabled = true\nhost = \"x\"\ncallsign = \"Y\"\n",
                encoding="utf-8",
            )

            notifications_path = Path(tmp) / "notifications.toml"
            notifications_path.write_text("[ntfy]\nenabled = false\n", encoding="utf-8")

            supervisor = ShackAssistantSupervisor(
                SupervisorConfig(),
                config_path=Path(tmp) / "supervisor.toml",
                watchlist_path=watchlist_path,
                notifications_path=notifications_path,
                dxcluster_config_path=dxcluster_path,
                pid_path=Path(tmp) / "supervisor.pid",
            )

            env = supervisor._child_env()

        self.assertEqual(env.get("PYTHONUNBUFFERED"), "1")
        self.assertIn(str(PROJECT_ROOT), env.get("PYTHONPATH", ""))

    def test_existing_watcher_paths_remain_valid(self) -> None:
        self.assertTrue(WSJTX_WATCHER_SCRIPT.exists())
        self.assertTrue((PROJECT_ROOT / "modules" / "station_watch" / "dxcluster_watcher.py").exists())


class SupervisorEnablementTests(unittest.TestCase):
    def _make_supervisor(
        self,
        tmp: str,
        *,
        supervisor_toml: str = "",
        dxcluster_toml: str = "",
        watchlist_exists: bool = True,
        no_restart: bool = False,
        popen_factory=MockProcess,
    ) -> ShackAssistantSupervisor:
        config_path = Path(tmp) / "supervisor.toml"
        if supervisor_toml:
            config_path.write_text(supervisor_toml, encoding="utf-8")

        watchlist_path = Path(tmp) / "watchlist.csv"
        if watchlist_exists:
            watchlist_path.write_text("callsign,label\nVB7F,Vancouver\n", encoding="utf-8")

        dxcluster_path = Path(tmp) / "dxcluster.toml"
        if dxcluster_toml:
            dxcluster_path.write_text(dxcluster_toml, encoding="utf-8")

        notifications_path = Path(tmp) / "notifications.toml"
        notifications_path.write_text("[ntfy]\nenabled = true\n", encoding="utf-8")

        config = load_supervisor_config(config_path)
        if no_restart:
            config.restart_failed_sources = False
        config.status_interval_seconds = 1
        config.shutdown_timeout_seconds = 1

        return ShackAssistantSupervisor(
            config,
            config_path=config_path,
            watchlist_path=watchlist_path,
            notifications_path=notifications_path,
            dxcluster_config_path=dxcluster_path,
            pid_path=Path(tmp) / "supervisor.pid",
            popen_factory=popen_factory,
        )

    def test_disabled_dxcluster_source_is_not_launched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            supervisor = self._make_supervisor(
                tmp,
                supervisor_toml=textwrap.dedent(
                    """
                    [sources.dxcluster]
                    enabled = false
                    """
                ).strip(),
                dxcluster_toml=textwrap.dedent(
                    """
                    [dxcluster]
                    enabled = true
                    host = "cluster.example.test"
                    callsign = "KD4KZW"
                    """
                ).strip(),
            )

            self.assertFalse(supervisor._sources["dxcluster"].enabled)
            self.assertEqual(
                supervisor._sources["dxcluster"].state,
                SourceState.DISABLED,
            )

    def test_dxcluster_requires_own_config_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dxcluster.toml"
            path.write_text(
                "[dxcluster]\nenabled = false\nhost = \"x\"\ncallsign = \"Y\"\n",
                encoding="utf-8",
            )

            enabled, reason = read_dxcluster_enabled(path)

        self.assertFalse(enabled)
        self.assertIn("disabled", reason)

    def test_no_enabled_sources_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            supervisor = self._make_supervisor(
                tmp,
                supervisor_toml=textwrap.dedent(
                    """
                    [sources.wsjtx]
                    enabled = false

                    [sources.dxcluster]
                    enabled = false
                    """
                ).strip(),
            )

            self.assertEqual(supervisor.enabled_source_count(), 0)
            self.assertEqual(supervisor.run(), 1)


class SupervisorProcessTests(unittest.TestCase):
    def _make_supervisor(
        self,
        tmp: str,
        *,
        processes: dict[str, MockProcess] | None = None,
        no_restart: bool = False,
    ) -> ShackAssistantSupervisor:
        watchlist_path = Path(tmp) / "watchlist.csv"
        watchlist_path.write_text("callsign,label\nVB7F,Vancouver\n", encoding="utf-8")

        dxcluster_path = Path(tmp) / "dxcluster.toml"
        dxcluster_path.write_text(
            textwrap.dedent(
                """
                [dxcluster]
                enabled = true
                host = "cluster.example.test"
                callsign = "KD4KZW"
                """
            ).strip(),
            encoding="utf-8",
        )

        notifications_path = Path(tmp) / "notifications.toml"
        notifications_path.write_text("[ntfy]\nenabled = false\n", encoding="utf-8")

        config = SupervisorConfig(restart_delay_seconds=1, status_interval_seconds=1)
        if no_restart:
            config.restart_failed_sources = False

        created: list[str] = []
        process_map = processes or {}

        def popen_factory(command, **kwargs):
            if any("watcher.py" in part for part in command):
                key = "wsjtx"
            else:
                key = "dxcluster"

            created.append(key)
            process = process_map.get(key, MockProcess())
            process.key = key
            return process

        supervisor = ShackAssistantSupervisor(
            config,
            config_path=Path(tmp) / "supervisor.toml",
            watchlist_path=watchlist_path,
            notifications_path=notifications_path,
            dxcluster_config_path=dxcluster_path,
            pid_path=Path(tmp) / "supervisor.pid",
            popen_factory=popen_factory,
        )
        supervisor._created_keys = created
        return supervisor

    def test_both_sources_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            supervisor = self._make_supervisor(tmp)

            with patch.object(supervisor, "print_startup_banner"):
                with patch("modules.supervisor.time.sleep", side_effect=KeyboardInterrupt):
                    supervisor.run()

            self.assertEqual(supervisor._created_keys, ["wsjtx", "dxcluster"])

    def test_child_output_is_source_prefixed(self) -> None:
        emitted: list[str] = []

        stdout = io.BytesIO(b"MATCH: VB7F\n")
        stop_event = threading.Event()

        stream_output(stdout, PREFIX_WSJTX, emitted.append, stop_event)

        self.assertEqual(emitted, [prefix_output_line(PREFIX_WSJTX, "MATCH: VB7F")])

    def test_one_child_exit_does_not_stop_other(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wsjtx = MockProcess(exit_after_polls=2, exit_code=1)
            dxcluster = MockProcess()
            supervisor = self._make_supervisor(
                tmp,
                processes={"wsjtx": wsjtx, "dxcluster": dxcluster},
            )

            supervisor._start_source(supervisor._sources["wsjtx"])
            supervisor._start_source(supervisor._sources["dxcluster"])
            supervisor._poll_children()
            supervisor._poll_children()

            self.assertEqual(wsjtx.returncode, 1)
            self.assertIsNone(dxcluster.poll())

    def test_failed_child_restarts_after_delay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wsjtx = MockProcess(exit_after_polls=1, exit_code=1)
            supervisor = self._make_supervisor(tmp, processes={"wsjtx": wsjtx})
            supervisor.config.restart_delay_seconds = 0

            supervisor._start_source(supervisor._sources["wsjtx"])
            supervisor._poll_children()

            self.assertEqual(
                supervisor._sources["wsjtx"].state,
                SourceState.RESTARTING,
            )

            supervisor._process_restarts()
            self.assertEqual(
                supervisor._sources["wsjtx"].state,
                SourceState.RUNNING,
            )

    def test_no_restart_prevents_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wsjtx = MockProcess(exit_after_polls=1, exit_code=1)
            supervisor = self._make_supervisor(
                tmp,
                processes={"wsjtx": wsjtx},
                no_restart=True,
            )

            supervisor._start_source(supervisor._sources["wsjtx"])
            supervisor._poll_children()

            self.assertEqual(supervisor._sources["wsjtx"].state, SourceState.FAILED)
            supervisor._process_restarts()
            self.assertIsNone(supervisor._sources["wsjtx"].process)

    def test_rapid_failure_loop_is_rate_limited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            supervisor = self._make_supervisor(tmp)
            source = supervisor._sources["wsjtx"]

            for _ in range(MAX_RAPID_FAILURES):
                supervisor._record_failure(source)

            self.assertTrue(source.rate_limited)

            source.state = SourceState.RESTARTING
            source.restart_at = 0
            supervisor._process_restarts()

            self.assertEqual(source.state, SourceState.FAILED)

    def test_shutdown_stops_all_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wsjtx = MockProcess()
            dxcluster = MockProcess()
            supervisor = self._make_supervisor(
                tmp,
                processes={"wsjtx": wsjtx, "dxcluster": dxcluster},
            )

            supervisor._start_source(supervisor._sources["wsjtx"])
            supervisor._start_source(supervisor._sources["dxcluster"])
            supervisor.shutdown()

            self.assertTrue(wsjtx.terminated or wsjtx.killed)
            self.assertTrue(dxcluster.terminated or dxcluster.killed)
            self.assertEqual(supervisor._sources["wsjtx"].state, SourceState.STOPPED)
            self.assertEqual(supervisor._sources["dxcluster"].state, SourceState.STOPPED)

    def test_forced_termination_after_timeout(self) -> None:
        class StubbornProcess(MockProcess):
            def terminate(self) -> None:
                self.terminated = True

            def poll(self) -> int | None:
                return None

        with tempfile.TemporaryDirectory() as tmp:
            wsjtx = StubbornProcess()
            supervisor = self._make_supervisor(tmp, processes={"wsjtx": wsjtx})
            supervisor.config.shutdown_timeout_seconds = 0

            supervisor._start_source(supervisor._sources["wsjtx"])
            supervisor.shutdown()

            self.assertTrue(wsjtx.killed)


class SupervisorLockTests(unittest.TestCase):
    def test_stale_pid_file_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "supervisor.pid"
            pid_path.write_text("999999\n", encoding="utf-8")

            acquire_supervisor_lock(pid_path)

            self.assertEqual(read_pid_file(pid_path), os.getpid())
            release_supervisor_lock(pid_path)
            self.assertFalse(pid_path.exists())

    def test_clean_shutdown_removes_pid_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "supervisor.pid"
            acquire_supervisor_lock(pid_path)
            release_supervisor_lock(pid_path)
            self.assertFalse(pid_path.exists())

    def test_active_supervisor_prevents_duplicate_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "supervisor.pid"
            pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")

            with patch("modules.supervisor.is_process_alive", return_value=True):
                with patch("modules.supervisor.sys.exit", side_effect=SystemExit(1)) as exit_mock:
                    with self.assertRaises(SystemExit):
                        acquire_supervisor_lock(pid_path)

                    exit_mock.assert_called_once_with(1)

    def test_is_process_alive_handles_missing_pid(self) -> None:
        self.assertFalse(is_process_alive(999999))


class SupervisorIntegrationTests(unittest.TestCase):
    def test_main_help(self) -> None:
        from modules.supervisor import main

        with self.assertRaises(SystemExit) as ctx:
            main(["--help"])

        self.assertEqual(ctx.exception.code, 0)

    def test_main_no_restart_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            watchlist = Path(tmp) / "watchlist.csv"
            watchlist.write_text("callsign\nVB7F\n", encoding="utf-8")

            dxcluster = Path(tmp) / "dxcluster.toml"
            dxcluster.write_text(
                "[dxcluster]\nenabled = true\nhost = \"x\"\ncallsign = \"Y\"\n",
                encoding="utf-8",
            )

            notifications = Path(tmp) / "notifications.toml"
            notifications.write_text("[ntfy]\nenabled = false\n", encoding="utf-8")

            pid_file = Path(tmp) / "supervisor.pid"

            with patch("modules.supervisor.ShackAssistantSupervisor.run", return_value=0):
                from modules.supervisor import main

                result = main(
                    [
                        "--watchlist",
                        str(watchlist),
                        "--dxcluster-config",
                        str(dxcluster),
                        "--notifications-config",
                        str(notifications),
                        "--pid-file",
                        str(pid_file),
                        "--no-restart",
                    ]
                )

            self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
