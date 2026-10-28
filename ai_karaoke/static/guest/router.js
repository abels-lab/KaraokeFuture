// The guest remote's two views, Now and Queue, and what the phone's Back button does with them.
// On a phone one view shows at a time (body.view-now / body.view-queue, see guest/layout.css);
// on a tablet or laptop both sit side by side and the view only matters for Back.
// History, bottom first: a guard entry ({view: "base"}), then {view: "now"}, then {view: "queue"}
// when Queue is open, then one entry per open popup (ui/popup.js) or dialog (guest/overlay-back.js).
// So Back closes popups first, then goes from Queue to Now, then lands on the guard: there we
// only say "Press Back again to leave", and the next tap in the app sets the guard up again.
// Load after ui/popup.js and guest/overlay-back.js. Needs common.js (toast).
// GuestRouter.show("now" | "queue"), GuestRouter.view, GuestRouter.onChange(fn(view))
const GuestRouter = (() => {
  const VIEWS = ["now", "queue"];
  const listeners = [];
  let view = "now";
  let armed = false;     // a "now" entry sits above the guard
  let tabBack = false;   // our own history.back() for the Now tab: no "leave" hint

  function paint(v) {
    const changed = v !== view;
    view = v;
    document.body.classList.toggle("view-now", v === "now");
    document.body.classList.toggle("view-queue", v === "queue");
    document.querySelectorAll("[data-tab]").forEach((b) => {
      if (b.dataset.tab === v) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
    if (changed && matchMedia("(max-width: 640px)").matches) scrollTo({ top: 0 });
    listeners.forEach((fn) => fn(v));
  }

  // A reload keeps the view it was on; a fresh visit makes its entry the guard
  const start = history.state || {};
  if (VIEWS.includes(start.view)) {
    armed = true;
    if (start.overlay) history.replaceState({ view: start.view }, "");
    paint(start.view);
  } else {
    history.replaceState({ view: "base" }, "");
    paint("now");
  }

  // Browsers skip history entries a page adds without a tap, so the guard is armed on one
  function arm() {
    if (armed || Popup.depth || history.state?.view !== "base") return;
    armed = true;
    history.pushState({ view: "now" }, "");
  }
  addEventListener("pointerdown", arm, true);
  addEventListener("keydown", arm, true);

  function show(v) {
    if (!VIEWS.includes(v)) return;
    if (Popup.depth) {   // close the popups first; route once their history steps are undone
      Popup.closeAll();
      addEventListener("popstate", () => setTimeout(() => show(v)), { once: true });
      return;
    }
    if (v === view) { scrollTo({ top: 0, behavior: "smooth" }); return; }
    if (v === "queue") {
      history.pushState({ view: "queue" }, "");
      paint("queue");
    } else if (history.state?.view === "queue") {
      tabBack = true;
      history.back();    // the popstate below paints Now
    } else {
      paint("now");
    }
  }

  addEventListener("popstate", (e) => {
    if (e.karaokePopup || e.karaokeOverlay) return;   // a popup or dialog closed: not a route
    const v = e.state?.view;
    const quiet = tabBack;
    tabBack = false;
    if (VIEWS.includes(v)) { armed = true; paint(v); return; }
    armed = false;       // on the guard: one more Back leaves the page
    paint("now");
    if (!quiet) toast("Press Back again to leave the karaoke");
  });

  return { show, get view() { return view; }, onChange: (fn) => listeners.push(fn) };
})();
