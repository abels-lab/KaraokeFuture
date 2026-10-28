// Views of the host app, in the URL hash so Back / Forward and reloads work without ever leaving
// the page (the music keeps playing): #stage (the control panel), #library (the song library),
// and for small screens #queue and #copilot (phone tabs; on a tablet #copilot is the slide-over
// drawer, on a laptop just the stage, where the Co-Pilot is always visible). The view is
// body[data-view]; host/host.css shows and hides by it, other files listen with Router.onShow.
// Old addresses land on the right view: /library → #library, /settings → stage + the Settings
// popup (both are rewritten to /host so a reload doesn't reopen it); /tv and /host stay as they are.
// Popups (ui/popup.js) own their own history entries on top of ours: popstate events they handled
// carry event.karaokePopup and are ignored here, and a new view is pushed only after open popups
// have closed and their step back has landed (afterPopups), so the two never fight.
// Needs ui/popup.js (loaded before this file). Router = { start() -> {settings, add}, go(view, {replace}),
//   leave(), afterPopups(fn), view, onShow(fn) }
const Router = (() => {
  const VIEWS = ["stage", "queue", "copilot", "library"];
  const listeners = [];
  let view = null;
  const fromHash = () => (VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : null);
  const url = (v, path = location.pathname) => `${path}${location.search}#${v}`;

  function show(v) {
    if (v === view) return;
    view = v;
    document.body.dataset.view = v;
    document.querySelectorAll("[data-go]").forEach((b) => {
      const inTabs = Boolean(b.closest("#host-tabs"));
      const on = b.dataset.go === v || (!inTabs && b.dataset.go === "stage" && (v === "queue" || v === "copilot"));
      b.classList.toggle("is-active", on);
      if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    });
    listeners.forEach((fn) => fn(v));
  }

  // Run fn once no popup is open any more (closing them steps the history back asynchronously)
  function afterPopups(fn) {
    if (!Popup.depth) { fn(); return; }
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      removeEventListener("popstate", landed);
      setTimeout(fn, 0);
    };
    const landed = (e) => { if (e.karaokePopup && !Popup.depth) finish(); };
    addEventListener("popstate", landed);
    setTimeout(finish, 700);   // safety net: the browser swallowed the step back
    Popup.closeAll();
  }

  function go(v, { replace = false } = {}) {
    if (!VIEWS.includes(v)) return;
    afterPopups(() => {
      if (v === view) return;
      if (replace) history.replaceState({ hostView: v, pushed: Boolean(history.state?.pushed) }, "", url(v));
      else history.pushState({ hostView: v, pushed: true }, "", url(v));
      show(v);
    });
  }

  // Close a view opened on top (the tablet's Co-Pilot drawer): Back when we pushed it, so the
  // history stays tidy; otherwise (it was the first page) swap it for the stage in place
  function leave() {
    if (history.state?.pushed) history.back();
    else go("stage", { replace: true });
  }

  addEventListener("popstate", (e) => { if (!e.karaokePopup) show(fromHash() || "stage"); });
  addEventListener("hashchange", () => show(fromHash() || "stage"));   // typed into the address bar

  // The first view, from the address the page was opened with
  function start() {
    const path = location.pathname.replace(/\/+$/, "") || "/";
    const first = fromHash() || (path === "/library" ? "library" : "stage");
    const wants = { settings: path === "/settings" || location.hash === "#settings", add: location.hash === "#add" };
    const base = path === "/library" || path === "/settings" ? "/host" : location.pathname;
    history.replaceState({ hostView: first, pushed: false }, "", url(first, base));
    show(first);
    return wants;
  }

  return { start, go, leave, afterPopups, get view() { return view; }, onShow: (fn) => listeners.push(fn) };
})();
