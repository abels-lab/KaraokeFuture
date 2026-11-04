// The host's Auto-DJ playlists, as a popup on either single-page app: every playlist (the
// built-in weekly / top hits and the party's own), ▶ Play one as the low-priority filler for
// when nobody is in line, ⏹ Stop it, and ➕ New / ✏️ Edit / 🗑️ Delete the party's own playlists
// (the form opens as a second popup on top: ui/playlist-form.js). ui/popup.js handles Back / Esc.
// Only the host may change them (the API refuses guests); listing is open to everyone.
// Needs common.js, ui/popup.js, ui/playlist-form.js. Opens no WebSocket.
// Playlists.open() shows the manager (one at a time).
const Playlists = (() => {
  const root = el("div", "space-y-3");
  const list = el("div", "space-y-2");
  const btn = (label, cls, onclick, title = "") => Object.assign(
    el("button", `tap rounded-lg px-2.5 py-1 text-xs font-semibold transition ${cls}`, label), { type: "button", onclick, title });
  const top = el("div", "flex flex-wrap items-center justify-between gap-2");
  top.append(el("p", "min-w-0 flex-1 text-xs text-stone-300", "Playlists fill dead air when the queue is empty, or keep your own party collections."),
    btn("➕ New playlist", "btn-gold font-bold", () => PlaylistForm.open(null, reload)));
  const foot = el("div", "flex justify-end border-t border-white/10 pt-3");
  foot.append(btn("⏹ Stop Auto-DJ", "bg-rose-500/20 font-bold text-rose-300 hover:bg-rose-500/30", async () => {
    try { await api("/api/playlists/stop", { method: "POST" }); toast("Auto-DJ playlist stopped"); popup?.close(); } catch (err) { fail(err); }
  }));
  root.append(top, list, foot);
  let popup = null;

  const note = (text, cls = "text-stone-400") => el("p", `p-4 text-center text-xs ${cls}`, text);
  const pill = (text, cls) => el("span", `rounded-full px-2 py-0.5 text-[10px] font-bold ${cls}`, text);

  function card(pl, activeId) {
    const current = pl.id === activeId;
    const box = el("div", `flex flex-col gap-2.5 rounded-xl border p-3 text-xs transition sm:flex-row sm:items-center ${
      current ? "border-amber-400/50 bg-amber-400/15" : "border-white/10 bg-white/5 hover:border-white/20"}`);
    const info = el("div", "min-w-0 flex-1 space-y-1");
    const name = el("div", "flex flex-wrap items-center gap-1.5");
    name.append(el("span", "min-w-0 truncate text-sm font-bold text-stone-100", pl.name));
    if (current) name.append(pill("Playing", "bg-emerald-500/20 text-emerald-300"));
    name.append(pl.is_built_in ? pill(pl.rotation ? "Weekly rotation" : "Built-in", "bg-white/10 font-normal text-stone-300")
      : pill("Custom", "bg-amber-400/20 text-amber-300"));
    info.append(name, el("p", "line-clamp-1 text-[11px] text-stone-400", pl.description || ""),
      el("p", "font-mono text-[10px] text-stone-500", `${pl.count || 0} songs`));

    const actions = el("div", "flex shrink-0 flex-wrap items-center justify-end gap-1.5");
    if (!pl.is_built_in) {
      actions.append(btn("✏️ Edit", "bg-white/10 text-stone-200 hover:bg-white/20", async () => {
        try { PlaylistForm.open(await api(`/api/playlists/${encodeURIComponent(pl.id)}`), reload); } catch (err) { fail(err); }
      }, "Edit the name and songs"), btn("🗑️", "bg-red-500/15 text-red-300 hover:bg-red-500/25", async () => {
        if (!(await Confirm.ask({ title: "Delete playlist?", message: `Delete the playlist “${pl.name}”? Its songs stay in the library.`, ok: "🗑 Delete playlist" }))) return;
        try { await api(`/api/playlists/${encodeURIComponent(pl.id)}`, { method: "DELETE" }); toast(`Deleted "${pl.name}"`); reload(); } catch (err) { fail(err); }
      }, `Delete "${pl.name}"`));
    }
    actions.append(btn(current ? "Active (restart)" : "▶ Play", current ? "bg-amber-400/20 font-bold text-amber-200 hover:bg-amber-400/30"
      : "btn-gold font-bold", async () => {
      try {
        await api(`/api/playlists/${encodeURIComponent(pl.id)}/play`, { method: "POST" });
        toast(`Auto-DJ started with "${pl.name}"!`);
        popup?.close();
      } catch (err) { fail(err); }
    }));
    box.append(info, actions);
    return box;
  }

  async function reload() {
    if (!list.children.length) list.replaceChildren(note("Loading playlists…"));
    try {
      const data = await api("/api/playlists");
      const all = data.playlists || [];
      list.replaceChildren(...(all.length ? all.map((pl) => card(pl, data.active_playlist?.id)) : [note("No playlists yet.")]));
    } catch (err) { list.replaceChildren(note(err.message || String(err), "text-rose-400")); }
  }

  function open() {
    if (popup) return;
    list.replaceChildren();
    reload();
    popup = Popup.open({ title: "📻 Playlists & Auto-DJ", content: root, size: "md", onClose: () => { popup = null; } });
  }
  return { open };
})();
