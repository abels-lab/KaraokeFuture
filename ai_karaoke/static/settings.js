// Advanced settings page: every tunable value with its explanation, default and when it applies.
// Changes save immediately; the server validates them. Per-setting, per-group and full resets.
let page = { groups: [], settings: [], can_edit: false };
const APPLIES = { "immediately": ["now", "bg-emerald-900/70 text-emerald-200"],
                  "next song": ["next song", "bg-sky-900/70 text-sky-200"],
                  "next processed song": ["new or rebuilt songs", "bg-amber-900/70 text-amber-200"] };

async function refresh() {
  try { page = await api("/api/settings"); render(); } catch (err) { fail(err); }
}

async function save(key, value) {
  try {
    page = await api("/api/settings", { method: "PUT", body: { values: { [key]: value } } });
    toast("Saved");
  } catch (err) { fail(err); }
  render(); // also snaps an invalid value back to the stored one
}

async function reset(keys, what) {
  if (!confirm(`Reset ${what} to the default value${keys && keys.length === 1 ? "" : "s"}?`)) return;
  try {
    page = await api("/api/settings/reset", { method: "POST", body: { keys } });
    toast(`${what[0].toUpperCase()}${what.slice(1)} reset to defaults`);
  } catch (err) { fail(err); }
  render();
}

const show = (spec, value) => {
  if (spec.kind === "bool") return value ? "on" : "off";
  if (spec.kind === "choice") return (spec.choices.find(([v]) => String(v) === String(value)) || [value, value])[1];
  return `${value}${spec.unit ? ` ${spec.unit}` : ""}`;
};

function control(spec) {
  const disabled = !page.can_edit;
  if (spec.kind === "bool") {
    const box = Object.assign(el("input", "h-5 w-5 accent-amber-400"), { type: "checkbox", checked: spec.value, disabled });
    box.onchange = () => save(spec.key, box.checked);
    return box;
  }
  if (spec.kind === "choice") {
    const select = Object.assign(el("select", "rounded-lg bg-black/50 px-2 py-1.5 text-sm ring-1 ring-white/10 disabled:opacity-60"), { disabled });
    for (const [value, label] of spec.choices) select.append(Object.assign(el("option", "bg-stone-900", label), { value }));
    select.value = String(spec.value);
    select.onchange = () => save(spec.key, select.value);
    return select;
  }
  const wrap = el("label", "flex items-center gap-2");
  const input = Object.assign(el("input", "w-24 rounded-lg bg-black/50 px-2 py-1.5 text-right font-mono text-sm ring-1 ring-white/10 disabled:opacity-60"),
    { type: "number", min: spec.min, max: spec.max, step: spec.step, value: spec.value, disabled });
  input.onchange = () => save(spec.key, input.value === "" ? null : Number(input.value));
  wrap.append(input, el("span", "w-16 text-xs text-stone-400", spec.unit || "")); // fixed width: boxes line up
  return wrap;
}

function row(spec) {
  const r = el("div", `flex flex-wrap items-start gap-3 border-l-2 py-3 pl-3 ${spec.changed ? "border-amber-400" : "border-transparent"}`);
  const text = el("div", "min-w-[14rem] flex-1");
  const [when, cls] = APPLIES[spec.applies] || [spec.applies, "bg-white/10"];
  const title = el("p", "flex flex-wrap items-center gap-2 font-semibold", spec.label);
  title.append(el("span", `rounded-full px-2 py-0.5 text-[11px] font-semibold ${cls}`, `applies: ${when}`));
  text.append(title, el("p", "mt-0.5 text-sm text-stone-400", spec.help),
    el("p", "mt-1 text-xs text-stone-500", `Default: ${show(spec, spec.default)}${spec.changed ? ` · now: ${show(spec, spec.value)}` : ""}`));
  const side = el("div", "flex items-center gap-2");
  side.append(control(spec));
  if (spec.changed && page.can_edit) {
    side.append(iconButton("↺", "Back to the default", () => reset([spec.key], `“${spec.label}”`), "px-2 py-1.5 text-sm"));
  }
  r.append(text, side);
  return r;
}

function render() {
  const q = $("filter").value.trim().toLowerCase();
  const changed = page.settings.filter((s) => s.changed);
  $("changed").textContent = changed.length ? `${changed.length} changed from the defaults` : "All settings at their defaults";
  $("reset-all").disabled = !page.can_edit || !changed.length;
  $("readonly").classList.toggle("hidden", page.can_edit);
  $("groups").replaceChildren(...page.groups.map(({ id, label }) => {
    const specs = page.settings.filter((s) => s.group === id && (!q || `${s.label} ${s.help}`.toLowerCase().includes(q)));
    if (!specs.length) return el("div", "hidden");
    const box = el("section", "panel px-4 py-2");
    const head = el("div", "flex items-center justify-between border-b border-white/10 py-2");
    head.append(el("h2", "font-display text-xl font-bold text-gold", label));
    const groupChanged = specs.filter((s) => s.changed).map((s) => s.key);
    if (groupChanged.length && page.can_edit) {
      head.append(iconButton("↺ Reset group", `Reset every setting in ${label}`, () => reset(groupChanged, `all of ${label}`), "px-3 py-1.5"));
    }
    box.append(head, ...specs.map(row));
    return box;
  }));
}

$("filter").oninput = render;
$("reset-all").onclick = () => reset(null, "every setting");
connectWS("remote", (msg) => { if (msg.type === "settings") refresh(); }); // changed in another tab
refresh();
