"""SQLite storage for users, messages and key/value state."""
import sqlite3
import threading
import time

from app import config

_local = threading.local()


def _conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(config.DB_PATH)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
    return _local.conn


def init_db() -> None:
    c = _conn()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            chat_id     INTEGER PRIMARY KEY,
            first_name  TEXT,
            last_name   TEXT,
            username    TEXT,
            first_seen  INTEGER,
            last_seen   INTEGER,
            msg_count   INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id   INTEGER,
            direction TEXT,          -- 'in' or 'out'
            text      TEXT,
            ts        INTEGER
        );
        CREATE TABLE IF NOT EXISTS kv (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    c.commit()


def upsert_user(chat_id: int, first_name: str, last_name: str, username: str) -> None:
    now = int(time.time())
    c = _conn()
    c.execute(
        """
        INSERT INTO users (chat_id, first_name, last_name, username, first_seen, last_seen, msg_count)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(chat_id) DO UPDATE SET
            first_name=excluded.first_name,
            last_name=excluded.last_name,
            username=excluded.username,
            last_seen=excluded.last_seen,
            msg_count=msg_count+1
        """,
        (chat_id, first_name, last_name, username, now, now),
    )
    c.commit()


def log_message(chat_id: int, direction: str, text: str) -> None:
    c = _conn()
    c.execute(
        "INSERT INTO messages (chat_id, direction, text, ts) VALUES (?, ?, ?, ?)",
        (chat_id, direction, (text or "")[:2000], int(time.time())),
    )
    c.commit()


def get_users(limit: int = 200):
    return _conn().execute(
        "SELECT * FROM users ORDER BY last_seen DESC LIMIT ?", (limit,)
    ).fetchall()


def count_users() -> int:
    return _conn().execute("SELECT COUNT(*) FROM users").fetchone()[0]


def count_messages() -> int:
    return _conn().execute("SELECT COUNT(*) FROM messages").fetchone()[0]


def recent_messages(limit: int = 100):
    return _conn().execute(
        "SELECT m.*, u.first_name, u.username FROM messages m "
        "LEFT JOIN users u ON u.chat_id = m.chat_id "
        "ORDER BY m.id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def kv_get(key: str, default=None):
    row = _conn().execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def kv_set(key: str, value: str) -> None:
    c = _conn()
    c.execute(
        "INSERT INTO kv (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    c.commit()
