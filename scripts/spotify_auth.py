#!/usr/bin/env python3
from __future__ import annotations

import os
import secrets
import sys
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv


AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SCOPES = [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
]


def main() -> int:
    load_dotenv()

    client_id = _env_or_prompt("SPOTIFY_CLIENT_ID")
    client_secret = _env_or_prompt("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "").strip() or input(
        "SPOTIFY_REDIRECT_URI: "
    ).strip()

    state = secrets.token_urlsafe(16)
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
            "show_dialog": "true",
            "state": state,
        }
    )
    authorize_url = f"{AUTH_URL}?{query}"

    print("\n1. Open this URL in a browser and sign in with the same Spotify account used by spotifyd:\n")
    print(authorize_url)
    print(
        "\n2. After the redirect, paste the full redirect URL here.\n"
        "   Example: http://127.0.0.1:8888/callback?code=...&state=...\n"
    )
    redirect_response = input("Paste redirect URL: ").strip()
    if not redirect_response:
        print("Redirect URL is required.", file=sys.stderr)
        return 1

    code, returned_state = _extract_code_and_state(redirect_response)
    if returned_state and returned_state != state:
        print("OAuth state mismatch. Run the auth flow again.", file=sys.stderr)
        return 1

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        auth=(client_id, client_secret),
        timeout=20,
    )
    payload = response.json()

    if response.status_code != 200:
        message = payload.get("error_description") or payload.get("error") or response.text
        print(f"Token exchange failed: {message}", file=sys.stderr)
        return 1

    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        print("Spotify did not return a refresh token.", file=sys.stderr)
        return 1

    print("\nAdd this value to your .env file:\n")
    print(f"SPOTIFY_REFRESH_TOKEN={refresh_token}")
    print("\nScopes used:")
    for scope in SCOPES:
        print(f"- {scope}")
    return 0


def _env_or_prompt(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    value = input(f"{name}: ").strip()
    if not value:
        print(f"{name} is required.", file=sys.stderr)
        raise SystemExit(1)
    return value


def _extract_code_and_state(redirect_response: str) -> tuple[str, str]:
    if redirect_response.startswith("http://") or redirect_response.startswith("https://"):
        parsed = urlparse(redirect_response)
        params = parse_qs(parsed.query)
        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        if code:
            return code, state

    if "code=" in redirect_response:
        params = parse_qs(redirect_response)
        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        if code:
            return code, state

    print("The redirect URL does not contain an OAuth code.", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
