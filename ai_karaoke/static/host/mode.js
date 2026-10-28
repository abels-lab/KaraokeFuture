// Player or controller: only ONE device should play the audio and drive the projector screens.
// Decided once when the page starts (host/boot.js), from who this device is (Auth.me):
// - the laptop running the karaoke (Auth.me.laptop) is the PLAYER, as the old /tv page was;
// - any other host device (a phone or tablet unlocked with the host PIN) is a CONTROLLER:
//   no audio, no "tv" WebSocket role, it steers the laptop over REST (host/controller.js);
// - a viewer without host rights is a controller too, read-only (the server refuses the rest).
// The host can override it per device with the "Play audio on this device" switch (a party
// without the laptop's browser open, or a laptop that should only remote-control). The choice
// is remembered in localStorage "host_play_here" ("1" / "0"; unset = the rule above). Changing
// it reloads the page once, because the WebSocket role is fixed per connection; nothing plays
// on this device at that moment that could be lost, except when turning the player off.
// Needs common.js, auth.js, ui/popup.js. HostMode = { decide(me) -> isPlayer, isPlayer, openSwitch() }
const HostMode = (() => {
  const KEY = "host_play_here";
  let player = false;

  function decide(me) {
    const pref = store(KEY);
    player = Boolean(me.admin) && (pref === "1" || (pref !== "0" && Boolean(me.laptop)));
    document.body.classList.toggle("host-player", player);
    document.body.classList.toggle("host-controller", !player);
    document.querySelectorAll("[data-mode-chip]").forEach((chip) => {
      chip.textContent = player ? "🔊 Player" : "🎛 Controller";
      chip.title = player ? "This device plays the audio and drives the projector — click to change"
        : "This device remote-controls the player — click to play the audio here instead";
    });
    return player;
  }

  function openSwitch() {
    const box = el("div", "space-y-4 text-sm text-stone-300");
    const here = el("p", "", player
      ? "🔊 This device is the player: it plays the songs' audio and is the clock every projector screen follows."
      : "🎛 This device is a remote control: the laptop's control panel plays the audio, this one only steers it.");
    const advice = el("p", "text-xs text-stone-400", player
      ? "Turn it off to use this device only as a remote control (no sound here)."
      : "Play here only when the laptop's control panel isn't open — otherwise both devices would play the music.");
    const btn = el("button", "btn-gold tap w-full rounded-xl px-4 py-3 text-base",
      player ? "🎛 Stop playing here (remote control only)" : "🔊 Play audio on this device");
    btn.type = "button";
    btn.onclick = () => {
      if (!player && !Auth.me.admin) { toast("Enter the host PIN first", false); Auth.unlock(); return; }
      store(KEY, player ? "0" : "1");
      location.reload();   // reconnect with the other WebSocket role
    };
    box.append(here, advice, btn);
    if (store(KEY) !== null) {
      const reset = el("button", "w-full text-xs font-semibold text-amber-400 hover:underline", "Back to automatic (the laptop plays)");
      reset.type = "button";
      reset.onclick = () => { try { localStorage.removeItem(KEY); } catch {} location.reload(); };
      box.append(reset);
    }
    Popup.open({ title: "Where does the music play?", content: box, size: "sm" });
  }

  return { decide, get isPlayer() { return player; }, openSwitch };
})();
