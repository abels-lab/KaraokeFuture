"""Tool definitions anyone in the chat may use (guests act on their own songs only, checked in
services/agent/tools_party.py). Gemini's schema dialect; llm_openai.py lower-cases the types."""
S, I, B, O, A = "STRING", "INTEGER", "BOOLEAN", "OBJECT", "ARRAY"


def tool(name: str, description: str, properties: dict | None = None, required: list | None = None) -> dict:
    return {"name": name, "description": description,
            "parameters": {"type": O, "properties": properties or {}, "required": required or []}}


def p(kind: str, description: str, **extra) -> dict:
    return {"type": kind, "description": description, **extra}


PARTY_TOOLS = [
    tool("get_party_status", "Now playing song, queued songs, active playlist and the current look."),
    tool("get_library_songs", "List songs already cached in the local library (to check what is downloaded).",
         {"limit": p(I, "Max songs to return (default 30)"),
          "search": p(S, "Optional filter on title or artist")}),
    tool("search_and_queue", "Search for a track and add it to the queue. A guest always sings it themselves; "
         "the host may name any singer.",
         {"query": p(S, "Song search query (e.g. 'Queen Bohemian Rhapsody')"),
          "singer": p(S, "Singer's name (host only; ignored for guests)"),
          "mode": p(S, "Optional singing game mode: 'party', 'score' or 'battle'")}, ["query"]),
    tool("queue_action", "Playback / queue action: skip (or next), play, pause, restart, remove (or delete), "
         "move, clear or promote. Guests may only skip, restart, pause or remove their own song.",
         {"action": p(S, "'skip', 'play', 'pause', 'restart', 'remove', 'move', 'clear' or 'promote'"),
          "uid": p(S, "Queue entry UID if known"),
          "song": p(S, "Song title / artist, or 'current' for the now playing song"),
          "index": p(I, "1-based position in the queue"),
          "offset": p(I, "For 'move': -1 up, 1 down"),
          "query": p(S, "Playlist song to promote"),
          "singer": p(S, "Singer when promoting a playlist song (host only)")}, ["action"]),
    tool("get_song_lyrics", "Current lyrics text of a song; the now playing (or next) song if none is named.",
         {"song_id": p(S, "Song ID in the cache (optional)"),
          "query": p(S, "Song title or artist (optional)")}),
    tool("list_playlists", "List the playlists (weekly hits, top hits, custom ones) with song counts."),
    tool("get_playlist", "Songs of one playlist.", {"playlist_id": p(S, "e.g. 'weekly_hits', 'top_hits'")},
         ["playlist_id"]),
    tool("record_improvement_request", "Log a wish you have no tool for (it goes to the developers' backlog).",
         {"topic": p(S, "Short title"), "description": p(S, "What was asked"),
          "safe_alternative": p(S, "Closest thing you could offer instead")}, ["topic", "description"]),
]
