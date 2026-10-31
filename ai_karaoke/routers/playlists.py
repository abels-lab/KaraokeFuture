"""Playlist API endpoints: list, create, update, delete, play, and promote songs."""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import auth
from core.playlist_manager import playlist_manager
from core.queue_manager import queue

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/playlists", tags=["playlists"])


class CreatePlaylistRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    songs: list[Any] = Field(default_factory=list)
    playlist_id: str | None = Field(default=None, max_length=64)


class UpdatePlaylistRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    songs: list[Any] | None = None
    action: str = Field(default="set")  # "set" | "add_songs" | "remove_songs"


class PlayPlaylistRequest(BaseModel):
    shuffle: bool = False
    loop: bool = False


class PromoteSongRequest(BaseModel):
    query: str | None = None
    index: int | None = None
    singer: str | None = None


@router.get("")
async def list_playlists() -> dict[str, Any]:
    """List all available playlists (built-in weekly hits & top hits, plus custom playlists)."""
    active_id = queue.active_playlist.get("id") if queue.active_playlist else None
    return {
        "playlists": playlist_manager.list_playlists(active_playlist_id=active_id),
        "active_playlist": queue.active_playlist_snapshot(),
    }


@router.get("/{playlist_id}")
async def get_playlist(playlist_id: str) -> dict[str, Any]:
    """Get full details and track list of a playlist."""
    pl = playlist_manager.get_playlist(playlist_id)
    if not pl:
        raise HTTPException(404, f"Playlist '{playlist_id}' not found")
    return pl


@router.post("", status_code=201)
async def create_playlist(
    req: CreatePlaylistRequest,
    who: auth.Who = Depends(auth.require_admin),
) -> dict[str, Any]:
    """Create a new custom playlist (Host only)."""
    try:
        return playlist_manager.create_playlist(
            name=req.name,
            songs=req.songs,
            description=req.description,
            playlist_id=req.playlist_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/{playlist_id}")
async def update_playlist(
    playlist_id: str,
    req: UpdatePlaylistRequest,
    who: auth.Who = Depends(auth.require_admin),
) -> dict[str, Any]:
    """Update a custom playlist (Host only)."""
    try:
        return playlist_manager.update_playlist(
            playlist_id=playlist_id,
            name=req.name,
            description=req.description,
            songs=req.songs,
            action=req.action,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/{playlist_id}")
async def delete_playlist(
    playlist_id: str,
    who: auth.Who = Depends(auth.require_admin),
) -> dict[str, Any]:
    """Delete a custom playlist (Host only)."""
    try:
        ok = playlist_manager.delete_playlist(playlist_id)
        if not ok:
            raise HTTPException(404, f"Playlist '{playlist_id}' not found")
        return {"ok": True, "deleted": playlist_id}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/{playlist_id}/play")
async def play_playlist(
    playlist_id: str,
    req: PlayPlaylistRequest = PlayPlaylistRequest(),
    who: auth.Who = Depends(auth.require_admin),
) -> dict[str, Any]:
    """Start playing a playlist with less priority in queue (Auto-DJ filler)."""
    try:
        res = await queue.start_playlist(playlist_id, shuffle=req.shuffle, loop=req.loop)
        return {"ok": True, "active_playlist": res}
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/stop")
async def stop_playlist(
    who: auth.Who = Depends(auth.require_admin),
) -> dict[str, Any]:
    """Stop the currently active playlist."""
    stopped = await queue.stop_playlist()
    return {"ok": stopped}


@router.post("/promote", status_code=201)
async def promote_playlist_song(
    req: PromoteSongRequest,
    request: Request,
) -> dict[str, Any]:
    """Promote a song from the currently playing playlist into the user queue."""
    who = auth.identify(request)
    if not queue.active_playlist:
        raise HTTPException(400, "No active playlist is currently playing")

    # Determine singer name and guest id
    if who.guest_id is not None:
        singer = who.name
        owner = who.guest_id
    elif who.admin:
        singer = req.singer.strip() if req.singer and req.singer.strip() else "Host"
        owner = None
    else:
        raise HTTPException(401, "Please log in on remote to add songs")

    target = req.index if req.index is not None else req.query
    if target is None:
        raise HTTPException(400, "Must provide 'query' or 'index' to promote")

    entry = await queue.promote_playlist_song(target, singer=singer, owner=owner)
    if not entry:
        raise HTTPException(404, "Song not found in active playlist queue")

    return {"ok": True, "entry": entry}
