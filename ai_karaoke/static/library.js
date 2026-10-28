// Song library page: the header from library.html plus the library panel (ui/library-panel.js:
// cache bar, filter, every cached song with queue / lyrics / re-sync / rebuild / delete).
// This page owns the WebSocket and tells the panel when songs, the queue or media changed.
// Needs common.js, auth.js, lyrics.js, ui/library-card.js, ui/library-panel.js.
const libraryPanel = createLibraryPanel();
$("header").after(libraryPanel);
$("header").insertBefore(hostBadge(), $("header").querySelector("a"));
connectWS("remote", (msg) => { if (["state", "library", "media"].includes(msg.type)) libraryPanel.refreshSoon(); });
