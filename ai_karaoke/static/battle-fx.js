// Battle mode sparks: each singer's pitch trail throws sparks in that singer's colour while they
// hit the note — more of them, and bigger, the longer the combo. Drawn on a canvas laid exactly
// over the note lanes (notes.js), so a spark starts where the trail is. Needs common.js, notes.js.
function createBattleFx(container) {
  const canvas = el("canvas", "pointer-events-none absolute inset-x-0 top-[14%] h-[46%] w-full");
  container.append(canvas);
  const ctx = canvas.getContext("2d");
  const sparks = [];
  let last = performance.now(), carry = [0, 0];

  function spawn(x, y, color, big) {
    const angle = Math.PI + (Math.random() - 0.5) * 1.6;   // backwards, along the trail
    const speed = 60 + Math.random() * (big ? 220 : 120);
    sparks.push({ x, y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed - 40, life: 1,
                  size: (big ? 3.5 : 2) + Math.random() * 2.5, color });
  }

  // heads: per singer {x, y, hit, streak} | null, from notes.render()
  function render(heads) {
    const now = performance.now(), dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const r = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(r.width * dpr)) { canvas.width = r.width * dpr; canvas.height = r.height * dpr; }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, r.width, r.height);
    (heads || []).forEach((h, i) => {
      if (!h?.hit) return;
      carry[i] = (carry[i] || 0) + dt * Math.min(90, 25 + h.streak * 1.5);
      for (; carry[i] >= 1; carry[i]--) spawn(h.x, h.y, PLAYER_COLORS[i], h.streak > 40 && Math.random() < 0.3);
    });
    for (let k = sparks.length - 1; k >= 0; k--) {
      const s = sparks[k];
      s.vy += 140 * dt; s.x += s.vx * dt; s.y += s.vy * dt; s.life -= dt * 1.4;
      if (s.life <= 0) { sparks.splice(k, 1); continue; }
      ctx.globalAlpha = s.life;
      ctx.fillStyle = s.color;
      ctx.beginPath(); ctx.arc(s.x, s.y, s.size * (0.5 + s.life / 2), 0, 7); ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  function clear() { sparks.length = 0; carry = [0, 0]; ctx.clearRect(0, 0, canvas.width, canvas.height); }
  const show = (on) => canvas.classList.toggle("hidden", !on);
  return { render, clear, show };
}
