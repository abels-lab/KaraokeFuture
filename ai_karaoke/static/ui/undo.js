// Undo instead of "are you sure?" for quick, everyday actions (removing a song from the queue or
// the history, putting one setting back to its default): the action happens at once, and a bar
// at the bottom offers ↶ Undo for a few seconds.
// - Undo.later(uid, text, run): for a removal. Rows with data-uid=uid hide now (list repaints keep
//   them hidden: isPending) and run(urgent) is called after the delay unless Undo is pressed.
//   When the page closes first, run(true) is called at once: use fetch keepalive then.
// - Undo.now(text, undo): the action already happened; Undo calls undo().
// Needs common.js (el).
const Undo = (() => {
  const DELAY = 5000;
  const pending = new Map();   // uid -> { run, timer }
  let bar = null, barTimer = null;

  function show(text, onUndo) {
    if (!bar) {
      bar = el("div", "undo-bar fixed inset-x-4 bottom-6 z-50 mx-auto flex max-w-md items-center gap-3 rounded-xl bg-stone-900/95 px-4 py-2.5 shadow-2xl ring-1 ring-white/10");
      bar.setAttribute("role", "status");
      bar.append(el("span", "min-w-0 flex-1 truncate text-sm font-semibold"),
        Object.assign(el("button", "tap shrink-0 rounded-lg bg-amber-400 px-3 py-1.5 text-sm font-bold text-stone-950 hover:bg-amber-300", "↶ Undo"), { type: "button" }));
      document.body.append(bar);
    }
    bar.firstChild.textContent = text;
    bar.lastChild.onclick = () => { hide(); onUndo(); };
    bar.classList.remove("hidden");
    clearTimeout(barTimer);
    barTimer = setTimeout(hide, DELAY);
  }
  const hide = () => { clearTimeout(barTimer); bar?.classList.add("hidden"); };

  const rows = (uid) => document.querySelectorAll(`[data-uid="${CSS.escape(String(uid))}"]`);

  function finish(uid, urgent) {
    const job = pending.get(uid);
    if (!job) return;
    clearTimeout(job.timer);
    pending.delete(uid);
    job.run(urgent);
  }

  function later(uid, text, run) {
    if (pending.has(uid)) return;
    rows(uid).forEach((r) => r.classList.add("hidden"));
    pending.set(uid, { run, timer: setTimeout(() => finish(uid, false), DELAY) });
    show(text, () => {
      clearTimeout(pending.get(uid)?.timer);
      pending.delete(uid);
      rows(uid).forEach((r) => r.classList.remove("hidden"));
    });
  }

  const now = (text, undo) => show(text, undo);
  const isPending = (uid) => pending.has(uid);
  addEventListener("pagehide", () => [...pending.keys()].forEach((uid) => finish(uid, true)));

  return { later, now, isPending };
})();
