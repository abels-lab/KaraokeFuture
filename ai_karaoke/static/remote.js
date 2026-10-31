// Guest phone: join the party with your name, find songs, add them to the queue and control
// your own playback. Needs common.js, auth.js, lyrics.js.
let nowEntry = null;

// Tab switcher: find songs vs personal queue
let currentTab = "songs";
function switchTab(tab) {
  currentTab = tab;
  const isSongs = tab === "songs";
  $("panel-songs")?.classList.toggle("hidden", !isSongs);
  $("panel-queue")?.classList.toggle("hidden", isSongs);

  if ($("tab-btn-songs")) {
    $("tab-btn-songs").className = `flex-1 flex items-center justify-center gap-2 rounded-xl py-2.5 transition-all font-bold ${
      isSongs
        ? "bg-gradient-to-r from-amber-500 to-yellow-400 text-stone-950 shadow-md"
        : "text-stone-400 hover:text-stone-200"
    }`;
  }
  if ($("tab-btn-queue")) {
    $("tab-btn-queue").className = `flex-1 flex items-center justify-center gap-2 rounded-xl py-2.5 transition-all font-bold ${
      !isSongs
        ? "bg-gradient-to-r from-amber-500 to-yellow-400 text-stone-950 shadow-md"
        : "text-stone-400 hover:text-stone-200"
    }`;
  }
}

$("tab-btn-songs")?.addEventListener("click", () => switchTab("songs"));
$("tab-btn-queue")?.addEventListener("click", () => switchTab("queue"));
$("btn-goto-songs")?.addEventListener("click", () => switchTab("songs"));

// ── Live state ────────────────────────────────────────────────────────────
let lastState = { now_playing: null, queue: [], played: [] };
function renderState(state = lastState) {
  lastState = state;
  const { now_playing: np, queue = [], played = [], active_playlist = null } = state;
  const mayControl = Auth.me.admin || Auth.owns(np);
  const mayScrub = Auth.me.admin || (Auth.owns(np) && Settings.get("guest_scrubbing", false));
  nowEntry = np;
  $("np-singer").textContent = np ? singers(np) : "Nobody yet";
  $("np-title").textContent = np ? np.title : "Add a song to get started";
  $("np-seek").disabled = !np || !mayScrub;
  $("transport").classList.toggle("hidden", Boolean(np) && !mayControl);
  $("transport-note").classList.toggle("hidden", !np || mayControl);

  // Update previous and next song buttons on remote
  const prev = played.length > 0 ? played[played.length - 1] : null;
  const next = queue.length > 0 ? queue[0] : (active_playlist?.queue?.[0] || null);
  if ($("remote-btn-prev")) {
    $("remote-btn-prev").disabled = !prev || !Auth.me.admin;
    if ($("remote-prev-label")) $("remote-prev-label").textContent = prev ? prev.title : "None";
    $("remote-btn-prev").title = prev ? `Previous: ${prev.title} (${singers(prev)})` : "No previous song";
  }
  if ($("remote-btn-next")) {
    $("remote-btn-next").disabled = !next || !(Auth.me.admin || Auth.owns(np));
    if ($("remote-next-label")) $("remote-next-label").textContent = next ? (next.title || next.query) : "Queue empty";
    $("remote-btn-next").title = next ? `Next: ${next.title || next.query}` : "No upcoming song";
  }

  document.querySelectorAll('#transport button[data-action="seek_by"]').forEach((b) => {
    b.disabled = !mayScrub;
    b.classList.toggle("opacity-40", !mayScrub);
    b.classList.toggle("pointer-events-none", !mayScrub);
  });

  if (!np) {
    renderPlayback({ uid: null, time: 0, duration: 0, paused: true });
  } else {
    const pb = np.playback || (state.playback?.uid === np.uid ? state.playback : null);
    if (pb && Number.isFinite(pb.time)) renderPlayback(pb);
  }

  const isAdmin = Boolean(Auth.me.admin);
  $("np-lyrics").classList.toggle("hidden", !np);
  if (np) {
    if (isAdmin) {
      $("np-lyrics").textContent = needsLyrics(np) ? "📝 AI lyrics: fix" : "📝 Edit lyrics";
      $("np-lyrics").className = `rounded-lg px-2.5 py-1 text-xs font-semibold ${
        needsLyrics(np) ? "bg-amber-900/80 text-amber-200 ring-1 ring-amber-500/50" : "bg-white/10 text-stone-200 hover:bg-white/20"
      }`;
    } else {
      $("np-lyrics").textContent = "📖 Read lyrics";
      $("np-lyrics").className = "rounded-lg bg-white/10 px-2.5 py-1 text-xs font-semibold text-stone-200 hover:bg-white/20";
    }
  }

  // Once a song starts playing, only the host can tweak guide vocals / mode mid-song
  $("np-prefs").replaceChildren(...(isAdmin && np && !dragging ? [songPrefs(np)] : []));
  renderNowBattle();
  renderQueue(queue, played, active_playlist);
}
Auth.onChange(() => renderState());

// Battle on stage: "Join" while its intro counts down. Intro messages come 4x a second: redraw
// only when the buttons change, so a tap never lands on a button being replaced
let npBattleKey = "";
function renderNowBattle(force = true) {
  const items = Battle.controls(nowEntry, { playing: true });
  const key = `${nowEntry?.uid}|${nowEntry?.partner?.id}|${items.map((b) => b.textContent).join()}`;
  if (!force && key === npBattleKey) return;
  npBattleKey = key;
  $("np-battle").replaceChildren(...items);
}

// ── Playback sync ────────────────────────────────────────────────────────
function renderPlayback({ time, duration, paused }) {
  if (!dragging) {
    $("np-seek").max = Math.round(duration);
    $("np-seek").value = Math.round(time);
    $("np-cur").textContent = fmtDuration(time);
    $("np-dur").textContent = fmtDuration(duration);
  }
  const btn = $("btn-toggle");
  btn.dataset.action = paused ? "play" : "pause";
  btn.innerHTML = paused
    ? '<svg viewBox="0 0 24 24" class="h-6 w-6 fill-current"><path d="M8 5v14l11-7z"/></svg>'
    : '<svg viewBox="0 0 24 24" class="h-6 w-6 fill-current"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>';
}

$("np-seek").oninput = () => { dragging = true; $("np-cur").textContent = fmtDuration($("np-seek").value); };
$("np-seek").onchange = () => { dragging = false; send({ type: "control", action: "seek", value: Number($("np-seek").value) }); };

document.querySelectorAll("#transport button").forEach((b) => {
  b.onclick = () => send({ type: "control", action: b.dataset.action, value: b.dataset.value });
});

// Previous and next buttons on remote
$("remote-btn-prev")?.addEventListener("click", () => send({ type: "control", action: "previous" }));
$("remote-btn-next")?.addEventListener("click", () => send({ type: "control", action: "skip" }));

$("np-lyrics").onclick = () => nowEntry && openLyrics(nowEntry);

// ── WebSocket ────────────────────────────────────────────────────────────
let remoteWs = null;
function send(msg) {
  if (remoteWs?.readyState === WebSocket.OPEN) remoteWs.send(JSON.stringify(msg));
}
function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws?role=remote`);
  remoteWs = ws;
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === "state") renderState(msg.data);
      else if (msg.type === "playback") renderPlayback(msg);
      else if (msg.type === "intro") IntroRun.show(msg);
      else if (msg.type === "denied") toast(msg.message, false);
      else if (msg.type === "auth") Auth.check();
    } catch {}
  };
  ws.onclose = () => setTimeout(connect, 2000);
}
connect();
