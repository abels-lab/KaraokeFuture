"""The browser-side half of the settings registry: singing game, playback, and the show around
each song (intro card, Battle / Duet). All are `client` settings: the control panel and the
projector reload them live (common.js Settings), so nothing here needs a restart."""
from core.settings_kinds import NEXT, NOW, _n, _s

SHOW_SPECS = [
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
    # ── Song intro & Battle / Duet ──────────────────────────────────────────
    _n("intro_seconds", "show", "Intro countdown", 5, 0, 15, 1, "s",
       "Before each song a full-screen card shows who sings what, counting down to the start. "
       "The host can skip it with a click or Enter. 0 = no card, the song starts at once.", NEXT, True),
    _s("p2_detect", "show", "Detect a second singer", True, "bool",
       "In Battle and Score mode with two microphones: when somebody starts singing into mic 2, "
       "Player 2 joins the game on its own (no phone needed).", NOW, client=True),
    _n("p2_voiced_seconds", "show", "Player 2: singing needed", 1.5, 0.5, 3, 0.1, "s",
       "How much clear singing on mic 2 (within the window below) makes Player 2 join.", NOW, True),
    _n("p2_window_seconds", "show", "Player 2: listening window", 3, 1, 6, 0.5, "s",
       "The stretch of time in which that much singing has to happen.", NOW, True),
    _n("p2_min_db", "show", "Player 2: loudness needed", -45, -70, -20, 1, "dB",
       "Mic 2 sound quieter than this never counts, however clear its pitch.", NOW, True),
    _n("p2_margin_db", "show", "Player 2: louder than mic 1 by", 6, 0, 20, 1, "dB",
       "Speakers and singer 1 reach mic 2 too. Mic 2 must be this much louder than mic 1 "
       "(or sing a clearly different note) to count as a second singer.", NOW, True),
    # ── Playback ────────────────────────────────────────────────────────────
    _s("skip_intro", "playback", "Skip non-music intros", True, "bool",
       "When a music video has spoken dialogue or an intro skit before the music, jump straight to the song start. "
       "To listen anyway, just drag the slider back to 0:00.", NOW, client=True),
    _n("guide_default", "playback", "Default guide-vocal volume", 20, 0, 100, 5, "%",
       "Starting volume of the original singer, until the slider is moved on this laptop. "
       "A singer's own choice on their phone wins for their song.", NOW, True),
    _s("guest_scrubbing", "playback", "Allow guests to scrub timeline", False, "bool",
       "When off, only the host can scrub and jump within a playing song. "
       "Disabled by default so guests cannot accidentally scrub or create delay.", NOW, client=True),
]
