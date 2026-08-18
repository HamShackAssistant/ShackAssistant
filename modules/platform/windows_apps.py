"""Windows application discovery for known ham-radio programs.

Discovery is data-driven so additional applications can be added by
registering a WindowsAppSpec. Candidate paths are built from process
environment variables (Program Files, LocalAppData, system drive) rather
than a specific user profile.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional


@dataclass(frozen=True)
class WindowsAppSpec:
    """Reusable install-layout description for one Windows application."""

    key: str
    display_name: str
    executable_names: tuple[str, ...]
    program_files_relatives: tuple[str, ...] = ()
    program_files_dir_prefixes: tuple[str, ...] = ()
    program_files_nested_roots: tuple[str, ...] = ()
    local_appdata_relatives: tuple[str, ...] = ()
    local_appdata_dir_prefixes: tuple[str, ...] = ()
    system_drive_relatives: tuple[str, ...] = ()


WINDOWS_APPLICATIONS: dict[str, WindowsAppSpec] = {
    "flrig": WindowsAppSpec(
        key="flrig",
        display_name="FLrig",
        executable_names=("flrig.exe",),
        program_files_relatives=(
            "flrig/flrig.exe",
            "W1HKJ/flrig/flrig.exe",
        ),
        program_files_dir_prefixes=("flrig",),
        program_files_nested_roots=("W1HKJ",),
    ),
    "wsjtx": WindowsAppSpec(
        key="wsjtx",
        display_name="WSJT-X",
        executable_names=("wsjtx.exe",),
        program_files_relatives=(
            "WSJT/wsjtx/bin/wsjtx.exe",
            "wsjtx/bin/wsjtx.exe",
        ),
        system_drive_relatives=("WSJT/wsjtx/bin/wsjtx.exe",),
    ),
    "gridtracker2": WindowsAppSpec(
        key="gridtracker2",
        display_name="GridTracker2",
        executable_names=("GridTracker2.exe",),
        program_files_relatives=(
            "GridTracker2/GridTracker2.exe",
            "GridTracker2/GridTracker2/GridTracker2.exe",
        ),
        local_appdata_relatives=(
            "Programs/GridTracker2/GridTracker2.exe",
            "Programs/GridTracker2/GridTracker2/GridTracker2.exe",
            "GridTracker2/GridTracker2.exe",
        ),
        local_appdata_dir_prefixes=("GridTracker2",),
    ),
}

_APP_KEY_ALIASES = {
    "flrig": "flrig",
    "wsjtx": "wsjtx",
    "wsjt": "wsjtx",
    "gridtracker2": "gridtracker2",
    "gridtracker": "gridtracker2",
}

_APP_PATHS_SUBKEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
)


def normalize_app_key(name: str) -> str:
    compact = "".join(character for character in name.casefold() if character.isalnum())
    return _APP_KEY_ALIASES.get(compact, compact)


def get_windows_app_spec(name: str) -> Optional[WindowsAppSpec]:
    return WINDOWS_APPLICATIONS.get(normalize_app_key(name))


def _path_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def program_files_roots(environ: Mapping[str, str]) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    for key in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        value = environ.get(key)
        if not value:
            continue
        path = Path(value)
        folded = str(path).casefold()
        if folded in seen:
            continue
        seen.add(folded)
        roots.append(path)
    return roots


def system_drive_root(environ: Mapping[str, str]) -> Path:
    drive = environ.get("SystemDrive") or "C:"
    if len(drive) == 2 and drive[1] == ":":
        return Path(drive + "\\")
    return Path(drive)


def _iter_prefix_executable_paths(
    root: Path,
    prefixes: tuple[str, ...],
    executable_name: str,
) -> Iterable[Path]:
    if not prefixes or not executable_name:
        return

    try:
        children = list(root.iterdir())
    except OSError:
        children = []

    for prefix in prefixes:
        yield root / prefix / executable_name

        prefix_folded = prefix.casefold()
        matches: list[Path] = []
        for child in children:
            try:
                if not child.is_dir():
                    continue
            except OSError:
                continue
            child_name = child.name.casefold()
            if child_name.startswith(prefix_folded) and child_name != prefix_folded:
                matches.append(child)

        for child in sorted(matches, key=lambda item: item.name.casefold()):
            yield child / executable_name


def iter_candidate_paths(
    spec: WindowsAppSpec,
    environ: Mapping[str, str],
) -> list[Path]:
    """Return well-known install candidates, preferring default locations."""
    candidates: list[Path] = []
    executable_name = spec.executable_names[0] if spec.executable_names else ""

    for root in program_files_roots(environ):
        for relative in spec.program_files_relatives:
            candidates.append(root / relative)
        candidates.extend(
            _iter_prefix_executable_paths(
                root,
                spec.program_files_dir_prefixes,
                executable_name,
            )
        )
        for nested in spec.program_files_nested_roots:
            candidates.extend(
                _iter_prefix_executable_paths(
                    root / nested,
                    spec.program_files_dir_prefixes,
                    executable_name,
                )
            )

    local_appdata = environ.get("LOCALAPPDATA")
    if local_appdata:
        local_root = Path(local_appdata)
        for relative in spec.local_appdata_relatives:
            candidates.append(local_root / relative)
        programs_root = local_root / "Programs"
        candidates.extend(
            _iter_prefix_executable_paths(
                programs_root,
                spec.local_appdata_dir_prefixes,
                executable_name,
            )
        )

    drive_root = system_drive_root(environ)
    for relative in spec.system_drive_relatives:
        candidates.append(drive_root / relative)

    return _unique_paths(candidates)


def lookup_app_paths_executable(executable_name: str) -> Optional[Path]:
    """Return an App Paths registry entry, if the executable still exists."""
    if sys.platform != "win32":
        return None

    try:
        import winreg
    except ImportError:
        return None

    hives = (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)
    for hive in hives:
        for subkey in _APP_PATHS_SUBKEYS:
            try:
                with winreg.OpenKey(hive, rf"{subkey}\{executable_name}") as key:
                    value, _unused = winreg.QueryValueEx(key, None)
            except OSError:
                continue

            if not value:
                continue

            path = Path(os.path.expandvars(str(value).strip().strip('"')))
            if _path_is_file(path):
                return path

    return None


def discover_windows_application(
    name: str,
    *,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], Optional[str]] | None = None,
    is_file: Callable[[Path], bool] | None = None,
    lookup_app_path: Callable[[str], Optional[Path]] | None = None,
) -> Optional[Path]:
    """Return the first existing executable for a known application name."""
    spec = get_windows_app_spec(name)
    if spec is None:
        return None

    if environ is None:
        environ = os.environ
    if which is None:
        which = shutil.which
    if is_file is None:
        is_file = _path_is_file
    if lookup_app_path is None:
        lookup_app_path = lookup_app_paths_executable

    for candidate in iter_candidate_paths(spec, environ):
        if is_file(candidate):
            return candidate

    for executable_name in spec.executable_names:
        registry_path = lookup_app_path(executable_name)
        if registry_path is not None and is_file(registry_path):
            return registry_path

    for executable_name in spec.executable_names:
        found = which(executable_name)
        if not found:
            continue
        found_path = Path(found)
        if is_file(found_path):
            return found_path

    return None
