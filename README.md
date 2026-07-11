# Shack Assistant

An open-source intelligent amateur radio station assistant for Linux, with planned support for Windows.

## Current Features

v0.1 is a Bash launcher that prepares and starts the shack environment:

- Starts FLrig
- Starts WSJT-X
- Starts GridTracker
- Starts CQRLOG
- Checks USB audio
- Checks USB/CAT serial devices
- Logs startup status

## Current Version

v0.1 - Bash launcher

## Usage

```bash
./scripts/start-shack.sh
```

Startup status is logged to `~/.shack-startup.log`.

## Requirements

- Linux with Bash
- PulseAudio (`pactl`) for audio checks (optional; skipped if unavailable)
- Installed shack applications: FLrig, WSJT-X, GridTracker, CQRLOG

GridTracker is expected at `/opt/GridTracker2/gridtracker2`.

## License

GNU General Public License v3. See [LICENSE](LICENSE).
