"""DJ Co-Pilot chat API. The host may always talk to it; logged-in guests too when the host
switched on Settings → AI Co-Pilot → "Guests may talk to the Co-Pilot". Either way it acts with
the asker's own rights (services/agent/registry.py)."""
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import auth, settings
from core.hub import hub
from services import agent

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])
GUEST_EVERY = 4.0   # seconds between two messages from the same guest
_last_by_guest: dict[int, float] = {}


class ChatRequest(BaseModel):
    message: str = Field(max_length=1000)
    history: list[dict[str, Any]] = Field(default=[], max_length=40)


def _chatter(request: Request) -> auth.Who:
    """The host, or a logged-in guest when guests may chat (at most one message per GUEST_EVERY)."""
    who = auth.identify(request)
    if who.admin:
        return who
    if who.guest_id is None:
        raise HTTPException(401, "Log in with your name on the remote page first")
    if not settings.get("agent_guest_chat"):
        raise HTTPException(403, "The host hasn't opened the DJ Co-Pilot to guests")
    now = time.monotonic()
    if now - _last_by_guest.get(who.guest_id, -GUEST_EVERY) < GUEST_EVERY:
        raise HTTPException(429, "Slow down a little: one message every few seconds")
    _last_by_guest[who.guest_id] = now
    return who


async def _show(sender: str, name: str, text: str) -> None:
    """The message on the projector's chat overlay (Settings → Screen & theme → chat)."""
    await hub.broadcast({"type": "chat", "id": f"{sender}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}",
                         "sender": sender, "name": name, "text": text, "timestamp": time.time()}, "screen")


@router.post("/chat")
async def chat(req: ChatRequest, who: auth.Who = Depends(_chatter)) -> dict[str, Any]:
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")
    await _show("user", who.name or "Host", req.message)
    res = await agent.chat_with_agent(req.message, req.history, who)
    if res.get("reply"):
        await _show("agent", "DJ Co-Pilot", res["reply"])
    return res


@router.get("/improvements")
async def get_improvements(who: auth.Who = Depends(auth.require_admin)) -> list[dict[str, Any]]:
    """What the Co-Pilot couldn't do: tool errors, wishes, give-ups."""
    return agent.list_improvements(limit=50)


@router.get("/ui-config")
async def get_ui_config() -> dict[str, Any]:
    """The Control Panel layout the Co-Pilot customised."""
    return agent.get_ui_config()
