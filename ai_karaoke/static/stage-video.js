// The stage's muted music video, locked to the song clock (stage.js): small drift is caught up by
// nudging the playback rate, a big one (a seek or a stall) snaps, at most once a second.
// createVideoSync(video) -> { set(src), sync(time, playing), seek(time), cancelSeek() }; video may be null.
function createVideoSync(video) {
  let lastVideoSync = 0, lastHardSeek = 0, pendingSeek = null;

  function set(src) {
    if (!video) return;
    if (!src) {
      delete video.dataset.src; video.removeAttribute("src"); video.load(); video.classList.add("opacity-0");
    } else if (video.dataset.src !== src) {
      video.dataset.src = src; video.src = src; video.classList.remove("opacity-0");
    }
  }

  function sync(t, playing) {
    if (!video?.dataset.src || video.readyState < 1) return;
    if (playing && video.paused && t < video.duration) video.play().catch(() => {});
    if (!playing && !video.paused) video.pause();
    const now = performance.now();
    if (now - lastVideoSync < 200) return;
    lastVideoSync = now;
    if (video.seeking) return;
    const drift = video.currentTime - t;
    const absDrift = Math.abs(drift);
    if (!playing) {
      if (absDrift > 0.05) video.currentTime = Math.max(0, t);
      video.playbackRate = 1;
    } else if (absDrift > 1.2) { // genuine seek or major stall: snap, throttled to max once per sec
      if (now - lastHardSeek > 1000) {
        lastHardSeek = now;
        video.currentTime = Math.max(0, t);
        video.playbackRate = 1;
      }
    } else if (absDrift < 0.06) { // within 60 ms: in sync, keep normal speed
      if (video.playbackRate !== 1) video.playbackRate = 1;
    } else { // gentle catch-up without visible stutter or decoder stalls
      const targetRate = Math.min(1.08, Math.max(0.92, 1.0 - drift * 0.5));
      if (Math.abs(video.playbackRate - targetRate) > 0.015) {
        video.playbackRate = targetRate;
      }
    }
  }

  function seek(t) {
    if (!video || !video.dataset.src) return;
    if (video.readyState >= 1) {
      video.currentTime = Math.max(0, t);
      video.playbackRate = 1;
      pendingSeek = null;
    } else {
      pendingSeek = t;
      video.addEventListener("loadedmetadata", () => {
        if (pendingSeek !== null) {
          video.currentTime = Math.max(0, pendingSeek);
          video.playbackRate = 1;
          pendingSeek = null;
        }
      }, { once: true });
    }
  }

  return { set, sync, seek, cancelSeek: () => { pendingSeek = null; } };
}
