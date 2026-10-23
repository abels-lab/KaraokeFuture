"""Every setting the Settings page can change: plain-language label and help, default (from
config.py, so environment variables still set the defaults), limits, and when it takes effect.
`client` settings are also sent to the browser pages (singing game, playback)."""
import config as c

GROUPS = [
    ("library", "Songs & downloads"), ("warmup", "Popular songs warm-up"), ("separation", "Vocal separation"), ("lyrics", "Lyrics"),
    ("timing", "Vocal detection & word timing"), ("melody", "Melody"),
    ("game", "Singing game"), ("playback", "Playback"),
]
NOW, NEXT, PROCESSING = "immediately", "next song", "next processed song"
# Settings that no longer exist; old settings.json files may still have them (silently dropped).
# allow_remote_settings: replaced by the host PIN (core/auth.py).
RETIRED = {"allow_remote_settings"}


def _s(key, group, label, default, kind, help_, applies=PROCESSING, client=False, **extra):
    return {"key": key, "group": group, "label": label, "default": default, "kind": kind,
            "help": help_, "applies": applies, "client": client, **extra}


def _n(key, group, label, default, lo, hi, step, unit, help_, applies=PROCESSING, client=False):
    return _s(key, group, label, default, "number", help_, applies, client, min=lo, max=hi, step=step, unit=unit)


SPECS = [
    # ── Songs & downloads ───────────────────────────────────────────────────
    _n("cache_limit_gb", "library", "Cache size limit", c.CACHE_LIMIT_BYTES / 1024**3, 1, 100, 1, "GB",
       "Disk space for processed songs. When it fills up, the songs played longest ago are deleted first.", NOW),
    _n("max_duration_min", "library", "Longest song allowed", c.MAX_DURATION_SEC / 60, 2, 30, 1, "min",
       "Longer results are hidden from search and refused (hour-long loops, albums; they fill the cache).", NOW),
    _n("min_duration_sec", "library", "Shortest song allowed", c.MIN_DURATION_SEC, 0, 180, 10, "s",
       "Shorter results (clips, previews, intros) are hidden from search and refused.", NOW),
    _n("search_results", "library", "Search results", c.SEARCH_RESULTS, 3, 15, 1, "",
       "How many songs a guest sees per search, after duplicates and non-songs are removed.", NOW),
    _s("use_soundcloud", "library", "Also search SoundCloud", True, "bool",
       "Adds SoundCloud songs to the results and uses them as a backup when a YouTube download fails.", NOW),
    _n("search_check_seconds", "library", "Search check time", 3.5, 0, 10, 0.5, "s",
       "Results are opened to make sure they really download; broken ones are swapped or hidden. "
       "Slower checks are skipped after this long (0 = don't check).", NOW),
    _n("max_queue", "library", "Queue length limit", c.MAX_QUEUE_LENGTH, 5, 200, 5, "songs",
       "Guests can't add more songs once the queue is this long.", NOW),
    _s("download_video", "library", "Download music videos", c.DOWNLOAD_VIDEO, "bool",
       "Play the song's video behind the lyrics. Adds roughly 30–60 MB per song."),
    _s("video_max_height", "library", "Video quality", c.VIDEO_MAX_HEIGHT, "choice",
       "Higher looks sharper on a big screen but downloads more.", choices=[[360, "360p"], [480, "480p"],
       [720, "720p (recommended)"], [1080, "1080p"]]),
    # ── Popular songs warm-up ───────────────────────────────────────────────
    _s("warm_enabled", "warmup", "Prepare popular songs in the background", True, "bool",
       "While nobody is waiting, karaoke classics are processed ahead so they start instantly. "
       "Guests' songs always go first.", NOW),
    _n("warm_count", "warmup", "Songs per rotation", 20, 0, 60, 1, "songs",
       "How many classics to keep ready. The list rotates every week.", NOW),
    _n("warm_interval_h", "warmup", "Check every", 12, 1, 168, 1, "hours",
       "How often the warm-up looks for classics that still need preparing.", NOW),
    _n("warm_budget_pct", "warmup", "Cache share for warm-up", 40, 5, 90, 5, "%",
       "Most of the cache the prepared classics may use. Unplayed ones from an old rotation are deleted first.", NOW),
    # ── Vocal separation ────────────────────────────────────────────────────
    _s("separator_model", "separation", "Separation model", c.SEPARATOR_MODEL, "choice",
       "The AI model that removes the vocals. Use Rebuild in the library to redo existing songs.",
       choices=[["model_bs_roformer_ep_317_sdr_12.9755.ckpt", "BS-Roformer (best, recommended)"],
                ["UVR-MDX-NET-Inst_HQ_3.onnx", "MDX-Net HQ3 (faster, lighter)"],
                ["htdemucs_ft.yaml", "Demucs fine-tuned (4 stems)"]]),
    _n("separator_overlap", "separation", "Separation overlap", c.SEPARATOR_OVERLAP, 1, 8, 1, "",
       "How many times each part of the song is processed. Higher is slightly cleaner but much slower."),
    _s("separator_fp16", "separation", "Fast GPU math (fp16)", c.SEPARATOR_FP16, "bool",
       "Roughly halves separation time on RTX cards with no audible difference."),
    _s("keep_original", "separation", "Keep the original audio", c.KEEP_ORIGINAL, "bool",
       "Keep original.wav after separation (about 40 MB per song). Only useful for debugging."),
    # ── Lyrics ──────────────────────────────────────────────────────────────
    _s("lyrics_aligner", "lyrics", "Lyrics timing engine", c.LYRICS_ALIGNER, "choice",
       "Times known lyrics word by word. MMS doesn't lose its place on repetitive songs.",
       choices=[["mms", "Meta MMS (recommended)"], ["stable-ts", "Whisper / stable-ts"]]),
    _s("whisper_model", "lyrics", "Speech recognition model", c.WHISPER_MODEL, "choice",
       "Used when no lyrics are found online. Turbo was the most accurate and fastest in our tests.",
       choices=[["large-v3-turbo", "large-v3-turbo (recommended)"], ["large-v3", "large-v3 (slower)"],
                ["medium", "medium"], ["small", "small (fastest, least accurate)"]]),
    _s("whisper_compute", "lyrics", "Speech model precision", c.WHISPER_COMPUTE_TYPE, "choice",
       "large-v3 in float16 nearly fills 6 GB of VRAM — use int8 with it.",
       choices=[["float16", "float16 (recommended)"], ["int8_float16", "int8 (less VRAM)"]]),
    _s("condition_on_previous_text", "lyrics", "Recognition uses previous text", c.CONDITION_ON_PREVIOUS_TEXT,
       "bool", "On made sung lyrics worse in our tests (mishearings snowball, lines repeat). Keep off."),
    _s("use_genius", "lyrics", "Search Genius for lyrics", True, "bool",
       "Last online source before speech recognition. Needs GENIUS_ACCESS_TOKEN on the laptop."),
    _n("min_lyric_lines", "lyrics", "Minimum lyric lines", c.MIN_LYRIC_LINES, 1, 20, 1, "lines",
       "Online lyrics shorter than this are treated as not found."),
    _n("lrclib_duration_diff", "lyrics", "Song-version match tolerance", 3.0, 1, 15, 0.5, "s",
       "How close an LRCLIB upload's length must be to ours to count as the same version."),
    _n("anchor_max_stray", "lyrics", "Line timing tolerance", 1.5, 0.5, 5, 0.1, "s",
       "A line further than this from its LRC timestamp is timed again in its own window."),
    _n("align_failure_threshold", "lyrics", "Alignment give-up point", c.ALIGN_FAILURE_THRESHOLD, 0.1, 0.9, 0.05, "",
       "Whisper alignment gives up when this share of words gets no duration."),
    _n("max_chars_per_sec", "lyrics", "Hallucination filter", c.MAX_CHARS_PER_SEC, 15, 80, 1, "chars/s",
       "Recognized lines sung faster than this are dropped as invented."),
    # ── Vocal detection & word timing ───────────────────────────────────────
    _n("vocal_lenient_db", "timing", "Instrumental-break sensitivity", 28.0, 10, 50, 1, "dB",
       "How far below the singer's loud parts still counts as vocals. Higher = fewer 'Instrumental' hints."),
    _n("vocal_strict_db", "timing", "'Sung without lyrics' sensitivity", 10.0, 4, 30, 1, "dB",
       "How close to the singer's loud parts counts as clear singing for the ⚠ library warning."),
    _n("hold_pad", "timing", "Held-note allowance", 1.2, 0, 4, 0.1, "s",
       "Singers hold the last note past a line's timing; this much isn't flagged as missing lyrics."),
    _n("min_unmatched", "timing", "Shortest missing-lyrics stretch", 2.5, 0.5, 10, 0.5, "s",
       "Sung stretches without lyrics shorter than this are not flagged."),
    _n("min_word", "timing", "Shortest word on screen", 0.15, 0.05, 0.5, 0.01, "s",
       "Words timed shorter than this are lengthened so they fill instead of flashing."),
    _n("hold_max", "timing", "Longest held word", 4.0, 0.5, 10, 0.5, "s",
       "How long a word may be stretched over a held note."),
    # ── Melody ──────────────────────────────────────────────────────────────
    _n("melody_voiced", "melody", "Pitch confidence", 0.4, 0.1, 0.9, 0.05, "",
       "How clear the original singer's pitch must be to become a note. Lower = more notes on shouty songs."),
    _n("melody_min_note", "melody", "Shortest note", 0.1, 0.05, 0.5, 0.01, "s", "Shorter pitch blips are not notes."),
    # ── Singing game (browser) ──────────────────────────────────────────────
    _n("game_gate_db", "game", "Microphone noise gate", -48, -80, -20, 1, "dB",
       "Quieter mic sound is ignored. Raise it if the room is loud.", NEXT, True),
    _n("game_perfect", "game", "Perfect pitch window", 0.5, 0.1, 1.5, 0.05, "semitones",
       "Within this many semitones of the note scores full points.", NEXT, True),
    _n("game_miss", "game", "Pitch miss point", 2.0, 1, 4, 0.1, "semitones",
       "This far off (or more) scores nothing. Must be larger than the perfect window.", NEXT, True),
    _n("game_results_seconds", "game", "Results screen time", 12, 3, 60, 1, "s",
       "How long the results card stays up before the next song starts.", NEXT, True),
    _n("party_min_percent", "game", "Party mode lowest score", 52, 0, 90, 1, "%",
       "Party mode never shows a lower 'good vocalist' score than this.", NEXT, True),
    # ── Playback ────────────────────────────────────────────────────────────
    _n("guide_default", "playback", "Default guide-vocal volume", 20, 0, 100, 5, "%",
       "Starting volume of the original singer, until the slider is moved on this laptop. "
       "A singer's own choice on their phone wins for their song.", NOW, True),
]
