# Shack Assistant

An open-source intelligent amateur radio station assistant for Linux, with planned support for Windows.

## Current Version

**v0.3.0**

## Features

### Shack Launcher (v0.1)

- Starts FLrig, WSJT-X, GridTracker, and CQRLOG
- Checks USB audio and USB/CAT serial devices
- Logs startup status

### Station Watch (WSJT-X — field validated)

- Watches WSJT-X decodes against an operator-supplied CSV watchlist
- Desktop and optional ntfy notifications
- Unchanged UDP relay to CQRLOG

### DX Cluster Watch (field validated)

- Connects directly to a configured DX Cluster node over TCP
- No additional GUI required
- Uses the same watchlist and notification pipeline as Station Watch
- Field validated: **VC3F** live detection with desktop and ntfy (2026-07-12)

### Shack Assistant Supervisor (implemented — not field validated)

- Runs WSJT-X Station Watch and DX Cluster Watch from one command
- Child processes remain independent for troubleshooting
- Graceful shutdown, restart protection, and PID lock

## Quick Start

```bash
./scripts/start-shack.sh
python3 -m modules.supervisor
```

Troubleshooting (run watchers independently — do not run alongside the supervisor):

```bash
python3 modules/station_watch/watcher.py
python3 -m modules.station_watch.dxcluster_watcher
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Installation](docs/INSTALLATION.md)
- [Operating Guide](docs/OPERATING_GUIDE.md)
- [Known Good Configuration](docs/KNOWN_GOOD_CONFIGURATION.md)
- [Changelog](docs/CHANGELOG.md)

## License

GNU General Public License v3. See [LICENSE](LICENSE).
