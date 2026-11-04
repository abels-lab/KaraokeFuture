"""Settings › Sources: the websites songs and lyrics come from. Host only (core/auth.py).

List the built-in and custom sources by kind, switch one on or off, move it up or down (the
fallback order), add / change / remove the host's own links, and test a link before saving it.
Every link is validated by core/source_links.py (public http(s) only, placeholders required);
a test runs the real lookup with a time limit and returns a short sample, never a browser.
"""
import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config import GENIUS_TOKEN
from core import auth, settings, sources_registry
from core.hub import hub
from core.source_links import MAX_LEN, MAX_NAME, LinkError, check_template
from services import custom_lyrics, custom_songs, usdb

router = APIRouter(prefix="/api/sources", dependencies=[Depends(auth.require_admin)])
TEST_SONG = ("Queen", "Bohemian Rhapsody")
TEST_TIMEOUT = 20   # seconds


class Toggle(BaseModel):
    enabled: bool


class Move(BaseModel):
    step: Literal[-1, 1]


class Link(BaseModel):
    kind: Literal["songs", "lyrics"]
    name: str = Field(min_length=1, max_length=MAX_NAME)
    template: str = Field(min_length=1, max_length=MAX_LEN)


class Test(BaseModel):
    kind: Literal["songs", "lyrics"]
    template: str = Field(min_length=1, max_length=MAX_LEN)
    query: str | None = Field(default=None, max_length=120)


def _page() -> dict:
    """Every kind with its sources, plus what the laptop is missing for some of them."""
    return {**sources_registry.snapshot(), "status": {
        "genius": "ready" if GENIUS_TOKEN else "GENIUS_ACCESS_TOKEN is not set on the laptop",
        "usdb": "ready" if usdb.configured() else "USDB_USER / USDB_PASSWORD are not set on the laptop",
        "ultimate-guitar": "ready" if settings.get("use_chords_lyrics") else "“Search guitar tab sites” is off",
        "amdm": "ready" if settings.get("use_chords_lyrics") else "“Search guitar tab sites” is off"}}


async def _changed() -> dict:
    await hub.broadcast({"type": "settings"})   # open Settings pages reload (some toggles are settings)
    return _page()


@router.get("")
async def read():
    return _page()


@router.put("/{source_id}")
async def toggle(source_id: str, req: Toggle):
    try:
        sources_registry.set_enabled(source_id, req.enabled)
    except KeyError:
        raise HTTPException(404, "No such source") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await _changed()


@router.post("/{source_id}/move")
async def move(source_id: str, req: Move):
    try:
        sources_registry.move(source_id, req.step)
    except KeyError:
        raise HTTPException(404, "No such source") from None
    return await _changed()


@router.post("/custom")
async def add(req: Link):
    try:
        sources_registry.save_custom(req.kind, req.name, req.template)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await _changed()


@router.put("/custom/{source_id}")
async def change(source_id: str, req: Link):
    try:
        sources_registry.save_custom(req.kind, req.name, req.template, source_id)
    except KeyError:
        raise HTTPException(404, "No such link") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await _changed()


@router.delete("/custom/{source_id}")
async def remove(source_id: str):
    try:
        sources_registry.remove_custom(source_id)
    except KeyError:
        raise HTTPException(404, "No such link") from None
    return await _changed()


def _run_test(req: Test) -> dict:
    template = check_template(req.template, req.kind)
    link = {"id": "test", "name": "Test", "template": template, "builtin": False}
    query = (req.query or "").strip() or " - ".join(TEST_SONG)
    if req.kind == "songs":
        results = custom_songs.search(link, query, 5)
        return {"query": query, "count": len(results),
                "sample": [f"{r['title']} ({r['duration'] // 60}:{r['duration'] % 60:02d})" if r["duration"] else r["title"]
                           for r in results]}
    text = custom_lyrics.fetch(link, query) or ""
    lines = [line for line in text.splitlines() if line.strip()]
    return {"query": query, "count": len(lines), "sample": lines[:2]}


@router.post("/test")
async def test(req: Test):
    """Try a link (saved or not) with a sample song. 422 for a link that breaks the rules."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(_run_test, req), TEST_TIMEOUT)
    except LinkError as exc:
        raise HTTPException(422, str(exc)) from exc
    except asyncio.TimeoutError:
        raise HTTPException(504, f"No answer within {TEST_TIMEOUT} s") from None
    except Exception as exc:   # yt-dlp: unsupported site, page not found...
        raise HTTPException(502, f"The link didn't work: {str(exc).removeprefix('ERROR: ')[:200]}") from exc
