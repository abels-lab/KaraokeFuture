// Hard mode: scrolling note lanes (reference melody), each singer's live pitch trail, and a
// HUD with points, combo and the sung note in cents. Needs common.js + mics.js (noteName).
const PLAYER_COLORS = ["#f4c25b", "#5eead4"]; // gold, teal
const BEHIND = 2, AHEAD = 4;                   // seconds visible either side of the playhead

function createNotes(container) {
  const canvas = el("canvas", "pointer-events-none absolute inset-x-0 top-[14%] h-[46%] w-full");
  const hud = el("div", "pointer-events-none absolute right-[3%] top-[3%] flex gap-4");
  container.append(canvas, hud);
  const ctx = canvas.getContext("2d");
  let notes = [], lo = 48, hi = 72, trails = [[], []], hits = [{}, {}];

  function load(melody) {
    notes = melody?.notes || [];
    trails = [[], []]; hits = [{}, {}];
    if (notes.length) {
      const span = notes.map((n) => n.midi).sort((a, b) => a - b);
      lo = span[Math.floor(span.length * 0.03)] - 2;
      hi = Math.max(lo + 12, span[Math.floor(span.length * 0.97)] + 2);
    }
  }

  // Display only: fold the singer's pitch into the octave of the song so the trail lands on the lanes
  const fold = (midi, around) => midi - 12 * Math.round((midi - around) / 12);

  function render(t, live) {
    const r = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(r.width * dpr)) { canvas.width = r.width * dpr; canvas.height = r.height * dpr; }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, r.width, r.height);
    const x = (time) => r.width * ((time - t + BEHIND) / (BEHIND + AHEAD));
    const y = (midi) => r.height * (1 - (midi - lo + 0.5) / (hi - lo + 1));
    const lane = r.height / (hi - lo + 1);
    ctx.fillStyle = "rgba(0,0,0,.35)";
    ctx.fillRect(0, 0, r.width, r.height);
    const current = notes.find((n) => n.start <= t && t <= n.end);
    live.forEach((p, i) => {                       // remember trail + which notes each singer hit
      if (p.pitch > 0) trails[i].push({ t, m: fold(p.pitch, current ? current.midi : (lo + hi) / 2), hit: p.hit });
      while (trails[i].length && trails[i][0].t < t - BEHIND) trails[i].shift();
      if (current && p.hit) hits[i][notes.indexOf(current)] = true;
    });
    for (const [k, n] of notes.entries()) {
      if (n.end < t - BEHIND || n.start > t + AHEAD) continue;
      const left = x(n.start), w = Math.max(4, x(n.end) - left), top = y(n.midi) - lane * 0.4;
      const hitBy = hits.findIndex((h) => h[k]);
      ctx.fillStyle = hitBy >= 0 ? PLAYER_COLORS[hitBy] : "rgba(255,248,236,.16)";
      ctx.strokeStyle = n === current ? "#fff" : "rgba(244,194,91,.7)";
      ctx.lineWidth = n === current ? 2 : 1;
      ctx.beginPath(); ctx.roundRect(left, top, w, lane * 0.8, lane * 0.4); ctx.fill(); ctx.stroke();
    }
    trails.forEach((trail, i) => {
      ctx.fillStyle = PLAYER_COLORS[i];
      for (const p of trail) { ctx.globalAlpha = p.hit ? 1 : 0.45; ctx.beginPath(); ctx.arc(x(p.t), y(p.m), p.hit ? 4 : 3, 0, 7); ctx.fill(); }
      ctx.globalAlpha = 1;
    });
    ctx.fillStyle = "rgba(255,255,255,.8)";
    ctx.fillRect(x(t) - 1, 0, 2, r.height);         // playhead
    renderHud(live, current);
    // Where each singer's trail is right now (battle sparks fly from there), null = silent
    return trails.map((trail, i) => {
      const p = trail[trail.length - 1];
      return p && p.t > t - 0.1 ? { x: x(p.t), y: y(p.m), hit: p.hit, streak: live[i]?.streak || 0 } : null;
    });
  }

  function renderHud(live, current) {
    if (hud.childElementCount !== live.length) {
      hud.replaceChildren(...live.map((_, i) => {
        const box = el("div", "panel min-w-[9rem] px-4 py-2 text-right");
        box.style.borderColor = PLAYER_COLORS[i];
        box.innerHTML = `<p data-h="name" class="truncate text-sm font-semibold"></p><p data-h="points" class="font-display text-3xl font-black"></p>
          <p data-h="detail" class="font-mono text-xs text-stone-300"></p>`;
        return box;
      }));
    }
    live.forEach((p, i) => {
      const box = hud.children[i], q = (k) => box.querySelector(`[data-h="${k}"]`);
      q("name").textContent = p.name;
      q("points").textContent = p.points.toLocaleString();
      q("points").style.color = PLAYER_COLORS[i];
      const cents = current && p.pitch > 0 ? Math.round((fold(p.pitch, current.midi) - current.midi) * 100) : null;
      q("detail").textContent = `${p.pitch > 0 ? noteName(p.pitch) : "–"}${cents !== null ? ` ${cents >= 0 ? "+" : ""}${cents}¢` : ""} · combo ${p.streak}`;
    });
  }

  function clear() {
    notes = []; trails = [[], []]; hits = [{}, {}];
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    hud.replaceChildren();
  }

  // A class, not the hidden attribute: the HUD's own `flex` class would override [hidden]
  const show = (on) => { canvas.classList.toggle("hidden", !on); hud.classList.toggle("hidden", !on); };
  return { load, render, clear, show };
}
