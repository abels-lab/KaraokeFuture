// Control panel side of the singing game: mode picker, mic frames -> Game engine, live state to
// projector screens (BroadcastChannel + WebSocket, 25 Hz) and the results when a song ends.
// Load after common, stage, mics, game, fx, notes, results, game-view; before tv.js.
const GamePanel = (() => {
  let mode = store("gameMode") || "off", roast = store("gameRoast") === "1";
  let entry = null, view = null, send = () => {}, active = mode; // active: the mode of the song playing
  // A singer's choice on their phone (entry.mode) beats the host's picker for their song.
  // "score" is the engine's "hard"; "battle" (two mics head to head) scores like it for now.
  const ENTRY_MODE = { party: "party", score: "hard", battle: "hard" };
  const modeFor = (e) => ENTRY_MODE[e?.mode] || mode;
  const channel = "BroadcastChannel" in window ? new BroadcastChannel("karaoke-game") : null;
  const ensureView = () => (view ||= createGameView($("monitor"), stage)); // stage comes from tv.js

  // ── Controls next to the microphones button ────────────────────────────────
  const picker = el("select", "flex-1 rounded-lg bg-white/10 px-2 py-2 text-sm font-semibold text-stone-200");
  picker.title = "Singing game";
  for (const [value, label] of [["off", "🎮 Game off"], ["party", "✨ Party mode"], ["hard", "🏆 Score (hard) mode"]]) {
    picker.append(Object.assign(el("option", "bg-stone-900", label), { value }));
  }
  picker.value = mode;
  const roastBox = Object.assign(el("input", "accent-amber-400"), { type: "checkbox", checked: roast });
  const roastLabel = el("label", "flex items-center gap-1.5 text-xs text-stone-400");
  roastLabel.title = "Hard mode verdicts with metaphors like “a dying duck” — not everyone loves them";
  roastLabel.append(roastBox, document.createTextNode("Roast verdicts"));
  $("game-controls").after(roastLabel);
  $("game-controls").append(picker);
  const syncControls = () => { roastLabel.classList.toggle("hidden", mode !== "hard"); };
  picker.onchange = () => { mode = picker.value; store("gameMode", mode); syncControls(); if (entry) load(entry); };
  roastBox.onchange = () => { roast = roastBox.checked; store("gameRoast", roast ? "1" : "0"); };
  syncControls();

  // Singer 1's default name becomes whoever queued the song
  function names() {
    return Mics.active.map((mic, slot) => {
      const name = Mics.config[mic].name;
      return slot === 0 && entry && (!name || name === MIC_DEFAULTS[mic].name) ? entry.singer : name;
    });
  }

  async function load(e) {
    entry = e;
    active = modeFor(e);
    Game.clear();
    const melody = await ensureView().load(e);
    if (active === "off" || entry !== e) return;
    if (!Mics.running) { toast("Game mode is on — start the microphones to play", false); return; }
    if (!melody) { toast("This song's melody isn't ready yet — no scoring this time", false); return; }
    Game.load(melody, names());
  }

  // A frame answers what the singer heard ~latency ago; the YIN window is centred 32 ms back
  Mics.onFrame((f) => {
    const slot = Mics.active.indexOf(f.player);
    if (!Game.loaded || slot < 0 || inst.paused) return;
    Game.frame(slot, f, inst.currentTime - Mics.config[f.player].latency / 1000 - 0.032);
  });

  const live = () => ({ mode: Game.loaded ? active : "off", roast, players: Game.loaded ? Game.live() : [] });

  const render = (t) => ensureView().render(t, live()); // the monitor (animation frames)

  // Projectors get the live state from a timer, not the animation loop: browsers stop animation
  // frames in a minimized window, but a tab playing audio keeps full-speed timers
  setInterval(() => {
    const game = live();
    if (game.mode === "off" || !entry) return;
    const message = { type: "game", uid: entry.uid, ...game };
    send(message);
    channel?.postMessage(message);
  }, 40);

  // Song ended: results everywhere; returns how long to wait before the next song
  function finish() {
    if (!Game.loaded) return 0;
    const message = { type: "game_result", uid: entry?.uid, mode: active, roast, results: Game.results() };
    send(message);
    channel?.postMessage(message);
    ensureView().showResults(message);
    Game.clear();
    return Settings.get("game_results_seconds", 12) * 1000;
  }

  function clear() { Game.clear(); view?.clear(); entry = null; }

  // mode: what the playing song uses ("off" | "party" | "hard"), after the singer's own choice
  return { init(fn) { send = fn; }, load, render, finish, clear, get mode() { return active; } };
})();
