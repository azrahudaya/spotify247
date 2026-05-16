#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


TOKEN_URL = "https://accounts.spotify.com/api/token"
CURRENTLY_PLAYING_URL = "https://api.spotify.com/v1/me/player/currently-playing"
SITE_DIR = Path(__file__).resolve().parents[1] / "site"
OUTPUT_PATH = SITE_DIR / "now-playing.json"


def main() -> int:
    if load_dotenv is not None:
        load_dotenv()

    payload = build_payload()
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH}")
    return 0


def build_payload() -> dict[str, Any]:
    missing = [
        name
        for name in (
            "SPOTIFY_CLIENT_ID",
            "SPOTIFY_CLIENT_SECRET",
            "SPOTIFY_REFRESH_TOKEN",
        )
        if not os.getenv(name, "").strip()
    ]
    if missing:
        return base_payload(
            state="setup_required",
            message=(
                "Add GitHub Actions secrets for SPOTIFY_CLIENT_ID, "
                "SPOTIFY_CLIENT_SECRET, and SPOTIFY_REFRESH_TOKEN."
            ),
            missing=missing,
        )

    session = requests.Session()

    try:
        access_token = refresh_access_token(session)
        playback = fetch_currently_playing(session, access_token)
    except requests.RequestException as exc:
        return base_payload(
            state="error",
            message=f"Network error while contacting Spotify: {exc}",
        )
    except RuntimeError as exc:
        return base_payload(
            state="error",
            message=str(exc),
        )

    if playback is None:
        return base_payload(
            state="idle",
            message="Nothing is playing right now.",
        )

    item = playback.get("item") or {}
    album = item.get("album") or {}
    images = album.get("images") or []
    artists = [
        artist.get("name", "").strip()
        for artist in item.get("artists", [])
        if artist.get("name", "").strip()
    ]
    artwork_url = None
    if len(images) > 1:
        artwork_url = images[1].get("url")
    elif images:
        artwork_url = images[0].get("url")

    return {
        **base_payload(
            state="playing" if playback.get("is_playing") else "paused",
            message=None,
        ),
        "is_playing": bool(playback.get("is_playing")),
        "title": item.get("name"),
        "artists": artists,
        "artist_line": ", ".join(artists) if artists else None,
        "album": album.get("name"),
        "artwork_url": artwork_url,
        "track_url": (item.get("external_urls") or {}).get("spotify"),
        "track_id": item.get("id"),
        "progress_ms": playback.get("progress_ms"),
        "duration_ms": item.get("duration_ms"),
        "device_name": (playback.get("device") or {}).get("name"),
    }


def base_payload(
    *,
    state: str,
    message: str | None,
    missing: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "project": "spotify247",
        "state": state,
        "message": message,
        "missing": missing or [],
        "generated_at": utc_now_iso(),
        "is_playing": False,
        "title": None,
        "artists": [],
        "artist_line": None,
        "album": None,
        "artwork_url": None,
        "track_url": None,
        "track_id": None,
        "progress_ms": None,
        "duration_ms": None,
        "device_name": None,
    }


def refresh_access_token(session: requests.Session) -> str:
    response = session.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": os.environ["SPOTIFY_REFRESH_TOKEN"],
        },
        auth=(
            os.environ["SPOTIFY_CLIENT_ID"],
            os.environ["SPOTIFY_CLIENT_SECRET"],
        ),
        timeout=20,
    )
    payload = response.json()
    if response.status_code != 200:
        message = payload.get("error_description") or payload.get("error") or response.text
        raise RuntimeError(f"Spotify token refresh failed: {message}")
    return payload["access_token"]


def fetch_currently_playing(
    session: requests.Session,
    access_token: str,
) -> dict[str, Any] | None:
    market = os.getenv("SPOTIFY_MARKET", "").strip()
    params = {"additional_types": "track"}
    if market:
        params["market"] = market

    response = session.get(
        CURRENTLY_PLAYING_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=20,
    )

    if response.status_code == 204:
        return None
    if response.status_code != 200:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        message = payload.get("error_description") or payload.get("error") or response.text
        raise RuntimeError(
            f"Spotify currently-playing request failed: HTTP {response.status_code} {message}"
        )

    payload = response.json()
    if not payload.get("item"):
        return None
    return payload


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


if __name__ == "__main__":
    raise SystemExit(main())
