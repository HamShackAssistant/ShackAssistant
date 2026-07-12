"""Supervisor configuration loading."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SUPERVISOR_CONFIG = "~/.config/shack-assistant/supervisor.toml"
DEFAULT_PID_FILE = "~/.local/state/shack-assistant/supervisor.pid"

DEFAULT_RESTART_DELAY_SECONDS = 10
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 10
DEFAULT_STATUS_INTERVAL_SECONDS = 5

MAX_RAPID_FAILURES = 5
RAPID_FAILURE_WINDOW_SECONDS = 60


@dataclass
class SourceSettings:
    wsjtx_enabled: bool = True
    dxcluster_enabled: bool = True


@dataclass
class SupervisorConfig:
    restart_failed_sources: bool = True
    restart_delay_seconds: int = DEFAULT_RESTART_DELAY_SECONDS
    shutdown_timeout_seconds: int = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS
    status_interval_seconds: int = DEFAULT_STATUS_INTERVAL_SECONDS
    sources: SourceSettings = None  # type: ignore[assignment]
    watchlist_path: str = ""
    notifications_config_path: str = ""
    dxcluster_config_path: str = ""

    def __post_init__(self) -> None:
        if self.sources is None:
            self.sources = SourceSettings()


def load_supervisor_config(path: Path) -> SupervisorConfig:
    """Load supervisor settings; missing file returns safe defaults."""
    config = SupervisorConfig()

    if not path.exists():
        logging.debug("Supervisor config not found at %s; using defaults.", path)
        return config

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logging.error("Could not read supervisor config %s: %s", path, exc)
        raise ValueError(f"Invalid supervisor configuration: {path}") from exc

    section = data.get("supervisor", {})
    if section and not isinstance(section, dict):
        raise ValueError(f"Invalid [supervisor] section in {path}")

    sources_section = data.get("sources", {})
    if sources_section and not isinstance(sources_section, dict):
        raise ValueError(f"Invalid [sources] section in {path}")

    wsjtx_section = sources_section.get("wsjtx", {})
    dxcluster_section = sources_section.get("dxcluster", {})

    if wsjtx_section and not isinstance(wsjtx_section, dict):
        raise ValueError(f"Invalid [sources.wsjtx] section in {path}")

    if dxcluster_section and not isinstance(dxcluster_section, dict):
        raise ValueError(f"Invalid [sources.dxcluster] section in {path}")

    config.restart_failed_sources = bool(
        section.get("restart_failed_sources", config.restart_failed_sources)
    )
    config.restart_delay_seconds = int(
        section.get("restart_delay_seconds", config.restart_delay_seconds)
    )
    config.shutdown_timeout_seconds = int(
        section.get("shutdown_timeout_seconds", config.shutdown_timeout_seconds)
    )
    config.status_interval_seconds = int(
        section.get("status_interval_seconds", config.status_interval_seconds)
    )

    config.sources = SourceSettings(
        wsjtx_enabled=bool(wsjtx_section.get("enabled", True)),
        dxcluster_enabled=bool(dxcluster_section.get("enabled", True)),
    )

    return config


def read_dxcluster_enabled(path: Path) -> tuple[bool, str]:
    """Return whether DX Cluster Watch should run from its own config file."""
    if not path.exists():
        return False, "configuration file not found"

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return False, f"could not read config: {exc}"

    section = data.get("dxcluster", {})
    if not isinstance(section, dict):
        return False, "invalid [dxcluster] section"

    if not bool(section.get("enabled", False)):
        return False, "disabled in dxcluster.toml"

    host = str(section.get("host", "")).strip()
    callsign = str(section.get("callsign", "")).strip()

    if not host:
        return False, "host not configured"

    if not callsign:
        return False, "callsign not configured"

    return True, ""


def read_ntfy_enabled(path: Path) -> bool:
    """Return whether ntfy push is enabled in the notification config."""
    if not path.exists():
        return False

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return False

    section = data.get("ntfy", {})
    if not isinstance(section, dict):
        return False

    return bool(section.get("enabled", False))
