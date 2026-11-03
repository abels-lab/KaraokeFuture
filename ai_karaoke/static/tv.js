// The player (the laptop's control panel): plays the audio and is the clock every projector
// screen follows — same-machine projector windows hear it instantly (BroadcastChannel), other
// devices via the WebSocket ("playback", 4 Hz). Before each song the intro countdown runs
// (intro-run.js). Only one device should be the player: host/mode.js decides, host/boot.js
// calls HostPlayer.start() and makes it the Deck. Audio resilience (retries, the guide track's
// lock-step, resume after a reload, song ended) is in tv-audio.js; the drawing in tv-now.js.
// Needs common.js, tv-now.js, tv-audio.js, game-panel.js, guide.js, intro-run.js and send()
// (host/boot.js: the page's one WebSocket).
// HostPlayer = { start(), onOpen(), onState(state), onControl(action, value), onMedia(song_id),
//   play(), pause(), toggle(), restart(), seekTo(t), seekBy(s), prev(), next(), time(), paused,
//   current, introRunning, skipIntro(), render(t) } — the Deck interface shared with host/controller.js.
const clockChannel = "BroadcastChannel" in window ? new BroadcastChannel("karaoke-clock") : null;
let current = null;   // the entry playing here (global: guide.js reads it)

function sendClock() {
  if (!current) return;
  TvAudio.remember(current.uid);
  const clock = { type: "playback", uid: current.uid, time: inst.currentTime, duration: inst.duration || 0, paused: inst.paused };
  send(clock);
  clockChannel?.postMessage(clock);
}

function onState({ now_playing: np, queue = [], played = [], screens = 0, active_playlist = null }) {
  renderSide(queue, played, screens, np, active_playlist);
  if (!np) {
    TvAudio.forget();
    if (current) stopSong();
    resetNowPlaying();
    showStage(false, queue);
    if (window.__pendingReload) location.reload();
    return;
  }
  if (!current || current.uid !== np.uid) {
    if (window.__pendingReload && current) { location.reload(); return; }
    loadSong(np);
    return;
  }
  if (JSON.stringify(current.partner) !== JSON.stringify(np.partner)) { // a second singer joined / left
    current.partner = np.partner;
    showSinger(current);
    GamePanel.partnerChanged(current);
  }
  if (current.guide !== np.guide || current.mode !== np.mode) { // the singer changed their choice mid-song
    const modeChanged = current.mode !== np.mode;
    const guideChanged = current.guide !== np.guide;
    current.mode = np.mode;
    if (!Guide.isHostLocked?.(current.uid)) {
      current.guide = np.guide;
      if (guideChanged) Guide.forEntry(current);
    }
    if (modeChanged) GamePanel.load(current);
  }
}

function onControl(action, value) {
  if (action === "play") play();
  else if (action === "pause") pause();
  else if (action === "restart") { seekTo(0); play(); }
  else if (action === "seek") seekTo(value);
  else if (action === "seek_by") seekTo(inst.currentTime + value);
}

async function loadSong(entry) {
  IntroRun.stop();
  current = entry;
  showSinger(entry);
  showStage(true);
  inst.src = entry.media.instrumental; voc.src = entry.media.vocals;
  Guide.forEntry(entry); // the singer's own guide volume, if they chose one
  const { time: savedTime, paused: wasPaused } = TvAudio.resumePoint(entry);

  await Promise.all([stage.load(entry), GamePanel.load(entry)]);
  if (current !== entry) return; // another song started while lyrics loaded

  if (savedTime > 1.5) {   // a reload mid-song: carry on where it was, no countdown
    const introMsg = { type: "intro", uid: entry.uid, left: 0, total: 0, mode: entry.mode || "", names: [] };
    send(introMsg);
    clockChannel?.postMessage(introMsg);
    TvAudio.whenReady(() => {
      if (current !== entry) return;
      seekTo(savedTime);
      if (!wasPaused) play();
    });
  } else {
    skipSpokenIntro(entry);
    // The intro card counts down; play() from anywhere (Space, a phone) cuts it short itself
    if (await IntroRun.start(entry, GamePanel.intro, send) && current === entry) play();
  }
}

// A music video's spoken intro / skit (SponsorBlock intro_end): start at the music instead
function skipSpokenIntro(entry) {
  const intro = Number(entry.media?.intro_end ?? 0);
  if (!Settings.get("skip_intro", true) || !(intro > 0)) return;
  TvAudio.whenReady(() => { if (current === entry && inst.currentTime < 1.0) seekTo(intro); });
}

function stopSong() {
  TvAudio.forget();
  current = null; pause(); stage.clear(); pulse.clear(); GamePanel.clear(); Guide.forEntry(null);
  [inst, voc].forEach((a) => { a.removeAttribute("src"); a.load(); });
  resetNowPlaying();
}

function play() {
  if (!current) return;
  IntroRun.stop(); // pressed during the countdown: start right now
  voc.currentTime = inst.currentTime;
  Promise.all([inst.play(), voc.play()]).catch((err) => {
    if (err.name === "NotAllowedError") $("unlock").classList.remove("hidden");
  });
}
function pause() { IntroRun.stop(); inst.pause(); voc.pause(); }

function seekTo(t) {
  if (!current || !Number.isFinite(t)) return;
  const dur = inst.duration;
  const max = Number.isFinite(dur) && dur > 0 ? dur - 0.25 : t;
  const target = Math.max(0, Math.min(t, max));
  inst.currentTime = voc.currentTime = target;
  stage.seek?.(target);
}

const HostPlayer = {
  isPlayer: true,
  start() {
    GamePanel.init(send);
    TvAudio.install();
    setInterval(sendClock, 250);
  },
  // Reconnected: tell the server (and so every screen) where the song is right now
  onOpen() {
    if (current && !inst.paused) send({ type: "sync_playback", uid: current.uid, time: inst.currentTime, duration: inst.duration || 0, paused: inst.paused });
  },
  onState, onControl,
  onMedia(songId) { if (current?.song_id === songId) stage.load(current); },
  play, pause, seekTo,
  toggle: () => (inst.paused ? play() : pause()),
  restart: () => onControl("restart"),
  seekBy: (s) => seekTo(inst.currentTime + s),
  prev: () => send({ type: "control", action: "previous" }),
  next: () => send({ type: "control", action: "skip" }),
  time: () => inst.currentTime,
  get introRunning() { return IntroRun.running; },
  skipIntro: () => IntroRun.skip(),
  get paused() { return inst.paused; },
  get current() { return current; },
  render: (t) => GamePanel.render(t),
};
