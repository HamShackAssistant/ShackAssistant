"""Unit tests for the platform abstraction layer."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from modules.platform import get_platform
from modules.platform.base import AutomationResult
from modules.platform.linux import LinuxPlatform, MANUAL_REMOTE_MODE_WARNING
from modules.platform.windows import WindowsPlatform


class PlatformSelectionTests(unittest.TestCase):
    def test_linux_platform_selected_on_linux(self) -> None:
        with patch.object(sys, "platform", "linux"):
            with patch("sys.platform", "linux"):
                platform = get_platform()

        self.assertIsInstance(platform, LinuxPlatform)
        self.assertEqual(platform.platform_name, "linux")

    def test_windows_platform_selected_on_windows(self) -> None:
        with patch("sys.platform", "win32"):
            platform = get_platform()

        self.assertIsInstance(platform, WindowsPlatform)
        self.assertEqual(platform.platform_name, "windows")

    def test_windows_placeholder_can_be_imported(self) -> None:
        platform = WindowsPlatform()

        self.assertFalse(
            platform.enable_logger_remote_mode().success
        )
        self.assertIsNone(platform.find_window("CQRLOG", 1))
        self.assertFalse(platform.activate_window("1"))
        self.assertFalse(platform.send_keystroke("1", "ctrl+j"))
        self.assertFalse(platform.notify("title", "body"))


class LinuxPlatformTests(unittest.TestCase):
    def setUp(self) -> None:
        self.platform = LinuxPlatform()

    def test_check_automation_dependencies_reports_missing_tools(self) -> None:
        with patch("modules.platform.linux.shutil.which", return_value=None):
            ok, message = self.platform.check_automation_dependencies()

        self.assertFalse(ok)
        self.assertIn("wmctrl", message)

    def test_find_window_matches_case_insensitive_substring(self) -> None:
        with patch.object(
            self.platform,
            "list_windows",
            return_value=[
                "0x01  0 host New QSO ... (CQRLOG for Linux), database: W1AW",
            ],
        ):
            window_id = self.platform.find_window("cqrlog for linux", 1)

        self.assertEqual(window_id, "0x01")

    def test_enable_logger_remote_mode_success(self) -> None:
        with patch.object(
            self.platform,
            "check_automation_dependencies",
            return_value=(True, ""),
        ):
            with patch.object(
                self.platform,
                "find_window",
                return_value="0x01",
            ):
                with patch.object(
                    self.platform,
                    "activate_window",
                    return_value=True,
                ):
                    with patch.object(
                        self.platform,
                        "send_keystroke",
                        return_value=True,
                    ):
                        with patch("modules.platform.linux.time.sleep"):
                            result = self.platform.enable_logger_remote_mode()

        self.assertTrue(result.success)
        self.assertEqual(
            result.status_line,
            "CQRLOG Remote Mode for WSJT-X : Enabled",
        )

    def test_enable_logger_remote_mode_warns_when_dependencies_missing(self) -> None:
        with patch.object(
            self.platform,
            "check_automation_dependencies",
            return_value=(False, "wmctrl and/or xdotool not available"),
        ):
            result = self.platform.enable_logger_remote_mode()

        self.assertFalse(result.success)
        self.assertIn(MANUAL_REMOTE_MODE_WARNING, result.warnings)

    def test_enable_logger_remote_mode_sends_ctrl_j_at_most_once(self) -> None:
        send_keystroke = MagicMock(return_value=True)

        with patch.object(
            self.platform,
            "check_automation_dependencies",
            return_value=(True, ""),
        ):
            with patch.object(
                self.platform,
                "find_window",
                return_value="0x01",
            ):
                with patch.object(
                    self.platform,
                    "activate_window",
                    return_value=True,
                ):
                    with patch.object(
                        self.platform,
                        "send_keystroke",
                        send_keystroke,
                    ):
                        with patch("modules.platform.linux.time.sleep"):
                            self.platform.enable_logger_remote_mode(
                                keystroke="ctrl+j",
                            )

        send_keystroke.assert_called_once_with("0x01", "ctrl+j")


class PlatformCliTests(unittest.TestCase):
    def test_cli_prints_success_status_line(self) -> None:
        from modules.platform.__main__ import run_enable_logger_remote_mode

        result = AutomationResult(
            success=True,
            progress_prefix="Waiting for CQRLOG main window...",
            progress_suffix=" found",
            status_line="CQRLOG Remote Mode for WSJT-X : Enabled",
        )

        with patch("modules.platform.__main__.get_platform") as get_platform_mock:
            get_platform_mock.return_value.enable_logger_remote_mode.return_value = (
                result
            )
            with patch("builtins.print") as print_mock:
                exit_code = run_enable_logger_remote_mode([])

        self.assertEqual(exit_code, 0)
        printed = " ".join(str(call.args[0]) for call in print_mock.call_args_list)
        self.assertIn("CQRLOG Remote Mode for WSJT-X : Enabled", printed)


if __name__ == "__main__":
    unittest.main()
