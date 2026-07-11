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
│                         ├── ntfy push (optional)        │
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

Station Watch is event-agnostic: it has no contest- or event-specific callsigns in code. Operators supply their own watchlists as external CSV files.

- Default active watchlist: `~/.local/share/shack-assistant/watchlist.csv` (operator-owned, not in the repository)
- Tracked example format: `data/station-watch.example.csv` (generic fictional callsigns only)
- Override path at runtime: `--watchlist PATH`
- Columns: `callsign`, optional `label` (or `description`)
- Comments (`#`) and header rows are skipped
- Callsigns are normalized to uppercase
- Matching tokenizes the decode message and checks for exact callsign matches
- Per-callsign alert cooldown defaults to 900 seconds
- Hot reload when the active CSV file is edited

#### Operator workflow (current)

Manual entry is CSV editing only. There is no UI or CLI for adding callsigns yet.

1. Copy `data/station-watch.example.csv` to a user-owned path, or create a new CSV in the same format
2. Edit rows to add or remove callsigns (single-call files are valid)
3. Start the watcher with the default path or `--watchlist` for a contest- or event-specific file
4. Swap watchlists by editing the active file or pointing `--watchlist` at another CSV

Example for a one-off event file:

```bash
python3 modules/station_watch/watcher.py --watchlist ~/watchlists/my-event.csv
```

#### Ignored operator data

These paths are not committed:

- `data/station-watch.csv` (legacy/local active file location)
- `data/watchlists/` (optional directory for event-specific lists)
- `~/.local/share/shack-assistant/watchlist.csv` (default active watchlist)

### Outputs

1. **Desktop notification** — `notify-send` with callsign (title), label, band, mode, SNR, dial frequency, UTC decode time, and WSJT-X message (fields omitted when unavailable)
2. **ntfy push notification** — optional; enabled via `~/.config/shack-assistant/notifications.toml`
3. **Spot log** — JSON lines appended to `logs/station-watch.jsonl`

### Notification Architecture

When a watchlist match passes cooldown checks:

```
Station Match
    ├── Desktop Notification (notify-send)
    └── ntfy Push Notification (optional)
```

- Desktop notifications always run via `notify-send`.
- ntfy is loaded from `~/.config/shack-assistant/notifications.toml` at startup.
- Example configuration: `config/notifications.example.toml` (tracked; copy and edit locally).
- If the config file is missing, ntfy is disabled and Station Watch continues normally.
- Network failures on ntfy are logged as warnings and do not stop the watcher.

### Band mapping

`frequency_to_band()` maps the last known status frequency to common amateur bands (160m through 2m) or reports MHz if unmatched.

## Data Files

| File | Role |
|------|------|
| `data/station-watch.example.csv` | Tracked example watchlist format (generic callsigns only) |
| `data/station-watch.csv` | Ignored operator watchlist (optional local path) |
| `data/watchlists/` | Ignored directory for event-specific operator lists |
| `~/.local/share/shack-assistant/watchlist.csv` | Default active watchlist (operator-owned, created locally) |
| `~/.config/shack-assistant/notifications.toml` | Operator notification settings (not in repo) |
| `config/notifications.example.toml` | Example ntfy configuration (tracked) |
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
