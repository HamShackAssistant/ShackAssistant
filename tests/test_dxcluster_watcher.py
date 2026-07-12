"""Unit tests for DX Cluster Watch matching and session behavior."""

from __future__ import annotations

import asyncio
import logging
import unittest
from unittest.mock import Mock, patch

from modules.station_watch.cooldown import CooldownTracker
from modules.station_watch.dx_spot_parser import DxSpot
from modules.station_watch.dxcluster_config import DxClusterConfig
from modules.station_watch.dxcluster_watcher import (
    DxClusterWatcher,
    STREAM_BUFFER_LIMIT,
    build_dxcluster_notification,
    cooldown_key,
    enforce_stream_buffer_limit,
    filter_telnet_bytes,
    format_mode_display,
)
from modules.station_watch.notifiers import AlertDispatchResult
from modules.station_watch.watcher import StationTarget


class FakeStreamReader:
    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    async def read(self, n: int = -1) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)

        return b""


class FakeStreamWriter:
    def __init__(self):
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class DxClusterWatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = DxClusterConfig(
            enabled=True,
            host="cluster.example.test",
            port=7300,
            callsign="KD4KZW",
            reconnect_delay_seconds=30,
            alert_cooldown_seconds=900,
        )
        self.watchlist = {
            "VB7F": StationTarget(callsign="VB7F", label="Vancouver"),
            "W4C": StationTarget(callsign="W4C", label="Atlanta"),
        }
        self.spot = DxSpot(
            spotter="W3LPL",
            frequency_khz=14074.0,
            callsign="VB7F",
            comment="FT8 CQ",
            time_utc="2026Z",
            band="20m",
            mode="FT8",
            raw_line="DX de W3LPL: 14074.0 VB7F FT8 CQ 2026Z",
        )
        self.unknown_mode_spot = DxSpot(
            spotter="N4XYZ",
            frequency_khz=7268.0,
            callsign="W4C",
            comment="CQ special event",
            time_utc="0132Z",
            band="40m",
            mode="UNKNOWN",
            raw_line="DX de N4XYZ: 7268.0 W4C CQ special event 0132Z",
        )

    def test_watchlist_match_notification_body(self) -> None:
        target = self.watchlist["VB7F"]
        title, body = build_dxcluster_notification(target, self.spot)

        self.assertIn("VB7F", title)
        self.assertIn("Vancouver", body)
        self.assertIn("20m · FT8 · 14.074 MHz", body)
        self.assertIn("W3LPL", body)
        self.assertIn("Source: DX Cluster", body)

    def test_unknown_mode_displayed_in_notification(self) -> None:
        target = self.watchlist["W4C"]
        title, body = build_dxcluster_notification(target, self.unknown_mode_spot)

        self.assertEqual(format_mode_display("UNKNOWN"), "Mode unknown")
        self.assertIn("40m · Mode unknown · 7.268 MHz", body)

    def test_cooldown_suppression(self) -> None:
        tracker = CooldownTracker(900)
        key = cooldown_key(self.watchlist["VB7F"], self.spot)

        self.assertTrue(tracker.should_alert(key))
        self.assertFalse(tracker.should_alert(key))

    def test_telnet_filter_removes_negotiation_bytes(self) -> None:
        raw = b"\xff\xfb\x01Hello\n"
        cleaned = filter_telnet_bytes(raw)
        self.assertEqual(cleaned, b"Hello\n")

    def test_login_prompt_handling(self) -> None:
        prompt = b"Please enter your callsign:\n"
        spot_line = (
            b"DX de W3LPL:     14074.0  VB7F        FT8 CQ                     2026Z\n"
        )

        reader = FakeStreamReader([prompt, spot_line, b""])
        writer = FakeStreamWriter()
        notified: list[tuple[str, str]] = []

        class FakeNotifier:
            def notify_alert(self, title: str, body: str) -> AlertDispatchResult:
                notified.append((title, body))
                return AlertDispatchResult(
                    desktop_sent=True,
                    ntfy_enabled=True,
                    ntfy_sent=True,
                )

        watcher = DxClusterWatcher(
            config=self.config,
            watchlist=self.watchlist,
            notifier=FakeNotifier(),
            dry_run=False,
            once=True,
        )

        with patch("builtins.print"):
            asyncio.run(watcher._process_stream(reader, writer))

        self.assertTrue(any(b"KD4KZW" in write for write in writer.writes))
        self.assertEqual(len(notified), 1)

    def test_login_prompt_without_newline(self) -> None:
        prompt = b"Please enter your callsign:"
        spot_line = (
            b"\nDX de W3LPL:     14074.0  VB7F        FT8 CQ                     2026Z\n"
        )

        reader = FakeStreamReader([prompt, spot_line, b""])
        writer = FakeStreamWriter()

        watcher = DxClusterWatcher(
            config=self.config,
            watchlist=self.watchlist,
            notifier=None,
            dry_run=True,
            once=True,
        )

        with patch("builtins.print"):
            asyncio.run(watcher._process_stream(reader, writer))

        self.assertEqual(len(writer.writes), 1)
        self.assertIn(b"KD4KZW", writer.writes[0])

    def test_stream_buffer_limit_trims_oversized_partial_data(self) -> None:
        oversized = "x" * (STREAM_BUFFER_LIMIT + 1024)
        trimmed = enforce_stream_buffer_limit(oversized)

        self.assertLessEqual(len(trimmed.encode("utf-8")), STREAM_BUFFER_LIMIT)
        self.assertTrue(trimmed.endswith("x" * 1024))

    def test_dry_run_does_not_call_notifier(self) -> None:
        notifier = Mock()

        watcher = DxClusterWatcher(
            config=self.config,
            watchlist=self.watchlist,
            notifier=notifier,
            dry_run=True,
        )

        with patch("builtins.print") as mock_print:
            watcher._handle_line(self.spot.raw_line)

        notifier.notify_alert.assert_not_called()
        output = "\n".join(
            str(call.args[0]) for call in mock_print.call_args_list
        )
        self.assertIn("DRY RUN", output)

    def test_live_match_calls_notify_alert(self) -> None:
        notifier = Mock()
        notifier.notify_alert.return_value = AlertDispatchResult(
            desktop_sent=True,
            ntfy_enabled=True,
            ntfy_sent=True,
        )

        watcher = DxClusterWatcher(
            config=self.config,
            watchlist=self.watchlist,
            notifier=notifier,
            dry_run=False,
        )

        with patch("builtins.print"):
            watcher._handle_line(self.spot.raw_line)

        notifier.notify_alert.assert_called_once()

    def test_non_match_does_not_call_notifier(self) -> None:
        notifier = Mock()

        watcher = DxClusterWatcher(
            config=self.config,
            watchlist=self.watchlist,
            notifier=notifier,
            dry_run=False,
        )

        line = "DX de W3LPL: 14074.0 K1ABC FT8 CQ 2026Z"
        watcher._handle_line(line)

        notifier.notify_alert.assert_not_called()

    def test_normal_logging_does_not_emit_parsed_spots_at_info(self) -> None:
        watcher = DxClusterWatcher(
            config=self.config,
            watchlist=self.watchlist,
            notifier=None,
            dry_run=True,
        )

        with self.assertLogs(level="DEBUG") as logs:
            logging.getLogger().setLevel(logging.DEBUG)
            watcher._handle_line(self.spot.raw_line)

        messages = "\n".join(logs.output)
        self.assertNotRegex(messages, r"\bINFO\b")
        self.assertIn("Parsed DX spot", messages)

    def test_reconnect_delay_on_disconnect(self) -> None:
        sleep_calls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            raise asyncio.CancelledError()

        async def failing_connection(host: str, port: int):
            raise OSError("connection refused")

        watcher = DxClusterWatcher(
            config=self.config,
            watchlist=self.watchlist,
            notifier=None,
            dry_run=True,
            open_connection=failing_connection,
            sleep=fake_sleep,
        )

        with patch("builtins.print"):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(watcher.run())

        self.assertEqual(sleep_calls, [30])


class DxClusterConfigValidationTests(unittest.TestCase):
    def test_invalid_configuration_exits(self) -> None:
        from modules.station_watch.dxcluster_config import validate_dxcluster_config

        with self.assertRaises(SystemExit):
            validate_dxcluster_config(
                DxClusterConfig(enabled=True, host="", callsign="KD4KZW")
            )


if __name__ == "__main__":
    unittest.main()
