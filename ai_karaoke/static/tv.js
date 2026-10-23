// Control panel (laptop): plays the audio and is the clock every projector screen follows.
// Shows a monitor of the stage (video + lyrics), transport with scrubbing, and the queue.
const inst = $("inst"), voc = $("voc"), seek = $("seek");
const stage = createStage({ main: $("line-main"), next: $("line-next"), hint: $("countdown"),
                            noLyrics: $("no-lyrics"), video: $("stage-video") });
// Same-machine projector windows get the clock instantly; other devices via the WebSocket
const channel = "BroadcastChannel" in window ? new BroadcastChannel("karaoke-clock") : null;
let current = null, scrubbing = false;

const send = connectWS("tv", (msg) => {
  if (msg.type === "state") onState(msg.data);
  else if (msg.type === "control") onControl(msg.action, msg.value);
  else if (msg.type === "media" && current?.song_id === msg.song_id) stage.load(current);
});
GamePanel.init(send);

function sendClock() {
  if (!current) return;
  const clock = { type: "playback", uid: current.uid, time: inst.currentTime, duration: inst.duration || 0, paused: inst.paused };
  send(clock);
  channel?.postMessage(clock);
}
setInterval(sendClock, 250);

function onState({ now_playing: np, queue, screens = 0 }) {
  renderQueue(queue);
  $("screens").textContent = screens ? `📽 ${screens} projector screen${screens > 1 ? "s" : ""} connected` : "No projector screen connected";
  $("screens").classList.toggle("text-emerald-400", screens > 0);
  if (!np) { if (current) stopSong(); showStage(false); }
  else if (!current || current.uid !== np.uid) loadSong(np);
}

function onControl(action, value) {
  if (action === "play") play();
  else if (action === "pause") pause();
  else if (action === "restart") { seekTo(0); play(); }
  else if (action === "seek") seekTo(value);
  else if (action === "seek_by") seekTo(inst.currentTime + value);
}

// ── Player ────────────────────────────────────────────────────────────────
const showStage = (on) => { $("stage").classList.toggle("hidden", !on); $("idle").classList.toggle("hidden", on); };

async function loadSong(entry) {
  current = entry;
  $("np-singer").textContent = entry.singer; $("np-title").textContent = entry.title;
  showStage(true);
  inst.src = entry.media.instrumental; voc.src = entry.media.vocals;
  await Promise.all([stage.load(entry), GamePanel.load(entry)]);
  if (current === entry) {
    const intro = Number(entry.media?.intro_end ?? 0);
    if (Settings.get("skip_intro", true) && intro > 0) {
      if (inst.readyState >= 1) {
        seekTo(intro);
      } else {
        inst.addEventListener("loadedmetadata", () => {
          if (current === entry && inst.currentTime < 1.0) seekTo(intro);
        }, { once: true });
      }
    }
    play(); // unless another song started while lyrics loaded
  }
}

function stopSong() {
  current = null; pause(); stage.clear(); GamePanel.clear();
  [inst, voc].forEach((a) => { a.removeAttribute("src"); a.load(); });
}

function play() {
  if (!current) return;
  voc.currentTime = inst.currentTime;
  Promise.all([inst.play(), voc.play()]).catch((err) => {
    if (err.name === "NotAllowedError") $("unlock").classList.remove("hidden");
  });
}
function pause() { inst.pause(); voc.pause(); }

function seekTo(t) {
  if (!current || !Number.isFinite(t)) return;
  const dur = inst.duration;
  const max = Number.isFinite(dur) && dur > 0 ? dur - 0.25 : t;
  inst.currentTime = voc.currentTime = Math.max(0, Math.min(t, max));
}

const reportEnded = (delay = 0) => { const uid = current?.uid; if (uid) setTimeout(() => send({ type: "ended", uid }), delay); };
inst.onended = () => reportEnded(GamePanel.finish()); // game on: results stay up before the next song
inst.onerror = () => inst.getAttribute("src") && reportEnded(3000); // broken file -> skip
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
  GamePanel.render(t);
}

function renderQueue(queue) {
  $("queue-count").textContent = queue.length;
  $("queue-empty").classList.toggle("hidden", queue.length > 0);
  $("queue").replaceChildren(...queue.map((e, i) => queueRow(e, i, queue.length)));
}

// ── Controls & startup ────────────────────────────────────────────────────
const setGuide = (v, remember = true) => {
  voc.volume = v / 100; $("guide").value = v; $("guide-value").textContent = `${v}%`;
  if (remember) store("guideVolume", String(v)); // moved by hand: this laptop keeps its own value
};
// Until the slider is moved here, follow the Settings page's default (also when it changes)
const initGuide = () => setGuide(Number(store("guideVolume") ?? Settings.get("guide_default", 20)), false);
Settings.onChange(initGuide);
$("guide").oninput = (e) => setGuide(Number(e.target.value));
$("btn-play").onclick = () => (inst.paused ? play() : pause());
$("btn-restart").onclick = () => onControl("restart");
$("btn-back").onclick = () => seekTo(inst.currentTime - 10);
$("btn-fwd").onclick = () => seekTo(inst.currentTime + 10);
$("btn-skip").onclick = () => send({ type: "control", action: "skip" });
$("unlock").onclick = () => {
  $("unlock").classList.add("hidden");
  play();
  // Audio input also needs this first click; restart the mics if they were on last time
  if (store("micsOn") === "1") Mics.start().then(() => micStrip?.render()).catch((err) => toast(`Microphones: ${err.message}`, false));
};
$("open-mics").onclick = () => openMicSetup();
// A separate window: drag it onto the projector, then click it (or press F) for fullscreen
$("open-screen").onclick = () => window.open("/screen", "karaoke-screen", "popup,width=1280,height=720");
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" && e.target.type !== "range") return;
  if (e.code === "Space") { e.preventDefault(); $("btn-play").click(); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); seekTo(inst.currentTime - 5); }
  else if (e.key === "ArrowRight") { e.preventDefault(); seekTo(inst.currentTime + 5); }
  else if (e.key === "n") $("btn-skip").click();
  else if (e.key === "f") document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
});

api("/api/info").then(({ qr, remote_url: url }) => {
  $("qr").src = $("qr-big").src = qr; $("qr-url").textContent = $("qr-url-big").textContent = url;
});
initGuide();
requestAnimationFrame(tick);
