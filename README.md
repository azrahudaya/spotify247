# Spotify 24/7 VPS Bot

Control Spotify playback on an Ubuntu VPS from Telegram. The playback device stays on `spotifyd`, while this bot uses the Spotify Web API for status, search, and playback controls.

## Features

- View the current track
- Control `prev / play-pause / next`
- Toggle repeat and shuffle
- Search from Telegram and play a track on the VPS
- Change volume
- Restrict access to selected Telegram user IDs

## Flow

```text
Telegram Bot
    -> app/main.py
    -> Spotify Web API
    -> spotifyd on Ubuntu VPS
    -> PulseAudio null sink for headless audio
```

## Requirements

- Spotify Premium account
- Telegram bot token from `@BotFather`
- Spotify Developer app for the Web API
- Ubuntu 22.04 or 24.04 VPS

Important: playback control requires a Spotify user OAuth token. Client credentials alone are not enough.

## Quick Setup

### 1. Create a Telegram bot

1. Open Telegram and chat with `@BotFather`.
2. Run `/newbot`.
3. Copy the bot token.
4. Put it in `TELEGRAM_BOT_TOKEN`.

### 2. Create a Spotify app

1. Open the Spotify Developer Dashboard: <https://developer.spotify.com/dashboard>
2. Create a new app.
3. Open the app page.
4. Copy the `Client ID`.
5. Reveal and copy the `Client Secret`.
6. Add a redirect URI such as `http://127.0.0.1:8888/callback`.
7. Save the app settings.

Use the same Spotify account for:

- `spotifyd`
- the refresh token generated for this bot

### 3. Create `.env`

```bash
cp .env.example .env
```

Fill the variables below:

| Variable | What it is | Where to get it |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | `@BotFather` |
| `TELEGRAM_ALLOWED_USER_IDS` | Comma-separated Telegram user IDs allowed to control the bot | Run the bot, then use `/whoami` |
| `SPOTIFY_CLIENT_ID` | Spotify app client ID | Spotify Developer Dashboard app page |
| `SPOTIFY_CLIENT_SECRET` | Spotify app client secret | Spotify Developer Dashboard app page |
| `SPOTIFY_REFRESH_TOKEN` | Spotify user refresh token | Generate with `python3 scripts/spotify_auth.py` |
| `SPOTIFY_REDIRECT_URI` | OAuth redirect URI | Must match the redirect URI in your Spotify app |
| `SPOTIFY_DEVICE_NAME` | Target playback device name | Must match `device_name` in `spotifyd.conf` |
| `SPOTIFY_MARKET` | Search market code | Optional |
| `BOT_POLL_TIMEOUT_SECONDS` | Telegram polling timeout | Optional |
| `BOT_SEARCH_LIMIT` | Search result limit, max `10` | Optional |
| `LOG_LEVEL` | App log level | Optional |

Minimum example:

```env
TELEGRAM_BOT_TOKEN=1234567890:replace_me
TELEGRAM_ALLOWED_USER_IDS=123456789
SPOTIFY_CLIENT_ID=replace_me
SPOTIFY_CLIENT_SECRET=replace_me
SPOTIFY_REFRESH_TOKEN=replace_me
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
SPOTIFY_DEVICE_NAME=Spotify VPS
```

If you do not know your Telegram user ID yet, start the bot first and run `/whoami`.

### 4. Generate the Spotify refresh token

Run:

```bash
python3 scripts/spotify_auth.py
```

The helper will:

1. Print an OAuth URL.
2. Ask you to open it in a browser.
3. Ask you to sign in with the same Spotify account used by `spotifyd`.
4. Ask you to paste the full redirect URL.
5. Print `SPOTIFY_REFRESH_TOKEN=...`.

Add the printed refresh token to `.env`.

### 5. Install dependencies on Ubuntu

Copy the project to the VPS, then run:

```bash
chmod +x scripts/install_ubuntu.sh
./scripts/install_ubuntu.sh "$PWD"
```

The script will:

- install Python, `venv`, `pip`, `pulseaudio`, `curl`, and `jq`
- install Python dependencies
- download the latest `spotifyd` release if it is not already installed

### 6. Configure headless audio

If the VPS has no sound card, use a PulseAudio null sink.

```bash
mkdir -p ~/.config/pulse
cp deploy/spotifyd/default.pa.append.example ~/.config/pulse/default.pa.append
cp /etc/pulse/default.pa ~/.config/pulse/default.pa
cat ~/.config/pulse/default.pa.append >> ~/.config/pulse/default.pa
pulseaudio -k || true
pulseaudio --start
pactl list short sinks
```

You should see a sink named `spotify247`.

### 7. Configure `spotifyd`

Copy the example config:

```bash
mkdir -p ~/.config/spotifyd
cp deploy/spotifyd/spotifyd.conf.example ~/.config/spotifyd/spotifyd.conf
```

Update the config:

- replace `YOUR_USER` in `cache_path`
- keep `device_name` equal to `SPOTIFY_DEVICE_NAME` in `.env`
- keep `backend = "pulseaudio"`
- keep `device = "spotify247"`
- keep `use_mpris = false` for headless service setups

### 8. Authenticate `spotifyd`

`spotifyd` has its own login flow. It does not use the bot refresh token.

Simple approach:

1. Run `spotifyd authenticate` on a machine with a browser.
2. Sign in with the same Spotify account.
3. Copy the generated credentials file to the VPS.

The credentials file is usually:

```text
<cache_path>/oauth/credentials.json
```

Example:

```text
/home/ubuntu/.cache/spotifyd/oauth/credentials.json
```

### 9. Test it manually

Terminal 1:

```bash
pulseaudio --start
spotifyd --no-daemon --config-path ~/.config/spotifyd/spotifyd.conf
```

Terminal 2:

```bash
source .venv/bin/activate
python -m app.main
```

Test commands in Telegram:

- `/whoami`
- `/panel`
- `/devices`
- `/search joji slow dancing`

If the panel opens and the device is online, the base setup is working.

### 10. Run it 24/7 with systemd user services

```bash
loginctl enable-linger "$USER"
mkdir -p ~/.config/systemd/user
cp deploy/systemd/spotifyd.user.service ~/.config/systemd/user/spotifyd.service
cp deploy/systemd/telegram-spotify-bot.user.service ~/.config/systemd/user/telegram-spotify-bot.service
systemctl --user daemon-reload
systemctl --user enable --now spotifyd.service
systemctl --user enable --now telegram-spotify-bot.service
```

The service files assume the project lives in `~/spotify247`. If your path is different, update:

- `WorkingDirectory`
- `EnvironmentFile`
- `ExecStart`

Useful commands:

```bash
systemctl --user status spotifyd.service
systemctl --user status telegram-spotify-bot.service
journalctl --user -u spotifyd.service -f
journalctl --user -u telegram-spotify-bot.service -f
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

## Notes

- Only users listed in `TELEGRAM_ALLOWED_USER_IDS` can control the bot.
- If `TELEGRAM_ALLOWED_USER_IDS` is empty, the bot can start but all control requests are denied.
- Spotify can only play on one active device per account at a time.
- The panel can open even when `spotifyd` is offline, but playback actions will fail.
- Search uses `BOT_SEARCH_LIMIT`. The default is `5` and the maximum is `10`.

## References

- spotifyd docs: <https://docs.spotifyd.rs/>
- spotifyd auth: <https://docs.spotifyd.rs/configuration/auth.html>
- Spotify playback API: <https://developer.spotify.com/documentation/web-api/reference/get-information-about-the-users-current-playback>
- Spotify devices API: <https://developer.spotify.com/documentation/web-api/reference/get-a-users-available-devices>
- Telegram Bot API: <https://core.telegram.org/bots/api>
