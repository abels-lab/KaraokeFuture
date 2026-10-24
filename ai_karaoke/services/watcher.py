"""Lightweight static file watcher for live frontend reloading without server restarts."""
import asyncio
import logging
from pathlib import Path

import watchfiles

from config import STATIC_DIR
from core.hub import hub

log = logging.getLogger(__name__)


async def watch_static() -> None:
    """Watches static/ for changes and broadcasts live-reload events over WebSocket.
    - If only .css files were changed: broadcasts 'hot_css' to swap stylesheets instantly with zero audio drop.
    - If .html or .js files changed: broadcasts 'reload' to soft-refresh connected browser tabs.
    """
    log.info("Started static file watcher on %s", STATIC_DIR)
    try:
        async for changes in watchfiles.awatch(STATIC_DIR):
            css_only = all(Path(p).suffix.lower() == ".css" for _, p in changes)
            if css_only:
                log.info("CSS modified (%d file(s)), broadcasting hot_css", len(changes))
                await hub.broadcast({"type": "hot_css"})
            else:
                log.info("Static assets modified (%d file(s)), broadcasting reload", len(changes))
                await hub.broadcast({"type": "reload"})
    except asyncio.CancelledError:
        log.info("Static file watcher stopped")
    except Exception as e:
        log.warning("Static file watcher error: %s", e)
