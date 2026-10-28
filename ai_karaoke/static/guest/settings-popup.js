// The guest remote's ⚙ popup. Everyone: who you are (log in / log out), host mode (PIN unlock),
// your defaults for new songs (guest/prefs.js) and this device's display options
// (guest/display.js). The host (PIN or the laptop) also gets 📚 Library (the shared library
// panel in a full popup on top) and every party setting (the shared settings panel).
// The content and both host panels are made once and reused for every open; the host panels
// only when a host first opens this, so a guest's phone never loads them.
// Needs common.js, auth.js, ui/popup.js, ui/settings-panel.js, ui/library-panel.js,
// guest/overlay-back.js, guest/prefs.js, guest/display.js, remote-login.js.
// GuestSettings.open(); GuestSettings.onSettings() on WS "settings"; .onLibrary() on "state" / "library" / "media".
const GuestSettings = (() => {
  const root = el("div", "space-y-4");
  const section = (title) => {
    const box = el("section", "panel space-y-3 p-4");
    box.append(el("h3", "text-xs font-semibold uppercase tracking-[0.2em] text-gold", title));
    return box;
  };
  const button = (label, cls, onclick) => Object.assign(el("button", `tap rounded-xl px-4 py-2 text-sm font-semibold ${cls}`, label),
    { type: "button", onclick });

  const you = section("You");
  const youBody = el("div", "space-y-3");
  you.append(youBody);
  const defaults = section("Your new songs");
  defaults.append(GuestPrefs.editor());
  const device = section("This device");
  device.append(GuestDisplay.editor());
  const host = el("div", "space-y-4");
  root.append(you, defaults, device, host);

  let settingsPanel = null, libraryPanel = null, popup = null;

  function openLibrary() {
    libraryPanel ||= createLibraryPanel();
    libraryPanel.refresh();
    Popup.open({ title: "📚 Library", content: libraryPanel, size: "full" });
  }

  function paintYou(me) {
    const name = me.guest?.name;
    const who = el("p", "text-sm text-stone-300");
    who.innerHTML = name ? "Singing as <b class='text-gold'></b>" : me.laptop ? "This is the laptop running the karaoke." : "Not logged in yet.";
    if (name) who.querySelector("b").textContent = name;
    const row = el("div", "flex flex-wrap gap-2");
    if (name || (me.admin && !me.laptop)) {
      row.append(button("Log out", "bg-white/10 hover:bg-white/20", async () => {
        if (await GuestLogin.logout()) popup?.close();
      }));
    }
    if (!name && !me.laptop) row.append(button("Log in", "btn-gold", () => { popup?.close(); setTimeout(GuestLogin.focus, 50); }));
    const pin = me.admin
      ? el("p", "text-sm text-stone-300", me.laptop ? "👑 You're the host: this laptop runs the karaoke." : "👑 Host mode is on for this device.")
      : button("🔑 Unlock host mode", "bg-white/10 hover:bg-white/20", () => GuestOverlay.open(() => Auth.unlock()));
    youBody.replaceChildren(who, row, pin);
  }

  function paintHost(me) {
    if (!me.admin) { host.replaceChildren(); return; }
    settingsPanel ||= createSettingsPanel();
    const lib = section("Host tools");
    lib.append(el("p", "text-sm text-stone-400", "Every cached song: queue for anyone, fix lyrics, re-sync, rebuild or delete."),
      button("📚 Open the library", "btn-gold", openLibrary));
    const party = el("div", "space-y-3");
    party.append(el("h3", "px-1 text-xs font-semibold uppercase tracking-[0.2em] text-gold", "Party settings"), settingsPanel);
    host.replaceChildren(lib, party);
  }

  function paint(me) {
    paintYou(me);
    if (popup) paintHost(me);   // host panels are made on first open, not on page load
  }
  Auth.onChange(paint);
  paint(Auth.me);

  function open() {
    paintHost(Auth.me);
    popup = Popup.open({ title: "⚙ Settings", content: root, size: Auth.me.admin ? "lg" : "md",
      onClose: () => { popup = null; } });
  }

  return {
    open,
    onSettings: () => settingsPanel?.refresh(),
    onLibrary: () => libraryPanel?.refreshSoon(),
  };
})();
