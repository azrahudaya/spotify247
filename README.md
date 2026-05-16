# spotify247

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-22.04%20%7C%2024.04-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com/)
[![Spotify](https://img.shields.io/badge/Spotify-Premium-1DB954?logo=spotify&logoColor=white)](https://www.spotify.com/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot%20API-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![Deployment](https://img.shields.io/badge/Deployment-systemd-222222?logo=systemd&logoColor=white)](https://systemd.io/)

`spotify247` is a self-hosted Telegram controller for Spotify. It can run as a portable controller on any machine with Python, or as a full 24/7 player on an Ubuntu/Debian VPS with `spotifyd`.

## What It Does

- control Spotify from Telegram
- show a playback panel with inline buttons
- play, pause, skip, go back, repeat, shuffle, and change volume
- search tracks from Telegram and play them instantly
- restrict controls to selected Telegram user IDs

## Modes

| Mode | Best For | Support |
| --- | --- | --- |
| Controller only | Laptop, desktop, Replit, Railway, Render, generic Python hosts | Uses any online Spotify device |
| 24/7 VPS player | Ubuntu/Debian VPS | Runs `spotifyd`, PulseAudio, and systemd services |

Controller-only mode does not need `spotifyd`. Leave `SPOTIFY_DEVICE_NAME` empty and the bot will use the active Spotify device, or the first controllable online device.

The full 24/7 player mode needs a Linux host because Spotify playback is handled by `spotifyd` and PulseAudio.

## Architecture

```text
Telegram
  -> spotify247 bot
  -> Spotify Web API
  -> active Spotify device
```

For VPS playback:

```text
Telegram
  -> spotify247 bot
  -> Spotify Web API
  -> spotifyd
  -> PulseAudio null sink
```

## Repository Layout

```text
app/
  bot.py
  config.py
  doctor.py
  main.py
  setup.py
  spotify.py
  telegram_api.py
deploy/
  spotifyd/
  systemd/
scripts/
  install_service.sh
  install_ubuntu.sh
  setup_spotifyd.sh
  spotify_auth.py
  uninstall_service.sh
```

## Requirements

Controller-only:

- Python 3.10+
- Spotify Premium account
- Telegram bot token from `@BotFather`
- Spotify Developer app
- at least one online Spotify device

Full VPS player:

- Ubuntu 22.04, Ubuntu 24.04, or a close Debian-based server
- Python 3.10+
- `spotifyd`
- PulseAudio
- systemd user services
- Spotify Premium account

Spotify playback control requires a user OAuth refresh token. Client credentials alone are not enough.

## Quick Start: Controller Only

This mode is the easiest way to let people clone the repo and control Spotify from Telegram.

```bash
git clone https://github.com/yourname/spotify247.git
cd spotify247
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.setup
python -m app.doctor
python -m app.main
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.setup
python -m app.doctor
python -m app.main
```

If `SPOTIFY_DEVICE_NAME` is empty, open Spotify on any device first. The bot will control that device.

## Quick Start: Ubuntu VPS Player

Use this when the server itself should appear as a Spotify Connect device and keep running 24/7.

```bash
git clone https://github.com/yourname/spotify247.git
cd spotify247
chmod +x scripts/*.sh
./scripts/install_ubuntu.sh "$PWD"
source .venv/bin/activate
python -m app.setup
./scripts/setup_spotifyd.sh "$PWD"
```

Then authenticate `spotifyd`. `spotifyd` uses its own login flow and does not use the bot refresh token.

```bash
spotifyd authenticate
```

After `spotifyd` is authenticated:

```bash
python -m app.doctor
./scripts/install_service.sh "$PWD"
```

Useful service commands:

```bash
systemctl --user status spotifyd.service
systemctl --user status telegram-spotify-bot.service
journalctl --user -u spotifyd.service -f
journalctl --user -u telegram-spotify-bot.service -f
```

To remove the services:

```bash
./scripts/uninstall_service.sh
```

## Setup Wizard

Run:

```bash
python -m app.setup
```

The wizard asks for:

- Telegram bot token
- allowed Telegram user IDs
- Spotify client ID
- Spotify client secret
- Spotify redirect URI
- optional Spotify device name
- Spotify market
- bot behavior settings

It can also generate `SPOTIFY_REFRESH_TOKEN` through the Spotify OAuth flow.

## Health Check

Run:

```bash
python -m app.doctor
```

It checks:

- `.env`
- `.env` file permissions on Linux
- Telegram bot token
- allowed user IDs
- Spotify refresh token
- Spotify device discovery
- Linux host tools, services, PulseAudio sink, and linger state for full player mode

## Environment Variables

| Variable | Description | Required |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from `@BotFather` | Yes |
| `TELEGRAM_ALLOWED_USER_IDS` | Comma-separated Telegram user IDs allowed to control the bot | Recommended |
| `SPOTIFY_CLIENT_ID` | Spotify app client ID | Yes |
| `SPOTIFY_CLIENT_SECRET` | Spotify app client secret | Yes |
| `SPOTIFY_REFRESH_TOKEN` | Spotify user refresh token | Yes |
| `SPOTIFY_REDIRECT_URI` | OAuth redirect URI used during setup | Recommended |
| `SPOTIFY_DEVICE_NAME` | Target Spotify device name. Leave empty for auto device mode | No |
| `SPOTIFY_MARKET` | Market code for search, such as `ID` or `US` | No |
| `BOT_POLL_TIMEOUT_SECONDS` | Telegram polling timeout, 5-50 seconds | No |
| `BOT_SEARCH_LIMIT` | Search result limit, 1-10 | No |
| `LOG_LEVEL` | Python log level | No |

Example:

```env
TELEGRAM_BOT_TOKEN=1234567890:replace_me
TELEGRAM_ALLOWED_USER_IDS=123456789
SPOTIFY_CLIENT_ID=replace_me
SPOTIFY_CLIENT_SECRET=replace_me
SPOTIFY_REFRESH_TOKEN=replace_me
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
SPOTIFY_DEVICE_NAME=
SPOTIFY_MARKET=ID
BOT_POLL_TIMEOUT_SECONDS=30
BOT_SEARCH_LIMIT=5
LOG_LEVEL=INFO
```

## Telegram Commands

- `/panel`
- `/status`
- `/now`
- `/search <query>`
- `/play`
- `/pause`
- `/next`
- `/prev`
- `/repeat`
- `/repeat track`
- `/repeat context`
- `/repeat off`
- `/shuffle`
- `/shuffle on`
- `/shuffle off`
- `/volume 70`
- `/devices`
- `/whoami`

## Deployment Notes

- Replit, Railway, Render, and similar platforms are suitable for controller-only mode.
- Replit Reserved VM can run a background worker, but it is not the best fit for `spotifyd` plus audio daemon setup.
- Ubuntu/Debian VPS is the recommended host for full 24/7 playback.
- Keep the project path free of whitespace when using the systemd installer.
- On Linux, keep `.env` readable only by the owner with `chmod 600 .env`.
- `SPOTIFY_DEVICE_NAME` should match `device_name` in `spotifyd.conf` only when you want a fixed VPS player.
- If `TELEGRAM_ALLOWED_USER_IDS` is empty, the bot starts but control requests are denied.
- Spotify can only play on one active device per account at a time.

## References

- spotifyd docs: <https://docs.spotifyd.rs/>
- spotifyd auth: <https://docs.spotifyd.rs/configuration/auth.html>
- Spotify Web API: <https://developer.spotify.com/documentation/web-api/>
- Telegram Bot API: <https://core.telegram.org/bots/api>
