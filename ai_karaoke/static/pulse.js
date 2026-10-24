// Adaptive theme (experimental): the stage light follows the music. The backing track's loudness
// and beats come from the server once per song (services/pulse.py); every frame this sets two
// CSS variables on <body> from the page's own playback clock, which theme.css turns into light:
// --level (0..1, smoothed loudness) and --beat (1 on a beat, fading out over BEAT_FADE seconds).
// Needs common.js + look.js. createPulse() -> { clear(), render(time, songId) } (fetches per song itself)
const BEAT_FADE = 0.28;

function createPulse() {
  let data = null, songId = null, level = 0;
  const style = document.body.style;
  const on = () => Settings.get("theme", "theater") === "adaptive";

  async function fetchFor(id) {
    if (songId === id && data) return;
    songId = id; data = null;
    try {
      const fresh = await api(`/api/songs/${id}/pulse`);
      if (songId === id) data = fresh;
    } catch { /* not ready or no instrumental: the theme just stays calm */ }
  }

  function clear() { songId = null; data = null; style.setProperty("--level", "0"); style.setProperty("--beat", "0"); }

  // Last beat at or before t (binary search: songs have hundreds of beats)
  function lastBeat(t) {
    const b = data.beats;
    let lo = 0, hi = b.length - 1, found = -Infinity;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (b[mid] <= t) { found = b[mid]; lo = mid + 1; } else hi = mid - 1;
    }
    return found;
  }

  function render(t, id) {
    if (!on()) { if (level) { level = 0; style.setProperty("--level", "0"); style.setProperty("--beat", "0"); } return; }
    if (id && id !== songId) fetchFor(id);
    if (!data) return;
    const target = data.level[Math.round(t / data.hop)] || 0;
    level += (target - level) * 0.1;   // smoothed, so the light breathes instead of flickering
    style.setProperty("--level", level.toFixed(3));
    style.setProperty("--beat", Math.max(0, 1 - (t - lastBeat(t)) / BEAT_FADE).toFixed(3));
  }

  return { clear, render };
}
