// Declarative control panel customization by the DJ Co-Pilot (services/agent.py tool
// customize_control_panel, pushed live as WS "ui_config"): column order, hidden panels / buttons,
// custom buttons (SFX, settings, playback control, songs), guide-slider size and thumb, extra CSS
// — all in one tool call, without a reload. The config is kept here and saved in localStorage for
// an instant first paint; tv-ui-apply.js paints it, tv-sfx.js plays the sound effects.
// Needs common.js, tv-ui-apply.js, tv-sfx.js.
// window.TvUi = { init(), applyConfig(cfg, save), getConfig(), playSfx(type), handleCustomAction(button) }
window.TvUi = (() => {
  const STORAGE_KEY = "karaoke_ui_config";
  let activeConfig = {
    column_order: ["left", "center", "right"],
    hidden_elements: [],
    custom_buttons: [],
    guide_width: "25%",
    guide_thumb: "default",
    custom_css: "",
  };
  const playSfx = (type) => TvSfx.play(type);

  // ── Custom Button Action Dispatcher ──────────────────────────────────────
  async function handleCustomAction(btn) {
    if (!btn) return;
    const action = btn.action;
    const val = btn.value;

    if (action === "sfx") {
      playSfx(val);
      toast(`🔊 SFX: ${btn.label || val}`, true);
    } else if (action === "toast") {
      toast(val || btn.label || "🎉 Party time!", true);
    } else if (action === "control") {
      try {   // the REST twin of the WebSocket "control" message: works in controller mode too
        await api("/api/player/control", { method: "POST", body: { action: val } });
      } catch (err) {
        toast(`Control action '${val}' failed: ${err.message}`, false);
      }
    } else if (action === "setting") {
      try {
        let key = "", value = "";
        if (typeof val === "object" && val) {
          key = val.key; value = val.value;
        } else if (String(val).includes(":")) {
          const parts = val.split(":");
          key = parts[0].trim();
          value = parts.slice(1).join(":").trim();
        } else {
          key = val; value = true;
        }
        if (value === "true") value = true;
        if (value === "false") value = false;
        await api("/api/settings", { method: "PUT", body: { values: { [key]: value } } });
        toast(`Setting updated: ${key} → ${value}`, true);
      } catch (err) {
        toast(`Setting change failed: ${err.message}`, false);
      }
    } else if (action === "queue_search") {
      try {
        let query = val, singer = "Host";
        if (typeof val === "object" && val) {
          query = val.query || val.title;
          singer = val.singer || "Host";
        }
        toast(`Queueing "${query}" for ${singer}…`, true);
        await api("/api/agent/chat", {
          method: "POST",
          body: { message: `Queue "${query}" for ${singer}` },
        });
      } catch (err) {
        toast(`Queue failed: ${err.message}`, false);
      }
    }
  }

  function applyConfig(cfg, save = true) {
    if (!cfg || typeof cfg !== "object") return;
    activeConfig = { ...activeConfig, ...cfg };
    if (save) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(activeConfig));
      } catch {}
    }

    if (activeConfig.column_order) TvUiApply.columns(activeConfig.column_order);
    if (activeConfig.hidden_elements) TvUiApply.hidden(activeConfig.hidden_elements);
    if (activeConfig.guide_width) TvUiApply.guideWidth(activeConfig.guide_width);
    if (activeConfig.guide_thumb) TvUiApply.guideThumb(activeConfig.guide_thumb);
    if (activeConfig.custom_css !== undefined) TvUiApply.css(activeConfig.custom_css);
    if (activeConfig.custom_buttons) TvUiApply.buttons(activeConfig.custom_buttons, handleCustomAction);
  }

  function init() {
    // 1. Instant paint from localStorage
    try {
      const cached = localStorage.getItem(STORAGE_KEY);
      if (cached) {
        applyConfig(JSON.parse(cached), false);
      }
    } catch {}

    // 2. Fetch authoritative UI config from backend
    if (typeof api === "function") {
      api("/api/agent/ui-config")
        .then((cfg) => {
          if (cfg && typeof cfg === "object") {
            applyConfig(cfg, true);
          }
        })
        .catch(() => {});
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  return {
    init,
    applyConfig,
    getConfig() { return { ...activeConfig }; },
    playSfx,
    handleCustomAction,
  };
})();
