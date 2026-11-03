// The player's audio tracks (instrumental #inst + guide vocals #voc) kept healthy: retries after
// a network error, a nudge when a track stalls, the guide track locked to the instrumental, the
// song's place remembered so a page reload resumes it, and "ended" reported to the server
// (after the game's results card, when one shows). Split from tv.js, which plays the songs.
// Needs common.js, tv-now.js (inst, voc, seek), game-panel.js; tv.js (current, sendClock, send)
// at run time. TvAudio = { install(), remember(uid), forget(), resumePoint(entry) -> {time, paused},
//   whenReady(fn) } — install() only in player mode, so a controller never touches its audio.
const TvAudio = (() => {
  const KEY = "karaoke_active_playback";   // this tab's song + time, for a reload mid-song

  function remember(uid) {
    try { sessionStorage.setItem(KEY, JSON.stringify({ uid, time: inst.currentTime, paused: inst.paused })); } catch {}
  }
  function forget() { try { sessionStorage.removeItem(KEY); } catch {} }

  // Where to start a song: this tab's own memory, or the server's clock if that is further on
  function resumePoint(entry) {
    let time = 0, paused = false;
    try {
      const saved = JSON.parse(sessionStorage.getItem(KEY) || "null");
      if (saved?.uid === entry.uid && Number.isFinite(saved.time)) { time = Number(saved.time); paused = Boolean(saved.paused); }
    } catch {}
    const pb = entry.playback;
    if (pb && (pb.uid === entry.uid || !pb.uid) && Number.isFinite(pb.time) && Number(pb.time) > time) {
      time = Number(pb.time);
      paused = Boolean(pb.paused);
    }
    return { time, paused };
  }

  // Run fn once the instrumental knows its length (seeking before that does nothing)
  function whenReady(fn) {
    if (inst.readyState >= 1) fn();
    else inst.addEventListener("loadedmetadata", fn, { once: true });
  }

  const reportEnded = (delay = 0) => {
    forget();
    const uid = current?.uid;
    if (uid) setTimeout(() => send({ type: "ended", uid }), delay);
  };

  let retries = 0, lastRetryTime = 0;
  function onError(audio, isInst) {
    if (!current || !audio.getAttribute("src")) return;
    const now = performance.now();
    if (now - lastRetryTime > 15000) retries = 0;
    lastRetryTime = now;
    retries++;
    if (retries <= 5) {
      const resumeAt = audio.currentTime, wasPlaying = !audio.paused;
      setTimeout(() => {
        if (!current) return;
        audio.load();
        const onReady = () => {
          if (!current) return;
          audio.currentTime = resumeAt;
          if (wasPlaying) audio.play().catch(() => {});
        };
        if (audio.readyState >= 1) onReady();
        else audio.addEventListener("loadedmetadata", onReady, { once: true });
      }, 800);
    } else if (isInst) {
      reportEnded(3000); // truly broken after 5 retries -> skip
    }
  }

  // A stalled track that should be playing: seeking to where it is wakes it up
  function guardStalls(audio, onPlaying) {
    let timer = null;
    audio.onstalled = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (!current || audio.paused) return;
        try { audio.currentTime = audio.currentTime; } catch {}
      }, 1500);
    };
    audio.onplaying = () => { clearTimeout(timer); onPlaying?.(); };
  }

  function install() {
    inst.onended = () => reportEnded(GamePanel.finish()); // game on: results stay up before the next song
    inst.onerror = () => onError(inst, true);
    voc.onerror = () => onError(voc, false);
    guardStalls(inst, () => { retries = 0; });
    guardStalls(voc);
    inst.onplay = inst.onpause = () => { setIcon($("btn-play"), inst.paused ? "play" : "pause"); sendClock(); };
    inst.onseeked = sendClock; // screens jump at once instead of waiting for the next tick
    inst.onloadedmetadata = () => setDuration(inst.duration);
    // Keep the guide-vocal track locked to the instrumental. A timer, not the animation loop:
    // browsers stop animation frames when this window is minimized, but timers keep running.
    setInterval(() => {
      if (!current) return;
      if (voc.paused !== inst.paused) inst.paused ? voc.pause() : voc.play().catch(() => {});
      if (!inst.paused && Math.abs(voc.currentTime - inst.currentTime) > 0.08) voc.currentTime = inst.currentTime;
    }, 500);
  }

  return { install, remember, forget, resumePoint, whenReady };
})();
