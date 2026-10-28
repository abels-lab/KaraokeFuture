// Song search as one self-contained block, for a popup on either single-page app: the search
// box (ready songs filter while typing, Search asks /api/search online), tag pills, the "Good
// luck" random ready song and the result list with Add. The host also gets a "Singer name" box
// (remembered as host_singer; empty = the host's own guest login), as on the guest remote.
// No page ids: every part is found inside the block, so several can exist at once.
// Needs common.js, auth.js, ui/ready-songs.js, ui/song-rows.js. Opens no WebSocket.
// createSearchPanel({ onAdded(entry), singerName, getState, onNeedLogin }) -> element with
//   .refresh() (reload the ready songs: call it on WS "library") and .focusQuery().
// singerName pre-fills the host's box; getState() -> {now_playing, queue} saves a fetch for "Good luck".
function createSearchPanel({ onAdded = null, singerName = null, getState = null, onNeedLogin = null } = {}) {
  const root = el("div", "space-y-3");
  root.innerHTML = `
    <label data-k="singer-box" class="block hidden"><span class="text-xs font-semibold text-stone-400">Singer name for songs you add (host only)</span>
      <input data-k="singer" maxlength="32" placeholder="e.g. Freddie" class="mt-1 w-full rounded-xl border border-white/10 bg-black/50 px-4 py-2 outline-none focus:border-amber-400">
    </label>
    <form data-k="form" class="flex gap-2">
      <input data-k="query" type="search" maxlength="120" placeholder="Search song or artist…" enterkeyhint="search"
             class="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/50 px-4 py-3 outline-none focus:border-amber-400">
      <button data-k="go" class="btn-gold rounded-xl px-5">Search</button>
    </form>
    <div class="flex items-center gap-2">
      <div data-k="pills" class="pill-row min-w-0 flex-1 py-1 text-xs"></div>
      <button data-k="lucky" type="button" class="flex shrink-0 items-center gap-1.5 rounded-xl bg-amber-400/20 px-3 py-1.5 text-xs font-bold text-amber-300 ring-1 ring-amber-400/40 transition hover:bg-amber-400/30 active:scale-95" title="Pick an accidental cached song">
        <span>🎲</span> Good luck</button>
    </div>
    <div data-k="lucky-card" class="hidden"></div>
    <section>
      <div class="mb-2 flex items-center justify-between">
        <h3 data-k="title" class="text-sm font-semibold uppercase tracking-wider text-stone-400"></h3>
        <button data-k="show-ready" type="button" class="hidden text-xs font-semibold text-amber-400 hover:underline">⚡ Show ready songs</button>
      </div>
      <ul data-k="results" class="space-y-2"></ul>
    </section>`;
  const part = (k) => root.querySelector(`[data-k="${k}"]`);
  let songs = [], genres = [], decades = [], tag = "all";

  function showList(items, title) {
    part("title").textContent = title;
    part("results").replaceChildren(...items.map((r) => SongRows.result(r, add)));
  }

  function showReady() {
    const pool = ReadySongs.filter(songs, tag, part("query").value.trim());
    const label = tag === "all" ? "" : `: ${tag}`;
    showList(pool, pool.length ? `Ready to sing instantly${label} (${pool.length})` : `No ready songs${label}`);
    part("show-ready").classList.add("hidden");
  }

  function paintPills() {
    part("pills").replaceChildren(...ReadySongs.pills(songs, genres, decades).map((p) => {
      const on = p.tag === tag;
      const b = el("button", `rounded-full px-3 py-1 font-semibold transition ${on
        ? "bg-amber-400 text-stone-950 shadow-sm" : "bg-white/10 text-stone-300 hover:bg-white/20"}`, p.label);
      b.type = "button";
      b.onclick = () => { tag = tag === p.tag ? "all" : p.tag; paintPills(); showReady(); };
      return b;
    }));
  }

  async function refresh() {
    const data = await api("/api/library").catch(() => ({ songs: [] }));
    songs = (data.songs || []).filter((s) => s.ready).map((s) => ({ ...s, cached: true }));
    genres = data.genres || [];
    decades = data.decades || [];
    paintPills();
    if (!part("query").value.trim()) showReady();
  }

  part("form").onsubmit = async (e) => {
    e.preventDefault();
    const q = part("query").value.trim();
    if (!q) { showReady(); return; }
    part("query").blur();
    part("go").disabled = true;
    part("title").textContent = "Searching…";
    part("lucky-card").classList.add("hidden");
    try {
      const { results } = await api(`/api/search?q=${encodeURIComponent(q)}`);
      showList(results, results.length ? `Results for “${q}”` : "No results online");
      part("show-ready").classList.remove("hidden");
    } catch (err) { part("title").textContent = ""; fail(err); }
    part("go").disabled = false;
  };

  part("query").oninput = () => {   // ready songs filter live while typing; Search goes online
    const q = part("query").value.trim();
    if (!q) { showReady(); return; }
    const pool = ReadySongs.filter(songs, tag, q);
    showList(pool, pool.length ? `Ready matches (${pool.length})` : "No cached matches — tap Search for online");
    part("show-ready").classList.toggle("hidden", tag === "all" && !songs.length);
  };

  part("show-ready").onclick = () => {
    part("query").value = "";
    tag = "all";
    paintPills();
    part("lucky-card").classList.add("hidden");
    showReady();
  };

  part("lucky").onclick = async () => {   // queued / playing now: the page's live state, else ask the server
    const state = getState?.() || await api("/api/queue").catch(() => null);
    const { song, problem } = ReadySongs.pick(ReadySongs.filter(songs, tag), ReadySongs.busy(songs, state), tag);
    if (problem) { toast(problem, false); return; }
    const card = part("lucky-card");
    card.replaceChildren(...SongRows.lucky(song, add, () => card.classList.add("hidden")));
    card.className = "space-y-2 rounded-xl border border-amber-500/30 bg-gradient-to-br from-amber-500/10 via-stone-900 to-amber-950/20 p-3";
    toast(`🎲 Picked: ${ReadySongs.name(song)}`);
  };

  // Guests sing as their login (the server ignores the name for them); the host names anyone
  async function add(r, btn) {
    const { admin, guest } = Auth.me;
    if (!guest && !admin) {
      toast("Log in with your singer name first", false);
      onNeedLogin?.();
      return;
    }
    const singer = admin ? part("singer").value.trim() || guest?.name || "" : "";
    if (admin && !singer) {
      toast("Type who's singing in the Singer name box first", false);
      part("singer").focus();
      return;
    }
    btn.disabled = true;
    try {
      const entry = await api("/api/queue", { method: "POST", body: { song_id: r.id, singer, title: r.title,
        channel: r.channel || "", duration: r.duration, mirrors: r.mirrors || [] } });
      btn.textContent = "Added ✓";
      toast(`Queued “${r.title}”${entry?.singer ? ` for ${entry.singer}` : ""}`);
      onAdded?.(entry);
    } catch (err) { btn.disabled = false; fail(err); }
  }

  function paintHost(me) {
    part("singer-box").classList.toggle("hidden", !me.admin);
    part("singer").placeholder = me.guest ? `${me.guest.name} (you), or anyone` : "e.g. Freddie";
  }
  part("singer").value = singerName ?? (store("host_singer") || "");
  part("singer").oninput = () => store("host_singer", part("singer").value.trim());
  Auth.onChange(paintHost);
  paintHost(Auth.me);
  refresh();
  return Object.assign(root, { refresh, focusQuery: () => part("query").focus() });
}
