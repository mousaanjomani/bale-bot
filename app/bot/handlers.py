"""Bot handlers — سبک بات مرجع + اتوماسیون سازمانی.

جریان اصلی:
- /start → اگر حساب به پرسنل متصل نیست: درخواست کد پرسنلی؛ وگرنه منوی اصلی
- منوی اصلی: دکمه هر پروسه فعال + «کارتابل من» + «درخواست‌های من» + دکمه‌های سفارشی
- شروع پروسه → فرم مرحله‌به‌مرحله → خلاصه و تأیید → ورود به گردش تأییدها
- هر مسئول در کارتابل خود درخواست‌ها را تأیید/رد (یا اجرا: چک/حواله/نقد) می‌کند
"""
import json
import logging

from app import config, org, store
from app.bot import workflow
from app.bot.client import BaleClient
from app.utils import jalali
from app.utils.phone import normalize_phone

CONTACT_KEYBOARD = {
    "keyboard": [[{"text": "📱 ارسال شماره موبایل", "request_contact": True}]],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}
REMOVE_KEYBOARD = {"remove_keyboard": True}

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
        chat_id, user.get("first_name", ""), user.get("last_name", ""),
        user.get("username", ""),
    )
    store.log_message(chat_id, "in", text or "[contact]")

    if msg.get("contact"):
        _on_contact(client, chat_id, user, msg["contact"])
        return

    if text.startswith("/start"):
        store.set_chat_state(chat_id, None)
        _start(client, chat_id, user)
        return
    if text.startswith("/ok"):
        _ack_event(client, chat_id, text[3:])
        return
    if text.startswith("/e") and text[2:].isdigit():
        _event_detail(client, chat_id, text[2:])
        return

    state = store.get_chat_state(chat_id)
    if state:
        _handle_state(client, chat_id, text, state)
        return
    if store.person_by_chat(chat_id) is None:
        _reply(client, chat_id,
               "برای استفاده از بات ابتدا باید شناسایی شوید — "
               "با دکمه زیر شماره موبایل خود را به اشتراک بگذارید:",
               CONTACT_KEYBOARD)
        return
    _reply(client, chat_id, config.get("default_reply", "✅"))


def _start(client: BaleClient, chat_id: int, user: dict) -> None:
    org_name = config.get("org_name") or config.get("bot_display_name", "")
    person = store.person_by_chat(chat_id)
    if person:
        _reply(client, chat_id,
               f"سلام {person['name']} 🌿\nبه ربات «{org_name}» خوش آمدید.")
        _send_main_menu(client, chat_id, person)
    else:
        name = (user.get("first_name", "") + " " + user.get("last_name", "")).strip()
        _reply(client, chat_id,
               f"سلام {name or 'همکار گرامی'} 🌿\nبه ربات «{org_name}» خوش آمدید.\n\n"
               "برای شناسایی، لطفاً با دکمه زیر شماره موبایل خود را به اشتراک بگذارید:",
               CONTACT_KEYBOARD)


def _on_contact(client: BaleClient, chat_id: int, user: dict, contact: dict) -> None:
    owner_id = contact.get("user_id")
    if owner_id and user.get("id") and owner_id != user["id"]:
        _reply(client, chat_id,
               "لطفاً شماره موبایل «خودتان» را با دکمه ارسال کنید، نه مخاطب دیگری را.",
               CONTACT_KEYBOARD)
        return
    phone = normalize_phone(contact.get("phone_number", ""))
    if not phone:
        _reply(client, chat_id, "شماره دریافت نشد؛ دوباره تلاش کنید.", CONTACT_KEYBOARD)
        return
    store.set_user_phone(chat_id, phone)

    existing = store.person_by_chat(chat_id)
    if existing:
        _send_main_menu(client, chat_id, existing)
        return

    person = store.person_by_phone(phone)
    if person is None:
        _reply(client, chat_id,
               f"شماره {phone} دریافت و ثبت شد ✅\n"
               "اما این شماره هنوز در فهرست پرسنل تعریف نشده است.\n"
               "لطفاً به مدیر سیستم اطلاع دهید تا شما را اضافه کند؛ "
               "سپس دوباره /start را بزنید.", REMOVE_KEYBOARD)
        return
    if person["chat_id"] and person["chat_id"] != chat_id:
        _reply(client, chat_id,
               "این شماره قبلاً به حساب دیگری متصل شده است ⚠️\n"
               "در صورت مغایرت با مدیر سیستم تماس بگیرید.", REMOVE_KEYBOARD)
        return
    store.link_person_chat(person["id"], chat_id)
    store.set_chat_state(chat_id, None)
    _reply(client, chat_id,
           f"شناسایی انجام شد ✅\n{org.person_title(person['id'])}", REMOVE_KEYBOARD)
    _send_main_menu(client, chat_id, person)


def _handle_state(client: BaleClient, chat_id: int, text: str, state: dict) -> None:
    flow = state.get("flow")
    if flow == "form":
        _form_input(client, chat_id, text, state)
    elif flow == "reject_reason":
        _finish_reject(client, chat_id, text, state)
    else:
        store.set_chat_state(chat_id, None)
        _reply(client, chat_id, config.get("default_reply", "✅"))


# ---------------------------------------------------------------- main menu

def _send_main_menu(client: BaleClient, chat_id: int, person) -> None:
    _reply(client, chat_id, "چه کاری برایتان انجام دهم؟", _main_menu_markup())


def _main_menu_markup() -> dict:
    rows = []
    for proc in store.get_processes(active_only=True):
        rows.append([{"text": proc["button"], "callback_data": f"proc:{proc['id']}"}])
    rows.append([
        {"text": "📥 کارتابل من", "callback_data": "cartable"},
        {"text": "📋 درخواست‌های من", "callback_data": "myreqs"},
    ])
    # دکمه‌های سفارشی تعریف‌شده در داشبورد (اختیاری)
    pair = []
    for it in (config.get("menus", {}) or {}).get("extra", []):
        btn = {"text": it["title"], "callback_data": f"m:extra:{it['id']}"}
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


# ---------------------------------------------------------------- callbacks

def _on_callback(client: BaleClient, cq: dict) -> None:
    data = cq.get("data", "")
    msg = cq.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    client.answer_callback(cq.get("id", ""))
    if chat_id is None:
        return

    person = store.person_by_chat(chat_id)

    if data.startswith("proc:"):
        _start_process(client, chat_id, person, data[5:])
    elif data == "cartable":
        _show_cartable(client, chat_id, person)
    elif data == "myreqs":
        _show_my_requests(client, chat_id, person)
    elif data == "wz:ok":
        _form_submit(client, chat_id, person)
    elif data == "wz:cancel":
        store.set_chat_state(chat_id, None)
        _reply(client, chat_id, "درخواست لغو شد.", _main_menu_markup())
    elif data.startswith("rq:ap:"):
        _require_person(client, chat_id, person) and _reply(
            client, chat_id,
            workflow.decide(client, int(data[6:]), person["id"], approve=True))
    elif data.startswith("rq:rj:"):
        if _require_person(client, chat_id, person):
            store.set_chat_state(chat_id, {"flow": "reject_reason", "req": int(data[6:])})
            _reply(client, chat_id,
                   "علت رد درخواست را بنویسید (یا «-» برای رد بدون توضیح):")
    elif data.startswith("rq:ex:"):
        if _require_person(client, chat_id, person):
            _, _, req_id, idx = data.split(":")
            _reply(client, chat_id,
                   workflow.execute(client, int(req_id), person["id"], int(idx)))
    elif data.startswith("ack:"):
        _ack_event(client, chat_id, data[4:])
    elif data.startswith("ev:"):
        _event_detail(client, chat_id, data[3:])
    elif data.startswith("m:"):
        _custom_menu_click(client, chat_id, data)
    else:
        _expired(client, chat_id)


def _require_person(client: BaleClient, chat_id: int, person) -> bool:
    if person is None:
        _reply(client, chat_id,
               "ابتدا باید شناسایی شوید — /start را بزنید و شماره موبایل خود را به اشتراک بگذارید.")
        return False
    return True


def _expired(client: BaleClient, chat_id: int) -> None:
    _reply(client, chat_id, config.get("expired_button_text", ""), _main_menu_markup())


# ---------------------------------------------------------------- wizard

def _start_process(client: BaleClient, chat_id: int, person, proc_id: str) -> None:
    if not _require_person(client, chat_id, person):
        return
    proc = store.get_process(proc_id)
    if proc is None or not proc["active"]:
        _expired(client, chat_id)
        return
    # همه مراحل «شخص مشخص» باید به پرسنل موجود اشاره کنند
    for step in proc["steps"]:
        a = step.get("assignee") or {}
        if a.get("type") == "person" and not store.get_person(a.get("person") or ""):
            _reply(client, chat_id,
                   f"⚠️ پروسه «{proc['name']}» هنوز به‌طور کامل تنظیم نشده است "
                   f"(مسئول مرحله «{step.get('title', '')}» تعیین نشده).\n"
                   "لطفاً به مدیر سیستم اطلاع دهید.")
            return
    state = {"flow": "form", "proc": proc["id"], "idx": 0, "data": {}}
    store.set_chat_state(chat_id, state)
    _ask_field(client, chat_id, proc, 0)


def _ask_field(client: BaleClient, chat_id: int, proc: dict, idx: int) -> None:
    fields = proc["form"]
    if idx < len(fields):
        f = fields[idx]
        hint = " (فقط عدد)" if f.get("type") == "number" else ""
        _reply(client, chat_id,
               f"«{proc['name']}» — مرحله {idx + 1} از {len(fields)}\n"
               f"{f['label']}{hint} را وارد کنید:")


def _form_input(client: BaleClient, chat_id: int, text: str, state: dict) -> None:
    proc = store.get_process(state["proc"])
    if proc is None:
        store.set_chat_state(chat_id, None)
        _expired(client, chat_id)
        return
    fields = proc["form"]
    idx = state["idx"]
    f = fields[idx]
    value = text.strip()
    if f.get("type") == "number":
        value = workflow.normalize_number(value)
        if not value.isdigit():
            _reply(client, chat_id, "لطفاً فقط عدد وارد کنید:")
            return
    state["data"][f["key"]] = value
    state["idx"] = idx + 1
    store.set_chat_state(chat_id, state)
    if state["idx"] < len(fields):
        _ask_field(client, chat_id, proc, state["idx"])
    else:
        _confirm_form(client, chat_id, proc, state)


def _confirm_form(client: BaleClient, chat_id: int, proc: dict, state: dict) -> None:
    lines = [f"خلاصه «{proc['name']}»:"]
    for f in proc["form"]:
        val = state["data"].get(f["key"], "")
        if f.get("type") == "number":
            val = workflow.fmt_amount(val)
        lines.append(f"{f['label']}: {val}")
    lines.append("\nثبت شود؟")
    markup = {"inline_keyboard": [[
        {"text": "✅ ثبت درخواست", "callback_data": "wz:ok"},
        {"text": "❌ انصراف", "callback_data": "wz:cancel"},
    ]]}
    _reply(client, chat_id, "\n".join(lines), markup)


def _form_submit(client: BaleClient, chat_id: int, person) -> None:
    state = store.get_chat_state(chat_id)
    if not person or not state or state.get("flow") != "form":
        _expired(client, chat_id)
        return
    proc = store.get_process(state["proc"])
    store.set_chat_state(chat_id, None)
    if proc is None:
        _expired(client, chat_id)
        return
    req_id = workflow.submit(client, proc["id"], person["id"], state["data"])
    _reply(client, chat_id,
           f"درخواست شما ثبت شد ✅ (شماره پیگیری #{req_id})\n"
           "از «📋 درخواست‌های من» می‌توانید وضعیت آن را دنبال کنید.",
           _main_menu_markup())


def _finish_reject(client: BaleClient, chat_id: int, text: str, state: dict) -> None:
    person = store.person_by_chat(chat_id)
    store.set_chat_state(chat_id, None)
    if not person:
        return
    comment = "" if text.strip() in ("-", "،", ".") else text.strip()
    result = workflow.decide(client, state["req"], person["id"],
                             approve=False, comment=comment)
    _reply(client, chat_id, result)


# ---------------------------------------------------------------- cartable

def _show_cartable(client: BaleClient, chat_id: int, person) -> None:
    if not _require_person(client, chat_id, person):
        return
    items = store.cartable(person["id"])
    if not items:
        _reply(client, chat_id, "کارتابل شما خالی است ✅")
        return
    _reply(client, chat_id, f"📥 کارتابل شما — {len(items)} مورد در انتظار:")
    for req in items:
        proc = store.get_process(req["process_id"])
        step = proc["steps"][req["step"]]
        text = f"مرحله: {step['title']}\n\n" + workflow.request_summary(req, proc)
        markup = workflow._step_markup(req, step)
        client.send_message(chat_id, text, reply_markup=markup)
        store.log_message(chat_id, "out", text)


def _show_my_requests(client: BaleClient, chat_id: int, person) -> None:
    if not _require_person(client, chat_id, person):
        return
    items = store.my_requests(person["id"])
    if not items:
        _reply(client, chat_id, "شما هنوز درخواستی ثبت نکرده‌اید.")
        return
    lines = ["📋 درخواست‌های شما:"]
    for req in items:
        lines.append(workflow.status_line(req))
    _reply(client, chat_id, "\n".join(lines))


# ---------------------------------------------------------------- misc

def _custom_menu_click(client: BaleClient, chat_id: int, data: str) -> None:
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
    _reply(client, chat_id, item.get("reply") or config.get("wip_reply", "🛠"))


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


def _reply(client: BaleClient, chat_id: int, text: str, markup: dict | None = None) -> None:
    client.send_message(chat_id, text, reply_markup=markup)
    store.log_message(chat_id, "out", text)
