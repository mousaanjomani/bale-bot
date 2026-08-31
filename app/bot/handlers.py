"""Update dispatch and command handlers.

کاربرد نهایی بات بعداً مشخص می‌شود؛ فعلاً ساختار پایه:
/start خوش‌آمدگویی + منوی دکمه‌ای، و پاسخ پیش‌فرض برای پیام‌های متنی.
"""
import logging

from app import config, store
from app.bot.client import BaleClient

log = logging.getLogger("bale.handlers")


def dispatch(client: BaleClient, update: dict) -> None:
    if "message" in update:
        _on_message(client, update["message"])
    elif "callback_query" in update:
        _on_callback(client, update["callback_query"])


def _on_message(client: BaleClient, msg: dict) -> None:
    chat = msg.get("chat") or {}
    user = msg.get("from") or {}
    chat_id = chat.get("id")
    text = msg.get("text", "")
    if chat_id is None:
        return

    store.upsert_user(
        chat_id,
        user.get("first_name", ""),
        user.get("last_name", ""),
        user.get("username", ""),
    )
    store.log_message(chat_id, "in", text)

    if text.startswith("/start"):
        reply = config.get("welcome_text", "سلام!")
        client.send_message(chat_id, reply, reply_markup=_main_menu())
        store.log_message(chat_id, "out", reply)
    else:
        reply = "پیام شما دریافت شد ✅"
        client.send_message(chat_id, reply)
        store.log_message(chat_id, "out", reply)


def _on_callback(client: BaleClient, cq: dict) -> None:
    data = cq.get("data", "")
    msg = cq.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    client.answer_callback(cq.get("id", ""))
    if chat_id is None:
        return
    if data == "about":
        client.send_message(chat_id, "این بات روی پیام‌رسان بله اجرا می‌شود.")


def _main_menu() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "درباره ما ℹ️", "callback_data": "about"}],
        ]
    }
