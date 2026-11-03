// Target colours for the adaptive theme (pulse.js): sampled from the video frame when it plays,
// else from the melody note being sung (or drifting with the beat and loudness).
// Colours are [r, g, b] 0-255. createFrameSampler() -> sample(video) -> {bg, acc} | null;
// tuneColors(melody, t, level, beat, lastBeatAt) -> {bg, acc}
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

// Average + most saturated colour of a 16x16 thumbnail of the playing video
function createFrameSampler() {
  let canvas = null, ctx = null;

  function getCtx() {
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvas.width = 16;
      canvas.height = 16;
      ctx = canvas.getContext("2d", { willReadFrequently: true });
    }
    return ctx;
  }

  return function sample(v) {
    if (!v || v.readyState < 2 || v.paused || v.ended || document.body.classList.contains("no-video")) {
      return null;
    }
    const c = getCtx();
    if (!c) return null;
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
        const bg = [avgR, avgG, avgB];

        if (bestSat > 0.2) {
          const accLum = 0.299 * bestR + 0.587 * bestG + 0.114 * bestB;
          const factor = Math.min(2.5, Math.max(1.0, 150 / (accLum + 1e-4)));
          return { bg, acc: [Math.min(255, bestR * factor), Math.min(255, bestG * factor), Math.min(255, bestB * factor)] };
        }
        const lum = 0.299 * avgR + 0.587 * avgG + 0.114 * avgB;
        const factor = Math.min(2.2, Math.max(1.0, 160 / (lum + 1e-4)));
        return { bg, acc: [Math.min(255, avgR * factor), Math.min(255, avgG * factor), Math.min(255, avgB * factor)] };
      }
    } catch {
      // Ignore canvas errors
    }
    return null;
  };
}

// Musical tunes palette when video is off, absent, or paused
function tuneColors(melody, t, lev, beat, lastBeatAt) {
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
    const beatPhase = lastBeatAt > -Infinity ? lastBeatAt * 24 : 0;
    hue = (beatPhase + t * 10 + lev * 50) % 360;
  }
  return {
    bg: hslToRgb(hue, 0.45, Math.max(0.06, Math.min(0.20, 0.10 + lev * 0.08 + lumBoost))),
    acc: hslToRgb(hue, 0.90, Math.max(0.45, Math.min(0.85, 0.60 + beat * 0.15 + lumBoost))),
  };
}
