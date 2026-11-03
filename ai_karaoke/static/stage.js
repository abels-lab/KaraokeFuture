// Stage renderer shared by the control panel (/tv) and the projector (/screen): lyrics with
// word-by-word fill, the muted video locked to a clock, and break / "♪" hints from the vocal map.
// Lyrics alternate between two fixed rows like classic karaoke: even lines on the top row, odd
// lines on the bottom one. The upcoming line already waits (dimmed) in its own row, so nothing
// moves when it starts; only a finished line is replaced, by the one after next.
// Needs common.js + stage-video.js. createStage(elements) -> { load(entry), clear(), render(time, playing) }
function createStage({ main, next, hint, noLyrics, video }) {
  let song = null, lyrics = [], regions = [], lineIdx = -2, words = [], lastT = 0;
  const videoSync = createVideoSync(video);
  const rows = [main, next];
  let shown = [[], []];   // per row: [{w, el}] of the line on it (filled by time, both rows)
  const getJSON = async (url, fallback) => {
    if (!url) return fallback;
    try { return await (await fetch(`${url}?v=${Date.now()}`)).json(); } catch { return fallback; } // cache-busted
  };

  // Also used to reload mid-song after lyrics are edited or a video arrives (video keeps playing)
  async function load(entry) {
    song = entry;
    videoSync.set(entry.media?.video);
    const [fresh, map] = await Promise.all([getJSON(entry.media?.lyrics, []), getJSON(entry.media?.vocal_map, {})]);
    if (song !== entry) return;
    lyrics = fresh; regions = map.regions || [];
    noLyrics.classList.toggle("hidden", lyrics.length > 0);
    renderLines(-2);
  }

  function clear() {
    videoSync.cancelSeek();
    song = null; lyrics = []; regions = [];
    videoSync.set(null); renderLines(-2);
    rows.forEach((row) => { row.style.fontSize = ""; });
    hint.textContent = ""; noLyrics.classList.add("hidden");
  }

  function renderLines(idx) {
    lineIdx = idx;
    rows.forEach((row, r) => {
      // The row of the current line keeps it; the other row shows the line after it
      const i = idx < 0 ? -1 : idx % 2 === r ? idx : idx + 1;
      if (row.dataset.line !== String(i) || !lyrics[i]) {
        row.dataset.line = String(i);
        const line = lyrics[i];
        const lineWords = line?.words || [];
        shown[r] = lineWords.map((w, k) => ({ w, el: el("span", "word", k ? w.word : w.word.trimStart()) }));
        row.replaceChildren(...shown[r].map((x) => x.el));

        // Dynamic font size stepping for long lines to prevent overflow on compact monitors
        const totalChars = line ? (line.text ? line.text.length : lineWords.reduce((sum, w) => sum + (w.word ? w.word.length : 0), 0)) : 0;
        if (totalChars > 65) {
          row.style.fontSize = "clamp(1.1rem, 1.8vw, 1.9rem)";
        } else if (totalChars > 45) {
          row.style.fontSize = "clamp(1.3rem, 2.3vw, 2.3rem)";
        } else {
          row.style.fontSize = "";
        }
      }
      row.style.opacity = i === idx ? "1" : "0.55";   // the waiting line is dimmed until it starts
    });
    words = idx >= 0 ? shown[idx % 2] : [];
  }

  function render(t, playing) {
    if (!song) return;
    lastT = t;
    videoSync.sync(t, playing);
    // Current or upcoming line. A line stays current a little past its end (singers hold the last
    // note), up to 1 s but never into the next line: its row is replaced only after that
    const idx = lyrics.findIndex((s, i) => t <= s.end + Math.min(1, Math.max(0, (lyrics[i + 1]?.start ?? Infinity) - s.end - 0.1)));
    if (idx !== lineIdx) renderLines(idx);
    for (const { el: span, w } of shown.flat()) {
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
    const row = rows[Math.max(0, lineIdx) % 2];
    return singing ? singing.el : row.childElementCount ? row : null;
  }

  return { load, clear, render, seek: videoSync.seek, get song() { return song; },
           get main() { return rows[Math.max(0, lineIdx) % 2]; }, get activeWord() { return activeWord(); } };
}
