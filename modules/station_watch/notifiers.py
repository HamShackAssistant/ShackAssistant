"""Optional notification providers for Station Watch."""

from __future__ import annotations

import json
import logging
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


DEFAULT_NOTIFICATIONS_CONFIG = "~/.config/shack-assistant/notifications.toml"
NTFY_TIMEOUT_SECONDS = 4
NTFY_TITLE = "🪿 Shack Watch Alert"


@dataclass
class NtfyConfig:
    enabled: bool = False
    server: str = "https://ntfy.sh"
    topic: str = ""


@dataclass
class SpotNotification:
    target: object
    message: str
    snr: int
    status: object
    decode_mode: str
    ms_since_midnight: int


def mask_topic(topic: str) -> str:
    if not topic:
        return "(empty)"

    if len(topic) <= 4:
        return "*" * len(topic)

    return f"{topic[:2]}...{topic[-2:]}"


def load_ntfy_config(path: Path) -> NtfyConfig:
    if not path.exists():
        logging.info(
            "Notification config not found at %s; ntfy push disabled.",
            path,
        )
        return NtfyConfig()

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logging.warning(
            "Could not read notification config %s: %s",
            path,
            exc,
        )
        return NtfyConfig()

    ntfy_section = data.get("ntfy", {})
    if not isinstance(ntfy_section, dict):
        logging.warning("Invalid [ntfy] section in %s; ntfy push disabled.", path)
        return NtfyConfig()

    enabled = bool(ntfy_section.get("enabled", False))
    server = str(ntfy_section.get("server", "https://ntfy.sh")).rstrip("/")
    topic = str(ntfy_section.get("topic", "")).strip()

    if enabled and not topic:
        logging.warning(
            "ntfy is enabled but topic is missing in %s; ntfy push disabled.",
            path,
        )
        enabled = False

    config = NtfyConfig(enabled=enabled, server=server, topic=topic)

    if config.enabled:
        logging.info(
            "ntfy push enabled (server=%s, topic=%s)",
            config.server,
            mask_topic(config.topic),
        )

    return config


def build_ntfy_body(
    notification: SpotNotification,
    build_body: Callable[..., str],
) -> str:
    body = build_body(
        target=notification.target,
        message=notification.message,
        snr=notification.snr,
        status=notification.status,
        decode_mode=notification.decode_mode,
        ms_since_midnight=notification.ms_since_midnight,
    )
    callsign = notification.target.callsign

    if body:
        return f"{callsign}\n{body}"

    return callsign


def build_ntfy_payload(config: NtfyConfig, title: str, body: str) -> bytes:
    payload = {
        "topic": config.topic,
        "title": title,
        "message": body,
        "priority": 4,
        "tags": ["radio"],
    }
    return json.dumps(payload).encode("utf-8")


def send_ntfy_notification(
    config: NtfyConfig,
    title: str,
    body: str,
) -> None:
    url = config.server

    try:
        data = build_ntfy_payload(config, title, body)
    except (TypeError, UnicodeError, ValueError) as exc:
        logging.warning(
            "ntfy push payload encoding failed (topic=%s): %s",
            mask_topic(config.topic),
            exc,
        )
        return

    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=NTFY_TIMEOUT_SECONDS):
            logging.debug(
                "ntfy push sent (topic=%s)",
                mask_topic(config.topic),
            )
    except urllib.error.HTTPError as exc:
        logging.warning(
            "ntfy push failed with HTTP %s (topic=%s): %s",
            exc.code,
            mask_topic(config.topic),
            exc,
        )
    except urllib.error.URLError as exc:
        logging.warning(
            "ntfy push failed (topic=%s): %s",
            mask_topic(config.topic),
            exc,
        )
    except TimeoutError:
        logging.warning(
            "ntfy push timed out after %d seconds (topic=%s)",
            NTFY_TIMEOUT_SECONDS,
            mask_topic(config.topic),
        )


class NotificationDispatcher:
    """Dispatch spot alerts to configured notification providers."""

    def __init__(
        self,
        config_path: Path,
        desktop_notifier: Callable[..., None],
        build_body: Callable[..., str],
    ):
        self.desktop_notifier = desktop_notifier
        self.build_body = build_body
        self.ntfy_config = load_ntfy_config(config_path)

    def notify_spot(self, notification: SpotNotification) -> None:
        self.desktop_notifier(
            target=notification.target,
            message=notification.message,
            snr=notification.snr,
            status=notification.status,
            decode_mode=notification.decode_mode,
            ms_since_midnight=notification.ms_since_midnight,
        )

        if not self.ntfy_config.enabled:
            return

        body = build_ntfy_body(notification, self.build_body)
        send_ntfy_notification(
            config=self.ntfy_config,
            title=NTFY_TITLE,
            body=body,
        )
