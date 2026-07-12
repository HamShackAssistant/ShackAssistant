"""CLI entry points for platform automation."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from . import get_platform


def append_log(message: str) -> None:
    log_file = os.environ.get("SHACK_LOGFILE", "").strip()
    if not log_file:
        return

    timestamp = datetime.now().strftime("%F %T")
    Path(log_file).expanduser().open("a", encoding="utf-8").write(
        f"{timestamp} - {message}\n"
    )


def print_warning(message: str) -> None:
    print(f"⚠ {message}", flush=True)
    append_log(f"WARN - {message}")


def run_enable_logger_remote_mode(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enable logger remote mode using the host platform adapter."
    )
    parser.add_argument(
        "--window-title-pattern",
        default="CQRLOG for Linux",
        help="Case-insensitive window title substring to match.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=12,
        help="Seconds to wait for the logger window.",
    )
    parser.add_argument(
        "--keystroke",
        default="ctrl+j",
        help="Keystroke sent after activating the logger window.",
    )

    args = parser.parse_args(argv)
    platform = get_platform()
    result = platform.enable_logger_remote_mode(
        window_title_pattern=args.window_title_pattern,
        keystroke=args.keystroke,
        timeout_seconds=args.timeout,
    )

    if result.progress_prefix:
        print(
            f"{result.progress_prefix}{result.progress_suffix}",
            flush=True,
        )

    for warning in result.warnings:
        print_warning(warning)

    if result.success:
        print(result.status_line, flush=True)
        append_log(f"OK - {result.status_line}")
        append_log("CQRLOG Remote Mode for WSJT-X enabled via Ctrl+J")
        return 0

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shack Assistant platform tools.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "enable-logger-remote-mode",
        help="Enable CQRLOG Remote Mode for WSJT-X.",
    )

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        parser.print_help()
        return 1

    command = argv[0]
    command_args = argv[1:]

    if command == "enable-logger-remote-mode":
        return run_enable_logger_remote_mode(command_args)

    parser.error(f"Unknown command: {command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
