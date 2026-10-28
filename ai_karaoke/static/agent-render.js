// DJ Co-Pilot chat bubbles: the host's message, the Co-Pilot's answer (a little markdown), chips
// for the tools it ran (setting changed, song queued, layout customized, live file edit with
// ↩ Undo) and cards for proposed backend changes (Apply & Restart / Discard). Split from agent.js,
// which sends the messages. Needs common.js (api, toast) and #agent-messages (host/markup-left.js).
// AgentRender = { user(text), agent(text, toolCalls, proposals), thinking() -> element, clear() }
const AgentRender = (() => {
  const box = $("agent-messages");
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
    if (t.name === "change_setting") return chip("bg-amber-950/60 border border-amber-500/30 text-amber-200", "⚙️", `Setting <b>${res.key}</b> → <b>${res.value}</b>`);
    if (t.name === "search_and_queue") return chip("bg-emerald-950/60 border border-emerald-500/30 text-emerald-200", "🎵", `Queued <b>${escapeHtml(res.title)}</b> for <b>${escapeHtml(res.singer)}</b>`);
    if (t.name === "queue_action") return chip("bg-blue-950/60 border border-blue-500/30 text-blue-200", "⏯️", `Playback action: <b>${res.status}</b>`);
    if (t.name === "customize_control_panel") {
      const desc = { add_button: "Added button to Control Panel", remove_button: "Removed button from Control Panel",
                     reset: "Reset Control Panel layout" }[res.action] || "Control Panel updated";
      return chip("bg-indigo-950/60 border border-indigo-500/30 text-indigo-200", "🎛️", desc);
    }
    if (t.name === "edit_frontend_file") {
      return `<div class="flex items-center justify-between rounded-xl bg-purple-950/50 border border-purple-500/30 px-3 py-1.5 text-xs text-purple-200">
        <div class="flex items-center gap-1.5 truncate">
          <span>🎨</span> <span>Live edit: <b>${escapeHtml(res.path)}</b> (${escapeHtml(res.summary)})</span>
        </div>
        <button class="ml-2 font-bold underline hover:text-white" data-undo-path="${res.path}">↩ Undo</button>
      </div>`;
    }
    return chip("bg-white/10 text-stone-300", "⚡", t.name);
  }

  function proposalCard(p) {
    const lines = (p.diff || "").split("\n").map((l) => {
      if (l.startsWith("+") && !l.startsWith("+++")) return `<span class="text-emerald-400">${escapeHtml(l)}</span>`;
      if (l.startsWith("-") && !l.startsWith("---")) return `<span class="text-red-400">${escapeHtml(l)}</span>`;
      return `<span class="text-stone-400">${escapeHtml(l)}</span>`;
    }).join("\n");
    return `
      <div class="rounded-xl border border-amber-500/40 bg-stone-900/90 p-3 space-y-2 text-xs" data-prop-id="${p.proposal_id}">
        <div class="flex items-center justify-between">
          <span class="font-bold text-amber-300">📝 Proposed Backend Change: ${escapeHtml(p.path)}</span>
          <span class="text-[10px] text-stone-400 font-mono">${p.proposal_id}</span>
        </div>
        <p class="text-stone-300">${escapeHtml(p.summary)}</p>
        <pre class="max-h-40 overflow-x-auto rounded bg-black/60 p-2 font-mono text-[11px] leading-relaxed scrollbar-none">${lines}</pre>
        <div class="flex items-center justify-end gap-2 pt-1">
          <button class="btn-cancel-diff px-3 py-1 rounded bg-white/10 hover:bg-white/20 text-stone-300 font-semibold">✕ Discard</button>
          <button class="btn-apply-diff px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold shadow">✓ Apply & Restart</button>
        </div>
      </div>`;
  }

  // ↩ Undo on a live file edit, Apply / Discard on a proposed backend change
  function bindActions(node) {
    node.querySelectorAll("[data-undo-path]").forEach((btn) => {
      btn.onclick = async () => {
        const path = btn.dataset.undoPath;
        btn.disabled = true;
        btn.textContent = "Reverting…";
        try {
          const res = await api("/api/agent/undo", { method: "POST", body: { path } });
          if (res.status === "undone") {
            btn.replaceWith(document.createTextNode("✓ Reverted"));
            toast(`Reverted ${path}`, true);
          }
        } catch (err) {
          toast(err.message || "Failed to revert", false);
          btn.disabled = false;
          btn.textContent = "↩ Undo";
        }
      };
    });
    node.querySelectorAll("[data-prop-id]").forEach((card) => {
      const body = { proposal_id: card.dataset.propId };
      const applyBtn = card.querySelector(".btn-apply-diff");
      applyBtn.onclick = async () => {
        applyBtn.disabled = true;
        applyBtn.textContent = "Applying…";
        try {
          const res = await api("/api/agent/diff/apply", { method: "POST", body });
          card.innerHTML = `<div class="rounded-xl bg-emerald-900/40 border border-emerald-500/40 p-3 text-emerald-200 font-semibold">✓ Applied to ${res.path} — server restarting cleanly with queue restored!</div>`;
        } catch (err) {
          toast(err.message || "Failed to apply diff", false);
          applyBtn.disabled = false;
          applyBtn.textContent = "✓ Apply & Restart";
        }
      };
      card.querySelector(".btn-cancel-diff").onclick = () =>
        api("/api/agent/diff/cancel", { method: "POST", body }).catch(() => {}).then(() => card.remove());
    });
  }

  function user(text) {
    const node = el("div", "flex justify-end");
    node.innerHTML = `<div class="max-w-[85%] rounded-2xl bg-amber-500/20 border border-amber-400/30 px-4 py-2.5 text-stone-100">${escapeHtml(text)}</div>`;
    box.append(node);
    scrollDown();
  }

  function agent(text, toolCalls = [], proposals = []) {
    const node = el("div", "space-y-3");
    const tools = toolCalls?.length ? `<div class="space-y-1.5">${toolCalls.map(toolChip).join("")}</div>` : "";
    const props = proposals?.length ? `<div class="space-y-2 mt-2">${proposals.map(proposalCard).join("")}</div>` : "";
    node.innerHTML = `
      <div class="flex items-start gap-2.5">
        <span class="text-xl">✨</span>
        <div class="flex-1 space-y-2">${tools}${props}
          <div class="rounded-2xl bg-white/5 border border-white/10 p-4 text-stone-200 leading-relaxed">${formatMarkdown(text)}</div>
        </div>
      </div>`;
    bindActions(node);
    box.append(node);
    scrollDown();
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
})();
