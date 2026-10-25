// Control panel (laptop): plays the audio and is the clock every projector screen follows.
// Shows a monitor of the stage (video + lyrics) and transport with scrubbing; the sidebar,
// buttons and keys are in tv-side.js. Before each song the intro countdown runs (intro-run.js),
// and while the next song is still being prepared the loading screen shows (loading.js).
const inst = $("inst"), voc = $("voc"), seek = $("seek");
const stage = createStage({ main: $("line-main"), next: $("line-next"), hint: $("countdown"),
                            noLyrics: $("no-lyrics"), video: $("stage-video") });
const loading = createLoading($("loading"), true);   // compact: the projector has the big one
const pulse = createPulse();   // adaptive theme: light follows the music
// Same-machine projector windows get the clock instantly; other devices via the WebSocket
const channel = "BroadcastChannel" in window ? new BroadcastChannel("karaoke-clock") : null;
let current = null, scrubbing = false;

const send = connectWS("tv", (msg) => {
  if (msg.type === "state") onState(msg.data);
  else if (msg.type === "control") onControl(msg.action, msg.value);
  else if (msg.type === "media" && current?.song_id === msg.song_id) stage.load(current);
  else if (msg.type === "library") loading.poke();   // a pipeline stage moved on
}, () => {
  if (current && !inst.paused) {
    send({
      type: "sync_playback",
      uid: current.uid,
      time: inst.currentTime,
      duration: inst.duration || 0,
      paused: inst.paused,
    });
  }
});
GamePanel.init(send);

function sendClock() {
  if (!current) return;
  try {
    sessionStorage.setItem("karaoke_active_playback", JSON.stringify({ uid: current.uid, time: inst.currentTime, paused: inst.paused }));
  } catch {}
  const clock = { type: "playback", uid: current.uid, time: inst.currentTime, duration: inst.duration || 0, paused: inst.paused };
  send(clock);
  channel?.postMessage(clock);
}
setInterval(sendClock, 250);

function onState({ now_playing: np, queue = [], played = [], screens = 0 }) {
  renderSide(queue, played, screens, np);
  if (!np) {
    try { sessionStorage.removeItem("karaoke_active_playback"); } catch {}
    if (current) stopSong();
    showStage(false, queue);
    if (window.__pendingReload) { location.reload(); return; }
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
    Object.assign(current, { guide: np.guide, mode: np.mode });
    Guide.forEntry(current);
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

// ── Player ────────────────────────────────────────────────────────────────
function showStage(on, queue = []) {
  $("stage").classList.toggle("hidden", !on);
  const waiting = loading.render(on ? [] : queue);   // nothing plays, songs wait: show their progress
  $("idle").classList.toggle("hidden", on);
  $("idle-mic").classList.toggle("hidden", waiting);   // room for the loading card under the QR code
}
const showSinger = (entry) => { $("np-singer").textContent = singers(entry); $("np-title").textContent = entry.title; };

async function loadSong(entry) {
  IntroRun.stop();
  current = entry;
  showSinger(entry);
  showStage(true);
  inst.src = entry.media.instrumental; voc.src = entry.media.vocals;
  Guide.forEntry(entry); // the singer's own guide volume, if they chose one

  let savedTime = 0, wasPaused = false;
  try {
    const raw = sessionStorage.getItem("karaoke_active_playback");
    if (raw) {
      const sp = JSON.parse(raw);
      if (sp?.uid === entry.uid && Number.isFinite(sp.time)) {
        savedTime = Number(sp.time);
        wasPaused = Boolean(sp.paused);
      }
    }
  } catch {}
  if (entry.playback && (entry.playback.uid === entry.uid || !entry.playback.uid) && Number.isFinite(entry.playback.time)) {
    const srvTime = Number(entry.playback.time);
    if (srvTime > savedTime) {
      savedTime = srvTime;
      wasPaused = Boolean(entry.playback.paused);
    }
  }

  const isResuming = savedTime > 1.5;

  await Promise.all([stage.load(entry), GamePanel.load(entry)]);
  if (current !== entry) return; // another song started while lyrics loaded

  if (isResuming) {
    IntroRun.stop();
    const introMsg = { type: "intro", uid: entry.uid, left: 0, total: 0, mode: entry.mode || "", names: [] };
    send(introMsg);
    channel?.postMessage(introMsg);

    const applyResume = () => {
      if (current !== entry) return;
      seekTo(savedTime);
      stage.seek?.(savedTime);
      if (!wasPaused) play();
    };

    if (inst.readyState >= 1) {
      applyResume();
    } else {
      inst.addEventListener("loadedmetadata", applyResume, { once: true });
    }
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
  if (inst.readyState >= 1) seekTo(intro);
  else inst.addEventListener("loadedmetadata", () => { if (current === entry && inst.currentTime < 1.0) seekTo(intro); }, { once: true });
}

function stopSong() {
  try { sessionStorage.removeItem("karaoke_active_playback"); } catch {}
  current = null; pause(); stage.clear(); pulse.clear(); GamePanel.clear(); Guide.forEntry(null);
  [inst, voc].forEach((a) => { a.removeAttribute("src"); a.load(); });
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

const reportEnded = (delay = 0) => {
  try { sessionStorage.removeItem("karaoke_active_playback"); } catch {}
  const uid = current?.uid;
  if (uid) setTimeout(() => send({ type: "ended", uid }), delay);
};
inst.onended = () => reportEnded(GamePanel.finish()); // game on: results stay up before the next song

let instRetries = 0, lastRetryTime = 0;
function handleAudioError(audio, isInst) {
  if (!current) return;
  const src = audio.getAttribute("src");
  if (!src) return;

  const now = performance.now();
  if (now - lastRetryTime > 15000) instRetries = 0;
  lastRetryTime = now;
  instRetries++;

  if (instRetries <= 5) {
    const resumeAt = audio.currentTime;
    const wasPlaying = !audio.paused;
    setTimeout(() => {
      if (!current) return;
      audio.load();
      const onReady = () => {
        if (!current) return;
        audio.currentTime = resumeAt;
        if (wasPlaying) audio.play().catch(() => {});
      };
      if (audio.readyState >= 1) onReady();
      else audio.addEventListener("loadedmetadata", onReady, { once: true });
    }, 800);
  } else if (isInst) {
    reportEnded(3000); // truly broken after 5 retries -> skip
  }
}

function handleAudioStall(audio) {
  if (!current || audio.paused) return;
  const t = audio.currentTime;
  try { audio.currentTime = t; } catch {}
}

inst.onerror = () => handleAudioError(inst, true);
voc.onerror = () => handleAudioError(voc, false);

let instStallTimer = null;
inst.onstalled = () => {
  clearTimeout(instStallTimer);
  instStallTimer = setTimeout(() => handleAudioStall(inst), 1500);
};
let vocStallTimer = null;
voc.onstalled = () => {
  clearTimeout(vocStallTimer);
  vocStallTimer = setTimeout(() => handleAudioStall(voc), 1500);
};

inst.onplaying = () => {
  instRetries = 0;
  clearTimeout(instStallTimer);
};
voc.onplaying = () => {
  clearTimeout(vocStallTimer);
};

inst.onplay = inst.onpause = () => { setIcon($("btn-play"), inst.paused ? "play" : "pause"); sendClock(); };
inst.onseeked = sendClock; // screens jump at once instead of waiting for the next tick
inst.onloadedmetadata = () => { seek.max = inst.duration; $("time-dur").textContent = fmt(inst.duration); };

// Timeline: dragging previews the time; letting go seeks both tracks
seek.oninput = () => { scrubbing = true; $("time-cur").textContent = fmt(Number(seek.value)); };
seek.onchange = () => { scrubbing = false; seekTo(Number(seek.value)); };

// Keep the guide-vocal track locked to the instrumental. A timer, not the animation loop:
// browsers stop animation frames when this window is minimized, but timers keep running.
setInterval(() => {
  if (!current) return;
  if (voc.paused !== inst.paused) inst.paused ? voc.pause() : voc.play().catch(() => {});
  if (!inst.paused && Math.abs(voc.currentTime - inst.currentTime) > 0.08) voc.currentTime = inst.currentTime;
}, 500);

function tick() {
  requestAnimationFrame(tick);
  if (!current) return;
  const t = inst.currentTime;
  if (!scrubbing) { seek.value = t; $("time-cur").textContent = fmt(t); }
  stage.render(t, !inst.paused);
  pulse.render(t, current.song_id);
  GamePanel.render(t);
}
requestAnimationFrame(tick);
