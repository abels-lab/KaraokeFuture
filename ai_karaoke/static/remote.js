// Guest remote, the Now view: the now-playing card with live transport + scrubbing (the
// transport only for your own song, or the host; scrubbing for guests only when the host's
// guest_scrubbing setting allows it), joining a battle on stage, and the lyrics button
// (read-only for guests, the editor for the host). Also feeds the phone's compact now bar,
// the Queue view (my-queue.js, with the Auto-DJ playlist below it) and the keep-awake option. When
// the singer queue is empty, Next names the Auto-DJ playlist's next song. The WebSocket lives in guest/app.js.
// Needs common.js, auth.js, lyrics.js, remote-battle.js, my-queue.js and the guest/ modules.
// renderState(state) with every "state" message, renderPlayback(msg) with every "playback" one;
// lastState is the latest state; openNowLyrics() opens the lyrics of the song on stage.
let nowEntry = null, scrubbing = false, nowPaused = true;
let lastState = { now_playing: null, queue: [], played: [] };

const mayControlNow = () => Boolean(Auth.me.admin || Auth.owns(nowEntry));
const isMine = (e) => Boolean(e && (Auth.owns(e) || (Auth.me.guest && e.partner?.id === Auth.me.guest.id)));

function renderNavSongs(prev, next) {
  $("remote-btn-prev").disabled = !prev || !Auth.me.admin;
  $("remote-prev-label").textContent = prev ? prev.title : "None";
  $("remote-btn-prev").title = prev ? `Previous: ${prev.title} (${singers(prev)})` : "No previous song";
  $("remote-btn-next").disabled = !next || !mayControlNow();
  const label = next ? next.title || next.query : "";   // an Auto-DJ pick may only have its query yet
  $("remote-next-label").textContent = next ? label : "Queue empty";
  $("remote-btn-next").title = !next ? "No upcoming song" : next.uid ? `Next: ${label} (${singers(next)})` : `Next (Auto-DJ): ${label}`;
}

function renderLyricsButton(np) {
  const b = $("np-lyrics");
  b.classList.toggle("hidden", !np);
  $("tab-lyrics").disabled = !np;
  $("tab-lyrics").classList.toggle("opacity-40", !np);
  if (!np) return;
  const fix = Auth.me.admin && needsLyrics(np);
  b.textContent = Auth.me.admin ? (fix ? "📝 AI lyrics: fix" : "📝 Edit lyrics") : "📖 Read lyrics";
  b.className = `tap rounded-lg px-2.5 py-1 text-xs font-semibold ${fix
    ? "bg-amber-900/80 text-amber-200 ring-1 ring-amber-500/50" : "bg-white/10 text-stone-200 hover:bg-white/20"}`;
}

function renderState(state = lastState) {
  lastState = state;
  const { now_playing: np, queue = [], played = [], active_playlist: autoDj = null } = state;
  nowEntry = np;
  const mayControl = mayControlNow();
  const mayScrub = Auth.me.admin || (Auth.owns(np) && Settings.get("guest_scrubbing", false));
  $("np-singer").textContent = np ? singers(np) : "Nobody yet";
  $("np-title").textContent = np ? np.title : "Add a song to get started";
  $("np-seek").disabled = !np || !mayScrub;
  $("transport").classList.toggle("hidden", Boolean(np) && !mayControl);
  $("transport-note").classList.toggle("hidden", !np || mayControl);
  renderNavSongs(played.length ? played[played.length - 1] : null, queue[0] || autoDj?.queue?.[0] || null);
  document.querySelectorAll('#transport button[data-action="seek_by"]').forEach((b) => {
    b.disabled = !mayScrub;
    b.classList.toggle("opacity-40", !mayScrub);
    b.classList.toggle("pointer-events-none", !mayScrub);
  });

  if (!np) renderPlayback({ uid: null, time: 0, duration: 0, paused: true });
  else {
    const pb = np.playback || (state.playback?.uid === np.uid ? state.playback : null);
    if (pb && Number.isFinite(pb.time)) renderPlayback(pb);
  }
  renderLyricsButton(np);
  // Once a song starts playing, only the host can tweak guide vocals / mode mid-song
  $("np-prefs").replaceChildren(...(Auth.me.admin && np && !dragging ? [songPrefs(np)] : []));
  renderNowBattle();
  renderQueue(queue, played, autoDj);
  NowBar.paint(np, { mayControl, paused: nowPaused });
  GuestDisplay.mySongUp(isMine(np) || isMine(queue[0]));
}
Auth.onChange(() => renderState());
Settings.onChange(() => renderState());   // guest_scrubbing / guide_default changed

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

function renderPlayback({ uid, time, duration, paused }) {
  if (uid && uid !== nowEntry?.uid) return;
  if (!scrubbing) { $("np-seek").max = duration || 0; $("np-seek").value = time; $("np-cur").textContent = fmt(time); }
  $("np-dur").textContent = fmt(duration);
  $("btn-toggle").dataset.action = paused ? "play" : "pause";
  setIcon($("btn-toggle"), paused ? "play" : "pause");
  if (nowPaused !== Boolean(paused)) {
    nowPaused = Boolean(paused);
    NowBar.paint(nowEntry, { mayControl: mayControlNow(), paused: nowPaused });
  }
}

// ── Transport: buttons + timeline scrubbing (REST, so the login cookie is always current) ──
const control = (action, value = 0) =>
  api("/api/player/control", { method: "POST", body: { action, value } }).catch(fail);
document.querySelectorAll("#transport [data-action]").forEach((btn) => {
  btn.onclick = () => control(btn.dataset.action, Number(btn.dataset.value || 0));
});
NowBar.onToggle((action) => control(action));
$("remote-btn-prev").onclick = () => control("previous");
$("remote-btn-next").onclick = () => control("skip");

$("np-seek").oninput = () => { scrubbing = true; $("np-cur").textContent = fmt(Number($("np-seek").value)); };
$("np-seek").onchange = () => {
  control("seek", Number($("np-seek").value));
  setTimeout(() => { scrubbing = false; }, 1200); // let the TV report the new position first
};
const openNowLyrics = () => nowEntry && GuestOverlay.open(() => openLyrics(nowEntry));   // Back closes it
$("np-lyrics").onclick = openNowLyrics;
