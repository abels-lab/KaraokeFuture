"""Settings page API: read every setting, change some, reset to defaults.

Changing is limited to this laptop unless "Allow changes from other devices" is on, so a
guest who opens the page on a phone can look but not break anything.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from config import get_local_ip
from core import settings
from core.hub import hub
from core.settings_schema import GROUPS

router = APIRouter(prefix="/api/settings")


class Changes(BaseModel):
    values: dict


class ResetRequest(BaseModel):
    keys: list[str] | None = None   # None = reset everything


def _is_this_laptop(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost", "testclient", get_local_ip())


def _check_allowed(request: Request) -> None:
    if not settings.get("allow_remote_settings") and not _is_this_laptop(request):
        raise HTTPException(403, "Settings can only be changed on the laptop running the karaoke")


def _page(request: Request) -> dict:
    return {"groups": [{"id": g, "label": label} for g, label in GROUPS], "settings": settings.snapshot(),
            "can_edit": settings.get("allow_remote_settings") or _is_this_laptop(request)}


@router.get("")
async def read(request: Request):
    return _page(request)


@router.get("/client")
async def client():
    """Values the browser pages use (singing game, playback)."""
    return settings.client_values()


@router.put("")
async def change(req: Changes, request: Request):
    _check_allowed(request)
    try:
        settings.update(req.values)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await hub.broadcast({"type": "settings"})   # open pages reload the values they use
    return _page(request)


@router.post("/reset")
async def reset(req: ResetRequest, request: Request):
    _check_allowed(request)
    unknown = [key for key in req.keys or [] if key not in settings.BY_KEY]
    if unknown:
        raise HTTPException(422, f"Unknown setting: {', '.join(unknown)}")
    settings.reset(req.keys)
    await hub.broadcast({"type": "settings"})
    return _page(request)
