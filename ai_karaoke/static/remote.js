// Guest phone: singer name, song search, queue (reorder / remove), live transport + scrubbing.
// The server only returns songs that can be added (filtered, de-duplicated, checked).
let nowEntry = null, scrubbing = false;
let cachedSongs = [], availableGenres = [], availableDecades = [];
let activeTag = "all";
const singer = () => $("singer").value.trim();

// ── Search & results ──────────────────────────────────────────────────────
$("search-form").onsubmit = async (e) => {
  e.preventDefault();
  const q = $("query").value.trim();
  if (!q) { showCached(); return; }
  $("query").blur();
  $("search-btn").disabled = true;
  $("results-title").textContent = "Searching…";
  $("lucky-card").classList.add("hidden");
  try {
    const { results } = await api(`/api/search?q=${encodeURIComponent(q)}`);
    renderResults(results, results.length ? `Results for “${q}”` : "No results online");
    $("btn-show-ready").classList.remove("hidden");
  } catch (err) {
    $("results-title").textContent = "";
    fail(err);
  }
  $("search-btn").disabled = false;
};

// Real-time filtering when user types or clears the search field
$("query").oninput = () => {
  const q = $("query").value.trim();
  if (!q) {
    $("btn-show-ready").classList.add("hidden");
    showCached();
  } else {
    const pool = filterCachedSongs(activeTag, q);
    renderResults(pool, pool.length ? `Ready matches (${pool.length})` : "No cached matches — tap Search for online");
    $("btn-show-ready").classList.toggle("hidden", activeTag === "all" && !cachedSongs.length);
  }
};

$("btn-show-ready").onclick = () => {
  $("query").value = "";
  activeTag = "all";
  updatePillsUI();
  $("lucky-card").classList.add("hidden");
  showCached();
};

function filterCachedSongs(tag, queryText = "") {
  let pool = cachedSongs;
  if (tag && tag !== "all") {
    const t = tag.toLowerCase();
    pool = pool.filter((s) =>
      (s.genre && s.genre.toLowerCase() === t) ||
      (s.decade && s.decade.toLowerCase() === t) ||
      (s.language && s.language.toLowerCase() === t) ||
      (Array.isArray(s.tags) && s.tags.includes(t)) ||
      (t === "russian" && s.language === "ru") ||
      (t === "duet" && (s.tags || []).includes("duet"))
    );
  }
  if (queryText) {
    const qTokens = queryText.toLowerCase().replace(/ё/g, "е").split(/\s+/).filter(Boolean);
    pool = pool.filter((s) => {
      const haystack = `${s.artist || ""} ${s.clean_title || ""} ${s.title || ""} ${s.channel || ""} ${s.genre || ""}`.toLowerCase().replace(/ё/g, "е");
      return qTokens.every((tok) => haystack.includes(tok));
    });
  }
  return pool;
}

function showCached() {
  const pool = filterCachedSongs(activeTag, $("query").value.trim());
  const tagLabel = activeTag === "all" ? "" : `: ${activeTag}`;
  renderResults(pool, pool.length ? `Ready to sing instantly${tagLabel} (${pool.length})` : `No ready songs${tagLabel}`);
  $("btn-show-ready").classList.add("hidden");
}

function updatePillsUI() {
  document.querySelectorAll("#tag-pills button").forEach((btn) => {
    const isActive = btn.dataset.tag === activeTag;
    btn.className = `shrink-0 rounded-full px-3 py-1 font-semibold transition ${
      isActive
        ? "bg-amber-400 text-stone-950 shadow-sm"
        : "bg-white/10 text-stone-300 hover:bg-white/20"
    }`;
  });
}

function renderTagPills() {
  const pills = [{ tag: "all", label: "✨ All" }];

  // Decades first
  const decadeOrder = ["80s", "90s", "2000s", "2010s", "70s", "2020s"];
  for (const d of decadeOrder) {
    if (availableDecades.includes(d)) pills.push({ tag: d, label: d });
  }

  // Top genres
  for (const g of availableGenres) {
    pills.push({ tag: g, label: g });
  }

  // Russian tag if available
  if (cachedSongs.some((s) => s.language === "ru")) {
    pills.push({ tag: "russian", label: "🇷🇺 Russian" });
  }

  // Duet tag if available
  if (cachedSongs.some((s) => (s.tags || []).includes("duet"))) {
    pills.push({ tag: "duet", label: "🎤 Duets" });
  }

  $("tag-pills").replaceChildren(...pills.map(({ tag, label }) => {
    const btn = el("button", "", label);
    btn.type = "button";
    btn.dataset.tag = tag;
    btn.onclick = () => {
      activeTag = activeTag === tag ? "all" : tag;
      updatePillsUI();
      showCached();
    };
    return btn;
  }));
  updatePillsUI();
}

// ── Good luck / Surprise pick ─────────────────────────────────────────────
$("btn-lucky").onclick = () => rollLuckySong();

function rollLuckySong() {
  const pool = filterCachedSongs(activeTag);
  if (!pool.length) {
    toast(`No ready songs under ${activeTag}`, false);
    return;
  }
  const song = pool[Math.floor(Math.random() * pool.length)];
  const card = $("lucky-card");
  card.className = "panel p-3 border-amber-400/50 bg-gradient-to-r from-amber-950/40 via-stone-900/60 to-amber-950/40 transition mb-2";

  const header = el("div", "flex items-center justify-between text-xs font-semibold text-amber-300 mb-1.5");
  header.append(el("span", "", `🎲 Accidental pick${activeTag !== "all" ? ` · ${activeTag}` : ""}`));
  const btnAgain = el("button", "text-xs text-stone-400 hover:text-white underline", "Roll again");
  btnAgain.type = "button";
  btnAgain.onclick = rollLuckySong;
  header.append(btnAgain);

  const body = el("div", "flex items-center gap-3");
  const img = Object.assign(el("img", "h-12 w-16 shrink-0 rounded-lg object-cover"),
    { src: song.thumbnail || thumbFor(song.id), alt: "", loading: "lazy" });
  const info = el("div", "min-w-0 flex-1");
  const displayTitle = song.artist && song.clean_title ? `${song.artist} – ${song.clean_title}` : song.title;
  info.append(
    el("p", "truncate text-sm font-bold text-amber-100", displayTitle),
    el("p", "truncate text-xs text-stone-400", [song.genre, song.decade, "⚡ Instant", song.duration ? fmt(song.duration) : ""].filter(Boolean).join(" · "))
  );
  const btnAdd = el("button", "btn-gold shrink-0 rounded-lg px-3 py-1.5 text-xs font-bold", "Add");
  btnAdd.onclick = () => addSong(song, btnAdd);
  body.append(img, info, btnAdd);

  card.replaceChildren(header, body);
  card.classList.remove("hidden");
  toast(`🎲 Picked: ${displayTitle}`);
}

function renderResults(items, title) {
  $("results-title").textContent = title;
  $("results").replaceChildren(...items.map((r) => {
    const li = el("li", "panel flex items-center gap-3 p-2");
    const img = Object.assign(el("img", "h-14 w-20 shrink-0 rounded-lg object-cover"),
      { src: r.thumbnail || thumbFor(r.id), alt: "", loading: "lazy" });
    const info = el("div", "min-w-0 flex-1");
    const displayTitle = r.artist && r.clean_title ? `${r.artist} – ${r.clean_title}` : r.title;
    const metaParts = [
      r.cached ? "⚡ Instant" : "",
      r.genre || "",
      r.decade || "",
      r.source === "soundcloud" ? "SoundCloud" : (!r.genre ? r.channel : ""),
      r.duration ? fmt(r.duration) : ""
    ].filter(Boolean);
    info.append(el("p", "line-clamp-2 text-sm font-semibold", displayTitle),
      el("p", "truncate text-xs text-stone-400", metaParts.join(" · ")));
    const btn = el("button", "btn-gold shrink-0 rounded-lg px-3 py-2 text-sm", "Add");
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
      body: { song_id: r.id, singer: singer(), title: r.title, channel: r.channel || "", duration: r.duration,
              mirrors: r.mirrors || [] } });
    btn.textContent = "Added ✓";
    toast(`Queued “${r.title}”`);
  } catch (err) { btn.disabled = false; fail(err); }
}

async function loadLibrary() {
  const data = await api("/api/library").catch(() => ({ songs: [] }));
  cachedSongs = (data.songs || []).filter((s) => s.ready).map((s) => ({ ...s, cached: true }));
  availableGenres = data.genres || [];
  availableDecades = data.decades || [];
  renderTagPills();
  showCached();
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
