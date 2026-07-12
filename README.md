# Shack Assistant

An open-source intelligent amateur radio station assistant for Linux, with planned support for Windows.

## Current Version

**v0.3.0**

## Features

### Shack Launcher (v0.1)

- Starts FLrig, WSJT-X, GridTracker, and CQRLOG
- Checks USB audio and USB/CAT serial devices
- Automatically enables CQRLOG Remote Mode for WSJT-X when `wmctrl` and `xdotool` are installed
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
```

The startup menu offers:

1. **Normal Operation** — radio applications only (default)
2. **Station Hunting** — radio applications plus Shack Assistant supervisor
3. **Exit**

Use station hunting only when monitoring specific watchlist stations. For ordinary QSOs, choose normal operation.

### CQRLOG Remote Mode automation

Automatic CQRLOG Remote Mode for WSJT-X requires:

```bash
wmctrl
xdotool
```

Install on Debian/Ubuntu:

```bash
sudo apt install wmctrl xdotool
```

Without these tools, startup continues normally but you must press **Ctrl+J** manually in the CQRLOG main window.

Launcher icon: `icons/shack-assistant.png` (branding source: `icons/Shack-Assistant.png`).

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
