"""Windows platform adapter."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from .base import AutomationResult, PlatformAdapter
from .windows_apps import discover_windows_application


class WindowsPlatform(PlatformAdapter):
    """Windows application launch and desktop automation."""

    def __init__(
        self,
        *,
        popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
        which: Callable[[str], Optional[str]] = shutil.which,
        discover: Callable[[str], Optional[Path]] | None = None,
    ) -> None:
        self._popen_factory = popen_factory
        self._which = which
        self._discover = discover or discover_windows_application

    @property
    def platform_name(self) -> str:
        return "windows"

    def discover_application(self, name: str) -> Optional[Path]:
        """Return the installed executable for a known application, if found."""
        return self._discover(name)

    def _resolve_executable(self, name: str, command: str) -> Optional[Path]:
        command = (command or "").strip().strip('"')
        if command:
            candidate = Path(command).expanduser()
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                pass

            looks_like_path = candidate.suffix.lower() == ".exe" or any(
                separator in command for separator in ("/", "\\")
            )
            if looks_like_path:
                return None

            found = self._which(command) or self._which(f"{command}.exe")
            if found:
                found_path = Path(found)
                try:
                    if found_path.is_file():
                        return found_path
                except OSError:
                    pass

        return self._discover(name)

    def _creation_flags(self) -> int:
        if os.name != "nt":
            return 0

        flags = 0
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return flags

    def launch_application(
        self,
        name: str,
        command: str,
        wait_seconds: float,
    ) -> bool:
        """Launch a Windows desktop application without waiting for it to exit."""
        del wait_seconds

        executable = self._resolve_executable(name, command)
        if executable is None:
            logging.debug("Could not find executable for %s (%s).", name, command)
            return False

        kwargs = {
            "cwd": str(executable.parent),
            "shell": False,
            "close_fds": True,
        }
        creation_flags = self._creation_flags()
        if creation_flags:
            kwargs["creationflags"] = creation_flags

        try:
            self._popen_factory([str(executable)], **kwargs)
        except OSError as exc:
            logging.debug("Could not launch %s: %s", name, exc)
            return False

        return True

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
