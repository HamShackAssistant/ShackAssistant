# Operating Guide

## Startup Menu

Launch Shack Assistant with a single entry point:

```bash
./scripts/start-shack.sh
```

The startup screen presents an operating mode menu:

```text
==================================================
Shack Assistant Startup
==================================================

Select Operating Mode

1. Normal Operation
   Launch radio applications only

2. Station Hunting
   Launch radio applications
   Start Shack Assistant Supervisor
   (which launches enabled watcher sources)

3. Exit

Selection [1]:
```

Press **Enter** to accept the default (option 1).

### Option 1 — Normal Operation

- Launches FLrig, WSJT-X, GridTracker, and CQRLOG
- Does **not** start the supervisor or any watchers
- Displays `Station monitoring : Disabled`

Use this for ordinary operating sessions when you are not hunting specific watchlist stations.

### Option 2 — Station Hunting

- Launches the same radio applications with the same timing and sequencing
- Displays `Station monitoring : Enabled`
- Starts `PYTHONPATH=. python3 -m modules.supervisor` in the same terminal
- The supervisor launches whichever watcher sources are enabled in supervisor configuration

The supervisor uses its PID lock at `~/.local/state/shack-assistant/supervisor.pid` to refuse duplicate instances.

### Option 3 — Exit

Exits cleanly without launching applications or the supervisor.

### Desktop launchers

Launcher artwork is stored in the repository at:

| File | Purpose |
|------|---------|
| `icons/shack-assistant.png` | Official desktop launcher icon |
| `icons/Shack-Assistant.png` | Larger branding artwork (1024×1024 source) |

Point a single desktop entry at:

```bash
./scripts/start-shack.sh
```

Example `Icon` entry:

```text
Icon=/home/lbell/Projects/ShackAssistant/icons/shack-assistant.png
```

The operator's desktop entry at `~/.local/share/applications/shack-assistant.desktop` is a **local user file** (not version-controlled). Update it when the icon path or startup script changes.

The operator selects the operating mode at startup. Additional modes (Contest, POTA, Development) may be added to this menu in future releases.

### Troubleshooting: independent watchers

Run these only when diagnosing a single source. **Do not** run standalone watchers alongside the supervisor or duplicate alerts will occur.

```bash
python3 modules/station_watch/watcher.py
python3 -m modules.station_watch.dxcluster_watcher
```

## Shack Assistant Supervisor

### What it does

- Starts WSJT-X Station Watch and DX Cluster Watch as isolated child processes
- Uses existing configuration paths (watchlist, notifications, dxcluster)
- Monitors child health and restarts failed sources after a configurable delay
- Handles `Ctrl+C` / `SIGTERM` with graceful shutdown
- Prevents duplicate supervisor instances via `~/.local/state/shack-assistant/supervisor.pid`

### Configuration

Copy `config/supervisor.example.toml` to `~/.config/shack-assistant/supervisor.toml`.

| Source | Default | Requirement |
|--------|---------|-------------|
| WSJT-X | enabled | Active watchlist must exist |
| DX Cluster | enabled | `dxcluster.toml` must have `enabled = true` and valid host/callsign |

Disable a source in supervisor config without removing its dedicated config file.

### Commands

Normal operation:

```bash
PYTHONPATH=. python3 -m modules.supervisor
```

Supervisor diagnostics:

```bash
PYTHONPATH=. python3 -m modules.supervisor --verbose
```

Child watcher diagnostics (passes `--verbose` to both watchers):

```bash
PYTHONPATH=. python3 -m modules.supervisor --child-verbose
```

Disable automatic restart:

```bash
PYTHONPATH=. python3 -m modules.supervisor --no-restart
```

### Normal console output

Startup shows watchlist count, notification channels, and source state. After startup the supervisor stays quiet unless a child exits, restarts, fails to start, or shutdown begins. Child lines are prefixed by source.

### Shutdown

Press `Ctrl+C` or send `SIGTERM`. The supervisor terminates children, waits up to the configured timeout, then force-kills any remaining processes.

## WSJT-X Station Watch

- Listens on UDP `127.0.0.1:2238`
- Relays packets unchanged to `127.0.0.1:2239` for CQRLOG
- Uses `~/.local/share/shack-assistant/watchlist.csv`
- Sends desktop and optional ntfy notifications on watchlist matches
- Field validated: **VB7F** live FT8 detection (2026-07-11)

## DX Cluster Watch

### What it does

DX Cluster Watch connects to a DXSpider-compatible cluster node, receives live DX spots, compares spotted callsigns against the same watchlist used by Station Watch, and sends alerts through the shared notification pipeline.

### Dry-run procedure

```bash
python3 -m modules.station_watch.dxcluster_watcher --dry-run --verbose
```

Dry-run successfully matched **VC3F** during live testing on 2026-07-12. Dry-run mode:

- Connects normally
- Parses spots normally
- Compares against the watchlist
- Prints a concise match block
- Does **not** send desktop or ntfy notifications

Normal mode (without `--verbose`) is quiet and operator-focused. Parser diagnostics, ignored lines, login handling, and cooldown suppression appear only with `--verbose`.

### Live operation

1. Configure `~/.config/shack-assistant/dxcluster.toml` with `enabled = true`
2. Ensure ntfy is configured in `~/.config/shack-assistant/notifications.toml` if push alerts are desired
3. Run via supervisor or independently:

   ```bash
   python3 -m modules.station_watch.dxcluster_watcher
   ```

Field validated: **VC3F** live detection with desktop and ntfy notifications (2026-07-12).

### Bounded test mode

Exit after one valid DX spot line is received:

```bash
python3 -m modules.station_watch.dxcluster_watcher --once --verbose
```

## CQRLOG Notes

### Automatic Remote Mode for WSJT-X

After CQRLOG launches, Shack Assistant attempts to enable **Remote Mode for WSJT-X** automatically:

1. Wait up to 12 seconds for the CQRLOG main window (title contains `CQRLOG for Linux`, case-insensitive)
2. Activate the window with `wmctrl`
3. Send `Ctrl+J` once with `xdotool`

On success, startup prints:

```text
CQRLOG Remote Mode for WSJT-X : Enabled
```

### Dependencies

Automatic activation requires:

- `wmctrl`
- `xdotool`

Implementation: `modules/platform/linux.py`, invoked by `scripts/start-shack.sh`.

If either tool is missing, or the CQRLOG window is not found in time, startup continues with a warning. Enable Remote Mode for WSJT-X manually with **Ctrl+J** in the CQRLOG main window.

`Ctrl+J` toggles Remote Mode for WSJT-X. The startup script sends it at most once per run.

### Integration health

- Do not rely on the red Offline indicator alone to judge WSJT-X integration health

## Resource Use

All watch modules and the supervisor are lightweight background processes suitable for an 8 GB RAM shack PC. The supervisor adds two child processes and line-prefix threads with bounded output handling. DX Cluster Watch maintains a single TCP connection with bounded read buffers and no spot database.
