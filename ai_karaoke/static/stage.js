// Stage renderer shared by the control panel (/tv) and the projector (/screen): lyrics with
// word-by-word fill, the muted video locked to a clock, and break / "♪" hints from the vocal map.
// Needs common.js. createStage(elements) -> { load(entry), clear(), render(time, playing) }
function createStage({ main, next, hint, noLyrics, video }) {
  let song = null, lyrics = [], regions = [], lineIdx = -2, words = [], lastVideoSync = 0, lastT = 0;
  const getJSON = async (url, fallback) => {
    if (!url) return fallback;
    try { return await (await fetch(`${url}?v=${Date.now()}`)).json(); } catch { return fallback; } // cache-busted
  };

  function setVideo(src) {
    if (!video) return;
    if (!src) {
      delete video.dataset.src; video.removeAttribute("src"); video.load(); video.classList.add("opacity-0");
    } else if (video.dataset.src !== src) {
      video.dataset.src = src; video.src = src; video.classList.remove("opacity-0");
    }
  }

  // Also used to reload mid-song after lyrics are edited or a video arrives (video keeps playing)
  async function load(entry) {
    song = entry;
    setVideo(entry.media?.video);
    const [fresh, map] = await Promise.all([getJSON(entry.media?.lyrics, []), getJSON(entry.media?.vocal_map, {})]);
    if (song !== entry) return;
    lyrics = fresh; regions = map.regions || [];
    noLyrics.classList.toggle("hidden", lyrics.length > 0);
    renderLines(-2);
  }

  function clear() {
    song = null; lyrics = []; regions = [];
    setVideo(null); renderLines(-2);
    hint.textContent = ""; noLyrics.classList.add("hidden");
  }

  function renderLines(idx) {
    lineIdx = idx;
    const line = lyrics[idx], following = idx >= 0 ? lyrics[idx + 1] : null;
    words = (line?.words || []).map((w, i) => ({ w, el: el("span", "word", i ? w.word : w.word.trimStart()) }));
    main.replaceChildren(...words.map((x) => x.el));
    next.textContent = following ? following.text : "";
  }

  let lastHardSeek = 0;

  function syncVideo(t, playing) {
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
    if (video && video.dataset.src && video.readyState >= 1) {
      video.currentTime = Math.max(0, t);
      video.playbackRate = 1;
    }
  }

  function render(t, playing) {
    if (!song) return;
    lastT = t;
    syncVideo(t, playing);
    // Current or upcoming line. A line stays up a little past its end (up to 1 s, but not into the
    // next line): singers hold the last note longer than its timing says
    const idx = lyrics.findIndex((s, i) => t <= s.end + Math.min(1, Math.max(0.4, (lyrics[i + 1]?.start ?? Infinity) - s.end - 0.1)));
    if (idx !== lineIdx) renderLines(idx);
    for (const { el: span, w } of words) {
      const p = Math.min(1, Math.max(0, (t - w.start) / Math.max(0.05, w.end - w.start)));
      span.style.setProperty("--p", `${(p * 100).toFixed(1)}%`);
    }
    const wait = idx >= 0 ? lyrics[idx].start - t : Infinity;
    const singing = regions.some(([s, e]) => t >= s && t <= e);
    let text = "";
    if (lyrics.length && wait > 3) {
      // Between lines: real instrumental break, or someone sings a part the lyrics don't have
      text = singing ? "♪ ♪ ♪" : Number.isFinite(wait) ? `🎸 Instrumental · ${Math.ceil(wait)}` : "";
    } else if (wait > 0.6 && Number.isFinite(wait)) {
      text = `♪ ${Math.ceil(wait)}`;                // get-ready countdown just before a line
    }
    if (hint.textContent !== text) hint.textContent = text;
  }

  // The word being sung right now (party effects spark from it), else the whole line
  function activeWord() {
    const singing = words.find(({ w }) => w.start <= lastT && lastT <= w.end);
    return singing ? singing.el : main.childElementCount ? main : null;
  }

  return { load, clear, render, seek, get song() { return song; },
           get main() { return main; }, get activeWord() { return activeWord(); } };
}
