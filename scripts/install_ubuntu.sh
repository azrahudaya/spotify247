#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-$HOME/spotify247}"
SPOTIFYD_RELEASE_FLAVOR="${SPOTIFYD_RELEASE_FLAVOR:-default}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This script only supports Linux/Ubuntu."
  exit 1
fi

sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  curl \
  ca-certificates \
  jq \
  pulseaudio \
  pulseaudio-utils

mkdir -p "$PROJECT_DIR"
if [[ ! -f "$PROJECT_DIR/requirements.txt" ]]; then
  echo "requirements.txt was not found in $PROJECT_DIR"
  echo "Run this script from the project root or pass the project root as the first argument."
  exit 1
fi

python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/pip" install --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

if command -v spotifyd >/dev/null 2>&1; then
  echo "spotifyd is already installed: $(command -v spotifyd)"
  exit 0
fi

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) ASSET_ARCH="x86_64" ;;
  aarch64 | arm64) ASSET_ARCH="aarch64" ;;
  *)
    echo "Architecture $ARCH is not supported by the automatic installer. Install spotifyd manually from the GitHub release page."
    exit 1
    ;;
esac

ASSET_NAME="spotifyd-linux-${ASSET_ARCH}-${SPOTIFYD_RELEASE_FLAVOR}.tar.gz"
RELEASE_JSON="$(curl -fsSL https://api.github.com/repos/Spotifyd/spotifyd/releases/latest)"
DOWNLOAD_URL="$(printf '%s' "$RELEASE_JSON" | jq -r --arg ASSET_NAME "$ASSET_NAME" '.assets[] | select(.name == $ASSET_NAME) | .browser_download_url' | head -n1)"

if [[ -z "$DOWNLOAD_URL" ]]; then
  echo "Could not find a spotifyd asset for $ASSET_NAME"
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

curl -fsSL "$DOWNLOAD_URL" -o "$TMP_DIR/spotifyd.tar.gz"
tar -xzf "$TMP_DIR/spotifyd.tar.gz" -C "$TMP_DIR"
SPOTIFYD_BIN="$(find "$TMP_DIR" -type f -name spotifyd | head -n1)"

if [[ -z "$SPOTIFYD_BIN" ]]; then
  echo "spotifyd binary was not found after extracting the asset."
  exit 1
fi

sudo install -m 0755 "$SPOTIFYD_BIN" /usr/local/bin/spotifyd

echo "spotifyd was installed to /usr/local/bin/spotifyd"
