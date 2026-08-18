"""Unit tests for the platform abstraction layer."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from modules.platform import get_platform
from modules.platform.base import AutomationResult
from modules.platform.linux import LinuxPlatform, MANUAL_REMOTE_MODE_WARNING
from modules.platform.windows import WindowsPlatform
from modules.platform.windows_apps import (
    discover_windows_application,
    get_windows_app_spec,
    iter_candidate_paths,
)


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

    def test_linux_launch_application_remains_shell_handled(self) -> None:
        with patch("modules.platform.linux.subprocess.Popen") as popen:
            result = self.platform.launch_application("FLrig", "flrig", 0)

        self.assertFalse(result)
        popen.assert_not_called()


class IsolatedWindowsDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.program_files = self.root / "Program Files"
        self.program_files_x86 = self.root / "Program Files (x86)"
        self.local_appdata = self.root / "LocalAppData"
        self.system_drive = self.root / "SystemDrive"
        self.environ = {
            "ProgramFiles": str(self.program_files),
            "ProgramFiles(x86)": str(self.program_files_x86),
            "LOCALAPPDATA": str(self.local_appdata),
            "SystemDrive": str(self.system_drive),
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _touch(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        return path

    def _discover(self, name: str, **kwargs):
        defaults = {
            "environ": self.environ,
            "which": lambda _name: None,
            "lookup_app_path": lambda _name: None,
        }
        defaults.update(kwargs)
        return discover_windows_application(name, **defaults)

    def test_discovers_versioned_flrig_in_program_files_x86(self) -> None:
        expected = self._touch(
            self.program_files_x86 / "flrig-2.0.12" / "flrig.exe"
        )

        found = self._discover("FLrig")

        self.assertEqual(found, expected)

    def test_discovers_unversioned_flrig_before_versioned_folder(self) -> None:
        unversioned = self._touch(self.program_files / "flrig" / "flrig.exe")
        self._touch(self.program_files / "flrig-2.0.12" / "flrig.exe")

        found = self._discover("flrig")

        self.assertEqual(found, unversioned)

    def test_discovers_wsjtx_on_system_drive(self) -> None:
        expected = self._touch(
            self.system_drive / "WSJT" / "wsjtx" / "bin" / "wsjtx.exe"
        )

        found = self._discover("WSJT-X")

        self.assertEqual(found, expected)

    def test_discovers_gridtracker2_under_local_appdata_programs(self) -> None:
        expected = self._touch(
            self.local_appdata / "Programs" / "GridTracker2" / "GridTracker2.exe"
        )

        found = self._discover("GridTracker2")

        self.assertEqual(found, expected)

    def test_prefers_program_files_over_path(self) -> None:
        expected = self._touch(self.program_files / "flrig" / "flrig.exe")
        path_hit = self.root / "path" / "flrig.exe"
        self._touch(path_hit)

        found = self._discover(
            "FLrig",
            which=lambda name: str(path_hit) if name == "flrig.exe" else None,
        )

        self.assertEqual(found, expected)

    def test_uses_path_when_install_locations_are_empty(self) -> None:
        path_hit = self._touch(self.root / "path" / "flrig.exe")

        found = self._discover(
            "FLrig",
            which=lambda name: str(path_hit) if name == "flrig.exe" else None,
        )

        self.assertEqual(found, path_hit)

    def test_uses_registry_app_path_when_provided(self) -> None:
        registry_hit = self._touch(self.root / "Custom Install" / "flrig.exe")

        found = self._discover(
            "FLrig",
            lookup_app_path=lambda name: (
                registry_hit if name == "flrig.exe" else None
            ),
        )

        self.assertEqual(found, registry_hit)

    def test_unknown_or_missing_application_returns_none(self) -> None:
        self.assertIsNone(self._discover("FLrig"))
        self.assertIsNone(self._discover("not-a-real-app"))

    def test_candidate_paths_follow_injected_environment(self) -> None:
        spec = get_windows_app_spec("GridTracker2")
        assert spec is not None

        candidates = iter_candidate_paths(spec, self.environ)
        self.assertTrue(
            any(str(self.local_appdata) in str(path) for path in candidates)
        )

        other_appdata = self.root / "OtherUserAppData"
        other_environ = dict(self.environ)
        other_environ["LOCALAPPDATA"] = str(other_appdata)
        other_candidates = iter_candidate_paths(spec, other_environ)

        self.assertTrue(
            any(str(other_appdata) in str(path) for path in other_candidates)
        )
        self.assertFalse(
            any(str(self.local_appdata) in str(path) for path in other_candidates)
        )

    def test_name_aliases_resolve_to_known_specs(self) -> None:
        self.assertEqual(get_windows_app_spec("FLrig").key, "flrig")
        self.assertEqual(get_windows_app_spec("WSJT-X").key, "wsjtx")
        self.assertEqual(get_windows_app_spec("GridTracker").key, "gridtracker2")


class WindowsLaunchTests(unittest.TestCase):
    def test_launch_returns_true_and_uses_argv_list_for_paths_with_spaces(self) -> None:
        popen = MagicMock()
        platform = WindowsPlatform(popen_factory=popen)
        executable = Path(r"C:\Program Files\flrig\flrig.exe")

        with patch.object(platform, "_resolve_executable", return_value=executable):
            started = platform.launch_application(
                "FLrig",
                str(executable),
                0,
            )

        self.assertTrue(started)
        popen.assert_called_once()
        args, kwargs = popen.call_args
        self.assertEqual(args[0], [str(executable)])
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(kwargs.get("cwd"), str(executable.parent))
        popen.return_value.wait.assert_not_called()
        popen.return_value.communicate.assert_not_called()

    def test_launch_returns_false_when_executable_is_missing(self) -> None:
        popen = MagicMock()
        platform = WindowsPlatform(
            popen_factory=popen,
            which=lambda _name: None,
            discover=lambda _name: None,
        )

        started = platform.launch_application(
            "FLrig",
            r"C:\Program Files\flrig\missing.exe",
            0,
        )

        self.assertFalse(started)
        popen.assert_not_called()

    def test_launch_returns_false_when_popen_fails(self) -> None:
        popen = MagicMock(side_effect=OSError("launch failed"))
        platform = WindowsPlatform(popen_factory=popen)
        executable = Path(r"C:\Program Files\flrig\flrig.exe")

        with patch.object(platform, "_resolve_executable", return_value=executable):
            started = platform.launch_application("FLrig", str(executable), 0)

        self.assertFalse(started)

    def test_launch_discovers_bare_command_name(self) -> None:
        popen = MagicMock()
        discovered = Path(r"C:\Program Files (x86)\flrig-2.0.12\flrig.exe")
        platform = WindowsPlatform(
            popen_factory=popen,
            which=lambda _name: None,
            discover=lambda name: discovered if name == "FLrig" else None,
        )

        with patch.object(Path, "is_file", return_value=False):
            started = platform.launch_application("FLrig", "flrig", 0)

        self.assertTrue(started)
        self.assertEqual(popen.call_args[0][0], [str(discovered)])

    def test_discover_application_delegates_to_windows_discovery(self) -> None:
        expected = Path(r"C:\Program Files (x86)\flrig-2.0.12\flrig.exe")
        platform = WindowsPlatform(discover=lambda name: expected if name == "FLrig" else None)

        self.assertEqual(platform.discover_application("FLrig"), expected)
        self.assertIsNone(platform.discover_application("missing"))


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
