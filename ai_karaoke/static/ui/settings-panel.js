// Every tunable setting as one block, for the /settings page and the apps' settings popup: the
// view-only notice (not the host), the Party & host PIN section, a filter box, how many settings
// differ from the defaults, reset all / per group / per setting, and the groups themselves.
// Changes save at once; the server validates them and refuses anyone but the host.
// No page ids or globals besides the constructor. Opens no WebSocket: call .refresh() when a
// "settings" message arrives (changed in another tab); host mode switching refreshes by itself.
// Needs common.js, auth.js, ui/settings-rows.js, ui/party-panel.js (ui/cache-panel.js optional).
// createSettingsPanel() -> element with .refresh()
function createSettingsPanel() {
  const root = el("div", "space-y-5");
  root.innerHTML = `
    <p data-k="readonly" class="panel hidden border-amber-500/40 p-3 text-sm text-amber-200">
      🔒 View only — settings can be changed on the laptop running the karaoke, or on this device after
      <button data-k="unlock" type="button" class="font-semibold underline">entering the host PIN</button>.</p>
    <div data-k="party"></div>
    <div data-k="cache"></div>
    <section class="panel flex flex-wrap items-center gap-3 p-3">
      <input data-k="filter" type="search" placeholder="Find a setting…"
             class="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/50 px-3 py-2 outline-none focus:border-amber-400">
      <span data-k="changed" class="text-sm text-stone-400"></span>
      <button data-k="reset-all" type="button" class="rounded-xl bg-red-900/70 px-4 py-2 text-sm font-semibold hover:bg-red-800 disabled:opacity-30">
        ↺ Reset all to defaults</button>
    </section>
    <div data-k="groups" class="space-y-5"></div>`;
  const part = (k) => root.querySelector(`[data-k="${k}"]`);
  part("party").replaceWith(createPartyPanel());
  // Song cache tools: only on pages that load ui/cache-panel.js (the host app)
  const cache = typeof createCachePanel === "function" ? createCachePanel() : el("div", "hidden");
  part("cache").replaceWith(cache);
  let page = { groups: [], settings: [], can_edit: false };

  async function refresh() {
    try { page = await api("/api/settings"); render(); } catch (err) { fail(err); }
    cache.refresh?.();
  }

  async function save(key, value) {
    try {
      page = await api("/api/settings", { method: "PUT", body: { values: { [key]: value } } });
      toast("Saved");
    } catch (err) { fail(err); }
    render(); // also snaps an invalid value back to the stored one
  }

  // One setting: at once, with Undo (ui/undo.js). A group or everything: asks first (ui/confirm.js).
  async function reset(keys, what) {
    const one = keys?.length === 1 && page.settings.find((s) => s.key === keys[0]);
    const What = `${what[0].toUpperCase()}${what.slice(1)}`;
    if (!one && !(await Confirm.ask({ title: "Reset settings?", message: `Reset ${what} to the default values?`, ok: "↺ Reset" }))) return;
    try {
      page = await api("/api/settings/reset", { method: "POST", body: { keys } });
      one ? Undo.now(`${What} back to the default`, () => save(one.key, one.value)) : toast(`${What} reset to defaults`);
    } catch (err) { fail(err); }
    render();
  }

  function group({ id, label }, q) {
    const specs = page.settings.filter((s) => s.group === id && (!q || `${s.label} ${s.help}`.toLowerCase().includes(q)));
    if (!specs.length) return el("div", "hidden");
    const box = el("section", "panel px-4 py-2");
    const head = el("div", "flex items-center justify-between border-b border-white/10 py-2");
    head.append(el("h2", "font-display text-xl font-bold text-gold", label));
    const groupChanged = specs.filter((s) => s.changed).map((s) => s.key);
    if (groupChanged.length && page.can_edit) {
      head.append(iconButton("↺ Reset group", `Reset every setting in ${label}`, () => reset(groupChanged, `all of ${label}`), "px-3 py-1.5"));
    }
    box.append(head, ...specs.map((spec) => SettingsRows.row(spec, page.can_edit, { save, reset })));
    return box;
  }

  function render() {
    const q = part("filter").value.trim().toLowerCase();
    const changed = page.settings.filter((s) => s.changed);
    part("changed").textContent = changed.length ? `${changed.length} changed from the defaults` : "All settings at their defaults";
    part("reset-all").disabled = !page.can_edit || !changed.length;
    part("readonly").classList.toggle("hidden", page.can_edit);
    part("groups").replaceChildren(...page.groups.map((g) => group(g, q)));
  }

  part("filter").oninput = render;
  part("reset-all").onclick = () => reset(null, "every setting");
  part("unlock").onclick = () => Auth.unlock();
  Auth.onChange(refresh); // host mode switched on/off: the server decides what may be edited
  refresh();
  // Side contents list where ui/settings-toc.js is loaded (the host app)
  return Object.assign(typeof SettingsToc === "object" ? SettingsToc.wrap(root) : root, { refresh });
}
