"""Tool definitions only the host may use (refused for guests in services/agent/registry.py), and
set_style, which guests may use when the host allows it (agent_guest_style)."""
from services.agent.schema_party import A, B, O, S, p, tool

_BUTTON = {"type": O, "description": "For 'add_button': id, label, icon (emoji), target ('display'|'nav'|"
           "'transport'), action ('sfx'|'control'|'setting'|'queue_search'|'toast'), value",
           "properties": {k: {"type": S} for k in ("id", "label", "icon", "target", "action", "value")},
           "required": ["id", "label", "action"]}

HOST_TOOLS = [
    tool("customize_control_panel", "Control Panel layout: reorder its 3 columns, hide/show panels and buttons, "
         "add/remove custom buttons, Guide Vocal slider width and thumb. Live, no reload. (Colours, fonts and "
         "effects are set_style.)",
         {"action": p(S, "'update' (default), 'add_button', 'remove_button' or 'reset'"),
          "column_order": p(A, "Order of 'left', 'center', 'right'", items={"type": S}),
          "hide_elements": p(A, "DOM IDs to hide (e.g. 'qr-card', 'nav-panel', 'btn-restart')", items={"type": S}),
          "show_elements": p(A, "DOM IDs to show again", items={"type": S}),
          "guide_width": p(S, "Guide Vocal slider width, e.g. '25%'"),
          "guide_thumb": p(S, "Slider thumb: 'default', 'smiley' or one emoji"),
          "button": _BUTTON,
          "button_id": p(S, "Button to remove for 'remove_button'")}),
    tool("change_setting", "Change an app setting by key (e.g. theme, accent, show_video, lyrics_mode, "
         "lyrics_position, title_text, screen_chat_enabled, agent_drawer_position). Style tweaks: set_style.",
         {"key": p(S, "Setting key"), "value": p(S, "New value (text, true/false or a number)")}, ["key", "value"]),
    tool("create_playlist", "Create a custom playlist.",
         {"name": p(S, "Playlist name"), "songs": p(A, "'Artist - Title' strings", items={"type": S}),
          "description": p(S, "Optional description"), "playlist_id": p(S, "Optional ID")}, ["name", "songs"]),
    tool("update_playlist", "Rename a custom playlist or set / add / remove its songs.",
         {"playlist_id": p(S, "Playlist ID"), "name": p(S, "New name"), "description": p(S, "New description"),
          "songs": p(A, "Song queries", items={"type": S}),
          "action": p(S, "'set' (default), 'add_songs' or 'remove_songs'")}, ["playlist_id"]),
    tool("delete_playlist", "Delete a custom playlist.", {"playlist_id": p(S, "Playlist ID")}, ["playlist_id"]),
    tool("play_playlist", "Play a playlist as Auto-DJ filler: singers' songs always go first.",
         {"playlist_id": p(S, "Playlist ID"), "shuffle": p(B, "Shuffle (default false)"),
          "loop": p(B, "Start over at the end (default false)")}, ["playlist_id"]),
    tool("stop_playlist", "Stop the Auto-DJ playlist."),
    tool("edit_song_lyrics", "Fix a song's lyrics: old_snippet → new_snippet, full text, or reset=true for the "
         "automatic ones. The now playing (or next) song if none is named.",
         {"song_id": p(S, "Song ID (optional)"), "query": p(S, "Song title or artist (optional)"),
          "old_snippet": p(S, "Exact text to replace"), "new_snippet": p(S, "Replacement"),
          "text": p(S, "Full new lyrics"), "reset": p(B, "Back to the automatic lyrics")}),
]

STYLE_TOOL = tool(
    "set_style", "Restyle every screen live (control panel, projector, phones). Pass only what changes. "
    "For anything the options can't do, custom_css: plain CSS, no url(), @import, comments, backslashes or '<'. "
    "reset=true restores the theme's own look.",
    {"theme": p(S, "'theater', 'club', 'rock' or 'adaptive' (pulses with the video)"),
     "accent": p(S, "Preset: 'theme', 'gold', 'neon', 'ice', 'lime', 'fire', 'silver'"),
     "accent_hex": p(S, "Any highlight colour as #rrggbb ('' = use the preset)"),
     "font": p(S, "'theme', 'rounded', 'condensed', 'serif', 'mono' or 'handwritten'"),
     "title_effect": p(S, "'none', 'glow', 'neon', 'rainbow', 'bounce' or 'wobble'"),
     "background": p(S, "'theme', 'aurora', 'disco', 'stars', 'scanlines' or 'dark'"),
     "glow": p("INTEGER", "Neon glow 0-100"),
     "corners": p("INTEGER", "Corner rounding 0-200 (100 = normal)"),
     "pulse": p("INTEGER", "Beat pulse 0-100"),
     "title_text": p(S, "Party title (max 40 characters)"),
     "custom_css": p(S, "Extra CSS for every screen, replaces the previous ('' clears it)"),
     "reset": p(B, "Clear all custom style first")})
