// Guest phone: the queue with your own songs highlighted and their controls — swap among your
// own songs (never ahead of anyone else), remove them, and per song the singing mode and the
// guide-vocal volume the control panel uses when it plays. Needs common.js, auth.js, lyrics.js.
const MODE_CHOICES = [["", "🎮 Host's choice"], ["party", "✨ Party"], ["score", "🏆 Score"], ["battle", "⚔️ Battle (2 mics)"]];
let lastQueue = [], dragging = false;
let queueFilter = "all"; // "all" | "mine"

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
  const cls = isTranscribed
    ? "bg-amber-900/80 text-amber-200 ring-1 ring-amber-500/50"
    : "bg-white/10 text-stone-200";
  return iconButton(label, title, () => openLyrics(e), cls);
}

function setQueueFilter(f) {
  queueFilter = f;
  const isAll = f === "all";
  $("qfilter-all")?.classList.toggle("bg-amber-400", isAll);
  $("qfilter-all")?.classList.toggle("text-stone-950", isAll);
  $("qfilter-all")?.classList.toggle("bg-white/10", !isAll);
  $("qfilter-all")?.classList.toggle("text-stone-300", !isAll);

  $("qfilter-mine")?.classList.toggle("bg-amber-400", !isAll);
  $("qfilter-mine")?.classList.toggle("text-stone-950", !isAll);
  $("qfilter-mine")?.classList.toggle("bg-white/10", isAll);
  $("qfilter-mine")?.classList.toggle("text-stone-300", isAll);
  renderQueue();
}

$("qfilter-all")?.addEventListener("click", () => setQueueFilter("all"));
$("qfilter-mine")?.addEventListener("click", () => setQueueFilter("mine"));

function renderQueue(queue = lastQueue) {
  lastQueue = queue;
  if (dragging) return;   // don't redraw under the finger; the save redraws it
  const { admin } = Auth.me;
  const mine = queue.filter(Auth.owns);

  if ($("queue-count")) $("queue-count").textContent = queue.length;
  if ($("queue-mine-count")) $("queue-mine-count").textContent = mine.length;
  const badge = $("tab-queue-badge");
  if (badge) {
    badge.textContent = queue.length;
    badge.className = `ml-1 rounded-full px-2 py-0.5 text-xs font-mono font-bold ${
      queue.length > 0 ? "bg-amber-400 text-stone-950" : "bg-white/10 text-stone-300"
    }`;
  }

  const items = queueFilter === "mine" ? mine : queue;
  const empty = $("queue-empty");
  if (empty) {
    empty.classList.toggle("hidden", items.length > 0);
    if (items.length === 0) {
      if (queue.length === 0) {
        if ($("empty-title")) $("empty-title").textContent = "Nobody in line";
        if ($("empty-sub")) $("empty-sub").textContent = "Be the first to queue a song!";
      } else {
        if ($("empty-title")) $("empty-title").textContent = "No songs queued by you";
        if ($("empty-sub")) $("empty-sub").textContent = `There are ${queue.length} other songs waiting in line.`;
      }
    }
  }

  $("queue")?.replaceChildren(...items.map((e) => {
    const own = Auth.owns(e);
    const canManage = admin || own;
    const pos = mine.indexOf(e);
    const idx = queue.indexOf(e);
    const row = queueRow(e, idx, queue.length, {
      thumb: false,
      extras: [lyricsActionBtn(e)],
      manage: admin ? "all" : own ? "mine" : null,
      first: admin ? idx === 0 : pos === 0,
      last: admin ? idx === queue.length - 1 : pos === mine.length - 1,
    });
    if (own) {
      row.classList.replace("ring-white/5", "ring-amber-400/60"); // yours stand out
    }
    if (canManage) {
      row.lastChild.append(songPrefs(e));
    }
    return row;
  }));
}
