# Installation

Shack Assistant runs on Linux. This guide covers the launcher, WSJT-X Station Watch, and DX Cluster Watch.

## Requirements

- Linux with Bash
- Python 3 (stdlib only for Station Watch modules)
- PulseAudio (`pactl`) for launcher audio checks (optional)
- Installed shack applications: FLrig, WSJT-X, GridTracker, CQRLOG
- `notify-send` (libnotify) for desktop notifications

GridTracker is expected at `/opt/GridTracker2/gridtracker2`.

## Launcher

```bash
./scripts/start-shack.sh
```

Startup status is logged to `~/.shack-startup.log`.

## Watchlist

Copy the example watchlist and edit it locally:

```bash
mkdir -p ~/.local/share/shack-assistant
cp data/station-watch.example.csv ~/.local/share/shack-assistant/watchlist.csv
```

## Notification Settings (Optional)

```bash
mkdir -p ~/.config/shack-assistant
cp config/notifications.example.toml ~/.config/shack-assistant/notifications.toml
```

Edit the copied file to enable ntfy if desired.

## DX Cluster Settings (Optional)

DX Cluster Watch connects directly to a configured cluster node over TCP. No additional GUI is required.

```bash
mkdir -p ~/.config/shack-assistant
cp config/dxcluster.example.toml ~/.config/shack-assistant/dxcluster.toml
```

Edit the copied file:

```toml
[dxcluster]
enabled = true
host = "your.cluster.host"
port = 7300
callsign = "YOURCALL"
reconnect_delay_seconds = 30
alert_cooldown_seconds = 900
```

Do not commit operator configuration files.

## Supervisor Settings (Optional)

The supervisor orchestrates both watchers from one terminal. Missing configuration uses safe defaults.

```bash
cp config/supervisor.example.toml ~/.config/shack-assistant/supervisor.toml
```

Example:

```toml
[supervisor]
restart_failed_sources = true
restart_delay_seconds = 10
shutdown_timeout_seconds = 10

[sources.wsjtx]
enabled = true

[sources.dxcluster]
enabled = true
```

DX Cluster still requires its own `dxcluster.toml` with `enabled = true`. The supervisor does not duplicate cluster host, port, callsign, ntfy, or watchlist settings.

## Python Module Launch

From the repository root:

**Supervisor (recommended for normal operation):**

```bash
PYTHONPATH=. python3 -m modules.supervisor
```

**Independent watchers (troubleshooting only — do not run alongside the supervisor):**

```bash
python3 modules/station_watch/watcher.py
python3 -m modules.station_watch.dxcluster_watcher
```

## Tests

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```
