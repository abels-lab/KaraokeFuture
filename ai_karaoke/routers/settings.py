"""Settings page API: read every setting, change some, reset to defaults.

Everyone may look; changing and resetting is for the host (core/auth.py): the laptop running
the karaoke, or a device unlocked with the host PIN. This replaced the old "Allow changes
from other devices" switch — one lock instead of two (an old settings.json that still has
that key loads fine; core/settings.py drops it quietly).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core import auth, settings
from core.hub import hub
from core.settings_schema import GROUPS

router = APIRouter(prefix="/api/settings")


class Changes(BaseModel):
    values: dict


class ResetRequest(BaseModel):
    keys: list[str] | None = None   # None = reset everything


def _page(request: Request) -> dict:
    return {"groups": [{"id": g, "label": label} for g, label in GROUPS], "settings": settings.snapshot(),
            "can_edit": auth.identify(request).admin}


@router.get("")
async def read(request: Request):
    return _page(request)


@router.get("/client")
async def client():
    """Values the browser pages use (singing game, playback)."""
    return settings.client_values()


@router.put("", dependencies=[Depends(auth.require_admin)])
async def change(req: Changes, request: Request):
    try:
        settings.update(req.values)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await hub.broadcast({"type": "settings"})   # open pages reload the values they use
    return _page(request)


@router.post("/reset", dependencies=[Depends(auth.require_admin)])
async def reset(req: ResetRequest, request: Request):
    unknown = [key for key in req.keys or [] if key not in settings.BY_KEY]
    if unknown:
        raise HTTPException(422, f"Unknown setting: {', '.join(unknown)}")
    settings.reset(req.keys)
    await hub.broadcast({"type": "settings"})
    return _page(request)
