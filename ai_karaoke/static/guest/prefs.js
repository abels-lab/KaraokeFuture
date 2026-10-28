// Personal defaults for the songs this device adds: guide-vocal volume and singing mode. They
// live in this browser only (localStorage) and go to the server with the usual per-song
// PATCH /api/queue/{uid} right after a song is added, the same call the queue's own controls make.
// "Host default" / "Host's choice" (empty) send nothing, so the control panel decides as before.
// Needs common.js (api, store, toast, el, Settings).
// GuestPrefs.get() -> {guide: number|null, mode: string|null}; GuestPrefs.set(changes);
// GuestPrefs.applyTo(entry) after an add; GuestPrefs.editor() -> block of controls for ⚙.
const GuestPrefs = (() => {
  const MODES = [["", "🎮 Host's choice"], ["party", "✨ Party"], ["score", "🏆 Score"], ["battle", "⚔️ Battle / Duet (2 mics)"]];

  function get() {
    const guide = store("guest_default_guide");
    const mode = store("guest_default_mode");
    return { guide: guide !== null && guide !== "" && Number.isFinite(Number(guide)) ? Number(guide) : null,
             mode: MODES.some(([v]) => v && v === mode) ? mode : null };
  }

  function set({ guide, mode }) {
    if (guide !== undefined) store("guest_default_guide", guide === null ? "" : String(guide));
    if (mode !== undefined) store("guest_default_mode", mode || "");
  }

  // A song that starts at once (empty queue) is already locked for guests: say so gently
  async function applyTo(entry) {
    const { guide, mode } = get();
    if (!entry?.uid || (guide === null && !mode)) return;
    try {
      await api(`/api/queue/${entry.uid}`, { method: "PATCH", body: { guide, mode } });   // the WS "state" redraws
    } catch {
      toast("Your default song settings could not be applied to this one", false);
    }
  }

  function editor() {
    const box = el("div", "space-y-3");
    const { guide, mode } = get();
    const modeRow = el("label", "flex flex-wrap items-center justify-between gap-2 text-sm");
    const pick = el("select", "tap rounded-lg bg-white/10 px-2 py-1.5 text-sm outline-none");
    for (const [value, label] of MODES) pick.append(Object.assign(el("option", "bg-stone-900", label), { value }));
    pick.value = mode || "";
    pick.onchange = () => { set({ mode: pick.value || null }); toast("Saved for your next songs"); };
    modeRow.append(el("span", "text-stone-300", "Singing mode"), pick);

    const guideRow = el("div", "space-y-1 text-sm");
    const head = el("div", "flex items-center justify-between gap-2");
    const shown = el("span", "font-mono font-semibold", guide === null ? "host default" : `${guide}%`);
    head.append(el("span", "text-stone-300", "🗣 Guide vocals (original singer)"), shown);
    const slider = Object.assign(el("input", "w-full accent-amber-400"), { type: "range", min: 0, max: 100, step: 5,
      value: guide ?? Settings.get("guide_default", 20) });
    slider.setAttribute("aria-label", "Default guide-vocal volume");
    slider.oninput = () => { shown.textContent = `${slider.value}%`; };
    slider.onchange = () => { set({ guide: Number(slider.value) }); toast("Saved for your next songs"); };
    const reset = el("button", "tap rounded-lg bg-white/10 px-3 py-1 text-xs font-semibold hover:bg-white/20", "↺ Use the host default");
    reset.type = "button";
    reset.onclick = () => {
      set({ guide: null });
      slider.value = Settings.get("guide_default", 20);
      shown.textContent = "host default";
      toast("Saved for your next songs");
    };
    guideRow.append(head, slider, reset);
    box.append(el("p", "text-xs text-stone-400", "Used for every song you add from this device. You can still change each song in the queue until it starts."),
      modeRow, guideRow);
    return box;
  }

  return { get, set, applyTo, editor };
})();
