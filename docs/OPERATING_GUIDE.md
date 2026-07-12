# Operating Guide

## Startup Order

1. Start the shack application stack:

   ```bash
   ./scripts/start-shack.sh
   ```

2. Start Shack Assistant Supervisor (recommended):

   ```bash
   PYTHONPATH=. python3 -m modules.supervisor
   ```

The supervisor starts enabled watcher processes in subprocesses, prefixes their output (`[WSJT-X]`, `[DX Cluster]`), and keeps both sources running from one terminal.

### Troubleshooting: independent watchers

Run these only when diagnosing a single source. **Do not** run standalone watchers alongside the supervisor or duplicate alerts will occur.

```bash
python3 modules/station_watch/watcher.py
python3 -m modules.station_watch.dxcluster_watcher
```

### Integrating with `start-shack.sh`

The launcher does not yet start the supervisor automatically. After field validation, add this line after the application startup block (review before applying):

```bash
start_app "Shack Assistant Supervisor" "cd $(dirname "$0")/.. && PYTHONPATH=. python3 -m modules.supervisor" 2
```

Note: backgrounding the supervisor with `nohup` hides prefixed child output. Prefer a dedicated terminal for normal supervised operation.

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

- Enable **Remote Mode for ADIF logger** for automatic WSJT-X QSO logging
- Do not rely on the red Offline indicator alone to judge WSJT-X integration health

## Resource Use

All watch modules and the supervisor are lightweight background processes suitable for an 8 GB RAM shack PC. The supervisor adds two child processes and line-prefix threads with bounded output handling. DX Cluster Watch maintains a single TCP connection with bounded read buffers and no spot database.
