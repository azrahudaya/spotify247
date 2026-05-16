from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass

import requests

from app.config import Config, ConfigError, load_config
from app.spotify import SpotifyApiError, SpotifyClient
from app.telegram_api import TelegramApi, TelegramApiError


@dataclass(frozen=True)
class CheckLine:
    name: str
    state: str
    detail: str


def main() -> int:
    check_lines: list[CheckLine] = [_check_env_file()]

    try:
        config = load_config()
    except ConfigError as exc:
        check_lines.append(
            CheckLine(
                "config",
                "fail",
                f"{exc}. Run python -m app.setup.",
            )
        )
        _print_check_lines(check_lines)
        return 1

    check_lines.append(_check_allowed_users(config))
    check_lines.append(_check_telegram(config))

    spotify_client = SpotifyClient(config)
    check_lines.extend(_check_spotify(config, spotify_client))
    check_lines.extend(_check_host_stack(config))

    _print_check_lines(check_lines)
    return 1 if any(line.state == "fail" for line in check_lines) else 0


def _check_env_file() -> CheckLine:
    from pathlib import Path

    if Path(".env").exists():
        return CheckLine(".env", "ok", "Found .env in the project root.")
    return CheckLine(".env", "warn", "No .env file found. Run python -m app.setup.")


def _check_allowed_users(config: Config) -> CheckLine:
    if config.telegram_allowed_user_ids:
        user_count = len(config.telegram_allowed_user_ids)
        return CheckLine("allowed users", "ok", f"{user_count} Telegram user ID configured.")
    return CheckLine(
        "allowed users",
        "warn",
        "No Telegram user IDs configured. Only /whoami and /help will be useful.",
    )


def _check_telegram(config: Config) -> CheckLine:
    try:
        bot_profile = TelegramApi(config.telegram_bot_token).get_me()
    except (requests.RequestException, TelegramApiError) as exc:
        return CheckLine("telegram", "fail", str(exc))

    bot_name = bot_profile.get("username") or bot_profile.get("first_name") or "unknown"
    return CheckLine("telegram", "ok", f"Bot token works as @{bot_name}.")


def _check_spotify(
    config: Config,
    spotify_client: SpotifyClient,
) -> list[CheckLine]:
    check_lines: list[CheckLine] = []

    try:
        spotify_user = spotify_client.get_current_user()
    except (requests.RequestException, SpotifyApiError) as exc:
        return [CheckLine("spotify auth", "fail", str(exc))]

    account_label = (
        spotify_user.get("display_name")
        or spotify_user.get("id")
        or spotify_user.get("uri")
        or "connected account"
    )
    check_lines.append(CheckLine("spotify auth", "ok", f"Connected as {account_label}."))

    try:
        devices = spotify_client.get_devices()
    except (requests.RequestException, SpotifyApiError) as exc:
        check_lines.append(CheckLine("spotify devices", "fail", str(exc)))
        return check_lines

    if not devices:
        check_lines.append(
            CheckLine(
                "spotify devices",
                "warn",
                "No devices are online. Open Spotify or start spotifyd before using controls.",
            )
        )
        return check_lines

    try:
        target_device = spotify_client.get_target_device()
    except SpotifyApiError as exc:
        check_lines.append(CheckLine("spotify device", "warn", str(exc)))
        return check_lines

    mode_label = "named target" if config.spotify_device_name else "auto device"
    active_label = "active" if target_device.is_active else "online"
    check_lines.append(
        CheckLine(
            "spotify device",
            "ok",
            f"{mode_label}: {target_device.name} ({target_device.type}, {active_label}).",
        )
    )
    return check_lines


def _check_host_stack(config: Config) -> list[CheckLine]:
    if platform.system() != "Linux":
        return [
            CheckLine(
                "host stack",
                "warn",
                "This host is controller-only. Use Ubuntu/Debian VPS for spotifyd playback.",
            )
        ]

    check_lines: list[CheckLine] = []
    spotifyd_path = shutil.which("spotifyd")
    pulseaudio_path = shutil.which("pulseaudio")
    systemctl_path = shutil.which("systemctl")

    check_lines.append(
        CheckLine(
            "spotifyd",
            "ok" if spotifyd_path else "warn",
            spotifyd_path or "spotifyd is not installed on this host.",
        )
    )
    check_lines.append(
        CheckLine(
            "pulseaudio",
            "ok" if pulseaudio_path else "warn",
            pulseaudio_path or "pulseaudio is not installed on this host.",
        )
    )
    check_lines.append(
        CheckLine(
            "systemd",
            "ok" if systemctl_path else "warn",
            systemctl_path or "systemctl is not available on this host.",
        )
    )

    if not config.spotify_device_name:
        check_lines.append(
            CheckLine(
                "player mode",
                "warn",
                "SPOTIFY_DEVICE_NAME is empty. This is fine for controller-only mode.",
            )
        )
    return check_lines


def _print_check_lines(check_lines: list[CheckLine]) -> None:
    width = max(len(line.name) for line in check_lines) if check_lines else 0
    for line in check_lines:
        print(f"[{line.state.upper():4}] {line.name.ljust(width)}  {line.detail}")


if __name__ == "__main__":
    raise SystemExit(main())
