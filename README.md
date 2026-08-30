# spotify247

![python](https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square&logo=python&logoColor=white)
![telegram](https://img.shields.io/badge/telegram-bot%20api-26a5e4?style=flat-square&logo=telegram&logoColor=white)
![spotify](https://img.shields.io/badge/spotify-web%20api-1db954?style=flat-square&logo=spotify&logoColor=white)
![deployment](https://img.shields.io/badge/deployment-systemd-222222?style=flat-square&logo=systemd&logoColor=white)
![license](https://img.shields.io/badge/license-mit-2563eb?style=flat-square)

bot telegram untuk mengontrol spotify. bisa dipakai sebagai controller biasa atau player 24/7 di ubuntu/debian dengan `spotifyd`.

## status

`v0.1.0` | maintained for personal and self-hosted use

## fitur

- play, pause, next, previous, repeat, shuffle, dan volume
- search track dari telegram
- playback panel dengan inline button
- pembatasan berdasarkan telegram user id
- spotify device auto-discovery atau fixed device
- setup wizard dan health check
- systemd service untuk vps

## mode

| mode | kebutuhan |
| --- | --- |
| controller | python, spotify premium, telegram bot, spotify app |
| vps player | ubuntu/debian, spotifyd, pulseaudio, systemd |

## arsitektur

```text
telegram -> spotify247 -> spotify web api -> spotify device
telegram -> spotify247 -> spotify web api -> spotifyd -> pulseaudio
```

## install

```bash
git clone https://github.com/azrahudaya/spotify247.git
cd spotify247
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.setup
python -m app.doctor
python -m app.main
```

untuk vps ubuntu/debian:

```bash
chmod +x scripts/*.sh
./scripts/install_ubuntu.sh "$PWD"
./scripts/setup_spotifyd.sh "$PWD"
spotifyd authenticate
./scripts/install_service.sh "$PWD"
```

## konfigurasi

wajib:

- `telegram_bot_token`
- `spotify_client_id`
- `spotify_client_secret`
- `spotify_refresh_token`

opsional:

- `telegram_allowed_user_ids`
- `spotify_device_name`
- `spotify_market`
- `bot_poll_timeout_seconds`
- `bot_search_limit`
- `log_level`

jangan commit `.env`. di linux gunakan:

```bash
chmod 600 .env
```

## perintah

```text
/panel
/status
/now
/search <query>
/play
/pause
/next
/prev
/repeat
/shuffle
/volume 70
/devices
/whoami
```

## development

```bash
python -m pip install -r requirements.txt pytest ruff
pytest -q
ruff check app scripts tests
```

## batasan

- spotify hanya dapat memutar satu device aktif untuk satu akun
- mode player membutuhkan linux dan konfigurasi audio
- spotify premium diperlukan untuk playback control
- api spotify dan telegram tetap tunduk pada kebijakan masing-masing provider

## dokumentasi

- [changelog](CHANGELOG.md)
- [roadmap](ROADMAP.md)
- [spotify web api](https://developer.spotify.com/documentation/web-api/)
- [telegram bot api](https://core.telegram.org/bots/api)
- [spotifyd](https://docs.spotifyd.rs/)

## license

mit. lihat [license](LICENSE).
