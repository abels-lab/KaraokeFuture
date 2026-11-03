// Guest phone: the queue with your own songs highlighted and their controls — swap among your
// own songs (never ahead of anyone else), remove them, and per song the singing mode and the
// guide-vocal volume the control panel uses when it plays. The ＋ in the empty-queue card opens
// the search popup (guest/app.js). Below the line: the Auto-DJ playlist's queue (ui/autodj-box.js;
// guests may claim a song from it, the host also manages playlists), hidden under "Played".
// Needs common.js, ui/queue-rows.js, auth.js, lyrics.js, remote-battle.js, guest/overlay-back.js, ui/autodj-box.js.
// renderQueue(queue, played, activePlaylist) with every "state" message; songPrefs(entry).
const MODE_CHOICES = [["", "🎮 Host's choice"], ["party", "✨ Party"], ["score", "🏆 Score"], ["battle", "⚔️ Battle / Duet (2 mics)"]];
let lastQueue = [], lastPlayed = [], lastAutoDj = null, dragging = false;
const autoDjBox = createAutoDjBox({ singer: () => store("host_singer") || "" });   // same name as the search popup
$("autodj-mount")?.append(autoDjBox);
let queueFilter = "all"; // "all" | "mine" | "played"

const savePrefs = (e, changes) => {
  Object.assign(e, changes);
  return api(`/api/queue/${e.uid}`, {
    method: "PATCH",
    body: { guide: e.guide !== undefined ? e.guide : null, mode: e.mode || null, ...changes }
  }).then(() => toast("Saved song settings")).catch(fail);
};

// Mode picker + guide slider for one queue entry (adjustable before song starts)
function songPrefs(e) {
  const box = el("div", "flex flex-wrap items-center gap-2 pt-1 text-xs text-stone-300");
  const mode = el("select", "rounded-lg bg-white/10 px-2 py-1 text-xs outline-none");
  mode.title = "Singing mode: party (friendly scoring), score (real pitch), battle (2 mics)";
  for (const [value, label] of MODE_CHOICES) mode.append(Object.assign(el("option", "bg-stone-900", label), { value }));
  mode.value = e.mode || "";
  mode.onchange = () => savePrefs(e, { mode: mode.value || null });

  const guideVal = Number.isFinite(e.guide) ? e.guide : Settings.get("guide_default", 20);
  const slider = Object.assign(el("input", "min-w-[5rem] flex-1 accent-amber-400"),
    { type: "range", min: 0, max: 100, step: 5, value: guideVal });
  slider.title = "Guide vocals: volume of the original singer (0% = mute, 100% = full)";
  const shown = el("span", "w-11 text-right font-mono font-semibold", Number.isFinite(e.guide) ? `${e.guide}%` : "default");
  slider.oninput = () => { dragging = true; shown.textContent = `${slider.value}%`; };
  slider.onchange = () => { dragging = false; savePrefs(e, { guide: Number(slider.value) }); };
  const reset = iconButton("↺", "Reset to host default volume", () => {
    delete e.guide;
    slider.value = Settings.get("guide_default", 20);
    shown.textContent = "default";
    savePrefs(e, { guide: null });
  });
  reset.disabled = !Number.isFinite(e.guide);
  box.append(mode, el("span", "", "🗣"), slider, shown, reset);
  return box;
}

function lyricsActionBtn(e) {
  const isTranscribed = needsLyrics(e);
  const isAdmin = Boolean(Auth.me?.admin);
  const label = isAdmin ? (isTranscribed ? "📝 Fix" : "📝 Lyrics") : "📖 Lyrics";
  const title = isAdmin ? (isTranscribed ? "Fix AI-transcribed lyrics" : "Edit lyrics") : "View lyrics";
  const cls = isTranscribed ? "bg-amber-900/80 text-amber-200 ring-1 ring-amber-500/50" : "bg-white/10 text-stone-200";
  return iconButton(label, title, () => GuestOverlay.open(() => openLyrics(e)), cls);   // Back closes it
}

// Filter pills: All in line / My songs / Already played
const FILTER_ON = ["bg-amber-400", "text-stone-950"], FILTER_OFF = ["bg-white/10", "text-stone-300"];
function setQueueFilter(f) {
  queueFilter = f;
  for (const name of ["all", "mine", "played"]) {
    const b = $(`qfilter-${name}`);
    b?.classList.remove(...FILTER_ON, ...FILTER_OFF);
    b?.classList.add(...(name === f ? FILTER_ON : FILTER_OFF));
    b?.setAttribute("aria-pressed", String(name === f));
  }
  renderQueue();
}
for (const name of ["all", "mine", "played"]) $(`qfilter-${name}`)?.addEventListener("click", () => setQueueFilter(name));

function setEmpty(show, title, sub) {
  $("queue-empty")?.classList.toggle("hidden", !show);
  if (!show) return;
  $("empty-title").textContent = title;
  $("empty-sub").textContent = sub;
}

function renderQueue(queue = lastQueue, played = lastPlayed, autoDj = lastAutoDj) {
  lastQueue = queue;
  lastPlayed = played;
  lastAutoDj = autoDj;
  if (dragging) return;   // don't redraw under the finger; the save redraws it
  const { admin } = Auth.me;
  const mine = queue.filter(Auth.owns);

  if ($("queue-count")) $("queue-count").textContent = queue.length;
  if ($("queue-mine-count")) $("queue-mine-count").textContent = mine.length;
  if ($("queue-played-count")) $("queue-played-count").textContent = played.length;
  const badge = $("tab-queue-badge");   // phone tab bar
  if (badge) {
    badge.textContent = queue.length;
    badge.className = `tab-badge ${queue.length ? "" : "hidden"} ${mine.length ? "bg-amber-400 text-stone-950" : "bg-white/20 text-stone-100"}`;
  }

  if (queueFilter === "played") {
    const revPlayed = [...played].reverse();
    setEmpty(!revPlayed.length, "No songs played yet", "Songs that finished singing will appear here.");
    $("queue")?.replaceChildren(...revPlayed.map((e, i) => playedRow(e, i)));
    autoDjBox.paint(autoDj, false);
    return;
  }

  const items = queueFilter === "mine" ? mine : queue;
  if (queue.length) setEmpty(!items.length, "No songs queued by you", `There are ${queue.length} other songs waiting in line.`);
  else if (autoDj) setEmpty(true, "Auto-DJ is on", `Playing from ${autoDj.name} while nobody is in line. Claim a song below or find one to sing next!`);
  else setEmpty(true, "Nobody in line", "Be the first to queue a song!");
  autoDjBox.paint(autoDj);

  $("queue")?.replaceChildren(...items.map((e) => {
    const own = Auth.owns(e);
    const canManage = admin || own;
    const pos = mine.indexOf(e);
    const idx = queue.indexOf(e);
    const row = queueRow(e, idx, queue.length, {
      thumb: false,
      extras: [...Battle.controls(e), lyricsActionBtn(e)],   // join / leave a battle (remote-battle.js)
      manage: admin ? "all" : own ? "mine" : null,
      first: admin ? idx === 0 : pos === 0,
      last: admin ? idx === queue.length - 1 : pos === mine.length - 1,
    });
    if (own) row.classList.replace("ring-white/5", "ring-amber-400/60"); // yours stand out
    if (canManage) row.lastChild.append(songPrefs(e));
    return row;
  }));
}
setQueueFilter("all");
