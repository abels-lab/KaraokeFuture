"""Host AI Assistant / Co-Pilot API endpoints."""
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import auth
from core.hub import hub
from services import agent

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = []


class DiffActionRequest(BaseModel):
    proposal_id: str


class UndoRequest(BaseModel):
    path: str


@router.post("/chat")
async def chat(req: ChatRequest, who: auth.Who = Depends(auth.require_admin)) -> dict[str, Any]:
    """Host AI chat: executes tools, answers questions, modifies styles or proposes Python diffs."""
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")

    user_msg_id = f"user_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    await hub.broadcast({
        "type": "chat",
        "id": user_msg_id,
        "sender": "user",
        "name": getattr(who, "name", None) or "Host",
        "text": req.message,
        "timestamp": time.time(),
    }, "screen")

    res = await agent.chat_with_agent(req.message, req.history)

    reply_text = res.get("reply", "")
    if reply_text:
        agent_msg_id = f"agent_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        await hub.broadcast({
            "type": "chat",
            "id": agent_msg_id,
            "sender": "agent",
            "name": "DJ Co-Pilot",
            "text": reply_text,
            "timestamp": time.time(),
        }, "screen")

    return res


@router.post("/diff/apply")
async def apply_diff(req: DiffActionRequest, who: auth.Who = Depends(auth.require_admin)) -> dict[str, Any]:
    """Host confirms a proposed backend diff: writes file and triggers reload."""
    res = agent.apply_proposal(req.proposal_id)
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@router.post("/diff/cancel")
async def cancel_diff(req: DiffActionRequest, who: auth.Who = Depends(auth.require_admin)) -> dict[str, Any]:
    """Host cancels a proposed backend diff."""
    res = agent.cancel_proposal(req.proposal_id)
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res


@router.post("/undo")
async def undo_edit(req: UndoRequest, who: auth.Who = Depends(auth.require_admin)) -> dict[str, Any]:
    """Reverts a frontend edit by restoring .bak file."""
    res = await agent.execute_tool("undo_frontend_edit", {"path": req.path})
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@router.get("/improvements")
async def get_improvements(who: auth.Who = Depends(auth.require_admin)) -> list[dict[str, Any]]:
    """Retrieve logged agent capability gaps, tool errors, and host feature requests."""
    return agent.list_improvements(limit=50)


@router.get("/ui-config")
async def get_ui_config() -> dict[str, Any]:
    """Retrieve active Control Panel UI customization config."""
    return agent.get_ui_config()
