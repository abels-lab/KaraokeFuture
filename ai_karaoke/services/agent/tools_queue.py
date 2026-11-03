"""queue_action for the DJ Co-Pilot, with the queue API's rules: the host may do anything, a
guest only skips, pauses, restarts, removes or moves their own song (core/auth.py may_manage)."""
from typing import Any

from core import auth
from core.queue_manager import queue

NOT_YOURS = "That's someone else's song: only they or the host can change it"
NOW_WORDS = ("current", "now", "now_playing", "this", "playing")


def _target(args: dict) -> dict | None:
    """The queue entry (or the now playing one) the request points at: uid, 1-based index or title."""
    if args.get("uid"):
        return queue.find_any(str(args["uid"]))
    if args.get("index") is not None:
        try:
            index = int(args["index"])
        except (TypeError, ValueError):
            return None
        return queue.entries[index - 1] if 1 <= index <= len(queue.entries) else None
    wanted = str(args.get("song") or args.get("query") or args.get("title") or "").lower().strip()
    if not wanted or wanted in NOW_WORDS:
        return queue.current or (queue.entries[0] if queue.entries and not wanted else None)
    for entry in [*queue.entries, *([queue.current] if queue.current else [])]:
        if wanted in entry.get("title", "").lower() or wanted in entry.get("channel", "").lower():
            return entry
    return None


async def queue_action(who: auth.Who, args: dict) -> dict[str, Any]:
    action = str(args.get("action") or "").lower().strip()
    current = queue.current
    if action in ("skip", "next", "pause", "restart", "play"):
        if current is None:
            if not who.admin:
                return {"error": "Nothing is playing; only the host can start the next song"}
            started = await queue.next()
            return {"status": "started", "now_playing": started["title"]} if started else \
                {"error": "No ready songs in the queue"}
        if not auth.may_manage(who, current):
            return {"error": NOT_YOURS}
        if action in ("skip", "next"):
            started = await queue.next()
            return {"status": "skipped", "now_playing": started["title"] if started else None}
        await queue.control(action)
        return {"status": action}
    if action in ("remove", "delete"):
        entry = _target(args)
        if entry is None:
            return {"error": "Could not find that song in the queue"}
        if not auth.may_manage(who, entry):
            return {"error": NOT_YOURS}
        if current and current.get("uid") == entry["uid"]:
            await queue.next()
            return {"status": "removed", "target": entry.get("title"), "message": "Removed the playing song"}
        ok = await queue.remove(entry["uid"])
        return {"status": "removed" if ok else "not_found", "target": entry.get("title"), "uid": entry["uid"]}
    if action == "move":
        entry = _target(args)
        try:
            offset = int(args.get("offset") or 0)
        except (TypeError, ValueError):
            offset = 0
        if entry is None or not offset:
            return {"error": "Say which queued song to move, and up or down"}
        if who.admin:
            ok = await queue.move(entry["uid"], offset)
        elif auth.owns(who, entry):   # a guest swaps places among their own songs only
            ok = await queue.move_own(entry["uid"], who.guest_id, "up" if offset < 0 else "down")
        else:
            return {"error": NOT_YOURS}
        return {"status": "moved" if ok else "not_moved", "uid": entry["uid"]}
    if action in ("clear", "delete_all", "remove_all"):
        if not who.admin:
            return {"error": auth.HOST_ONLY}
        queue.entries.clear()
        await queue.broadcast_state()
        return {"status": "cleared"}
    if action == "promote":
        target = args.get("uid") or args.get("query") or args.get("song")
        if target is None:
            return {"error": "Which playlist song?"}
        if who.admin:
            entry = await queue.promote_playlist_song(target, singer=str(args.get("singer") or "Host"))
        elif who.guest_id is not None:
            entry = await queue.promote_playlist_song(target, singer=who.name, owner=who.guest_id)
        else:
            return {"error": "Log in with your name on the remote page first"}
        return {"status": "promoted", "entry": entry} if entry else {"error": "Not in the active playlist"}
    return {"error": f"Unsupported action: {action}"}
