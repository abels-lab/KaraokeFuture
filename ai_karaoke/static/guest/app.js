// Guest remote wiring: the song-search popup (＋ Find a song), the ⚙ popup, the ✨ DJ Co-Pilot chat, the host's 📻
// playlists popup (ui/playlists-panel.js), the phone's tab bar, the laptop's third column of
// ready songs, and the page's one WebSocket, which hands every
// message to the part that needs it (the shared panels never open their own).
// Each panel is made once and the same element goes into every popup that shows it.
// Load last. Needs everything remote.html loads before it.
const GuestApp = (() => {
  const phone = matchMedia("(max-width: 640px)");
  const laptop = matchMedia("(min-width: 1025px)");
  const needLogin = () => { Popup.closeAll(); setTimeout(GuestLogin.focus, 50); };
  // Songs added from this device get the guest's own defaults (guide volume, mode) right away
  const panelOptions = { onAdded: (entry) => GuestPrefs.applyTo(entry), getState: () => lastState, onNeedLogin: needLogin };
  const search = createSearchPanel(panelOptions);
  let side = null;   // laptop: a second search panel beside the queue, made the first time it fits

  function openSearch() {
    if (Popup.depth) return;
    Popup.open({ title: "＋ Find a song", content: search, size: phone.matches ? "full" : "lg" });
    if (!matchMedia("(pointer: coarse)").matches) search.focusQuery();   // phones: no surprise keyboard
  }

  // The host's "Singer name" box exists in both search panels: keep them showing the same name
  function linkSingerBoxes(...panels) {
    const boxes = panels.map((p) => p.querySelector('[data-k="singer"]')).filter(Boolean);
    boxes.forEach((b) => b.addEventListener("input", () => boxes.forEach((o) => { if (o !== b) o.value = b.value; })));
  }

  function makeSide() {
    if (side || !laptop.matches) return;
    side = createSearchPanel(panelOptions);
    $("guest-side").append(el("h2", "mb-3 text-sm font-semibold uppercase tracking-wider text-gold", "⚡ Ready to sing"), side);
    linkSingerBoxes(search, side);
  }
  laptop.addEventListener("change", makeSide);
  makeSide();

  const actions = {
    search: openSearch,
    settings: () => { if (!Popup.depth) GuestSettings.open(); },
    lyrics: () => openNowLyrics(),
    copilot: () => GuestCopilot.open(),   // the ✨ button (guest/copilot.js)
    playlists: () => { if (!Popup.depth && Auth.me.admin) Playlists.open(); },   // host only (header 📻)
  };
  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-open]");
    if (opener && actions[opener.dataset.open]) { actions[opener.dataset.open](); return; }
    const tab = e.target.closest("[data-tab]");
    if (tab) GuestRouter.show(tab.dataset.tab);
  });

  // A song finished processing: the ready lists gain it
  let readyKey = "";
  function watchReady(state) {
    const key = [state.now_playing, ...(state.queue || [])].filter((e) => e?.status === "ready").map((e) => e.song_id).sort().join();
    if (key === readyKey) return;
    readyKey = key;
    refreshReady();
  }
  let readyTimer = null;
  const refreshReady = () => {
    clearTimeout(readyTimer);
    readyTimer = setTimeout(() => { search.refresh(); side?.refresh(); }, 400);
  };

  connectWS("remote", (msg) => {
    if (msg.type === "state") { renderState(msg.data); watchReady(msg.data); GuestSettings.onLibrary(); }
    else if (msg.type === "playback") renderPlayback(msg);
    else if (msg.type === "intro") Battle.onIntro(msg);
    else if (msg.type === "settings") GuestSettings.onSettings();
    else if (msg.type === "library") { refreshReady(); GuestSettings.onLibrary(); }
    else if (msg.type === "media") GuestSettings.onLibrary();
  });

  return { openSearch };
})();
