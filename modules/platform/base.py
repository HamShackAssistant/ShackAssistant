"""Platform abstraction layer for Shack Assistant."""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AutomationResult:
    """Outcome of a platform automation action."""

    success: bool
    status_line: str = ""
    warnings: list[str] = field(default_factory=list)
    progress_prefix: str = ""
    progress_suffix: str = ""


class PlatformAdapter(ABC):
    """Defines how Shack Assistant interacts with the host operating system."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable platform identifier."""

    @abstractmethod
    def launch_application(
        self,
        name: str,
        command: str,
        wait_seconds: float,
    ) -> bool:
        """Launch an external application."""

    @abstractmethod
    def find_window(
        self,
        title_substring: str,
        timeout_seconds: int,
    ) -> Optional[str]:
        """Return a platform-specific window identifier, if found."""

    @abstractmethod
    def activate_window(self, window_id: str) -> bool:
        """Bring a window to the foreground."""

    @abstractmethod
    def send_keystroke(self, window_id: str, keystroke: str) -> bool:
        """Send a keystroke to a specific window."""

    @abstractmethod
    def enable_logger_remote_mode(
        self,
        *,
        logger_name: str = "CQRLOG",
        window_title_pattern: str = "CQRLOG for Linux",
        keystroke: str = "ctrl+j",
        timeout_seconds: int = 12,
    ) -> AutomationResult:
        """Enable remote logging mode in the configured logger application."""

    @abstractmethod
    def notify(self, title: str, body: str) -> bool:
        """Display a desktop notification."""

    def check_automation_dependencies(self) -> tuple[bool, str]:
        """Return whether required automation tools are available."""
        return True, ""


def get_platform() -> PlatformAdapter:
    """Return the platform adapter for the current operating system."""
    if sys.platform.startswith("linux"):
        from .linux import LinuxPlatform

        return LinuxPlatform()

    if sys.platform == "win32":
        from .windows import WindowsPlatform

        return WindowsPlatform()

    raise NotImplementedError(f"Unsupported platform: {sys.platform}")
