// How the pages look, from the Settings page ("Screen & theme"), applied live on every page:
// theme (body data-theme: background picture, theme.css), colour preset (the --gold /
// --gold-deep variables that titles, buttons and sung words use), the party title ([data-title]),
// where the lyrics sit ([data-lyrics-box]) and whether music videos show (body.no-video).
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
    const title = Settings.get("title_text", "Karaoke Night");
    document.querySelectorAll("[data-title]").forEach((e) => { e.textContent = title; });
    document.querySelectorAll("[data-lyrics-box]").forEach((e) => { e.dataset.pos = Settings.get("lyrics_position", "bottom"); });
    document.body.classList.toggle("no-video", !Settings.get("show_video", true));
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
