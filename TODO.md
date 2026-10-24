# KaraokeFuture - Backlog & Improvement Notes

> [!NOTE]
> Notes and backlog items recorded for future development sessions.

---

## 1. Video Playback Lags / Stuttering on Screen (`/screen` and `/tv`)

### Observations
- On some tracks or screens (especially external projector displays), video playback experiences stuttering, frame drops, or micro-lags.

### Likely Causes & Investigation Paths
1. **Sync Drift Correction Frequency (`static/stage.js` & `screen.js`)**:
   - In `stage.js`, `tick()` checks `drift = video.currentTime - t`.
   - If drift exceeds `0.05s`, it adjusts `playbackRate` (`0.95` or `1.05`) or performs `video.currentTime = t` seeks.
   - Frequent seeking or rate toggling at 4–25 Hz can cause the browser's hardware video decoder to drop keyframes and stutter.
   - *Fix ideas*: Add a deadband threshold (e.g. only adjust rate if drift > 0.12s, seek only if drift > 0.5s), and use smoother rate smoothing instead of abrupt seeks.
2. **Video Codec & Hardware Decoding (yt-dlp format selection)**:
   - YouTube downloads may grab AV1 or VP9 codecs at 1080p/720p, which can struggle with software decoding on secondary outputs or when GPU VRAM is shared.
   - Preferring H.264 (`mp4` / `avc1`) in `yt-dlp` download options ensures universal hardware decoding acceleration.
3. **Adaptive Canvas Sampling Overhead (`static/pulse.js`)**:
   - The adaptive theme grabs a $16 \times 16$ offscreen canvas from the `<video>` element on animation frames (`requestAnimationFrame`).
   - Extracting video frames onto canvas can force CPU-GPU readbacks in some browser environments.
   - *Fix ideas*: Throttle video color extraction to 5–10 Hz instead of every frame, or skip canvas extraction when video is paused or idle.
4. **Browser Hardware Acceleration & Display Refresh**:
   - Multi-monitor setups with mismatched refresh rates (e.g. 144Hz laptop screen + 60Hz projector) can cause Chromium vsync jitter.

---

## 2. Lyrics Timing Drift ("Some songs lyrics are a bit out")

### Observations
- For certain songs, word-fill timing feels slightly ahead or behind the vocal audio, or word transitions don't align perfectly with the vocals.

### Likely Causes & Investigation Paths
1. **Audio Alignment Offsets & Processing Latency**:
   - Latency between the audio output device (Bluetooth, HDMI, USB audio interface) and screen display creates a natural perceptual lag.
   - *Fix ideas*: Add a global "Audio / Lyrics delay" offset setting (e.g. `±50ms` to `±500ms`, step `25ms`) in Settings under `Screen & theme` or `Playback`.
2. **LRC vs Whisper Stable-TS Anchor Discrepancies**:
   - When using online synced LRC, some timestamps mark the start of the vocal line rather than word-level start.
   - When using Whisper alignment (`align_failure_threshold`, `anchor_max_stray`), fast speech or instrumental intros can cause stable-ts to stretch words (`hold_max`, `min_word`).
3. **Intro & Lead-in Timing**:
   - Songs with long spoken skits or SponsorBlock cut points can shift down-stream timestamps if offsets aren't normalized at 0:00.
4. **Per-Song Offset in Library (`/library`)**:
   - Allow the host to nudge lyrics timing for a specific song (e.g. `+0.3s` / `-0.2s` button in the song inspector).

---

## 3. Host-Authoritative Playback & Seamless Reload Resumption (COMPLETED)

### Objective
Make the host's playing screen (`/tv`) the authority for playback state so that during short connection blips, server restarts, or page reloads, the song does **not** restart from 0:00 and does **not** replay the 5-second intro countdown card.

### Implementation Status: COMPLETED
1. **Backend State Tracking (`core/queue_manager.py` & `routers/ws.py`)**:
   - `QueueManager` tracks `self.playback = {"time": 0.0, "duration": 0.0, "paused": True, "updated_at": 0.0}`.
   - `update_playback(self, uid, time_sec, duration, paused)` updates playback and persists throttled saves into `data/queue.json`.
   - `snapshot()` includes `"playback": self.playback` and attaches `playback` to `now_playing`.
   - `_save()` and `restore()` persist and restore `playback` alongside `current` and `played`.
   - Handshake message `{"type": "sync_playback", "uid": ..., "time": ..., "paused": ...}` is handled in `ws.py` for reconnects and authoritative time updates.

2. **Frontend Playback Authority & Session Storage (`static/tv.js`)**:
   - Every clock tick saves active playback timestamp to `sessionStorage` (`karaoke_active_playback`).
   - `loadSong(entry)` checks `sessionStorage` and server `entry.playback`. If resuming an in-progress song (`savedTime > 1.5s`):
     - Bypasses the pre-song countdown card (`IntroRun.stop()`) and notifies screens to hide intro card.
     - Seeks `inst.currentTime = voc.currentTime = savedTime` upon metadata readiness.
     - Calls `stage.seek(savedTime)` to immediately catch up lyrics and monitor video.
     - Resumes playback smoothly if it was playing.
   - On WebSocket reconnect, `tv.js` sends `sync_playback` handshake with current time and paused state.
   - Resilient audio network handling: `stalled` and `error` handlers on `inst` and `voc` re-buffer and resume from current timestamp instead of failing on temporary connection blips.

3. **Projector Screen Smooth Sync (`static/screen.js` & `stage.js`)**:
   - `onState()` initializes clock directly from server playback state without resetting to 0.
   - `onClock()` smoothly receives time jumps and applies `stage.seek(m.time)` without re-triggering intro cards or resetting video opacity.
   - `stage.seek(t)` queues pending seeks if video metadata is loading, snapping into sync as soon as metadata arrives.
