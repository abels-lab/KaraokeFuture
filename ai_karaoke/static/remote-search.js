// Guest phone: song search (online on Search, ready songs while typing), the result list and
// adding a song to the queue. The server only returns songs that can be added (filtered,
// de-duplicated, checked). Needs common.js, auth.js, remote-library.js.
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
  // The host may queue for anyone (empty box = their own login); the server ignores it for guests
  const singer = Auth.me.admin ? $("host-singer").value.trim() || Auth.me.guest?.name || "" : "";
  if (Auth.me.admin && !singer) {
    toast("Type who's singing in the Singer name box first", false);
    $("host-singer").focus();
    return;
  }
  btn.disabled = true;
  try {
    await api("/api/queue", { method: "POST", body: { song_id: r.id, singer, title: r.title,
      channel: r.channel || "", duration: r.duration, mirrors: r.mirrors || [] } });
    btn.textContent = "Added ✓";
    toast(`Queued “${r.title}” · tap Queue tab to view`);
  } catch (err) { btn.disabled = false; fail(err); }
}
