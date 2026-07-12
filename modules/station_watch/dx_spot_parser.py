"""DX Cluster spot line parser."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


DX_SPOT_PATTERN = re.compile(
    r"^DX\s+de\s+([A-Z0-9/]+):\s+"
    r"([\d.]+)\s+"
    r"([A-Z0-9/]+)\s+"
    r"(.+?)\s+"
    r"(\d{4}Z)\s*$",
    re.IGNORECASE,
)

LOGIN_PROMPT_PATTERN = re.compile(
    r"(callsign|call|login|user)\s*:",
    re.IGNORECASE,
)

PARTIAL_LOGIN_PROMPT_END = re.compile(
    r"(?:callsign|call|login|user)\s*:\s*$",
    re.IGNORECASE,
)

FREQ_TOLERANCE_MHZ = 0.003

FT8_DIAL_FREQUENCIES_MHZ = (
    1.840,
    3.573,
    5.357,
    7.074,
    10.136,
    14.074,
    18.100,
    21.074,
    24.917,
    28.074,
    50.313,
)

FT4_DIAL_FREQUENCIES_MHZ = (
    7.047,
    10.140,
    14.080,
    18.104,
    21.140,
    24.919,
    28.180,
)


@dataclass
class DxSpot:
    spotter: str
    frequency_khz: float
    callsign: str
    comment: str
    time_utc: str
    band: str
    mode: str
    raw_line: str


def normalize_callsign(value: str) -> str:
    return value.strip().upper()


def frequency_khz_to_band(frequency_khz: float) -> str:
    mhz = frequency_khz / 1000.0

    bands = [
        (1.8, 2.0, "160m"),
        (3.5, 4.0, "80m"),
        (5.0, 5.5, "60m"),
        (7.0, 7.3, "40m"),
        (10.1, 10.15, "30m"),
        (14.0, 14.35, "20m"),
        (18.068, 18.168, "17m"),
        (21.0, 21.45, "15m"),
        (24.89, 24.99, "12m"),
        (28.0, 29.7, "10m"),
        (50.0, 54.0, "6m"),
        (144.0, 148.0, "2m"),
    ]

    for lower, upper, name in bands:
        if lower <= mhz <= upper:
            return name

    return f"{mhz:.3f} MHz" if frequency_khz > 0 else "Unknown band"


def infer_mode(comment: str) -> str:
    upper = comment.upper()

    for mode in ("FT8", "FT4", "CW", "RTTY", "PSK31", "PSK63", "JT65", "JT9"):
        if mode in upper:
            return mode

    return "UNKNOWN"


def infer_mode_from_frequency_khz(frequency_khz: float) -> str:
    mhz = frequency_khz / 1000.0

    for dial in FT8_DIAL_FREQUENCIES_MHZ:
        if abs(mhz - dial) <= FREQ_TOLERANCE_MHZ:
            return "FT8"

    for dial in FT4_DIAL_FREQUENCIES_MHZ:
        if abs(mhz - dial) <= FREQ_TOLERANCE_MHZ:
            return "FT4"

    return "UNKNOWN"


def resolve_mode(comment: str, frequency_khz: float) -> str:
    explicit = infer_mode(comment)

    if explicit != "UNKNOWN":
        return explicit

    return infer_mode_from_frequency_khz(frequency_khz)


def parse_spot_line(line: str) -> Optional[DxSpot]:
    stripped = line.strip()

    if not stripped or not stripped.upper().startswith("DX DE "):
        return None

    match = DX_SPOT_PATTERN.match(stripped)

    if not match:
        return None

    spotter = normalize_callsign(match.group(1))
    frequency_khz = float(match.group(2))
    callsign = normalize_callsign(match.group(3))
    comment = match.group(4).strip()
    time_utc = match.group(5).upper()

    if not re.fullmatch(r"[A-Z0-9/]{3,15}", callsign):
        return None

    if not re.fullmatch(r"[A-Z0-9/]{3,15}", spotter):
        return None

    return DxSpot(
        spotter=spotter,
        frequency_khz=frequency_khz,
        callsign=callsign,
        comment=comment,
        time_utc=time_utc,
        band=frequency_khz_to_band(frequency_khz),
        mode=resolve_mode(comment, frequency_khz),
        raw_line=stripped,
    )


def is_login_prompt(line: str) -> bool:
    return bool(LOGIN_PROMPT_PATTERN.search(line))


def is_partial_login_prompt(buffer: str) -> bool:
    """Detect a login prompt in an incomplete line without a trailing newline."""
    stripped = buffer.rstrip()

    if not stripped:
        return False

    return bool(PARTIAL_LOGIN_PROMPT_END.search(stripped))
