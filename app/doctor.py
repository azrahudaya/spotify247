from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

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
    env_path = Path(".env")
    if not env_path.exists():
        return CheckLine(".env", "warn", "No .env file found. Run python -m app.setup.")
    if env_path.is_symlink():
        return CheckLine(".env", "warn", ".env is a symlink. Make sure its target is private.")
    if os.name != "nt":
        loose_bits = env_path.stat().st_mode & 0o077
        if loose_bits:
            return CheckLine(
                ".env",
                "warn",
                f".env is readable outside the owner. Run chmod 600 .env.",
            )
        return CheckLine(".env", "ok", "Found .env with owner-only permissions.")
    return CheckLine(".env", "ok", "Found .env in the project root.")


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
    pactl_path = shutil.which("pactl")

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
    check_lines.append(_check_spotifyd_config())

    if pactl_path:
        check_lines.append(_check_pulse_sink())
    else:
        check_lines.append(
            CheckLine("pulse sink", "warn", "pactl is not available on this host.")
        )

    if systemctl_path:
        check_lines.extend(_check_systemd_user_units(config))
    if shutil.which("loginctl"):
        check_lines.append(_check_linger_state())

    if not config.spotify_device_name:
        check_lines.append(
            CheckLine(
                "player mode",
                "warn",
                "SPOTIFY_DEVICE_NAME is empty. This is fine for controller-only mode.",
            )
        )
    return check_lines


def _check_spotifyd_config() -> CheckLine:
    config_path = Path.home() / ".config" / "spotifyd" / "spotifyd.conf"
    if config_path.exists():
        return CheckLine("spotifyd config", "ok", str(config_path))
    return CheckLine(
        "spotifyd config",
        "warn",
        f"{config_path} was not found. Run scripts/setup_spotifyd.sh on VPS hosts.",
    )


def _check_pulse_sink() -> CheckLine:
    code, output = _run_host_probe(["pactl", "list", "short", "sinks"])
    if code != 0:
        return CheckLine("pulse sink", "warn", "PulseAudio sink list is unavailable.")
    if "spotify247" in output:
        return CheckLine("pulse sink", "ok", "spotify247 sink is available.")
    return CheckLine("pulse sink", "warn", "spotify247 sink was not found.")


def _check_systemd_user_units(config: Config) -> list[CheckLine]:
    unit_names = ["telegram-spotify-bot.service"]
    if config.spotify_device_name:
        unit_names.append("spotifyd.service")

    check_lines: list[CheckLine] = []
    for unit_name in unit_names:
        enabled_code, enabled_output = _run_host_probe(
            ["systemctl", "--user", "is-enabled", unit_name]
        )
        active_code, active_output = _run_host_probe(
            ["systemctl", "--user", "is-active", unit_name]
        )
        if enabled_code == 0 and active_code == 0:
            check_lines.append(
                CheckLine(unit_name, "ok", f"{enabled_output}; {active_output}.")
            )
        else:
            detail = ", ".join(
                item
                for item in (
                    enabled_output or "not enabled",
                    active_output or "not active",
                )
                if item
            )
            check_lines.append(CheckLine(unit_name, "warn", detail))
    return check_lines


def _check_linger_state() -> CheckLine:
    user_name = os.getenv("USER") or os.getenv("LOGNAME") or ""
    if not user_name:
        return CheckLine("linger", "warn", "Could not determine the current Linux user.")
    code, output = _run_host_probe(
        ["loginctl", "show-user", user_name, "-p", "Linger", "--value"]
    )
    if code == 0 and output.strip().lower() == "yes":
        return CheckLine("linger", "ok", f"linger is enabled for {user_name}.")
    return CheckLine(
        "linger",
        "warn",
        f"linger is not enabled for {user_name}. Run sudo loginctl enable-linger {user_name}.",
    )


def _run_host_probe(command: list[str]) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    output = (completed.stdout or completed.stderr).strip()
    return completed.returncode, output


def _print_check_lines(check_lines: list[CheckLine]) -> None:
    width = max(len(line.name) for line in check_lines) if check_lines else 0
    for line in check_lines:
        print(f"[{line.state.upper():4}] {line.name.ljust(width)}  {line.detail}")


if __name__ == "__main__":
    raise SystemExit(main())
