// Singing game engine (control panel): scores each singer's mic frames against melody.json.
// Pitch (octave-folded, so any voice can sing any song), timing (singing where the original
// sings) and loudness (rising and falling with the original). No text recognition.
const Game = (() => {
  // From the Settings page, read at each song's start: noise gate (dB), pitch window (semitones)
  let GATE_DB = -48, PERFECT = 0.5, MISS = 2.0;
  let melody = null, players = [], noteIdx = 0, sungFrames = 1;

  const fold = (d) => ((d % 12) + 18) % 12 - 6;      // nearest-octave difference in semitones
  const clamp = (x) => Math.max(0, Math.min(1, x));

  function player(i, name) {
    return { i, name, vibe: 0.35, streak: 0, best: 0, livePitch: 0, hit: false, earned: 0, refPitched: 0,
             pitch: [0, 0], timing: [0, 0, 0], env: [], peakDb: -30, onNote: {} };  // timing: hit, missed, extra
  }

  // names: one per mic slot; on: which slots play from the start (a battle's Player 2 may
  // join later, when they start singing or a partner joins: activate)
  function load(melodyJson, names, on = names.map(() => true)) {
    GATE_DB = Settings.get("game_gate_db", -48);
    PERFECT = Settings.get("game_perfect", 0.5);
    MISS = Math.max(PERFECT + 0.1, Settings.get("game_miss", 2.0));
    melody = melodyJson;
    noteIdx = 0;
    sungFrames = Math.max(1, melody.energy.filter((e) => e > 0.25).length); // points = share of these
    players = names.map((name, i) => ({ ...player(i, name), on: on[i] !== false }));
  }

  // One mic frame. t = song time the singer was answering (playback time minus latency).
  function frame(i, { pitch, clarity, db }, t) {
    const p = players[i];
    if (!melody || !p || !p.on || t < 0) return;
    const k = Math.round(t / melody.hop);
    const refPitch = melody.pitch[k] || 0, refEnergy = melody.energy[k] || 0;
    p.peakDb = Math.max(p.peakDb - 0.002, db);                // slowly forgets old peaks
    // A close mic hears its singer far louder than the room: "singing" is relative to them
    const singing = db > Math.max(GATE_DB, p.peakDb - 20), voiced = singing && pitch > 0 && clarity > 0.6;
    p.livePitch = voiced ? pitch : 0;
    const expect = refEnergy > 0.25, rest = refEnergy < 0.08;  // original sings / clearly rests
    p.lastT = t;
    p.hit = false;
    let q = null;
    const level = clamp((db - (p.peakDb - 40)) / 40);          // relative to the singer's own peak
    p.env.push(level, refEnergy);                              // loudness curves, compared in summary()
    if (expect) {
      p.timing[singing ? 0 : 1]++;                             // hit / missed entry
      p.refPitched += refPitch > 0 ? 1 : 0;
      const amp = 1 - Math.abs(level - refEnergy);             // instant version, for the vibe only
      if (refPitch > 0 && (voiced || !singing)) {              // shouts/consonants: skipped, silence: miss
        const score = voiced ? clamp(1 - (Math.abs(fold(pitch - refPitch)) - PERFECT) / (MISS - PERFECT)) : 0;
        p.pitch[0] += score; p.pitch[1]++;
        p.hit = score > 0.5;
        q = score;
        if (voiced) markNote(p, t, score);
      } else {
        q = singing ? 0.6 + 0.3 * amp : 0;                     // shouted / unpitched: rhythm + energy
      }
    } else if (rest && singing) {
      p.timing[2]++;                                           // sound where the original rests
      q = 0.15;
    }
    if (expect) p.earned += q;
    if (q !== null) {
      p.vibe += (q - p.vibe) * 0.06;                           // ~0.3 s smoothing at 50 frames/s
      p.streak = q > 0.6 ? p.streak + 1 : Math.max(0, p.streak - 3);
      p.best = Math.max(p.best, p.streak);
    } else {
      p.vibe += (0.35 - p.vibe) * 0.01;                        // drift back to neutral in breaks
    }
  }

  function markNote(p, t, score) {
    const notes = melody.notes;
    while (noteIdx < notes.length && notes[noteIdx].end < t - 1) noteIdx++;
    for (let n = noteIdx; n < notes.length && notes[n].start <= t; n++) {
      if (t <= notes[n].end) {
        const acc = (p.onNote[n] ||= [0, 0]);
        acc[0] += score; acc[1]++;
      }
    }
  }

  // A note counts as hit when at least half of the frames sung on it were in tune
  const noteHits = (p) => Object.values(p.onNote).filter(([s, n]) => n >= 2 && s / n >= 0.5).length;

  // Loudness follows the original vocal (phrases, breaths, accents)? Pearson correlation in
  // 3 s windows. Music bleed follows the band instead, so it scores low here.
  function envelopeMatch(env) {
    const W = 150, rs = [];
    for (let s = 0; s + 2 * W <= env.length; s += W) {        // env = [level, ref, level, ref, ...]
      let sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
      for (let k = s; k < s + 2 * W; k += 2) {
        const x = env[k], y = env[k + 1];
        sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y;
      }
      const n = W, vx = sxx - (sx * sx) / n, vy = syy - (sy * sy) / n;
      if (vy / n < 0.01) continue;                             // original barely changes: no evidence
      rs.push(vx > 1e-9 ? Math.max(0, (sxy - (sx * sy) / n) / Math.sqrt(vx * vy)) : 0);
    }
    return rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : 0;
  }

  function summary(p) {
    const rate = ([a, b]) => (b ? a / b : null);
    const pitch = rate(p.pitch), amp = envelopeMatch(p.env);
    // Timing = F1 of "singing when the original sings" and "quiet when it rests": music bleed
    // is loud everywhere, so it fails the second half
    const [hit, missed, extra] = p.timing;
    const timing = hit ? (2 * hit) / (2 * hit + missed + extra) : 0;
    // Weight of pitch = how much of the song has clear notes; shouted / rapped songs lean on
    // timing and energy instead
    const pitchWeight = pitch === null ? 0 : Math.min(0.6, p.refPitched / Math.max(1, hit + missed));
    // Loudness shape outweighs timing: being loud at the right moments is easy for bleed too
    const overall = pitchWeight * (pitch ?? 0) + (1 - pitchWeight) * (0.4 * timing + 0.6 * amp);
    const notesTotal = melody ? melody.notes.filter((n) => n.end <= (p.lastT ?? 0)).length : 0;
    return {
      name: p.name, overall: clamp(overall), pitch, timing, amp, bestStreak: p.best,
      notesHit: noteHits(p), notesTotal, points: points(p),
    };
  }

  const points = (p) => Math.round(Math.min(1, p.earned / sungFrames) * 10000);

  return {
    load, frame,
    get loaded() { return Boolean(melody); },
    get players() { return players; },
    // Slot i plays from now on (its score counts from here); rename for a partner who joined
    activate(i, name) {
      const p = players[i];
      if (p) { p.on = true; if (name) p.name = name; }
    },
    live: () => players.filter((p) => p.on).map((p) => ({ name: p.name, vibe: p.vibe, pitch: p.livePitch, hit: p.hit,
                                      streak: p.streak, points: points(p) })),
    results: () => players.filter((p) => p.on).map(summary),
    clear: () => { melody = null; players = []; },
  };
})();
