// The lyrics dialog (lyrics.js) and the host-PIN dialog (auth.js) are not ui/popup.js popups, so
// the phone's Back button would walk past them and change the view underneath. This gives such
// a dialog its own history entry while it is open: Back closes it (via its Cancel / Close
// button), and closing it any other way pops the entry again. Shared files stay untouched.
// Load after ui/popup.js and before guest/router.js. Needs nothing else.
// GuestOverlay.open(openFn) -> runs openFn(), then tracks the dialog it showed.
// popstate events handled here get event.karaokeOverlay = true (the router ignores them).
const GuestOverlay = (() => {
  let open_ = null;          // { box, observer } while one of those dialogs is up
  let expectBack = false;    // our own history.back() after the dialog closed itself

  // Those dialogs are full-screen "fixed inset-0" boxes shown by swapping hidden -> flex
  const visibleDialog = () => [...document.querySelectorAll("body > div.fixed.inset-0.flex")]
    .find((d) => !d.classList.contains("popup-backdrop"));

  function track(box) {
    history.pushState({ ...(history.state || {}), overlay: true }, "");
    const observer = new MutationObserver(() => {
      if (box.classList.contains("flex")) return;
      stop();
      if (history.state?.overlay) { expectBack = true; history.back(); }
    });
    observer.observe(box, { attributes: true, attributeFilter: ["class"] });
    open_ = { box, observer };
  }

  function stop() {
    open_?.observer.disconnect();
    open_ = null;
  }

  addEventListener("popstate", (e) => {
    if (expectBack) { expectBack = false; e.karaokeOverlay = true; return; }
    if (!open_) return;
    e.karaokeOverlay = true;
    const { box } = open_;
    stop();
    box.querySelector('[data-k="cancel"]')?.click();
  });

  function open(openFn) {
    const before = visibleDialog();
    // lyrics.js shows its dialog before it waits for the text; auth.js may only toast (no PIN set)
    openFn();
    const box = visibleDialog();
    if (box && box !== before && !open_) track(box);
  }
  return { open };
})();
