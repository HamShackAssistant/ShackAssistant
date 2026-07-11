#!/usr/bin/env python3
"""
Shack Assistant - Station Watch

Receives WSJT-X UDP packets forwarded by GridTracker, checks decoded
messages against a callsign watchlist, generates desktop notifications,
and relays the original packets to CQRLOG.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import socket
import sys
import struct
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

try:
    from .notifiers import (
        DEFAULT_NOTIFICATIONS_CONFIG,
        NotificationDispatcher,
        SpotNotification,
    )
except ImportError:
    from notifiers import (
        DEFAULT_NOTIFICATIONS_CONFIG,
        NotificationDispatcher,
        SpotNotification,
    )


WSJTX_MAGIC = 0xADBCCBDA
MESSAGE_STATUS = 1
MESSAGE_DECODE = 2
DEFAULT_WATCHLIST = "~/.local/share/shack-assistant/watchlist.csv"


@dataclass
class StationTarget:
    callsign: str
    label: str = ""


@dataclass
class RadioStatus:
    frequency_hz: int = 0
    mode: str = ""


class PacketReader:
    """Minimal reader for Qt QDataStream values used by WSJT-X."""

    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def remaining(self) -> int:
        return len(self.data) - self.offset

    def read(self, size: int) -> bytes:
        if self.remaining() < size:
            raise ValueError(
                f"Packet ended unexpectedly at byte {self.offset}; "
                f"needed {size} more bytes"
            )

        value = self.data[self.offset:self.offset + size]
        self.offset += size
        return value

    def u8(self) -> int:
        return struct.unpack(">B", self.read(1))[0]

    def u32(self) -> int:
        return struct.unpack(">I", self.read(4))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self.read(4))[0]

    def u64(self) -> int:
        return struct.unpack(">Q", self.read(8))[0]

    def f64(self) -> float:
        return struct.unpack(">d", self.read(8))[0]

    def boolean(self) -> bool:
        return bool(self.u8())

    def byte_array(self) -> bytes:
        length = self.u32()

        if length == 0xFFFFFFFF:
            return b""

        return self.read(length)

    def string(self) -> str:
        length = self.u32()

        if length == 0xFFFFFFFF or length == 0:
            return ""

        raw = self.read(length)

        try:
            return raw.decode("utf-16-be")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace")


def normalize_callsign(value: str) -> str:
    return value.strip().upper()


def load_watchlist(path: Path) -> dict[str, StationTarget]:
    targets: dict[str, StationTarget] = {}

    if not path.exists():
        logging.warning("Watchlist does not exist: %s", path)
        return targets

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)

        for row_number, row in enumerate(reader, start=1):
            if not row:
                continue

            first = row[0].strip()

            if not first or first.startswith("#"):
                continue

            if first.lower() in {"callsign", "call"}:
                continue

            callsign = normalize_callsign(first)
            label = row[1].strip() if len(row) > 1 else ""

            if not re.fullmatch(r"[A-Z0-9/]{3,15}", callsign):
                logging.warning(
                    "Ignoring invalid callsign on row %d: %s",
                    row_number,
                    callsign,
                )
                continue

            targets[callsign] = StationTarget(
                callsign=callsign,
                label=label,
            )

    return targets


def parse_header(reader: PacketReader) -> tuple[int, int, bytes]:
    magic = reader.u32()

    if magic != WSJTX_MAGIC:
        raise ValueError(f"Invalid WSJT-X magic value: 0x{magic:08X}")

    schema = reader.u32()
    message_type = reader.u32()
    unique_id = reader.byte_array()

    return schema, message_type, unique_id


def parse_status(reader: PacketReader) -> RadioStatus:
    frequency_hz = reader.u64()
    mode = reader.string()

    return RadioStatus(
        frequency_hz=frequency_hz,
        mode=mode,
    )


def parse_decode(reader: PacketReader) -> dict[str, object]:
    new_decode = reader.boolean()
    milliseconds_since_midnight = reader.u32()
    snr = reader.i32()
    delta_time = reader.f64()
    delta_frequency = reader.u32()
    mode = reader.string()
    message = reader.string()
    low_confidence = reader.boolean()
    off_air = reader.boolean()

    return {
        "new_decode": new_decode,
        "milliseconds_since_midnight": milliseconds_since_midnight,
        "snr": snr,
        "delta_time": delta_time,
        "delta_frequency": delta_frequency,
        "mode": mode,
        "message": message.strip(),
        "low_confidence": low_confidence,
        "off_air": off_air,
    }


def find_watched_calls(
    message: str,
    targets: dict[str, StationTarget],
) -> list[StationTarget]:
    tokens = {
        normalize_callsign(token.strip("<>,.;:()[]{}"))
        for token in message.split()
    }

    return [
        target
        for callsign, target in targets.items()
        if callsign in tokens
    ]


def frequency_to_band(frequency_hz: int) -> str:
    mhz = frequency_hz / 1_000_000

    bands = [
        (1.8, 2.0, "160m"),
        (3.5, 4.0, "80m"),
        (5.0, 5.5, "60m"),
        (7.0, 7.3, "40m"),
        (10.1, 10.15, "30m"),
        (14.0, 14.35, "20m"),
        (18.068, 18.168, "17m"),
        (21.0, 21.45, "15m"),
        (24.89, 24.99, "12m"),
        (28.0, 29.7, "10m"),
        (50.0, 54.0, "6m"),
        (144.0, 148.0, "2m"),
    ]

    for lower, upper, name in bands:
        if lower <= mhz <= upper:
            return name

    return f"{mhz:.3f} MHz" if frequency_hz else "Unknown band"


def format_dial_frequency(frequency_hz: int) -> Optional[str]:
    if frequency_hz <= 0:
        return None

    mhz = frequency_hz / 1_000_000

    if mhz >= 100:
        return f"{mhz:.3f} MHz"

    return f"{mhz:.6f} MHz"


def format_decode_utc(ms_since_midnight: int) -> str:
    base = datetime.now(timezone.utc).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    decode_time = base + timedelta(milliseconds=ms_since_midnight)
    return decode_time.strftime("%Y-%m-%d %H:%M:%S UTC")


def build_notification_body(
    target: StationTarget,
    message: str,
    snr: int,
    status: RadioStatus,
    decode_mode: str,
    ms_since_midnight: int,
) -> str:
    lines: list[str] = []

    if target.label:
        lines.append(target.label)

    detail_parts: list[str] = []

    if status.frequency_hz > 0:
        detail_parts.append(frequency_to_band(status.frequency_hz))

    mode = decode_mode or status.mode
    if mode:
        detail_parts.append(mode)

    detail_parts.append(f"{snr:+d} dB")
    lines.append(" | ".join(detail_parts))

    dial_frequency = format_dial_frequency(status.frequency_hz)
    if dial_frequency:
        lines.append(dial_frequency)

    lines.append(format_decode_utc(ms_since_midnight))

    if message:
        lines.append(message)

    return "\n".join(lines)


def send_desktop_notification(
    target: StationTarget,
    message: str,
    snr: int,
    status: RadioStatus,
    decode_mode: str,
    ms_since_midnight: int,
) -> None:
    title = f"Station spotted: {target.callsign}"
    body = build_notification_body(
        target=target,
        message=message,
        snr=snr,
        status=status,
        decode_mode=decode_mode,
        ms_since_midnight=ms_since_midnight,
    )

    try:
        subprocess.run(
            [
                "notify-send",
                "--app-name=Shack Assistant",
                "--urgency=critical",
                "--icon=dialog-information",
                title,
                body,
            ],
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logging.warning("Desktop notification failed: %s", exc)


def append_spot_log(
    path: Path,
    target: StationTarget,
    message: str,
    snr: int,
    status: RadioStatus,
    decode_mode: str,
) -> None:
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "callsign": target.callsign,
        "label": target.label,
        "message": message,
        "snr": snr,
        "mode": decode_mode or status.mode,
        "frequency_hz": status.frequency_hz,
        "band": frequency_to_band(status.frequency_hz),
    }

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def build_socket(listen_host: str, listen_port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((listen_host, listen_port))
    return sock


def run(args: argparse.Namespace) -> None:
    watchlist_path = Path(args.watchlist).expanduser().resolve()
    log_path = Path(args.log_file).expanduser().resolve()

    if not watchlist_path.exists():
        default_path = Path(DEFAULT_WATCHLIST).expanduser().resolve()
        logging.error("Watchlist not found: %s", watchlist_path)
        logging.error("Default watchlist path: %s", default_path)
        logging.error(
            "Create a watchlist CSV or pass a different file with --watchlist PATH"
        )
        logging.error(
            "See data/station-watch.example.csv in the repository for CSV format."
        )
        sys.exit(1)

    targets = load_watchlist(watchlist_path)

    logging.info(
        "Loaded %d watched callsign(s) from %s",
        len(targets),
        watchlist_path,
    )

    sock = build_socket(args.listen_host, args.listen_port)
    relay_address = (args.relay_host, args.relay_port)
    status = RadioStatus()

    last_alert: dict[str, float] = {}
    watchlist_modified = (
        watchlist_path.stat().st_mtime if watchlist_path.exists() else 0
    )

    logging.info(
        "Listening on UDP %s:%d",
        args.listen_host,
        args.listen_port,
    )
    logging.info(
        "Relaying packets to UDP %s:%d",
        args.relay_host,
        args.relay_port,
    )

    notifications_config_path = Path(
        DEFAULT_NOTIFICATIONS_CONFIG
    ).expanduser().resolve()
    notifier = NotificationDispatcher(
        config_path=notifications_config_path,
        desktop_notifier=send_desktop_notification,
        build_body=build_notification_body,
    )

    while True:
        packet, sender = sock.recvfrom(65535)

        # Relay the original packet unchanged so CQRLOG can receive it.
        try:
            sock.sendto(packet, relay_address)
        except OSError as exc:
            logging.error("Could not relay UDP packet: %s", exc)

        # Automatically reload the CSV whenever it is edited.
        try:
            current_modified = watchlist_path.stat().st_mtime

            if current_modified != watchlist_modified:
                targets = load_watchlist(watchlist_path)
                watchlist_modified = current_modified
                logging.info(
                    "Reloaded watchlist; now watching %d callsign(s)",
                    len(targets),
                )
        except FileNotFoundError:
            pass

        try:
            reader = PacketReader(packet)
            schema, message_type, unique_id = parse_header(reader)

            if message_type == MESSAGE_STATUS:
                status = parse_status(reader)
                continue

            if message_type != MESSAGE_DECODE:
                continue

            decode = parse_decode(reader)
            message = str(decode["message"])

            matches = find_watched_calls(message, targets)

            for target in matches:
                now = time.monotonic()
                previous = last_alert.get(target.callsign, 0)

                if now - previous < args.cooldown:
                    continue

                last_alert[target.callsign] = now

                snr = int(decode["snr"])
                decode_mode = str(decode["mode"])

                logging.warning(
                    "WATCH MATCH: %s | %s | SNR %+d",
                    target.callsign,
                    message,
                    snr,
                )

                notifier.notify_spot(
                    SpotNotification(
                        target=target,
                        message=message,
                        snr=snr,
                        status=status,
                        decode_mode=decode_mode,
                        ms_since_midnight=int(
                            decode["milliseconds_since_midnight"]
                        ),
                    )
                )

                append_spot_log(
                    path=log_path,
                    target=target,
                    message=message,
                    snr=snr,
                    status=status,
                    decode_mode=decode_mode,
                )

        except (ValueError, struct.error) as exc:
            logging.debug(
                "Ignored non-WSJT-X or unsupported packet from %s: %s",
                sender,
                exc,
            )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch WSJT-X UDP decodes for selected callsigns."
    )

    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=2238)
    parser.add_argument("--relay-host", default="127.0.0.1")
    parser.add_argument("--relay-port", type=int, default=2239)

    parser.add_argument(
        "--watchlist",
        default=DEFAULT_WATCHLIST,
        help=(
            "Path to the active watchlist CSV. "
            f"Default: {DEFAULT_WATCHLIST}"
        ),
    )

    parser.add_argument(
        "--log-file",
        default="logs/station-watch.jsonl",
    )

    parser.add_argument(
        "--cooldown",
        type=int,
        default=900,
        help="Seconds before alerting again for the same station.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    try:
        run(args)
    except KeyboardInterrupt:
        logging.info("Station Watch stopped.")


if __name__ == "__main__":
    main()
