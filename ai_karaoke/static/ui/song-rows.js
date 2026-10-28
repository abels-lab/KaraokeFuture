// The song lines of the search panel (ui/search-panel.js): one search result or ready song with
// its Add button, and the "Good luck" surprise card. Same look as the guest remote.
// Needs common.js (el, fmt, thumbFor) and ui/ready-songs.js (ReadySongs.name).
// SongRows.result(song, onAdd(song, button)) -> <li>; SongRows.lucky(song, onAdd, onDismiss) -> [header, body]
const SongRows = (() => {
  const thumb = (s, cls) => Object.assign(el("img", `${cls} shrink-0 rounded-lg object-cover`),
    { src: s.thumbnail || thumbFor(s.id), alt: "", loading: "lazy" });

  function addButton(song, onAdd, cls) {
    const btn = el("button", `btn-gold shrink-0 rounded-lg ${cls}`, "Add");
    btn.type = "button";
    btn.onclick = () => onAdd(song, btn);
    return btn;
  }

  function result(r, onAdd) {
    const li = el("li", "panel flex items-center gap-3 p-2");
    const info = el("div", "min-w-0 flex-1");
    const meta = [r.cached ? "⚡ Instant" : "", r.genre || "", r.decade || "",
      r.source === "soundcloud" ? "SoundCloud" : (!r.genre ? r.channel : ""),
      r.duration ? fmt(r.duration) : ""].filter(Boolean);
    info.append(el("p", "line-clamp-2 text-sm font-semibold", ReadySongs.name(r)),
      el("p", "truncate text-xs text-stone-400", meta.join(" · ")));
    li.append(thumb(r, "h-14 w-20"), info, addButton(r, onAdd, "px-3 py-2 text-sm"));
    return li;
  }

  function lucky(song, onAdd, onDismiss) {
    const header = el("div", "mb-1 flex items-center justify-between text-xs font-bold text-amber-300");
    const x = el("button", "px-1 text-stone-400 hover:text-stone-200", "✕");
    Object.assign(x, { type: "button", title: "Hide", onclick: onDismiss });
    header.append(el("span", "flex items-center gap-1", "🎲 Accidental Song Pick"), x);
    const body = el("div", "flex items-center gap-3");
    const info = el("div", "min-w-0 flex-1");
    info.append(el("p", "truncate text-sm font-bold text-amber-100", ReadySongs.name(song)),
      el("p", "truncate text-xs text-stone-400",
        [song.genre, song.decade, "⚡ Instant", song.duration ? fmt(song.duration) : ""].filter(Boolean).join(" · ")));
    body.append(thumb(song, "h-14 w-20"), info, addButton(song, onAdd, "px-3 py-1.5 text-xs font-bold"));
    return [header, body];
  }

  return { result, lucky };
})();
