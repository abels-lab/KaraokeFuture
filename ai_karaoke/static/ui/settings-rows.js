// One line of the settings panel (ui/settings-panel.js): the setting's name, its "applies"
// badge, help text, default, the right control for its kind (switch, choice, text, number with
// unit) and its own ↺ reset. The control calls back; saving and resetting live in the panel.
// Needs common.js (el, iconButton).
// SettingsRows.row(spec, canEdit, { save(key, value), reset(keys, what) }) -> element
const SettingsRows = (() => {
  const APPLIES = { "immediately": ["now", "bg-emerald-900/70 text-emerald-200"],
                    "next song": ["next song", "bg-sky-900/70 text-sky-200"],
                    "next processed song": ["new or rebuilt songs", "bg-amber-900/70 text-amber-200"] };

  // A value as people read it: on/off, the choice's label, or the number with its unit
  const show = (spec, value) => {
    if (spec.kind === "bool") return value ? "on" : "off";
    if (spec.kind === "choice") return (spec.choices.find(([v]) => String(v) === String(value)) || [value, value])[1];
    return `${value}${spec.unit ? ` ${spec.unit}` : ""}`;
  };

  function control(spec, canEdit, save) {
    const disabled = !canEdit;
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
    if (spec.kind === "text") {   // custom CSS gets a code box, saved when it loses focus
      const input = Object.assign(el(spec.css ? "textarea" : "input", spec.css
        ? "h-32 w-full min-w-[16rem] rounded-lg bg-black/50 px-2 py-1.5 font-mono text-xs ring-1 ring-white/10 disabled:opacity-60"
        : "w-56 rounded-lg bg-black/50 px-2 py-1.5 text-sm ring-1 ring-white/10 disabled:opacity-60"),
        { maxLength: spec.max_len, value: spec.value, disabled });
      input.onchange = () => save(spec.key, input.value);
      return input;
    }
    const wrap = el("label", "flex items-center gap-2");
    const input = Object.assign(el("input", "w-24 rounded-lg bg-black/50 px-2 py-1.5 text-right font-mono text-sm ring-1 ring-white/10 disabled:opacity-60"),
      { type: "number", min: spec.min, max: spec.max, step: spec.step, value: spec.value, disabled });
    input.onchange = () => save(spec.key, input.value === "" ? null : Number(input.value));
    wrap.append(input, el("span", "w-16 text-xs text-stone-400", spec.unit || "")); // fixed width: boxes line up
    return wrap;
  }

  function row(spec, canEdit, { save, reset }) {
    const r = el("div", `flex flex-wrap items-start gap-3 border-l-2 py-3 pl-3 ${spec.changed ? "border-amber-400" : "border-transparent"}`);
    r.dataset.key = spec.key;
    const text = el("div", "min-w-[14rem] flex-1");
    const [when, cls] = APPLIES[spec.applies] || [spec.applies, "bg-white/10"];
    const title = el("p", "flex flex-wrap items-center gap-2 font-semibold", spec.label);
    title.append(el("span", `rounded-full px-2 py-0.5 text-[11px] font-semibold ${cls}`, `applies: ${when}`));
    text.append(title, el("p", "mt-0.5 text-sm text-stone-400", spec.help),
      el("p", "mt-1 text-xs text-stone-500", `Default: ${show(spec, spec.default)}${spec.changed ? ` · now: ${show(spec, spec.value)}` : ""}`));
    const side = el("div", "flex items-center gap-2");
    side.append(control(spec, canEdit, save));
    if (spec.changed && canEdit) {
      side.append(iconButton("↺", "Back to the default", () => reset([spec.key], `“${spec.label}”`), "px-2 py-1.5 text-sm"));
    }
    r.append(text, side);
    return r;
  }

  return { row, show };
})();
