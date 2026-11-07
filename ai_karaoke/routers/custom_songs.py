"""Endpoints for custom & unofficial songs: direct file upload and external link ingestion."""
import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from core import auth, settings
from core.queue_access import enqueue, singer_for
from core.worker import worker
from services import custom_ingest

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/custom", tags=["custom"])


class ProbeRequest(BaseModel):
    url: str = Field(min_length=3, max_length=500)


class LinkRequest(BaseModel):
    url: str = Field(min_length=3, max_length=500)
    title: str = Field(default="", max_length=200)
    artist: str = Field(default="", max_length=120)
    lyrics_text: str = Field(default="", max_length=20000)
    target: Literal["queue", "library"] = "queue"
    singer: str = Field(default="", max_length=32)


def _check_upload_allowed(who: auth.Who) -> None:
    if not who.admin and not settings.get("allow_guest_uploads", True):
        raise HTTPException(403, "Guest song uploads are disabled by the host.")


@router.post("/probe")
async def probe_link(req: ProbeRequest):
    """Inspect an external link to preview title, artist, duration and thumbnail before importing."""
    try:
        return await asyncio.to_thread(custom_ingest.probe_url, req.url)
    except custom_ingest.IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        log.warning("Probe failed for %s: %s", req.url, exc)
        raise HTTPException(400, f"Could not inspect link: {exc}") from exc


@router.post("/upload", status_code=201)
async def upload_custom_song(
    request: Request,
    file: UploadFile = File(...),
    lyrics_file: UploadFile | None = File(None),
    lyrics_text: str = Form(""),
    title: str = Form(""),
    artist: str = Form(""),
    target: Literal["queue", "library"] = Form("queue"),
    singer: str = Form(""),
):
    who = auth.identify(request)
    _check_upload_allowed(who)

    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty audio file received.")

    raw_lyrics = lyrics_text
    if lyrics_file:
        try:
            l_bytes = await lyrics_file.read()
            if l_bytes:
                raw_lyrics = l_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            log.warning("Could not read uploaded lyrics file: %s", exc)

    try:
        meta = await asyncio.to_thread(
            custom_ingest.ingest_file,
            content,
            file.filename or "upload.mp3",
            title=title,
            artist=artist,
            lyrics=raw_lyrics,
        )
    except custom_ingest.IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        log.exception("Upload failed for %s", file.filename)
        raise HTTPException(500, f"Upload processing failed: {exc}") from exc

    song_id = meta["id"]
    if target == "queue":
        singer_name, owner = singer_for(who, singer)
        await enqueue(
            song_id=song_id,
            title=meta.get("title", "Custom Song"),
            channel=meta.get("channel", ""),
            duration=meta.get("duration"),
            singer=singer_name,
            owner=owner,
            thumbnail=meta.get("thumbnail"),
        )
    else:
        await worker.submit_library(song_id)

    return {
        "song_id": song_id,
        "title": meta.get("title"),
        "channel": meta.get("channel"),
        "duration": meta.get("duration"),
        "queued": target == "queue",
    }


@router.post("/link", status_code=201)
async def import_custom_link(req: LinkRequest, request: Request):
    who = auth.identify(request)
    _check_upload_allowed(who)

    try:
        meta = await asyncio.to_thread(
            custom_ingest.ingest_link,
            req.url,
            title=req.title,
            artist=req.artist,
            lyrics=req.lyrics_text,
        )
    except custom_ingest.IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        log.exception("Link import failed for %s", req.url)
        raise HTTPException(500, f"Link import failed: {exc}") from exc

    song_id = meta["id"]
    if req.target == "queue":
        singer_name, owner = singer_for(who, req.singer)
        await enqueue(
            song_id=song_id,
            title=meta.get("title", "Custom Song"),
            channel=meta.get("channel", ""),
            duration=meta.get("duration"),
            singer=singer_name,
            owner=owner,
            thumbnail=meta.get("thumbnail"),
        )
    else:
        await worker.submit_library(song_id)

    return {
        "song_id": song_id,
        "title": meta.get("title"),
        "channel": meta.get("channel"),
        "duration": meta.get("duration"),
        "queued": req.target == "queue",
    }
