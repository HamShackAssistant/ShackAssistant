#!/usr/bin/env bash

APP_NAME="Shack Assistant"
LOGFILE="$HOME/.shack-startup.log"

clear
echo "================================="
echo "        SHACK ASSISTANT"
echo "================================="
echo
echo "Starting shack environment..."
echo "Log: $LOGFILE"
echo

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

if [[ "${SHACK_MONITORING:-0}" == "1" ]]; then
  echo "Station monitoring: Enabled"
else
  echo "Station monitoring: Disabled"
fi

echo
echo "Welcome back, BellDog."
echo "73 de Goose"
echo

if [[ "${SHACK_MONITORING:-0}" != "1" ]]; then
  read -p "Press Enter to close this window..."
fi
