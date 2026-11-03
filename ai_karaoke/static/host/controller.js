// Controller mode: the host app on a phone or tablet (or any device that isn't the player) plays
// NO audio and never asks for the WebSocket "tv" role. Its buttons ask the laptop over REST
// (/api/player/control: play, pause, restart, seek, seek_by, skip, previous — the server checks
// the host's rights), and it follows the laptop's clock ("playback" 4 Hz, "intro" during the
// countdown) like a projector does, so the stage preview, timeline and countdown stay in step.
// The guide slider sets the playing song's own guide volume (PATCH /api/queue/<uid>).
// #host-note says who plays: view-only (no host PIN yet), no player connected (offer to play
// here, host/mode.js), player not answering, or simply "the laptop plays".
// Needs common.js, auth.js, tv-now.js, tv-side.js, guide.js, intro.js; host/mode.js when clicked.
// HostController = the Deck interface of tv.js: { start(), onState, onClock, onIntro, onMedia,
//   play(), pause(), toggle(), restart(), seekTo(t), seekBy(s), prev(), next(), time(), paused, current,
//   introRunning, skipIntro() }
const HostController = (() => {
  const intro = createIntro({ hint: true, container: $("monitor") });   // a tap starts the song now
  let entry = null, tvConnected = false, lastClockAt = 0, introAt = 0;
  let clock = { uid: null, time: 0, paused: true, at: 0 };
  const now = () => (clock.paused ? clock.time : clock.time + (performance.now() - clock.at) / 1000);
  const control = (action, value = null) => {
    if (!entry && !["skip", "previous"].includes(action)) return Promise.resolve();
    return api("/api/player/control", { method: "POST", body: { action, value } }).catch(fail);
  };

  function setClock(next) {
    const pausedChanged = next.paused !== clock.paused;
    clock = { ...next, at: performance.now() };
    if (pausedChanged) setIcon($("btn-play"), clock.paused ? "play" : "pause");
  }

  function onClock(m) {
    if (!entry || m.uid !== entry.uid) return;
    lastClockAt = performance.now();
    setDuration(m.duration);
    // Keep the running prediction unless the state changed or it is clearly off (as screen.js)
    if (m.paused !== clock.paused || clock.uid !== m.uid || Math.abs(now() - m.time) > 0.12) {
      const jump = Math.abs(now() - m.time) > 0.35;
      setClock({ uid: m.uid, time: m.time, paused: m.paused });
      if (jump) stage.seek?.(m.time);
    }
  }

  function onIntro(m) {
    if (m.uid !== entry?.uid || !(m.left > 0)) { intro.hide(); return; }
    introAt = performance.now();
    intro.show({ entry, ...m });
  }

  function onState({ now_playing: np, queue = [], played = [], screens = 0, playback, tv_connected: tv, active_playlist: autoDj = null }) {
    tvConnected = Boolean(tv);
    renderSide(queue, played, screens, np, autoDj);
    if (!np) {
      if (entry) { stage.clear(); pulse.clear(); intro.hide(); Guide.forEntry(null); }
      entry = null;
      setClock({ uid: null, time: 0, paused: true });
      resetNowPlaying();
      showStage(false, queue);
    } else if (entry?.uid !== np.uid) {
      entry = np;
      const pb = np.playback?.uid === np.uid ? np.playback : playback?.uid === np.uid ? playback : null;
      const start = Number(pb?.time) || 0;
      setClock({ uid: np.uid, time: start, paused: pb ? Boolean(pb.paused) : true });
      lastClockAt = performance.now();
      intro.hide();
      showSinger(np);
      showStage(true);
      setDuration(Number(pb?.duration) || np.duration);
      stage.load(np).then(() => { if (start > 0 && entry === np) stage.seek?.(now()); });
      Guide.forEntry(np);
    } else {
      if (entry.guide !== np.guide) Guide.forEntry(np);
      entry = np;   // same song, fresher details (a battle partner, the singer's choices)
      showSinger(np);
    }
    // The player left: its clock stopped too, so stop predicting time running on
    if (!tvConnected && !clock.paused) setClock({ uid: clock.uid, time: now(), paused: true });
    paintNote();
  }

  // ── #host-note: who plays the audio, and what this device may do ─────────
  const NOTE = { lock: "bg-amber-900/50 text-amber-100 ring-1 ring-amber-500/30",
                 warn: "bg-red-950/60 text-red-100 ring-1 ring-red-500/30", info: "bg-white/5 text-stone-400" };
  function paintNote() {
    const note = $("host-note");
    const lost = tvConnected && entry && !clock.paused && performance.now() - lastClockAt > 3000;
    let kind = "info", html = "🎛 Remote control — the laptop plays the audio and drives the projector.";
    if (!Auth.me.admin) {
      kind = "lock";
      html = `🔒 View only. <button type="button" data-k="unlock" class="font-semibold underline">Enter the host PIN</button> to control the party.`;
    } else if (!tvConnected) {
      kind = "warn";
      html = `No player connected: open the control panel on the laptop, or
        <button type="button" data-k="here" class="font-semibold underline">🔊 play the audio on this device</button>.`;
    } else if (lost) {
      kind = "warn";
      html = "⏳ Waiting for the player… (the laptop's control panel is not answering)";
    }
    if (note.dataset.html === html) return;   // repainted every second: touch the DOM only on change
    note.dataset.html = html;
    note.className = `rounded-xl px-3 py-2 text-xs ${NOTE[kind]}`;
    note.innerHTML = html;
    note.querySelector('[data-k="unlock"]')?.addEventListener("click", () => Auth.unlock());
    note.querySelector('[data-k="here"]')?.addEventListener("click", () => HostMode.openSwitch());
  }

  // Moving the guide slider here sets the playing song's own guide volume on the laptop
  function guideChanged() {
    if (!entry) return;
    const guide = Math.round(Number($("guide").value));
    api(`/api/queue/${entry.uid}`, { method: "PATCH", body: { guide, mode: entry.mode ?? null } }).catch(fail);
  }

  function start() {
    $("guide").addEventListener("change", guideChanged);
    intro.card.onclick = () => control("play");   // the player cuts its countdown short
    Auth.onChange(paintNote);
    setInterval(() => {
      paintNote();
      // The countdown's last message got lost (player closed mid-intro): don't stay stuck on it
      if (intro.visible && performance.now() - introAt > 1500) intro.hide();
    }, 1000);
    if ("BroadcastChannel" in window) {   // a player in another tab of this browser: its clock at once
      new BroadcastChannel("karaoke-clock").onmessage = (e) => (e.data.type === "intro" ? onIntro(e.data) : onClock(e.data));
    }
    paintNote();
  }

  return {
    isPlayer: false, start, onState, onClock, onIntro,
    onMedia(songId) { if (entry?.song_id === songId) stage.load(entry); },
    play: () => control("play"), pause: () => control("pause"),
    toggle: () => control(clock.paused ? "play" : "pause"),
    restart: () => control("restart"),
    seekTo: (t) => control("seek", Math.max(0, Math.min(3600, t))),
    seekBy: (s) => control("seek_by", s),
    prev: () => control("previous"), next: () => control("skip"),
    time: now,
    get introRunning() { return intro.visible; },
    skipIntro: () => control("play"),
    get paused() { return clock.paused; },
    get current() { return entry; },
  };
})();
