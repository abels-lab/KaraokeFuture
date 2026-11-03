"""Host-only DJ Co-Pilot tools (services/agent/registry.py refuses them for guests): Control Panel
layout, settings and playlists. Settings that would point the Co-Pilot somewhere else (provider,
key, model, endpoint) or open it to guests stay on the Settings page: a chat message can't change them."""
import re
from typing import Any

from core import auth, settings
from core.hub import hub
from core.playlist_manager import playlist_manager
from core.queue_manager import queue
from services.agent import store

LOCKED = {"agent_provider", "agent_api_key", "agent_model", "agent_base_url", "agent_guest_chat",
          "agent_guest_style"}
_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")
_WIDTH = re.compile(r"\d{1,3}(\.\d+)?(%|rem|px)")
BUTTON_ACTIONS = {"sfx", "control", "setting", "queue_search", "toast"}


def _clean_button(btn: Any) -> dict | str:
    """A custom button with only known fields and safe values, or why not."""
    if not isinstance(btn, dict) or not _ID.fullmatch(str(btn.get("id", ""))):
        return "A button needs an id (letters, digits, - or _)"
    if btn.get("action") not in BUTTON_ACTIONS:
        return f"Button action must be one of {', '.join(sorted(BUTTON_ACTIONS))}"
    return {"id": btn["id"], "label": str(btn.get("label") or btn["id"])[:30], "icon": str(btn.get("icon") or "")[:4],
            "target": btn.get("target") if btn.get("target") in ("display", "nav", "transport") else "display",
            "action": btn["action"], "value": str(btn.get("value") or "")[:120]}


async def customize_control_panel(who: auth.Who, args: dict) -> dict[str, Any]:
    action = str(args.get("action") or "update").strip().lower()
    cfg = store.get_ui_config()
    if action == "reset":
        cfg = dict(store.DEFAULT_UI_CONFIG)
    elif action == "add_button":
        btn = _clean_button(args.get("button"))
        if isinstance(btn, str):
            return {"error": btn}
        cfg["custom_buttons"] = [b for b in cfg["custom_buttons"] if b.get("id") != btn["id"]] + [btn]
    elif action == "remove_button":
        if not args.get("button_id"):
            return {"error": "Missing button_id to remove"}
        cfg["custom_buttons"] = [b for b in cfg["custom_buttons"] if b.get("id") != args["button_id"]]
    order = args.get("column_order")
    if isinstance(order, list) and sorted(order) == ["center", "left", "right"]:
        cfg["column_order"] = order
    if isinstance(args.get("hide_elements"), list):
        ids = [i for i in args["hide_elements"] if _ID.fullmatch(str(i))]
        cfg["hidden_elements"] = list(dict.fromkeys([*cfg["hidden_elements"], *ids]))
    if isinstance(args.get("show_elements"), list):
        cfg["hidden_elements"] = [i for i in cfg["hidden_elements"] if i not in set(args["show_elements"])]
    if args.get("guide_width") and _WIDTH.fullmatch(str(args["guide_width"]).strip()):
        cfg["guide_width"] = str(args["guide_width"]).strip()
    if args.get("guide_thumb"):   # "default", "smiley" or one emoji (a few code points)
        thumb = str(args["guide_thumb"]).strip()
        cfg["guide_thumb"] = thumb if thumb in ("default", "smiley") else thumb[:4] or "default"
    store.save_ui_config(cfg)
    await hub.broadcast({"type": "ui_config", "config": cfg})
    return {"status": "ok", "action": action, "config": cfg}


def _as_value(raw: Any) -> Any:
    if isinstance(raw, (bool, int, float)):
        return raw
    text = str(raw)
    if text.lower() in ("true", "yes", "on"):
        return True
    if text.lower() in ("false", "no", "off"):
        return False
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return text


async def change_setting(who: auth.Who, args: dict) -> dict[str, Any]:
    key = str(args.get("key") or "")
    if not key:
        return {"error": "Missing key"}
    if key in LOCKED:
        return {"error": f"'{key}' can only be changed on the Settings page, not from the chat"}
    value = _as_value(args.get("value"))
    try:
        settings.update({key: value})
    except ValueError as exc:
        return {"error": str(exc)}
    await hub.broadcast({"type": "settings"})
    return {"status": "ok", "key": key, "value": value}


async def playlist_tool(name: str, args: dict) -> dict[str, Any]:
    pid = args.get("playlist_id")
    try:
        if name == "create_playlist":
            if not args.get("name"):
                return {"error": "Missing playlist name"}
            return {"status": "ok", "playlist": playlist_manager.create_playlist(
                args["name"], args.get("songs") or [], description=args.get("description", ""), playlist_id=pid)}
        if name == "stop_playlist":
            return {"status": "ok" if await queue.stop_playlist() else "no_active_playlist"}
        if not pid:
            return {"error": "Missing playlist_id"}
        if name == "update_playlist":
            return {"status": "ok", "playlist": playlist_manager.update_playlist(
                playlist_id=pid, name=args.get("name"), description=args.get("description"),
                songs=args.get("songs"), action=args.get("action", "set"))}
        if name == "delete_playlist":
            ok = playlist_manager.delete_playlist(pid)
            return {"status": "ok", "deleted": pid} if ok else {"error": f"Playlist '{pid}' not found"}
        res = await queue.start_playlist(pid, shuffle=bool(args.get("shuffle")), loop=bool(args.get("loop")))
        return {"status": "ok", "active_playlist": res}
    except Exception as e:
        return {"error": str(e)}
