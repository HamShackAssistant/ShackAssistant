# Current Status

Last updated from repository inspection: 2026-07-11.

## Released — v0.1 Bash Launcher

**Status:** Tracked in git.

`scripts/start-shack.sh` is the only released feature. It:

1. Runs pre-flight checks for USB audio (via `pactl`) and USB/CAT serial devices (`/dev/ttyUSB*`)
2. Starts FLrig, WSJT-X, GridTracker, and CQRLOG
3. Logs results to `~/.shack-startup.log`

### Known assumptions in the launcher

- GridTracker binary path is hardcoded to `/opt/GridTracker2/gridtracker2`
- Audio detection looks for device names matching `USB.*Audio`, `CODEC`, or `Burr`
- Applications are started with `nohup` and verified via `pgrep`

## CQRLOG / WSJT-X Integration Notes

### Current Status

The following integration has been verified:

- FLrig controls the radio correctly.
- WSJT-X communicates with FLrig.
- GridTracker communicates with WSJT-X.
- CQRLOG receives live WSJT-X data (callsign, frequency, mode, DXCC, etc.).

### Automatic QSO Logging

Automatic logging from WSJT-X to CQRLOG requires CQRLOG to be placed into
**Remote Mode for ADIF logger**.

When this mode is enabled:

- Logging a completed QSO in WSJT-X automatically inserts the QSO into CQRLOG.
- Live WSJT-X fields continue to populate normally.

### Notes

The red **Offline** indicator in the CQRLOG New QSO window may remain displayed
even while live WSJT-X information is being received. Based on current testing,
this indicator alone should not be used to determine whether the WSJT-X
integration is functioning.

Future work:

- Verify the exact conditions that change the Offline indicator.
- Determine whether the indicator reflects WSJT-X heartbeat status,
  ADIF remote mode, or another internal CQRLOG state.

## In Development — Station Watch

**Status:** Untracked; not part of any release.

The following files exist locally but are not committed:

| File | Purpose |
|------|---------|
| `modules/station_watch/watcher.py` | UDP listener for WSJT-X decodes |
| `modules/station_watch/__init__.py` | Package marker (empty) |
| `modules/__init__.py` | Package marker (empty) |
| `data/station-watch.csv` | Sample callsign watchlist |

### What Station Watch does (from source)

- Listens on UDP `127.0.0.1:2238` for WSJT-X packets forwarded by GridTracker
- Parses WSJT-X status and decode messages
- Matches decoded message tokens against a CSV watchlist
- Sends desktop notifications via `notify-send`
- Relays original packets unchanged to UDP `127.0.0.1:2239` for CQRLOG
- Appends spot records to `logs/station-watch.jsonl`
- Reloads the watchlist automatically when the CSV file changes

### Sample watchlist entries

`data/station-watch.csv` contains three callsigns: WC5WC, W4C, VC3F.

## Not Present in Repository

- No `requirements.txt`, `pyproject.toml`, or package installer
- No automated tests
- No systemd service or desktop entry for Station Watch
- No integration of Station Watch into `start-shack.sh`
- No Windows support

## Documentation

| File | Status |
|------|--------|
| `README.md` | Present |
| `AGENTS.md` | Present |
| `docs/CURRENT_STATUS.md` | Present |
| `docs/ARCHITECTURE.md` | Present |
| `docs/ROADMAP.md` | Present |
