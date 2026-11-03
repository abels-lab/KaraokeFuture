"""Song cache tools for the Settings page: usage, trim to the limit, clear. Host only.

Songs that are playing, queued, recently played or being processed are never deleted
(core/cache_admin.py). Pasted lyrics live outside the cache and are never touched.
"""
import asyncio
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core import auth, cache_admin
from core.hub import hub

router = APIRouter(prefix="/api/cache", dependencies=[Depends(auth.require_admin)])


class ClearRequest(BaseModel):
    what: Literal["warm", "all"]   # unplayed warm-ups only | everything not protected


@router.get("")
async def cache_stats():
    return await asyncio.to_thread(cache_admin.stats)


@router.post("/trim")
async def cache_trim():
    result = await asyncio.to_thread(cache_admin.trim)
    if result["evicted"]:
        await hub.broadcast({"type": "library"})
    return {**result, "stats": await asyncio.to_thread(cache_admin.stats)}


@router.post("/clear")
async def cache_clear(req: ClearRequest):
    result = await asyncio.to_thread(cache_admin.clear, req.what)
    if result["evicted"]:
        await hub.broadcast({"type": "library"})
    return {**result, "stats": await asyncio.to_thread(cache_admin.stats)}
