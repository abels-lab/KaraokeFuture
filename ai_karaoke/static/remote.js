// Guest phone: song search, "I don't know what to sing", the queue (my-queue.js) and live
// transport + scrubbing — the transport only for your own song (or the host).
// The server only returns songs that can be added (filtered, de-duplicated, checked).
let nowEntry = null, scrubbing = false;

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
      { src: r.thumbnail || thumbFor(r.id), alt: "", loading: "lazy" });
    const info = el("div", "min-w-0 flex-1");
    info.append(el("p", "line-clamp-2 text-sm font-semibold", r.title),
      el("p", "truncate text-xs text-stone-400",
        [r.cached ? "⚡ Instant" : "", r.source === "soundcloud" ? "SoundCloud" : "", r.channel,
         r.duration ? fmt(r.duration) : ""].filter(Boolean).join(" · ")));
    const btn = el("button", "btn-gold shrink-0 rounded-lg px-3 py-2 text-sm", "Add");
    btn.onclick = () => addSong(r, btn);
    li.append(img, info, btn);
    return li;
  }));
}

async function addSong(r, btn) {
  if (!Auth.me.guest) { toast("Log in with your singer name first", false); $("login-name").focus(); return; }
  btn.disabled = true;
  try {
    await api("/api/queue", { method: "POST",
      body: { song_id: r.id, title: r.title, channel: r.channel || "", duration: r.duration, mirrors: r.mirrors || [] } });
    btn.textContent = "Added ✓";
    toast(`Queued “${r.title}”`);
  } catch (err) { btn.disabled = false; fail(err); }
}

$("surprise").onclick = async () => {
  $("surprise").disabled = true;
  try {
    const entry = await api("/api/queue/surprise", { method: "POST" });
    toast(`🎲 You're singing “${entry.title}”!`);
  } catch (err) { fail(err); }
  $("surprise").disabled = false;
};

async function loadLibrary() {
  const { songs } = await api("/api/library").catch(() => ({ songs: [] }));
  const ready = songs.filter((s) => s.ready).map((s) => ({ ...s, cached: true }));
  if (ready.length && !$("results").children.length) renderResults(ready, "Ready to sing instantly");
}

// ── Live state ────────────────────────────────────────────────────────────
let lastState = { now_playing: null, queue: [] };
function renderState(state = lastState) {
  lastState = state;
  const { now_playing: np, queue } = state;
  const mayControl = Auth.me.admin || Auth.owns(np);
  nowEntry = np;
  $("np-singer").textContent = np ? np.singer : "Nobody yet";
  $("np-title").textContent = np ? np.title : "Add a song to get started";
  $("np-seek").disabled = !np || !mayControl;
  $("transport").classList.toggle("hidden", Boolean(np) && !mayControl);
  $("transport-note").classList.toggle("hidden", !np || mayControl);
  if (!np) renderPlayback({ uid: null, time: 0, duration: 0, paused: true });
  $("np-lyrics").classList.toggle("hidden", !Auth.me.admin || !needsLyrics(np)); // lyrics were only transcribed
  $("np-prefs").replaceChildren(...(Auth.owns(np) && !dragging ? [songPrefs(np)] : []));
  renderQueue(queue);
}
Auth.onChange(() => renderState());

function renderPlayback({ uid, time, duration, paused }) {
  if (uid && uid !== nowEntry?.uid) return;
  if (!scrubbing) { $("np-seek").max = duration || 0; $("np-seek").value = time; $("np-cur").textContent = fmt(time); }
  $("np-dur").textContent = fmt(duration);
  $("btn-toggle").dataset.action = paused ? "play" : "pause";
  setIcon($("btn-toggle"), paused ? "play" : "pause");
}

connectWS("remote", (msg) => {
  if (msg.type === "state") renderState(msg.data);
  else if (msg.type === "playback") renderPlayback(msg);
});

// ── Transport: buttons + timeline scrubbing (REST, so the login cookie is always current) ──
const control = (action, value = 0) =>
  api("/api/player/control", { method: "POST", body: { action, value } }).catch(fail);
document.querySelectorAll("[data-action]").forEach((btn) => {
  btn.onclick = () => control(btn.dataset.action, Number(btn.dataset.value || 0));
});
$("np-seek").oninput = () => { scrubbing = true; $("np-cur").textContent = fmt(Number($("np-seek").value)); };
$("np-seek").onchange = () => {
  control("seek", Number($("np-seek").value));
  setTimeout(() => { scrubbing = false; }, 1200); // let the TV report the new position first
};
$("np-lyrics").onclick = () => nowEntry && openLyrics(nowEntry);
loadLibrary();
