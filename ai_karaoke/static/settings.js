// Advanced settings page: the header from settings.html plus the settings panel
// (ui/settings-panel.js: every setting, resets, Party & host PIN). This page owns the
// WebSocket and tells the panel when settings changed in another tab.
// Needs common.js, auth.js, ui/settings-rows.js, ui/party-panel.js, ui/settings-panel.js.
const settingsPanel = createSettingsPanel();
document.querySelector("header").after(settingsPanel);
document.querySelector("header").insertBefore(hostBadge(), document.querySelector("header a"));
connectWS("remote", (msg) => { if (msg.type === "settings") settingsPanel.refresh(); }); // changed in another tab
