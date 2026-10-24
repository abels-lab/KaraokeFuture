// Guest phone: tabs, the now-playing card with live transport + scrubbing (the transport only
// for your own song, or the host), and joining a battle on stage. Search, ready songs and the
// "Good luck" pick: remote-search.js, remote-library.js, remote-lucky.js; the queue: my-queue.js.
let nowEntry = null, scrubbing = false;
let activeTab = "songs"; // "songs" | "queue"

// ── Tab switcher: Songs vs Queue ──────────────────────────────────────────
function switchTab(tab) {
  activeTab = tab;
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
let lastState = { now_playing: null, queue: [] };
function renderState(state = lastState) {
  lastState = state;
  const { now_playing: np, queue } = state;
  const mayControl = Auth.me.admin || Auth.owns(np);
  const mayScrub = Auth.me.admin || (Auth.owns(np) && Settings.get("guest_scrubbing", false));
  nowEntry = np;
  $("np-singer").textContent = np ? singers(np) : "Nobody yet";
  $("np-title").textContent = np ? np.title : "Add a song to get started";
  $("np-seek").disabled = !np || !mayScrub;
  $("transport").classList.toggle("hidden", Boolean(np) && !mayControl);
  $("transport-note").classList.toggle("hidden", !np || mayControl);

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
  renderQueue(queue);
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
Battle.onChange(() => renderNowBattle(false));
Battle.onChange(renderNowBattle);

function renderPlayback({ uid, time, duration, paused }) {
  if (uid && uid !== nowEntry?.uid) return;
  if (!scrubbing) { $("np-seek").max = duration || 0; $("np-seek").value = time; $("np-cur").textContent = fmt(time); }
  $("np-dur").textContent = fmt(duration);
  $("btn-toggle").dataset.action = paused ? "play" : "pause";
  setIcon($("btn-toggle"), paused ? "play" : "pause");
}

connectWS("remote", (msg) => {
  if (msg.type === "state") renderState(msg.data);
  else if (msg.type === "playback") renderPlayback(msg);
  else if (msg.type === "intro") Battle.onIntro(msg);
});

// ── Transport: buttons + timeline scrubbing (REST, so the login cookie is always current) ──
const control = (action, value = 0) =>
  api("/api/player/control", { method: "POST", body: { action, value } }).catch(fail);
document.querySelectorAll("[data-action]").forEach((btn) => {
  btn.onclick = () => control(btn.dataset.action, Number(btn.dataset.value || 0));
});
$("np-seek").oninput = () => { scrubbing = true; $("np-cur").textContent = fmt(Number($("np-seek").value)); };
$("np-seek").onchange = () => {
  control("seek", Number($("np-seek").value));
  setTimeout(() => { scrubbing = false; }, 1200); // let the TV report the new position first
};
$("np-lyrics").onclick = () => nowEntry && openLyrics(nowEntry);
loadLibrary();
