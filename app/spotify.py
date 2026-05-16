from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from app.config import Config


ACCOUNTS_BASE_URL = "https://accounts.spotify.com"
WEB_API_BASE_URL = "https://api.spotify.com/v1"
CONTROL_SUCCESS_STATUSES = {200, 202, 204}


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

    def get_current_user(self) -> dict[str, Any]:
        return self._api("GET", "/me")

    def get_devices(self) -> list[dict[str, Any]]:
        payload = self._api("GET", "/me/player/devices")
        return payload.get("devices", [])

    def get_target_device(self) -> TargetDevice:
        devices = self.get_devices()
        named_target = self._config.spotify_device_name
        device = (
            self._match_named_device(devices, named_target)
            if named_target
            else self._pick_auto_device(devices)
        )

        if not device:
            if named_target:
                raise SpotifyApiError(
                    f"Device '{named_target}' not found. "
                    "Make sure spotifyd is running or leave SPOTIFY_DEVICE_NAME empty "
                    "to use any active Spotify device."
                )
            raise SpotifyApiError(
                "No controllable Spotify device is online. Open Spotify on a device "
                "or run spotifyd on the server."
            )

        device_name = device.get("name") or named_target or "Auto device"
        if device.get("is_restricted"):
            raise SpotifyApiError(
                f"Device '{device_name}' is restricted and cannot be controlled through the API."
            )
        device_id = device.get("id")
        if not device_id:
            raise SpotifyApiError(f"Device '{device_name}' does not expose a usable device ID.")
        return TargetDevice(
            device_id=device_id,
            name=device_name,
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
            expected_statuses=CONTROL_SUCCESS_STATUSES,
        )
        target.is_active = True
        return target

    def resume(self) -> None:
        target = self.ensure_target_active(play=True)
        self._api(
            "PUT",
            "/me/player/play",
            params={"device_id": target.device_id},
            expected_statuses=CONTROL_SUCCESS_STATUSES,
        )

    def pause(self) -> None:
        target = self.ensure_target_active(play=False)
        self._api(
            "PUT",
            "/me/player/pause",
            params={"device_id": target.device_id},
            expected_statuses=CONTROL_SUCCESS_STATUSES,
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
            expected_statuses=CONTROL_SUCCESS_STATUSES,
        )

    def previous_track(self) -> None:
        target = self.ensure_target_active(play=False)
        self._api(
            "POST",
            "/me/player/previous",
            params={"device_id": target.device_id},
            expected_statuses=CONTROL_SUCCESS_STATUSES,
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
            expected_statuses=CONTROL_SUCCESS_STATUSES,
        )
        return next_state

    def set_repeat(self, state: str) -> None:
        if state not in {"off", "track", "context"}:
            raise SpotifyApiError("Repeat must be off, track, or context.")
        target = self.ensure_target_active(play=False)
        self._api(
            "PUT",
            "/me/player/repeat",
            params={"state": state, "device_id": target.device_id},
            expected_statuses=CONTROL_SUCCESS_STATUSES,
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
            expected_statuses=CONTROL_SUCCESS_STATUSES,
        )
        return next_state

    def set_shuffle(self, state: bool) -> None:
        target = self.ensure_target_active(play=False)
        self._api(
            "PUT",
            "/me/player/shuffle",
            params={"state": str(state).lower(), "device_id": target.device_id},
            expected_statuses=CONTROL_SUCCESS_STATUSES,
        )

    def set_volume(self, volume_percent: int) -> None:
        if volume_percent < 0 or volume_percent > 100:
            raise SpotifyApiError("Volume must be between 0 and 100.")
        target = self.ensure_target_active(play=False)
        self._api(
            "PUT",
            "/me/player/volume",
            params={"volume_percent": volume_percent, "device_id": target.device_id},
            expected_statuses=CONTROL_SUCCESS_STATUSES,
        )

    def change_volume(self, delta: int) -> int:
        target = self.ensure_target_active(play=False)
        base_volume = target.volume_percent

        if base_volume is None:
            playback = self.get_playback()
            base_volume = (playback or {}).get("device", {}).get("volume_percent")

        if base_volume is None:
            raise SpotifyApiError("Spotify did not return the current device volume.")

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
            expected_statuses=CONTROL_SUCCESS_STATUSES,
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
            try:
                return response.json()
            except ValueError:
                return {"raw_text": response.text.strip()}

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
                f"Spotify auth failed: HTTP {response.status_code}"
            ) from exc

        if response.status_code != 200:
            message = payload.get("error_description") or payload.get("error") or response.text
            raise SpotifyApiError(
                "Spotify refresh failed. "
                "Check SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, and "
                f"SPOTIFY_REFRESH_TOKEN. Detail: {message}"
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
                "Spotify rejected the request. Make sure you are using Premium, "
                "the OAuth scopes are correct, and the target device is not restricted. "
                f"Detail: {message}"
            )
        elif response.status_code == 404:
            message = (
                "Spotify could not find an active playback for this action. "
                "spotifyd is usually not active as a device yet. "
                f"Detail: {message}"
            )
        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            extra = f" Try again in {retry_after} seconds." if retry_after else ""
            message = f"Spotify rate limit.{extra}"

        return SpotifyApiError(f"Spotify API error {response.status_code}: {message}")

    @staticmethod
    def _match_named_device(
        devices: list[dict[str, Any]],
        named_target: str,
    ) -> dict[str, Any] | None:
        normalized_target = named_target.casefold()
        partial_match: dict[str, Any] | None = None

        for device in devices:
            device_name = device.get("name", "")
            normalized_device = device_name.casefold()
            if normalized_device == normalized_target:
                return device
            if normalized_target in normalized_device:
                partial_match = device

        return partial_match

    @staticmethod
    def _pick_auto_device(devices: list[dict[str, Any]]) -> dict[str, Any] | None:
        usable_devices = [
            device
            for device in devices
            if device.get("id") and not device.get("is_restricted")
        ]
        active_device = next(
            (device for device in usable_devices if device.get("is_active")),
            None,
        )
        return active_device or (usable_devices[0] if usable_devices else None)
