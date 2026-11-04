// A themed "are you sure?" dialog instead of the browser's confirm(): a small popup (ui/popup.js)
// with a plain question, buttons that say what they do, an optional checkbox ("also forget the
// pasted lyrics") and, for the few actions nothing can bring back, a word to type first.
// Esc, Back, ✕ and a tap beside it all mean "no". Cancel comes first, so Enter never deletes.
// Needs common.js (el) and ui/popup.js.
// await Confirm.ask({ title, message, ok, cancel, danger = true, check, type })
//   -> false, or { checked } (truthy) when confirmed. check: checkbox label; type: word to type.
const Confirm = (() => {
  function ask({ title = "Are you sure?", message = "", ok = "OK", cancel = "Cancel", danger = true, check = null, type = null } = {}) {
    return new Promise((resolve) => {
      let answer = false;
      const body = el("div", "space-y-4");
      for (const line of String(message).split("\n").filter(Boolean)) body.append(el("p", "text-sm text-stone-300", line));

      let box = null;
      if (check) {
        const label = el("label", "flex cursor-pointer items-center gap-2 text-sm text-stone-200");
        box = Object.assign(el("input", "h-5 w-5 accent-amber-400"), { type: "checkbox" });
        label.append(box, el("span", "", check));
        body.append(label);
      }

      let typed = null;
      if (type) {
        const label = el("label", "block space-y-1.5 text-sm text-stone-300");
        label.append(el("span", "", "Type "), el("b", "font-mono text-amber-300", type), el("span", "", " to confirm"));
        typed = Object.assign(el("input", "w-full rounded-xl border border-white/10 bg-black/50 px-3 py-2 font-mono uppercase outline-none focus:border-amber-400"),
          { type: "text", autocomplete: "off", spellcheck: false });
        typed.setAttribute("autocapitalize", "characters");
        label.append(typed);
        body.append(label);
      }

      const row = el("div", "flex flex-wrap justify-end gap-2 pt-1");
      const no = Object.assign(el("button", "tap rounded-xl bg-white/10 px-4 py-2 text-sm font-semibold hover:bg-white/20", cancel), { type: "button" });
      const yes = Object.assign(el("button", `tap rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-30 ${danger
        ? "bg-red-800 text-white hover:bg-red-700" : "btn-gold"}`, ok), { type: "button" });
      row.append(no, yes);
      body.append(row);

      const valid = () => !typed || typed.value.trim().toUpperCase() === type.toUpperCase();
      yes.disabled = !valid();
      const popup = Popup.open({ title, content: body, size: "sm", onClose: () => resolve(answer) });
      no.onclick = () => popup.close();
      yes.onclick = () => {
        if (!valid()) return;
        answer = { checked: Boolean(box?.checked) };
        popup.close();
      };
      if (typed) {
        typed.oninput = () => { yes.disabled = !valid(); };
        typed.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); yes.click(); } };
        if (!matchMedia("(pointer: coarse)").matches) typed.focus();
      }
    });
  }

  return { ask };
})();
