// Guest phone: song search, tag filters, "Good luck" picker, the queue (my-queue.js) and live
// transport + scrubbing — the transport only for your own song (or the host).
// The server only returns songs that can be added (filtered, de-duplicated, checked).
let nowEntry = null, scrubbing = false;
let cachedSongs = [], availableGenres = [], availableDecades = [];
let activeTag = "all";
let activeTab = "songs"; // "songs" | "queue"

// ── Tab switcher: Songs vs Queue ──────────────────────────────────────────
function switchTab(tab) {
  activeTab = tab;
  const isSongs = tab === "songs";
  $("panel-songs")?.classList.toggle("hidden", !isSongs);
  $("panel-queue")?.classList.toggle("hidden", isSongs);

  if ($("tab-btn-songs")) {
    $("tab-btn-songs").className = `flex-1 flex items-center justify-center gap-2 rounded-xl py-2.5 transition-all font-bold ${
      isSongs
        ? "bg-gradient-to-r from-amber-500 to-yellow-400 text-stone-950 shadow-md"
        : "text-stone-400 hover:text-stone-200"
    }`;
  }
  if ($("tab-btn-queue")) {
    $("tab-btn-queue").className = `flex-1 flex items-center justify-center gap-2 rounded-xl py-2.5 transition-all font-bold ${
      !isSongs
        ? "bg-gradient-to-r from-amber-500 to-yellow-400 text-stone-950 shadow-md"
        : "text-stone-400 hover:text-stone-200"
    }`;
  }
}

$("tab-btn-songs")?.addEventListener("click", () => switchTab("songs"));
$("tab-btn-queue")?.addEventListener("click", () => switchTab("queue"));
$("btn-goto-songs")?.addEventListener("click", () => switchTab("songs"));

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

// ── Good luck accidental card ──────────────────────────────────────────────
$("btn-lucky").onclick = () => rollLuckySong();

function rollLuckySong() {
  const allTagged = filterCachedSongs(activeTag);
  if (!allTagged.length) {
    toast(`No ready songs under ${activeTag}`, false);
    return;
  }

  // Exclude songs currently in queue or currently playing
  const activeIds = new Set(
    [lastState.now_playing?.song_id, ...lastState.queue.map((e) => e.song_id)].filter(Boolean)
  );
  const free = allTagged.filter((s) => !activeIds.has(s.id));

  if (!free.length) {
    toast(`All songs under ${activeTag} are already queued or playing!`, false);
    return;
  }

  // Exclude songs played in the last hour (3600 seconds)
  const now = Date.now() / 1000;
  const RECENT_SECONDS = 3600;
  const fresh = free.filter((s) => !s.played_at || (now - Number(s.played_at)) > RECENT_SECONDS);

  // If there are fresh songs, pick from them; otherwise fall back to available free songs
  const pool = fresh.length ? fresh : free;
  const song = pool[Math.floor(Math.random() * pool.length)];
  const card = $("lucky-card");

  const header = el("div", "flex items-center justify-between text-xs text-amber-300 font-bold mb-1");
  header.append(
    el("span", "flex items-center gap-1", "🎲 Accidental Song Pick"),
    Object.assign(el("button", "text-stone-400 hover:text-stone-200 px-1", "✕"), {
      onclick: () => card.classList.add("hidden"),
    })
  );

  const body = el("div", "flex items-center gap-3");
  const img = Object.assign(el("img", "h-14 w-20 shrink-0 rounded-lg object-cover"), {
    src: song.thumbnail || thumbFor(song.id),
    alt: "",
    loading: "lazy",
  });
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
  card.className = "p-3 rounded-xl bg-gradient-to-br from-amber-500/10 via-stone-900 to-amber-950/20 border border-amber-500/30 space-y-2";
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
  if (!Auth.me.guest && !Auth.me.admin) {
    toast("Log in with your singer name first", false);
    $("login-name").focus();
    return;
  }
  btn.disabled = true;
  try {
    await api("/api/queue", { method: "POST",
      body: { song_id: r.id, title: r.title, channel: r.channel || "", duration: r.duration, mirrors: r.mirrors || [] } });
    btn.textContent = "Added ✓";
    toast(`Queued “${r.title}” · tap Queue tab to view`);
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

  const isAdmin = Boolean(Auth.me.admin);
  $("np-lyrics").classList.toggle("hidden", !np);
  if (np) {
    if (isAdmin) {
      $("np-lyrics").textContent = needsLyrics(np) ? "📝 AI lyrics: fix" : "📝 Edit lyrics";
      $("np-lyrics").className = `rounded-lg px-2.5 py-1 text-xs font-semibold ${
        needsLyrics(np) ? "bg-amber-900/80 text-amber-200 ring-1 ring-amber-500/50" : "bg-white/10 text-stone-200 hover:bg-white/20"
      }`;
    } else {
      $("np-lyrics").textContent = "📖 Read lyrics";
      $("np-lyrics").className = "rounded-lg bg-white/10 px-2.5 py-1 text-xs font-semibold text-stone-200 hover:bg-white/20";
    }
  }

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
