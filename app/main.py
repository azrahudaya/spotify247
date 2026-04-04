from __future__ import annotations

import logging
import sys

from app.bot import SpotifyTelegramBot
from app.config import ConfigError, load_config
from app.spotify import SpotifyClient
from app.telegram_api import TelegramApi


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    telegram_api = TelegramApi(config.telegram_bot_token)
    spotify_client = SpotifyClient(config)
    bot = SpotifyTelegramBot(config, telegram_api, spotify_client)
    bot.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

