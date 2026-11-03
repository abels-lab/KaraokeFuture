// Create or edit one of the party's own Auto-DJ playlists: a name, a short description and the
// songs, one per line ("Artist - Song title" or any search words; the server finds the karaoke
// track in the library or downloads it when its turn comes). Opens as a popup on top of the
// playlists manager (ui/playlists-panel.js); Save / Cancel / Back close it. Host only (the API).
// Needs common.js, ui/popup.js. Opens no WebSocket.
// PlaylistForm.open(playlist | null, onSaved()) -> null makes a new playlist.
const PlaylistForm = (() => {
  const root = el("form", "space-y-3");
  root.innerHTML = `
    <label class="block"><span class="mb-1 block text-xs font-semibold text-stone-300">Playlist name *</span>
      <input data-k="name" maxlength="100" required placeholder="e.g. 90s Rock Classics"
             class="w-full rounded-xl border border-white/10 bg-black/50 px-3 py-2 text-sm outline-none focus:border-amber-400"></label>
    <label class="block"><span class="mb-1 block text-xs font-semibold text-stone-300">Description</span>
      <input data-k="desc" maxlength="500" placeholder="A note or theme (optional)"
             class="w-full rounded-xl border border-white/10 bg-black/50 px-3 py-2 text-xs outline-none focus:border-amber-400"></label>
    <label class="block"><span class="mb-1 flex items-center justify-between text-xs font-semibold text-stone-300">Songs, one per line *
        <span data-k="count" class="font-mono text-[11px] font-normal text-stone-400">0 song(s)</span></span>
      <textarea data-k="songs" rows="8" placeholder="Queen - Bohemian Rhapsody&#10;Bon Jovi - Livin' on a Prayer&#10;Nirvana - Smells Like Teen Spirit"
             class="w-full resize-y rounded-xl border border-white/10 bg-black/50 p-2.5 font-mono text-xs outline-none focus:border-amber-400"></textarea>
      <span class="mt-1 block text-[10px] text-stone-400">Format: <code>Artist - Song title</code> or search words. Tracks come from the library or are downloaded when needed.</span></label>
    <div class="flex justify-end gap-2 border-t border-white/10 pt-3 text-xs">
      <button data-k="cancel" type="button" class="tap rounded-lg bg-white/10 px-3 py-2 font-semibold text-stone-300 hover:bg-white/20">Cancel</button>
      <button data-k="save" class="tap btn-gold rounded-lg px-4 py-2 font-bold">💾 Save playlist</button>
    </div>`;
  const part = (k) => root.querySelector(`[data-k="${k}"]`);
  const lines = () => part("songs").value.split("\n").map((l) => l.trim()).filter(Boolean);
  const count = () => { part("count").textContent = `${lines().length} song(s)`; };
  part("songs").oninput = count;
  let editing = null, popup = null, saved = null;
  part("cancel").onclick = () => popup?.close();

  const songLine = (s) => (typeof s === "string" ? s : s.artist && s.title ? `${s.artist} - ${s.title}` : s.title || s.query || "");

  root.onsubmit = async (e) => {
    e.preventDefault();
    const name = part("name").value.trim(), songs = lines(), description = part("desc").value.trim();
    if (!name) { toast("Give the playlist a name", false); part("name").focus(); return; }
    if (!songs.length) { toast("Add at least one song", false); part("songs").focus(); return; }
    part("save").disabled = true;
    try {
      if (editing) {
        await api(`/api/playlists/${encodeURIComponent(editing)}`, { method: "PUT", body: { name, description, songs, action: "set" } });
        toast(`Updated "${name}"!`);
      } else {
        await api("/api/playlists", { method: "POST", body: { name, description, songs } });
        toast(`Created "${name}"!`);
      }
      popup?.close();
      saved?.();
    } catch (err) { fail(err); }
    part("save").disabled = false;
  };

  function open(playlist = null, onSaved = null) {
    if (popup) return;
    editing = playlist?.id || null;
    saved = onSaved;
    part("name").value = playlist?.name || "";
    part("desc").value = playlist?.description || "";
    part("songs").value = (playlist?.songs || []).map(songLine).filter(Boolean).join("\n");
    count();
    popup = Popup.open({ title: playlist ? `✏️ Edit: ${playlist.name}` : "✏️ New playlist", content: root, size: "md",
      onClose: () => { popup = null; } });
    if (!matchMedia("(pointer: coarse)").matches) part("name").focus();
  }
  return { open };
})();
