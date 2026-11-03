// The Co-Pilot's control panel customizations, applied to the page: column order, hidden panels
// and buttons (by element id), guide-slider width and thumb, extra CSS and custom buttons in the
// display / nav / transport rows. Split from tv-ui.js, which keeps and saves the config; this file
// only paints it. The ids are the markup's (host/markup-*.js). Column order matters on the laptop
// layout only: tablets and phones arrange the cards themselves (host/host.css).
// Needs common.js. TvUiApply = { columns(order), hidden(ids), guideWidth(css), guideThumb(kind),
//   buttons(list, onClick(button)) }
const TvUiApply = (() => {
  function columns(order) {
    const layout = $("tv-layout");
    if (!layout || !Array.isArray(order) || !order.length) return;
    const cols = { left: $("col-left"), center: $("col-center"), right: $("col-right") };
    order.forEach((key, idx) => {
      const col = cols[key];
      if (col) {
        col.style.order = String(idx + 1);
        layout.appendChild(col);
      }
    });
  }

  function hidden(hiddenList) {
    const hiddenSet = new Set(Array.isArray(hiddenList) ? hiddenList : []);
    // First, show elements previously hidden by the agent that are no longer hidden
    document.querySelectorAll("[data-agent-hidden='true']").forEach((node) => {
      if (!hiddenSet.has(node.id)) {
        node.classList.remove("hidden");
        node.removeAttribute("data-agent-hidden");
      }
    });
    hiddenSet.forEach((id) => {
      const node = $(id);
      if (node) {
        node.classList.add("hidden");
        node.setAttribute("data-agent-hidden", "true");
      }
    });
  }

  function guideWidth(widthStr) {
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

  // A <style> of our own, made once and refilled on every change
  function styleTag(id) {
    let tag = $(id);
    if (!tag) {
      tag = document.createElement("style");
      tag.id = id;
      document.head.appendChild(tag);
    }
    return tag;
  }

  // "default", "smiley" (theme.css body.smiley-guide) or any emoji drawn into the slider thumb
  function guideThumb(thumbStr) {
    const tag = styleTag("agent-guide-thumb-style");
    const clean = String(thumbStr || "default").trim();
    document.body.classList.toggle("smiley-guide", clean === "smiley");
    if (!clean || clean === "default" || clean === "smiley") { tag.textContent = ""; return; }
    const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><text y='19' font-size='19'>${clean}</text></svg>`;
    const dataUri = `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
    const thumb = `
        width: 1.4rem !important;
        height: 1.4rem !important;
        border-radius: 50% !important;
        background: #f4c25b ${dataUri} center/contain no-repeat !important;
        border: none !important;
        cursor: pointer !important;
        filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.5)) !important;`;
    tag.textContent = `
      #guide::-webkit-slider-thumb {
        -webkit-appearance: none !important;
        appearance: none !important;${thumb}
      }
      #guide::-moz-range-thumb {${thumb}
      }`;
  }

  const BUTTON_STYLE = {
    transport: "flex h-10 items-center justify-center gap-1 rounded-full bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 px-3 text-xs font-semibold text-amber-200 transition active:scale-95 shrink-0 shadow-sm",
    other: "flex items-center justify-center gap-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 px-3 py-1.5 text-xs font-semibold text-amber-200 transition active:scale-95 shadow-sm",
  };

  function buttons(list, onClick) {
    const containers = { display: $("custom-controls"), nav: $("custom-nav-controls"), transport: $("custom-transport-controls") };
    Object.values(containers).forEach((c) => { if (c) c.innerHTML = ""; });
    if (!Array.isArray(list)) return;
    list.forEach((b) => {
      const target = b.target || "display";
      const parent = containers[target] || containers.display;
      if (!parent) return;
      const btnEl = document.createElement("button");
      btnEl.id = `custom-btn-${b.id}`;
      btnEl.className = target === "transport" ? BUTTON_STYLE.transport : BUTTON_STYLE.other;
      btnEl.title = `${b.label} (${b.action}: ${b.value || ""})`;
      if (b.icon) btnEl.append(el("span", "shrink-0", b.icon));   // text, never markup
      btnEl.append(el("span", "", b.label));
      btnEl.onclick = () => onClick(b);
      parent.appendChild(btnEl);
    });
  }

  return { columns, hidden, guideWidth, guideThumb, buttons };
})();
