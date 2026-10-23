// One game surface — the projector screen or the control panel's monitor: party effects or
// hard-mode lanes over the stage (battle: the same lanes with both singers and their own
// sparks), plus the results card. Needs fx.js, notes.js, battle-fx.js, results.js.
// game = {mode: "off" | "party" | "hard" | "battle", roast, players: [{name, vibe, pitch, hit, streak, points}]}
function createGameView(container, stage) {
  const layer = el("div", "pointer-events-none absolute inset-0 z-10");
  const overlay = el("div", "absolute inset-0 z-20 hidden items-center justify-center bg-black/75 p-6");
  container.append(layer, overlay);
  const fx = createFx(layer), notes = createNotes(layer), sparks = createBattleFx(layer);
  let melody = null, partyOn = false, hideTimer = null;

  async function load(entry) {
    melody = null;
    notes.clear();
    if (entry?.media?.melody) {
      try { melody = await (await fetch(`${entry.media.melody}?v=${Date.now()}`)).json(); } catch { melody = null; }
    }
    notes.load(melody);
    return melody;
  }

  function render(t, game) {
    const mode = game?.players?.length ? game.mode : "off";
    const lanes = mode === "hard" || mode === "battle";
    notes.show(lanes);
    sparks.show(mode === "battle");
    if (mode === "party") {
      // Duets: the better singer of the moment lights the stage
      const vibe = Math.max(...game.players.map((p) => p.vibe));
      const energy = melody ? melody.energy[Math.round(t / melody.hop)] || 0 : 0.5;
      fx.render(stage.activeWord, vibe, energy);
      partyOn = true;
    } else if (partyOn) {
      fx.clear(stage.main);
      partyOn = false;
    }
    if (lanes) {
      const heads = notes.render(t, game.players);
      if (mode === "battle") sparks.render(heads);
    }
  }

  function showResults(message, ms = Settings.get("game_results_seconds", 12) * 1000) {
    overlay.replaceChildren(resultsCard(message));
    overlay.classList.replace("hidden", "flex");
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => overlay.classList.replace("flex", "hidden"), ms);
  }

  function clear() {
    melody = null;
    notes.clear();
    sparks.clear();
    fx.clear(stage.main);
    partyOn = false;
  }

  return { load, render, showResults, clear, get melody() { return melody; } };
}
