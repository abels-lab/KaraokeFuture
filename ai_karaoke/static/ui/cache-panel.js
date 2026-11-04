// "Song cache" block of the settings panel (host only): how full the cache is, how much the
// warm-up and the queue use, free disk, and buttons to trim it to its limit or clear it.
// Songs that are playing, queued, recently played or being processed are never deleted, and
// pasted lyrics live outside the cache (the server enforces both, routers/cache.py).
// Needs common.js and auth.js. createCachePanel() -> <section> with .refresh(); hidden for guests.
function createCachePanel() {
  const GB = 1024 ** 3;
  const gb = (n) => `${(n / GB).toFixed(n >= 10 * GB ? 0 : 2)} GB`;
  const box = el("section", "panel hidden space-y-3 p-4");
  box.innerHTML = `
    <div class="flex items-center justify-between gap-3">
      <h2 class="font-display text-xl font-bold text-gold">Song cache</h2>
      <span data-k="used" class="text-sm text-stone-300"></span>
    </div>
    <div class="h-2 overflow-hidden rounded-full bg-white/10">
      <div data-k="bar" class="h-full rounded-full bg-amber-400 transition-all"></div>
    </div>
    <p data-k="detail" class="text-sm text-stone-400"></p>
    <p data-k="warn" class="hidden rounded-xl border border-red-500/40 p-2 text-sm text-red-200"></p>
    <div class="flex flex-wrap gap-2 border-t border-white/10 pt-3">
      <button data-k="trim" type="button" class="rounded-xl bg-white/10 px-4 py-2 text-sm font-semibold hover:bg-white/20">✂ Trim to limit</button>
      <button data-k="warm" type="button" class="rounded-xl bg-white/10 px-4 py-2 text-sm font-semibold hover:bg-white/20 disabled:opacity-30">🔥 Clear unplayed warm-ups</button>
      <button data-k="all" type="button" class="rounded-xl bg-red-900/70 px-4 py-2 text-sm font-semibold hover:bg-red-800 disabled:opacity-30">🗑 Clear cache</button>
    </div>
    <p class="text-xs text-stone-500">Songs that are playing, queued or being prepared are always kept, and so are the next Auto-DJ songs. Pasted lyrics and lyrics found online are never deleted.</p>`;
  const part = (k) => box.querySelector(`[data-k="${k}"]`);

  function paint(s) {
    part("used").textContent = `${gb(s.used)} of ${gb(s.limit)}${s.over_limit ? " — over the limit" : ""}`;
    part("used").classList.toggle("text-red-300", s.over_limit);
    part("bar").style.width = `${Math.min(100, (s.used / Math.max(1, s.limit)) * 100)}%`;
    part("detail").textContent = [
      `${s.ready} ready song${s.ready === 1 ? "" : "s"}` + (s.incomplete ? `, ${s.incomplete} in progress` : ""),
      `warm-up ${gb(s.warm_used)} of ${gb(s.warm_budget)} (${s.warm_songs} unplayed${s.stale_warm ? `, ${s.stale_warm} from an old rotation` : ""})`,
      `${s.protected} kept for the queue (${gb(s.protected_used)})`,
      `${gb(s.disk_free)} free on disk`,
    ].join(" · ");
    const warn = [
      s.stuck && "Over the limit, but every song left is playing or queued: it shrinks as songs are played.",
      s.disk_low && `The disk is almost full (under ${gb(s.min_free)} free): new songs can't be downloaded until you free space.`,
    ].filter(Boolean).join(" ");
    part("warn").textContent = warn;
    part("warn").classList.toggle("hidden", !warn);
    part("warm").disabled = !s.warm_songs;
    part("all").disabled = s.songs <= s.protected;
  }

  async function refresh() {
    if (!Auth.me.admin) { box.classList.add("hidden"); return; }
    try { paint(await api("/api/cache")); box.classList.remove("hidden"); } catch { box.classList.add("hidden"); }
  }

  async function run(path, body, question) {
    if (question && !(await Confirm.ask({ title: "Delete songs from the cache?", message: question, ok: "🗑 Delete" }))) return;
    try {
      const res = await api(path, { method: "POST", body });
      const n = res.evicted.length;
      toast(n ? `Deleted ${n} song${n === 1 ? "" : "s"}, freed ${gb(res.freed)}` : "Nothing to delete");
      paint(res.stats);
    } catch (err) { fail(err); }
  }

  part("trim").onclick = () => run("/api/cache/trim");
  part("warm").onclick = () => run("/api/cache/clear", { what: "warm" }, "Delete every warmed-up song nobody has played yet?");
  part("all").onclick = () => run("/api/cache/clear", { what: "all" },
    "Delete every cached song that isn't playing or queued? They are downloaded and processed again when someone picks them.");
  Auth.onChange(refresh);
  refresh();
  return Object.assign(box, { refresh });
}
