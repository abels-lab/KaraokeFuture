// Projector screen: video + lyrics only, no audio and no controls. It follows the control
// panel's clock — instantly via BroadcastChannel when both windows run on the same laptop,
// otherwise via the WebSocket — and predicts the time between updates for smooth motion.
// The intro countdown and "Player 2 joined" are the control panel's too: this page only shows
// them. With nothing playing but songs waiting, the loading screen tracks their progress.
const stage = createStage({ main: $("line-main"), next: $("line-next"), hint: $("hint"),
                            noLyrics: $("no-lyrics"), video: $("video") });
let current = null, clock = { uid: null, time: 0, paused: true, at: 0 }, lastClockAt = 0;
// Singing game: effects / note lanes over the stage, results card at the end of a song
const gameView = createGameView(document.body, stage);
const intro = createIntro(), loading = createLoading($("loading")), pulse = createPulse();
let game = null, gameAt = 0, introAt = 0;
function onGame(m) {
  if (m.type === "game_result") gameView.showResults(m);
  else if (m.uid === current?.uid) {
    // Battle / score: a second singer appeared mid-song (phone join or singing into mic 2)
    if (game?.uid === m.uid && m.players.length > game.players.length) toast(`🎤 ${m.players[m.players.length - 1].name} joined!`);
    game = m; gameAt = performance.now();
  }
}
function onIntro(m) {
  if (m.uid !== current?.uid || !(m.left > 0)) { intro.hide(); return; }
  introAt = performance.now();
  intro.show({ entry: current, ...m });
}

const now = () => clock.paused ? clock.time : clock.time + (performance.now() - clock.at) / 1000;

function onClock(m) {
  if (!current || m.uid !== current.uid) return;
  lastClockAt = performance.now();
  const jump = Math.abs(now() - m.time) > 0.35;
  // Keep the running prediction unless the clock state changed or it is clearly off:
  // re-basing on every message would make the words jitter by the network delay
  if (m.paused !== clock.paused || clock.uid !== m.uid || Math.abs(now() - m.time) > 0.12) {
    clock = { uid: m.uid, time: m.time, paused: m.paused, at: lastClockAt };
    if (jump) stage.seek?.(m.time);
  }
}

connectWS("screen", (msg) => {
  if (msg.type === "state") onState(msg.data);
  else if (msg.type === "playback") onClock(msg);
  else if (msg.type === "media" && current?.song_id === msg.song_id) stage.load(current);
  else if (msg.type === "game" || msg.type === "game_result") onGame(msg);
  else if (msg.type === "intro") onIntro(msg);
  else if (msg.type === "library") loading.poke();
});
if ("BroadcastChannel" in window) {
  new BroadcastChannel("karaoke-clock").onmessage = (e) => (e.data.type === "intro" ? onIntro(e.data) : onClock(e.data));
  new BroadcastChannel("karaoke-game").onmessage = (e) => onGame(e.data);
}

function onState({ now_playing: np, queue }) {
  renderUpNext(queue);
  if (!np) {
    if (current) { stage.clear(); gameView.clear(); intro.hide(); pulse.clear(); }
    current = null;
  } else if (current?.uid !== np.uid) {
    current = np;
    clock = { uid: np.uid, time: 0, paused: true, at: performance.now() };
    game = null;
    intro.hide();
    stage.load(np);
    gameView.load(np);
  } else {
    current = np;   // same song, fresher details (a battle partner joined or left)
  }
  if (current) { $("singer").textContent = singers(current); $("title").textContent = current.title; }
  $("stage").classList.toggle("hidden", !current);
  $("stage").classList.toggle("flex", Boolean(current));
  const waiting = loading.render(current ? [] : queue);   // songs wait, none ready yet: their progress
  $("idle").classList.toggle("hidden", Boolean(current) || waiting);
}

function renderUpNext(queue) {
  const next = queue.find((e) => e.status === "ready") || queue[0];
  $("up-next").classList.toggle("hidden", !next);
  if (next) { $("up-next-singer").textContent = singers(next); $("up-next-title").textContent = next.title; }
  $("idle-next").replaceChildren(...(queue.length ? [el("p", "text-center font-semibold uppercase tracking-widest text-gold", "Up next")] : []),
    ...queue.slice(0, 4).map((e, i) => el("p", "truncate text-stone-200", `${i + 1}. ${singers(e)} — ${e.title}`)));
}

function tick() {
  requestAnimationFrame(tick);
  // The countdown's last message got lost (control panel closed mid-intro): don't stay stuck on it
  if (intro.visible && performance.now() - introAt > 1500) intro.hide();
  if (!current) return;
  stage.render(now(), !clock.paused);
  pulse.render(now(), current.song_id);
  $("info-card").style.opacity = Look.infoCard(now(), current.duration || 0) ? "1" : "0";   // who sings + who's next
  gameView.render(now(), performance.now() - gameAt < 1000 ? game : null); // stale = nobody singing
  // No clock for 3 s while a song should be playing: the control panel is gone or reconnecting
  $("lost").classList.toggle("hidden", clock.paused || performance.now() - lastClockAt < 3000);
}

// Fullscreen needs a user gesture; the cursor hides after 2 s without movement
const toggleFullscreen = () => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen().catch(() => {});
document.addEventListener("click", toggleFullscreen);
document.addEventListener("keydown", (e) => { if (e.key === "f" || e.key === "F") toggleFullscreen(); });
document.addEventListener("fullscreenchange", () => { $("fs-tip").style.opacity = document.fullscreenElement ? "0" : "1"; });
let cursorTimer = null;
document.addEventListener("mousemove", () => {
  document.body.classList.remove("idle-cursor");
  clearTimeout(cursorTimer);
  cursorTimer = setTimeout(() => document.body.classList.add("idle-cursor"), 2000);
});

api("/api/info").then(({ qr, remote_url: url }) => { $("qr").src = qr; $("qr-url").textContent = url; });
requestAnimationFrame(tick);
