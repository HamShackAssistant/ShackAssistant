# Architecture

This document describes the components present in the repository as of v0.1.

## Overview

```
┌─────────────────────────────────────────────────────────┐
│                  scripts/start-shack.sh                 │
│              (v0.1 — released, tracked)                 │
│                                                         │
│  Pre-flight checks ──► Start apps ──► Log to file      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│           modules/station_watch/watcher.py              │
│         (in development — untracked, not released)      │
│                                                         │
│  GridTracker ──UDP──► watcher ──UDP──► CQRLOG          │
│                         │                               │
│                         ├── notify-send (desktop alert) │
│                         └── logs/station-watch.jsonl    │
└─────────────────────────────────────────────────────────┘
```

## v0.1 Bash Launcher

**File:** `scripts/start-shack.sh`

### Flow

1. **Logging setup** — writes to `$HOME/.shack-startup.log`
2. **Pre-flight checks**
   - `check_audio()` — uses `pactl` to report default sink/source and detect USB audio devices
   - `check_cat_usb()` — lists `/dev/ttyUSB*` serial devices
3. **Application startup** — `start_app()` launches each program with `nohup` if not already running:
   - FLrig (`flrig`)
   - WSJT-X (`wsjtx`)
   - GridTracker (`/opt/GridTracker2/gridtracker2`)
   - CQRLOG (`cqrlog`)
4. **Completion** — prints status and waits for Enter

### Design notes

- Each app has a configurable startup wait (`sleep`) before verifying the process
- Already-running apps are detected and skipped
- Failures are reported to both console and log file

## Station Watch (In Development)

**File:** `modules/station_watch/watcher.py`

Station Watch sits in the UDP path between GridTracker and CQRLOG. It is designed to observe WSJT-X protocol traffic without modifying it.

### UDP topology

| Endpoint | Default | Role |
|----------|---------|------|
| Listen | `127.0.0.1:2238` | Receives packets forwarded by GridTracker |
| Relay | `127.0.0.1:2239` | Forwards original packets to CQRLOG |

The relay sends the **unchanged** received packet to the relay address before any parsing.

### WSJT-X packet handling

The watcher implements a minimal WSJT-X UDP parser:

- Validates magic number `0xADBCCBDA`
- Handles message types:
  - `MESSAGE_STATUS` (1) — updates current frequency and mode
  - `MESSAGE_DECODE` (2) — extracts decode text, SNR, and mode
- Ignores other message types and non-WSJT-X packets

String fields use Qt QDataStream encoding (UTF-16-BE with length prefix).

### Watchlist matching

- Loaded from a CSV file (default: `data/station-watch.csv`)
- Columns: `callsign`, optional `label`
- Comments (`#`) and header rows are skipped
- Callsigns are normalized to uppercase
- Matching tokenizes the decode message and checks for exact callsign matches
- Per-callsign alert cooldown defaults to 900 seconds

### Outputs

1. **Desktop notification** — `notify-send` with callsign, band, mode, SNR, and message
2. **Spot log** — JSON lines appended to `logs/station-watch.jsonl`

### Band mapping

`frequency_to_band()` maps the last known status frequency to common amateur bands (160m through 2m) or reports MHz if unmatched.

## Data Files

| File | Role |
|------|------|
| `data/station-watch.csv` | Callsign watchlist (untracked sample data) |
| `logs/station-watch.jsonl` | Spot log output (created at runtime by watcher; not in repo) |
| `~/.shack-startup.log` | Launcher log (created at runtime; not in repo) |

## External Dependencies

### Bash launcher

- Bash
- `pactl` (PulseAudio; optional)
- `pgrep`, `nohup`, `ls`, `awk`, `grep`, `xargs`
- FLrig, WSJT-X, GridTracker, CQRLOG (installed separately)

### Station Watch

- Python 3 (stdlib only — no third-party packages in source)
- `notify-send` (libnotify; for desktop alerts)
