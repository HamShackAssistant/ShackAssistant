# Agent Instructions — Shack Assistant

Guidance for AI coding agents working in this repository.

## Project Summary

Shack Assistant is a Linux ham shack startup and station-assistant utility. The released v0.1 feature is a Bash launcher (`scripts/start-shack.sh`) that runs pre-flight checks and starts common shack applications.

## Before Making Changes

1. Read this file.
2. Read `docs/CURRENT_STATUS.md` for what is released vs. in development.
3. Read `docs/ARCHITECTURE.md` for how components fit together.
4. Inspect the relevant source files before editing.
5. Propose a plan and wait for approval before major changes.

## Development Principles

- Preserve working functionality.
- Prefer small, reviewable changes.
- Match existing naming, structure, and style.
- Do not remove working ham radio integrations without explicit approval.
- Do not claim features are complete in documentation unless they exist and are tracked in the repository.

## Repository Layout

```
scripts/start-shack.sh     # v0.1 Bash launcher (tracked)
modules/station_watch/     # Station Watch module (untracked, in development)
data/station-watch.csv     # Watchlist sample data (untracked, in development)
```

## What Not to Change Without Approval

- Ham radio application startup sequence in `scripts/start-shack.sh`
- UDP relay behavior in Station Watch (CQRLOG depends on unchanged packet relay)
- Existing integrations: FLrig, WSJT-X, GridTracker, CQRLOG

### CQRLOG

When testing WSJT-X integration:

- Verify live field population separately from automatic logging.
- Enable **Remote Mode for ADIF logger** before testing automatic log insertion.
- Do not assume the red "Offline" indicator indicates a failed integration;
  verify actual functionality first.

## After Coding

Report:

- Files changed
- Commands executed
- Tests run
- Brief implementation summary

## Commits and Pull Requests

- Only create commits or pull requests when the user explicitly asks.
- Do not push unless explicitly requested.
