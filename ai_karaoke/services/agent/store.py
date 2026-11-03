"""What the DJ Co-Pilot keeps on disk: the Control Panel layout it customised (ui_config.json,
pushed live as WS "ui_config" to static/tv-ui.js) and its improvement backlog (what it couldn't
do, tool errors), both in the data folder."""
import json
import logging
import time
from typing import Any

from config import DATA_DIR

log = logging.getLogger(__name__)

IMPROVEMENTS_FILE = DATA_DIR / "agent_improvements.jsonl"
UI_CONFIG_FILE = DATA_DIR / "ui_config.json"

DEFAULT_UI_CONFIG: dict[str, Any] = {
    "column_order": ["left", "center", "right"],
    "hidden_elements": [],
    "custom_buttons": [],
    "guide_width": "25%",
    "guide_thumb": "default",
}


def get_ui_config() -> dict[str, Any]:
    """The saved Control Panel layout, merged with the defaults. Fields the layout no longer has
    (custom_css moved to the custom_css setting, checked by core/css_guard.py) are dropped."""
    merged = dict(DEFAULT_UI_CONFIG)
    if UI_CONFIG_FILE.is_file():
        try:
            data = json.loads(UI_CONFIG_FILE.read_text(encoding="utf-8"))
            merged.update({k: v for k, v in data.items() if k in DEFAULT_UI_CONFIG})
        except Exception as e:
            log.warning("Failed to load ui_config: %s", e)
    return merged


def save_ui_config(cfg: dict[str, Any]) -> dict[str, Any]:
    try:
        UI_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        UI_CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.warning("Failed to save ui_config: %s", e)
    return cfg


def record_improvement(category: str, summary: str, details: dict[str, Any] | None = None,
                       prompt: str = "") -> dict[str, Any]:
    """Log a capability gap, tool error or feature request for later."""
    entry = {
        "timestamp": time.time(),
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "category": category,
        "summary": summary,
        "prompt": prompt,
        "details": details or {},
    }
    try:
        IMPROVEMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(IMPROVEMENTS_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        log.info("Recorded agent improvement [%s]: %s", category, summary)
    except Exception as e:
        log.warning("Failed to record agent improvement: %s", e)
    return entry


def list_improvements(limit: int = 50) -> list[dict[str, Any]]:
    if not IMPROVEMENTS_FILE.is_file():
        return []
    try:
        lines = IMPROVEMENTS_FILE.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in lines if line.strip()][-limit:]
    except Exception:
        return []
