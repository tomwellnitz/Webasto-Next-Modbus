#!/usr/bin/env bash
# Run the integration in a real Home Assistant against the virtual wallbox.
#
#   ./scripts/ha-smoke.sh                 # latest Home Assistant release
#   ./scripts/ha-smoke.sh --ha beta       # newest beta (or release, if newer)
#   ./scripts/ha-smoke.sh --ha 2026.11.0b3 --model unite
#
# Unlike the pytest suite this needs no pytest-homeassistant release for the
# target version, so it also works against a Home Assistant beta the
# day it is published. It installs Home Assistant into a throwaway venv,
# starts the virtual wallbox (from the project's own environment), loads a
# config entry for it and lets Home Assistant poll. It fails unless the entry
# sets up, polls succeed, the entities have values and nothing from the
# integration is logged as an error or a warning.
#
# Needs uv and Python 3.14. The first run takes a few minutes: Home
# Assistant installs the requirements of its own core integrations.
set -euo pipefail

HA_VERSION=latest
MODEL=next
POLLS=3
PORT=15020
TIMEOUT=600
INSTALL_TIMEOUT=900
KEEP=0

usage() {
  sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'
  echo "Options: --ha VERSION|latest|beta  --model next|unite  --polls N  --port N  --timeout SECONDS  --keep"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ha) HA_VERSION=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    --polls) POLLS=$2; shift 2 ;;
    --port) PORT=$2; shift 2 ;;
    --timeout) TIMEOUT=$2; shift 2 ;;
    --keep) KEEP=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

REPO=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/ha-smoke.XXXXXX")
VENV=$WORK/venv
CFG=$WORK/config
LOG=$WORK/home-assistant.log
SIM_PID=""
HA_PID=""

# Ask Home Assistant to stop, and kill it if it hasn't after a minute. SIGTERM,
# not SIGINT: a Home Assistant that is still starting up ignores SIGINT.
stop_ha() {
  [[ -n "$HA_PID" ]] || return 0
  kill -TERM "$HA_PID" 2>/dev/null || true
  for _ in $(seq 60); do
    kill -0 "$HA_PID" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$HA_PID" 2>/dev/null; then
    echo "⚠️  Home Assistant did not stop within 60 s, killing it" >&2
    kill -KILL "$HA_PID" 2>/dev/null || true
  fi
  wait "$HA_PID" 2>/dev/null || true
  HA_PID=""
}

show_logs() {
  echo "----- last 80 lines of the Home Assistant log -----" >&2
  tail -80 "$LOG" >&2 || true
  echo "----- virtual wallbox log -----" >&2
  tail -20 "$WORK/virtual-wallbox.log" >&2 || true
}

cleanup() {
  stop_ha
  if [[ -n "$SIM_PID" ]]; then
    kill "$SIM_PID" 2>/dev/null || true
    wait "$SIM_PID" 2>/dev/null || true
  fi
  if [[ $KEEP -eq 1 ]]; then
    echo "Kept $WORK"
  else
    rm -rf "$WORK"
  fi
}
trap cleanup EXIT

if [[ "$HA_VERSION" == beta ]]; then
  # Pin the newest Home Assistant version, pre-releases included, instead of
  # `--prerelease allow`: that would let every dependency resolve to an alpha
  # or beta too, which is not what a Home Assistant beta ships with.
  HA_VERSION=$(python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("https://pypi.org/pypi/homeassistant/json", timeout=30) as response:
    data = json.load(response)
uploads = [(files[0]["upload_time"], version) for version, files in data["releases"].items() if files]
print(max(uploads)[1])
PY
)
fi

echo "🏠 Installing Home Assistant ($HA_VERSION) into $VENV"
uv venv --quiet --python 3.14 "$VENV"
if [[ "$HA_VERSION" == latest ]]; then
  timeout "$INSTALL_TIMEOUT" uv pip install --quiet --python "$VENV/bin/python" homeassistant
else
  timeout "$INSTALL_TIMEOUT" uv pip install --quiet --python "$VENV/bin/python" "homeassistant==$HA_VERSION"
fi
"$VENV/bin/python" -c "from homeassistant.const import __version__; print('   Home Assistant', __version__)"

echo "⚙️  Writing the configuration ($MODEL on 127.0.0.1:$PORT)"
mkdir -p "$CFG/custom_components" "$CFG/.storage"
ln -s "$REPO/custom_components/webasto_next_modbus" "$CFG/custom_components/webasto_next_modbus"
cat > "$CFG/configuration.yaml" <<'YAML'
homeassistant:
  name: ha-smoke
recorder:
  commit_interval: 1
logger:
  default: warning
  logs:
    custom_components.webasto_next_modbus: debug
YAML
MINOR=$(sed -n 's/^CONFIG_ENTRY_MINOR_VERSION = \([0-9]*\)$/\1/p' "$REPO/custom_components/webasto_next_modbus/__init__.py")
cat > "$CFG/.storage/core.config_entries" <<JSON
{"version": 1, "minor_version": 1, "key": "core.config_entries", "data": {"entries": [
  {"entry_id": "01HASMOKEWEBASTOENTRY0000", "version": 1, "minor_version": ${MINOR:-1},
   "domain": "webasto_next_modbus", "title": "Wallbox",
   "data": {"host": "127.0.0.1", "port": $PORT, "unit_id": 255, "scan_interval": 10,
            "variant": "22kw", "model": "$MODEL"},
   "options": {}, "pref_disable_new_entities": false, "pref_disable_polling": false,
   "source": "user", "unique_id": "127.0.0.1-255", "disabled_by": null}
]}}
JSON

echo "🔌 Starting the virtual wallbox"
(cd "$REPO" && uv run --quiet python -m virtual_wallbox --port "$PORT" --zero-mode --log-level WARNING) \
  > "$WORK/virtual-wallbox.log" 2>&1 &
SIM_PID=$!
sleep 3

echo "🚀 Starting Home Assistant (waiting for $POLLS successful polls, at most ${TIMEOUT}s)"
"$VENV/bin/python" -m homeassistant --config "$CFG" > "$LOG" 2>&1 &
HA_PID=$!
deadline=$((SECONDS + TIMEOUT))
polls=0
while (( SECONDS < deadline )); do
  if ! kill -0 "$HA_PID" 2>/dev/null; then
    echo "❌ Home Assistant exited early" >&2
    show_logs
    exit 1
  fi
  polls=$(grep -c "Finished fetching Webasto Next.*success: True" "$LOG" || true)
  (( polls >= POLLS )) && break
  sleep 5
done
TIMED_OUT=0
if (( polls < POLLS )); then
  TIMED_OUT=1
  echo "⏱️  Timed out after ${TIMEOUT}s with $polls successful poll(s)" >&2
fi
stop_ha

echo "🔎 Checking the result"
if ! "$VENV/bin/python" "$REPO/scripts/ha_smoke_check.py" --config "$CFG" --log "$LOG" --polls "$POLLS" \
  || (( TIMED_OUT )); then
  show_logs
  exit 1
fi
