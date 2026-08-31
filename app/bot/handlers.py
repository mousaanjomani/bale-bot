"""Update dispatch and handlers — modeled on the reference bot:

- /start → خوش‌آمد شخصی‌شده + انتخاب نقش
- انتخاب نقش → ویرایش همان پیام: «نقش «X» انتخاب شد ✅ ...» + منوی دوستونه
- دکمه‌های منو از تنظیمات (داشبورد) خوانده می‌شوند
- دکمهٔ منقضی‌شده → پیام «این دکمه مربوط به صفحه‌ای است که بسته شده...» + منوی مجدد
- رویدادها: /okNNN (دیدم/تأیید) و /eNNN (شرح کامل) + دکمه‌های معادل
"""
import logging

from app import config, store
from app.bot.client import BaleClient
from app.utils import jalali

log = logging.getLogger("bale.handlers")


def dispatch(client: BaleClient, update: dict) -> None:
    if "message" in update:
        _on_message(client, update["message"])
    elif "callback_query" in update:
        _on_callback(client, update["callback_query"])


# ---------------------------------------------------------------- messages

def _on_message(client: BaleClient, msg: dict) -> None:
    chat = msg.get("chat") or {}
    user = msg.get("from") or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
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
        _send_welcome(client, chat_id, user)
    elif text.startswith("/ok"):
        _ack_event(client, chat_id, text[3:])
    elif text.startswith("/e") and text[2:].isdigit():
        _event_detail(client, chat_id, text[2:])
    else:
        _reply(client, chat_id, config.get("default_reply", "✅"))


def _send_welcome(client: BaleClient, chat_id: int, user: dict) -> None:
    name = (user.get("first_name", "") + " " + user.get("last_name", "")).strip() or "دوست عزیز"
    welcome = config.get("welcome_text", "").format(
        name=name, bot_name=config.get("bot_display_name", "")
    )
    _reply(client, chat_id, welcome)

    roles = config.get("roles", [])
    if len(roles) <= 1:
        role_key = roles[0]["key"] if roles else "staff"
        store.set_user_role(chat_id, role_key)
        _reply(client, chat_id, "چه کاری برایتان انجام دهم؟", _menu_markup(role_key))
    else:
        markup = {"inline_keyboard": [
            [{"text": r["title"], "callback_data": f"role:{r['key']}"}] for r in roles
        ]}
        _reply(client, chat_id, config.get("role_prompt", ""), markup)


# ---------------------------------------------------------------- callbacks

def _on_callback(client: BaleClient, cq: dict) -> None:
    data = cq.get("data", "")
    msg = cq.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    message_id = msg.get("message_id")
    client.answer_callback(cq.get("id", ""))
    if chat_id is None:
        return

    if data.startswith("role:"):
        _pick_role(client, chat_id, message_id, data[5:])
    elif data.startswith("m:"):
        _menu_click(client, chat_id, data)
    elif data.startswith("ack:"):
        _ack_event(client, chat_id, data[4:])
    elif data.startswith("ev:"):
        _event_detail(client, chat_id, data[3:])
    else:
        _expired(client, chat_id)


def _pick_role(client: BaleClient, chat_id: int, message_id: int | None, role_key: str) -> None:
    role = next((r for r in config.get("roles", []) if r["key"] == role_key), None)
    if role is None:
        _expired(client, chat_id)
        return
    store.set_user_role(chat_id, role_key)
    text = config.get("role_selected_text", "").format(role=role["title"])
    markup = _menu_markup(role_key)
    if message_id:
        client.edit_message_text(chat_id, message_id, text, reply_markup=markup)
    else:
        _reply(client, chat_id, text, markup)
    store.log_message(chat_id, "out", text)


def _menu_click(client: BaleClient, chat_id: int, data: str) -> None:
    # data = "m:<role>:<item_id>"
    try:
        _, role_key, item_id = data.split(":", 2)
    except ValueError:
        _expired(client, chat_id)
        return
    items = (config.get("menus", {}) or {}).get(role_key, [])
    item = next((i for i in items if i["id"] == item_id), None)
    if item is None:
        _expired(client, chat_id)
        return
    reply = item.get("reply") or config.get("wip_reply", "🛠")
    _reply(client, chat_id, reply)


def _expired(client: BaleClient, chat_id: int) -> None:
    role_key = store.get_user_role(chat_id) or _first_role_key()
    _reply(client, chat_id, config.get("expired_button_text", ""), _menu_markup(role_key))


# ---------------------------------------------------------------- events

def _ack_event(client: BaleClient, chat_id: int, event_id: str) -> None:
    event_id = event_id.strip().lstrip("#")
    ev = store.get_event(event_id)
    if ev is None:
        _reply(client, chat_id, f"رویداد #{event_id} یافت نشد.")
        return
    store.ack_event(event_id, chat_id)
    _reply(client, chat_id, f"رویداد #{event_id} تأیید شد ✅")


def _event_detail(client: BaleClient, chat_id: int, event_id: str) -> None:
    event_id = event_id.strip().lstrip("#")
    ev = store.get_event(event_id)
    if ev is None:
        _reply(client, chat_id, f"رویداد #{event_id} یافت نشد.")
        return
    text = (
        f"📄 شرح کامل رویداد #{event_id}\n"
        f"زمان: {jalali.now_str(ev['created'])}\n\n"
        f"{ev['detail'] or ev['title']}"
    )
    _reply(client, chat_id, text)


def send_event_to(client: BaleClient, chat_id: int, event_id: int, title: str) -> None:
    """اعلان رویداد به سبک بات مرجع: متن + شناسه + دکمه‌های دیدم/شرح کامل."""
    text = (
        f"({jalali.now_str()})\n"
        f"⚠️ {title}\n"
        f"رویداد #{event_id}\n\n"
        f"شرح کامل: /e{event_id}\n"
        f"دیدم (تأیید): /ok{event_id}"
    )
    markup = {"inline_keyboard": [[
        {"text": f"✅ دیدم #{event_id}", "callback_data": f"ack:{event_id}"},
        {"text": "📄 شرح کامل", "callback_data": f"ev:{event_id}"},
    ]]}
    _reply(client, chat_id, text, markup)


# ---------------------------------------------------------------- helpers

def _first_role_key() -> str:
    roles = config.get("roles", [])
    return roles[0]["key"] if roles else "staff"


def _menu_markup(role_key: str) -> dict:
    """منوی دوستونه؛ آیتم‌های wide یک ردیف کامل می‌گیرند."""
    items = (config.get("menus", {}) or {}).get(role_key, [])
    rows, pair = [], []
    for it in items:
        btn = {"text": it["title"], "callback_data": f"m:{role_key}:{it['id']}"}
        if it.get("wide"):
            if pair:
                rows.append(pair)
                pair = []
            rows.append([btn])
        else:
            pair.append(btn)
            if len(pair) == 2:
                rows.append(pair)
                pair = []
    if pair:
        rows.append(pair)
    return {"inline_keyboard": rows}


def _reply(client: BaleClient, chat_id: int, text: str, markup: dict | None = None) -> None:
    client.send_message(chat_id, text, reply_markup=markup)
    store.log_message(chat_id, "out", text)
