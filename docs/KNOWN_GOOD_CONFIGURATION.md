# Known Good Configuration

Authoritative baseline for the Shack Assistant station environment. This document records the current, tested, and verified configuration. Use it as the reference point for development, troubleshooting, and system rebuilds.

**Policy:** Update this document only after a configuration change has been successfully tested in the shack.

---

## Table of Contents

- [Overview](#overview)
- [Validation Status](#validation-status)
- [Project Milestones](#project-milestones)
- [Platform and Launcher](#platform-and-launcher)
- [Application Stack](#application-stack)
- [Pre-Flight Checks](#pre-flight-checks)
- [Verified Integration Chain](#verified-integration-chain)
- [CQRLOG and WSJT-X Integration](#cqrlog-and-wsjt-x-integration)
- [Station Watch](#station-watch)
- [Operator Data Paths](#operator-data-paths)
- [Logging](#logging)
- [Future Verified Configuration Placeholders](#future-verified-configuration-placeholders)
- [Revision History](#revision-history)

---

## Overview

Shack Assistant **v0.3.0** is a Linux-based ham shack startup and station-assistant utility. The known-good baseline consists of:

- A Bash launcher that performs pre-flight checks and starts the shack application stack
- A verified digital-mode integration path: FLrig → WSJT-X → GridTracker → CQRLOG
- Station Watch for callsign monitoring, desktop alerts, and optional ntfy push notifications

---

## Validation Status

| Field | Value |
|-------|-------|
| Current Baseline | Verified |
| Last Field Validation | 2026-07-11 |
| Validation Event | Station Watch successfully detected watched station **VB7F** during live FT8 operation, resulting in a successful QSO |

### Verified Components

- [x] FLrig
- [x] WSJT-X
- [x] GridTracker
- [x] CQRLOG Remote Mode
- [x] Station Watch
- [x] Desktop Notifications
- [x] ntfy Notifications

---

## Project Milestones

### Version 0.3.0

- First successful Station Watch implementation
- CSV watchlist support
- Desktop notifications
- ntfy notifications
- First successful live detection: **VB7F**

---

## Platform and Launcher

| Item | Value |
|------|-------|
| Operating system | Linux |
| Project version | v0.3.0 |
| Launcher script | `scripts/start-shack.sh` |
| Launcher type | Bash |
| Startup log | `~/.shack-startup.log` |

Start the shack environment:

```bash
./scripts/start-shack.sh
```

The launcher:

1. Runs pre-flight checks
2. Starts FLrig, WSJT-X, GridTracker, and CQRLOG
3. Records results to the startup log

Station Watch is started separately and is not yet integrated into the launcher script.

---

## Application Stack

Applications are started in this order if not already running:

| Application | Start command | Startup wait |
|-------------|---------------|--------------|
| FLrig | `flrig` | 3 seconds |
| WSJT-X | `wsjtx` | 5 seconds |
| GridTracker | `/opt/GridTracker2/gridtracker2` | 3 seconds |
| CQRLOG | `cqrlog` | 3 seconds |

Each application is launched with `nohup` and verified with `pgrep`. Already-running instances are detected and skipped.

---

## Pre-Flight Checks

### USB Audio (PulseAudio)

The launcher uses `pactl` when available to:

- Report the default audio sink and source
- Detect USB audio output devices matching `USB.*Audio`, `CODEC`, or `Burr`
- Detect USB audio input devices matching the same patterns

If `pactl` is not available, the audio check is skipped with a warning.

### USB/CAT Serial

The launcher checks for USB serial devices at:

```text
/dev/ttyUSB*
```

A warning is logged if no matching device is found.

---

## Verified Integration Chain

The following integration has been verified:

- FLrig controls the radio correctly
- WSJT-X communicates with FLrig
- GridTracker communicates with WSJT-X
- CQRLOG receives live WSJT-X data (callsign, frequency, mode, DXCC, and related fields)

```
Radio ◄── CAT ──► FLrig ◄──► WSJT-X ◄──► GridTracker
                              │
                              └── live data ──► CQRLOG
```

---

## CQRLOG and WSJT-X Integration

### Live Field Population

CQRLOG receives live WSJT-X fields during operation. Verify live field population separately from automatic QSO logging.

### Automatic QSO Logging

Automatic logging from WSJT-X to CQRLOG requires CQRLOG to be placed into **Remote Mode for ADIF logger**.

When this mode is enabled:

- Logging a completed QSO in WSJT-X automatically inserts the QSO into CQRLOG
- Live WSJT-X fields continue to populate normally

### Offline Indicator

The red **Offline** indicator in the CQRLOG New QSO window may remain displayed even while live WSJT-X information is being received.

Based on current testing, this indicator alone should **not** be used to determine whether the WSJT-X integration is functioning. Verify actual field population and logging behavior instead.

### Open Items

- Verify the exact conditions that change the Offline indicator
- Determine whether the indicator reflects WSJT-X heartbeat status, ADIF remote mode, or another internal CQRLOG state

---

## Station Watch

Station Watch has been field-validated as part of the v0.3.0 baseline. On 2026-07-11, it detected watched station **VB7F** during live FT8 operation, issued notifications, and the operator completed a successful QSO.

Station Watch is not yet integrated into `scripts/start-shack.sh`. Start it separately after the shack application stack is running.

### UDP Topology

| Endpoint | Default | Role |
|----------|---------|------|
| Listen | `127.0.0.1:2238` | Receives WSJT-X packets forwarded by GridTracker |
| Relay | `127.0.0.1:2239` | Forwards original packets unchanged to CQRLOG |

### Start Command

```bash
python3 modules/station_watch/watcher.py --watchlist data/station-watch.example.csv
```

Default watchlist path:

```text
~/.local/share/shack-assistant/watchlist.csv
```

Example watchlist format (repository):

```text
data/station-watch.example.csv
```

### Notifications

| Channel | Configuration | Status |
|---------|---------------|--------|
| Desktop | `notify-send` (enabled when a match occurs) | Verified |
| ntfy push | Optional; `~/.config/shack-assistant/notifications.toml` | Verified |

Example ntfy configuration template:

```text
config/notifications.example.toml
```

Copy the example to the operator config path and edit locally. Do not commit operator notification settings.

### Notification Architecture

```
Station Match
    ├── Desktop Notification (notify-send)
    └── ntfy Push Notification (optional)
```

### Defaults

| Setting | Value |
|---------|-------|
| Per-callsign alert cooldown | 900 seconds |
| Spot log | `logs/station-watch.jsonl` |

---

## Operator Data Paths

These paths are operator-owned and must not be committed to the repository:

| Path | Purpose |
|------|---------|
| `~/.local/share/shack-assistant/watchlist.csv` | Active Station Watch watchlist |
| `~/.config/shack-assistant/notifications.toml` | Notification settings |
| `data/station-watch.csv` | Optional local watchlist (ignored by git) |
| `data/watchlists/` | Optional per-event watchlist directory (ignored by git) |

---

## Logging

| Log | Path | Created by |
|-----|------|------------|
| Shack startup | `~/.shack-startup.log` | `scripts/start-shack.sh` |
| Station Watch spots | `logs/station-watch.jsonl` | Station Watch watcher |

---

## Future Verified Configuration Placeholders

Add new subsections below as additional configurations are tested and confirmed.

### Radio Hardware

<!-- Placeholder: document verified radio model, CAT port, and rig-specific settings after testing. -->

_To be added after verification._

### Audio Device Mapping

<!-- Placeholder: document verified PulseAudio sink/source names after testing. -->

_To be added after verification._

### GridTracker UDP Forwarding

<!-- Placeholder: document verified GridTracker UDP forwarding settings after testing. -->

_To be added after verification._

### Network and Remote Access

<!-- Placeholder: document additional remote notification providers after testing. -->

_To be added after verification._

---

## Revision History

| Date | Revision | Summary | Verified by |
|------|----------|---------|-------------|
| 2026-07-12 | 1.0 | Initial known-good baseline: v0.1 launcher, application stack, pre-flight checks, verified FLrig/WSJT-X/GridTracker/CQRLOG integration, CQRLOG ADIF remote-mode notes, Station Watch in-development defaults | Station testing |
| 2026-07-12 | 1.1 | Updated to v0.3.0; added Validation Status and Project Milestones; documented VB7F live FT8 detection and successful QSO; marked Station Watch, desktop notifications, and ntfy as verified | Station testing |
