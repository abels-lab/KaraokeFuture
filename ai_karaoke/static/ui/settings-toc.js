// Side contents list for the settings panel (ui/settings-panel.js): one entry per section that
// renders — every <section> with an <h2> (party, cache, each settings group, any panel added
// later) — so new groups and panels show up by themselves. A click scrolls the popup to that
// section (smoothly, unless the viewer prefers reduced motion); an IntersectionObserver marks the
// section in view; a badge counts the settings changed from their defaults ([data-changed] rows).
// Laptop / wide popup: a sticky left column. Narrow (phone): a sticky chip bar that scrolls
// sideways. The width switch is a container query on the popup's width (ui/settings-toc.css).
// Needs common.js (el). SettingsToc.wrap(panel) -> element holding the list and the panel.
const SettingsToc = (() => {
  const motion = () => (matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");
  const scroller = (node) => {
    for (let p = node.parentElement; p; p = p.parentElement) {
      if (/(auto|scroll)/.test(getComputedStyle(p).overflowY) && p.scrollHeight > p.clientHeight) return p;
    }
    return null;
  };

  function wrap(panel) {
    const shell = el("div", "settings-shell");
    const nav = el("nav", "settings-toc");
    nav.setAttribute("aria-label", "Settings sections");
    const list = el("div", "settings-toc-list");
    nav.append(list);
    const grid = el("div", "settings-grid");   // a container query styles only what is inside
    grid.append(nav, panel);
    shell.append(grid);
    panel.classList.add("settings-main");

    let entries = [];          // [{ section, button }] in page order
    let lock = null;           // the section a click went to: it stays marked until a hand scroll
    const visible = new Set();
    // In view: the first section in the band near the top; at the very bottom, where the last short
    // sections can never reach that band, the last one showing
    function pick() {
      const box = scroller(shell);
      const shown = entries.filter((e) => visible.has(e.section));
      const atEnd = box && box.scrollTop + box.clientHeight >= box.scrollHeight - 4;
      return (atEnd ? shown[shown.length - 1] : shown[0])?.section;
    }
    const io = new IntersectionObserver((changes) => {
      for (const c of changes) c.isIntersecting ? visible.add(c.target) : visible.delete(c.target);
      if (!lock) mark(pick());
    }, { rootMargin: "-15% 0px -45% 0px" });

    function mark(section) {
      if (!section) return;
      for (const { section: s, button } of entries) {
        const on = s === section;
        button.classList.toggle("is-active", on);
        on ? button.setAttribute("aria-current", "true") : button.removeAttribute("aria-current");
        // Chip bar: bring the active chip into sight. Instantly: a second smooth scroll would
        // cancel the popup's own smooth scroll in Chrome.
        if (on && list.scrollWidth > list.clientWidth) {
          const [b, l] = [button.getBoundingClientRect(), list.getBoundingClientRect()];
          list.scrollLeft += b.left - l.left - (l.width - b.width) / 2;
        }
      }
    }

    const handScroll = () => { if (lock) { lock = null; mark(pick()); } };
    function go(section) {
      const box = scroller(section);
      lock = section;
      mark(section);
      if (!box) return;
      if (!box.dataset.tocHooked) {   // wheel, touch, keys or the scrollbar: the viewer took over
        box.dataset.tocHooked = "1";
        for (const type of ["wheel", "touchmove", "keydown", "pointerdown"]) box.addEventListener(type, handScroll, { passive: true });
      }
      const margin = parseFloat(getComputedStyle(section).scrollMarginTop) || 0;
      const top = section.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop - margin;
      box.scrollTo({ top, behavior: motion() });
    }

    // Outermost visible sections with a heading, in page order
    function sections() {
      const all = [...panel.querySelectorAll("section")].filter((s) => s.querySelector("h2") && !s.closest(".hidden"));
      return all.filter((s) => !all.some((o) => o !== s && o.contains(s)));
    }

    function build() {
      io.disconnect();
      visible.clear();
      const current = entries.find((e) => e.button.classList.contains("is-active"))?.label;
      entries = sections().map((section) => {
        const label = section.querySelector("h2").textContent.trim();
        const changed = section.querySelectorAll("[data-changed]").length;
        const button = el("button", "settings-toc-item");
        button.type = "button";
        button.append(el("span", "settings-toc-label", label));
        if (changed) {
          const badge = el("span", "settings-toc-badge", String(changed));
          badge.title = `${changed} changed from the default${changed === 1 ? "" : "s"}`;
          button.append(badge);
        }
        button.onclick = () => go(section);
        io.observe(section);
        return { section, button, label };
      });
      list.replaceChildren(...entries.map((e) => e.button));
      nav.classList.toggle("hidden", entries.length < 2);
      mark((entries.find((e) => e.label === current) || entries[0])?.section);
    }

    // The panel repaints itself (filter, saves, host mode, panels hiding): rebuild. A mutation
    // observer already batches a whole repaint into one call (no rAF: it stalls in background tabs).
    new MutationObserver(build).observe(panel, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "data-changed"] });
    build();
    return shell;
  }

  return { wrap };
})();
