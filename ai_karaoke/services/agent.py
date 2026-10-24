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

from config import BASE_DIR
from core import settings
from core.hub import hub
from core.queue_manager import queue
from services import sources

log = logging.getLogger(__name__)

# Pending backend diffs awaiting host confirmation
PENDING_PROPOSALS: dict[str, dict] = {}

SYSTEM_PROMPT = """You are the AI Karaoke Host & DJ Co-Pilot for AI Karaoke.
You assist the host with running the party:
1. Finding and enqueuing songs for singers (use search_and_queue).
2. Changing app settings (themes, accents, durations, volume, guest permissions).
3. Queue management (skipping songs, moving, removing).
4. Live frontend code editing (static/*.css, static/*.js, static/*.html): modify styles, lyric sizes, colors, animations directly via edit_frontend_file.
5. Server backend code modifications (core/*.py, routers/*.py, services/*.py): propose changes via propose_backend_diff so the host can review the diff.

Guidelines:
- Keep verbal responses concise, witty, and party-ready.
- When the host asks to queue a song or change something, immediately call the appropriate tool.
- For frontend visual tweaks, read the file first with read_code_file if needed, then apply with edit_frontend_file.
- For Python code, always use propose_backend_diff. Never attempt to edit backend files directly.
"""

# ── Tool Definitions ──────────────────────────────────────────────────────────

TOOLS_SCHEMA = [
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
        "name": "change_setting",
        "description": "Change an application setting (e.g. theme to 'adaptive', accent to 'lime', show_video to true/false, guest_scrubbing, cache_limit_gb).",
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
        "description": "Read the contents of a project file (e.g. static/theme.css, static/tv.js, core/worker.py).",
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
        "description": "Directly edit a frontend file in static/ (e.g. static/theme.css, static/remote.html). Automatically backs up and hot-reloads.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path in static/ (e.g. static/theme.css)"},
                "content": {"type": "STRING", "description": "New full content of the file"},
                "summary": {"type": "STRING", "description": "Short description of the modification"},
            },
            "required": ["path", "content", "summary"],
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


# ── Tool Execution ────────────────────────────────────────────────────────────

async def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    log.info("Agent executing tool '%s' with args %s", name, args)

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
        if not query:
            return {"error": "Empty query"}
        results = await sources.search_all(query)
        if not results:
            return {"error": f"No songs found for '{query}'"}
        top = results[0]
        entry = await queue.add(
            song_id=top["song_id"],
            title=top["title"],
            channel=top["channel"],
            duration=top.get("duration", 0),
            singer=singer,
            thumbnail=top.get("thumbnail"),
            mode=mode,
        )
        return {
            "status": "queued",
            "title": entry["title"],
            "singer": singer,
            "uid": entry["uid"],
        }

    elif name == "queue_action":
        action = args.get("action")
        uid = args.get("uid")
        offset = args.get("offset", 0)
        if action == "skip":
            if queue.current:
                await queue.next()
                return {"status": "skipped"}
            return {"error": "Nothing currently playing"}
        elif action in ("play", "pause", "restart"):
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
        summary = args.get("summary", "Frontend edit")
        target = _safe_path(rel)
        if not target or not str(target).startswith(str(BASE_DIR / "static")):
            return {"error": "Only files inside static/ can be edited directly"}
        try:
            if target.is_file():
                bak = target.with_suffix(target.suffix + ".bak")
                bak.write_bytes(target.read_bytes())
            target.write_text(content, encoding="utf-8")
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
            return {"status": "undone", "path": rel}
        except Exception as e:
            return {"error": str(e)}

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
        return await _chat_gemini(message, history, model, api_key)
    else:
        return await _chat_openai(message, history, model, api_key)


async def _chat_gemini(message: str, history: list[dict], model: str, api_key: str) -> dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
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
        for _ in range(5):  # max 5 tool call rounds per turn
            payload = {
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": contents,
                "tools": gemini_tools,
            }
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                log.error("Gemini API error %d: %s", res.status_code, res.text)
                return {"reply": f"❌ Gemini API Error ({res.status_code}): {res.text[:200]}", "tool_calls": []}

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
                if fn_name == "propose_backend_diff" and result.get("status") == "proposed":
                    proposals.append(result)
                resp_parts.append({
                    "functionResponse": {
                        "name": fn_name,
                        "response": {"result": result},
                    }
                })

            contents.append({"role": "user", "parts": resp_parts})

    return {"reply": "Tool execution completed.", "tool_calls": executed_tools, "proposals": proposals}


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
                "parameters": {
                    "type": "object",
                    "properties": t["parameters"]["properties"],
                    "required": t["parameters"]["required"],
                },
            },
        }
        for t in TOOLS_SCHEMA
    ]

    headers = {"Authorization": f"Bearer {api_key or 'local'}"}
    executed_tools = []
    proposals = []

    async with httpx.AsyncClient(timeout=45.0) as client:
        for _ in range(5):
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
                if fn_name == "propose_backend_diff" and result.get("status") == "proposed":
                    proposals.append(result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result),
                })

    return {"reply": "Completed.", "tool_calls": executed_tools, "proposals": proposals}
