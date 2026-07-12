"""Cooldown tracking for alert deduplication."""

from __future__ import annotations

import logging
import time


class CooldownTracker:
    """Suppress repeated alerts for the same key within a cooldown window."""

    def __init__(self, cooldown_seconds: int):
        self.cooldown_seconds = cooldown_seconds
        self._last_alert: dict[str, float] = {}

    def should_alert(self, key: str) -> bool:
        now = time.monotonic()
        previous = self._last_alert.get(key)

        if previous is not None and now - previous < self.cooldown_seconds:
            logging.debug(
                "Alert suppressed by cooldown (%ds): %s",
                self.cooldown_seconds,
                key,
            )
            return False

        self._last_alert[key] = now
        return True
