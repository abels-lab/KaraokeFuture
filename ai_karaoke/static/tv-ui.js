// Declarative Control Panel UI & Layout Controller for /tv
// Allows live layout reordering, panel/button toggling, custom buttons (SFX, settings, control, songs),
// guide vocal slider sizing & emoji thumbs, and live custom CSS injection in 1 tool call without reload.
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

  // ── WebAudio Party Sound Effects Synthesizer ─────────────────────────────
  let audioCtx = null;
  function getAudioContext() {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return null;
      if (!audioCtx) audioCtx = new AudioContext();
      if (audioCtx.state === "suspended") audioCtx.resume();
      return audioCtx;
    } catch {
      return null;
    }
  }

  function playSfx(type) {
    const ctx = getAudioContext();
    if (!ctx) return;
    const sound = String(type || "airhorn").toLowerCase().trim();

    try {
      const now = ctx.currentTime;
      if (sound === "airhorn") {
        // Reggae airhorn: Bb4 (466Hz) and Eb5 (622Hz) sawtooth stabs
        const bursts = [
          [0.00, 0.11],
          [0.15, 0.11],
          [0.30, 0.11],
          [0.45, 0.42],
        ];
        bursts.forEach(([st, dur]) => {
          const o1 = ctx.createOscillator();
          const o2 = ctx.createOscillator();
          const g = ctx.createGain();
          o1.type = "sawtooth";
          o2.type = "sawtooth";
          o1.frequency.setValueAtTime(466.16, now + st);
          o1.frequency.linearRampToValueAtTime(475.0, now + st + 0.04);
          o2.frequency.setValueAtTime(622.25, now + st);
          o2.frequency.linearRampToValueAtTime(630.0, now + st + 0.04);

          g.gain.setValueAtTime(0, now + st);
          g.gain.linearRampToValueAtTime(0.25, now + st + 0.015);
          g.gain.setValueAtTime(0.25, now + st + dur - 0.02);
          g.gain.linearRampToValueAtTime(0, now + st + dur);

          o1.connect(g);
          o2.connect(g);
          g.connect(ctx.destination);
          o1.start(now + st);
          o2.start(now + st);
          o1.stop(now + st + dur);
          o2.stop(now + st + dur);
        });
      } else if (sound === "applause") {
        // Bandpass filtered noise with clapping pops
        const dur = 2.0;
        const bufLen = Math.floor(ctx.sampleRate * dur);
        const buffer = ctx.createBuffer(1, bufLen, ctx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < bufLen; i++) {
          const pop = Math.random() < 0.015 ? (Math.random() * 2 - 1) * 2.5 : 0;
          data[i] = (Math.random() * 2 - 1) * 0.35 + pop;
        }
        const src = ctx.createBufferSource();
        src.buffer = buffer;
        const filter = ctx.createBiquadFilter();
        filter.type = "bandpass";
        filter.frequency.setValueAtTime(1100, now);
        filter.Q.setValueAtTime(1.2, now);
        const g = ctx.createGain();
        g.gain.setValueAtTime(0, now);
        g.gain.linearRampToValueAtTime(0.28, now + 0.25);
        g.gain.setValueAtTime(0.28, now + 1.2);
        g.gain.exponentialRampToValueAtTime(0.001, now + dur);

        src.connect(filter);
        filter.connect(g);
        g.connect(ctx.destination);
        src.start(now);
      } else if (sound === "drumroll") {
        // Snare roll crescendo ending in a punchy rimshot
        const hits = 22;
        const dur = 1.1;
        for (let i = 0; i < hits; i++) {
          const t = now + (i / hits) * dur;
          const vol = 0.04 + 0.22 * (i / hits);
          const o = ctx.createOscillator();
          const g = ctx.createGain();
          o.type = "triangle";
          o.frequency.setValueAtTime(175, t);
          g.gain.setValueAtTime(vol, t);
          g.gain.exponentialRampToValueAtTime(0.001, t + 0.04);
          o.connect(g);
          g.connect(ctx.destination);
          o.start(t);
          o.stop(t + 0.04);
        }
        const endT = now + dur + 0.02;
        const oEnd = ctx.createOscillator();
        const gEnd = ctx.createGain();
        oEnd.frequency.setValueAtTime(260, endT);
        gEnd.gain.setValueAtTime(0.38, endT);
        gEnd.gain.exponentialRampToValueAtTime(0.001, endT + 0.35);
        oEnd.connect(gEnd);
        gEnd.connect(ctx.destination);
        oEnd.start(endT);
        oEnd.stop(endT + 0.35);
      } else if (sound === "laser") {
        // Fast pitch dive retro laser
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sawtooth";
        o.frequency.setValueAtTime(1200, now);
        o.frequency.exponentialRampToValueAtTime(75, now + 0.16);
        g.gain.setValueAtTime(0.25, now);
        g.gain.exponentialRampToValueAtTime(0.001, now + 0.16);
        o.connect(g);
        g.connect(ctx.destination);
        o.start(now);
        o.stop(now + 0.16);
      } else if (sound === "cheer") {
        // Celebratory chord ascending sweep
        const chord = [392.0, 523.25, 659.25, 783.99];
        chord.forEach((freq, idx) => {
          const o = ctx.createOscillator();
          const g = ctx.createGain();
          o.type = "triangle";
          o.frequency.setValueAtTime(freq * 0.85, now);
          o.frequency.exponentialRampToValueAtTime(freq, now + 0.18);
          g.gain.setValueAtTime(0, now);
          g.gain.linearRampToValueAtTime(0.12, now + 0.07);
          g.gain.exponentialRampToValueAtTime(0.001, now + 0.85 + idx * 0.08);
          o.connect(g);
          g.connect(ctx.destination);
          o.start(now);
          o.stop(now + 1.0);
        });
      } else {
        // Default chime
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sine";
        o.frequency.setValueAtTime(587.33, now);
        g.gain.setValueAtTime(0.2, now);
        g.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
        o.connect(g);
        g.connect(ctx.destination);
        o.start(now);
        o.stop(now + 0.3);
      }
    } catch (err) {
      console.warn("SFX error:", err);
    }
  }

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
      try {
        if (typeof send === "function") {
          send({ type: "control", action: val });
        }
        await api("/api/queue/control", { method: "POST", body: { action: val } });
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

  // ── DOM Layout & Customizer ──────────────────────────────────────────────
  function applyColumnOrder(order) {
    const layout = $("tv-layout");
    if (!layout || !Array.isArray(order) || !order.length) return;
    const cols = {
      left: $("col-left"),
      center: $("col-center"),
      right: $("col-right"),
    };
    order.forEach((key, idx) => {
      const col = cols[key];
      if (col) {
        col.style.order = String(idx + 1);
        layout.appendChild(col);
      }
    });
  }

  function applyHiddenElements(hiddenList) {
    const hiddenSet = new Set(Array.isArray(hiddenList) ? hiddenList : []);
    // First, show elements previously hidden by agent that are no longer hidden
    document.querySelectorAll("[data-agent-hidden='true']").forEach((el) => {
      if (!hiddenSet.has(el.id)) {
        el.classList.remove("hidden");
        el.removeAttribute("data-agent-hidden");
      }
    });
    // Now hide specified elements
    hiddenSet.forEach((id) => {
      const el = $(id);
      if (el) {
        el.classList.add("hidden");
        el.setAttribute("data-agent-hidden", "true");
      }
    });
  }

  function applyGuideWidth(widthStr) {
    const guide = $("guide");
    if (!guide || !widthStr) return;
    document.documentElement.style.setProperty("--guide-slider-width", widthStr);
    guide.style.width = widthStr;
    const clean = String(widthStr).trim();
    if (clean === "100%" || parseInt(clean) > 30) {
      guide.style.maxWidth = "none";
      guide.style.minWidth = "5.5rem";
    } else if (clean === "25%") {
      guide.style.maxWidth = "7.5rem";
      guide.style.minWidth = "5.5rem";
    }
  }

  function applyGuideThumb(thumbStr) {
    let styleTag = $("agent-guide-thumb-style");
    if (!styleTag) {
      styleTag = document.createElement("style");
      styleTag.id = "agent-guide-thumb-style";
      document.head.appendChild(styleTag);
    }
    const clean = String(thumbStr || "default").trim();
    if (!clean || clean === "default") {
      styleTag.textContent = "";
      document.body.classList.remove("smiley-guide");
      return;
    }
    if (clean === "smiley") {
      document.body.classList.add("smiley-guide");
      styleTag.textContent = "";
      return;
    }
    document.body.classList.remove("smiley-guide");
    // Render custom emoji in SVG data URL for slider thumb
    const emoji = clean;
    const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><text y='19' font-size='19'>${emoji}</text></svg>`;
    const dataUri = `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
    styleTag.textContent = `
      #guide::-webkit-slider-thumb {
        -webkit-appearance: none !important;
        appearance: none !important;
        width: 1.4rem !important;
        height: 1.4rem !important;
        border-radius: 50% !important;
        background: #f4c25b ${dataUri} center/contain no-repeat !important;
        border: none !important;
        cursor: pointer !important;
        filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.5)) !important;
      }
      #guide::-moz-range-thumb {
        width: 1.4rem !important;
        height: 1.4rem !important;
        border-radius: 50% !important;
        background: #f4c25b ${dataUri} center/contain no-repeat !important;
        border: none !important;
        cursor: pointer !important;
        filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.5)) !important;
      }
    `;
  }

  function applyCustomCss(cssStr) {
    let tag = $("agent-custom-css");
    if (!tag) {
      tag = document.createElement("style");
      tag.id = "agent-custom-css";
      document.head.appendChild(tag);
    }
    tag.textContent = cssStr || "";
  }

  function applyCustomButtons(buttons) {
    const containers = {
      display: $("custom-controls"),
      nav: $("custom-nav-controls"),
      transport: $("custom-transport-controls"),
    };
    Object.values(containers).forEach((c) => { if (c) c.innerHTML = ""; });

    if (!Array.isArray(buttons)) return;
    buttons.forEach((b) => {
      const target = b.target || "display";
      const parent = containers[target] || containers.display;
      if (!parent) return;

      const btnEl = document.createElement("button");
      btnEl.id = `custom-btn-${b.id}`;
      btnEl.className = b.style || (
        target === "transport"
          ? "flex h-10 items-center justify-center gap-1 rounded-full bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 px-3 text-xs font-semibold text-amber-200 transition active:scale-95 shrink-0 shadow-sm"
          : "flex items-center justify-center gap-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 px-3 py-1.5 text-xs font-semibold text-amber-200 transition active:scale-95 shadow-sm"
      );
      btnEl.title = `${b.label} (${b.action}: ${b.value || ""})`;

      const iconSpan = b.icon ? `<span class="shrink-0">${b.icon}</span>` : "";
      const textSpan = `<span>${b.label}</span>`;
      btnEl.innerHTML = `${iconSpan}${textSpan}`;
      btnEl.onclick = () => handleCustomAction(b);
      parent.appendChild(btnEl);
    });
  }

  function applyConfig(cfg, save = true) {
    if (!cfg || typeof cfg !== "object") return;
    activeConfig = { ...activeConfig, ...cfg };
    if (save) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(activeConfig));
      } catch {}
    }

    if (activeConfig.column_order) applyColumnOrder(activeConfig.column_order);
    if (activeConfig.hidden_elements) applyHiddenElements(activeConfig.hidden_elements);
    if (activeConfig.guide_width) applyGuideWidth(activeConfig.guide_width);
    if (activeConfig.guide_thumb) applyGuideThumb(activeConfig.guide_thumb);
    if (activeConfig.custom_css !== undefined) applyCustomCss(activeConfig.custom_css);
    if (activeConfig.custom_buttons) applyCustomButtons(activeConfig.custom_buttons);
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
