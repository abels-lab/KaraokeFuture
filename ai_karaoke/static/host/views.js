// What the header, the phone tabs and the in-page links open: views (data-go="<view>", via
// host/router.js) and popups (data-act="add | settings | more | mode"). Settings and ＋ Add song
// are popups over whatever is showing, so nothing stops playing; the Library is a view of its
// own. Each shared panel (ui/settings-panel.js, ui/search-panel.js, ui/library-panel.js) is
// built ONCE, the first time it is needed, and the same element goes into every popup after
// that (each one registers a permanent Auth listener). Panels open no WebSocket: host/boot.js
// passes the page's messages on through HostViews.onMessage. The tablet's Co-Pilot drawer
// closes with its ✕, the shade beside it, Esc or Back (Router.leave).
// Needs common.js, auth.js, look.js, ui/popup.js, the ui/ panels, host/router.js, host/mode.js.
// HostViews = { openAdd(), openSettings(), openMore(), onMessage(msg), state }
const HostViews = (() => {
  let settingsPanel = null, searchPanel = null, libraryPanel = null, moreBox = null;
  let lastState = null, libraryStale = false;
  const phone = () => matchMedia("(max-width: 640px)").matches;
  const keyboard = () => !matchMedia("(pointer: coarse)").matches;   // focusing opens no phone keyboard

  const settings = () => (settingsPanel ||= createSettingsPanel());
  const search = () => (searchPanel ||= createSearchPanel({ getState: () => lastState, onNeedLogin: () => Auth.unlock() }));

  // One popup at a time from the header and tabs: a new one replaces what was open
  function popup(options, then) {
    Router.afterPopups(() => { Popup.open(options); then?.(); });
  }
  const openSettings = () => popup({ title: "⚙️ Settings", content: settings(), size: phone() ? "full" : "lg" });
  const openAdd = () => popup({ title: "＋ Add a song", content: search(), size: phone() ? "full" : "md" },
    () => keyboard() && search().focusQuery());
  const openMore = () => popup({ title: "More", content: more(), size: "sm" });

  // The phone's "More" sheet: everything the laptop shows in its header and navigation card
  function more() {
    if (moreBox) return moreBox;
    moreBox = el("div", "grid gap-2");
    const item = (label, attrs = {}) => {
      const b = el(attrs.href ? "a" : "button", "tap flex items-center gap-3 rounded-xl bg-white/10 px-4 py-3 text-left font-semibold hover:bg-white/20", label);
      Object.entries(attrs).forEach(([k, v]) => b.setAttribute(k, v));
      if (!attrs.href) b.type = "button";
      return b;
    };
    const screen = item("📽 Projector screen (this device)");
    screen.classList.add("player-only");
    screen.onclick = () => $("open-screen").click();
    const badge = hostBadge();
    badge.className = "tap rounded-xl bg-white/10 px-4 py-3 text-left font-semibold hover:bg-white/20";
    moreBox.append(item("📚 Song library", { "data-go": "library" }), item("⚙️ Settings", { "data-act": "settings" }),
      item(HostMode.isPlayer ? "🔊 Player: the music plays here" : "🎛 Controller: the laptop plays", { "data-act": "mode" }),
      screen, item("📱 Guest remote", { href: "/remote", target: "_blank" }), badge,
      item("☕ Buy me a coffee", { href: "https://github.com/sponsors/abels-lab", target: "_blank", rel: "noopener", "data-support-link": "" }));
    Look.apply();   // the support link's address and visibility come from the settings
    return moreBox;
  }

  const ACTIONS = { add: openAdd, custom: () => CustomSongModal.open({ onQueued: () => { if (libraryPanel) libraryPanel.refreshSoon(); }, onSaved: () => { if (libraryPanel) libraryPanel.refreshSoon(); } }), settings: openSettings, more: openMore, mode: () => HostMode.openSwitch() };
  document.addEventListener("click", (e) => {
    const target = e.target.closest("[data-go], [data-act]");
    if (!target) return;
    if (target.dataset.go) { e.preventDefault(); Router.go(target.dataset.go); }
    else if (ACTIONS[target.dataset.act]) { e.preventDefault(); ACTIONS[target.dataset.act](); }
  });

  // The Library view is built the first time it shows; it only refreshes while in sight
  function showLibrary() {
    if (!libraryPanel) {
      libraryPanel = createLibraryPanel();
      $("library-mount").append(libraryPanel);
    } else if (libraryStale) libraryPanel.refreshSoon();
    libraryStale = false;
  }

  Router.onShow((view) => {
    if (view === "library") showLibrary();
    if (view === "copilot" && keyboard()) setTimeout(() => $("agent-input").focus(), 50);
  });
  $("agent-close").onclick = () => Router.leave();
  $("drawer-shade").onclick = () => Router.leave();
  $("host-badge-slot").append(hostBadge());

  function onMessage(msg) {
    if (msg.type === "state") lastState = msg.data;
    if (msg.type === "settings") settingsPanel?.refresh();   // changed in another tab or by the Co-Pilot
    if (msg.type === "library") searchPanel?.refresh();      // a song became ready to sing
    if (["state", "library", "media"].includes(msg.type) && libraryPanel) {
      if (Router.view === "library") libraryPanel.refreshSoon(); else libraryStale = true;
    }
  }

  return { openAdd, openSettings, openMore, onMessage, get state() { return lastState; } };
})();
