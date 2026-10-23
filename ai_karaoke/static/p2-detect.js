// Battle / Score with two mics: notices a second singer on mic 2 without anyone touching a phone.
// A 20 ms mic-2 frame counts as singing when it has a clear pitch, is louder than the Settings
// page's p2_min_db (speakers alone shouldn't get there on a close mic), and is not bleed: the
// speakers reach both mics about equally, and singer 1 reaches mic 2 much quieter and on the
// same note. So the frame must be p2_margin_db louder than mic 1 at that moment, or sing a
// clearly different note than a singing mic 1 while not much quieter than it.
// p2_voiced_seconds of such frames within p2_window_seconds = Player 2 joins.
// Needs common.js (Settings). createP2Detect() -> { reset(), feed(slot, frame) -> true = joined }
function createP2Detect() {
  const FRAME_MS = 20;                                  // pitch-worklet.js hop
  const fold = (d) => ((d % 12) + 18) % 12 - 6;         // nearest-octave difference, semitones
  const SILENT = { db: -120, pitch: 0, clarity: 0 };
  let last1 = null, hits = [];                          // mic 1's latest frame; times of good mic-2 frames

  function qualifies(f) {
    const margin = Settings.get("p2_margin_db", 6);
    if (!(f.pitch > 0 && f.clarity > 0.6 && f.db > Settings.get("p2_min_db", -45))) return false;
    const one = last1 && Math.abs(f.at - last1.at) < 100 ? last1 : SILENT;
    if (f.db - one.db >= margin) return true;           // clearly louder than mic 1: its own singer
    const oneSings = one.pitch > 0 && one.clarity > 0.6;
    return oneSings && Math.abs(fold(f.pitch - one.pitch)) >= 1 && f.db >= one.db - margin;
  }

  function feed(slot, f) {
    if (slot === 0) { last1 = f; return false; }
    if (slot !== 1) return false;
    if (qualifies(f)) hits.push(f.at);
    const windowMs = Settings.get("p2_window_seconds", 3) * 1000;
    while (hits.length && hits[0] < f.at - windowMs) hits.shift();
    return hits.length * FRAME_MS >= Settings.get("p2_voiced_seconds", 1.5) * 1000;
  }

  return { feed, reset() { last1 = null; hits = []; } };
}
