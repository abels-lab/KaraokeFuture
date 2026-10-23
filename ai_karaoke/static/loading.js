// "Getting the next song ready" screen for the control panel and the projector. When nothing
// plays but songs wait, it shows the next song's pipeline stage live (the queue status the
// worker reports, core/worker.py, arrives with every "state" broadcast), a step indicator,
// how long it has been at it, its place in the processing line (/api/info, fetched at most
// every 2 s) and who comes after. Needs common.js.
// createLoading(section) -> { render(queue) -> shown?, poke() (something changed: refetch info) }
const LOADING_STEPS = [["queued", "Waiting"], ["downloading", "Downloading"], ["separating", "Removing vocals"],
                       ["aligning", "Syncing lyrics"], ["melody", "Reading the melody"]];

function createLoading(section) {
  section.innerHTML = `
    <div class="flex w-full max-w-4xl flex-col items-center gap-[3vh] text-center">
      <p class="text-[clamp(.8rem,1.1vw,1.2rem)] font-semibold uppercase tracking-[0.4em] text-gold">Getting the next song ready</p>
      <img data-l="thumb" alt="" class="h-[18vh] rounded-2xl object-cover shadow-2xl ring-1 ring-amber-200/20">
      <div class="min-w-0 max-w-full">
        <h2 data-l="singer" class="font-display truncate text-[clamp(2rem,4.5vw,5rem)] font-black leading-tight"></h2>
        <p data-l="title" class="truncate text-[clamp(1rem,1.8vw,2rem)] text-stone-200"></p>
      </div>
      <ol data-l="steps" class="flex w-full flex-wrap justify-center gap-2"></ol>
      <p data-l="status" class="font-mono text-[clamp(.9rem,1.3vw,1.4rem)] text-stone-300"></p>
      <div data-l="next" class="panel hidden w-full max-w-2xl space-y-1 px-6 py-4 text-left text-[clamp(.85rem,1.1vw,1.2rem)]"></div>
    </div>`;
  const part = (k) => section.querySelector(`[data-l="${k}"]`);
  let queue = [], info = null, fetchedAt = 0, pending = null;
  const seen = {};   // uid -> {status, stageAt, firstAt}: elapsed times, measured on this device

  function poke() {   // throttled: at most one /api/info request every 2 s, the last one wins
    if (pending) return;
    pending = setTimeout(() => {
      pending = null; fetchedAt = performance.now();
      api("/api/info").then((i) => { info = i; paint(); }).catch(() => {});
    }, Math.max(0, 2000 - (performance.now() - fetchedAt)));
  }

  function lineText(head) {
    const done = ["ready", "error"];
    if (head.status === "ready") return "Ready — starting in a moment";
    if (head.status === "error") return `Couldn't prepare this song: ${head.error || "unknown error"}`;
    if (!["queued", "waiting"].includes(head.status) || info?.processing === head.song_id) return "Being prepared right now";
    const ahead = new Set(queue.slice(0, queue.indexOf(head)).filter((e) => !done.includes(e.status)).map((e) => e.song_id)).size;
    const warm = info && !info.processing && info.backlog?.low ? " · finishing a background warm-up first" : "";
    return `${ahead ? `${ahead} song${ahead > 1 ? "s" : ""} ahead of it` : "Next in line"}${info ? ` · ${info.backlog?.high ?? 0} job(s) waiting` : ""}${warm}`;
  }

  function paint() {
    const head = queue.find((e) => e.status !== "error") || queue[0];
    if (!head) return;
    const now = performance.now();
    const s = (seen[head.uid] ||= { status: head.status, stageAt: now, firstAt: now });
    if (s.status !== head.status) Object.assign(s, { status: head.status, stageAt: now });
    part("thumb").src = head.thumbnail || thumbFor(head.song_id);
    part("singer").textContent = singers(head);
    part("title").textContent = head.title;
    const key = head.status === "waiting" ? "queued" : head.status;   // error: no step lit
    const at = key === "ready" ? LOADING_STEPS.length : LOADING_STEPS.findIndex(([k]) => k === key);
    part("steps").replaceChildren(...LOADING_STEPS.map(([, label], i) => {
      const state = i < at ? "bg-amber-400/90 text-stone-950"
        : i === at ? "bg-amber-400/25 text-gold ring-2 ring-amber-400 animate-pulse" : "bg-white/10 text-stone-400";
      return el("li", `rounded-full px-4 py-1.5 text-[clamp(.75rem,1vw,1.1rem)] font-semibold ${state}`, `${i < at ? "✓ " : ""}${label}`);
    }));
    const clock = head.status === "ready" || head.status === "error" ? "" : ` · ${fmt((now - s.stageAt) / 1000)} at this step · ${fmt((now - s.firstAt) / 1000)} in total`;
    part("status").textContent = lineText(head) + clock;
    const later = queue.filter((e) => e !== head).slice(0, 4);
    part("next").classList.toggle("hidden", !later.length);
    part("next").replaceChildren(el("p", "font-semibold uppercase tracking-widest text-gold", "Up next"), ...later.map((e, i) => {
      const row = el("p", "flex items-center gap-2 truncate text-stone-200", `${i + 1}. ${singers(e)} — ${e.title}`);
      const [label, color] = STATUS[e.status] || [e.status, "bg-stone-600"];
      row.append(el("span", `ml-auto shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${color}`, label));
      return row;
    }));
  }

  function render(q) {
    queue = q || [];
    const shown = queue.length > 0;
    section.classList.toggle("hidden", !shown);
    section.classList.toggle("flex", shown);
    if (shown) { paint(); poke(); }
    return shown;
  }

  setInterval(() => { if (!section.classList.contains("hidden")) paint(); }, 1000);   // elapsed time
  return { render, poke };
}
