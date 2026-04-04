from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_allowed_user_ids: tuple[int, ...]
    spotify_client_id: str
    spotify_client_secret: str
    spotify_refresh_token: str
    spotify_redirect_uri: str
    spotify_device_name: str
    spotify_market: str | None
    bot_poll_timeout_seconds: int
    bot_search_limit: int
    log_level: str


def load_config() -> Config:
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)

    required = {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        "SPOTIFY_CLIENT_ID": os.getenv("SPOTIFY_CLIENT_ID", "").strip(),
        "SPOTIFY_CLIENT_SECRET": os.getenv("SPOTIFY_CLIENT_SECRET", "").strip(),
        "SPOTIFY_REFRESH_TOKEN": os.getenv("SPOTIFY_REFRESH_TOKEN", "").strip(),
        "SPOTIFY_REDIRECT_URI": os.getenv("SPOTIFY_REDIRECT_URI", "").strip(),
        "SPOTIFY_DEVICE_NAME": os.getenv("SPOTIFY_DEVICE_NAME", "").strip(),
    }

    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ConfigError(
            "Missing required environment variables: " + ", ".join(sorted(missing))
        )

    search_limit = _parse_int(
        "BOT_SEARCH_LIMIT",
        os.getenv("BOT_SEARCH_LIMIT", "5"),
        minimum=1,
        maximum=10,
    )
    poll_timeout = _parse_int(
        "BOT_POLL_TIMEOUT_SECONDS",
        os.getenv("BOT_POLL_TIMEOUT_SECONDS", "30"),
        minimum=5,
        maximum=50,
    )

    return Config(
        telegram_bot_token=required["TELEGRAM_BOT_TOKEN"],
        telegram_allowed_user_ids=_parse_user_ids(
            os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
        ),
        spotify_client_id=required["SPOTIFY_CLIENT_ID"],
        spotify_client_secret=required["SPOTIFY_CLIENT_SECRET"],
        spotify_refresh_token=required["SPOTIFY_REFRESH_TOKEN"],
        spotify_redirect_uri=required["SPOTIFY_REDIRECT_URI"],
        spotify_device_name=required["SPOTIFY_DEVICE_NAME"],
        spotify_market=os.getenv("SPOTIFY_MARKET", "").strip() or None,
        bot_poll_timeout_seconds=poll_timeout,
        bot_search_limit=search_limit,
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
    )


def _parse_user_ids(raw_value: str) -> tuple[int, ...]:
    if not raw_value.strip():
        return tuple()

    user_ids: list[int] = []
    for item in raw_value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            user_ids.append(int(item))
        except ValueError as exc:
            raise ConfigError(
                "TELEGRAM_ALLOWED_USER_IDS must contain comma-separated integers."
            ) from exc
    return tuple(user_ids)


def _parse_int(name: str, raw_value: str, minimum: int, maximum: int) -> int:
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc

    if value < minimum or value > maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}.")
    return value

