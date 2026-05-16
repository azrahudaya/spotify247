#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-$PWD}"
PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
SERVICE_DIR="$HOME/.config/systemd/user"
SKIP_SPOTIFYD="${SPOTIFY247_SKIP_SPOTIFYD:-0}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "systemd service install only supports Linux."
  exit 1
fi

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  echo ".env was not found in $PROJECT_DIR"
  echo "Run python -m app.setup first."
  exit 1
fi

if [[ ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  echo "Virtualenv was not found at $PROJECT_DIR/.venv"
  echo "Run scripts/install_ubuntu.sh \"$PROJECT_DIR\" first."
  exit 1
fi

mkdir -p "$SERVICE_DIR"

if [[ "$SKIP_SPOTIFYD" != "1" ]]; then
  cat > "$SERVICE_DIR/spotifyd.service" <<EOF
[Unit]
Description=spotifyd headless Spotify Connect daemon
After=network-online.target pulseaudio.service
Wants=network-online.target

[Service]
Type=simple
ExecStartPre=/bin/sh -lc 'pulseaudio --check >/dev/null 2>&1 || pulseaudio --start'
ExecStart=/usr/local/bin/spotifyd --no-daemon --config-path %h/.config/spotifyd/spotifyd.conf
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
fi

cat > "$SERVICE_DIR/telegram-spotify-bot.service" <<EOF
[Unit]
Description=Telegram Spotify controller bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/.venv/bin/python -m app.main
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

if command -v loginctl >/dev/null 2>&1; then
  loginctl enable-linger "$USER" >/dev/null 2>&1 || true
fi

systemctl --user daemon-reload

if [[ "$SKIP_SPOTIFYD" != "1" ]]; then
  systemctl --user enable --now spotifyd.service
fi

systemctl --user enable --now telegram-spotify-bot.service

echo "Installed systemd user services in $SERVICE_DIR"
