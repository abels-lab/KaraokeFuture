// How the pages look, from the Settings page ("Screen & theme", "Layout"), applied live on every page:
// theme (body data-theme: background picture, theme.css), colour preset (the --gold /
// --gold-deep variables that titles, buttons and sung words use), the party title ([data-title]),
// where the lyrics sit ([data-lyrics-box]), whether music videos show (body.no-video) and the
// lyrics mode (body.lyrics-plain: no word fill, body.lyrics-off: no lyrics), video & background
// shading intensity (--stage-dim), QR code display (body.no-qr, body.no-qr-link, --qr-scale),
// and side panel width (--side-panel-width) on the control panel. The party's custom style
// (Settings → Custom style, the DJ Co-Pilot's set_style) is applyStyle: style-fx.css classes and
// variables, and the custom CSS (checked on the server by core/css_guard.py) in a <style> of its own.
// Needs common.js (Settings). Look.infoCard(time, duration) -> should the song info card show now?
const ACCENTS = { gold: ["#f4c25b", "#d99a2b"], neon: ["#ff5fd2", "#d01f9e"], ice: ["#7fd8ff", "#2b9bd9"],
                  lime: ["#c6f25b", "#86b51f"], fire: ["#ff7a3d", "#d8341a"], silver: ["#eef0f6", "#9ea7ba"] };
const THEME_ACCENT = { theater: "gold", club: "neon", rock: "fire", adaptive: "ice" };

const Look = (() => {
  function apply() {
    const theme = Settings.get("theme", "theater"), preset = Settings.get("accent", "theme");
    document.body.dataset.theme = theme;
    const hex = Settings.get("style_accent_hex", "");
    const [gold, deep] = /^#[0-9a-f]{6}$/i.test(hex) ? [hex, `color-mix(in srgb, ${hex} 70%, #000)`]
      : ACCENTS[preset === "theme" ? THEME_ACCENT[theme] : preset] || ACCENTS.gold;
    document.documentElement.style.setProperty("--gold", gold);
    document.documentElement.style.setProperty("--gold-deep", deep);
    applyStyle();

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
  // One class per choice (fx-font-rounded …), dropped again at the theme's default
  function choiceClass(prefix, value, off) {
    document.body.classList.forEach((c) => { if (c.startsWith(prefix)) document.body.classList.remove(c); });
    if (value && value !== off) document.body.classList.add(prefix + value);
  }

  function applyStyle() {
    const body = document.body, root = document.documentElement.style;
    if (!document.getElementById("fx-bg")) body.prepend(Object.assign(document.createElement("div"), { id: "fx-bg" }));
    choiceClass("fx-font-", Settings.get("style_font", "theme"), "theme");
    choiceClass("fx-title-", Settings.get("style_title_effect", "none"), "none");
    choiceClass("fx-bg-", Settings.get("style_background", "theme"), "theme");
    const glow = Number(Settings.get("style_glow", 0)) / 100, pulse = Number(Settings.get("style_pulse", 0)) / 100;
    const corners = Number(Settings.get("style_corners", 100)) / 100;
    body.classList.toggle("fx-glow", glow > 0);
    body.classList.toggle("fx-pulse", pulse > 0);
    body.classList.toggle("fx-corners", corners !== 1);
    body.classList.toggle("fx-square", corners === 0);
    root.setProperty("--fx-glow", glow);
    root.setProperty("--fx-pulse", pulse);
    root.setProperty("--fx-r", corners);
    let tag = document.getElementById("party-custom-css");
    if (!tag) {
      tag = Object.assign(document.createElement("style"), { id: "party-custom-css" });
      document.head.appendChild(tag);   // last, so it wins over the theme
    }
    tag.textContent = Settings.get("custom_css", "") || "";
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
