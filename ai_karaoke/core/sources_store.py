"""Reading and writing DATA_DIR/sources.json for core/sources_registry.py.

{"off": [source ids switched off], "order": {kind: [source ids]}, "custom": [{id, kind, name,
template}]}. Anything that can't be read (broken JSON, an entry that fails today's link rules)
is logged and skipped, so a hand-edited file can never stop the app. Writes are atomic.
"""
import json
import logging
import os
from pathlib import Path

from core.source_links import check_name, check_template
from core.sources_builtin import CUSTOM_KINDS

log = logging.getLogger(__name__)


def empty() -> dict:
    return {"off": [], "order": {}, "custom": []}


def _custom(item) -> dict:
    if not isinstance(item, dict) or item.get("kind") not in CUSTOM_KINDS:
        raise ValueError("not a song or lyrics link")
    sid = str(item.get("id") or "")
    if not sid.startswith("c_") or len(sid) > 20:
        raise ValueError("bad id")
    return {"id": sid, "kind": item["kind"], "name": check_name(item.get("name")),
            "template": check_template(item.get("template"), item["kind"]), "builtin": False}


def load(path: Path) -> dict:
    state = empty()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return state
    except (OSError, ValueError) as exc:
        log.warning("%s is unreadable (%s): using the default sources", path.name, exc)
        return state
    raw = raw if isinstance(raw, dict) else {}
    state["off"] = [s for s in raw.get("off") or [] if isinstance(s, str)]
    order = raw.get("order") if isinstance(raw.get("order"), dict) else {}
    state["order"] = {k: [s for s in v if isinstance(s, str)] for k, v in order.items() if isinstance(v, list)}
    for item in raw.get("custom") or []:
        try:
            state["custom"].append(_custom(item))
        except (TypeError, ValueError) as exc:
            log.warning("Ignoring source link %r: %s", item, exc)
    return state


def save(path: Path, state: dict) -> None:
    data = {"off": state["off"], "order": state["order"],
            "custom": [{k: c[k] for k in ("id", "kind", "name", "template")} for c in state["custom"]]}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
