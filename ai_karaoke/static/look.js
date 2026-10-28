// How the pages look, from the Settings page ("Screen & theme", "Layout"), applied live on every page:
// theme (body data-theme: background picture, theme.css), colour preset (the --gold /
// --gold-deep variables that titles, buttons and sung words use), the party title ([data-title]),
// where the lyrics sit ([data-lyrics-box]), whether music videos show (body.no-video) and the
// lyrics mode (body.lyrics-plain: no word fill, body.lyrics-off: no lyrics), video & background
// shading intensity (--stage-dim), QR code display (body.no-qr, body.no-qr-link, --qr-scale),
// and side panel width (--side-panel-width) on the control panel.
// Needs common.js (Settings). Look.infoCard(time, duration) -> should the song info card show now?
const ACCENTS = { gold: ["#f4c25b", "#d99a2b"], neon: ["#ff5fd2", "#d01f9e"], ice: ["#7fd8ff", "#2b9bd9"],
                  lime: ["#c6f25b", "#86b51f"], fire: ["#ff7a3d", "#d8341a"], silver: ["#eef0f6", "#9ea7ba"] };
const THEME_ACCENT = { theater: "gold", club: "neon", rock: "fire", adaptive: "ice" };

const Look = (() => {
  function apply() {
    const theme = Settings.get("theme", "theater"), preset = Settings.get("accent", "theme");
    document.body.dataset.theme = theme;
    const [gold, deep] = ACCENTS[preset === "theme" ? THEME_ACCENT[theme] : preset] || ACCENTS.gold;
    document.documentElement.style.setProperty("--gold", gold);
    document.documentElement.style.setProperty("--gold-deep", deep);

    // Tunable video & stage background shading (0% - 100%, default 40%)
    const rawDim = Settings.get("stage_dim", 40);
    const stageDim = Math.max(0, Math.min(1, (Number(rawDim) ?? 40) / 100));
    document.documentElement.style.setProperty("--stage-dim", stageDim.toFixed(2));

    // QR code display settings (show/hide QR, show/hide link, size multiplier)
    const showQr = Settings.get("show_qr", true);
    document.body.classList.toggle("no-qr", !showQr);
    const showLink = Settings.get("show_qr_link", true);
    document.body.classList.toggle("no-qr-link", !showLink);
    const qrSizeRaw = Settings.get("qr_size", 100);
    const qrScale = Math.max(0.5, Math.min(2.0, (Number(qrSizeRaw) || 100) / 100));
    document.documentElement.style.setProperty("--qr-scale", qrScale.toFixed(2));

    // Side panel width on the control panel (/tv)
    const rawSideWidth = Settings.get("side_panel_width", 28);
    const sideWidthNum = Number(rawSideWidth) || 28;
    const sideUnit = sideWidthNum > 100 ? "px" : "rem";
    document.documentElement.style.setProperty("--side-panel-width", `${sideWidthNum}${sideUnit}`);

    // DJ Co-Pilot chat panel width on the control panel (/tv)
    const rawAgentWidth = Settings.get("chat_panel_width", 27);
    const agentWidthNum = Number(rawAgentWidth) || 27;
    const agentUnit = agentWidthNum > 100 ? "px" : "rem";
    document.documentElement.style.setProperty("--agent-panel-width", `${agentWidthNum}${agentUnit}`);

    const title = Settings.get("title_text", "Karaoke Night");
    document.querySelectorAll("[data-title]").forEach((e) => { e.textContent = title; });
    const pos = Settings.get("lyrics_position", "bottom");
    document.body.dataset.lyricsPos = pos;
    document.querySelectorAll("[data-lyrics-box]").forEach((e) => { e.dataset.pos = pos; });
    document.body.classList.toggle("no-video", !Settings.get("show_video", true));
    const lyrics = Settings.get("lyrics_mode", "full");
    document.body.classList.toggle("lyrics-plain", lyrics === "plain");
    document.body.classList.toggle("lyrics-off", lyrics === "off");

    // Support / Buy Me a Coffee link
    const supportUrl = Settings.get("support_url", "https://github.com/sponsors/abels-lab");
    const showSupportOnRemote = Settings.get("show_support_on_remote", true);
    document.querySelectorAll("#support-link, [data-support-link]").forEach((el) => {
      if (supportUrl) {
        el.href = supportUrl;
        el.classList.remove("hidden");
      } else {
        el.classList.add("hidden");
      }
    });
    const supportFooter = document.getElementById("support-footer");
    if (supportFooter) {
      supportFooter.classList.toggle("hidden", !showSupportOnRemote || !supportUrl);
    }
  }
  Settings.onChange(apply);

  // Right after the song starts, and once more around its middle (both optional)
  function infoCard(t, duration) {
    const secs = Settings.get("info_card_seconds", 6);
    if (!secs) return false;
    if (t < secs) return true;
    return Settings.get("info_card_middle", true) && duration > 3 * secs && Math.abs(t - duration / 2) < secs / 2;
  }
  return { apply, infoCard };
})();
