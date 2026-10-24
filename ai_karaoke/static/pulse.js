// Adaptive theme (experimental): the stage light and accents follow the video and music.
// - Background image: servers_on_scene.jpg (servers on the stage)
// - Colors from video frames when playing, or from the song's musical tunes & melody when video is off
// - Backing track loudness (--level) and bass hits (--beat) modulate ambient glow and accents
// Needs common.js + look.js. createPulse() -> { clear(), render(time, songId) }
const BEAT_FADE = 0.28;
const DEFAULT_BG = [4, 6, 18];
const DEFAULT_ACC = [127, 216, 255]; // Ice blue

function hslToRgb(h, s, l) {
  h = ((h % 360) + 360) % 360;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  let r = 0, g = 0, b = 0;
  if (h < 60) { r = c; g = x; }
  else if (h < 120) { r = x; g = c; }
  else if (h < 180) { g = c; b = x; }
  else if (h < 240) { g = x; b = c; }
  else if (h < 300) { r = x; b = c; }
  else { r = c; b = x; }
  return [(r + m) * 255, (g + m) * 255, (b + m) * 255];
}

function createPulse() {
  let data = null, melody = null, songId = null, level = 0;
  let canvas = null, ctx = null;
  let lastSampleClock = 0;
  let tgtBg = [...DEFAULT_BG], curBg = [...DEFAULT_BG];
  let tgtAcc = [...DEFAULT_ACC], curAcc = [...DEFAULT_ACC];

  const style = document.body.style;
  const on = () => Settings.get("theme", "theater") === "adaptive";

  function getCtx() {
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvas.width = 16;
      canvas.height = 16;
      ctx = canvas.getContext("2d", { willReadFrequently: true });
    }
    return ctx;
  }

  function sampleVideo(v) {
    if (!v || v.readyState < 2 || v.paused || v.ended || document.body.classList.contains("no-video")) {
      return false;
    }
    const c = getCtx();
    if (!c) return false;
    try {
      c.drawImage(v, 0, 0, 16, 16);
      const img = c.getImageData(0, 0, 16, 16).data;
      let rSum = 0, gSum = 0, bSum = 0, count = 0;
      let bestSat = -1, bestR = DEFAULT_ACC[0], bestG = DEFAULT_ACC[1], bestB = DEFAULT_ACC[2];

      for (let i = 0; i < img.length; i += 4) {
        const r = img[i], g = img[i + 1], b = img[i + 2];
        const lum = 0.299 * r + 0.587 * g + 0.114 * b;
        if (lum < 16 || lum > 245) continue;

        rSum += r; gSum += g; bSum += b; count++;

        const max = Math.max(r, g, b), min = Math.min(r, g, b);
        if (max > 25) {
          const sat = (max - min) / max;
          if (sat > bestSat && lum >= 35 && lum <= 230) {
            bestSat = sat;
            bestR = r; bestG = g; bestB = b;
          }
        }
      }

      if (count >= 12) {
        const avgR = rSum / count, avgG = gSum / count, avgB = bSum / count;
        tgtBg = [avgR, avgG, avgB];

        if (bestSat > 0.2) {
          const accLum = 0.299 * bestR + 0.587 * bestG + 0.114 * bestB;
          const factor = Math.min(2.5, Math.max(1.0, 150 / (accLum + 1e-4)));
          tgtAcc = [Math.min(255, bestR * factor), Math.min(255, bestG * factor), Math.min(255, bestB * factor)];
        } else {
          const lum = 0.299 * avgR + 0.587 * avgG + 0.114 * avgB;
          const factor = Math.min(2.2, Math.max(1.0, 160 / (lum + 1e-4)));
          tgtAcc = [Math.min(255, avgR * factor), Math.min(255, avgG * factor), Math.min(255, avgB * factor)];
        }
        return true;
      }
    } catch {
      // Ignore canvas errors
    }
    return false;
  }

  // Musical tunes palette when video is off, absent, or paused
  function tunePalette(t, lev, beat) {
    let hue = null, lumBoost = 0;
    if (melody && melody.notes && melody.notes.length) {
      const curNote = melody.notes.find((n) => t >= n.start && t <= n.end);
      if (curNote) {
        // Chromatic circle (12 semitones: C=0, C#=30, D=60, D#=90, E=120, F=150, F#=180, G=210, G#=240, A=270, A#=300, B=330)
        const NOTE_HUES = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330];
        hue = NOTE_HUES[curNote.midi % 12];
        const oct = Math.max(2, Math.min(7, Math.floor(curNote.midi / 12)));
        lumBoost = (oct - 4) * 0.03;
      }
    }
    if (hue === null) {
      const b = lastBeat(t);
      const beatPhase = b > -Infinity ? b * 24 : 0;
      hue = (beatPhase + t * 10 + lev * 50) % 360;
    }
    tgtBg = hslToRgb(hue, 0.45, Math.max(0.06, Math.min(0.20, 0.10 + lev * 0.08 + lumBoost)));
    tgtAcc = hslToRgb(hue, 0.90, Math.max(0.45, Math.min(0.85, 0.60 + beat * 0.15 + lumBoost)));
  }

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
      const hasSampled = sampleVideo(video);
      if (!hasSampled) {
        tunePalette(t, level, beat);
      }
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
