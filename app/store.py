"""SQLite storage for users, messages, org chart, processes and requests."""
import json
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
        CREATE TABLE IF NOT EXISTS events (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            title    TEXT,
            detail   TEXT,
            created  INTEGER,
            acked_by INTEGER,
            acked_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS units (
            id     TEXT PRIMARY KEY,
            name   TEXT,
            parent TEXT,
            sup    TEXT,          -- supervisor person id
            dep    TEXT           -- deputy person id
        );
        CREATE TABLE IF NOT EXISTS people (
            id      TEXT PRIMARY KEY,
            name    TEXT,
            code    TEXT,         -- personnel code, used to link the Bale account
            unit    TEXT,
            chat_id INTEGER       -- linked Bale chat id (NULL = not linked)
        );
        CREATE TABLE IF NOT EXISTS processes (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            name   TEXT,
            button TEXT,          -- bot button label
            active INTEGER DEFAULT 1,
            form   TEXT,          -- json: [{key,label,type}]
            steps  TEXT           -- json: [{title, assignee:{type,person}, execute, options}]
        );
        CREATE TABLE IF NOT EXISTS requests (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            process_id INTEGER,
            requester  TEXT,      -- person id
            data       TEXT,      -- json form values
            status     TEXT,      -- pending | done | rejected
            step       INTEGER,   -- current step index
            assignee   TEXT,      -- person id responsible for current step
            result     TEXT,      -- e.g. payment method chosen by executor
            created    INTEGER,
            closed     INTEGER
        );
        CREATE TABLE IF NOT EXISTS request_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            step_idx   INTEGER,
            actor      TEXT,      -- person id
            action     TEXT,      -- submit | approve | reject | execute
            comment    TEXT,
            ts         INTEGER
        );
        CREATE TABLE IF NOT EXISTS chat_states (
            chat_id INTEGER PRIMARY KEY,
            state   TEXT
        );
        """
    )
    try:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
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


def set_user_role(chat_id: int, role: str) -> None:
    c = _conn()
    c.execute("UPDATE users SET role=? WHERE chat_id=?", (role, chat_id))
    c.commit()


def get_user_role(chat_id: int):
    row = _conn().execute(
        "SELECT role FROM users WHERE chat_id=?", (chat_id,)
    ).fetchone()
    return row["role"] if row else None


def create_event(title: str, detail: str) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO events (title, detail, created) VALUES (?, ?, ?)",
        (title, detail, int(time.time())),
    )
    c.commit()
    return cur.lastrowid


def get_event(event_id) -> "sqlite3.Row | None":
    try:
        eid = int(event_id)
    except (TypeError, ValueError):
        return None
    return _conn().execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()


def ack_event(event_id, chat_id: int) -> None:
    c = _conn()
    c.execute(
        "UPDATE events SET acked_by=?, acked_at=? WHERE id=?",
        (chat_id, int(time.time()), int(event_id)),
    )
    c.commit()


def get_events(limit: int = 100):
    return _conn().execute(
        "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()


# ---------------------------------------------------------------- org chart

def get_units():
    return _conn().execute("SELECT * FROM units ORDER BY rowid").fetchall()


def get_people():
    return _conn().execute("SELECT * FROM people ORDER BY rowid").fetchall()


def get_unit(unit_id):
    return _conn().execute("SELECT * FROM units WHERE id=?", (unit_id,)).fetchone()


def get_person(person_id):
    return _conn().execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()


def person_by_chat(chat_id: int):
    return _conn().execute(
        "SELECT * FROM people WHERE chat_id=?", (chat_id,)
    ).fetchone()


def person_by_code(code: str):
    return _conn().execute(
        "SELECT * FROM people WHERE code=? AND code != ''", (code.strip(),)
    ).fetchone()


def link_person_chat(person_id: str, chat_id) -> None:
    c = _conn()
    if chat_id:
        c.execute("UPDATE people SET chat_id=NULL WHERE chat_id=?", (chat_id,))
    c.execute("UPDATE people SET chat_id=? WHERE id=?", (chat_id, person_id))
    c.commit()


def replace_org(units: list, people: list) -> None:
    """Replace the whole org chart (dashboard editor saves everything at once).
    Keeps existing chat links for people whose id is unchanged."""
    c = _conn()
    old_links = {r["id"]: r["chat_id"] for r in get_people() if r["chat_id"]}
    c.execute("DELETE FROM units")
    c.execute("DELETE FROM people")
    for u in units:
        c.execute(
            "INSERT INTO units (id, name, parent, sup, dep) VALUES (?, ?, ?, ?, ?)",
            (u["id"], u.get("name", ""), u.get("parent"), u.get("sup"), u.get("dep")),
        )
    for p in people:
        c.execute(
            "INSERT INTO people (id, name, code, unit, chat_id) VALUES (?, ?, ?, ?, ?)",
            (p["id"], p.get("name", ""), str(p.get("code", "")).strip(),
             p.get("unit"), p.get("chat_id") or old_links.get(p["id"])),
        )
    c.commit()


# ---------------------------------------------------------------- processes

def get_processes(active_only: bool = False):
    q = "SELECT * FROM processes"
    if active_only:
        q += " WHERE active=1"
    rows = _conn().execute(q + " ORDER BY id").fetchall()
    return [_proc_dict(r) for r in rows]


def get_process(process_id):
    r = _conn().execute(
        "SELECT * FROM processes WHERE id=?", (process_id,)
    ).fetchone()
    return _proc_dict(r) if r else None


def _proc_dict(r) -> dict:
    return {
        "id": r["id"], "name": r["name"], "button": r["button"],
        "active": bool(r["active"]),
        "form": json.loads(r["form"] or "[]"),
        "steps": json.loads(r["steps"] or "[]"),
    }


def save_process(p: dict):
    c = _conn()
    form = json.dumps(p.get("form", []), ensure_ascii=False)
    steps = json.dumps(p.get("steps", []), ensure_ascii=False)
    if p.get("id"):
        c.execute(
            "UPDATE processes SET name=?, button=?, active=?, form=?, steps=? WHERE id=?",
            (p["name"], p["button"], 1 if p.get("active", True) else 0, form, steps, p["id"]),
        )
        pid = p["id"]
    else:
        cur = c.execute(
            "INSERT INTO processes (name, button, active, form, steps) VALUES (?, ?, ?, ?, ?)",
            (p["name"], p["button"], 1 if p.get("active", True) else 0, form, steps),
        )
        pid = cur.lastrowid
    c.commit()
    return pid


def delete_process(process_id) -> None:
    c = _conn()
    c.execute("DELETE FROM processes WHERE id=?", (process_id,))
    c.commit()


# ---------------------------------------------------------------- requests

def create_request(process_id: int, requester: str, data: dict) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO requests (process_id, requester, data, status, step, created) "
        "VALUES (?, ?, ?, 'pending', 0, ?)",
        (process_id, requester, json.dumps(data, ensure_ascii=False), int(time.time())),
    )
    c.commit()
    return cur.lastrowid


def get_request(request_id):
    return _conn().execute(
        "SELECT * FROM requests WHERE id=?", (request_id,)
    ).fetchone()


def update_request(request_id: int, **fields) -> None:
    keys = ", ".join(f"{k}=?" for k in fields)
    c = _conn()
    c.execute(f"UPDATE requests SET {keys} WHERE id=?",
              (*fields.values(), request_id))
    c.commit()


def get_requests(limit: int = 300):
    return _conn().execute(
        "SELECT * FROM requests ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()


def cartable(person_id: str):
    return _conn().execute(
        "SELECT * FROM requests WHERE status='pending' AND assignee=? ORDER BY id",
        (person_id,),
    ).fetchall()


def my_requests(person_id: str, limit: int = 20):
    return _conn().execute(
        "SELECT * FROM requests WHERE requester=? ORDER BY id DESC LIMIT ?",
        (person_id, limit),
    ).fetchall()


def add_request_log(request_id: int, step_idx: int, actor: str,
                    action: str, comment: str = "") -> None:
    c = _conn()
    c.execute(
        "INSERT INTO request_log (request_id, step_idx, actor, action, comment, ts) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (request_id, step_idx, actor, action, comment, int(time.time())),
    )
    c.commit()


def get_request_log(request_id: int):
    return _conn().execute(
        "SELECT * FROM request_log WHERE request_id=? ORDER BY id", (request_id,)
    ).fetchall()


# ---------------------------------------------------------------- chat state

def get_chat_state(chat_id: int) -> dict | None:
    r = _conn().execute(
        "SELECT state FROM chat_states WHERE chat_id=?", (chat_id,)
    ).fetchone()
    return json.loads(r["state"]) if r else None


def set_chat_state(chat_id: int, state: dict | None) -> None:
    c = _conn()
    if state is None:
        c.execute("DELETE FROM chat_states WHERE chat_id=?", (chat_id,))
    else:
        c.execute(
            "INSERT INTO chat_states (chat_id, state) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET state=excluded.state",
            (chat_id, json.dumps(state, ensure_ascii=False)),
        )
    c.commit()


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
