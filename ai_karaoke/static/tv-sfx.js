// Party sound effects for the Co-Pilot's custom buttons (action "sfx"), synthesized with WebAudio
// so no sound files are needed: airhorn, applause, drumroll, laser, cheer, anything else = a chime.
// They play on the device whose button was pressed. Split from tv-ui.js (TvUi.playSfx calls this).
// Needs nothing. TvSfx.play(type)
const TvSfx = (() => {
  let audioCtx = null;
  function context() {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return null;
      if (!audioCtx) audioCtx = new AudioContext();
      if (audioCtx.state === "suspended") audioCtx.resume();
      return audioCtx;
    } catch {
      return null;
    }
  }

  // One oscillator through its own gain: freq(param) and gain(param) shape them over time
  function voice(ctx, { type = "sine", start, stop, freq, gain, dest = ctx.destination }) {
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type;
    freq(o.frequency);
    gain(g.gain);
    o.connect(g);
    g.connect(dest);
    o.start(start);
    o.stop(stop);
  }

  // Reggae airhorn: Bb4 (466 Hz) and Eb5 (622 Hz) sawtooth stabs
  function airhorn(ctx, now) {
    for (const [st, dur] of [[0, 0.11], [0.15, 0.11], [0.3, 0.11], [0.45, 0.42]]) {
      for (const [from, to] of [[466.16, 475.0], [622.25, 630.0]]) {
        voice(ctx, { type: "sawtooth", start: now + st, stop: now + st + dur,
          freq: (f) => { f.setValueAtTime(from, now + st); f.linearRampToValueAtTime(to, now + st + 0.04); },
          gain: (g) => {
            g.setValueAtTime(0, now + st); g.linearRampToValueAtTime(0.25, now + st + 0.015);
            g.setValueAtTime(0.25, now + st + dur - 0.02); g.linearRampToValueAtTime(0, now + st + dur);
          } });
      }
    }
  }

  // Band-pass filtered noise with clapping pops
  function applause(ctx, now) {
    const dur = 2.0, len = Math.floor(ctx.sampleRate * dur);
    const buffer = ctx.createBuffer(1, len, ctx.sampleRate), data = buffer.getChannelData(0);
    for (let i = 0; i < len; i++) {
      const pop = Math.random() < 0.015 ? (Math.random() * 2 - 1) * 2.5 : 0;
      data[i] = (Math.random() * 2 - 1) * 0.35 + pop;
    }
    const src = ctx.createBufferSource(), filter = ctx.createBiquadFilter(), g = ctx.createGain();
    src.buffer = buffer;
    filter.type = "bandpass";
    filter.frequency.setValueAtTime(1100, now);
    filter.Q.setValueAtTime(1.2, now);
    g.gain.setValueAtTime(0, now);
    g.gain.linearRampToValueAtTime(0.28, now + 0.25);
    g.gain.setValueAtTime(0.28, now + 1.2);
    g.gain.exponentialRampToValueAtTime(0.001, now + dur);
    src.connect(filter);
    filter.connect(g);
    g.connect(ctx.destination);
    src.start(now);
  }

  // Snare roll crescendo ending in a punchy rimshot
  function drumroll(ctx, now) {
    const hits = 22, dur = 1.1;
    for (let i = 0; i < hits; i++) {
      const t = now + (i / hits) * dur, vol = 0.04 + 0.22 * (i / hits);
      voice(ctx, { type: "triangle", start: t, stop: t + 0.04, freq: (f) => f.setValueAtTime(175, t),
        gain: (g) => { g.setValueAtTime(vol, t); g.exponentialRampToValueAtTime(0.001, t + 0.04); } });
    }
    const end = now + dur + 0.02;
    voice(ctx, { start: end, stop: end + 0.35, freq: (f) => f.setValueAtTime(260, end),
      gain: (g) => { g.setValueAtTime(0.38, end); g.exponentialRampToValueAtTime(0.001, end + 0.35); } });
  }

  // Fast pitch dive retro laser
  const laser = (ctx, now) => voice(ctx, { type: "sawtooth", start: now, stop: now + 0.16,
    freq: (f) => { f.setValueAtTime(1200, now); f.exponentialRampToValueAtTime(75, now + 0.16); },
    gain: (g) => { g.setValueAtTime(0.25, now); g.exponentialRampToValueAtTime(0.001, now + 0.16); } });

  // Celebratory chord, ascending sweep
  function cheer(ctx, now) {
    [392.0, 523.25, 659.25, 783.99].forEach((freq, idx) => voice(ctx, { type: "triangle", start: now, stop: now + 1.0,
      freq: (f) => { f.setValueAtTime(freq * 0.85, now); f.exponentialRampToValueAtTime(freq, now + 0.18); },
      gain: (g) => {
        g.setValueAtTime(0, now); g.linearRampToValueAtTime(0.12, now + 0.07);
        g.exponentialRampToValueAtTime(0.001, now + 0.85 + idx * 0.08);
      } }));
  }

  const chime = (ctx, now) => voice(ctx, { start: now, stop: now + 0.3, freq: (f) => f.setValueAtTime(587.33, now),
    gain: (g) => { g.setValueAtTime(0.2, now); g.exponentialRampToValueAtTime(0.001, now + 0.3); } });

  const SOUNDS = { airhorn, applause, drumroll, laser, cheer };

  function play(type) {
    const ctx = context();
    if (!ctx) return;
    try {
      (SOUNDS[String(type || "airhorn").toLowerCase().trim()] || chime)(ctx, ctx.currentTime);
    } catch (err) {
      console.warn("SFX error:", err);
    }
  }
  return { play };
})();
