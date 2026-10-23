// Guest phone: the ready-to-sing songs (already processed, start instantly) and their tag
// filters — decades, genres, Russian, duets. Search and the "Good luck" pick build on these
// (remote-search.js, remote-lucky.js). Needs common.js.
let cachedSongs = [], availableGenres = [], availableDecades = [];
let activeTag = "all";

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

async function loadLibrary() {
  const data = await api("/api/library").catch(() => ({ songs: [] }));
  cachedSongs = (data.songs || []).filter((s) => s.ready).map((s) => ({ ...s, cached: true }));
  availableGenres = data.genres || [];
  availableDecades = data.decades || [];
  renderTagPills();
  showCached();
}
