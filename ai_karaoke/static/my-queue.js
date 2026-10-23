// Guest phone: the queue with your own songs highlighted and their controls — swap among your
// own songs (never ahead of anyone else), remove them, and per song the singing mode and the
// guide-vocal volume the control panel uses when it plays. Needs common.js, auth.js, lyrics.js.
const MODE_CHOICES = [["", "🎮 Host's choice"], ["party", "✨ Party"], ["score", "🏆 Score"], ["battle", "⚔️ Battle (2 mics)"]];
let lastQueue = [], dragging = false;

const savePrefs = (e, changes) =>
  api(`/api/queue/${e.uid}`, { method: "PATCH", body: { guide: e.guide ?? null, mode: e.mode ?? null, ...changes } })
    .then(() => toast("Saved for your song")).catch(fail);

// Mode picker + guide slider for one entry ("host" = the control panel's own setting)
function songPrefs(e) {
  const box = el("div", "flex flex-wrap items-center gap-2 pt-1 text-xs text-stone-300");
  const mode = el("select", "rounded-lg bg-white/10 px-2 py-1 text-xs");
  mode.title = "How this song is played: party (always a nice score), score (real pitch scoring), battle (two singers)";
  for (const [value, label] of MODE_CHOICES) mode.append(Object.assign(el("option", "bg-stone-900", label), { value }));
  mode.value = e.mode || "";
  mode.onchange = () => savePrefs(e, { mode: mode.value || null });
  const slider = Object.assign(el("input", "min-w-[5rem] flex-1"),
    { type: "range", min: 0, max: 100, step: 5, value: e.guide ?? Settings.get("guide_default", 20) });
  slider.title = "Guide vocals: how loud the original singer sings along";
  const shown = el("span", "w-10 text-right font-mono", e.guide == null ? "host" : `${e.guide}%`);
  slider.oninput = () => { dragging = true; shown.textContent = `${slider.value}%`; };
  slider.onchange = () => { dragging = false; savePrefs(e, { guide: Number(slider.value) }); };
  const reset = iconButton("↺", "Back to the host's guide volume", () => savePrefs(e, { guide: null }));
  reset.disabled = e.guide == null;
  box.append(mode, el("span", "", "🗣"), slider, shown, reset);
  return box;
}

function renderQueue(queue = lastQueue) {
  lastQueue = queue;
  if (dragging) return;   // don't redraw under the finger; the save redraws it
  const { admin } = Auth.me;
  const mine = queue.filter(Auth.owns);
  $("queue-count").textContent = queue.length;
  $("queue-empty").classList.toggle("hidden", queue.length > 0);
  $("queue").replaceChildren(...queue.map((e, i) => {
    const own = Auth.owns(e), pos = mine.indexOf(e);
    const row = queueRow(e, i, queue.length, {
      thumb: false, extras: admin && needsLyrics(e) ? [lyricsButton(e)] : [],
      manage: admin ? "all" : own ? "mine" : null, first: admin ? i === 0 : pos === 0,
      last: admin ? i === queue.length - 1 : pos === mine.length - 1,
    });
    if (own) {
      row.classList.replace("ring-white/5", "ring-amber-400/60"); // yours stand out
      row.lastChild.append(songPrefs(e));
    }
    return row;
  }));
}
