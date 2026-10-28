"""AI Co-Pilot / Host Assistant: executes party commands, settings, song searches, and code changes."""
import difflib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from config import BASE_DIR, DATA_DIR, MELODY_FILE
from core import cache_manager, settings
from core.worker import worker
from core.hub import hub
from core.queue_manager import queue
import asyncio
from services import search as smart_search
from services import sources
from services import lyrics_source, ultrastar_source

log = logging.getLogger(__name__)

# Pending backend diffs awaiting host confirmation
PENDING_PROPOSALS: dict[str, dict] = {}

IMPROVEMENTS_FILE = DATA_DIR / "agent_improvements.jsonl"
UI_CONFIG_FILE = DATA_DIR / "ui_config.json"

DEFAULT_UI_CONFIG: dict[str, Any] = {
    "column_order": ["left", "center", "right"],
    "hidden_elements": [],
    "custom_buttons": [],
    "guide_width": "25%",
    "guide_thumb": "default",
    "custom_css": "",
}


def get_ui_config() -> dict[str, Any]:
    """Return the persisted Control Panel UI customization config, merged with defaults."""
    if UI_CONFIG_FILE.is_file():
        try:
            data = json.loads(UI_CONFIG_FILE.read_text(encoding="utf-8"))
            merged = dict(DEFAULT_UI_CONFIG)
            merged.update(data)
            return merged
        except Exception as e:
            log.warning("Failed to load ui_config: %s", e)
    return dict(DEFAULT_UI_CONFIG)


def save_ui_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Persist the Control Panel UI customization config."""
    try:
        UI_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        UI_CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.warning("Failed to save ui_config: %s", e)
    return cfg



def record_improvement(
    category: str,
    summary: str,
    details: dict[str, Any] | None = None,
    prompt: str = "",
) -> dict[str, Any]:
    """Log an agent capability gap, tool error, or feature request for future improvements."""
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
    """Return recent agent improvement records."""
    if not IMPROVEMENTS_FILE.is_file():
        return []
    try:
        lines = IMPROVEMENTS_FILE.read_text(encoding="utf-8").strip().splitlines()
        entries = [json.loads(line) for line in lines if line.strip()]
        return entries[-limit:]
    except Exception:
        return []

SYSTEM_PROMPT = """You are the AI Karaoke Host & DJ Co-Pilot for AI Karaoke.
You assist the host with running the party:
1. Finding and enqueuing songs for singers (use search_and_queue). To inspect what tracks are already downloaded/cached in the local library, use get_library_songs. NEVER use read_code_file to search for songs, look for files, or check library status.
2. Control Panel Layout & Customization:
   - ALWAYS prefer the customize_control_panel tool (executes in 1 tool call!) when the host asks to:
     * Change the Control Panel layout, reorder columns (e.g. column_order=["right", "center", "left"])
     * Hide or show panels or buttons (e.g. hide_elements=["qr-card", "nav-panel", "btn-restart"])
     * Add or remove custom buttons (SFX buttons like airhorn/applause/cheer/laser, settings toggles, transport buttons, or quick song buttons)
     * Resize the Guide Vocal slider (e.g. guide_width="25%", "50%", "100%") or change its thumb (e.g. guide_thumb="smiley" or "😊" or "🎤")
     * Apply live CSS tweaks (custom_css="...") without reloading or modifying disk files.
   - When asked to move or dock the chat panel / DJ drawer to the left or right, call change_setting(key="agent_drawer_position", value="left"|"right").
3. Changing app settings (themes, accents, durations, volume, guest permissions) via change_setting.
4. Queue management (skipping songs, moving, removing) via queue_action.
5. Live frontend code editing (static/*.css, static/*.js, static/*.html): modify permanent styles or templates directly via edit_frontend_file (supports full content OR old_snippet and new_snippet for quick surgical edits).
6. Server backend code modifications (core/*.py, routers/*.py, services/*.py): propose changes via propose_backend_diff so the host can review the diff.
7. Recording feature requests & capability gaps: call record_improvement_request when the host asks for something you lack tools for or that cannot safely be performed live.
8. Inspecting & editing song lyrics: use get_song_lyrics to inspect current lyrics, and edit_song_lyrics to fix typos, replace words/lines (using old_snippet and new_snippet), provide full lyrics, or reset to original lyrics (using reset=True). If song_id or query is omitted, it automatically targets the now-playing song (or next in queue).

Frontend File & DOM ID Reference Map (NEVER guess static/index.html - it does NOT exist!):
- static/tv.html: Host Control Panel (/tv). Key DOM IDs:
  * #tv-layout: 3-column workstation grid
  * Left Column (#col-left): #qr-card (QR code box), #agent-drawer (DJ Co-Pilot chat)
  * Center Column (#col-center): #preview-card (#idle mic & qr, #stage video & monitor lyrics), #display-panel (#btn-video, #btn-lyrics, #open-screen, #open-mics, #custom-controls), #nav-panel (#custom-nav-controls)
  * Right Column (#col-right): #now-playing-card (#np-singer, #np-title, #seek, #transport-bar [#btn-prev, #btn-restart, #btn-back, #btn-play, #btn-fwd, #btn-next, #custom-transport-controls], #guide-control [#guide, #guide-value]), #tv-sidebar (#side-lists, queue tabs)
- static/screen.html: Projector Screen (/screen).
- static/remote.html: Guest Phone Remote (/remote).
- static/settings.html: Settings Page (/settings).
- static/theme.css: Global styles, layout grid rules, themes (adaptive, rock, club).

Guidelines:
- Keep verbal responses concise, witty, charismatic, and party-ready.
- When the host asks to customize buttons, layout, or guide vocal slider width/thumb, IMMEDIATELY call customize_control_panel. Do NOT waste turns reading static/tv.html or inventing non-existent files.
- For lyric requests ("fix lyrics", "change the words in this song", "show me the lyrics"): use get_song_lyrics to inspect existing lines, and edit_song_lyrics with old_snippet and new_snippet for fast surgical word/phrase corrections without rewriting the whole song. To revert to original lyrics, call edit_song_lyrics(reset=True).
- For finding songs to queue: use your vast musical knowledge to pick great songs, and use search_and_queue. If the host asks about songs that are already cached or NOT already local/cached, use get_library_songs.
- NEVER call read_code_file for general questions, music requests, or checking cached songs. Only use read_code_file when the host explicitly asks to modify frontend CSS/HTML styles or inspect frontend code.
- If the host asks for an action or feature you lack tools for:
  1. DO NOT invent file names or blindly call read_code_file/edit_frontend_file in a loop.
  2. Call record_improvement_request(topic=..., description=..., safe_alternative=...) so the request is saved in the developer improvement backlog.
  3. Respond warmly and playfully as a friendly party DJ.
- If any tool returns an error, do NOT retry the exact same failing tool or guess random file names.
- For Python code, always use propose_backend_diff. Never attempt to edit backend files directly.
"""

# ── Tool Definitions ──────────────────────────────────────────────────────────

TOOLS_SCHEMA = [
    {
        "name": "customize_control_panel",
        "description": "Customize the Control Panel layout, reorder columns, hide/show panels, add/remove custom buttons (SFX, settings, transport, songs), resize the Guide Vocal slider (e.g. guide_width='25%'), change slider thumb ('smiley'), or apply live custom CSS. Executes live in 1 tool call without page reload.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action type: 'update' (default), 'add_button', 'remove_button', or 'reset'",
                },
                "column_order": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Order of the 3 columns: list of 'left', 'center', 'right' (e.g. ['right', 'center', 'left'])",
                },
                "hide_elements": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "List of panel or button DOM IDs to hide (e.g. ['qr-card', 'nav-panel', 'display-panel', 'btn-restart'])",
                },
                "show_elements": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "List of panel or button DOM IDs to show/unhide",
                },
                "guide_width": {
                    "type": "STRING",
                    "description": "Width of the Guide Vocal slider, e.g. '25%', '50%', '100%'",
                },
                "guide_thumb": {
                    "type": "STRING",
                    "description": "Thumb style for Guide Vocal slider, e.g. 'smiley', '😊', '🎤', 'default'",
                },
                "button": {
                    "type": "OBJECT",
                    "description": "Custom button definition when action is 'add_button'. Fields: id (str), label (str), action ('sfx'|'control'|'setting'|'queue_search'|'toast'), value (str), target ('display'|'nav'|'transport', default 'display')",
                    "properties": {
                        "id": {"type": "STRING"},
                        "label": {"type": "STRING"},
                        "icon": {"type": "STRING"},
                        "target": {"type": "STRING"},
                        "action": {"type": "STRING"},
                        "value": {"type": "STRING"},
                        "style": {"type": "STRING"},
                    },
                    "required": ["id", "label", "action"],
                },
                "button_id": {
                    "type": "STRING",
                    "description": "ID of button to remove when action is 'remove_button'",
                },
                "custom_css": {
                    "type": "STRING",
                    "description": "Live custom CSS to inject into the page head",
                },
            },
            "required": [],
        },
    },
    {
        "name": "record_improvement_request",
        "description": "Log a capability gap, missing tool, or host feature request into the development wishlist when you lack tools or cannot safely perform an action live (e.g. creating custom playlists, moving permanent structural HTML elements, deleting files, shell commands).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "topic": {"type": "STRING", "description": "Short title of the feature or missing tool (e.g. 'custom_playlists', 'reorder_permanent_ui')"},
                "description": {"type": "STRING", "description": "Details of what the host requested"},
                "safe_alternative": {"type": "STRING", "description": "Closest safe workaround or alternative suggested to the host"},
            },
            "required": ["topic", "description"],
        },
    },
    {
        "name": "get_party_status",
        "description": "Get current now playing song, queued songs, active theme, and party settings.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_library_songs",
        "description": "List songs already cached / saved in the local karaoke library. Use this to check if a song is already local or to see what is downloaded.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "limit": {"type": "INTEGER", "description": "Max songs to return (default 30)"},
                "search": {"type": "STRING", "description": "Optional search filter for title or artist"},
            },
            "required": [],
        },
    },
    {
        "name": "change_setting",
        "description": "Change an application setting (e.g. agent_drawer_position to 'left' or 'right' to move this chat panel, theme to 'adaptive', accent to 'lime', show_video to true/false, guest_scrubbing, cache_limit_gb).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "key": {"type": "STRING", "description": "Setting key name"},
                "value": {"type": "STRING", "description": "New value (as string, bool, or number)"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "search_and_queue",
        "description": "Search YouTube / sources for a track and add it to the queue for a singer.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Song search query (e.g. 'Queen Bohemian Rhapsody')"},
                "singer": {"type": "STRING", "description": "Name of the singer (e.g. 'Host', 'Alice', 'Everyone')"},
                "mode": {"type": "STRING", "description": "Optional singing game mode: 'party', 'score', or 'battle'"},
            },
            "required": ["query", "singer"],
        },
    },
    {
        "name": "queue_action",
        "description": "Perform an action on the playback or queue: skip, play, pause, restart, remove, move.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "'skip', 'play', 'pause', 'restart', 'remove', or 'move'"},
                "uid": {"type": "STRING", "description": "Queue entry UID if applicable"},
                "offset": {"type": "INTEGER", "description": "Offset to move if action is 'move' (e.g. -1 for up, 1 for down)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "read_code_file",
        "description": "Read the contents of a project file (e.g. static/theme.css, static/look.js). Only use when modifying frontend UI styles or inspecting code. NEVER use to search for songs or check local media files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative file path from project root"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "edit_frontend_file",
        "description": "Directly edit a frontend file in static/ (e.g. static/theme.css, static/remote.html). Provide either full 'content' OR 'old_snippet' and 'new_snippet' for quick surgical edits. Automatically backs up and hot-reloads.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path in static/ (e.g. static/theme.css)"},
                "content": {"type": "STRING", "description": "New full content of the file (optional if using snippets)"},
                "old_snippet": {"type": "STRING", "description": "Exact text snippet to replace in the file (optional if using content)"},
                "new_snippet": {"type": "STRING", "description": "Replacement text snippet (optional if using content)"},
                "summary": {"type": "STRING", "description": "Short description of the modification"},
            },
            "required": ["path", "summary"],
        },
    },
    {
        "name": "propose_backend_diff",
        "description": "Propose a backend Python change in core/, routers/, or services/. Shows an interactive diff in chat for host confirmation before applying.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to Python file (e.g. core/worker.py)"},
                "old_snippet": {"type": "STRING", "description": "Exact text snippet to replace"},
                "new_snippet": {"type": "STRING", "description": "Replacement text snippet"},
                "summary": {"type": "STRING", "description": "Brief explanation of what this backend change does"},
            },
            "required": ["path", "old_snippet", "new_snippet", "summary"],
        },
    },
    {
        "name": "undo_frontend_edit",
        "description": "Revert the last frontend edit by restoring the .bak backup.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path in static/ to revert"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_song_lyrics",
        "description": "Get current lyrics text for a song. Defaults to the now-playing song or top queued song if song_id/query is omitted.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "song_id": {"type": "STRING", "description": "Specific song ID in cache (optional)"},
                "query": {"type": "STRING", "description": "Song title or artist to search in queue or library (optional)"},
            },
            "required": [],
        },
    },
    {
        "name": "edit_song_lyrics",
        "description": "Edit or fix lyrics for a song (supports surgical text replacement via old_snippet/new_snippet, full replacement via text, or resetting to automatic via reset=True). Defaults to now-playing song if song_id/query is omitted.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "song_id": {"type": "STRING", "description": "Specific song ID in cache (optional)"},
                "query": {"type": "STRING", "description": "Song title or artist to locate in queue or library (optional)"},
                "old_snippet": {"type": "STRING", "description": "Exact text or line in the lyrics to replace"},
                "new_snippet": {"type": "STRING", "description": "Replacement text or line"},
                "text": {"type": "STRING", "description": "Full new lyric text (optional if using old_snippet/new_snippet)"},
                "reset": {"type": "BOOLEAN", "description": "Set to true to discard custom lyrics and reset to automatic online detection"},
            },
            "required": [],
        },
    },
]


def _safe_path(rel_path: str) -> Path | None:
    """Resolve path and ensure it stays within project root."""
    try:
        clean = Path(rel_path).as_posix().lstrip("/\\")
        target = (BASE_DIR / clean).resolve()
        if target.is_relative_to(BASE_DIR):
            return target
    except Exception:
        pass
    return None


def _resolve_song(song_id: str | None = None, query: str | None = None) -> tuple[str | None, str | None, dict | None]:
    """Resolve song_id, title, and metadata from song_id, query, or active queue."""
    if song_id and cache_manager.song_dir(song_id).is_dir():
        meta = cache_manager.read_meta(song_id)
        return song_id, meta.get("title", song_id), meta

    if query:
        q_lower = query.lower().strip()
        snap = queue.snapshot()
        np = snap.get("now_playing")
        if np and (q_lower in str(np.get("title", "")).lower() or q_lower in str(np.get("id", "")).lower() or q_lower in str(np.get("song_id", "")).lower()):
            sid = np.get("id") or np.get("song_id")
            return sid, np.get("title"), cache_manager.read_meta(sid)
        for item in snap.get("queue", []):
            if q_lower in str(item.get("title", "")).lower() or q_lower in str(item.get("id", "")).lower() or q_lower in str(item.get("song_id", "")).lower():
                sid = item.get("id") or item.get("song_id")
                return sid, item.get("title"), cache_manager.read_meta(sid)
        for s in cache_manager.list_songs():
            if q_lower in str(s.get("title", "")).lower() or q_lower in str(s.get("channel", "")).lower() or q_lower in str(s.get("id", "")).lower():
                return s["id"], s.get("title", s["id"]), s

    snap = queue.snapshot()
    if snap.get("now_playing"):
        np = snap["now_playing"]
        sid = np.get("id") or np.get("song_id")
        return sid, np.get("title"), cache_manager.read_meta(sid)
    if snap.get("queue"):
        first = snap["queue"][0]
        sid = first.get("id") or first.get("song_id")
        return sid, first.get("title"), cache_manager.read_meta(sid)

    return None, None, None


# ── Tool Execution ────────────────────────────────────────────────────────────

async def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    log.info("Agent executing tool '%s' with args %s", name, args)

    if name == "customize_control_panel":
        action = str(args.get("action", "update")).strip().lower()
        cfg = get_ui_config()

        if action == "reset":
            cfg = dict(DEFAULT_UI_CONFIG)
        elif action == "add_button":
            btn = args.get("button")
            if not isinstance(btn, dict) or not btn.get("id"):
                return {"error": "Missing button object with 'id'"}
            buttons = [b for b in cfg.get("custom_buttons", []) if b.get("id") != btn["id"]]
            buttons.append(btn)
            cfg["custom_buttons"] = buttons
        elif action == "remove_button":
            btn_id = args.get("button_id")
            if not btn_id:
                return {"error": "Missing button_id to remove"}
            cfg["custom_buttons"] = [b for b in cfg.get("custom_buttons", []) if b.get("id") != btn_id]

        if "column_order" in args and isinstance(args["column_order"], list):
            cfg["column_order"] = args["column_order"]

        if "hide_elements" in args and isinstance(args["hide_elements"], list):
            hidden = list(cfg.get("hidden_elements", []))
            for el_id in args["hide_elements"]:
                if el_id and el_id not in hidden:
                    hidden.append(el_id)
            cfg["hidden_elements"] = hidden

        if "show_elements" in args and isinstance(args["show_elements"], list):
            show_set = set(args["show_elements"])
            cfg["hidden_elements"] = [el_id for el_id in cfg.get("hidden_elements", []) if el_id not in show_set]

        if "guide_width" in args and args["guide_width"]:
            cfg["guide_width"] = str(args["guide_width"]).strip()

        if "guide_thumb" in args and args["guide_thumb"]:
            cfg["guide_thumb"] = str(args["guide_thumb"]).strip()

        if "custom_css" in args and args["custom_css"] is not None:
            cfg["custom_css"] = str(args["custom_css"])

        save_ui_config(cfg)
        await hub.broadcast({"type": "ui_config", "config": cfg})
        return {"status": "ok", "action": action, "config": cfg}

    elif name == "record_improvement_request":
        topic = str(args.get("topic", "unspecified")).strip()
        desc = str(args.get("description", "")).strip()
        alt = str(args.get("safe_alternative", "")).strip()
        record_improvement(
            category="feature_request",
            summary=f"{topic}: {desc[:100]}",
            details={"topic": topic, "description": desc, "safe_alternative": alt},
        )
        return {
            "status": "recorded",
            "topic": topic,
            "note": "Request recorded in development wishlist for future updates.",
        }

    if name == "get_party_status":
        snap = queue.snapshot()
        current = snap.get("now_playing")
        items = snap.get("queue", [])
        return {
            "now_playing": {
                "title": current.get("title") if current else None,
                "singer": current.get("singer") if current else None,
                "duration": current.get("duration") if current else None,
            } if current else None,
            "queue_count": len(items),
            "upcoming": [{"title": i.get("title"), "singer": i.get("singer")} for i in items[:5]],
            "theme": settings.get("theme"),
            "accent": settings.get("accent"),
        }

    elif name == "get_library_songs":
        limit = int(args.get("limit", 30))
        query = str(args.get("search", "")).lower().strip()
        all_songs = await asyncio.to_thread(cache_manager.list_songs)
        if query:
            filtered = [
                s for s in all_songs
                if query in str(s.get("title", "")).lower() or query in str(s.get("channel", "")).lower()
            ]
        else:
            filtered = all_songs
        return {
            "total_cached": len(all_songs),
            "matched_count": len(filtered),
            "songs": [
                {
                    "id": s.get("id"),
                    "title": s.get("title", "Unknown"),
                    "channel": s.get("channel", ""),
                    "ready": bool(s.get("ready")),
                }
                for s in filtered[:limit]
            ],
        }

    elif name == "change_setting":
        key = args.get("key")
        val = args.get("value")
        if not key:
            return {"error": "Missing key"}
        # Type coercions
        if str(val).lower() in ("true", "yes", "on"):
            val = True
        elif str(val).lower() in ("false", "no", "off"):
            val = False
        else:
            try:
                val = float(val) if "." in str(val) else int(val)
            except ValueError:
                pass
        try:
            settings.update({key: val})
            await hub.broadcast({"type": "settings"})
            return {"status": "ok", "key": key, "value": val}
        except Exception as e:
            return {"error": str(e)}

    elif name == "search_and_queue":
        query = args.get("query", "").strip()
        singer = args.get("singer", "Host").strip()
        mode = args.get("mode")
        play_now = args.get("play_now", False)
        if not query:
            return {"error": "Empty query"}
        results, _ = await asyncio.to_thread(smart_search.run, query)
        if not results:
            return {"error": f"No songs found for '{query}'"}
        top = results[0]
        song_id = top.get("id") or top.get("song_id")
        entry = await queue.add(
            song_id=song_id,
            title=top.get("title", "Unknown"),
            channel=top.get("channel", ""),
            duration=top.get("duration", 0) or 0,
            singer=singer,
            thumbnail=top.get("thumbnail"),
            mode=mode,
        )
        await worker.submit(song_id)
        if cache_manager.is_ready(song_id) and not cache_manager.song_file(song_id, MELODY_FILE).is_file():
            await worker.submit_melody(song_id)

        # If idle and song is already processed, auto-start playback immediately
        if (queue.current is None or play_now) and entry.get("status") == "ready":
            await queue.next()

        is_now_playing = bool(queue.current and queue.current.get("uid") == entry["uid"])
        return {
            "status": "playing" if is_now_playing else "queued",
            "title": entry["title"],
            "singer": singer,
            "uid": entry["uid"],
            "ready": entry.get("status") == "ready",
            "now_playing": is_now_playing,
        }

    elif name == "queue_action":
        action = args.get("action")
        uid = args.get("uid")
        offset = args.get("offset", 0)
        if action in ("skip", "next"):
            started = await queue.next()
            if started:
                return {"status": "skipped", "now_playing": started["title"]}
            return {"error": "No more ready songs in queue"}
        elif action == "play":
            if queue.current is None:
                started = await queue.next()
                if started:
                    return {"status": "started", "now_playing": started["title"]}
                return {"error": "No ready songs in queue to play"}
            await queue.control("play")
            return {"status": "play"}
        elif action in ("pause", "restart"):
            await queue.control(action)
            return {"status": action}
        elif action == "remove" and uid:
            ok = await queue.remove(uid)
            return {"status": "removed" if ok else "not_found"}
        elif action == "move" and uid:
            ok = await queue.move(uid, offset)
            return {"status": "moved" if ok else "not_found"}
        return {"error": f"Unsupported action: {action}"}

    elif name == "read_code_file":
        rel = args.get("path", "")
        target = _safe_path(rel)
        if not target or not target.is_file():
            return {"error": f"File not found: {rel}"}
        try:
            return {"path": rel, "content": target.read_text(encoding="utf-8")}
        except Exception as e:
            return {"error": str(e)}

    elif name == "edit_frontend_file":
        rel = args.get("path", "")
        content = args.get("content", "")
        old_snippet = args.get("old_snippet", "")
        new_snippet = args.get("new_snippet", "")
        summary = args.get("summary", "Frontend edit")
        target = _safe_path(rel)
        if not target or not str(target).startswith(str(BASE_DIR / "static")):
            return {"error": "Only files inside static/ can be edited directly"}
        try:
            if target.is_file():
                bak = target.with_suffix(target.suffix + ".bak")
                bak.write_bytes(target.read_bytes())
                current_text = target.read_text(encoding="utf-8")
            else:
                current_text = ""

            if old_snippet:
                norm_old = old_snippet.replace("\r\n", "\n")
                norm_curr = current_text.replace("\r\n", "\n")
                if norm_old not in norm_curr:
                    return {"error": "Could not locate exact old_snippet in file"}
                final_content = norm_curr.replace(norm_old, new_snippet.replace("\r\n", "\n"))
            else:
                final_content = content

            target.write_text(final_content, encoding="utf-8")
            if rel.endswith(".css"):
                await hub.broadcast({"type": "hot_css"})
            elif rel.endswith((".html", ".js")):
                await hub.broadcast({"type": "reload"})
            return {"status": "applied", "path": rel, "summary": summary, "backed_up": True}
        except Exception as e:
            return {"error": str(e)}

    elif name == "propose_backend_diff":
        rel = args.get("path", "")
        old = args.get("old_snippet", "")
        new = args.get("new_snippet", "")
        summary = args.get("summary", "Proposed backend modification")
        target = _safe_path(rel)
        if not target or not target.is_file():
            return {"error": f"File not found: {rel}"}
        file_text = target.read_text(encoding="utf-8")
        if old.replace("\r\n", "\n") not in file_text.replace("\r\n", "\n"):
            return {"error": "Could not locate exact old_snippet in file"}

        prop_id = f"prop_{uuid.uuid4().hex[:8]}"
        updated_text = file_text.replace(old.replace("\r\n", "\n"), new.replace("\r\n", "\n"))
        diff_lines = list(difflib.unified_diff(
            file_text.splitlines(keepends=True),
            updated_text.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        ))
        diff_text = "".join(diff_lines)

        PENDING_PROPOSALS[prop_id] = {
            "id": prop_id,
            "path": rel,
            "old": old,
            "new": new,
            "summary": summary,
            "diff": diff_text,
            "created": time.time(),
        }
        return {
            "status": "proposed",
            "proposal_id": prop_id,
            "path": rel,
            "summary": summary,
            "diff": diff_text,
        }

    elif name == "undo_frontend_edit":
        rel = args.get("path", "")
        target = _safe_path(rel)
        if not target:
            return {"error": "Invalid path"}
        bak = target.with_suffix(target.suffix + ".bak")
        if not bak.is_file():
            return {"error": "No backup found to restore"}
        try:
            target.write_bytes(bak.read_bytes())
            bak.unlink()
            if rel.endswith(".css"):
                await hub.broadcast({"type": "hot_css"})
            elif rel.endswith((".html", ".js")):
                await hub.broadcast({"type": "reload"})
            return {"status": "undone", "path": rel}
        except Exception as e:
            return {"error": str(e)}

    elif name == "get_song_lyrics":
        song_id, title, meta = _resolve_song(args.get("song_id"), args.get("query"))
        if not song_id:
            return {
                "error": "Could not identify which song's lyrics to inspect. Please specify a song title or ID, or have a song playing or queued."
            }
        lyrics_text = lyrics_source.current_text(song_id)
        if not lyrics_text:
            return {
                "song_id": song_id,
                "title": title,
                "text": "",
                "line_count": 0,
                "has_user_lyrics": False,
                "status": "no_lyrics_found",
            }
        lines = lyrics_text.splitlines()
        return {
            "song_id": song_id,
            "title": title,
            "has_user_lyrics": lyrics_source.load_user(song_id) is not None,
            "source": meta.get("lyrics_source") if meta else None,
            "line_count": len(lines),
            "text": lyrics_text,
        }

    elif name == "edit_song_lyrics":
        song_id, title, meta = _resolve_song(args.get("song_id"), args.get("query"))
        if not song_id:
            return {
                "error": "Could not identify which song's lyrics to edit. Please specify a song title or ID, or have a song playing or queued."
            }

        reset = bool(args.get("reset", False))
        if reset:
            lyrics_source.delete_user(song_id)
            lyrics_source.forget_online(song_id)
            ultrastar_source.forget(song_id)
            await worker.submit_lyrics(song_id)
            return {
                "status": "reset",
                "song_id": song_id,
                "title": title,
                "summary": f"Reset lyrics for '{title}' to automatic online detection and triggered re-alignment.",
            }

        old_snippet = args.get("old_snippet")
        new_snippet = args.get("new_snippet")
        full_text = args.get("text")

        if not full_text and (old_snippet is None or new_snippet is None):
            return {
                "error": "Please provide either 'text' for full lyrics replacement OR 'old_snippet' and 'new_snippet' for surgical editing."
            }

        current = lyrics_source.current_text(song_id)
        if old_snippet is not None and new_snippet is not None:
            norm_old = str(old_snippet).replace("\r\n", "\n")
            norm_curr = current.replace("\r\n", "\n")
            if norm_old not in norm_curr:
                lines_preview = "\n".join(current.splitlines()[:8])
                return {
                    "error": f"Could not find snippet '{old_snippet}' in current lyrics for '{title}'.",
                    "current_lyrics_preview": lines_preview,
                }
            final_text = norm_curr.replace(norm_old, str(new_snippet).replace("\r\n", "\n"))
        else:
            final_text = full_text

        try:
            line_count = lyrics_source.save_user(song_id, final_text)
        except ValueError as exc:
            return {"error": str(exc)}

        await worker.submit_lyrics(song_id)
        return {
            "status": "updated",
            "song_id": song_id,
            "title": title,
            "line_count": line_count,
            "summary": f"Successfully updated lyrics for '{title}' ({line_count} lines) and scheduled re-alignment.",
        }

    return {"error": f"Unknown tool: {name}"}


# ── Proposal Application ──────────────────────────────────────────────────────

def apply_proposal(proposal_id: str) -> dict[str, Any]:
    prop = PENDING_PROPOSALS.pop(proposal_id, None)
    if not prop:
        return {"error": "Proposal not found or expired"}
    target = _safe_path(prop["path"])
    if not target or not target.is_file():
        return {"error": "Target file no longer exists"}
    try:
        content = target.read_text(encoding="utf-8")
        norm_old = prop["old"].replace("\r\n", "\n")
        norm_new = prop["new"].replace("\r\n", "\n")
        norm_content = content.replace("\r\n", "\n")
        if norm_old not in norm_content:
            return {"error": "Target snippet changed since proposal was generated"}
        # Backup
        bak = target.with_suffix(target.suffix + ".bak")
        bak.write_text(content, encoding="utf-8")
        # Apply
        target.write_text(norm_content.replace(norm_old, norm_new), encoding="utf-8")
        log.info("Applied backend proposal %s to %s", proposal_id, prop["path"])
        return {"status": "applied", "path": prop["path"], "summary": prop["summary"]}
    except Exception as e:
        return {"error": str(e)}


def cancel_proposal(proposal_id: str) -> dict[str, Any]:
    if PENDING_PROPOSALS.pop(proposal_id, None):
        return {"status": "cancelled", "proposal_id": proposal_id}
    return {"error": "Proposal not found"}


# ── LLM Client (Gemini & OpenAI) ─────────────────────────────────────────────

def _get_api_key() -> str:
    key = settings.get("agent_api_key").strip()
    if not key:
        key = os.getenv("GEMINI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    return key


async def chat_with_agent(message: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Execute a chat turn with Google Gemini (or OpenAI-compatible fallback)."""
    provider = settings.get("agent_provider")
    model = settings.get("agent_model")
    api_key = _get_api_key()

    if not api_key and provider == "gemini":
        return {
            "reply": "⚠️ Please configure your **Google AI Studio API key** in Settings → AI Co-Pilot (or set GEMINI_API_KEY in your environment).",
            "tool_calls": [],
        }

    history = history or []

    if provider == "gemini":
        if not model or model.strip().removeprefix("models/") == "gemini-2.5-flash":
            model = "gemini-3.8-flash"
        return await _chat_gemini(message, history, model, api_key)
    else:
        return await _chat_openai(message, history, model, api_key)


async def _chat_gemini(message: str, history: list[dict], model: str, api_key: str) -> dict[str, Any]:
    clean_model = model.strip().removeprefix("models/")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
    
    # Format Gemini contents
    contents = []
    for h in history[-8:]:  # keep last 8 turns for context
        role = "model" if h.get("role") in ("assistant", "model") else "user"
        contents.append({"role": role, "parts": [{"text": h.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    gemini_tools = [
        {
            "functionDeclarations": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                }
                for t in TOOLS_SCHEMA
            ]
        }
    ]

    executed_tools = []
    proposals = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Loop for function calling
        for _ in range(8):  # max 8 tool call rounds per turn
            payload = {
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": contents,
                "tools": gemini_tools,
            }
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                log.error("Gemini API error %d: %s", res.status_code, res.text)
                tip = ""
                if res.status_code == 404:
                    tip = f"\n\n💡 *Tip: Model '{clean_model}' was not found. Try 'gemini-3.8-flash', 'gemini-flash-latest', or 'gemini-3.5-flash' in Settings → AI Co-Pilot.*"
                elif res.status_code == 400 and "API_KEY_INVALID" in res.text:
                    tip = "\n\n💡 *Tip: Google AI Studio API key appears invalid. Check Settings → AI Co-Pilot.*"
                return {"reply": f"❌ Gemini API Error ({res.status_code}): {res.text[:250]}{tip}", "tool_calls": []}

            data = res.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return {"reply": "Received empty response from Gemini.", "tool_calls": executed_tools}

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            
            # Check for function calls
            fn_calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not fn_calls:
                # Text response complete
                text_parts = [p.get("text", "") for p in parts if "text" in p]
                reply_text = "\n".join(text_parts).strip()
                return {
                    "reply": reply_text or "Done!",
                    "tool_calls": executed_tools,
                    "proposals": proposals,
                }

            # Append model turn with function calls
            contents.append({"role": "model", "parts": parts})

            # Execute tool calls and create response parts
            resp_parts = []
            for fn in fn_calls:
                fn_name = fn.get("name")
                fn_args = fn.get("args", {})
                result = await execute_tool(fn_name, fn_args)
                executed_tools.append({"name": fn_name, "args": fn_args, "result": result})
                if "error" in result:
                    record_improvement(
                        category="tool_error",
                        summary=f"Tool '{fn_name}' error: {result['error']}",
                        details={"tool": fn_name, "args": fn_args, "error": result["error"]},
                        prompt=message,
                    )
                if fn_name == "propose_backend_diff" and result.get("status") == "proposed":
                    proposals.append(result)
                resp_parts.append({
                    "functionResponse": {
                        "name": fn_name,
                        "response": {"result": result},
                    }
                })

            contents.append({"role": "user", "parts": resp_parts})

    record_improvement(
        category="turn_limit_exhausted",
        summary=f"Hit 8-turn limit on prompt: {message[:100]}",
        details={"tools_called": [t.get("name") for t in executed_tools]},
        prompt=message,
    )
    tool_names = ", ".join(dict.fromkeys(t.get("name", "") for t in executed_tools if t.get("name")))
    friendly_reply = (
        "🎤 Whoa, I went down a bit of a rabbit hole working through all the steps on that request and hit my DJ turn limit! "
        f"I tried steps with {tool_names or 'various tools'} but paused before wrapping it up to keep the party running safely. "
        "I've logged this in my improvement backlog so our developers can make this capability seamless. "
        "Would you like me to try a simpler approach or pick a specific action?"
    )
    return {"reply": friendly_reply, "tool_calls": executed_tools, "proposals": proposals}


def _normalize_openai_schema(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        return params
    out = {}
    for k, v in params.items():
        if k == "type" and isinstance(v, str):
            out[k] = v.lower()
        elif isinstance(v, dict):
            out[k] = _normalize_openai_schema(v)
        else:
            out[k] = v
    return out


async def _chat_openai(message: str, history: list[dict], model: str, api_key: str) -> dict[str, Any]:
    base_url = settings.get("agent_base_url").strip().rstrip("/")
    if not base_url:
        base_url = "https://api.openai.com/v1"
    url = f"{base_url}/chat/completions"

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history[-8:]:
        role = "assistant" if h.get("role") in ("assistant", "model") else "user"
        messages.append({"role": role, "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": _normalize_openai_schema(t["parameters"]),
            },
        }
        for t in TOOLS_SCHEMA
    ]

    headers = {"Authorization": f"Bearer {api_key or 'local'}"}
    executed_tools = []
    proposals = []

    async with httpx.AsyncClient(timeout=45.0) as client:
        for _ in range(8):
            payload = {
                "model": model,
                "messages": messages,
                "tools": openai_tools,
            }
            res = await client.post(url, json=payload, headers=headers)
            if res.status_code != 200:
                return {"reply": f"❌ API Error ({res.status_code}): {res.text[:200]}", "tool_calls": []}

            data = res.json()
            choice = data["choices"][0]
            msg = choice["message"]
            messages.append(msg)

            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                return {
                    "reply": msg.get("content", "Done!"),
                    "tool_calls": executed_tools,
                    "proposals": proposals,
                }

            for tc in tool_calls:
                fn = tc["function"]
                fn_name = fn["name"]
                fn_args = json.loads(fn.get("arguments", "{}"))
                result = await execute_tool(fn_name, fn_args)
                executed_tools.append({"name": fn_name, "args": fn_args, "result": result})
                if "error" in result:
                    record_improvement(
                        category="tool_error",
                        summary=f"Tool '{fn_name}' error: {result['error']}",
                        details={"tool": fn_name, "args": fn_args, "error": result["error"]},
                        prompt=message,
                    )
                if fn_name == "propose_backend_diff" and result.get("status") == "proposed":
                    proposals.append(result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result),
                })

    record_improvement(
        category="turn_limit_exhausted",
        summary=f"Hit 8-turn limit on prompt: {message[:100]}",
        details={"tools_called": [t.get("name") for t in executed_tools]},
        prompt=message,
    )
    tool_names = ", ".join(dict.fromkeys(t.get("name", "") for t in executed_tools if t.get("name")))
    friendly_reply = (
        "🎤 Whoa, I went down a bit of a rabbit hole working through all the steps on that request and hit my DJ turn limit! "
        f"I tried steps with {tool_names or 'various tools'} but paused before wrapping it up to keep the party running safely. "
        "I've logged this in my improvement backlog so our developers can make this capability seamless. "
        "Would you like me to try a simpler approach or pick a specific action?"
    )
    return {"reply": friendly_reply, "tool_calls": executed_tools, "proposals": proposals}
