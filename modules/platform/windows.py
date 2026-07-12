"""Windows platform adapter (placeholder)."""

from __future__ import annotations

from typing import Optional

from .base import AutomationResult, PlatformAdapter


class WindowsPlatform(PlatformAdapter):
    """Placeholder Windows implementation for future cross-platform support."""

    @property
    def platform_name(self) -> str:
        return "windows"

    def launch_application(
        self,
        name: str,
        command: str,
        wait_seconds: float,
    ) -> bool:
        # Future Windows implementation.
        return False

    def find_window(
        self,
        title_substring: str,
        timeout_seconds: int,
    ) -> Optional[str]:
        # Future Windows implementation.
        return None

    def activate_window(self, window_id: str) -> bool:
        # Future Windows implementation.
        return False

    def send_keystroke(self, window_id: str, keystroke: str) -> bool:
        # Future Windows implementation.
        return False

    def enable_logger_remote_mode(
        self,
        *,
        logger_name: str = "CQRLOG",
        window_title_pattern: str = "CQRLOG for Linux",
        keystroke: str = "ctrl+j",
        timeout_seconds: int = 12,
    ) -> AutomationResult:
        # Future Windows implementation.
        del logger_name, window_title_pattern, keystroke, timeout_seconds
        return AutomationResult(
            success=False,
            warnings=[
                "Automatic logger remote mode is not implemented on Windows yet.",
                "Enable remote logging manually in the logger application.",
            ],
        )

    def notify(self, title: str, body: str) -> bool:
        # Future Windows implementation.
        del title, body
        return False
