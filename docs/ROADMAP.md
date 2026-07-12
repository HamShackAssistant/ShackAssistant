# Roadmap

Items below are derived from repository contents and stated project goals. Nothing here is committed work unless noted.

## Done — v0.3.0

- [x] Bash launcher with pre-flight checks (`scripts/start-shack.sh`)
- [x] USB audio and CAT serial detection
- [x] Startup of FLrig, WSJT-X, GridTracker, CQRLOG
- [x] Station Watch (WSJT-X) with CSV watchlist
- [x] Desktop and ntfy notifications
- [x] Field validation: VB7F live FT8 detection

## In Progress — Shack Assistant Supervisor

Implemented but not field validated:

- [x] Subprocess orchestration for WSJT-X and DX Cluster watchers
- [x] Source enable/disable configuration
- [x] Child output prefixing (`[WSJT-X]`, `[DX Cluster]`, `[Supervisor]`)
- [x] Restart protection and graceful shutdown
- [x] PID lock for duplicate-instance prevention
- [x] Unit tests
- [ ] Field validation: both sources running simultaneously with real alert received
- [ ] Integrate into `scripts/start-shack.sh` (documented; not applied)

## Done — DX Cluster Watch

- [x] TCP cluster client with asyncio
- [x] DXSpider-style spot parser
- [x] Shared watchlist and notification pipeline
- [x] Dry-run mode
- [x] Unit tests
- [x] Field validation: VC3F live detection with desktop and ntfy (2026-07-12)

## Earlier — v0.1

## Planned — From Project Description

The README incoming description mentions Windows support. No Windows code or scripts exist in the repository.

- [ ] Windows support (not started)

## Likely Next Steps (inferred, not specified in code)

These are reasonable follow-ons based on gaps in the current repository. They are not confirmed priorities.

- Packaging or install script for the launcher and watcher
- Configuration file for app paths, UDP ports, and watchlist location
- Manual watchlist entry UI or CLI (CSV editing is the current workflow)
- systemd user service for Station Watch
- Tests for WSJT-X packet parsing and watchlist matching
- Remove hardcoded GridTracker path from the launcher

## Out of Scope (not evidenced in repository)

No source or docs reference these; they are not current goals unless added explicitly:

- Web UI or dashboard
- Database-backed logging
- Integration beyond FLrig / WSJT-X / GridTracker / CQRLOG
