// Adaptive theme (experimental): the stage light and accents follow the video and music.
// - Background image: servers_on_scene.jpg (servers on the stage)
// - Colors from video frames when playing, or from the song's musical tunes & melody when video is off
// - Backing track loudness (--level) and bass hits (--beat) modulate ambient glow and accents
// Needs common.js + look.js + pulse-colors.js. createPulse() -> { clear(), render(time, songId) }
const BEAT_FADE = 0.28;

function createPulse() {
  let data = null, melody = null, songId = null, level = 0;
  let lastSampleClock = 0;
  let tgtBg = [...DEFAULT_BG], curBg = [...DEFAULT_BG];
  let tgtAcc = [...DEFAULT_ACC], curAcc = [...DEFAULT_ACC];

  const style = document.body.style;
  const on = () => Settings.get("theme", "theater") === "adaptive";

  const sampleVideo = createFrameSampler();

  async function fetchFor(id) {
    if (songId === id && data) return;
    songId = id; data = null; melody = null;
    try {
      const [freshPulse, freshMelody] = await Promise.all([
        api(`/api/songs/${id}/pulse`).catch(() => null),
        fetch(`/media/${id}/melody.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      ]);
      if (songId === id) {
        data = freshPulse;
        melody = freshMelody;
      }
    } catch { /* calm fallback */ }
  }

  function clear() {
    songId = null; data = null; melody = null; level = 0;
    tgtBg = [...DEFAULT_BG]; curBg = [...DEFAULT_BG];
    tgtAcc = [...DEFAULT_ACC]; curAcc = [...DEFAULT_ACC];
    style.removeProperty("--level");
    style.removeProperty("--beat");
    style.removeProperty("--adaptive-bg");
    style.removeProperty("--adaptive-glow");
    style.removeProperty("--adaptive-accent");
    style.removeProperty("--adaptive-accent-deep");
    if (typeof Look !== "undefined" && Look.apply) {
      Look.apply();
    }
  }

  function lastBeat(t) {
    if (!data?.beats?.length) return -Infinity;
    const b = data.beats;
    let lo = 0, hi = b.length - 1, found = -Infinity;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (b[mid] <= t) { found = b[mid]; lo = mid + 1; } else hi = mid - 1;
    }
    return found;
  }

  function render(t, id) {
    if (!on()) {
      if (level || curBg[0] !== DEFAULT_BG[0]) clear();
      return;
    }
    if (id && id !== songId) fetchFor(id);

    // Audio pulse
    const targetLev = (data && data.level ? data.level[Math.round(t / data.hop)] : 0) || 0;
    level += (targetLev - level) * 0.1;
    const beat = Math.max(0, 1 - (t - lastBeat(t)) / BEAT_FADE);

    // Color sampling (~4 Hz)
    const nowClock = performance.now();
    if (nowClock - lastSampleClock > 250) {
      lastSampleClock = nowClock;
      const video = document.getElementById("video") || document.getElementById("stage-video");
      ({ bg: tgtBg, acc: tgtAcc } = sampleVideo(video) || tuneColors(melody, t, level, beat, lastBeat(t)));
    }

    // Smooth color interpolation (LERP factor 0.08)
    const LERP = 0.08;
    curBg[0] += (tgtBg[0] - curBg[0]) * LERP;
    curBg[1] += (tgtBg[1] - curBg[1]) * LERP;
    curBg[2] += (tgtBg[2] - curBg[2]) * LERP;
    curAcc[0] += (tgtAcc[0] - curAcc[0]) * LERP;
    curAcc[1] += (tgtAcc[1] - curAcc[1]) * LERP;
    curAcc[2] += (tgtAcc[2] - curAcc[2]) * LERP;

    const bgR = Math.round(curBg[0]), bgG = Math.round(curBg[1]), bgB = Math.round(curBg[2]);
    const accR = Math.round(curAcc[0]), accG = Math.round(curAcc[1]), accB = Math.round(curAcc[2]);
    const deepR = Math.round(accR * 0.72), deepG = Math.round(accG * 0.72), deepB = Math.round(accB * 0.72);

    // Dynamic glow reacts to ambient video hue and flairs on beats
    const glowAlpha = Math.min(0.55, 0.15 + level * 0.22 + beat * 0.20).toFixed(3);
    const glowR = Math.min(255, Math.round(bgR * (1 + beat * 0.45)));
    const glowG = Math.min(255, Math.round(bgG * (1 + beat * 0.45)));
    const glowB = Math.min(255, Math.round(bgB * (1 + beat * 0.45)));

    style.setProperty("--level", level.toFixed(3));
    style.setProperty("--beat", beat.toFixed(3));
    style.setProperty("--adaptive-bg", `rgb(${Math.round(bgR * 0.18)}, ${Math.round(bgG * 0.18)}, ${Math.round(bgB * 0.22)})`);
    style.setProperty("--adaptive-glow", `rgba(${glowR}, ${glowG}, ${glowB}, ${glowAlpha})`);
    style.setProperty("--adaptive-accent", `rgb(${accR}, ${accG}, ${accB})`);
    style.setProperty("--adaptive-accent-deep", `rgb(${deepR}, ${deepG}, ${deepB})`);

    // Dynamically harmonize lyric fill & button accents when set to "Theme colour"
    if (Settings.get("accent", "theme") === "theme") {
      document.documentElement.style.setProperty("--gold", `rgb(${accR}, ${accG}, ${accB})`);
      document.documentElement.style.setProperty("--gold-deep", `rgb(${deepR}, ${deepG}, ${deepB})`);
    }
  }

  return { clear, render };
}
