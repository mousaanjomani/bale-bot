"""Flask web dashboard for managing the Bale bot on the customer server."""
import functools
import json
import logging
import threading
import time

from flask import (
    Flask, flash, jsonify, redirect, render_template, request, session, url_for,
)

from app import config, store, updater
from app.bot import poller
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


@app.context_processor
def inject_globals():
    latest = updater.state.get("latest") or {}
    return {
        "version": __version__,
        "update_available": latest.get("has_update") and latest.get("latest"),
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
            "welcome_text": request.form.get("welcome_text", "").strip(),
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
            data = json.loads(request.form.get("data", "{}"))
            roles = data.get("roles", [])
            menus = data.get("menus", {})
            assert isinstance(roles, list) and isinstance(menus, dict)
            config.update({"roles": roles, "menus": menus})
            flash("منوی بات ذخیره شد. ✅")
        except Exception:
            flash("خطا در ذخیره منو — ساختار نامعتبر است.")
        return redirect(url_for("menu_editor"))
    return render_template(
        "menu.html",
        roles=config.get("roles", []),
        menus=config.get("menus", {}),
    )


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
        targets = [
            u["chat_id"] for u in store.get_users(limit=10000)
            if target == "all" or (u["role"] or "") == target
        ]

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
    return render_template(
        "broadcast.html",
        roles=config.get("roles", []),
        events=store.get_events(50),
    )


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
