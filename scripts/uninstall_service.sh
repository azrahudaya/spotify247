#!/usr/bin/env bash
set -euo pipefail

SERVICE_DIR="$HOME/.config/systemd/user"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "systemd service uninstall only supports Linux."
  exit 1
fi

systemctl --user disable --now telegram-spotify-bot.service >/dev/null 2>&1 || true
systemctl --user disable --now spotifyd.service >/dev/null 2>&1 || true

rm -f "$SERVICE_DIR/telegram-spotify-bot.service"
rm -f "$SERVICE_DIR/spotifyd.service"

systemctl --user daemon-reload

echo "Removed spotify247 systemd user services."
