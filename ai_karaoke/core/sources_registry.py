"""Every outside website used to find songs and lyrics, which are on, and in what order.

Built-in sources are listed here; the host can switch each off and reorder them within their
kind (Settings › Sources), and add their own links (core/source_links.py checks them). The
services ask ordered(kind) or enabled(id) right before each lookup, so changes apply at once.
Where an older Settings switch already exists (SoundCloud, Genius) that switch IS the toggle,
so the two places can never disagree. State lives in DATA_DIR/sources.json; a broken or
hand-edited file falls back to the defaults for whatever can't be read, never stops the app.
"""
import logging
import secrets
import threading

from config import DATA_DIR
from core import settings, sources_store
from core.source_links import check_name, check_template
from core.sources_builtin import BUILTINS, BY_ID, CUSTOM_KINDS, KINDS

log = logging.getLogger(__name__)
STATE_FILE = DATA_DIR / "sources.json"
MAX_CUSTOM = 30
_lock = threading.RLock()
_state: dict | None = None


def _data() -> dict:
    global _state
    if _state is None:
        _state = sources_store.load(STATE_FILE)
    return _state


def reload() -> None:
    global _state
    with _lock:
        _state = None


def _save() -> None:
    sources_store.save(STATE_FILE, _data())


def _find(source_id: str) -> dict | None:
    return BY_ID.get(source_id) or next((c for c in _data()["custom"] if c["id"] == source_id), None)


def enabled(source_id: str) -> bool:
    with _lock:
        entry = _find(source_id)
        if entry is None:
            return False
        return bool(settings.get(entry["setting"])) if entry.get("setting") else source_id not in _data()["off"]


def entries(kind: str) -> list[dict]:
    """Every source of a kind (on and off), in the host's order; new ones go last."""
    with _lock:
        members = [b for b in BUILTINS if b["kind"] == kind] + [c for c in _data()["custom"] if c["kind"] == kind]
        order = _data()["order"].get(kind, [])
        members.sort(key=lambda e: order.index(e["id"]) if e["id"] in order else len(order))
        return [{**e, "enabled": enabled(e["id"])} for e in members]


def ordered(kind: str) -> list[dict]:
    """The switched-on sources of a kind, best first: the order the services try them in."""
    return [e for e in entries(kind) if e["enabled"]]


def rank(source_id: str, kind: str = "songs") -> int:
    ids = [e["id"] for e in entries(kind)]
    return ids.index(source_id) if source_id in ids else len(ids)


def set_enabled(source_id: str, on: bool) -> None:
    with _lock:
        entry = _find(source_id)
        if entry is None:
            raise KeyError(source_id)
        if entry.get("setting"):
            settings.update({entry["setting"]: bool(on)})
            return
        off = [s for s in _data()["off"] if s != source_id]
        _data()["off"] = off if on else off + [source_id]
        _save()


def move(source_id: str, step: int) -> None:
    """One place up (-1) or down (+1) within its kind."""
    with _lock:
        entry = _find(source_id)
        if entry is None:
            raise KeyError(source_id)
        ids = [e["id"] for e in entries(entry["kind"])]
        i = ids.index(source_id)
        j = max(0, min(len(ids) - 1, i + step))
        ids[i], ids[j] = ids[j], ids[i]
        _data()["order"][entry["kind"]] = ids
        _save()


def save_custom(kind: str, name: str, template: str, source_id: str | None = None) -> dict:
    """Add a link, or change one (source_id). Raises ValueError with a reason for the host."""
    if kind not in CUSTOM_KINDS:
        raise ValueError("A link can be a song source or a lyrics source")
    clean = {"kind": kind, "name": check_name(name), "template": check_template(template, kind), "builtin": False}
    with _lock:
        custom = _data()["custom"]
        if source_id is None:
            if len(custom) >= MAX_CUSTOM:
                raise ValueError(f"At most {MAX_CUSTOM} links")
            entry = {"id": "c_" + secrets.token_hex(4), **clean}
            custom.append(entry)
        else:
            entry = next((c for c in custom if c["id"] == source_id), None)
            if entry is None:
                raise KeyError(source_id)
            entry.update(clean)
        _save()
        return {**entry, "enabled": enabled(entry["id"])}


def remove_custom(source_id: str) -> None:
    with _lock:
        before = len(_data()["custom"])
        _data()["custom"] = [c for c in _data()["custom"] if c["id"] != source_id]
        if len(_data()["custom"]) == before:
            raise KeyError(source_id)
        _data()["off"] = [s for s in _data()["off"] if s != source_id]
        _save()


def snapshot() -> dict:
    return {"kinds": [{"id": k, "label": label, "orderable": o, "sources": entries(k)} for k, label, o in KINDS],
            "custom_kinds": list(CUSTOM_KINDS), "max_custom": MAX_CUSTOM}
