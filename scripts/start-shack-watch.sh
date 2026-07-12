#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

export SHACK_MONITORING=1

bash "$SCRIPT_DIR/start-shack.sh"

echo
echo "Starting Shack Assistant supervisor..."
echo

cd "$PROJECT_ROOT"
export PYTHONPATH=.

exec python3 -m modules.supervisor
