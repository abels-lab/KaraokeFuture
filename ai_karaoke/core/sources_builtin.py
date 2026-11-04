"""The outside websites the karaoke uses out of the box, grouped by what they are for.

Order here is the default fallback order within a kind (core/sources_registry.py lets the host
change it). "setting" names an older Settings switch that already turns a source on or off: it
stays the one switch for that source. The URLs are shown on the Settings page for reference;
each service keeps its own request code (services/sources.py, lrclib.py, genius.py, ...).
"""
KINDS = [  # id, label, whether the order matters (it is the fallback order)
    ("songs", "Song search & download", True),
    ("synced", "Synced lyrics", True),
    ("lyrics", "Plain lyrics", True),
    ("chords", "Chord sheets (lyrics without the chords)", True),
    ("info", "Song info & timing", False),
]
CUSTOM_KINDS = ("songs", "lyrics")   # what the host's own links can be


def _b(sid, kind, name, url, note, setting=None):
    return {"id": sid, "kind": kind, "name": name, "url": url, "note": note, "setting": setting, "builtin": True}


BUILTINS = [
    _b("youtube", "songs", "YouTube", "https://www.youtube.com", "Main song source (yt-dlp)."),
    _b("soundcloud", "songs", "SoundCloud", "https://soundcloud.com",
       "Extra results, and a backup when a download fails (yt-dlp). Same switch as “Also search SoundCloud”.",
       "use_soundcloud"),
    _b("lrclib", "synced", "LRCLIB", "https://lrclib.net/api/search", "Timed lyrics matched to the song's length."),
    _b("syncedlyrics", "synced", "Musixmatch, NetEase & co.", "https://pypi.org/project/syncedlyrics/",
       "Timed lyrics through the syncedlyrics library."),
    _b("genius", "lyrics", "Genius", "https://genius.com",
       "Needs GENIUS_ACCESS_TOKEN on the laptop. Same switch as “Search Genius for lyrics”.", "use_genius"),
    _b("ultimate-guitar", "chords", "Ultimate Guitar", "https://www.ultimate-guitar.com",
       "Chord sheets with the chords removed. Also needs “Search guitar tab sites” on."),
    _b("amdm", "chords", "AmDm.ru", "https://amdm.ru", "Russian songs only. Also needs “Search guitar tab sites” on."),
    _b("usdb", "info", "USDB (UltraStar)", "https://usdb.animux.de/",
       "Ready-made singing timing and notes. Needs USDB_USER / USDB_PASSWORD on the laptop."),
    _b("itunes", "info", "iTunes Search", "https://itunes.apple.com/search", "Artist, clean title, genre and year."),
    _b("sponsorblock", "info", "SponsorBlock", "https://sponsor.ajay.app", "Skips spoken intros in YouTube videos."),
]
BY_ID = {b["id"]: b for b in BUILTINS}
