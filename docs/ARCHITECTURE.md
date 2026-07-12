# Architecture

This document describes the components present in the Shack Assistant repository.

## Overview

```
┌─────────────────────────────────────────────────────────┐
│                  scripts/start-shack.sh                 │
│              (v0.1 — released, tracked)                 │
│                                                         │
│  Pre-flight checks ──► Start apps ──► Log to file      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              modules/supervisor.py                      │
│         (orchestration — not field validated)           │
│                                                         │
│  +-- WSJT-X Station Watch (subprocess)                  │
│  +-- DX Cluster Watch (subprocess)                      │
└─────────────────────────────────────────────────────────┘

WSJT-X UDP ───────┐
                  ├── Watchlist Matcher ── Notification Pipeline
DX Cluster TCP ───┘
                  │
                  ├── notify-send (desktop alert)
                  ├── ntfy push (optional)
                  └── logs/station-watch.jsonl (WSJT-X only)
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
5. **CQRLOG integration** — calls `python3 -m modules.platform enable-logger-remote-mode`

### Design notes

- Each app has a configurable startup wait (`sleep`) before verifying the process
- Already-running apps are detected and skipped
- Failures are reported to both console and log file
- CQRLOG Remote Mode automation is delegated to the platform abstraction layer

## Platform Abstraction Layer

**Package:** `modules/platform/`

Shack Assistant separates platform-independent orchestration from operating-system-specific automation. The core decides *what* to launch and *which integrations to enable*. Platform adapters decide *how* those actions are performed on each host.

### Why it exists

Linux startup currently relies on `wmctrl` and `xdotool` to enable CQRLOG **Remote Mode for WSJT-X** (`Ctrl+J`). That behavior is effective on Linux but must not become part of the portable core. A platform layer keeps future Windows support isolated behind a stable interface.

### Interface

`PlatformAdapter` in `modules/platform/base.py` defines:

| Method | Purpose |
|--------|---------|
| `launch_application()` | Start external applications |
| `find_window()` | Locate a window by title substring |
| `activate_window()` | Bring a window to the foreground |
| `send_keystroke()` | Send a keystroke to a window |
| `enable_logger_remote_mode()` | Enable logger remote logging (CQRLOG today) |
| `notify()` | Display a desktop notification |

`get_platform()` selects the adapter using `sys.platform`.

### Linux implementation

**File:** `modules/platform/linux.py`

- Uses `wmctrl` to list and activate windows
- Uses `xdotool` to send `Ctrl+J` once to the CQRLOG main window
- Matches window titles case-insensitively on the stable substring `CQRLOG for Linux`
- Checks for `wmctrl` and `xdotool` before attempting automation
- Invoked from `scripts/start-shack.sh` via:

  ```bash
  python3 -m modules.platform enable-logger-remote-mode
  ```

Application launch (`flrig`, `wsjtx`, etc.) remains in the Bash launcher for now. Notification delivery for watchlist alerts remains in `modules/station_watch/notifiers.py`.

### Windows implementation

**File:** `modules/platform/windows.py`

Placeholder stubs only. Methods return safe no-op or manual-required results until Windows automation is designed.

### Supported operating systems

| OS | Status |
|----|--------|
| Linux | Implemented (`linux.py`) |
| Windows | Placeholder (`windows.py`) |

## Station Watch (WSJT-X — Field Validated)

**File:** `modules/station_watch/watcher.py`

Station Watch sits in the UDP path between GridTracker and CQRLOG. It is designed to observe WSJT-X protocol traffic without modifying it. This source is field validated as part of v0.3.0.

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

## DX Cluster Watch (Implemented — Not Field Validated)

**File:** `modules/station_watch/dxcluster_watcher.py`

DX Cluster Watch is a lightweight TCP client that connects directly to a configured DXSpider-compatible cluster node. No additional GUI application is required.

### Role in the architecture

- Runs independently of WSJT-X Station Watch
- Uses the same active watchlist: `~/.local/share/shack-assistant/watchlist.csv`
- Reuses the shared notification pipeline (`NotificationDispatcher.notify_alert`)
- Is optional and disabled unless configured and explicitly launched
- Fails safely without affecting the WSJT-X watcher

### Configuration

Operator config: `~/.config/shack-assistant/dxcluster.toml`

Example template: `config/dxcluster.example.toml`

| Setting | Default | Purpose |
|---------|---------|---------|
| `enabled` | `false` | Must be `true` for live operation |
| `host` | `""` | Cluster node hostname |
| `port` | `7300` | Cluster node TCP port |
| `callsign` | `""` | Login callsign |
| `reconnect_delay_seconds` | `30` | Delay before reconnect |
| `alert_cooldown_seconds` | `900` | Per callsign+band cooldown |

### Network client

- Uses `asyncio.open_connection(host, port)`
- Filters common Telnet negotiation bytes from the text stream
- Detects login prompts and submits the configured callsign
- Reconnects after disconnect using the configured delay

### Spot parsing

**File:** `modules/station_watch/dx_spot_parser.py`

Parses DXSpider-style spot lines and produces a structured `DxSpot` object with spotter, frequency, callsign, comment, UTC time, band, and conservative mode inference.

### Resource profile

- Single asyncio TCP connection
- Bounded read buffers (4 KB per read)
- No unbounded spot history
- No database
- Suitable for continuous background use on an 8 GB RAM shack PC

## Shack Assistant Supervisor (Implemented — Not Field Validated)

**Files:** `modules/supervisor.py`, `modules/supervisor_config.py`

The supervisor is a thin orchestration layer that launches the existing WSJT-X and DX Cluster watchers as independent child processes. It does not merge their implementations or share an event loop.

### Process model

```
Shack Assistant Supervisor
        |
        +-- WSJT-X Station Watch (subprocess: watcher.py)
        |
        +-- DX Cluster Watch (subprocess: -m dxcluster_watcher)
```

Child commands use `sys.executable` with `PYTHONPATH` set to the repository root.

### Responsibilities

| Supervisor | Child watchers |
|------------|----------------|
| Start enabled sources | Source-specific network I/O |
| Prefix child stdout/stderr | Watchlist matching |
| Monitor process health | Notification delivery |
| Restart after unexpected exit | Cooldowns and parsing |
| Graceful shutdown | Reconnect logic (DX Cluster) |

### Configuration

Operator config: `~/.config/shack-assistant/supervisor.toml`

Example template: `config/supervisor.example.toml`

| Setting | Default | Purpose |
|---------|---------|---------|
| `restart_failed_sources` | `true` | Restart children after unexpected exit |
| `restart_delay_seconds` | `10` | Minimum delay before restart |
| `shutdown_timeout_seconds` | `10` | Wait before force-kill on shutdown |
| `sources.wsjtx.enabled` | `true` | Start WSJT-X watcher |
| `sources.dxcluster.enabled` | `true` | Start DX Cluster watcher (also requires `dxcluster.toml` enabled) |

The supervisor does not duplicate watchlist, ntfy, or DX Cluster connection settings.

### Duplicate protection

PID file: `~/.local/state/shack-assistant/supervisor.pid`

A second supervisor instance refuses to start when a valid PID is active. Stale PID files are recovered safely.

### Resource profile

- Two child Python processes (same as running watchers independently)
- Line-prefix reader threads with bounded buffering
- No GUI, database, or busy polling
- Suitable for 8 GB RAM shack PC

### Independent operation

Both watchers remain launchable for troubleshooting. Do not run standalone watchers alongside the supervisor.

## Data Files

| File | Role |
|------|------|
| `data/station-watch.example.csv` | Tracked example watchlist format (generic callsigns only) |
| `data/station-watch.csv` | Ignored operator watchlist (optional local path) |
| `data/watchlists/` | Ignored directory for event-specific operator lists |
| `~/.local/share/shack-assistant/watchlist.csv` | Default active watchlist (operator-owned, created locally) |
| `~/.config/shack-assistant/notifications.toml` | Operator notification settings (not in repo) |
| `config/notifications.example.toml` | Example ntfy configuration (tracked) |
| `~/.config/shack-assistant/dxcluster.toml` | Operator DX Cluster settings (not in repo) |
| `config/dxcluster.example.toml` | Example DX Cluster configuration (tracked) |
| `~/.config/shack-assistant/supervisor.toml` | Operator supervisor settings (not in repo) |
| `config/supervisor.example.toml` | Example supervisor configuration (tracked) |
| `~/.local/state/shack-assistant/supervisor.pid` | Supervisor PID lock (runtime) |
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

### DX Cluster Watch

- Python 3 `asyncio` (stdlib)
- Network access to configured cluster host/port
- `notify-send` and optional ntfy (shared notification config)

### Shack Assistant Supervisor

- Python 3 subprocess and threading (stdlib)
- No additional dependencies beyond child watcher requirements
