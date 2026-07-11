# Roadmap

Items below are derived from repository contents and stated project goals. Nothing here is committed work unless noted.

## Done — v0.1

- [x] Bash launcher with pre-flight checks (`scripts/start-shack.sh`)
- [x] USB audio and CAT serial detection
- [x] Startup of FLrig, WSJT-X, GridTracker, CQRLOG
- [x] Startup logging to `~/.shack-startup.log`

## In Progress — Station Watch (untracked)

Source exists locally but is not committed or integrated:

- [ ] Commit Station Watch module and example watchlist (`data/station-watch.example.csv`)
- [ ] Integrate Station Watch into shack startup (launcher or separate service)
- [ ] Document GridTracker UDP forwarding configuration
- [ ] Verify end-to-end flow: GridTracker → watcher → CQRLOG

### Station Watch capabilities already implemented in source

- WSJT-X UDP packet parsing (status and decode messages)
- CSV watchlist with hot reload (operator-owned external files; event-agnostic)
- Desktop notifications via `notify-send`
- Unchanged packet relay to CQRLOG
- JSONL spot logging with cooldown per callsign

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
