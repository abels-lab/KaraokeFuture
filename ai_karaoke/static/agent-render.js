// DJ Co-Pilot chat bubbles: the host's message, the Co-Pilot's answer (a little markdown) and chips
// for the tools it ran (setting changed, song queued, style changed, layout customized). Split from
// agent.js, which sends the messages; the guest remote's chat (guest/copilot.js) draws with it too.
// Needs common.js. createAgentRender(box) draws into that element; AgentRender draws into the host's
// #agent-messages (host/markup-left.js), and only once a page that has it calls one of its methods.
// { user(text) -> element, agent(text, toolCalls) -> element, thinking() -> element, clear() }
function createAgentRender(box) {
  const escapeHtml = (str) => String(str || "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[m]);
  const formatMarkdown = (text) => escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code class='rounded bg-black/40 px-1 py-0.5 text-amber-200 font-mono text-xs'>$1</code>")
    .replace(/\n/g, "<br>");
  const scrollDown = () => { box.scrollTop = box.scrollHeight; };
  const chip = (colors, icon, html) => `<div class="inline-flex items-center gap-1.5 rounded-full ${colors} px-3 py-1 text-xs"><span>${icon}</span> <span>${html}</span></div>`;

  function toolChip(t) {
    const res = t.result || {};
    if (res.error) return chip("bg-red-950/60 border border-red-500/30 text-red-300", "⚠️", escapeHtml(res.error));
    if (t.name === "change_setting") return chip("bg-amber-950/60 border border-amber-500/30 text-amber-200", "⚙️", `Setting <b>${escapeHtml(res.key)}</b> → <b>${escapeHtml(res.value)}</b>`);
    if (t.name === "search_and_queue") return chip("bg-emerald-950/60 border border-emerald-500/30 text-emerald-200", "🎵", `Queued <b>${escapeHtml(res.title)}</b> for <b>${escapeHtml(res.singer)}</b>`);
    if (t.name === "queue_action") return chip("bg-blue-950/60 border border-blue-500/30 text-blue-200", "⏯️", `Playback action: <b>${escapeHtml(res.status)}</b>`);
    if (t.name === "customize_control_panel") {
      const desc = { add_button: "Added button to Control Panel", remove_button: "Removed button from Control Panel",
                     reset: "Reset Control Panel layout" }[res.action] || "Control Panel updated";
      return chip("bg-indigo-950/60 border border-indigo-500/30 text-indigo-200", "🎛️", desc);
    }
    if (t.name === "set_style") {
      const what = Object.keys(res.changed || {}).map((k) => k.replace(/^style_/, "").replace(/_/g, " ")).join(", ");
      return chip("bg-fuchsia-950/60 border border-fuchsia-500/30 text-fuchsia-200", "🎨",
        res.reset ? `Style reset${what ? `, then ${escapeHtml(what)}` : ""}` : `Style: <b>${escapeHtml(what)}</b>`);
    }
    return chip("bg-white/10 text-stone-300", "⚡", t.name);
  }

  function user(text) {
    const node = el("div", "flex justify-end");
    node.innerHTML = `<div class="max-w-[85%] rounded-2xl bg-amber-500/20 border border-amber-400/30 px-4 py-2.5 text-stone-100">${escapeHtml(text)}</div>`;
    box.append(node);
    scrollDown();
    return node;
  }

  function agent(text, toolCalls = []) {
    const node = el("div", "space-y-3");
    const tools = toolCalls?.length ? `<div class="space-y-1.5">${toolCalls.map(toolChip).join("")}</div>` : "";
    node.innerHTML = `
      <div class="flex items-start gap-2.5">
        <span class="text-xl">✨</span>
        <div class="min-w-0 flex-1 space-y-2">${tools}
          <div class="rounded-2xl bg-white/5 border border-white/10 p-4 text-stone-200 leading-relaxed">${formatMarkdown(text)}</div>
        </div>
      </div>`;
    box.append(node);
    scrollDown();
    return node;
  }

  function thinking() {
    const node = el("div", "flex items-center gap-2 text-stone-400 text-xs italic");
    node.innerHTML = "<span>✨</span> <span>DJ Co-Pilot is thinking…</span>";
    box.append(node);
    scrollDown();
    return node;
  }

  const clear = () => {
    box.innerHTML = `<div class="rounded-2xl bg-white/5 p-4 border border-white/10 text-stone-300 space-y-2">
      <p class="font-semibold text-gold">👋 Chat cleared. Ready for your next command!</p></div>`;
  };
  return { user, agent, thinking, clear };
}
const AgentRender = createAgentRender($("agent-messages"));
