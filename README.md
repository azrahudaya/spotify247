# Spotify 24/7 VPS + Telegram Control

Project ini bikin panel Telegram untuk mengontrol playback Spotify yang jalan di VPS Ubuntu. Playback device-nya tetap `spotifyd`, sedangkan bot ini pakai Spotify Web API untuk:

- lihat lagu yang sedang diputar
- tombol `prev / play-pause / next`
- tombol repeat yang muter `off -> track -> context`
- tombol shuffle
- cari lagu dari Telegram lalu putar langsung di VPS
- naik/turun volume

## Arsitektur

```text
Telegram Bot
    -> app/main.py
    -> Spotify Web API
    -> spotifyd on Ubuntu VPS
    -> PulseAudio null sink (kalau VPS tidak punya audio device)
```

## Isi project

```text
app/
  bot.py
  config.py
  main.py
  spotify.py
  telegram_api.py
deploy/
  spotifyd/
  systemd/
scripts/
  install_ubuntu.sh
  spotify_auth.py
```

## Prasyarat

- akun Spotify Premium
- bot Telegram dari `@BotFather`
- 1 Spotify Developer app untuk Web API bot ini
- VPS Ubuntu 22.04 atau 24.04

Catatan: untuk playback control Spotify, kamu butuh OAuth user token, bukan client credentials biasa.

## 1. Siapkan Spotify app untuk bot

1. Buka Spotify Developer Dashboard.
2. Buat app baru.
3. Tambahkan redirect URI, misalnya `http://127.0.0.1:8888/callback`.
4. Ambil `Client ID` dan `Client Secret`.
5. Copy `.env.example` jadi `.env`, lalu isi:

```bash
cp .env.example .env
```

Isi minimal:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_IDS=123456789
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
SPOTIFY_DEVICE_NAME=Spotify VPS
```

Kalau belum tahu user id Telegram kamu, jalankan bot dulu lalu pakai `/whoami`.

## 2. Ambil Spotify refresh token untuk bot

Jalankan helper ini dari repo:

```bash
python3 scripts/spotify_auth.py
```

Flow-nya:

1. script menampilkan URL OAuth
2. kamu buka URL itu di browser
3. login dengan akun Spotify yang sama dengan spotifyd
4. copy URL redirect hasil login
5. paste balik ke terminal
6. script akan print `SPOTIFY_REFRESH_TOKEN=...`

Masukkan nilai itu ke file `.env`.

## 3. Install dependency di Ubuntu VPS

Copy project ini ke VPS, lalu:

```bash
chmod +x scripts/install_ubuntu.sh
./scripts/install_ubuntu.sh "$PWD"
```

Script ini akan:

- install `python3`, `venv`, `pip`, `pulseaudio`
- install dependency Python bot
- download binary `spotifyd` latest release jika belum ada

## 4. Siapkan audio headless untuk VPS

Kalau VPS tidak punya sound card, pakai PulseAudio null sink.

1. Buat file config PulseAudio user:

```bash
mkdir -p ~/.config/pulse
cp deploy/spotifyd/default.pa.append.example ~/.config/pulse/default.pa.append
```

2. Tambahkan isi file itu ke `~/.config/pulse/default.pa`:

```bash
cp /etc/pulse/default.pa ~/.config/pulse/default.pa
cat ~/.config/pulse/default.pa.append >> ~/.config/pulse/default.pa
```

3. Restart PulseAudio user:

```bash
pulseaudio -k || true
pulseaudio --start
```

4. Cek sink:

```bash
pactl list short sinks
```

Kamu harus melihat sink bernama `spotify247`.

## 5. Siapkan spotifyd

Copy config contoh:

```bash
mkdir -p ~/.config/spotifyd
cp deploy/spotifyd/spotifyd.conf.example ~/.config/spotifyd/spotifyd.conf
```

Ubah placeholder `YOUR_USER` di `cache_path`, lalu pastikan:

- `device_name` sama dengan `SPOTIFY_DEVICE_NAME` di `.env`
- `backend = "pulseaudio"`
- `device = "spotify247"`

### Auth spotifyd

`spotifyd` punya auth sendiri, terpisah dari refresh token bot.

Cara paling praktis:

1. jalankan `spotifyd authenticate` di mesin yang punya browser
2. login dengan akun Spotify yang sama
3. copy file kredensial hasil auth ke VPS

Menurut dokumentasi `spotifyd`, file kredensial biasanya ada di:

```text
<cache_path>/oauth/credentials.json
```

Jadi kalau `cache_path = /home/ubuntu/.cache/spotifyd`, file yang harus ada di VPS adalah:

```text
/home/ubuntu/.cache/spotifyd/oauth/credentials.json
```

## 6. Jalankan bot dan spotifyd manual

Tes dulu tanpa systemd:

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

Di Telegram:

- `/whoami`
- `/panel`
- `/devices`
- `/search joji slow dancing`

Kalau panel muncul dan device online, berarti flow dasar sudah benar.

## 7. Jadikan 24/7 dengan systemd user service

Supaya tetap jalan walau kamu logout:

```bash
loginctl enable-linger "$USER"
mkdir -p ~/.config/systemd/user
cp deploy/systemd/spotifyd.user.service ~/.config/systemd/user/spotifyd.service
cp deploy/systemd/telegram-spotify-bot.user.service ~/.config/systemd/user/telegram-spotify-bot.service
systemctl --user daemon-reload
systemctl --user enable --now spotifyd.service
systemctl --user enable --now telegram-spotify-bot.service
```

Catatan: file service di repo ini mengasumsikan project ada di `~/spotify247`. Kalau path repo kamu beda, ubah `WorkingDirectory`, `EnvironmentFile`, dan `ExecStart`.

Cek status:

```bash
systemctl --user status spotifyd.service
systemctl --user status telegram-spotify-bot.service
```

Lihat log:

```bash
journalctl --user -u spotifyd.service -f
journalctl --user -u telegram-spotify-bot.service -f
```

## Command Telegram

- `/panel`
- `/search <judul>`
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

## Hal yang perlu kamu tahu

- Bot ini sengaja hanya mengizinkan user yang ada di `TELEGRAM_ALLOWED_USER_IDS`.
- Kalau `TELEGRAM_ALLOWED_USER_IDS` kosong, bot tetap bisa jalan, tapi semua kontrol akan ditolak sampai user id diisi.
- Spotify hanya bisa aktif di satu playback device per akun pada waktu yang sama.
- Kalau `spotifyd` belum online, panel tetap bisa muncul tapi action playback akan gagal.
- Search memakai batas maksimal 10 hasil. Default project ini 5 hasil.

## Referensi resmi

- spotifyd docs: <https://docs.spotifyd.rs/>
- spotifyd auth: <https://docs.spotifyd.rs/configuration/auth.html>
- Spotify playback API: <https://developer.spotify.com/documentation/web-api/reference/get-information-about-the-users-current-playback>
- Spotify devices API: <https://developer.spotify.com/documentation/web-api/reference/get-a-users-available-devices>
- Telegram Bot API: <https://core.telegram.org/bots/api>
