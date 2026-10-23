// Song library: every cached song + lyrics source, with queue / edit / re-sync / rebuild / delete.
let songs = [], refreshTimer = null;
const GB = 1024 ** 3, MB = 1024 ** 2;

async function refresh() {
  try {
    const data = await api("/api/library");
    songs = data.songs;
    $("storage-text").textContent =
      `${(data.used / GB).toFixed(2)} GB of ${(data.limit / GB).toFixed(0)} GB · ${songs.length} song${songs.length === 1 ? "" : "s"}`;
    $("storage-bar").style.width = `${Math.min(100, (data.used / data.limit) * 100)}%`;
    render();
  } catch (err) { fail(err); }
}
const refreshSoon = () => { clearTimeout(refreshTimer); refreshTimer = setTimeout(refresh, 300); };

function render() {
  const q = $("filter").value.trim().toLowerCase();
  const shown = songs.filter((s) => !q || `${s.title} ${s.channel}`.toLowerCase().includes(q));
  $("empty").classList.toggle("hidden", shown.length > 0);
  $("songs").replaceChildren(...shown.map(card));
}

const badge = (text, cls) => el("span", `rounded-full px-2 py-0.5 text-[11px] font-semibold ${cls}`, text);

function action(label, title, onclick, { disabled = false, cls = "bg-white/10 hover:bg-white/20" } = {}) {
  const b = el("button", `rounded-lg px-2.5 py-1.5 text-xs font-semibold disabled:opacity-30 ${cls}`, label);
  return Object.assign(b, { title, onclick, disabled });
}

function card(s) {
  const busy = Boolean(s.stage), usable = s.ready && !busy;
  const info = el("div", "min-w-0 flex-1");
  const tags = el("div", "mt-1.5 flex flex-wrap gap-1");
  const [srcLabel, srcCls] = LYRICS_SOURCE[s.lyrics_source] || ["No lyrics", "bg-white/10"];
  if (s.ready) tags.append(badge(`${srcLabel}${s.lyric_lines ? ` · ${s.lyric_lines} lines` : ""}`, srcCls));
  if (s.has_video) tags.append(badge("🎬 Video", "bg-white/10 text-stone-200"));
  if (s.source === "soundcloud" || s.fallback_used) tags.append(badge(s.source === "soundcloud" ? "☁ SoundCloud" : "↺ Backup upload", "bg-white/10 text-stone-200"));
  if (s.warmed) tags.append(badge("🔥 Prepared in advance", "bg-violet-900/70 text-violet-200"));
  if (s.ready && s.timing_poor) { // words don't line up with the singing
    const warn = badge("⏱ Timing unreliable", "cursor-pointer bg-red-900/80 text-red-100");
    warn.title = "The lyrics don't line up with the singing. Paste LRC lyrics with [mm:ss] timestamps to fix it. Click to edit.";
    warn.onclick = () => openLyrics(s);
    tags.append(warn);
  }
  const missing = s.unmatched_vocals.reduce((sum, [a, b]) => sum + b - a, 0);
  if (s.ready && missing) { // sung parts no lyric line covers: probably missing lines
    const warn = badge(`⚠ ${Math.round(missing)} s sung without lyrics`, "cursor-pointer bg-orange-900/80 text-orange-100");
    warn.title = `Singing but no lyrics at ${s.unmatched_vocals.map(([a, b]) => `${fmt(a)}–${fmt(b)}`).join(", ")}. Click to edit.`;
    warn.onclick = () => openLyrics(s);
    tags.append(warn);
  }
  if (busy) { const [l, c] = STATUS[s.stage] || [s.stage, "bg-stone-600"]; tags.append(badge(`⏳ ${l}`, c)); }
  else if (!s.ready) tags.append(badge("Incomplete", "bg-red-800"));
  if (s.playing) tags.append(badge("▶ Playing", "bg-emerald-700"));
  else if (s.in_queue) tags.append(badge("In queue", "bg-sky-800"));
  info.append(
    el("h3", "line-clamp-2 font-semibold leading-snug", s.title),
    el("p", "truncate text-xs text-stone-400",
      [s.channel, s.duration ? fmt(s.duration) : "", `${Math.round(s.size / MB)} MB`].filter(Boolean).join(" · ")),
    tags);

  const top = el("div", "flex gap-3");
  top.append(Object.assign(el("img", "h-20 w-28 shrink-0 rounded-lg object-cover"),
    { src: s.thumbnail || thumbFor(s.id), alt: "", loading: "lazy" }), info);

  const actions = el("div", "flex flex-wrap gap-1.5");
  actions.append(action("🎤 Queue", "Add to the queue", () => queueSong(s), { disabled: !usable, cls: "btn-gold" }));
  if (!Auth.me.admin) { // guests look; the song tools are the host's (the server checks too)
    actions.append(action("📖 Lyrics", "Read the lyrics", () => openLyrics(s), { disabled: !usable }));
    const c = el("article", "panel flex flex-col gap-3 p-3");
    c.append(top, actions);
    return c;
  }
  actions.append(
    action("📝 Lyrics", "View and edit the lyrics", () => openLyrics(s), { disabled: !usable }),
    action("↻ Re-sync", "Sync the current lyrics text to the vocals again", () => regenerate(s, "lyrics"), { disabled: !usable }));
  if (s.has_user_lyrics) {
    actions.append(action("🌐 Auto lyrics", "Forget the pasted lyrics; search online or transcribe again",
      () => regenerate(s, "lyrics", true), { disabled: !usable }));
  }
  if (s.ready && !s.has_video) {
    actions.append(action("🎬 Get video", "Download the music video to play behind the lyrics",
      () => regenerate(s, "video"), { disabled: busy }));
  }
  actions.append(
    action("⟳ Rebuild", "Download, separate vocals and sync lyrics again from scratch",
      () => regenerate(s, "all"), { disabled: busy || s.playing }),
    action("🗑", "Delete from the cache", () => removeSong(s),
      { disabled: busy || s.in_queue, cls: "bg-white/10 hover:bg-red-800" }));

  const c = el("article", "panel flex flex-col gap-3 p-3");
  c.append(top, actions);
  return c;
}

// Guests queue as themselves; the host may type any singer name (empty = their own login)
async function queueSong(s) {
  const { admin, guest } = Auth.me;
  const name = admin ? $("singer").value.trim() || guest?.name || "" : guest?.name || "";
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

async function removeSong(s) {
  if (!confirm(`Delete “${s.title}” from the cache (${Math.round(s.size / MB)} MB)?`)) return;
  const forgetLyrics = s.has_user_lyrics &&
    confirm("Also forget its pasted lyrics?\nOK = forget them · Cancel = keep them for next time");
  try {
    await api(`/api/songs/${s.id}?lyrics=${forgetLyrics}`, { method: "DELETE" });
    toast(`Deleted “${s.title}”`);
    refreshSoon();
  } catch (err) { fail(err); }
}

$("filter").oninput = render;
$("header").insertBefore(hostBadge(), $("header").querySelector("a"));
Auth.onChange(({ admin }) => { $("singer-box").classList.toggle("hidden", !admin); render(); });
$("singer").value = store("singer") || "";
$("singer").oninput = () => store("singer", $("singer").value.trim());
connectWS("remote", (msg) => { if (["state", "library", "media"].includes(msg.type)) refreshSoon(); });
refresh();
