"""Which DJ Co-Pilot tools a person may use, and running them as that person.

The model only ever sees the tools the asker may use (tools_for), and execute_tool checks again,
so neither a guest's message nor text a tool brings back (a song title, lyrics) can make it act
beyond the asker's rights: guests act on their own songs, the host on everything, and nobody's
chat reaches files or code."""
import logging
from typing import Any

from core import auth, settings
from services.agent import tools_host, tools_lyrics, tools_party, tools_queue, tools_style
from services.agent.schema_host import HOST_TOOLS, STYLE_TOOL
from services.agent.schema_party import PARTY_TOOLS

log = logging.getLogger(__name__)

PARTY = {
    "get_party_status": tools_party.party_status,
    "get_library_songs": tools_party.library_songs,
    "search_and_queue": tools_party.search_and_queue,
    "queue_action": tools_queue.queue_action,
    "get_song_lyrics": tools_lyrics.get_lyrics,
    "list_playlists": tools_party.list_playlists,
    "get_playlist": tools_party.get_playlist,
    "record_improvement_request": tools_party.improvement_request,
}
HOST = {
    "customize_control_panel": tools_host.customize_control_panel,
    "change_setting": tools_host.change_setting,
    "edit_song_lyrics": tools_lyrics.edit_lyrics,
    **{name: (lambda n: lambda who, args: tools_host.playlist_tool(n, args))(name)
       for name in ("create_playlist", "update_playlist", "delete_playlist", "play_playlist", "stop_playlist")},
}


def may_style(who: auth.Who) -> bool:
    return who.admin or (who.guest_id is not None and settings.get("agent_guest_style"))


def tools_for(who: auth.Who) -> list[dict]:
    """The tool definitions to offer the model for this person."""
    return [*PARTY_TOOLS, *([STYLE_TOOL] if may_style(who) else []), *(HOST_TOOLS if who.admin else [])]


async def execute_tool(name: str, args: dict[str, Any], who: auth.Who) -> dict[str, Any]:
    log.info("Co-Pilot tool %s for %s: %s", name, who.name or ("host" if who.admin else "guest"), args)
    args = args if isinstance(args, dict) else {}
    if name == "set_style":
        if not may_style(who):
            return {"error": "Only the host can restyle the party (or allow guests in Settings → AI Co-Pilot)"}
        handler = tools_style.set_style
    elif name in HOST:
        if not who.admin:
            return {"error": auth.HOST_ONLY}
        handler = HOST[name]
    elif name in PARTY:
        handler = PARTY[name]
    else:
        return {"error": f"Unknown tool: {name}"}
    try:
        result = handler(who, args)
        return await result if hasattr(result, "__await__") else result
    except Exception as exc:   # a tool bug must not end the chat turn
        log.exception("Co-Pilot tool %s failed", name)
        return {"error": f"{name} failed: {exc}"}
