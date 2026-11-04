// "Sources" block of the settings panel (host only): every website songs and lyrics come from,
// grouped by what it is for. Each source has an on/off switch and, where the order matters,
// ↑ ↓ buttons (the order is the fallback order). The host's own links can be changed, tested
// and removed, and new ones added below (ui/sources-form.js). The server enforces all of it
// (routers/sources.py). Needs common.js, auth.js, ui/sources-form.js.
// createSourcesPanel() -> <section> with .refresh(); hidden for guests.
function createSourcesPanel() {
  const KIND_ICON = { songs: "🎵", synced: "⏱", lyrics: "📝", chords: "🎸", info: "ℹ️" };
  const box = el("section", "panel hidden space-y-4 p-4");
  box.innerHTML = `
    <div>
      <h2 class="font-display text-xl font-bold text-gold">Sources</h2>
      <p class="text-sm text-stone-400">Where songs and lyrics are looked for. Within each group they are tried from the top;
        switched-off sources are skipped. Changes apply to the next search or song.</p>
    </div>
    <div data-k="kinds" class="space-y-4"></div>
    <div data-k="form"></div>`;
  const part = (k) => box.querySelector(`[data-k="${k}"]`);
  const form = createSourcesForm((page) => paint(page));
  part("form").replaceWith(form);
  let page = null;

  async function call(path, method, body) {
    try { paint(await api(path, { method, body })); } catch (err) { fail(err); refresh(); }
  }

  function row(src, i, list, kind) {
    const r = el("div", `flex flex-wrap items-center gap-2 border-l-2 py-2 pl-3 ${src.enabled ? "border-amber-400" : "border-transparent opacity-60"}`);
    const text = el("div", "min-w-[12rem] flex-1");
    const title = el("p", "flex flex-wrap items-center gap-2 font-semibold", src.name);
    if (!src.builtin) title.append(el("span", "rounded-full bg-sky-900/70 px-2 py-0.5 text-[11px] font-semibold text-sky-200", "your link"));
    const url = el("p", "break-all font-mono text-xs text-stone-500", src.builtin ? src.url : src.template);
    text.append(title, url);
    if (src.note) text.append(el("p", "text-xs text-stone-400", src.note));
    const status = page.status?.[src.id];
    if (status && status !== "ready") text.append(el("p", "text-xs text-amber-300", `⚠ ${status}`));

    const side = el("div", "flex flex-wrap items-center gap-1.5");
    const id = encodeURIComponent(src.id);
    if (kind.orderable && list.length > 1) {
      side.append(
        Object.assign(iconButton("↑", "Try earlier", () => call(`/api/sources/${id}/move`, "POST", { step: -1 }), "px-2.5 py-1.5 text-sm"), { disabled: i === 0 }),
        Object.assign(iconButton("↓", "Try later", () => call(`/api/sources/${id}/move`, "POST", { step: 1 }), "px-2.5 py-1.5 text-sm"), { disabled: i === list.length - 1 }));
    }
    if (!src.builtin) {
      side.append(iconButton("✎", "Change or test this link", () => form.edit(src), "px-2.5 py-1.5 text-sm"),
        iconButton("🗑", "Remove this link", () => confirm(`Remove the link “${src.name}”?`)
          && call(`/api/sources/custom/${id}`, "DELETE"), "px-2.5 py-1.5 text-sm"));
    }
    const label = el("label", "flex cursor-pointer items-center gap-2 pl-1 text-sm");
    const toggle = Object.assign(el("input", "h-5 w-5 accent-amber-400"), { type: "checkbox", checked: src.enabled });
    toggle.title = src.enabled ? "Switch off" : "Switch on";
    toggle.onchange = () => call(`/api/sources/${id}`, "PUT", { enabled: toggle.checked });
    label.append(toggle, el("span", "w-7 text-stone-400", src.enabled ? "on" : "off"));
    side.append(label);
    r.append(text, side);
    return r;
  }

  function kindBlock(kind) {
    const block = el("div", "rounded-xl border border-white/10 px-3 py-2");
    const on = kind.sources.filter((s) => s.enabled).length;
    const head = el("div", "flex flex-wrap items-baseline justify-between gap-2 border-b border-white/10 pb-1");
    head.append(el("h3", "font-semibold text-amber-200", `${KIND_ICON[kind.id] || ""} ${kind.label}`),
      el("span", `text-xs ${on ? "text-stone-400" : "text-red-300"}`, on ? `${on} of ${kind.sources.length} on` : "all off"));
    block.append(head, ...kind.sources.map((s, i, list) => row(s, i, list, kind)));
    return block;
  }

  function paint(data) {
    page = data;
    part("kinds").replaceChildren(...data.kinds.map(kindBlock));
    box.classList.remove("hidden");
  }

  async function refresh() {
    if (!Auth.me.admin) { box.classList.add("hidden"); return; }
    try { paint(await api("/api/sources")); } catch { box.classList.add("hidden"); }
  }

  Auth.onChange(refresh);
  refresh();
  return Object.assign(box, { refresh });
}
