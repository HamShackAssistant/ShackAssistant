"""DX Cluster Watch configuration loading."""

from __future__ import annotations

import logging
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DXCLUSTER_CONFIG = "~/.config/shack-assistant/dxcluster.toml"


@dataclass
class DxClusterConfig:
    enabled: bool = False
    host: str = ""
    port: int = 7300
    callsign: str = ""
    reconnect_delay_seconds: int = 30
    alert_cooldown_seconds: int = 900


def load_dxcluster_config(path: Path) -> DxClusterConfig:
    if not path.exists():
        logging.error("DX Cluster config not found: %s", path)
        logging.error(
            "Copy config/dxcluster.example.toml to %s and edit it.",
            path,
        )
        sys.exit(1)

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logging.error("Could not read DX Cluster config %s: %s", path, exc)
        sys.exit(1)

    section = data.get("dxcluster", {})

    if not isinstance(section, dict):
        logging.error("Invalid [dxcluster] section in %s", path)
        sys.exit(1)

    config = DxClusterConfig(
        enabled=bool(section.get("enabled", False)),
        host=str(section.get("host", "")).strip(),
        port=int(section.get("port", 7300)),
        callsign=str(section.get("callsign", "")).strip().upper(),
        reconnect_delay_seconds=int(section.get("reconnect_delay_seconds", 30)),
        alert_cooldown_seconds=int(section.get("alert_cooldown_seconds", 900)),
    )

    return config


def validate_dxcluster_config(config: DxClusterConfig) -> None:
    if not config.enabled:
        logging.error(
            "DX Cluster Watch is disabled in configuration. "
            "Set enabled = true to run."
        )
        sys.exit(1)

    if not config.host:
        logging.error("DX Cluster host is required when enabled = true.")
        sys.exit(1)

    if config.port <= 0 or config.port > 65535:
        logging.error("DX Cluster port must be between 1 and 65535.")
        sys.exit(1)

    if not config.callsign:
        logging.error("DX Cluster login callsign is required when enabled = true.")
        sys.exit(1)

    if config.reconnect_delay_seconds < 1:
        logging.error("reconnect_delay_seconds must be at least 1.")
        sys.exit(1)

    if config.alert_cooldown_seconds < 0:
        logging.error("alert_cooldown_seconds must be zero or greater.")
        sys.exit(1)
