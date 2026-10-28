// Phone only: a slim now-playing bar stuck to the top of the Queue view (guest/layout.css shows
// it there), so you always see who's singing. A tap on it opens the Now view; the play / pause
// button appears only for whoever may control the song (the singer or the host).
// Needs common.js (el, svg, singers) and guest/router.js.
// NowBar.paint(entry | null, { mayControl, paused }); NowBar.onToggle(fn) for the play / pause tap.
const NowBar = (() => {
  const bar = $("now-bar");
  const info = el("button", "flex min-w-0 flex-1 items-center gap-2 text-left");
  info.type = "button";
  info.title = "Show what's playing";
  const dot = el("span", "h-2.5 w-2.5 shrink-0 rounded-full bg-stone-500");
  const text = el("span", "min-w-0 flex-1");
  const title = el("span", "block truncate text-sm font-semibold", "Nobody singing yet");
  const who = el("span", "block truncate text-xs text-stone-400", "");
  text.append(title, who);
  info.append(dot, text);
  const toggle = el("button", "tap tap-square btn-gold flex h-10 w-10 shrink-0 items-center justify-center rounded-full");
  toggle.type = "button";
  toggle.setAttribute("aria-label", "Play / pause");
  bar.append(info, toggle);

  let onToggle = () => {};
  info.onclick = () => GuestRouter.show("now");
  toggle.onclick = () => onToggle(toggle.dataset.action);

  function paint(np, { mayControl = false, paused = true } = {}) {
    title.textContent = np ? np.title : "Nobody singing yet";
    who.textContent = np ? `🎤 ${singers(np)}` : "Tap ＋ to add a song";
    dot.className = `h-2.5 w-2.5 shrink-0 rounded-full ${np && !paused ? "animate-pulse bg-emerald-400" : "bg-stone-500"}`;
    toggle.classList.toggle("hidden", !np || !mayControl);
    toggle.dataset.action = paused ? "play" : "pause";
    toggle.innerHTML = svg(paused ? "play" : "pause");
  }
  paint(null);

  return { paint, onToggle: (fn) => { onToggle = fn; } };
})();
