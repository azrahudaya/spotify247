#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-$PWD}"
PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "spotifyd setup only supports Linux."
  exit 1
fi

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  echo ".env was not found in $PROJECT_DIR"
  echo "Run python -m app.setup first."
  exit 1
fi

PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "python3 was not found."
  exit 1
fi

DEVICE_NAME_TOML="$(
  cd "$PROJECT_DIR"
  "$PYTHON_BIN" - <<'PY'
import json
import sys

from app.config import ConfigError, load_config

try:
    config = load_config()
except ConfigError as exc:
    print(exc, file=sys.stderr)
    raise SystemExit(1)

print(json.dumps(config.spotify_device_name or "Spotify VPS"))
PY
)"

CACHE_USER="$(id -un)"
PULSE_DIR="$HOME/.config/pulse"
SPOTIFYD_DIR="$HOME/.config/spotifyd"
PULSE_DEFAULT="$PULSE_DIR/default.pa"
SPOTIFYD_CONFIG="$SPOTIFYD_DIR/spotifyd.conf"

mkdir -p "$PULSE_DIR" "$SPOTIFYD_DIR" "$HOME/.cache/spotifyd"

if [[ ! -f "$PULSE_DEFAULT" && -f /etc/pulse/default.pa ]]; then
  cp /etc/pulse/default.pa "$PULSE_DEFAULT"
fi

touch "$PULSE_DEFAULT"

if ! grep -q "sink_name=spotify247" "$PULSE_DEFAULT"; then
  {
    echo "load-module module-always-sink"
    echo "load-module module-null-sink sink_name=spotify247 sink_properties=device.description=Spotify247"
    echo "set-default-sink spotify247"
  } >> "$PULSE_DEFAULT"
fi

cat > "$SPOTIFYD_CONFIG" <<EOF
[global]
device_name = $DEVICE_NAME_TOML
device_type = "speaker"
backend = "pulseaudio"
device = "spotify247"
cache_path = "$HOME/.cache/spotifyd"
bitrate = 160
volume_controller = "softvol"
autoplay = true
disable_discovery = true
use_mpris = false
EOF

pulseaudio -k >/dev/null 2>&1 || true
pulseaudio --start

echo "Configured PulseAudio null sink and spotifyd for $CACHE_USER."
echo "spotifyd config: $SPOTIFYD_CONFIG"
