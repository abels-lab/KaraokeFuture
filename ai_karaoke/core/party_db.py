"""Tonight's party in a small SQLite file: guests, their login sessions and the host PIN.

Why a database at all: sessions must survive a server restart (a phone shouldn't have to log
in again because the laptop rebooted), and names must stay unique all night. Why SQLite: it
is in the standard library and one file is easy to wipe. Nothing here is precious: "Wipe
Party DB" deletes guests and sessions but keeps the host PIN (the `host` table).

Session tokens are random; only their SHA-256 is stored, so the file alone can't be used to
log in as someone. Guest ids are AUTOINCREMENT, so a guest created after a wipe never gets
the id of a deleted guest (and so never inherits their queue entries).
"""
import hashlib
import secrets
import sqlite3
import threading
import time

from config import PARTY_DB_FILE

SESSION_SECONDS = 3 * 24 * 3600   # a party login lasts three days, then log in again
_lock = threading.Lock()
_SCHEMA = """
CREATE TABLE IF NOT EXISTS guests (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE, password TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, guest_id INTEGER,
    admin INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS host (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _run(sql: str, args: tuple = (), many: bool = False) -> list[sqlite3.Row]:
    """One short transaction per call; the lock keeps threads from interleaving writes."""
    with _lock:
        db = sqlite3.connect(PARTY_DB_FILE)
        try:
            db.row_factory = sqlite3.Row
            db.executescript(_SCHEMA)
            rows = db.executescript(sql).fetchall() if many else db.execute(sql, args).fetchall()
            db.commit()
            return rows
        finally:
            db.close()


def name_key(name: str) -> str:
    """'Freddie', 'FREDDIE' and 'freddie' are one guest (also for non-English letters)."""
    return " ".join(name.casefold().split())


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ── Guests ───────────────────────────────────────────────────────────────────
def find_guest(name: str) -> sqlite3.Row | None:
    rows = _run("SELECT * FROM guests WHERE name_key = ?", (name_key(name),))
    return rows[0] if rows else None


def add_guest(name: str, password_hash: str) -> int | None:
    """The new guest's id, or None when someone just took that name."""
    try:
        _run("INSERT INTO guests (name, name_key, password, created) VALUES (?, ?, ?, ?)",
             (name, name_key(name), password_hash, time.time()))
    except sqlite3.IntegrityError:
        return None
    row = find_guest(name)
    return row["id"] if row else None


def count_guests() -> int:
    return _run("SELECT COUNT(*) AS n FROM guests")[0]["n"]


# ── Sessions ─────────────────────────────────────────────────────────────────
def new_session(guest_id: int | None, admin: bool = False) -> str:
    """Returns the token for the cookie (never stored as such)."""
    token = secrets.token_urlsafe(32)
    _run("INSERT INTO sessions (token, guest_id, admin, created) VALUES (?, ?, ?, ?)",
         (_digest(token), guest_id, int(admin), time.time()))
    return token


def session(token: str | None) -> dict | None:
    """{guest_id, admin, name} of a live session, or None (unknown, expired or wiped)."""
    if not token:
        return None
    rows = _run("SELECT s.guest_id, s.admin, s.created, g.name FROM sessions s "
                "LEFT JOIN guests g ON g.id = s.guest_id WHERE s.token = ?", (_digest(token),))
    if not rows or time.time() - rows[0]["created"] > SESSION_SECONDS:
        return None
    row = dict(rows[0])
    if row["guest_id"] is not None and row["name"] is None:   # guest gone: treat as no guest
        row["guest_id"] = None
    return {"guest_id": row["guest_id"], "admin": bool(row["admin"]), "name": row["name"]}


def update_session(token: str, **fields) -> None:
    """guest_id=… and/or admin=… on an existing session."""
    for key in ("guest_id", "admin"):
        if key in fields:
            value = int(fields[key]) if key == "admin" else fields[key]
            _run(f"UPDATE sessions SET {key} = ? WHERE token = ?", (value, _digest(token)))


def drop_session(token: str) -> None:
    _run("DELETE FROM sessions WHERE token = ?", (_digest(token),))


# ── Host PIN & wipe ──────────────────────────────────────────────────────────
def pin_hash() -> str | None:
    rows = _run("SELECT value FROM host WHERE key = 'pin'")
    return rows[0]["value"] if rows else None


def set_pin_hash(value: str) -> None:
    """A new PIN also ends every PIN-unlocked host session: old PIN holders are out."""
    _run("INSERT OR REPLACE INTO host (key, value) VALUES ('pin', ?)", (value,))
    _run("UPDATE sessions SET admin = 0")


def wipe() -> None:
    """Forget every guest and session; the host PIN stays."""
    _run("DELETE FROM sessions; DELETE FROM guests;", many=True)
