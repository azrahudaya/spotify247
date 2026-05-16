from __future__ import annotations

from typing import Any

import requests


class TelegramApiError(RuntimeError):
    pass


class TelegramApi:
    def __init__(self, bot_token: str) -> None:
        self._session = requests.Session()
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

    def get_updates(self, offset: int | None, timeout_seconds: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout_seconds,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset

        response = self._session.post(
            f"{self._base_url}/getUpdates",
            json=payload,
            timeout=(10, timeout_seconds + 10),
        )
        data = self._parse_response(response)
        return data["result"]

    def get_me(self) -> dict[str, Any]:
        response = self._session.post(
            f"{self._base_url}/getMe",
            timeout=20,
        )
        data = self._parse_response(response)
        return data["result"]

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
        reply_to_message_id: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id

        response = self._session.post(
            f"{self._base_url}/sendMessage",
            json=payload,
            timeout=20,
        )
        data = self._parse_response(response)
        return data["result"]

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        response = self._session.post(
            f"{self._base_url}/editMessageText",
            json=payload,
            timeout=20,
        )
        try:
            data = self._parse_response(response)
        except TelegramApiError as exc:
            if "message is not modified" in str(exc).lower():
                return None
            raise
        return data["result"]

    def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: str | None = None,
        show_alert: bool = False,
    ) -> None:
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text[:200]

        response = self._session.post(
            f"{self._base_url}/answerCallbackQuery",
            json=payload,
            timeout=10,
        )
        self._parse_response(response)

    @staticmethod
    def _parse_response(response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise TelegramApiError(
                f"Telegram returned non-JSON response: HTTP {response.status_code}"
            ) from exc

        if response.status_code != 200 or not data.get("ok", False):
            description = data.get("description", response.text.strip())
            raise TelegramApiError(
                f"Telegram API error {response.status_code}: {description}"
            )
        return data
