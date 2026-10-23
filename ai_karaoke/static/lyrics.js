// Lyrics editor dialog (phones + library). Opens pre-filled with the song's current text;
// saving stores it permanently and the worker re-syncs it to the vocals.
// Needs common.js (+ auth.js: read-only for anyone but the host; the server refuses them too).
// Exposes openLyrics(song), needsLyrics(entry), lyricsButton(entry).
const needsLyrics = (e) => e?.media?.lyrics_source === "transcribed";

const lyricsModal = (() => {
  const m = el("div", "fixed inset-0 z-40 hidden items-end justify-center bg-black/75 p-3 sm:items-center");
  m.innerHTML = `
    <form class="panel w-full max-w-xl space-y-3 p-4">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0"><h2 class="font-display text-xl font-bold text-gold">Edit lyrics</h2>
          <p data-k="song" class="truncate text-sm text-stone-300"></p></div>
        <span data-k="source" class="shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold"></span>
      </div>
      <textarea data-k="text" rows="14" maxlength="20000" placeholder="Paste the lyrics here — one sung line per line"
        class="w-full rounded-xl border border-white/10 bg-black/50 p-3 text-sm leading-relaxed outline-none focus:border-amber-400"></textarea>
      <p class="text-xs text-stone-400">Fix misheard words or paste lyrics from any site. They're synced to the
        singer's voice automatically and saved, so this song keeps them for good.</p>
      <div class="flex gap-2">
        <button type="button" data-k="clear" class="rounded-xl bg-white/10 px-4 py-3 text-sm font-semibold">Clear</button>
        <button type="button" data-k="cancel" class="flex-1 rounded-xl bg-white/10 py-3 font-semibold">Cancel</button>
        <button data-k="save" class="btn-gold flex-1 rounded-xl py-3">Save &amp; sync</button>
      </div>
    </form>`;
  document.body.append(m);
  const part = (k) => m.querySelector(`[data-k="${k}"]`);
  let song = null;
  const close = () => { m.classList.replace("flex", "hidden"); song = null; };

  part("cancel").onclick = close;
  part("clear").onclick = () => { part("text").value = ""; part("text").focus(); };
  m.onclick = (e) => { if (e.target === m) close(); };
  m.querySelector("form").onsubmit = async (e) => {
    e.preventDefault();
    if (!song) return;
    part("save").disabled = true;
    try {
      const { lines } = await api(`/api/lyrics/${song.id}`, { method: "POST", body: { text: part("text").value } });
      toast(`Saved — syncing ${lines} lines to the vocals…`);
      close();
    } catch (err) { fail(err); }
    part("save").disabled = false;
  };

  return async (target) => {
    song = { id: target.song_id || target.id, title: target.title };
    const host = typeof Auth === "undefined" || Auth.me.admin;   // only the host may change lyrics
    part("text").readOnly = !host;
    ["save", "clear"].forEach((k) => part(k).classList.toggle("hidden", !host));
    m.querySelector("h2").textContent = host ? "Edit lyrics" : "Lyrics (only the host can change them)";
    part("song").textContent = song.title;
    part("text").value = "Loading…";
    part("source").textContent = "";
    m.classList.replace("hidden", "flex");
    try {
      const data = await api(`/api/songs/${song.id}/lyrics`);
      const [label, color] = LYRICS_SOURCE[data.source] || ["No lyrics yet", "bg-white/10"];
      part("source").textContent = label;
      part("source").className = `shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${color}`;
      part("text").value = data.text;
    } catch { part("text").value = ""; }
    part("text").scrollTop = 0; // start reading at the first line; no focus, so phones keep the keyboard down
  };
})();

const openLyrics = (song) => lyricsModal(song);
const lyricsButton = (entry) => iconButton("📝", "Fix lyrics", () => openLyrics(entry), "bg-amber-900/60");
