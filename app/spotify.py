from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from app.config import Config


ACCOUNTS_BASE_URL = "https://accounts.spotify.com"
WEB_API_BASE_URL = "https://api.spotify.com/v1"


class SpotifyApiError(RuntimeError):
    pass


@dataclass
class TargetDevice:
    device_id: str
    name: str
    is_active: bool
    type: str
    volume_percent: int | None


class SpotifyClient:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._session = requests.Session()
        self._access_token = ""
        self._access_token_expires_at = 0.0

    def get_playback(self) -> dict[str, Any] | None:
        return self._api("GET", "/me/player", expected_statuses={200, 204})

    def get_devices(self) -> list[dict[str, Any]]:
        payload = self._api("GET", "/me/player/devices")
        return payload.get("devices", [])

    def get_target_device(self) -> TargetDevice:
        normalized_target = self._config.spotify_device_name.casefold()
        exact_match: dict[str, Any] | None = None
        partial_match: dict[str, Any] | None = None

        for device in self.get_devices():
            device_name = device.get("name", "")
            if device_name.casefold() == normalized_target:
                exact_match = device
                break
            if normalized_target in device_name.casefold():
                partial_match = device

        device = exact_match or partial_match
        if not device:
            raise SpotifyApiError(
                f"Device '{self._config.spotify_device_name}' tidak ditemukan. "
                "Pastikan spotifyd sudah jalan dan nama device cocok."
            )
        if device.get("is_restricted"):
            raise SpotifyApiError(
                f"Device '{device.get('name', self._config.spotify_device_name)}' "
                "sedang restricted dan tidak bisa dikontrol via API."
            )
        device_id = device.get("id")
        if not device_id:
            raise SpotifyApiError(
                f"Device '{device.get('name', self._config.spotify_device_name)}' "
                "tidak punya device_id yang bisa dipakai."
            )
        return TargetDevice(
            device_id=device_id,
            name=device.get("name", self._config.spotify_device_name),
            is_active=bool(device.get("is_active")),
            type=device.get("type", "unknown"),
            volume_percent=device.get("volume_percent"),
        )

    def ensure_target_active(self, *, play: bool = False) -> TargetDevice:
        target = self.get_target_device()
        if target.is_active:
            return target

        self._api(
            "PUT",
            "/me/player",
            json_body={"device_ids": [target.device_id], "play": play},
            expected_statuses={204},
        )
        target.is_active = True
        return target

    def resume(self) -> None:
        target = self.ensure_target_active(play=True)
        self._api(
            "PUT",
            "/me/player/play",
            params={"device_id": target.device_id},
            expected_statuses={204},
        )

    def pause(self) -> None:
        target = self.ensure_target_active(play=False)
        self._api(
            "PUT",
            "/me/player/pause",
            params={"device_id": target.device_id},
            expected_statuses={204},
        )

    def toggle_playback(self) -> None:
        playback = self.get_playback()
        if playback and playback.get("is_playing"):
            current_device = playback.get("device", {})
            try:
                target = self.get_target_device()
            except SpotifyApiError:
                target = None
            if target and current_device.get("id") == target.device_id:
                self.pause()
                return
        self.resume()

    def next_track(self) -> None:
        target = self.ensure_target_active(play=False)
        self._api(
            "POST",
            "/me/player/next",
            params={"device_id": target.device_id},
            expected_statuses={204},
        )

    def previous_track(self) -> None:
        target = self.ensure_target_active(play=False)
        self._api(
            "POST",
            "/me/player/previous",
            params={"device_id": target.device_id},
            expected_statuses={204},
        )

    def cycle_repeat(self) -> str:
        playback = self.get_playback()
        current_state = (playback or {}).get("repeat_state", "off")
        next_state = {
            "off": "track",
            "track": "context",
            "context": "off",
        }.get(current_state, "track")

        target = self.ensure_target_active(play=False)
        self._api(
            "PUT",
            "/me/player/repeat",
            params={"state": next_state, "device_id": target.device_id},
            expected_statuses={204},
        )
        return next_state

    def set_repeat(self, state: str) -> None:
        if state not in {"off", "track", "context"}:
            raise SpotifyApiError("Repeat hanya menerima off, track, atau context.")
        target = self.ensure_target_active(play=False)
        self._api(
            "PUT",
            "/me/player/repeat",
            params={"state": state, "device_id": target.device_id},
            expected_statuses={204},
        )

    def toggle_shuffle(self) -> bool:
        playback = self.get_playback()
        shuffle_state = bool((playback or {}).get("shuffle_state", False))
        next_state = not shuffle_state
        target = self.ensure_target_active(play=False)
        self._api(
            "PUT",
            "/me/player/shuffle",
            params={"state": str(next_state).lower(), "device_id": target.device_id},
            expected_statuses={204},
        )
        return next_state

    def set_shuffle(self, state: bool) -> None:
        target = self.ensure_target_active(play=False)
        self._api(
            "PUT",
            "/me/player/shuffle",
            params={"state": str(state).lower(), "device_id": target.device_id},
            expected_statuses={204},
        )

    def set_volume(self, volume_percent: int) -> None:
        if volume_percent < 0 or volume_percent > 100:
            raise SpotifyApiError("Volume harus antara 0 sampai 100.")
        target = self.ensure_target_active(play=False)
        self._api(
            "PUT",
            "/me/player/volume",
            params={"volume_percent": volume_percent, "device_id": target.device_id},
            expected_statuses={204},
        )

    def change_volume(self, delta: int) -> int:
        target = self.ensure_target_active(play=False)
        base_volume = target.volume_percent

        if base_volume is None:
            playback = self.get_playback()
            base_volume = (playback or {}).get("device", {}).get("volume_percent")

        if base_volume is None:
            raise SpotifyApiError("Spotify tidak mengembalikan volume device saat ini.")

        next_volume = min(100, max(0, base_volume + delta))
        self.set_volume(next_volume)
        return next_volume

    def play_track(self, track_id: str) -> None:
        target = self.ensure_target_active(play=False)
        self._api(
            "PUT",
            "/me/player/play",
            params={"device_id": target.device_id},
            json_body={"uris": [f"spotify:track:{track_id}"]},
            expected_statuses={204},
        )

    def search_tracks(self, query: str) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "q": query,
            "type": "track",
            "limit": self._config.bot_search_limit,
        }
        if self._config.spotify_market:
            params["market"] = self._config.spotify_market

        payload = self._api("GET", "/search", params=params)
        return payload.get("tracks", {}).get("items", [])

    def _api(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        expected_statuses: set[int] | None = None,
        retry_on_unauthorized: bool = True,
    ) -> dict[str, Any] | None:
        if expected_statuses is None:
            expected_statuses = {200}

        response = self._session.request(
            method=method,
            url=f"{WEB_API_BASE_URL}{path}",
            headers={"Authorization": f"Bearer {self._get_access_token()}"},
            params=params,
            json=json_body,
            timeout=20,
        )

        if response.status_code == 401 and retry_on_unauthorized:
            self._refresh_access_token(force=True)
            return self._api(
                method,
                path,
                params=params,
                json_body=json_body,
                expected_statuses=expected_statuses,
                retry_on_unauthorized=False,
            )

        if response.status_code in expected_statuses:
            if response.status_code == 204 or not response.content:
                return None
            return response.json()

        raise self._build_error(response)

    def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._access_token_expires_at:
            return self._access_token
        self._refresh_access_token(force=True)
        return self._access_token

    def _refresh_access_token(self, *, force: bool) -> None:
        if not force and self._access_token and time.time() < self._access_token_expires_at:
            return

        response = self._session.post(
            f"{ACCOUNTS_BASE_URL}/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._config.spotify_refresh_token,
            },
            auth=(
                self._config.spotify_client_id,
                self._config.spotify_client_secret,
            ),
            timeout=20,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise SpotifyApiError(
                f"Spotify auth gagal: HTTP {response.status_code}"
            ) from exc

        if response.status_code != 200:
            message = payload.get("error_description") or payload.get("error") or response.text
            raise SpotifyApiError(
                "Refresh token Spotify gagal. "
                f"Periksa SPOTIFY_CLIENT_ID/SECRET/REFRESH_TOKEN. Detail: {message}"
            )

        self._access_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        self._access_token_expires_at = time.time() + max(60, expires_in - 60)

    @staticmethod
    def _build_error(response: requests.Response) -> SpotifyApiError:
        message = response.text.strip()
        try:
            payload = response.json()
        except ValueError:
            payload = {}

        if isinstance(payload.get("error"), dict):
            message = payload["error"].get("message", message)
        elif payload.get("error_description"):
            message = payload["error_description"]
        elif payload.get("error"):
            message = str(payload["error"])

        if response.status_code == 403:
            message = (
                "Spotify menolak request. Pastikan akun Premium dipakai, "
                "scope OAuth benar, dan device target tidak restricted. "
                f"Detail: {message}"
            )
        elif response.status_code == 404:
            message = (
                "Spotify tidak menemukan playback aktif untuk aksi ini. "
                "Biasanya berarti spotifyd belum aktif sebagai device. "
                f"Detail: {message}"
            )
        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            extra = f" Coba lagi dalam {retry_after} detik." if retry_after else ""
            message = f"Spotify rate limit.{extra}"

        return SpotifyApiError(f"Spotify API error {response.status_code}: {message}")

