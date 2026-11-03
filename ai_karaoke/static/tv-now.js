// Control panel: what is on stage right now, drawn the same way whether this device plays the
// audio (player, tv.js) or only remote-controls the laptop (controller, host/controller.js):
// the stage monitor (muted video + lyrics), the idle / "getting ready" card, now singing, the
// timeline and the play icon. Both decks answer the same questions — Deck.current (the entry on
// stage), Deck.time(), Deck.paused, Deck.seekTo(t) — so this file never asks which one it is.
// Needs common.js, stage.js, loading.js, pulse.js and the markup (host/markup-*.js).
// Globals: inst / voc (the audio elements, used only by the player), stage, loading, pulse,
// Deck (set by host/boot.js), showStage(on, queue), showSinger(entry), resetNowPlaying(),
// setDuration(seconds).
const inst = $("inst"), voc = $("voc"), seek = $("seek");
const stage = createStage({ main: $("line-main"), next: $("line-next"), hint: $("countdown"),
                            noLyrics: $("no-lyrics"), video: $("stage-video") });
const loading = createLoading($("loading"), true);   // compact: the projector has the big one
const pulse = createPulse();   // adaptive theme: light follows the music
let Deck = null;               // the player or the controller, chosen once by host/boot.js
let scrubbing = false;

function showStage(on, queue = []) {
  $("stage").classList.toggle("hidden", !on);
  const waiting = loading.render(on ? [] : queue);   // nothing plays, songs wait: show their progress
  $("idle").classList.toggle("hidden", on);
  $("idle").classList.toggle("has-loading", waiting);
  $("idle-mic").classList.remove("hidden");
}

function showSinger(entry) {
  $("np-singer").textContent = singers(entry);
  $("np-title").textContent = entry.title;
  const lbtn = $("np-lyrics-btn");
  lbtn.classList.remove("hidden");
  lbtn.onclick = () => openLyrics(entry);
}

function resetNowPlaying() {
  $("np-singer").textContent = "Nobody yet";
  $("np-title").textContent = "Pick a song to get started";
  $("np-lyrics-btn").classList.add("hidden");
  $("time-cur").textContent = "0:00";
  $("time-dur").textContent = "0:00";
  seek.value = 0;
  seek.max = 0;
  setIcon($("btn-play"), "play");
}
resetNowPlaying();

function setDuration(seconds) {
  if (!(seconds > 0)) return;
  seek.max = seconds;
  $("time-dur").textContent = fmt(seconds);
}

// Timeline: dragging previews the time; letting go seeks (the player's tracks, or the laptop's)
seek.oninput = () => { scrubbing = true; $("time-cur").textContent = fmt(Number(seek.value)); };
seek.onchange = () => { scrubbing = false; Deck?.seekTo(Number(seek.value)); };

// One animation loop for the monitor, the timeline and the adaptive light
function tick() {
  requestAnimationFrame(tick);
  const entry = Deck?.current;
  if (!entry) return;
  const t = Deck.time();
  if (!scrubbing) { seek.value = t; $("time-cur").textContent = fmt(t); }
  stage.render(t, !Deck.paused);
  pulse.render(t, entry.song_id);
  Deck.render?.(t);   // the player also draws the singing game
}
requestAnimationFrame(tick);
