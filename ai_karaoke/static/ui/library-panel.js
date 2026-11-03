// The song library as one block, for the /library page and the host app: cache use bar, a
// filter, the host's "Singer name (for 🎤 Queue)" box, and a card per cached song with queue /
// lyrics / re-sync / rebuild / delete (ui/library-card.js). No page ids or globals besides the
// constructor. Opens no WebSocket: the page calls .refreshSoon() on WS "state" / "library" /
// "media" messages; the panel also refreshes itself after its own re-sync / rebuild / delete.
// Needs common.js, auth.js, lyrics.js (openLyrics), ui/library-card.js.
// createLibraryPanel() -> element with .refresh() and .refreshSoon() (bursts become one reload)
function createLibraryPanel() {
  const GB = 1024 ** 3, MB = 1024 ** 2;
  const root = el("div", "space-y-5");
  root.innerHTML = `
    <section class="panel grid gap-4 p-4 sm:grid-cols-[1fr_auto_auto] sm:items-end">
      <div>
        <p class="text-xs font-semibold uppercase tracking-widest text-gold">Cache</p>
        <p data-k="storage-text" class="mt-1 text-sm text-stone-300">…</p>
        <div class="mt-2 h-2 overflow-hidden rounded-full bg-white/10">
          <div data-k="storage-bar" class="h-full w-0 rounded-full bg-gradient-to-r from-amber-300 to-amber-600"></div>
        </div>
      </div>
      <label data-k="singer-box" class="block hidden">
        <span class="text-xs font-semibold text-stone-400">Singer name (for 🎤 Queue)</span>
        <input data-k="singer" maxlength="32" placeholder="e.g. Freddie"
               class="mt-1 w-full rounded-xl border border-white/10 bg-black/50 px-3 py-2 outline-none focus:border-amber-400 sm:w-48">
      </label>
      <label class="block">
        <span class="text-xs font-semibold text-stone-400">Filter</span>
        <input data-k="filter" type="search" placeholder="Title or artist…"
               class="mt-1 w-full rounded-xl border border-white/10 bg-black/50 px-3 py-2 outline-none focus:border-amber-400 sm:w-56">
      </label>
    </section>
    <div data-k="songs" class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"></div>
    <p data-k="empty" class="hidden panel p-6 text-center text-stone-400">No songs yet — queue something from the remote and it will appear here.</p>`;
  const part = (k) => root.querySelector(`[data-k="${k}"]`);
  let songs = [], timer = null;

  async function refresh() {
    try {
      const data = await api("/api/library");
      songs = data.songs;
      part("storage-text").textContent =
        `${(data.used / GB).toFixed(2)} GB of ${(data.limit / GB).toFixed(0)} GB · ${songs.length} song${songs.length === 1 ? "" : "s"}`;
      part("storage-bar").style.width = `${Math.min(100, (data.used / data.limit) * 100)}%`;
      render();
    } catch (err) { fail(err); }
  }
  const refreshSoon = () => { clearTimeout(timer); timer = setTimeout(refresh, 300); };

  function render() {
    const q = part("filter").value.trim().toLowerCase();
    const shown = songs.filter((s) => !q || `${s.title} ${s.channel}`.toLowerCase().includes(q));
    part("empty").classList.toggle("hidden", shown.length > 0);
    part("songs").replaceChildren(...shown.map((s) => LibraryCard.card(s, actions)));
  }

  // Guests queue as themselves; the host may type any singer name (empty = their own login)
  async function queue(s) {
    const { admin, guest } = Auth.me;
    const name = admin ? part("singer").value.trim() || guest?.name || "" : guest?.name || "";
    if (!name) { toast(admin ? "Enter a singer name first" : "Log in on the 📱 Remote page first", false); return; }
    try {
      await api("/api/queue", { method: "POST",
        body: { song_id: s.id, singer: name, title: s.title, channel: s.channel || "", duration: s.duration } });
      toast(`Queued “${s.title}” for ${name}`);
    } catch (err) { fail(err); }
  }

  async function regenerate(s, target, reset = false) {
    const question = target === "all"
      ? `Rebuild “${s.title}” from scratch?\nDownload, vocal separation and lyrics run again (about a minute).`
      : reset ? `Forget the pasted lyrics for “${s.title}” and detect them automatically again?` : null;
    if (question && !confirm(question)) return;
    try {
      await api(`/api/songs/${s.id}/regenerate`, { method: "POST", body: { target, reset } });
      toast({ all: "Rebuilding — this takes about a minute…", video: "Downloading the video…" }[target] || "Re-syncing lyrics…");
      refreshSoon();
    } catch (err) { fail(err); }
  }

  async function remove(s) {
    if (!confirm(`Delete “${s.title}” from the cache (${Math.round(s.size / MB)} MB)?`)) return;
    const forgetLyrics = s.has_user_lyrics &&
      confirm("Also forget its pasted lyrics?\nOK = forget them · Cancel = keep them for next time");
    try {
      await api(`/api/songs/${s.id}?lyrics=${forgetLyrics}`, { method: "DELETE" });
      toast(`Deleted “${s.title}”`);
      refreshSoon();
    } catch (err) { fail(err); }
  }

  const actions = { queue, regenerate, remove, lyrics: (s) => openLyrics(s) };
  part("filter").oninput = render;
  part("singer").value = store("singer") || "";
  part("singer").oninput = () => store("singer", part("singer").value.trim());
  const paintHost = ({ admin }) => part("singer-box").classList.toggle("hidden", !admin);
  Auth.onChange((me) => { paintHost(me); render(); });   // host tools appear / go on every card
  paintHost(Auth.me);
  refresh();
  return Object.assign(root, { refresh, refreshSoon });
}
