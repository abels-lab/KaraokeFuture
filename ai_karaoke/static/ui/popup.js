// Popups for the single-page apps: settings, song search and friends open on top of the page
// instead of on a page of their own. On a phone a popup is a bottom sheet, on a tablet or laptop
// a centred dialog (the look lives in ui/responsive.css). Esc, a tap on the dark backdrop, the ✕
// and the browser / Android Back button close the top one; a popup may open another on top.
// Back works because every open popup owns one history entry (same URL, state {popup: depth}):
// Back pops the entry and we close the popup, our own close() pops it for us.
// Needs common.js (el) and ui/responsive.css.
// Popup.open({ title, content, size: "sm"|"md"|"lg"|"full", onClose }) -> { close(), body, root }
// Popup.closeAll(), Popup.depth. popstate events this module handled get event.karaokePopup = true.
const Popup = (() => {
  const stack = [];          // open popups, bottom first
  let pushed = 0;            // history entries our popups own right now
  let goingBack = false;     // our own history.go(-n) is on its way; its popstate is ours
  const FOCUSABLE = "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])";

  // A popup left in the history by a reload has nothing to close: start clean
  if (history.state && history.state.popup) history.replaceState(null, "");

  // Make the history entries match the open popups (one entry per popup)
  function syncHistory() {
    if (goingBack) return;   // wait until our last step back has landed
    while (pushed < stack.length) history.pushState({ popup: ++pushed }, "");
    if (pushed > stack.length) {
      goingBack = true;
      history.go(stack.length - pushed);
    }
  }

  addEventListener("popstate", (e) => {
    const depth = (e.state && e.state.popup) || 0;
    if (goingBack) {         // the step back we asked for
      goingBack = false;
      pushed = depth;
      e.karaokePopup = true;
      syncHistory();         // popups opened meanwhile get their entries now
      return;
    }
    if (!stack.length && !pushed && !depth) return;   // not ours: a page route changed
    e.karaokePopup = true;
    pushed = depth;
    while (stack.length > depth) remove(stack[stack.length - 1]);
    syncHistory();           // Forward onto an entry whose popup is gone: step back again
  });

  // Esc closes the top popup, unless another overlay (lyrics, host PIN) covers it
  addEventListener("keydown", (e) => {
    const top = stack[stack.length - 1];
    if (!top) return;
    if (e.key === "Escape" && covers(top)) { e.preventDefault(); close(top); }
    if (e.key === "Tab") keepFocusInside(top, e);
  });
  const covers = (p) => p.backdrop.contains(document.elementFromPoint(innerWidth / 2, innerHeight / 2) || p.backdrop);

  function keepFocusInside(p, e) {
    const items = [...p.dialog.querySelectorAll(FOCUSABLE)].filter((x) => !x.disabled && x.offsetParent);
    if (!items.length || !p.dialog.contains(document.activeElement)) return;
    const [first, last] = [items[0], items[items.length - 1]];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  // Page behind stays put while a popup is open
  const lockScroll = () => document.documentElement.classList.toggle("popup-lock", stack.length > 0);

  function build({ title, size }) {
    const backdrop = el("div", "popup-backdrop");
    backdrop.style.zIndex = `calc(var(--popup-z, 30) + ${stack.length})`;
    const dialog = el("div", `popup popup-${["sm", "md", "lg", "full"].includes(size) ? size : "md"}`);
    Object.assign(dialog, { tabIndex: -1 });
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    const head = el("div", "popup-head");
    const heading = el("h2", "popup-title font-display text-xl font-bold text-gold", title || "");
    heading.id = `popup-title-${Date.now()}-${stack.length}`;
    dialog.setAttribute("aria-labelledby", heading.id);
    const x = el("button", "popup-x rounded-lg bg-white/10 hover:bg-white/20", "✕");
    Object.assign(x, { type: "button", title: "Close" });
    x.setAttribute("aria-label", "Close");
    head.append(heading, x);
    const body = el("div", "popup-body");
    dialog.append(el("div", "popup-handle"), head, body);
    backdrop.append(dialog);
    return { backdrop, dialog, body, x };
  }

  function open({ title = "", content = null, size = "md", onClose = null } = {}) {
    const parts = build({ title, size });
    const p = { ...parts, onClose, returnFocus: document.activeElement, closed: false };
    if (content) parts.body.append(content);
    parts.x.onclick = () => close(p);
    // Backdrop: close only when the press both started and ended outside the dialog (no drag-out)
    let downOutside = false;
    parts.backdrop.addEventListener("pointerdown", (e) => { downOutside = e.target === parts.backdrop; });
    parts.backdrop.addEventListener("click", (e) => { if (downOutside && e.target === parts.backdrop) close(p); });
    stack.push(p);
    document.body.append(parts.backdrop);
    lockScroll();
    requestAnimationFrame(() => parts.backdrop.classList.add("popup-open"));
    const first = [...parts.body.querySelectorAll(FOCUSABLE)].find((x) => !x.disabled && x.offsetParent);
    (first && !matchMedia("(pointer: coarse)").matches ? first : parts.dialog).focus({ preventScroll: true });
    syncHistory();
    return { close: () => close(p), body: parts.body, root: parts.dialog };
  }

  // Take a popup (and any opened from it) off the screen, without touching the history
  function remove(p) {
    const at = stack.indexOf(p);
    if (at < 0) return;
    for (const q of stack.splice(at).reverse()) {
      q.closed = true;
      q.backdrop.remove();
      if (q.returnFocus && q.returnFocus.isConnected) q.returnFocus.focus({ preventScroll: true });
      try { q.onClose?.(); } catch (err) { console.error(err); }
    }
    lockScroll();
  }

  function close(p) {
    if (p.closed) return;
    remove(p);
    syncHistory();
  }

  const closeAll = () => { if (stack.length) close(stack[0]); };
  return { open, closeAll, get depth() { return stack.length; } };
})();
