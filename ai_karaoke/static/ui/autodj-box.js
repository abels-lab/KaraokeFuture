// The Auto-DJ playlist queue, shown below the singer queue on both apps. While the host runs a
// playlist its songs play (low priority) whenever nobody is in line; this card names the
// playlist, says how many songs are left and lists the next ones. "🎤 Sing this!" moves one
// into the singer queue: a guest's own song, or the host's under the host's singer name. The
// host also gets 🔀 Manage (ui/playlists-panel.js) and ⏹ Stop, and with no playlist running an
// idle card to pick one; guests see nothing then. Several boxes may exist (no page ids).
// Needs common.js, auth.js, ui/popup.js, ui/playlists-panel.js. Opens no WebSocket.
// createAutoDjBox({ max, compact, singer() }) -> element with .paint(activePlaylist, visible = true)
//   singer() -> the host's singer name for promoted songs (empty = "Host" / the host's login).
function createAutoDjBox({ max = 15, compact = false, singer = () => "" } = {}) {
  const root = el("div", "hidden");
  const small = compact ? "text-[10px]" : "text-[11px]";
  const btn = (label, cls, onclick, title = "") => Object.assign(
    el("button", `tap shrink-0 rounded-lg px-2.5 py-1 ${small} font-bold transition ${cls}`, label), { type: "button", onclick, title });
  const manageBtn = () => btn("🔀 Manage", "bg-white/10 text-stone-200 hover:bg-white/20", () => Playlists.open(), "Pick, create or edit playlists");
  const stopBtn = () => btn("⏹ Stop", "bg-rose-500/20 text-rose-300 hover:bg-rose-500/30", () =>
    api("/api/playlists/stop", { method: "POST" }).then(() => toast("Stopped the Auto-DJ playlist")).catch(fail), "Stop the Auto-DJ playlist");

  async function promote(item, button) {
    const name = item.title || item.query;
    const body = { query: item.query || item.title };
    if (Auth.me.admin && singer()) body.singer = singer();
    button.disabled = true;
    try {
      await api("/api/playlists/promote", { method: "POST", body });
      toast(`Added "${name}" to the singer queue!`);
    } catch (err) { fail(err); }
    button.disabled = false;
  }

  function songRow(item, i) {
    const row = el("li", "flex items-center gap-2 rounded-xl border border-white/5 bg-black/40 p-2 text-xs transition hover:border-amber-400/30");
    const text = el("div", "min-w-0 flex-1");
    text.append(el("p", "truncate font-semibold text-stone-200", item.title || item.query),
      el("p", "truncate text-[10px] text-stone-400", item.artist ? `${item.artist} · Auto-DJ` : "Auto-DJ filler"));
    const claim = btn(compact ? "🎤 Queue" : "🎤 Sing this!", "bg-amber-400/20 text-amber-300 hover:bg-amber-400/30", null,
      "Move this song into the singer queue to sing it next");
    claim.onclick = () => promote(item, claim);
    row.append(el("span", "w-5 shrink-0 text-center font-mono text-[10px] font-bold text-amber-400/80", String(i + 1)), text);
    if (Auth.me.admin || Auth.me.guest) row.append(claim);   // logged-out guests only look
    return row;
  }

  function active(pl) {
    const box = el("div", "space-y-2.5 rounded-2xl border border-amber-400/25 bg-amber-500/10 p-3");
    const head = el("div", "flex items-center gap-2 border-b border-amber-400/20 pb-2");
    const title = el("div", "min-w-0 flex-1");
    title.append(el("p", "truncate text-xs font-bold text-amber-300", `📻 Auto-DJ: ${pl.name}`),
      el("p", "truncate text-[10px] text-stone-400", `${pl.remaining} song(s) queued · plays when nobody is in line`));
    head.append(title, ...(Auth.me.admin ? [manageBtn(), stopBtn()]
      : [el("span", "shrink-0 rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-semibold text-stone-300", "Auto filler")]));
    const list = el("ul", `space-y-1.5 overflow-y-auto pr-1 ${compact ? "max-h-56" : "max-h-72"}`);
    list.append(...pl.queue.slice(0, max).map(songRow));
    box.append(head, list);
    if (pl.remaining > max) box.append(el("p", "pt-1 text-center text-[10px] italic text-stone-400", `+ ${pl.remaining - max} more songs in the playlist`));
    return box;
  }

  function idle() {
    const box = el("div", "space-y-2 rounded-2xl border border-dashed border-amber-400/30 bg-amber-400/5 p-3 text-xs");
    box.append(el("p", "font-bold text-amber-300", "📻 Auto-DJ: idle"));
    if (!compact) box.append(el("p", "text-stone-300", "No playlist is running. Pick or create one to play filler songs whenever nobody is waiting in line."));
    box.append(btn("▶ Select / manage playlists", "btn-gold", () => Playlists.open()));
    return box;
  }

  root.paint = (pl, visible = true) => {
    const has = Boolean(pl?.queue?.length);
    const show = visible && (has || Auth.me.admin);
    root.classList.toggle("hidden", !show);
    root.replaceChildren(...(show ? [has ? active(pl) : idle()] : []));
  };
  return root;
}
