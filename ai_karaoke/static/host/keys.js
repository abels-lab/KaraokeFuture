// Keyboard shortcuts of the host app (laptop, or a tablet with a keyboard). They work in every
// view, but never while typing (text boxes, the lyrics editor, selects) and never under a popup
// (Esc closes that one, ui/popup.js), so the Settings filter or song search can take any key.
//   Space play / pause (during the countdown: start now) · Enter / Esc skip the countdown
//   ← / → seek 5 s · P / N previous / next song · V video on / off · L lyrics mode · F fullscreen
//   A or / ＋ Add song · B library ⇄ stage · , settings · Ctrl+J the DJ Co-Pilot · Esc closes its drawer
// Moved here from tv-side.js (transport keys) and agent.js (Ctrl+J). Needs common.js, tv-now.js
// (Deck), ui/popup.js, host/router.js, host/views.js.
(() => {
  const typing = (t) => t.isContentEditable || t.tagName === "TEXTAREA" || t.tagName === "SELECT"
    || (t.tagName === "INPUT" && t.type !== "range");
  const overlayOpen = () => Popup.depth > 0 || [...document.querySelectorAll("body > .fixed.inset-0")].some((m) => m.classList.contains("flex"));
  const fullscreen = () => (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen()).catch?.(() => {});

  function openCopilot() {
    if (matchMedia("(min-width: 1025px)").matches) $("agent-input").focus();   // always visible on a laptop
    else Router.go("copilot");
  }

  const KEYS = {
    p: () => $("btn-prev").click(),
    n: () => $("btn-next").click(),
    v: () => $("btn-video").click(),
    l: () => $("btn-lyrics").click(),
    f: fullscreen,
    a: () => HostViews.openAdd(),
    "/": () => HostViews.openAdd(),
    b: () => Router.go(Router.view === "library" ? "stage" : "library"),
    ",": () => HostViews.openSettings(),
  };

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "j") { e.preventDefault(); openCopilot(); return; }
    if (e.key === "Escape" && Router.view === "copilot" && !overlayOpen()) { e.preventDefault(); Router.leave(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || typing(e.target) || overlayOpen()) return;
    if (Deck?.introRunning && (e.key === "Enter" || e.key === "Escape")) { e.preventDefault(); Deck.skipIntro(); }
    else if (e.code === "Space") { e.preventDefault(); $("btn-play").click(); }   // during the intro: start now
    else if (e.key === "ArrowLeft") { e.preventDefault(); Deck?.seekBy(-5); }
    else if (e.key === "ArrowRight") { e.preventDefault(); Deck?.seekBy(5); }
    else if (KEYS[e.key.toLowerCase()]) { e.preventDefault(); KEYS[e.key.toLowerCase()](); }
  });
})();
