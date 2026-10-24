# KaraokeFuture - Backlog & Improvement Notes

> [!NOTE]
> Notes and backlog items recorded for future development sessions. Nothing in this document is currently being implemented.

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

## 3. Host-Authoritative Playback & Seamless Reload Resumption

### Observations
- When the server restarts or the browser reloads mid-song, the song starts from `0:00` and replays the 5-second intro countdown card.

### Planned Architecture
1. **Host Screen as Source of Truth**:
   - The host screen (`/tv`) controls audio playback locally via `<audio id="inst">` and `<audio id="voc">`.
   - On short server reboots or Wi-Fi blips, the host audio continues playing seamlessly from browser RAM.
   - On reconnect, the host reports its active timestamp and song UID back to the server; the server adopts the host's state.
2. **Session Storage Restore on Page Reload**:
   - Save playback position (`uid`, `currentTime`, `paused`) to `sessionStorage` on every clock tick.
   - On fresh page load / F5, if the song was already in progress, immediately seek audio, skip the intro countdown, and resume without disruption.
