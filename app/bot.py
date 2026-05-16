from __future__ import annotations

import html
import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from app.config import Config
from app.spotify import SpotifyApiError, SpotifyClient
from app.telegram_api import TelegramApi, TelegramApiError


logger = logging.getLogger(__name__)


@dataclass
class RenderedMessage:
    text: str
    reply_markup: dict[str, Any]


class SpotifyTelegramBot:
    def __init__(
        self,
        config: Config,
        telegram_api: TelegramApi,
        spotify_client: SpotifyClient,
    ) -> None:
        self._config = config
        self._telegram = telegram_api
        self._spotify = spotify_client
        self._pending_search_users: dict[int, int] = {}
        self._panel_messages: dict[int, int] = {}

    def run_forever(self) -> None:
        offset: int | None = None

        while True:
            try:
                updates = self._telegram.get_updates(
                    offset=offset,
                    timeout_seconds=self._config.bot_poll_timeout_seconds,
                )
                for update in updates:
                    offset = update["update_id"] + 1
                    self._handle_update(update)
            except (requests.RequestException, TelegramApiError) as exc:
                logger.warning("Telegram polling issue: %s", exc)
                time.sleep(3)
            except Exception:
                logger.exception("Unexpected bot error")
                time.sleep(3)

    def _handle_update(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            self._handle_callback_query(update["callback_query"])
        elif "message" in update:
            self._handle_message(update["message"])

    def _handle_message(self, message: dict[str, Any]) -> None:
        chat = message.get("chat", {})
        from_user = message.get("from", {})
        chat_id = chat.get("id")
        user_id = from_user.get("id")
        message_id = message.get("message_id")
        text = (message.get("text") or "").strip()

        if not chat_id or not user_id or not text:
            return

        if text.startswith("/"):
            self._handle_command(chat_id, user_id, message_id, text)
            return

        if not self._is_authorized(user_id):
            return

        if self._pending_search_users.get(chat_id) == user_id:
            self._pending_search_users.pop(chat_id, None)
            self._send_search_results(
                chat_id,
                query=text,
                reply_to_message_id=message_id,
            )

    def _handle_command(
        self,
        chat_id: int,
        user_id: int,
        message_id: int,
        raw_text: str,
    ) -> None:
        command_with_target, _, argument_text = raw_text.partition(" ")
        command = command_with_target.split("@", 1)[0]
        argument_text = argument_text.strip()
        command = command.lower()

        if command in {"/start", "/help"}:
            self._telegram.send_message(chat_id, self._help_text(user_id))
            return

        if command == "/whoami":
            self._telegram.send_message(
                chat_id,
                (
                    "<b>Telegram Identity</b>\n"
                    f"User ID: <code>{user_id}</code>\n"
                    f"Chat ID: <code>{chat_id}</code>"
                ),
            )
            return

        if not self._is_authorized(user_id):
            self._telegram.send_message(
                chat_id,
                (
                    "Access denied.\n"
                    "Add your user ID to <code>TELEGRAM_ALLOWED_USER_IDS</code>.\n"
                    f"Your user ID: <code>{user_id}</code>"
                ),
            )
            return

        try:
            if command in {"/panel", "/status", "/now"}:
                self._send_or_replace_panel(chat_id)
                return

            if command == "/play":
                self._spotify.resume()
                self._send_or_replace_panel(chat_id)
                return

            if command == "/pause":
                self._spotify.pause()
                self._send_or_replace_panel(chat_id)
                return

            if command == "/next":
                self._spotify.next_track()
                self._send_or_replace_panel(chat_id)
                return

            if command in {"/prev", "/previous"}:
                self._spotify.previous_track()
                self._send_or_replace_panel(chat_id)
                return

            if command == "/repeat":
                if argument_text:
                    self._spotify.set_repeat(argument_text.lower())
                else:
                    self._spotify.cycle_repeat()
                self._send_or_replace_panel(chat_id)
                return

            if command == "/shuffle":
                if argument_text in {"on", "true", "1"}:
                    self._spotify.set_shuffle(True)
                elif argument_text in {"off", "false", "0"}:
                    self._spotify.set_shuffle(False)
                else:
                    self._spotify.toggle_shuffle()
                self._send_or_replace_panel(chat_id)
                return

            if command == "/volume":
                if not argument_text:
                    raise SpotifyApiError("Use /volume 0-100.")
                self._spotify.set_volume(int(argument_text))
                self._send_or_replace_panel(chat_id)
                return

            if command == "/search":
                if argument_text:
                    self._send_search_results(chat_id, query=argument_text)
                else:
                    self._pending_search_users[chat_id] = user_id
                    self._telegram.send_message(
                        chat_id,
                        "Send a song title to search. Example: <code>Joji slow dancing</code>",
                        reply_to_message_id=message_id,
                    )
                return

            if command == "/devices":
                self._telegram.send_message(chat_id, self._devices_text())
                return

            self._telegram.send_message(chat_id, self._help_text(user_id))
        except (SpotifyApiError, ValueError) as exc:
            self._telegram.send_message(
                chat_id,
                f"<b>Error</b>\n{html.escape(str(exc))}",
                reply_to_message_id=message_id,
            )

    def _handle_callback_query(self, callback_query: dict[str, Any]) -> None:
        callback_id = callback_query["id"]
        from_user = callback_query.get("from", {})
        user_id = from_user.get("id")
        message = callback_query.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        message_id = message.get("message_id")
        data = callback_query.get("data", "")

        if not user_id or not chat_id or not message_id:
            self._telegram.answer_callback_query(
                callback_id,
                text="Invalid callback.",
                show_alert=True,
            )
            return

        if not self._is_authorized(user_id):
            self._telegram.answer_callback_query(
                callback_id,
                text="Access denied.",
                show_alert=True,
            )
            return

        try:
            if data == "action:search":
                self._pending_search_users[chat_id] = user_id
                self._telegram.answer_callback_query(
                    callback_id,
                    text="Send a song title in this chat.",
                )
                self._telegram.send_message(
                    chat_id,
                    "Search mode is on. Send a song title to play it on the VPS.",
                    reply_to_message_id=message_id,
                )
                return

            if data == "action:refresh":
                self._refresh_panel_message(chat_id, message_id)
                self._telegram.answer_callback_query(callback_id, text="Panel refreshed.")
                return

            if data == "action:toggle":
                self._spotify.toggle_playback()
            elif data == "action:prev":
                self._spotify.previous_track()
            elif data == "action:next":
                self._spotify.next_track()
            elif data == "action:repeat":
                next_state = self._spotify.cycle_repeat()
                self._telegram.answer_callback_query(
                    callback_id,
                    text=f"Repeat: {next_state}.",
                )
                self._refresh_panel_message(chat_id, message_id)
                return
            elif data == "action:shuffle":
                shuffle_state = self._spotify.toggle_shuffle()
                self._telegram.answer_callback_query(
                    callback_id,
                    text=f"Shuffle {'on' if shuffle_state else 'off'}.",
                )
                self._refresh_panel_message(chat_id, message_id)
                return
            elif data == "action:vol_down":
                next_volume = self._spotify.change_volume(-10)
                self._telegram.answer_callback_query(
                    callback_id,
                    text=f"Volume {next_volume}%",
                )
                self._refresh_panel_message(chat_id, message_id)
                return
            elif data == "action:vol_up":
                next_volume = self._spotify.change_volume(10)
                self._telegram.answer_callback_query(
                    callback_id,
                    text=f"Volume {next_volume}%",
                )
                self._refresh_panel_message(chat_id, message_id)
                return
            elif data.startswith("track:"):
                track_id = data.split(":", 1)[1]
                self._spotify.play_track(track_id)
            else:
                self._telegram.answer_callback_query(
                    callback_id,
                    text="Unknown action.",
                    show_alert=True,
                )
                return

            self._telegram.answer_callback_query(callback_id, text="Done.")
            self._refresh_panel_message(chat_id, message_id)
        except SpotifyApiError as exc:
            self._telegram.answer_callback_query(
                callback_id,
                text=str(exc),
                show_alert=True,
            )

    def _send_or_replace_panel(self, chat_id: int) -> None:
        rendered = self._render_panel()
        existing_message_id = self._panel_messages.get(chat_id)

        if existing_message_id:
            try:
                self._telegram.edit_message_text(
                    chat_id=chat_id,
                    message_id=existing_message_id,
                    text=rendered.text,
                    reply_markup=rendered.reply_markup,
                )
                return
            except TelegramApiError:
                logger.info("Falling back to a new panel message for chat %s", chat_id)

        sent_message = self._telegram.send_message(
            chat_id=chat_id,
            text=rendered.text,
            reply_markup=rendered.reply_markup,
        )
        self._panel_messages[chat_id] = sent_message["message_id"]

    def _refresh_panel_message(self, chat_id: int, message_id: int) -> None:
        rendered = self._render_panel()
        self._telegram.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=rendered.text,
            reply_markup=rendered.reply_markup,
        )
        self._panel_messages[chat_id] = message_id

    def _render_panel(self) -> RenderedMessage:
        playback = self._spotify.get_playback()
        target_device = None
        target_status = "offline"
        target_device_name = self._config.spotify_device_name or "Auto device"

        try:
            target_device = self._spotify.get_target_device()
            target_device_name = target_device.name
            target_status = "active" if target_device.is_active else "online"
        except SpotifyApiError:
            target_device = None

        track = (playback or {}).get("item")
        current_device = (playback or {}).get("device", {})
        is_target_active = bool(
            playback
            and target_device
            and current_device.get("id") == target_device.device_id
        )

        lines = ["<b>Spotify VPS Panel</b>", ""]
        lines.append(
            "Playback device: "
            f"<code>{html.escape(target_device_name)}</code> ({html.escape(target_status)})"
        )

        if playback and track:
            artists = ", ".join(
                artist.get("name", "Unknown Artist")
                for artist in track.get("artists", [])
            ) or "Unknown Artist"
            progress_ms = int(playback.get("progress_ms") or 0)
            duration_ms = int(track.get("duration_ms") or 0)
            status = "Playing" if playback.get("is_playing") else "Paused"
            if not is_target_active:
                status += " on another device"

            lines.extend(
                [
                    f"Status: <b>{status}</b>",
                    f"Track: <b>{html.escape(track.get('name', 'Unknown Track'))}</b>",
                    f"Artist: {html.escape(artists)}",
                    f"Album: {html.escape(track.get('album', {}).get('name', 'Unknown Album'))}",
                    f"Progress: {self._format_ms(progress_ms)} / {self._format_ms(duration_ms)}",
                    f"Repeat: {html.escape(str(playback.get('repeat_state', 'off')))}",
                    f"Shuffle: {'on' if playback.get('shuffle_state') else 'off'}",
                    (
                        "Current device: "
                        f"<code>{html.escape(current_device.get('name', 'unknown'))}</code>"
                    ),
                ]
            )
        else:
            lines.extend(
                [
                    "Status: <b>Idle</b>",
                    "No active track on the target device.",
                ]
            )

        keyboard: list[list[dict[str, Any]]] = [
            [
                {"text": "Prev", "callback_data": "action:prev"},
                {"text": "Play/Pause", "callback_data": "action:toggle"},
                {"text": "Next", "callback_data": "action:next"},
            ],
            [
                {
                    "text": f"Repeat: {self._repeat_label(playback)}",
                    "callback_data": "action:repeat",
                },
                {
                    "text": f"{'Shuffle On' if (playback or {}).get('shuffle_state') else 'Shuffle Off'}",
                    "callback_data": "action:shuffle",
                },
            ],
            [
                {"text": "Vol -10", "callback_data": "action:vol_down"},
                {"text": "Vol +10", "callback_data": "action:vol_up"},
            ],
            [
                {"text": "Search", "callback_data": "action:search"},
                {"text": "Refresh", "callback_data": "action:refresh"},
            ],
        ]

        if track and track.get("external_urls", {}).get("spotify"):
            keyboard.append(
                [
                    {
                        "text": "Open in Spotify",
                        "url": track["external_urls"]["spotify"],
                    }
                ]
            )

        return RenderedMessage(
            text="\n".join(lines),
            reply_markup={"inline_keyboard": keyboard},
        )

    def _send_search_results(
        self,
        chat_id: int,
        *,
        query: str,
        reply_to_message_id: int | None = None,
    ) -> None:
        tracks = self._spotify.search_tracks(query)
        if not tracks:
            self._telegram.send_message(
                chat_id,
                f"No results for <code>{html.escape(query)}</code>.",
                reply_to_message_id=reply_to_message_id,
            )
            return

        text_lines = [
            "<b>Search Results</b>",
            f"Query: <code>{html.escape(query)}</code>",
            "Choose a track to play on the VPS:",
        ]
        keyboard: list[list[dict[str, Any]]] = []
        for track in tracks:
            artists = ", ".join(
                artist.get("name", "Unknown Artist")
                for artist in track.get("artists", [])
            ) or "Unknown Artist"
            title = track.get("name", "Unknown Track")
            keyboard.append(
                [
                    {
                        "text": self._truncate_button_label(f"{title} - {artists}"),
                        "callback_data": f"track:{track['id']}",
                    }
                ]
            )

        self._telegram.send_message(
            chat_id,
            "\n".join(text_lines),
            reply_markup={"inline_keyboard": keyboard},
            reply_to_message_id=reply_to_message_id,
        )

    def _devices_text(self) -> str:
        devices = self._spotify.get_devices()
        if not devices:
            return "<b>Devices</b>\nNo Spotify devices are online."

        lines = ["<b>Devices</b>"]
        for device in devices:
            status = []
            if device.get("is_active"):
                status.append("active")
            if device.get("is_restricted"):
                status.append("restricted")
            if not status:
                status.append("idle")

            volume = device.get("volume_percent")
            volume_text = f"{volume}%" if volume is not None else "n/a"
            lines.append(
                (
                    f"- <code>{html.escape(device.get('name', 'unknown'))}</code> | "
                    f"{html.escape(device.get('type', 'unknown'))} | "
                    f"{html.escape(', '.join(status))} | vol {volume_text}"
                )
            )
        return "\n".join(lines)

    def _help_text(self, user_id: int) -> str:
        lines = [
            "<b>Spotify Telegram Bot</b>",
            "",
            "Commands:",
            "/panel - show the control panel",
            "/search &lt;query&gt; - search and pick a track",
            "/play, /pause, /next, /prev",
            "/repeat [off|track|context]",
            "/shuffle [on|off]",
            "/volume 0-100",
            "/devices - show online Spotify devices",
            "/whoami - show your Telegram user ID",
            "",
        ]

        if self._is_authorized(user_id):
            lines.append("This user can control the bot.")
        else:
            lines.append(
                "This user is not allowed. Add the user ID to "
                "<code>TELEGRAM_ALLOWED_USER_IDS</code>."
            )
        return "\n".join(lines)

    def _is_authorized(self, user_id: int) -> bool:
        allowed = self._config.telegram_allowed_user_ids
        if not allowed:
            return False
        return user_id in allowed

    @staticmethod
    def _truncate_button_label(label: str, maximum_length: int = 56) -> str:
        if len(label) <= maximum_length:
            return label
        return label[: maximum_length - 1] + "..."

    @staticmethod
    def _repeat_label(playback: dict[str, Any] | None) -> str:
        state = (playback or {}).get("repeat_state", "off")
        return str(state).capitalize()

    @staticmethod
    def _format_ms(milliseconds: int) -> str:
        total_seconds = max(0, milliseconds // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:d}:{seconds:02d}"
