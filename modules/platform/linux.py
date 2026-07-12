"""Linux platform adapter."""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from typing import Optional

from .base import AutomationResult, PlatformAdapter

LOGGER_REMOTE_MODE_STATUS = "CQRLOG Remote Mode for WSJT-X : Enabled"
MANUAL_REMOTE_MODE_WARNING = (
    "CQRLOG Remote Mode for WSJT-X must be enabled manually with Ctrl+J"
)


class LinuxPlatform(PlatformAdapter):
    """Linux-specific application launch and desktop automation."""

    @property
    def platform_name(self) -> str:
        return "linux"

    def check_automation_dependencies(self) -> tuple[bool, str]:
        missing = [
            tool
            for tool in ("wmctrl", "xdotool")
            if shutil.which(tool) is None
        ]

        if not missing:
            return True, ""

        return False, "wmctrl and/or xdotool not available"

    def launch_application(
        self,
        name: str,
        command: str,
        wait_seconds: float,
    ) -> bool:
        # Application launch remains in scripts/start-shack.sh for now.
        logging.debug(
            "launch_application(%s) is handled by the shell launcher on Linux.",
            name,
        )
        return False

    def list_windows(self) -> list[str]:
        try:
            completed = subprocess.run(
                ["wmctrl", "-l"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return []

        if completed.returncode != 0:
            return []

        return completed.stdout.splitlines()

    def find_window(
        self,
        title_substring: str,
        timeout_seconds: int,
    ) -> Optional[str]:
        pattern = title_substring.casefold()
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            for line in self.list_windows():
                if pattern in line.casefold():
                    return line.split(maxsplit=1)[0]

            time.sleep(1)

        return None

    def activate_window(self, window_id: str) -> bool:
        try:
            completed = subprocess.run(
                ["wmctrl", "-i", "-a", window_id],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return False

        return completed.returncode == 0

    def send_keystroke(self, window_id: str, keystroke: str) -> bool:
        try:
            completed = subprocess.run(
                ["xdotool", "key", "--window", window_id, keystroke],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return False

        return completed.returncode == 0

    def enable_logger_remote_mode(
        self,
        *,
        logger_name: str = "CQRLOG",
        window_title_pattern: str = "CQRLOG for Linux",
        keystroke: str = "ctrl+j",
        timeout_seconds: int = 12,
    ) -> AutomationResult:
        del logger_name  # Reserved for future multi-logger support.

        dependencies_ok, dependency_message = self.check_automation_dependencies()
        if not dependencies_ok:
            return AutomationResult(
                success=False,
                warnings=[dependency_message, MANUAL_REMOTE_MODE_WARNING],
            )

        progress_prefix = "Waiting for CQRLOG main window..."
        window_id = self.find_window(window_title_pattern, timeout_seconds)

        if window_id is None:
            return AutomationResult(
                success=False,
                progress_prefix=progress_prefix,
                progress_suffix=" not found",
                warnings=[
                    (
                        "CQRLOG main window not found within "
                        f"{timeout_seconds}s"
                    ),
                    MANUAL_REMOTE_MODE_WARNING,
                ],
            )

        if not self.activate_window(window_id):
            return AutomationResult(
                success=False,
                progress_prefix=progress_prefix,
                progress_suffix=" found",
                warnings=[
                    "Could not activate CQRLOG main window",
                    MANUAL_REMOTE_MODE_WARNING,
                ],
            )

        time.sleep(0.5)

        if not self.send_keystroke(window_id, keystroke):
            return AutomationResult(
                success=False,
                progress_prefix=progress_prefix,
                progress_suffix=" found",
                warnings=[
                    "Could not send Ctrl+J to CQRLOG",
                    MANUAL_REMOTE_MODE_WARNING,
                ],
            )

        return AutomationResult(
            success=True,
            progress_prefix=progress_prefix,
            progress_suffix=" found",
            status_line=LOGGER_REMOTE_MODE_STATUS,
        )

    def notify(self, title: str, body: str) -> bool:
        if shutil.which("notify-send") is None:
            logging.debug("notify-send not available on Linux.")
            return False

        try:
            completed = subprocess.run(
                ["notify-send", title, body],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return False

        return completed.returncode == 0
