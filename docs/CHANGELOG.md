# Changelog

## v0.3.0 — 2026-07-11

### Field Validated

- WSJT-X Station Watch
- Desktop notifications
- ntfy notifications
- First successful live detection: **VB7F** during FT8 operation

### Added

- Station Watch WSJT-X UDP watcher with watchlist matching
- CSV watchlist support with hot reload
- Rich desktop and ntfy notifications
- Known-good configuration documentation

## Unreleased

### Added

- Shack Assistant Supervisor (`modules/supervisor.py`)
- Supervisor configuration (`config/supervisor.example.toml`)
- Unit tests for supervisor orchestration, restart, shutdown, and PID lock

### Added (DX Cluster Watch)

- DX Cluster Watch TCP client (`modules/station_watch/dxcluster_watcher.py`)
- DXSpider-style spot parser with high-confidence FT8/FT4 frequency inference
- DX Cluster configuration (`config/dxcluster.example.toml`)
- Shared `NotificationDispatcher.notify_alert()` dispatch results
- Quiet operator-focused terminal output
- Unit tests for DX Cluster parsing and session behavior
- Installation and operating guides

### Status

- DX Cluster Watch field validated: **VC3F** live detection with desktop and ntfy (2026-07-12)
- Shack Assistant Supervisor implemented; not field validated until both sources run simultaneously under it with a real alert received

## v0.1

### Added

- Bash launcher (`scripts/start-shack.sh`)
- USB audio and CAT serial pre-flight checks
- Startup of FLrig, WSJT-X, GridTracker, and CQRLOG
