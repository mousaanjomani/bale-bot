"""Flask web dashboard for managing the Bale bot on the customer server."""
import functools
import logging
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
    return {"version": __version__}


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
            "welcome_text": request.form.get("welcome_text", "").strip(),
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
