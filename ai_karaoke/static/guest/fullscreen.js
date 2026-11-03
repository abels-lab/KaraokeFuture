// Fullscreen on/off (the header's ⛶ button, tablet and laptop). In a normal window the browser's
// tabs and the taskbar take ~150px, which is what makes the remote scroll on a laptop; fullscreen
// gives that room back. It uses the page's Fullscreen API, so Esc or the button leave it again,
// unlike Chrome's F11 fullscreen, which only F11 can end and a page can't switch off.
(() => {
  const btn = $("btn-fullscreen");
  if (!btn) return;
  if (!document.fullscreenEnabled) { btn.remove(); return; }   // iPhone Safari: no page fullscreen
  const icon = (d) => `<svg viewBox="0 0 24 24" class="h-5 w-5 fill-none stroke-current" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>`;
  const ENTER = icon("M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5");
  const LEAVE = icon("M9 4v5H4M15 4v5h5M20 15h-5v5M4 15h5v5");

  function paint() {
    const on = Boolean(document.fullscreenElement);
    btn.innerHTML = on ? LEAVE : ENTER;
    btn.setAttribute("aria-pressed", String(on));
    btn.title = on ? "Leave fullscreen (Esc)" : "Fullscreen";
  }
  btn.addEventListener("click", () => {
    const go = document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
    go.catch(() => toast("Fullscreen isn't allowed here", false));
  });
  document.addEventListener("fullscreenchange", paint);
  paint();
})();
