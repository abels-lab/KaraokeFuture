// One song card of the library panel (ui/library-panel.js): picture, title, size, badges
// (lyrics source, video, warnings, processing stage, queued / playing) and its buttons.
// Guests get Queue + read lyrics; the host also re-sync / auto lyrics / get video / rebuild /
// delete (the server checks too). The buttons call back; the work lives in the panel.
// Needs common.js (el, fmt, thumbFor, STATUS, LYRICS_SOURCE), auth.js.
// LibraryCard.card(song, { queue(s), lyrics(s), regenerate(s, target, reset), remove(s) }) -> <article>
const LibraryCard = (() => {
  const MB = 1024 ** 2;
  const badge = (text, cls) => el("span", `rounded-full px-2 py-0.5 text-[11px] font-semibold ${cls}`, text);

  function action(label, title, onclick, { disabled = false, cls = "bg-white/10 hover:bg-white/20" } = {}) {
    const b = el("button", `rounded-lg px-2.5 py-1.5 text-xs font-semibold disabled:opacity-30 ${cls}`, label);
    return Object.assign(b, { type: "button", title, onclick, disabled });
  }

  // A red/orange badge that opens the lyrics editor: the lyrics need fixing
  function warning(text, cls, title, onclick) {
    const warn = badge(text, `cursor-pointer ${cls}`);
    Object.assign(warn, { title, onclick });
    return warn;
  }

  function tags(s, on) {
    const box = el("div", "mt-1.5 flex flex-wrap gap-1");
    const busy = Boolean(s.stage);
    const [srcLabel, srcCls] = LYRICS_SOURCE[s.lyrics_source] || ["No lyrics", "bg-white/10"];
    if (s.ready) box.append(badge(`${srcLabel}${s.lyric_lines ? ` · ${s.lyric_lines} lines` : ""}`, srcCls));
    if (s.has_video) box.append(badge("🎬 Video", "bg-white/10 text-stone-200"));
    if (s.custom) box.append(badge(s.source === "upload" ? "📁 Custom upload" : "🔗 Custom link", "bg-amber-500/20 text-amber-300 ring-1 ring-amber-400/40"));
    if (s.source === "soundcloud" || s.fallback_used) box.append(badge(s.source === "soundcloud" ? "☁ SoundCloud" : "↺ Backup upload", "bg-white/10 text-stone-200"));
    if (s.warmed) box.append(badge("🔥 Prepared in advance", "bg-violet-900/70 text-violet-200"));
    if (s.ready && s.timing_poor) { // words don't line up with the singing
      box.append(warning("⏱ Timing unreliable", "bg-red-900/80 text-red-100",
        "The lyrics don't line up with the singing. Paste LRC lyrics with [mm:ss] timestamps to fix it. Click to edit.", () => on.lyrics(s)));
    }
    const missing = s.unmatched_vocals.reduce((sum, [a, b]) => sum + b - a, 0);
    if (s.ready && missing) { // sung parts no lyric line covers: probably missing lines
      box.append(warning(`⚠ ${Math.round(missing)} s sung without lyrics`, "bg-orange-900/80 text-orange-100",
        `Singing but no lyrics at ${s.unmatched_vocals.map(([a, b]) => `${fmt(a)}–${fmt(b)}`).join(", ")}. Click to edit.`, () => on.lyrics(s)));
    }
    if (busy) { const [l, c] = STATUS[s.stage] || [s.stage, "bg-stone-600"]; box.append(badge(`⏳ ${l}`, c)); }
    else if (!s.ready) box.append(badge("Incomplete", "bg-red-800"));
    if (s.playing) box.append(badge("▶ Playing", "bg-emerald-700"));
    else if (s.in_queue) box.append(badge("In queue", "bg-sky-800"));
    return box;
  }

  function hostActions(s, on, busy, usable) {
    const out = [
      action("📝 Lyrics", "View and edit the lyrics", () => on.lyrics(s), { disabled: !usable }),
      action("↻ Re-sync", "Sync the current lyrics text to the vocals again", () => on.regenerate(s, "lyrics"), { disabled: !usable })];
    if (s.has_user_lyrics) {
      out.push(action("🌐 Auto lyrics", "Forget the pasted lyrics; search online or transcribe again",
        () => on.regenerate(s, "lyrics", true), { disabled: !usable }));
    }
    if (s.ready && !s.has_video) {
      out.push(action("🎬 Get video", "Download the music video to play behind the lyrics",
        () => on.regenerate(s, "video"), { disabled: busy }));
    }
    out.push(
      action("⟳ Rebuild", "Download, separate vocals and sync lyrics again from scratch",
        () => on.regenerate(s, "all"), { disabled: busy || s.playing }),
      action("🗑", "Delete from the cache", () => on.remove(s),
        { disabled: busy || s.in_queue, cls: "bg-white/10 hover:bg-red-800" }));
    return out;
  }

  function card(s, on) {
    const busy = Boolean(s.stage), usable = s.ready && !busy;
    const info = el("div", "min-w-0 flex-1");
    info.append(
      el("h3", "line-clamp-2 font-semibold leading-snug", s.title),
      el("p", "truncate text-xs text-stone-400",
        [s.channel, s.duration ? fmt(s.duration) : "", `${Math.round(s.size / MB)} MB`].filter(Boolean).join(" · ")),
      tags(s, on));
    const top = el("div", "flex gap-3");
    top.append(Object.assign(el("img", "h-20 w-28 shrink-0 rounded-lg object-cover"),
      { src: s.thumbnail || thumbFor(s.id), alt: "", loading: "lazy" }), info);

    const actions = el("div", "flex flex-wrap gap-1.5");
    actions.append(action("🎤 Queue", "Add to the queue", () => on.queue(s), { disabled: !usable, cls: "btn-gold" }));
    if (Auth.me.admin) actions.append(...hostActions(s, on, busy, usable));
    else actions.append(action("📖 Lyrics", "Read the lyrics", () => on.lyrics(s), { disabled: !usable })); // guests look
    const c = el("article", "panel flex flex-col gap-3 p-3");
    c.append(top, actions);
    return c;
  }

  return { card };
})();
