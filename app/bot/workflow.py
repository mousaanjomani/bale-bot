"""Request engine: submit, approve/reject, execute, and notifications."""
import json
import logging

from app import org, store
from app.bot.client import BaleClient
from app.utils import jalali

log = logging.getLogger("workflow")

FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_number(text: str) -> str:
    return text.translate(FA_DIGITS).replace(",", "").replace("٬", "").strip()


def fmt_amount(value) -> str:
    try:
        return f"{int(str(value)):,}"
    except (TypeError, ValueError):
        return str(value)


def request_summary(req, proc: dict | None = None) -> str:
    proc = proc or store.get_process(req["process_id"])
    data = json.loads(req["data"] or "{}")
    lines = [f"درخواست #{req['id']} — {proc['name'] if proc else ''}"]
    lines.append(f"درخواست‌کننده: {org.person_title(req['requester'])}")
    for f in (proc["form"] if proc else []):
        val = data.get(f["key"], "—")
        if f.get("type") == "number":
            val = fmt_amount(val) + " ریال" if f["key"] == "amount" else fmt_amount(val)
        lines.append(f"{f['label']}: {val}")
    lines.append(f"تاریخ ثبت: {jalali.now_str(req['created'])}")
    return "\n".join(lines)


def _notify(client: BaleClient, person_id: str, text: str,
            markup: dict | None = None) -> bool:
    p = store.get_person(person_id)
    if not p or not p["chat_id"]:
        return False
    client.send_message(p["chat_id"], text, reply_markup=markup)
    store.log_message(p["chat_id"], "out", text)
    return True


def _step_markup(req, step: dict) -> dict:
    rows = []
    if step.get("execute"):
        options = step.get("options") or ["انجام شد"]
        rows = [[{"text": f"✅ {o}", "callback_data": f"rq:ex:{req['id']}:{i}"}]
                for i, o in enumerate(options)]
        rows.append([{"text": "❌ رد درخواست", "callback_data": f"rq:rj:{req['id']}"}])
    else:
        rows = [[
            {"text": "✅ تأیید", "callback_data": f"rq:ap:{req['id']}"},
            {"text": "❌ رد", "callback_data": f"rq:rj:{req['id']}"},
        ]]
    return {"inline_keyboard": rows}


def notify_assignee(client: BaleClient, req, proc: dict | None = None) -> None:
    proc = proc or store.get_process(req["process_id"])
    step = proc["steps"][req["step"]]
    text = (
        f"🔔 درخواست جدید در کارتابل شما\n"
        f"مرحله: {step['title']}\n\n" + request_summary(req, proc)
    )
    if not _notify(client, req["assignee"], text, _step_markup(req, step)):
        _notify(client, req["requester"],
                f"⚠️ مسئول مرحله «{step['title']}» هنوز به بات متصل نشده است؛ "
                f"درخواست #{req['id']} در کارتابل ایشان می‌ماند.")


def submit(client: BaleClient, process_id: int, requester: str, data: dict) -> int:
    req_id = store.create_request(process_id, requester, data)
    store.add_request_log(req_id, -1, requester, "submit")
    _advance(client, req_id, start_step=0)
    return req_id


def _advance(client: BaleClient, req_id: int, start_step: int) -> None:
    """Move the request to the first actionable step at/after start_step."""
    req = store.get_request(req_id)
    proc = store.get_process(req["process_id"])
    steps = proc["steps"]
    idx = start_step
    while idx < len(steps):
        step = steps[idx]
        assignee = org.resolve_assignee(step, req["requester"])
        if assignee is None:
            store.add_request_log(req_id, idx, "", "approve",
                                  "مسئول تعریف نشده — عبور خودکار")
            idx += 1
            continue
        if assignee == req["requester"] and not step.get("execute"):
            store.add_request_log(req_id, idx, assignee, "approve",
                                  "درخواست‌کننده خودِ مسئول است — تأیید خودکار")
            idx += 1
            continue
        store.update_request(req_id, step=idx, assignee=assignee)
        req = store.get_request(req_id)
        notify_assignee(client, req, proc)
        return
    # همه مراحل طی شد
    import time
    store.update_request(req_id, status="done", assignee=None,
                         closed=int(time.time()))
    _notify(client, req["requester"],
            f"✅ درخواست #{req_id} به پایان رسید و انجام شد.")


def decide(client: BaleClient, req_id: int, actor: str, approve: bool,
           comment: str = "") -> str:
    req = store.get_request(req_id)
    if req is None or req["status"] != "pending":
        return "این درخواست دیگر در جریان نیست."
    if req["assignee"] != actor:
        return "این درخواست در کارتابل شما نیست."
    proc = store.get_process(req["process_id"])
    step = proc["steps"][req["step"]]
    if approve:
        store.add_request_log(req_id, req["step"], actor, "approve", comment)
        _notify(client, req["requester"],
                f"✅ درخواست #{req_id} در مرحله «{step['title']}» تأیید شد.")
        _advance(client, req_id, start_step=req["step"] + 1)
        return f"درخواست #{req_id} تأیید شد ✅"
    import time
    store.add_request_log(req_id, req["step"], actor, "reject", comment)
    store.update_request(req_id, status="rejected", assignee=None,
                         closed=int(time.time()))
    reason = f"\nعلت: {comment}" if comment else ""
    _notify(client, req["requester"],
            f"❌ درخواست #{req_id} در مرحله «{step['title']}» رد شد.{reason}")
    return f"درخواست #{req_id} رد شد ❌"


def execute(client: BaleClient, req_id: int, actor: str, option_idx: int) -> str:
    req = store.get_request(req_id)
    if req is None or req["status"] != "pending":
        return "این درخواست دیگر در جریان نیست."
    if req["assignee"] != actor:
        return "این درخواست در کارتابل شما نیست."
    proc = store.get_process(req["process_id"])
    step = proc["steps"][req["step"]]
    options = step.get("options") or ["انجام شد"]
    if not (0 <= option_idx < len(options)):
        return "گزینه نامعتبر است."
    choice = options[option_idx]
    store.add_request_log(req_id, req["step"], actor, "execute", choice)
    store.update_request(req_id, result=choice)
    _notify(client, req["requester"],
            f"✅ درخواست #{req_id}: «{step['title']}» انجام شد — {choice}")
    _advance(client, req_id, start_step=req["step"] + 1)
    return f"ثبت شد: {choice} ✅"


STATUS_FA = {"pending": "⏳ در جریان", "done": "✅ انجام شده", "rejected": "❌ رد شده"}


def status_line(req) -> str:
    proc = store.get_process(req["process_id"])
    st = STATUS_FA.get(req["status"], req["status"])
    extra = ""
    if req["status"] == "pending" and req["assignee"]:
        step = proc["steps"][req["step"]] if req["step"] < len(proc["steps"]) else {}
        extra = f" — نزد {org.person_title(req['assignee'])} ({step.get('title', '')})"
    elif req["result"]:
        extra = f" — {req['result']}"
    return f"#{req['id']} {proc['name'] if proc else ''} — {st}{extra}"
