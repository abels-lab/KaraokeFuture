// Control panel: runs the pre-song countdown (Settings "intro_seconds", 0 = off) and tells every
// projector and phone where it stands — the screens only draw what the TV says, so the number
// never drifts between them. Same-laptop projector windows hear it at once (BroadcastChannel),
// other devices over the WebSocket. Needs common.js + intro.js.
// IntroRun.start(entry, details, send) -> Promise<boolean>: true = start the song now (countdown
// over or skipped by the host), false = stopped (another song came, or play/pause was pressed
// elsewhere and already took over). details() -> {mode, names} for the card, read live.
const IntroRun = (() => {
  const card = createIntro({ hint: true });
  const channel = "BroadcastChannel" in window ? new BroadcastChannel("karaoke-clock") : null;
  let run = null, lastSent = 0, lastCount = 0;

  function post(left) {
    const { entry, total, details, send } = run;
    const { mode, names } = details();
    if (left > 0) card.show({ entry, left, mode, names });
    const count = Math.ceil(left);
    // 4 messages a second, plus one the moment the number changes (phones, projectors)
    if (left > 0 && count === lastCount && performance.now() - lastSent < 250) return;
    lastSent = performance.now(); lastCount = count;
    const message = { type: "intro", uid: entry.uid, left: Math.max(0, left), total, mode, names };
    send(message);
    channel?.postMessage(message);
  }

  function finish(go) {
    if (!run) return;
    clearInterval(run.timer);
    post(0);   // screens drop their card now instead of when the messages stop
    card.hide();
    const { resolve } = run;
    run = null;
    resolve(go);
  }

  function start(entry, details, send) {
    finish(false);
    const total = Number(Settings.get("intro_seconds", 5));
    if (!(total > 0)) return Promise.resolve(true);
    return new Promise((resolve) => {
      run = { entry, total, details, send, resolve, end: performance.now() + total * 1000 };
      lastCount = 0;
      const step = () => {
        const left = (run.end - performance.now()) / 1000;
        if (left <= 0) finish(true); else post(left);
      };
      run.timer = setInterval(step, 100);
      step();
    });
  }

  card.card.onclick = () => finish(true);
  return { start, skip: () => finish(true), stop: () => finish(false), get running() { return Boolean(run); },
           get uid() { return run?.entry.uid; } };
})();
