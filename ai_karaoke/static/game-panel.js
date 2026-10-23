// Control panel side of the singing game: mode picker, mic frames -> Game engine, live state to
// projector screens (BroadcastChannel + WebSocket, 25 Hz) and the results when a song ends.
// Battle: both mic slots score at once (slot 0 = the owner, slot 1 = the partner who joined on
// their phone, else "Player 2"). Without a partner, Player 2 joins by singing into mic 2
// (p2-detect.js) — in Score mode too, when a second mic is set up.
// Load after common, stage, mics, game, fx, notes, battle-fx, results, game-view, p2-detect; before tv.js.
const GamePanel = (() => {
  let mode = store("gameMode") || "off", roast = store("gameRoast") === "1";
  let entry = null, view = null, send = () => {}, active = mode; // active: the mode of the song playing
  // A singer's choice on their phone (entry.mode) beats the host's picker for their song
  const ENTRY_MODE = { party: "party", score: "hard", battle: "battle" };
  const modeFor = (e) => ENTRY_MODE[e?.mode] || mode;
  const scored = () => active === "hard" || active === "battle";
  const channel = "BroadcastChannel" in window ? new BroadcastChannel("karaoke-game") : null;
  const ensureView = () => (view ||= createGameView($("monitor"), stage)); // stage comes from tv.js
  const detect = createP2Detect();
  let waitingP2 = false;   // slot 1 exists but hasn't joined yet (no partner, nobody sang)

  // ── Controls next to the microphones button ────────────────────────────────
  const picker = el("select", "flex-1 rounded-lg bg-white/10 px-2 py-2 text-sm font-semibold text-stone-200");
  picker.title = "Singing game";
  for (const [value, label] of [["off", "🎮 Game off"], ["party", "✨ Party mode"], ["hard", "🏆 Score (hard) mode"],
    ["battle", "⚔️ Battle / Duet"]]) {
    picker.append(Object.assign(el("option", "bg-stone-900", label), { value }));
  }
  picker.value = mode;
  const roastBox = Object.assign(el("input", "accent-amber-400"), { type: "checkbox", checked: roast });
  const roastLabel = el("label", "flex items-center gap-1.5 text-xs text-stone-400");
  roastLabel.title = "Hard mode verdicts with metaphors like “a dying duck” — not everyone loves them";
  roastLabel.append(roastBox, document.createTextNode("Roast verdicts"));
  $("game-controls").after(roastLabel);
  $("game-controls").append(picker);
  const syncControls = () => { roastLabel.classList.toggle("hidden", mode !== "hard" && mode !== "battle"); };
  picker.onchange = () => { mode = picker.value; store("gameMode", mode); syncControls(); if (entry) load(entry); };
  roastBox.onchange = () => { roast = roastBox.checked; store("gameRoast", roast ? "1" : "0"); };
  syncControls();

  // Slot 0's default name becomes whoever queued the song; slot 1's the battle partner
  function names() {
    return Mics.active.map((mic, slot) => {
      const name = Mics.config[mic].name, isDefault = !name || name === MIC_DEFAULTS[mic].name;
      if (slot === 0) return entry && isDefault ? entry.singer : name;
      return entry?.partner?.name || (isDefault ? "Player 2" : name);
    });
  }

  async function load(e) {
    entry = e;
    active = modeFor(e);
    Game.clear();
    detect.reset();
    waitingP2 = false;
    const melody = await ensureView().load(e);
    if (active === "off" || entry !== e) return;
    if (!Mics.running) { toast("Game mode is on — start the microphones to play", false); return; }
    if (!melody) { toast("This song's melody isn't ready yet — no scoring this time", false); return; }
    if (active === "battle" && Mics.active.length < 2) toast("Battle needs a second microphone — set one up under 🎤 Microphones", false);
    // Score / battle: Player 2 plays from the start only when a partner joined on their phone
    const on = Mics.active.map((_, slot) => slot === 0 || !scored() || Boolean(e.partner));
    waitingP2 = on.length > 1 && !on[1] && Settings.get("p2_detect", true);
    Game.load(melody, names(), on);
  }

  function joined(name) {
    waitingP2 = false;
    Game.activate(1, name);
    toast(`🎤 ${name} joined!`);
  }

  // The playing song's partner changed (joined / left on a phone, during the intro or before)
  function partnerChanged(e) {
    entry = e;
    const p2 = Game.loaded && Game.players[1];
    if (!p2) return;
    if (e.partner && !p2.on && scored()) joined(e.partner.name);
    else p2.name = names()[1];   // renamed, or back to "Player 2" after the partner left
  }

  // A frame answers what the singer heard ~latency ago; the YIN window is centred 32 ms back
  Mics.onFrame((f) => {
    const slot = Mics.active.indexOf(f.player);
    if (!Game.loaded || slot < 0 || inst.paused) return;
    if (waitingP2 && detect.feed(slot, f) && Game.players[1]) joined(Game.players[1].name);
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

  function clear() { Game.clear(); view?.clear(); entry = null; waitingP2 = false; }

  // mode: what the playing song uses ("off" | "party" | "hard" | "battle"), after the singer's
  // own choice; intro(): what the pre-song card shows (intro-run.js)
  return { init(fn) { send = fn; }, load, render, finish, clear, partnerChanged, get mode() { return active; },
           intro: () => ({ mode: active, names: names() }) };
})();
