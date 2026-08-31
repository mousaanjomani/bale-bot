"""Configuration handling.

Config and runtime data live OUTSIDE the app folder so that upgrades
(which replace the app folder) never touch them.

Layout on the customer server:
    C:\\BaleBot\\app\\   -> application code (replaced on upgrade)
    C:\\BaleBot\\data\\  -> config.json, bot.db, logs (persistent)

During development the data dir falls back to <repo>/data.
"""
import json
import os
import secrets
import threading

_lock = threading.Lock()

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# If the app is installed under ...\app, data lives in the sibling "data" dir.
_parent = os.path.dirname(APP_DIR)
if os.path.basename(APP_DIR).lower() == "app" and os.path.isdir(_parent):
    DATA_DIR = os.path.join(_parent, "data")
else:
    DATA_DIR = os.path.join(APP_DIR, "data")

os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
DB_PATH = os.path.join(DATA_DIR, "bot.db")
LOG_PATH = os.path.join(DATA_DIR, "bot.log")

DEFAULTS = {
    "bot_token": "",
    "api_base": "https://tapi.bale.ai",
    "web_port": 8585,
    "web_host": "0.0.0.0",
    "admin_user": "admin",
    "admin_password": "admin",
    "secret_key": "",
    # GitHub repo used by the in-dashboard upgrade button ("owner/repo")
    "update_repo": "",
    "welcome_text": "سلام! به بات ما خوش آمدید 🌟",
    "bot_enabled": True,
}


def _load() -> dict:
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    if not cfg.get("secret_key"):
        cfg["secret_key"] = secrets.token_hex(32)
        _save(cfg)
    return cfg


def _save(cfg: dict) -> None:
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


_config = _load()


def get(key, default=None):
    with _lock:
        return _config.get(key, default)


def all_config() -> dict:
    with _lock:
        return dict(_config)


def update(values: dict) -> None:
    with _lock:
        _config.update(values)
        _save(_config)
