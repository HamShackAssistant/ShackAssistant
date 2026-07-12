#!/usr/bin/env bash

set -euo pipefail

APP_NAME="Shack Assistant"
LOGFILE="$HOME/.shack-startup.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

log() {
  echo "$(date '+%F %T') - $*" >> "$LOGFILE"
}

ok() {
  echo "✓ $1"
  log "OK - $1"
}

warn() {
  echo "⚠ $1"
  log "WARN - $1"
}

fail() {
  echo "✗ $1"
  log "FAIL - $1"
}

start_app() {
  local name="$1"
  local cmd="$2"
  local wait_time="$3"

  if pgrep -f "$cmd" >/dev/null 2>&1; then
    ok "$name already running"
  else
    echo -n "Starting $name..."
    nohup bash -c "$cmd" >/dev/null 2>&1 &
    sleep "$wait_time"

    if pgrep -f "$cmd" >/dev/null 2>&1; then
      echo " OK"
      log "Started $name"
    else
      echo " FAILED"
      fail "$name did not start"
    fi
  fi
}

check_audio() {
  echo
  echo "Audio check:"

  if pactl info >/dev/null 2>&1; then
    DEFAULT_SINK=$(pactl info | awk -F': ' '/Default Sink/ {print $2}')
    DEFAULT_SOURCE=$(pactl info | awk -F': ' '/Default Source/ {print $2}')

    echo "Default output: $DEFAULT_SINK"
    echo "Default input : $DEFAULT_SOURCE"

    if pactl list short sinks | grep -qi "USB.*Audio\|CODEC\|Burr"; then
      ok "USB audio output device detected"
    else
      warn "USB audio output device not detected"
    fi

    if pactl list short sources | grep -qi "USB.*Audio\|CODEC\|Burr"; then
      ok "USB audio input device detected"
    else
      warn "USB audio input device not detected"
    fi
  else
    warn "pactl not available; skipping audio check"
  fi
}

check_cat_usb() {
  echo
  echo "USB/CAT check:"

  if ls /dev/ttyUSB* >/dev/null 2>&1; then
    ok "USB serial device found: $(ls /dev/ttyUSB* | xargs)"
  else
    warn "No /dev/ttyUSB device found"
  fi
}

show_operating_mode_menu() {
  clear
  echo "=================================================="
  echo "Shack Assistant Startup"
  echo "=================================================="
  echo
  echo "Select Operating Mode"
  echo
  echo "1. Normal Operation"
  echo "   Launch radio applications only"
  echo
  echo "2. Station Hunting"
  echo "   Launch radio applications"
  echo "   Start Shack Assistant Supervisor"
  echo "   (which launches enabled watcher sources)"
  echo
  echo "3. Exit"
  echo
}

read_operating_mode() {
  local selection=""

  read -r -p "Selection [1]: " selection
  selection="${selection:-1}"

  case "$selection" in
    1)
      echo "normal"
      ;;
    2)
      echo "hunting"
      ;;
    3)
      echo "exit"
      ;;
    *)
      echo "normal"
      ;;
  esac
}

show_operating_mode_menu
OPERATING_MODE="$(read_operating_mode)"

if [[ "$OPERATING_MODE" == "exit" ]]; then
  exit 0
fi

clear
echo "================================="
echo "        SHACK ASSISTANT"
echo "================================="
echo
echo "Starting shack environment..."
echo "Log: $LOGFILE"
echo

echo "================================="
echo " Pre-flight checks"
echo "================================="

check_audio
check_cat_usb

echo
echo "================================="
echo " Launching applications"
echo "================================="

start_app "FLrig" "flrig" 3
start_app "WSJT-X" "wsjtx" 5
start_app "GridTracker" "/opt/GridTracker2/gridtracker2" 3
start_app "CQRLOG" "cqrlog" 3

echo
echo "================================="
echo " Shack startup complete"
echo "================================="
echo
echo "Shack applications started."

if [[ "$OPERATING_MODE" == "hunting" ]]; then
  echo "Station monitoring : Enabled"
else
  echo "Station monitoring : Disabled"
fi

echo
echo "Welcome back, BellDog."
echo "73 de Goose"
echo

if [[ "$OPERATING_MODE" == "hunting" ]]; then
  echo "Starting Shack Assistant supervisor..."
  echo
  cd "$PROJECT_ROOT"
  export PYTHONPATH=.
  exec python3 -m modules.supervisor
fi

read -p "Press Enter to close this window..."
