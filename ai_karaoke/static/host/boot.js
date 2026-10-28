// Starts the host app, last of all scripts: asks who this device is, picks the Deck — the player
// (tv.js, WebSocket role "tv") on the laptop, the controller (host/controller.js, role "remote")
// anywhere else, see host/mode.js — opens the page's ONE WebSocket and hands every message to the
// Deck and to the shared panels (host/views.js). The first view comes from the address
// (host/router.js), with the Settings or Add song popup when /settings or #add asked for one.
// The WebSocket, the audio and the projector clock live as long as the page: views and popups
// only show and hide parts of it. Needs every other host script.
// Global send(msg): the WebSocket's send, for tv.js, game-panel.js and intro-run.js.
let wsSend = null;
function send(msg) { return wsSend?.(msg); }

(async () => {
  const wants = Router.start();   // the view first, so /library never flashes the stage
  if (wants.settings) HostViews.openSettings();
  else if (wants.add) HostViews.openAdd();

  const me = await Auth.load();
  const player = HostMode.decide(me);
  Deck = player ? HostPlayer : HostController;
  Deck.start();

  wsSend = connectWS(player ? "tv" : "remote", (msg) => {
    if (msg.type === "state") Deck.onState(msg.data);
    else if (msg.type === "control") Deck.onControl?.(msg.action, msg.value);   // sent to the player only
    else if (msg.type === "playback") Deck.onClock?.(msg);                       // the player's clock, to controllers
    else if (msg.type === "intro") Deck.onIntro?.(msg);
    else if (msg.type === "media") Deck.onMedia(msg.song_id);
    else if (msg.type === "library") loading.poke();   // a pipeline stage moved on
    HostViews.onMessage(msg);
  }, () => Deck.onOpen?.());
})();
