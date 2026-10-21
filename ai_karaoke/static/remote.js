// Guest phone: singer name, YouTube search, queue (reorder / remove), live transport + scrubbing.
let nowEntry = null, scrubbing = false;
const singer = () => $("singer").value.trim();

// ── Search & results ──────────────────────────────────────────────────────
$("search-form").onsubmit = async (e) => {
  e.preventDefault();
  const q = $("query").value.trim();
  if (!q) return;
  $("query").blur();
  $("search-btn").disabled = true;
  $("results-title").textContent = "Searching…";
  try {
    const { results } = await api(`/api/search?q=${encodeURIComponent(q)}`);
    renderResults(results, results.length ? "Results" : "No results");
  } catch (err) {
    $("results-title").textContent = "";
    fail(err);
  }
  $("search-btn").disabled = false;
};

function renderResults(items, title) {
  $("results-title").textContent = title;
  $("results").replaceChildren(...items.map((r) => {
    const li = el("li", "panel flex items-center gap-3 p-2");
    const img = Object.assign(el("img", "h-14 w-20 shrink-0 rounded-lg object-cover"),
      { src: r.thumbnail || `https://i.ytimg.com/vi/${r.id}/hqdefault.jpg`, alt: "", loading: "lazy" });
    const info = el("div", "min-w-0 flex-1");
    info.append(el("p", "line-clamp-2 text-sm font-semibold", r.title),
      el("p", "truncate text-xs text-stone-400",
        [r.cached ? "⚡ Instant" : "", r.channel, r.duration ? fmt(r.duration) : ""].filter(Boolean).join(" · ")));
    const btn = el("button", "btn-gold shrink-0 rounded-lg px-3 py-2 text-sm", r.too_long ? "Too long" : "Add");
    btn.disabled = !!r.too_long;
    btn.onclick = () => addSong(r, btn);
    li.append(img, info, btn);
    return li;
  }));
}

async function addSong(r, btn) {
  if (!singer()) { toast("Enter your singer name first", false); $("singer").focus(); return; }
  btn.disabled = true;
  try {
    await api("/api/queue", { method: "POST",
      body: { song_id: r.id, singer: singer(), title: r.title, channel: r.channel || "", duration: r.duration } });
    btn.textContent = "Added ✓";
    toast(`Queued “${r.title}”`);
  } catch (err) { btn.disabled = false; fail(err); }
}

async function loadLibrary() {
  const { songs } = await api("/api/library").catch(() => ({ songs: [] }));
  const ready = songs.filter((s) => s.ready).map((s) => ({ ...s, cached: true }));
  if (ready.length && !$("results").children.length) renderResults(ready, "Ready to sing instantly");
}

// ── Live state ────────────────────────────────────────────────────────────
function renderState({ now_playing: np, queue }) {
  nowEntry = np;
  $("np-singer").textContent = np ? np.singer : "Nobody yet";
  $("np-title").textContent = np ? np.title : "Add a song to get started";
  $("np-seek").disabled = !np;
  if (!np) renderPlayback({ uid: null, time: 0, duration: 0, paused: true });
  $("np-lyrics").classList.toggle("hidden", !needsLyrics(np)); // lyrics were only transcribed
  $("queue-count").textContent = queue.length;
  $("queue-empty").classList.toggle("hidden", queue.length > 0);
  const me = singer().toLowerCase();
  $("queue").replaceChildren(...queue.map((e, i) => {
    const row = queueRow(e, i, queue.length, { thumb: false, extras: needsLyrics(e) ? [lyricsButton(e)] : [] });
    if (me && e.singer.toLowerCase() === me) row.classList.replace("ring-white/5", "ring-amber-400/60"); // yours stand out
    return row;
  }));
}

function renderPlayback({ uid, time, duration, paused }) {
  if (uid && uid !== nowEntry?.uid) return;
  if (!scrubbing) { $("np-seek").max = duration || 0; $("np-seek").value = time; $("np-cur").textContent = fmt(time); }
  $("np-dur").textContent = fmt(duration);
  $("btn-toggle").dataset.action = paused ? "play" : "pause";
  setIcon($("btn-toggle"), paused ? "play" : "pause");
}

const send = connectWS("remote", (msg) => {
  if (msg.type === "state") renderState(msg.data);
  else if (msg.type === "playback") renderPlayback(msg);
});

// ── Transport: buttons + timeline scrubbing ───────────────────────────────
document.querySelectorAll("[data-action]").forEach((btn) => {
  btn.onclick = () => send({ type: "control", action: btn.dataset.action, value: Number(btn.dataset.value || 0) });
});
$("np-seek").oninput = () => { scrubbing = true; $("np-cur").textContent = fmt(Number($("np-seek").value)); };
$("np-seek").onchange = () => {
  send({ type: "control", action: "seek", value: Number($("np-seek").value) });
  setTimeout(() => { scrubbing = false; }, 1200); // let the TV report the new position first
};
$("np-lyrics").onclick = () => nowEntry && openLyrics(nowEntry);

$("singer").value = store("singer") || "";
$("singer").oninput = () => store("singer", singer());
loadLibrary();
