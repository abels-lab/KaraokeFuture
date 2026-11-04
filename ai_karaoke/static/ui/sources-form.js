// The "Add your own link" form of the Sources block (ui/sources-panel.js): what the link is for
// (song search or lyrics page), a name, the URL template with its placeholders, Test and Save.
// The server checks every link (public http/https only, placeholders required, routers/sources.py);
// Test runs the real lookup with a sample song and shows a short result. Needs common.js.
// createSourcesForm(onSaved(page)) -> element with .edit(link) to load a saved link for changing
function createSourcesForm(onSaved) {
  const HELP = {
    songs: "A search or playlist page on a site yt-dlp can read, with {query} where the search words go, e.g. https://vimeo.com/search?q={query}",
    lyrics: "A lyrics page, with {artist}, {title} or {query} where they go; {artist_slug} / {title_slug} give “guns-n-roses” style names, e.g. https://example.com/lyrics/{artist_slug}/{title_slug}.html",
  };
  const input = "min-w-0 rounded-xl border border-white/10 bg-black/50 px-3 py-2 text-sm outline-none focus:border-amber-400";
  const box = el("form", "space-y-2 rounded-xl border border-white/10 p-3");
  box.innerHTML = `
    <p data-k="title" class="font-semibold">Add your own link</p>
    <div class="flex flex-wrap gap-2">
      <select data-k="kind" class="${input}">
        <option class="bg-stone-900" value="songs">🎵 Song search</option>
        <option class="bg-stone-900" value="lyrics">📝 Lyrics page</option>
      </select>
      <input data-k="name" maxlength="40" required placeholder="Name" class="${input} w-40 flex-1">
    </div>
    <input data-k="template" maxlength="300" required placeholder="https://…{query}…" inputmode="url"
           autocapitalize="off" autocomplete="off" spellcheck="false" class="${input} w-full font-mono">
    <p data-k="help" class="break-words text-xs text-stone-400"></p>
    <div class="flex flex-wrap items-center gap-2">
      <input data-k="query" maxlength="120" placeholder="Test song (default: Queen - Bohemian Rhapsody)" class="${input} w-full sm:w-auto sm:flex-1">
      <button data-k="test" type="button" class="rounded-xl bg-white/10 px-4 py-2 text-sm font-semibold hover:bg-white/20 disabled:opacity-30">▶ Test</button>
      <button data-k="save" type="submit" class="rounded-xl bg-amber-500 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-400 disabled:opacity-30">Save</button>
      <button data-k="cancel" type="button" class="hidden rounded-xl bg-white/10 px-4 py-2 text-sm hover:bg-white/20">Cancel</button>
    </div>
    <div data-k="result" class="hidden break-words rounded-xl bg-black/40 p-2 text-sm"></div>`;
  const part = (k) => box.querySelector(`[data-k="${k}"]`);
  let editing = null;   // id of the saved link being changed, or null when adding

  const fields = () => ({ kind: part("kind").value, name: part("name").value.trim(), template: part("template").value.trim() });
  const showHelp = () => { part("help").textContent = HELP[part("kind").value]; };

  function result(text, ok, lines = []) {
    const r = part("result");
    r.replaceChildren(el("p", ok ? "text-emerald-300" : "text-red-300", text), ...lines.map((l) => el("p", "truncate text-stone-300", `• ${l}`)));
    r.classList.remove("hidden");
  }

  function reset() {
    editing = null;
    HTMLFormElement.prototype.reset.call(box);   // box.reset is this function (exported below)
    part("title").textContent = "Add your own link";
    part("cancel").classList.add("hidden");
    part("kind").disabled = false;
    part("result").classList.add("hidden");
    showHelp();
  }

  function edit(link) {
    editing = link.id;
    part("kind").value = link.kind;
    part("name").value = link.name;
    part("template").value = link.template;
    part("title").textContent = `Change “${link.name}”`;
    part("cancel").classList.remove("hidden");
    part("result").classList.add("hidden");
    showHelp();
    box.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  async function busy(button, job) {
    button.disabled = true;
    try { await job(); } finally { button.disabled = false; }
  }

  part("test").onclick = () => busy(part("test"), async () => {
    const { kind, template } = fields();
    if (!template) { result("Type the link first", false); return; }
    result("Testing… (up to 20 s)", true);
    try {
      const res = await api("/api/sources/test", { method: "POST", body: { kind, template, query: part("query").value.trim() || null } });
      const what = kind === "songs" ? "song" : "lyric line";
      result(res.count ? `Works: ${res.count} ${what}${res.count === 1 ? "" : "s"} for “${res.query}”` : `Nothing found for “${res.query}”`,
        res.count > 0, res.sample);
    } catch (err) { result(err.message, false); }
  });

  box.onsubmit = (event) => {
    event.preventDefault();
    busy(part("save"), async () => {
      try {
        const page = await api(editing ? `/api/sources/custom/${encodeURIComponent(editing)}` : "/api/sources/custom",
          { method: editing ? "PUT" : "POST", body: fields() });
        toast(editing ? "Link changed" : "Link added");
        reset();
        onSaved(page);
      } catch (err) { result(err.message, false); }
    });
  };
  part("cancel").onclick = reset;
  part("kind").onchange = showHelp;
  showHelp();
  return Object.assign(box, { edit, reset });
}
