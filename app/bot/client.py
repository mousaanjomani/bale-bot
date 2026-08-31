"""Minimal client for the Bale Messenger Bot API.

Bale exposes a Telegram-compatible Bot API at https://tapi.bale.ai/bot<TOKEN>.
Only the methods this project needs are wrapped here.
"""
import logging

import requests

from app import config

log = logging.getLogger("bale.client")


class BaleClient:
    def __init__(self, token: str | None = None):
        self.token = token or config.get("bot_token")
        self.base = config.get("api_base", "https://tapi.bale.ai").rstrip("/")
        self.session = requests.Session()

    @property
    def url(self) -> str:
        return f"{self.base}/bot{self.token}"

    def call(self, method: str, timeout: int = 35, **params):
        try:
            r = self.session.post(f"{self.url}/{method}", json=params, timeout=timeout)
            data = r.json()
        except Exception as e:
            log.warning("API call %s failed: %s", method, e)
            return None
        if not data.get("ok"):
            log.warning("API %s returned error: %s", method, data)
            return None
        return data.get("result")

    def get_me(self):
        return self.call("getMe", timeout=15)

    def get_updates(self, offset: int = 0, poll_timeout: int = 25):
        try:
            r = self.session.post(
                f"{self.url}/getUpdates",
                json={"offset": offset, "timeout": poll_timeout},
                timeout=poll_timeout + 10,
            )
            data = r.json()
        except Exception as e:
            log.warning("getUpdates failed: %s", e)
            return None
        if not data.get("ok"):
            log.warning("getUpdates returned error: %s", data)
            return None
        return data.get("result")

    def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None):
        params = {"chat_id": chat_id, "text": text}
        if reply_markup:
            params["reply_markup"] = reply_markup
        return self.call("sendMessage", **params)

    def answer_callback(self, callback_query_id: str, text: str = ""):
        return self.call(
            "answerCallbackQuery", callback_query_id=callback_query_id, text=text
        )

    def edit_message_text(self, chat_id: int, message_id: int, text: str,
                          reply_markup: dict | None = None):
        params = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if reply_markup:
            params["reply_markup"] = reply_markup
        return self.call("editMessageText", **params)

    def send_photo(self, chat_id: int, photo: str, caption: str = ""):
        return self.call("sendPhoto", chat_id=chat_id, photo=photo, caption=caption)
