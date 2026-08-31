"""Self-update from GitHub Releases.

The dashboard's "بروزرسانی" button uses this module:
  1. check(): compare local version with the latest GitHub release tag.
  2. apply(): download the release zip, unpack over the app folder
     (data/ lives outside and is never touched), reinstall requirements,
     then exit the process — the supervisor loop (run_bot.ps1) restarts
     the new version automatically.
"""
import io
import logging
import os
import subprocess
import sys
import threading
import time
import zipfile

import requests

from app import config
from app.version import __version__

log = logging.getLogger("updater")

state = {
    "busy": False,
    "log": [],
    "latest": None,       # info dict from last check
}


def _log(msg: str) -> None:
    log.info(msg)
    state["log"].append(msg)
    del state["log"][:-50]


def _ver_tuple(v: str):
    v = v.strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def check() -> dict:
    """Return {current, latest, has_update, notes, zip_url} or {error}."""
    repo = config.get("update_repo", "")
    if not repo:
        return {"error": "ریپوی بروزرسانی تنظیم نشده است.", "current": __version__}
    try:
        r = requests.get(
            f"https://api.github.com/repos/{repo}/releases/latest",
            timeout=20,
            headers={"Accept": "application/vnd.github+json"},
        )
        if r.status_code == 404:
            return {"error": "هنوز نسخه‌ای منتشر نشده است.", "current": __version__}
        r.raise_for_status()
        rel = r.json()
    except Exception as e:
        return {"error": f"خطا در اتصال به گیت‌هاب: {e}", "current": __version__}

    tag = rel.get("tag_name", "")
    zip_url = None
    for asset in rel.get("assets", []):
        if asset.get("name", "").endswith(".zip"):
            zip_url = asset.get("browser_download_url")
            break
    if not zip_url:
        zip_url = rel.get("zipball_url")

    info = {
        "current": __version__,
        "latest": tag,
        "has_update": _ver_tuple(tag) > _ver_tuple(__version__),
        "notes": rel.get("body", ""),
        "zip_url": zip_url,
        "name": rel.get("name", tag),
    }
    state["latest"] = info
    return info


# ------------------------------------------------------------------
# Auto-check: every 2 hours refresh state["latest"]; the dashboard shows
# a banner when an update is available and applies it after the admin
# confirms — nothing is installed without confirmation.
AUTO_CHECK_INTERVAL = 2 * 3600


def start_auto_check() -> None:
    threading.Thread(target=_auto_loop, daemon=True, name="update-check").start()


def _auto_loop() -> None:
    time.sleep(30)  # let the app settle before the first check
    while True:
        try:
            check()
        except Exception:
            log.exception("auto version check failed")
        time.sleep(AUTO_CHECK_INTERVAL)


def apply_async() -> bool:
    if state["busy"]:
        return False
    t = threading.Thread(target=_apply, daemon=True, name="updater")
    t.start()
    return True


def _apply() -> None:
    state["busy"] = True
    state["log"] = []
    try:
        info = state.get("latest") or check()
        if info.get("error") or not info.get("has_update"):
            _log("نسخه جدیدی برای نصب وجود ندارد.")
            return
        zip_url = info["zip_url"]
        _log(f"دانلود نسخه {info['latest']} ...")
        r = requests.get(zip_url, timeout=300)
        r.raise_for_status()

        _log("باز کردن بسته و جایگزینی فایل‌ها ...")
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        # GitHub zipballs nest everything under a single top folder; our
        # release assets do not. Detect a common prefix and strip it.
        prefix = ""
        top = names[0].split("/")[0] if names else ""
        if top and all(n.startswith(top + "/") for n in names):
            prefix = top + "/"

        app_dir = config.APP_DIR
        for name in names:
            rel_path = name[len(prefix):]
            if not rel_path or rel_path.endswith("/"):
                continue
            # never touch persistent data
            if rel_path.startswith("data/"):
                continue
            dest = os.path.join(app_dir, *rel_path.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(name) as src, open(dest, "wb") as out:
                out.write(src.read())
        _log("نصب وابستگی‌ها ...")
        req = os.path.join(app_dir, "requirements.txt")
        if os.path.exists(req):
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req, "-q"],
                check=False,
            )
        _log("بروزرسانی کامل شد. در حال راه‌اندازی مجدد ...")
        threading.Timer(1.5, lambda: os._exit(42)).start()
    except Exception as e:
        _log(f"خطا در بروزرسانی: {e}")
        log.exception("update failed")
    finally:
        state["busy"] = False


def restart_process() -> None:
    """Exit; the supervisor loop restarts us."""
    threading.Timer(0.7, lambda: os._exit(42)).start()
