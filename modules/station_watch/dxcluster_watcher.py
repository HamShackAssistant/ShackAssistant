"""DX Cluster Watch — TCP client and alert pipeline."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Callable, Optional

try:
    from .cooldown import CooldownTracker
    from .dx_spot_parser import (
        DxSpot,
        is_login_prompt,
        is_partial_login_prompt,
        parse_spot_line,
    )
    from .dxcluster_config import (
        DEFAULT_DXCLUSTER_CONFIG,
        DxClusterConfig,
        load_dxcluster_config,
        validate_dxcluster_config,
    )
    from .notifiers import DEFAULT_NOTIFICATIONS_CONFIG, NotificationDispatcher
    from .watcher import DEFAULT_WATCHLIST, StationTarget, load_watchlist
except ImportError:
    from cooldown import CooldownTracker
    from dx_spot_parser import (
        DxSpot,
        is_login_prompt,
        is_partial_login_prompt,
        parse_spot_line,
    )
    from dxcluster_config import (
        DEFAULT_DXCLUSTER_CONFIG,
        DxClusterConfig,
        load_dxcluster_config,
        validate_dxcluster_config,
    )
    from notifiers import DEFAULT_NOTIFICATIONS_CONFIG, NotificationDispatcher
    from watcher import DEFAULT_WATCHLIST, StationTarget, load_watchlist


READ_BUFFER_LIMIT = 4096
STREAM_BUFFER_LIMIT = 16384
LOGIN_PROMPT_WINDOW_LINES = 20


def filter_telnet_bytes(data: bytes) -> bytes:
    """Remove common Telnet negotiation sequences from received bytes."""
    result = bytearray()
    index = 0

    while index < len(data):
        byte = data[index]

        if byte == 0xFF and index + 1 < len(data):
            command = data[index + 1]

            if command in (0xFB, 0xFC, 0xFD, 0xFE) and index + 2 < len(data):
                index += 3
                continue

            if command == 0xFF:
                result.append(0xFF)
                index += 2
                continue

        result.append(byte)
        index += 1

    return bytes(result)


def format_frequency_mhz(frequency_khz: float) -> str:
    return f"{frequency_khz / 1000.0:.3f} MHz"


def enforce_stream_buffer_limit(buffer: str, limit: int = STREAM_BUFFER_LIMIT) -> str:
    encoded = buffer.encode("utf-8")

    if len(encoded) <= limit:
        return buffer

    logging.warning(
        "DX Cluster partial buffer exceeded %d bytes; trimming malformed data",
        limit,
    )
    return encoded[-limit:].decode("utf-8", errors="replace")


def format_mode_display(mode: str) -> str:
    if mode == "UNKNOWN":
        return "Mode unknown"

    return mode


def build_dxcluster_notification(
    target: StationTarget,
    spot: DxSpot,
) -> tuple[str, str]:
    title = f"DX Cluster Watch: {target.callsign} spotted"
    lines: list[str] = []

    if target.label:
        lines.append(target.label)

    lines.append(
        f"{spot.band} · {format_mode_display(spot.mode)} · "
        f"{format_frequency_mhz(spot.frequency_khz)}"
    )
    lines.append(f"Spotted by {spot.spotter}")
    lines.append(f"Comment: {spot.comment}")
    lines.append("Source: DX Cluster")

    return title, "\n".join(lines)


def build_match_summary_lines(
    target: StationTarget,
    spot: DxSpot,
) -> list[str]:
    lines = [target.callsign]

    if target.label:
        lines.append(target.label)

    lines.append(
        f"{spot.band} · {format_mode_display(spot.mode)} · "
        f"{format_frequency_mhz(spot.frequency_khz)}"
    )
    lines.append(f"Spotted by {spot.spotter}")

    return lines


def print_startup_banner(
    config: DxClusterConfig,
    watchlist_count: int,
    *,
    dry_run: bool,
    ntfy_enabled: bool,
) -> None:
    notifications = "Desktop"

    if ntfy_enabled:
        notifications = "Desktop + ntfy"

    print("=" * 50)
    print("Shack Assistant - DX Cluster Watch")
    print("=" * 50)
    print(f"Node          : {config.host}:{config.port}")
    print(f"Login         : {config.callsign}")
    print(f"Watchlist     : {watchlist_count} stations")
    print(f"Notifications : {notifications}")
    print(f"Reconnect     : {config.reconnect_delay_seconds} seconds")
    print(f"Dry Run       : {'Yes' if dry_run else 'No'}")


def print_match_block(
    target: StationTarget,
    spot: DxSpot,
    *,
    dry_run: bool,
    dispatch_result: Optional[object] = None,
) -> None:
    header = "DX CLUSTER MATCH — DRY RUN" if dry_run else "DX CLUSTER MATCH"

    print("-" * 50)
    print(header)

    for line in build_match_summary_lines(target, spot):
        print(line)

    if dry_run:
        print("No notifications sent.")
    elif dispatch_result is not None:
        if dispatch_result.desktop_sent:
            print("Desktop notification sent.")
        else:
            print("Desktop notification failed.")

        if dispatch_result.ntfy_enabled:
            if dispatch_result.ntfy_sent:
                print("ntfy notification sent.")
            else:
                print("ntfy notification failed.")

    print("-" * 50)


def cooldown_key(target: StationTarget, spot: DxSpot) -> str:
    return f"{target.callsign}:{spot.band}"


class DxClusterWatcher:
    """Connect to a DX Cluster node and alert on watchlist matches."""

    def __init__(
        self,
        config: DxClusterConfig,
        watchlist: dict[str, StationTarget],
        notifier: Optional[NotificationDispatcher],
        *,
        dry_run: bool = False,
        once: bool = False,
        verbose: bool = False,
        open_connection: Optional[Callable] = None,
        sleep: Optional[Callable] = None,
    ):
        self.config = config
        self.watchlist = watchlist
        self.notifier = notifier
        self.dry_run = dry_run
        self.once = once
        self.verbose = verbose
        self._open_connection = open_connection or asyncio.open_connection
        self._sleep = sleep or asyncio.sleep
        self.cooldown = CooldownTracker(config.alert_cooldown_seconds)
        self._received_valid_spot = False
        self._stop = False

    async def run(self) -> None:
        logging.debug(
            "DX Cluster Watch starting (host=%s, port=%d, dry_run=%s)",
            self.config.host,
            self.config.port,
            self.dry_run,
        )

        while not self._stop:
            try:
                await self._connect_and_process()
            except asyncio.CancelledError:
                raise
            except OSError as exc:
                logging.warning("DX Cluster connection error: %s", exc)
                print("Connection lost.")
            except Exception as exc:
                logging.warning("DX Cluster session error: %s", exc)
                print("Connection error.")

            if self.once and self._received_valid_spot:
                logging.debug("--once complete after receiving a valid DX spot")
                break

            print(
                f"Reconnecting in {self.config.reconnect_delay_seconds} seconds..."
            )
            logging.debug(
                "Reconnecting to DX Cluster in %d seconds",
                self.config.reconnect_delay_seconds,
            )
            await self._sleep(self.config.reconnect_delay_seconds)

    async def _connect_and_process(self) -> None:
        print("Connecting...")
        logging.debug(
            "Connecting to DX Cluster %s:%d",
            self.config.host,
            self.config.port,
        )

        reader, writer = await self._open_connection(
            self.config.host,
            self.config.port,
        )

        print("Connected.")
        print("Waiting for watched stations...")
        logging.debug(
            "Connected to DX Cluster %s:%d",
            self.config.host,
            self.config.port,
        )

        try:
            await self._process_stream(reader, writer)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logging.debug("Disconnected from DX Cluster")

    async def _send_login(self, writer) -> None:
        writer.write(f"{self.config.callsign}\r\n".encode("utf-8"))
        await writer.drain()
        logging.debug("Callsign submitted for DX Cluster login")

    async def _process_stream(self, reader: asyncio.StreamReader, writer) -> None:
        login_sent = False
        prompt_lines_seen = 0
        buffer = ""

        while not self._stop:
            raw = await reader.read(READ_BUFFER_LIMIT)

            if not raw:
                logging.warning("DX Cluster connection closed by remote host")
                break

            cleaned = filter_telnet_bytes(raw).decode("utf-8", errors="replace")
            buffer += cleaned
            buffer = enforce_stream_buffer_limit(buffer)

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.rstrip("\r")

                if not line.strip():
                    continue

                if not login_sent:
                    prompt_lines_seen += 1

                    if is_login_prompt(line):
                        logging.debug("Login prompt detected; sending callsign")
                        await self._send_login(writer)
                        login_sent = True
                        continue

                    if prompt_lines_seen >= LOGIN_PROMPT_WINDOW_LINES:
                        logging.debug(
                            "No login prompt detected; sending callsign proactively"
                        )
                        await self._send_login(writer)
                        login_sent = True

                    continue

                self._handle_line(line)

                if self.once and self._received_valid_spot:
                    self._stop = True
                    break

            if not login_sent and is_partial_login_prompt(buffer):
                logging.debug(
                    "Login prompt detected in partial buffer; sending callsign"
                )
                await self._send_login(writer)
                login_sent = True
                buffer = ""

    def _handle_line(self, line: str) -> None:
        spot = parse_spot_line(line)

        if spot is None:
            logging.debug("Ignored non-spot line: %s", line)
            return

        self._received_valid_spot = True
        logging.debug("Parsed DX spot: %s on %s", spot.callsign, spot.band)

        target = self.watchlist.get(spot.callsign)

        if target is None:
            return

        key = cooldown_key(target, spot)

        if not self.cooldown.should_alert(key):
            return

        title, body = build_dxcluster_notification(target, spot)

        if self.dry_run:
            print_match_block(target, spot, dry_run=True)
            logging.debug("Dry-run notification for %s", target.callsign)
            return

        dispatch_result = None

        if self.notifier is not None:
            dispatch_result = self.notifier.notify_alert(title=title, body=body)

        print_match_block(
            target,
            spot,
            dry_run=False,
            dispatch_result=dispatch_result,
        )


def parse_arguments(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch a DX Cluster node for callsigns in the active watchlist."
    )

    parser.add_argument(
        "--config",
        default=DEFAULT_DXCLUSTER_CONFIG,
        help=f"DX Cluster config path. Default: {DEFAULT_DXCLUSTER_CONFIG}",
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
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and match spots without sending notifications.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Exit after one valid DX spot line is received.",
    )

    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_arguments(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    config_path = Path(args.config).expanduser().resolve()
    config = load_dxcluster_config(config_path)

    if args.dry_run:
        if not config.host:
            logging.error("DX Cluster host is required for dry-run testing.")
            sys.exit(1)
    else:
        validate_dxcluster_config(config)

    watchlist_path = Path(args.watchlist).expanduser().resolve()

    if not watchlist_path.exists():
        logging.error("Watchlist not found: %s", watchlist_path)
        sys.exit(1)

    watchlist = load_watchlist(watchlist_path)

    notifier = None
    ntfy_enabled = False

    if not args.dry_run:
        notifications_path = Path(args.notifications_config).expanduser().resolve()
        notifier = NotificationDispatcher(
            config_path=notifications_path,
            desktop_notifier=lambda **kwargs: None,
            build_body=lambda **kwargs: "",
        )
        ntfy_enabled = notifier.ntfy_config.enabled

    print_startup_banner(
        config,
        len(watchlist),
        dry_run=args.dry_run,
        ntfy_enabled=ntfy_enabled,
    )
    print()

    watcher = DxClusterWatcher(
        config=config,
        watchlist=watchlist,
        notifier=notifier,
        dry_run=args.dry_run,
        once=args.once,
        verbose=args.verbose,
    )

    try:
        asyncio.run(watcher.run())
    except KeyboardInterrupt:
        print("DX Cluster Watch stopped.")
        logging.debug("DX Cluster Watch stopped.")


if __name__ == "__main__":
    main()
