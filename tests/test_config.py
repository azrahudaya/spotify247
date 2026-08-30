from pathlib import Path

import pytest

from app.config import ConfigError, _parse_int, _parse_user_ids, load_config


def test_parse_user_ids_skips_empty_items():
    assert _parse_user_ids("123, 456,,") == (123, 456)


def test_parse_user_ids_rejects_non_integer():
    with pytest.raises(ConfigError, match="comma-separated integers"):
        _parse_user_ids("123,abc")


def test_parse_int_enforces_bounds():
    assert _parse_int("LIMIT", "5", minimum=1, maximum=10) == 5
    with pytest.raises(ConfigError, match="between 1 and 10"):
        _parse_int("LIMIT", "11", minimum=1, maximum=10)


def test_load_config_uses_defaults_and_env_file(tmp_path, monkeypatch):
    env_file = Path(tmp_path) / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=telegram\n"
        "SPOTIFY_CLIENT_ID=client\n"
        "SPOTIFY_CLIENT_SECRET=secret\n"
        "SPOTIFY_REFRESH_TOKEN=refresh\n"
        "TELEGRAM_ALLOWED_USER_IDS=10, 20\n"
    )
    monkeypatch.chdir(tmp_path)
    config = load_config()
    assert config.telegram_allowed_user_ids == (10, 20)
    assert config.spotify_redirect_uri == "http://127.0.0.1:8888/callback"
    assert config.bot_poll_timeout_seconds == 30
    assert config.bot_search_limit == 5


def test_load_config_reports_missing_values(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in (
        "TELEGRAM_BOT_TOKEN",
        "SPOTIFY_CLIENT_ID",
        "SPOTIFY_CLIENT_SECRET",
        "SPOTIFY_REFRESH_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        load_config()
