"""How the screens look and what they show around the lyrics, plus where the QR code points.
All but `qr_link` are `client` settings: the control panel, projector and phones restyle live
(static/look.js) the moment they change, no reload needed."""
from core.settings_kinds import NOW, _n, _s

LOOK_SPECS = [
    # ── Guest access ────────────────────────────────────────────────────────
    _s("qr_link", "access", "QR code opens", "auto", "choice",
       "Automatic: the Tailscale Funnel address when Funnel points at this app (phones join from mobile "
       "data, over HTTPS), else the home Wi-Fi address. Start with start-karaoke.bat to switch Funnel on.",
       NOW, choices=[["auto", "Automatic (Funnel if on)"], ["lan", "Home Wi-Fi address only"]]),
    # ── Screen & theme ──────────────────────────────────────────────────────
    _s("title_text", "look", "Party title", "Karaoke Night", "text",
       "The big title on the control panel, projector and phones.", NOW, client=True, max_len=40),
    _s("theme", "look", "Theme", "theater", "choice",
       "Theater: velvet curtains. Club: neon dance floor. Rock: stage fire. Adaptive (experimental): "
       "ambient stage lighting and accents adapt dynamically to the music video colors and pulse to the beat.", NOW, client=True,
       choices=[["theater", "Theater"], ["club", "Club"], ["rock", "Rock"], ["adaptive", "Adaptive (experimental)"]]),
    _s("accent", "look", "Colour preset", "theme", "choice",
       "Highlight colour for titles, buttons and sung words. “Theme colour” uses the theme's own.",
       NOW, client=True, choices=[["theme", "Theme colour"], ["gold", "Gold"], ["neon", "Neon pink"],
                                  ["ice", "Ice blue"], ["lime", "Lime"], ["fire", "Fire red"], ["silver", "Silver"]]),
    _s("lyrics_position", "look", "Lyrics position", "bottom", "choice",
       "Where the lyrics sit on the projector (and the control panel's preview).", NOW, client=True,
       choices=[["top", "Top"], ["middle", "Middle"], ["bottom", "Bottom"]]),
    _s("lyrics_mode", "look", "Lyrics", "full", "choice",
       "Highlighted: words fill as they're sung. Plain: just the text, no filling. Off: no lyrics on any "
       "screen (for singers who know the song). The control panel's 📝 button switches it too.", NOW, client=True,
       choices=[["full", "Highlighted"], ["plain", "Plain text"], ["off", "Off"]]),
    _s("show_video", "look", "Show music videos", True, "bool",
       "Off: plain background behind the lyrics on every screen (videos still download, see Songs & downloads). "
       "The control panel's 🎬 button switches it too.", NOW, client=True),
    _n("info_card_seconds", "look", "Song info card", 6, 0, 20, 1, "s",
       "After a song starts, a small card shows who sings, the song and who's next. 0 = never.", NOW, True),
    _s("info_card_middle", "look", "Song info card mid-song", True, "bool",
       "Show the same card once more halfway through the song.", NOW, client=True),
    _s("loading_jokes", "look", "Jokes while loading", True, "bool",
       "While the next song is being prepared, the screens pass the time with karaoke memes.", NOW, client=True),
]
