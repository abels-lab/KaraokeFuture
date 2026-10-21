// Party-mode effects: no numbers, only light. vibe (0..1) from the game engine:
//   > 0.45 shine   — sung words glow gold
//   > 0.70 sparkle — golden sparks fly off the word being sung
//   > 0.85 burst   — bigger star bursts; stage lights at full warmth
// energy (0..1, the song's own vocal loudness right now) sets how lively the sparks are.
function createFx(container) {
  const canvas = el("canvas", "pointer-events-none absolute inset-0 h-full w-full");
  const lights = el("div", "pointer-events-none absolute inset-x-0 bottom-0 h-1/2 transition-opacity duration-700");
  lights.style.background = "radial-gradient(ellipse 60% 100% at 50% 100%, rgba(244,194,91,.55), transparent 70%)";
  lights.style.opacity = "0";
  container.append(lights, canvas);
  const ctx = canvas.getContext("2d");
  const sparks = [];
  let last = performance.now(), carry = 0;

  function resize() {
    const r = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(r.width * dpr)) { canvas.width = r.width * dpr; canvas.height = r.height * dpr; }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return r;
  }

  function spawn(x, y, big, energy) {
    const angle = -Math.PI / 2 + (Math.random() - 0.5) * 2.2;
    const speed = (40 + Math.random() * 120) * (0.6 + energy);
    sparks.push({ x, y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, life: 1,
                  size: (big ? 5 : 2) + Math.random() * (big ? 6 : 3), hue: 38 + Math.random() * 14,
                  spin: Math.random() * Math.PI });
  }

  function star(s) { // four-pointed twinkle
    ctx.save();
    ctx.translate(s.x, s.y);
    ctx.rotate(s.spin);
    ctx.globalAlpha = Math.max(0, s.life);
    ctx.fillStyle = `hsl(${s.hue} 95% ${60 + 30 * s.life}%)`;
    ctx.beginPath();
    for (let k = 0; k < 8; k++) {
      const r = k % 2 ? s.size * 0.28 : s.size;
      ctx.lineTo(Math.cos((k * Math.PI) / 4) * r, Math.sin((k * Math.PI) / 4) * r);
    }
    ctx.fill();
    ctx.restore();
  }

  // anchor: element being sung (its glow + spark source); vibe 0..1; energy 0..1
  function render(anchor, vibe, energy) {
    const now = performance.now(), dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const box = resize();
    lights.style.opacity = String(Math.max(0, (vibe - 0.3) / 0.7));
    const line = anchor?.closest("p") || anchor;
    if (line) {
      const glow = Math.max(0, (vibe - 0.45) / 0.55);
      line.style.filter = glow ? `drop-shadow(0 0 ${6 + 26 * glow}px rgba(244,194,91,${0.35 + 0.5 * glow}))` : "";
      line.classList.toggle("vibe-shine", vibe > 0.45);
    }
    if (anchor && vibe > 0.7) {
      const r = anchor.getBoundingClientRect();
      const x = r.left - box.left + r.width * (0.3 + 0.7 * Math.random()), y = r.top - box.top + r.height * 0.4;
      carry += dt * (vibe > 0.85 ? 70 : 35) * (0.5 + energy);
      for (; carry >= 1; carry--) spawn(x + (Math.random() - 0.5) * 30, y, vibe > 0.85 && Math.random() < 0.25, energy);
    }
    ctx.clearRect(0, 0, box.width, box.height);
    for (let i = sparks.length - 1; i >= 0; i--) {
      const s = sparks[i];
      s.vy += 160 * dt; s.x += s.vx * dt; s.y += s.vy * dt;
      s.life -= dt * 0.9; s.spin += dt * 4;
      if (s.life <= 0) sparks.splice(i, 1); else star(s);
    }
  }

  function clear(anchorLine) {
    sparks.length = 0;
    lights.style.opacity = "0";
    if (anchorLine) { anchorLine.style.filter = ""; anchorLine.classList.remove("vibe-shine"); }
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  return { render, clear };
}
