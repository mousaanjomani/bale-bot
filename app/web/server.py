"""Flask web dashboard for managing the Bale bot on the customer server."""
import functools
import glob
import json
import logging
import os
import threading
import time

from flask import (
    Flask, flash, jsonify, redirect, render_template, request, send_file,
    session, url_for,
)

from app import config, org, store, updater
from app.bot import poller, workflow
from app.version import __version__

log = logging.getLogger("web")

app = Flask(__name__)
app.secret_key = config.get("secret_key")


def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def _logo_file():
    files = glob.glob(os.path.join(config.DATA_DIR, "logo.*"))
    return files[0] if files else None


@app.context_processor
def inject_globals():
    latest = updater.state.get("latest") or {}
    return {
        "version": __version__,
        "update_available": latest.get("has_update") and latest.get("latest"),
        "org_name": config.get("org_name", ""),
        "has_logo": bool(_logo_file()),
    }


@app.template_filter("dt")
def fmt_dt(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(ts)))
    except Exception:
        return "—"


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        if u == config.get("admin_user") and p == config.get("admin_password"):
            session["logged_in"] = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "نام کاربری یا رمز عبور اشتباه است."
        time.sleep(1)
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    p = poller.get()
    status = p.status if p else "stopped"
    bot_info = p.bot_info if p else None
    uptime = int(time.time() - p.started_at) if p else 0
    return render_template(
        "dashboard.html",
        status=status,
        bot_info=bot_info,
        uptime=uptime,
        user_count=store.count_users(),
        msg_count=store.count_messages(),
        token_set=bool(config.get("bot_token")),
        bot_enabled=config.get("bot_enabled", True),
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        values = {
            "bot_token": request.form.get("bot_token", "").strip(),
            "bot_display_name": request.form.get("bot_display_name", "").strip(),
            "default_reply": request.form.get("default_reply", "").strip(),
            "wip_reply": request.form.get("wip_reply", "").strip(),
            "admin_user": request.form.get("admin_user", "admin").strip() or "admin",
        }
        new_pass = request.form.get("admin_password", "")
        if new_pass:
            values["admin_password"] = new_pass
        try:
            values["web_port"] = int(request.form.get("web_port", 8585))
        except ValueError:
            pass
        config.update(values)
        flash("تنظیمات ذخیره شد. ✅")
        return redirect(url_for("settings"))
    return render_template("settings.html", cfg=config.all_config())


@app.route("/menu", methods=["GET", "POST"])
@login_required
def menu_editor():
    if request.method == "POST":
        try:
            items = json.loads(request.form.get("data", "[]"))
            assert isinstance(items, list)
            config.update({"menus": {"extra": items}})
            flash("دکمه‌های سفارشی ذخیره شد. ✅")
        except Exception:
            flash("خطا در ذخیره — ساختار نامعتبر است.")
        return redirect(url_for("menu_editor"))
    return render_template(
        "menu.html",
        items=(config.get("menus", {}) or {}).get("extra", []),
    )


# ---------------------------------------------------------------- org chart

@app.route("/org", methods=["GET", "POST"])
@login_required
def org_page():
    if request.method == "POST":
        try:
            data = json.loads(request.form.get("data", "{}"))
            units = data.get("units", [])
            people = data.get("people", [])
            assert isinstance(units, list) and isinstance(people, list)
            store.replace_org(units, people)
            flash("چارت سازمانی ذخیره شد. ✅")
        except Exception:
            log.exception("org save failed")
            flash("خطا در ذخیره چارت سازمانی.")
        return redirect(url_for("org_page"))
    units = [dict(u) for u in store.get_units()]
    people = [dict(p) for p in store.get_people()]
    return render_template(
        "org.html", units=units, people=people,
        bot_users=[dict(u) for u in store.get_users(limit=500)],
    )


@app.route("/org/settings", methods=["POST"])
@login_required
def org_settings():
    config.update({"org_name": request.form.get("org_name", "").strip()})
    f = request.files.get("logo")
    if f and f.filename:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
            for old in glob.glob(os.path.join(config.DATA_DIR, "logo.*")):
                os.remove(old)
            f.save(os.path.join(config.DATA_DIR, "logo" + ext))
        else:
            flash("فرمت لوگو باید تصویر باشد (png/jpg/svg/...).")
    flash("مشخصات سازمان ذخیره شد. ✅")
    return redirect(url_for("org_page"))


@app.route("/logo")
def logo():
    path = _logo_file()
    if not path:
        return ("", 404)
    return send_file(path)


# ---------------------------------------------------------------- processes

@app.route("/processes", methods=["GET", "POST"])
@login_required
def processes_page():
    if request.method == "POST":
        try:
            data = json.loads(request.form.get("data", "{}"))
            if data.get("delete"):
                store.delete_process(int(data["delete"]))
                flash("پروسه حذف شد.")
            else:
                for p in data.get("processes", []):
                    store.save_process(p)
                flash("پروسه‌ها ذخیره شدند. ✅")
        except Exception:
            log.exception("process save failed")
            flash("خطا در ذخیره پروسه‌ها.")
        return redirect(url_for("processes_page"))
    return render_template(
        "processes.html",
        processes=store.get_processes(),
        people=[dict(p) for p in store.get_people()],
    )


# ---------------------------------------------------------------- requests

@app.route("/requests")
@login_required
def requests_page():
    rows = []
    for req in store.get_requests():
        proc = store.get_process(req["process_id"])
        logs = store.get_request_log(req["id"])
        rows.append({
            "req": req,
            "proc": proc,
            "summary": workflow.request_summary(req, proc),
            "status_fa": workflow.STATUS_FA.get(req["status"], req["status"]),
            "assignee": org.person_title(req["assignee"]) if req["assignee"] else "",
            "requester": org.person_title(req["requester"]),
            "logs": [
                {
                    "actor": org.person_title(l["actor"]) if l["actor"] else "سیستم",
                    "action": {"submit": "ثبت درخواست", "approve": "تأیید",
                               "reject": "رد", "execute": "اجرا"}.get(l["action"], l["action"]),
                    "comment": l["comment"],
                    "ts": l["ts"],
                }
                for l in logs
            ],
        })
    return render_template("requests.html", rows=rows)


@app.route("/broadcast", methods=["GET", "POST"])
@login_required
def broadcast():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        detail = request.form.get("detail", "").strip()
        target = request.form.get("target", "all")
        if not title:
            flash("عنوان اعلان را وارد کنید.")
            return redirect(url_for("broadcast"))

        event_id = store.create_event(title, detail)
        if target == "staff":
            targets = [p["chat_id"] for p in store.get_people() if p["chat_id"]]
        else:
            targets = [u["chat_id"] for u in store.get_users(limit=10000)]

        def _send():
            from app.bot.client import BaleClient
            from app.bot.handlers import send_event_to
            client = BaleClient()
            for cid in targets:
                try:
                    send_event_to(client, cid, event_id, title)
                except Exception:
                    log.exception("broadcast to %s failed", cid)

        threading.Thread(target=_send, daemon=True).start()
        flash(f"اعلان #{event_id} برای {len(targets)} کاربر در حال ارسال است. ✅")
        return redirect(url_for("broadcast"))
    return render_template("broadcast.html", events=store.get_events(50))


@app.route("/users")
@login_required
def users():
    return render_template("users.html", users=store.get_users())


@app.route("/messages")
@login_required
def messages():
    return render_template("messages.html", messages=store.recent_messages())


@app.route("/logs")
@login_required
def logs():
    try:
        with open(config.LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-300:]
    except FileNotFoundError:
        lines = []
    return render_template("logs.html", lines=lines)


@app.route("/update")
@login_required
def update_page():
    return render_template("update.html")


@app.route("/api/status")
@login_required
def api_status():
    p = poller.get()
    return jsonify({
        "status": p.status if p else "stopped",
        "version": __version__,
        "uptime": int(time.time() - p.started_at) if p else 0,
        "users": store.count_users(),
        "messages": store.count_messages(),
    })


@app.route("/api/update/check")
@login_required
def api_update_check():
    return jsonify(updater.check())


@app.route("/api/update/apply", methods=["POST"])
@login_required
def api_update_apply():
    ok = updater.apply_async()
    return jsonify({"started": ok})


@app.route("/api/update/progress")
@login_required
def api_update_progress():
    return jsonify({"busy": updater.state["busy"], "log": updater.state["log"]})


@app.route("/api/bot/toggle", methods=["POST"])
@login_required
def api_bot_toggle():
    enabled = not config.get("bot_enabled", True)
    config.update({"bot_enabled": enabled})
    return jsonify({"enabled": enabled})


@app.route("/api/restart", methods=["POST"])
@login_required
def api_restart():
    updater.restart_process()
    return jsonify({"restarting": True})
