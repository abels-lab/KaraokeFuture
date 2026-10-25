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


---

## 4. Enhanced Queue Navigation & Control Panel Usability (COMPLETED)

### Objective
Make the queue navigation intuitive for users and hosts:
1. Next song and previous song buttons display real song titles instead of generic icons.
2. Full history of played songs is retained, allowing backwards navigation if a song was mistakenly skipped.
3. Host can view the whole queue, inspect all previously played songs, and select any past song to replay immediately.
4. "Back to queue" button on already played songs allows re-adding them to the active lineup.
5. Drag handle on each waiting song enables fluid reordering to any position without relying on step-by-step up/down buttons.

### Implementation Summary
- **Backend (`core/queue_manager.py`, `core/queue_personal.py`, `routers/queue.py`, `routers/api.py`, `routers/ws.py`)**:
  - `self.played: list[dict]` keeps track of all finished and skipped songs with full metadata.
  - `previous()`: Pops the last played song from `self.played`, places the currently active song back at index 0 of `self.entries`, and begins playback immediately.
  - `play_played(uid)`: Allows host to select any historical song to play now.
  - `requeue(uid)`: Returns an already played song into the upcoming queue.
  - `move_to(uid, target_index)`: Supports arbitrary index relocation via drag-and-drop.
  - Added REST endpoints: `POST /api/queue/previous`, `POST /api/queue/{uid}/play`, `POST /api/queue/{uid}/requeue`, `POST /api/player/previous`.
  - Added WebSocket control action `previous` and extended `next`/`skip`.
- **Frontend Control Panel (`static/tv.html`, `static/tv-side.js`, `static/common.js`, `static/tv.js`, `static/theme.css`)**:
  - Replaced icon-only skip button with Previous and Next buttons that display actual song titles (`Prev: [Title]`, `Next: [Title]`), with tooltips and disabled states when history or queue is empty. Keyboard shortcuts: `P` (previous) and `N` (next).
  - Sidebar equipped with 3 tabs: **📋 Up next**, **⏮ Played**, and **📑 All** (Whole Queue timeline).
  - Drag handle (`⠿`) on each waiting queue row for desktop HTML5 drag & drop with amber drop indicator lines (`.drop-target-above`, `.drop-target-below`).
  - Dedicated `playedRow` component with "▶ Play now", "↩ Queue" (back to queue), and "✕" (delete from history).
- **Mobile Remote (`static/remote.html`, `static/remote.js`, `static/my-queue.js`)**:
  - Added "Prev: [Title]" and "Next: [Title]" controls in the transport area.
  - Added "Played" sub-filter pill in the Queue tab to view past songs and re-queue them.

---

## 5. Control Panel (`/tv`) UI Weak Points & Guest Interaction Vulnerabilities

### Objective
Audit the host control panel (`/tv`), identify fragile UI/layout points under real-world party conditions, and address potential disruptions caused by manual guest setups and phone actions (`/remote`).

---

### A. Control Panel (`/tv`) UI Weak Points & Layout Flaws

1. **Transport Bar Wrapping on Compact / Scaled Laptop Displays**:
   - **Issue**: In `static/tv.html`, the playback control bar (`footer.panel`) contains Previous & Next buttons with text labels (`max-w-[210px]`), 5 circular transport buttons, 2 screen toggles, and the Guide Vocal slider (`w-28 xl:w-36` + labels).
   - **Vulnerability**: On standard karaoke laptops (1366x768 or 1080p with 125%–150% Windows display scaling), the effective viewport width for the stage column is only ~550px–650px. The controls wrap into 2 or 3 chaotic rows, pushing the video monitor up or clipping the time scrubber.
   - **Recommended Fix**:
     - Implement responsive media queries in `theme.css`: collapse `btn-prev` and `btn-next` to icon-only (or truncated max-w 120px) under `1200px` screen width.
     - Stack or condense the Guide slider into a compact popover or vertical mini-fader on smaller viewports.

2. **Idle Screen Overflow with Multiple Loading Tracks**:
   - **Issue**: On the idle screen (`#idle`), `#loading` (loading card list from `loading.js`) renders directly underneath the large microphone image (`w-80`) and the large QR code box (`h-52 w-52`).
   - **Vulnerability**: When 3 or more songs are queued and being processed concurrently, the total height exceeds standard screen viewports, introducing a vertical scrollbar on what is meant to be a clean TV display, and pushing the QR code off the top.
   - **Recommended Fix**:
     - Scale down `#idle-mic` and `#qr-big` when songs are loading (`#idle.has-loading` styling).
     - Set a max-height on `#loading` with clean internal scrolling or a carousel/paged view of pending downloads.

3. **DJ Co-Pilot Drawer / Floating Button Occlusion**:
   - **Issue**: The `✨ DJ Co-Pilot` toggle button is fixed at `bottom-6 right-6` (or `left-6`). When on the right, it directly overlaps the bottom sidebar links (`🎤 Microphones`, `📽 Open projector screen`, `📚 Library`, `⚙️ Settings`).
   - **Vulnerability**: When the chat drawer opens, it completely blocks the host from viewing either the active playback monitor or the queue and transport controls.
   - **Recommended Fix**:
     - Implement an integrated "Split Screen / Docked Column" mode (`agent_layout_mode: split`) that resizes `#tv-layout` to a 3-column grid (`Stage | Co-Pilot | Queue`), shrinking the video instead of floating above it.
     - Reposition the toggle button above the sidebar footer actions (e.g. `bottom-20`) to prevent blocking the projector or settings buttons.

4. **Monitor Lyric Text Overflow on Long Lines**:
   - **Issue**: Lyrics inside `#monitor` use `text-[clamp(1.6rem,3vw,3rem)]` with `flex-col justify-end`.
   - **Vulnerability**: Fast rap verses or multi-clause lyrics (15+ words in a line) wrap onto 3–4 lines on compact laptop monitors, colliding with `#countdown` or pushing the active line outside the monitor frame.
   - **Recommended Fix**:
     - Add dynamic font size stepping in `static/stage.js`: if a line exceeds 45 characters, dynamically drop the font size by 20–30% (`text-sm`/`text-base` fallback) to prevent overflow.

---

### B. Potential Troubles Caused by Manual Guest Setups & Actions (`/remote`)

1. **Unthrottled Queue Flooding (Spamming Songs)**:
   - **Issue**: Any guest on mobile (`/remote`) can search and queue songs repeatedly up to the global `max_queue` limit (default: 50).
   - **Vulnerability**: A single enthusiastic or trolling guest can queue 15–20 songs in two minutes. This consumes GPU/CPU stem separation resources for hours and starves other singers from getting their turn.
   - **Recommended Fix**:
     - Add a **"Fair Queueing"** rule in `core/queue_manager.py`: enforce a per-guest active limit (e.g., max 2 unplayed songs per guest session).
     - Add a configurable cooldown timer (e.g., 60 seconds between song submissions per guest).

2. **Mid-Song Guide Vocal & Game Mode Hijacking**:
   - **Issue**: When a guest is on `/remote`, they can modify their song's guide-vocal percentage (0% to 100%) and mode ("party", "score", "battle").
   - **Vulnerability**: In `static/tv.js` lines 62–67, any update to `np.guide` received from WebSocket immediately sets `Guide.forEntry(current)`. If the guest drags their phone slider to 0% (muting vocals) or 100% (drowning out the singer) while the song is playing, it overrides the host laptop's physical slider live!
   - **Recommended Fix**:
     - Add a **Host Override Lock**: once the host moves the physical guide slider on `/tv`, flag the song as `host_guide_locked = true` for the rest of that track, ignoring further remote slider inputs from the guest.

3. **Singer Name Impersonation & Clashing**:
   - **Issue**: `/remote` has an open text field for singer names with no reservation or unique validation.
   - **Vulnerability**: A guest can enter "Host", "Everyone", or the exact name of another guest at the party. This allows guests to impersonate others, clutter the queue history, or bypass host identity expectations.
   - **Recommended Fix**:
     - Disallow the reserved name "Host" on `/remote` unless authorized by host PIN.
     - Append subtle guest session IDs or unique color avatars (e.g. `Alice #2`) if two phones use the exact same name.

4. **Unauthorized Battle / Duet Hijacking**:
   - **Issue**: If a song is queued in `battle` mode, any guest on the remote can tap "Join" (`/api/queue/{uid}/join`) to become the partner.
   - **Vulnerability**: An uninvited guest can tap "Join" and force themselves into someone else's duet or battle without the original singer's knowledge or approval.
   - **Recommended Fix**:
     - Add an approval request handshake: when a guest taps "Join", singer 1 or the host must tap "Accept" on their screen, or singer 1 can specify a partner by name when queueing.

5. **Audio Autoplay Lockout on Browser Start (`#unlock`)**:
   - **Issue**: Browsers block audio playback until user interaction (`#unlock` overlay).
   - **Vulnerability**: If `/tv` is launched or auto-refreshed, and a guest on phone starts playback or a song becomes ready while nobody has clicked the laptop screen, the intro counts down and tries to play, but the browser blocks audio. The lyrics and timer tick silently.
   - **Recommended Fix**:
     - Check `AudioContext.state` / `inst.paused` on page load: if autoplay is blocked, show a prominent glowing "Audio Suspended - Click to Enable Sound" banner that alerts the host immediately before songs start.

6. **Broken Downloads / DRM Streams Stalling the Stage**:
   - **Issue**: Guests frequently select SoundCloud DRM tracks or geo-restricted YouTube links that fail yt-dlp download with 403 or DRM errors.
   - **Vulnerability**: In some edge cases, an errored song in the queue displays a red error badge, but if it is at index 0 and idle, the stage can stall without automatically advancing to the next playable song.
   - **Recommended Fix**:
     - When a song encounters an unrecoverable download error, show a toast notification ("Skipping unplayable track: [Title]") and automatically trigger `queue.next()` to keep the party moving smoothly.

