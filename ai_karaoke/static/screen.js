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
  else if (msg.type === "chat") onChat(msg);
});
if ("BroadcastChannel" in window) {
  new BroadcastChannel("karaoke-clock").onmessage = (e) => (e.data.type === "intro" ? onIntro(e.data) : onClock(e.data));
  new BroadcastChannel("karaoke-game").onmessage = (e) => onGame(e.data);
  new BroadcastChannel("karaoke-chat").onmessage = (e) => onChat(e.data);
}

function onState({ now_playing: np, queue, playback }) {
  renderUpNext(queue);
  if (!np) {
    if (current) { stage.clear(); gameView.clear(); intro.hide(); pulse.clear(); }
    current = null;
    if (window.__pendingReload) { location.reload(); return; }
  } else if (current?.uid !== np.uid) {
    if (window.__pendingReload && current) { location.reload(); return; }
    current = np;
    const pb = np.playback || (playback?.uid === np.uid ? playback : null);
    const startTime = Number(pb?.time) || 0;
    clock = { uid: np.uid, time: startTime, paused: pb ? Boolean(pb.paused) : true, at: performance.now() };
    lastClockAt = performance.now();
    game = null;
    intro.hide();
    stage.load(np);
    if (startTime > 0) stage.seek?.(startTime);
    gameView.load(np);
  } else {
    current = np;   // same song, fresher details (a battle partner joined or left)
  }
  if (current) { $("singer").textContent = singers(current); $("title").textContent = current.title; }
  $("stage").classList.toggle("hidden", !current);
  $("stage").classList.toggle("flex", Boolean(current));
  const waiting = loading.render(current ? [] : queue);   // songs wait, none ready yet: their progress
  $("idle").classList.toggle("hidden", Boolean(current) || waiting);
  const showCorner = Boolean(current) || waiting;
  $("corner-qr")?.classList.toggle("hidden", !showCorner);
  $("corner-qr")?.classList.toggle("flex", showCorner);
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

api("/api/info").then(({ qr, remote_url: url }) => {
  $("qr").src = qr;
  $("qr-url").textContent = url;
  if ($("qr-corner")) {
    $("qr-corner").src = qr;
    $("qr-corner-url").textContent = url.replace(/^https?:\/\//, "");
  }
});
requestAnimationFrame(tick);


// Top-left temporary chat notifications (7 seconds duration, small font)
function createScreenChat(root) {
  if (!root) return { addMessage: () => {} };
  const messagesEl = $("screen-chat-messages") || root;
  const seenIds = new Set();
  let hideTimer = null;
  const MAX_MESSAGES = 4;

  function escapeText(str) {
    return String(str || "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[m]);
  }

  function formatText(text) {
    if (!text) return "";
    let t = escapeText(text);
    t = t.replace(/\*\*(.*?)\*\*/g, "<strong class='text-white font-semibold'>$1</strong>");
    t = t.replace(/`([^`]+)`/g, "<code class='rounded bg-black/50 px-1 py-0.5 text-amber-200 font-mono text-[10px]'>$1</code>");
    t = t.replace(/\n+/g, "<br>");
    return t;
  }

  function addMessage(msg) {
    if (!msg || !msg.text) return;
    const dedupKey = msg.id || `${msg.sender}:${String(msg.text).slice(0, 40)}`;
    if (seenIds.has(dedupKey)) return;
    seenIds.add(dedupKey);
    if (seenIds.size > 50) {
      const first = seenIds.values().next().value;
      seenIds.delete(first);
    }

    const isAgent = msg.sender === "agent";
    const senderName = isAgent ? "DJ Co-Pilot" : (msg.name || "Host");
    const badgeColor = isAgent ? "text-purple-300" : "text-amber-300";
    const borderColor = isAgent ? "border-purple-500/40" : "border-amber-500/40";
    const icon = isAgent ? "✨" : "🎤";

    const card = document.createElement("div");
    card.className = `rounded-xl bg-black/85 backdrop-blur-md border ${borderColor} px-3 py-2 shadow-2xl transition-all duration-300`;
    card.innerHTML = `
      <div class="flex items-center gap-1.5 ${badgeColor} text-[11px] font-bold uppercase tracking-wider">
        <span>${icon}</span>
        <span>${escapeText(senderName)}</span>
      </div>
      <div class="mt-0.5 text-[12px] leading-snug text-stone-200 break-words font-normal">
        ${formatText(msg.text)}
      </div>
    `;

    messagesEl.appendChild(card);

    while (messagesEl.children.length > MAX_MESSAGES) {
      messagesEl.firstElementChild.remove();
    }

    root.style.opacity = "1";
    root.style.pointerEvents = "auto";

    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      root.style.opacity = "0";
      root.style.pointerEvents = "none";
    }, 7000);
  }

  return { addMessage };
}

const screenChat = createScreenChat($("screen-chat"));
function onChat(m) {
  screenChat.addMessage(m);
}
