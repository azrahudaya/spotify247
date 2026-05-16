from __future__ import annotations

import getpass
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import dotenv_values


AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
ENV_PATH = Path(".env")
ENV_KEYS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_USER_IDS",
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_CLIENT_SECRET",
    "SPOTIFY_REFRESH_TOKEN",
    "SPOTIFY_REDIRECT_URI",
    "SPOTIFY_DEVICE_NAME",
    "SPOTIFY_MARKET",
    "BOT_POLL_TIMEOUT_SECONDS",
    "BOT_SEARCH_LIMIT",
    "LOG_LEVEL",
]
SPOTIFY_SCOPES = [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
]


def main() -> int:
    env_garden = _load_env_garden()
    print("spotify247 setup")
    print("Leave SPOTIFY_DEVICE_NAME empty if you want controller-only mode.")
    print("")

    env_garden["TELEGRAM_BOT_TOKEN"] = _ask_text(
        "Telegram bot token",
        env_garden.get("TELEGRAM_BOT_TOKEN", ""),
        hidden=True,
    )
    env_garden["TELEGRAM_ALLOWED_USER_IDS"] = _ask_user_ids(
        env_garden.get("TELEGRAM_ALLOWED_USER_IDS", "")
    )
    env_garden["SPOTIFY_CLIENT_ID"] = _ask_text(
        "Spotify client ID",
        env_garden.get("SPOTIFY_CLIENT_ID", ""),
    )
    env_garden["SPOTIFY_CLIENT_SECRET"] = _ask_text(
        "Spotify client secret",
        env_garden.get("SPOTIFY_CLIENT_SECRET", ""),
        hidden=True,
    )
    env_garden["SPOTIFY_REDIRECT_URI"] = _ask_text(
        "Spotify redirect URI",
        env_garden.get("SPOTIFY_REDIRECT_URI", "") or DEFAULT_REDIRECT_URI,
    )
    env_garden["SPOTIFY_DEVICE_NAME"] = _ask_text(
        "Spotify device name",
        env_garden.get("SPOTIFY_DEVICE_NAME", ""),
        required=False,
    )
    env_garden["SPOTIFY_MARKET"] = _ask_text(
        "Spotify market code",
        env_garden.get("SPOTIFY_MARKET", "ID"),
        required=False,
    ).upper()
    env_garden["BOT_POLL_TIMEOUT_SECONDS"] = _ask_number(
        "Telegram poll timeout seconds",
        env_garden.get("BOT_POLL_TIMEOUT_SECONDS", "30"),
        minimum=5,
        maximum=50,
    )
    env_garden["BOT_SEARCH_LIMIT"] = _ask_number(
        "Search result limit",
        env_garden.get("BOT_SEARCH_LIMIT", "5"),
        minimum=1,
        maximum=10,
    )
    env_garden["LOG_LEVEL"] = _ask_text(
        "Log level",
        env_garden.get("LOG_LEVEL", "INFO"),
    ).upper()

    current_refresh = env_garden.get("SPOTIFY_REFRESH_TOKEN", "")
    if not current_refresh:
        if _ask_yes("Generate Spotify refresh token now", default=True):
            env_garden["SPOTIFY_REFRESH_TOKEN"] = _run_spotify_oauth(env_garden)
        else:
            env_garden["SPOTIFY_REFRESH_TOKEN"] = _ask_text(
                "Spotify refresh token",
                "",
                hidden=True,
            )
    elif _ask_yes("Generate a new Spotify refresh token", default=False):
        env_garden["SPOTIFY_REFRESH_TOKEN"] = _run_spotify_oauth(env_garden)

    _write_env_garden(env_garden)
    print("")
    print("Wrote .env")
    print("Run: python -m app.doctor")
    print("Then run: python -m app.main")
    return 0


def _load_env_garden() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    return {key: str(value or "") for key, value in dotenv_values(ENV_PATH).items()}


def _ask_text(
    label: str,
    current_value: str,
    *,
    required: bool = True,
    hidden: bool = False,
) -> str:
    while True:
        prompt = f"{label}"
        if current_value:
            prompt += " [Enter to keep]"
        prompt += ": "
        raw_value = getpass.getpass(prompt).strip() if hidden else input(prompt).strip()
        if raw_value:
            return raw_value
        if current_value:
            return current_value
        if not required:
            return ""
        print(f"{label} is required.")


def _ask_user_ids(current_value: str) -> str:
    while True:
        value = _ask_text(
            "Allowed Telegram user IDs",
            current_value,
            required=False,
        )
        if not value:
            return ""
        pieces = [piece.strip() for piece in value.split(",") if piece.strip()]
        if all(piece.isdigit() for piece in pieces):
            return ",".join(pieces)
        print("Use comma-separated numeric Telegram user IDs.")


def _ask_number(label: str, current_value: str, *, minimum: int, maximum: int) -> str:
    while True:
        value = _ask_text(label, current_value)
        try:
            parsed_value = int(value)
        except ValueError:
            print(f"{label} must be a number.")
            continue
        if minimum <= parsed_value <= maximum:
            return str(parsed_value)
        print(f"{label} must be between {minimum} and {maximum}.")


def _ask_yes(label: str, *, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{label}? [{suffix}]: ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Answer y or n.")


def _run_spotify_oauth(env_garden: dict[str, str]) -> str:
    oauth_state = secrets.token_urlsafe(16)
    authorize_query = urlencode(
        {
            "client_id": env_garden["SPOTIFY_CLIENT_ID"],
            "response_type": "code",
            "redirect_uri": env_garden["SPOTIFY_REDIRECT_URI"],
            "scope": " ".join(SPOTIFY_SCOPES),
            "show_dialog": "true",
            "state": oauth_state,
        }
    )
    print("")
    print("Open this Spotify OAuth URL:")
    print(f"{AUTH_URL}?{authorize_query}")
    print("")
    redirect_echo = input("Paste the full redirect URL: ").strip()
    if not redirect_echo:
        print("Redirect URL is required.", file=sys.stderr)
        raise SystemExit(1)

    auth_code, returned_state = _pluck_code_and_state(redirect_echo)
    if returned_state and returned_state != oauth_state:
        print("OAuth state mismatch. Run setup again.", file=sys.stderr)
        raise SystemExit(1)

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": env_garden["SPOTIFY_REDIRECT_URI"],
        },
        auth=(
            env_garden["SPOTIFY_CLIENT_ID"],
            env_garden["SPOTIFY_CLIENT_SECRET"],
        ),
        timeout=20,
    )
    try:
        payload = response.json()
    except ValueError:
        print(f"Spotify returned HTTP {response.status_code}.", file=sys.stderr)
        raise SystemExit(1)

    if response.status_code != 200:
        message = payload.get("error_description") or payload.get("error") or response.text
        print(f"Token exchange failed: {message}", file=sys.stderr)
        raise SystemExit(1)

    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        print("Spotify did not return a refresh token.", file=sys.stderr)
        raise SystemExit(1)
    return str(refresh_token)


def _pluck_code_and_state(redirect_echo: str) -> tuple[str, str]:
    if redirect_echo.startswith(("http://", "https://")):
        parsed = urlparse(redirect_echo)
        params = parse_qs(parsed.query)
    else:
        params = parse_qs(redirect_echo)

    auth_code = params.get("code", [""])[0]
    oauth_state = params.get("state", [""])[0]
    if auth_code:
        return auth_code, oauth_state

    print("The redirect URL does not contain an OAuth code.", file=sys.stderr)
    raise SystemExit(1)


def _write_env_garden(env_garden: dict[str, str]) -> None:
    ordered_keys = [key for key in ENV_KEYS if key in env_garden]
    extra_keys = sorted(key for key in env_garden if key not in ENV_KEYS)
    lines = [_env_line(key, env_garden.get(key, "")) for key in ordered_keys + extra_keys]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _harden_env_file(ENV_PATH)


def _env_line(key: str, value: str) -> str:
    if value == "":
        return f"{key}="
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'{key}="{escaped}"'


def _harden_env_file(env_path: Path) -> None:
    if os.name == "nt":
        return
    try:
        env_path.chmod(0o600)
    except OSError as exc:
        print(f"Could not set .env permissions to 600: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
