// DJ Co-Pilot Host Assistant drawer & Voice Input for /tv
(() => {
  const toggleBtn = $("agent-toggle");
  const drawer = $("agent-drawer");
  const closeBtn = $("agent-close");
  const clearBtn = $("agent-clear");
  const messagesEl = $("agent-messages");
  const form = $("agent-form");
  const input = $("agent-input");
  const sendBtn = $("agent-send");
  const micBtn = $("agent-mic");

  if (!toggleBtn || !drawer) return;

  let history = [];
  let isListening = false;
  let recognition = null;

  // ── Open / Close Drawer ────────────────────────────────────────────────────
  function openDrawer() {
    drawer.classList.remove("translate-x-full");
    input.focus();
  }

  function closeDrawer() {
    drawer.classList.add("translate-x-full");
  }

  toggleBtn.onclick = () => {
    if (drawer.classList.contains("translate-x-full")) openDrawer();
    else closeDrawer();
  };
  closeBtn.onclick = closeDrawer;

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !drawer.classList.contains("translate-x-full")) closeDrawer();
    if ((e.ctrlKey || e.metaKey) && (e.key === "j" || e.key === "J")) {
      e.preventDefault();
      if (drawer.classList.contains("translate-x-full")) openDrawer();
      else closeDrawer();
    }
  });

  clearBtn.onclick = () => {
    history = [];
    messagesEl.innerHTML = `
      <div class="rounded-2xl bg-white/5 p-4 border border-white/10 text-stone-300 space-y-2">
        <p class="font-semibold text-gold">👋 Chat cleared. Ready for your next command!</p>
      </div>
    `;
  };

  // ── Speech Recognition (Voice DJ) ──────────────────────────────────────────
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRec) {
    recognition = new SpeechRec();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "en-US";

    recognition.onstart = () => {
      isListening = true;
      micBtn.classList.add("bg-red-600", "text-white", "animate-pulse");
      micBtn.classList.remove("bg-white/10", "text-stone-300");
    };

    recognition.onresult = (ev) => {
      let transcript = "";
      for (let i = ev.resultIndex; i < ev.results.length; ++i) {
        transcript += ev.results[i][0].transcript;
      }
      input.value = transcript;
    };

    recognition.onend = () => {
      isListening = false;
      micBtn.classList.remove("bg-red-600", "text-white", "animate-pulse");
      micBtn.classList.add("bg-white/10", "text-stone-300");
      if (input.value.trim()) {
        form.requestSubmit();
      }
    };

    recognition.onerror = () => {
      isListening = false;
      micBtn.classList.remove("bg-red-600", "text-white", "animate-pulse");
      micBtn.classList.add("bg-white/10", "text-stone-300");
    };

    micBtn.onclick = () => {
      if (isListening) recognition.stop();
      else {
        input.value = "";
        recognition.start();
      }
    };
  } else {
    micBtn.classList.add("opacity-30", "cursor-not-allowed");
    micBtn.title = "Voice recognition not supported by this browser";
  }

  // ── Render Utilities ───────────────────────────────────────────────────────
  function scrollDown() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function appendUserMsg(text) {
    const el = document.createElement("div");
    el.className = "flex justify-end";
    el.innerHTML = `
      <div class="max-w-[85%] rounded-2xl bg-amber-500/20 border border-amber-400/30 px-4 py-2.5 text-stone-100">
        ${escapeHtml(text)}
      </div>
    `;
    messagesEl.append(el);
    scrollDown();
  }

  function appendAgentMsg(text, toolCalls = [], proposals = []) {
    const el = document.createElement("div");
    el.className = "space-y-3";

    let toolsHtml = "";
    if (toolCalls && toolCalls.length) {
      toolsHtml = `<div class="space-y-1.5">` + toolCalls.map(renderToolChip).join("") + `</div>`;
    }

    let proposalsHtml = "";
    if (proposals && proposals.length) {
      proposalsHtml = `<div class="space-y-2 mt-2">` + proposals.map(renderProposalCard).join("") + `</div>`;
    }

    el.innerHTML = `
      <div class="flex items-start gap-2.5">
        <span class="text-xl">✨</span>
        <div class="flex-1 space-y-2">
          ${toolsHtml}
          ${proposalsHtml}
          <div class="rounded-2xl bg-white/5 border border-white/10 p-4 text-stone-200 leading-relaxed">
            ${formatMarkdown(text)}
          </div>
        </div>
      </div>
    `;

    // Bind undo buttons
    el.querySelectorAll("[data-undo-path]").forEach((btn) => {
      btn.onclick = async () => {
        const path = btn.dataset.undoPath;
        btn.disabled = true;
        btn.textContent = "Reverting…";
        try {
          const res = await api("/api/agent/undo", { path });
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

    // Bind proposal actions
    el.querySelectorAll("[data-prop-id]").forEach((card) => {
      const propId = card.dataset.propId;
      const applyBtn = card.querySelector(".btn-apply-diff");
      const cancelBtn = card.querySelector(".btn-cancel-diff");

      if (applyBtn) {
        applyBtn.onclick = async () => {
          applyBtn.disabled = true;
          applyBtn.textContent = "Applying…";
          try {
            const res = await api("/api/agent/diff/apply", { proposal_id: propId });
            card.innerHTML = `<div class="rounded-xl bg-emerald-900/40 border border-emerald-500/40 p-3 text-emerald-200 font-semibold">✓ Applied to ${res.path} — server restarting cleanly with queue restored!</div>`;
          } catch (err) {
            toast(err.message || "Failed to apply diff", false);
            applyBtn.disabled = false;
            applyBtn.textContent = "✓ Apply & Restart";
          }
        };
      }

      if (cancelBtn) {
        cancelBtn.onclick = async () => {
          try {
            await api("/api/agent/diff/cancel", { proposal_id: propId });
            card.remove();
          } catch {
            card.remove();
          }
        };
      }
    });

    messagesEl.append(el);
    scrollDown();
  }

  function renderToolChip(t) {
    const name = t.name;
    const res = t.result || {};
    if (res.error) {
      return `<div class="inline-flex items-center gap-1.5 rounded-full bg-red-950/60 border border-red-500/30 px-3 py-1 text-xs text-red-300">
        <span>⚠️</span> <span>${escapeHtml(res.error)}</span>
      </div>`;
    }

    if (name === "change_setting") {
      return `<div class="inline-flex items-center gap-1.5 rounded-full bg-amber-950/60 border border-amber-500/30 px-3 py-1 text-xs text-amber-200">
        <span>⚙️</span> <span>Setting <b>${res.key}</b> → <b>${res.value}</b></span>
      </div>`;
    }
    if (name === "search_and_queue") {
      return `<div class="inline-flex items-center gap-1.5 rounded-full bg-emerald-950/60 border border-emerald-500/30 px-3 py-1 text-xs text-emerald-200">
        <span>🎵</span> <span>Queued <b>${escapeHtml(res.title)}</b> for <b>${escapeHtml(res.singer)}</b></span>
      </div>`;
    }
    if (name === "queue_action") {
      return `<div class="inline-flex items-center gap-1.5 rounded-full bg-blue-950/60 border border-blue-500/30 px-3 py-1 text-xs text-blue-200">
        <span>⏯️</span> <span>Playback action: <b>${res.status}</b></span>
      </div>`;
    }
    if (name === "edit_frontend_file") {
      return `<div class="flex items-center justify-between rounded-xl bg-purple-950/50 border border-purple-500/30 px-3 py-1.5 text-xs text-purple-200">
        <div class="flex items-center gap-1.5 truncate">
          <span>🎨</span> <span>Live edit: <b>${escapeHtml(res.path)}</b> (${escapeHtml(res.summary)})</span>
        </div>
        <button class="ml-2 font-bold underline hover:text-white" data-undo-path="${res.path}">↩ Undo</button>
      </div>`;
    }
    return `<div class="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs text-stone-300">
      <span>⚡</span> <span>${name}</span>
    </div>`;
  }

  function renderProposalCard(p) {
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
      </div>
    `;
  }

  function escapeHtml(str) {
    return String(str || "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[m]);
  }

  function formatMarkdown(text) {
    let t = escapeHtml(text);
    // Bold **text**
    t = t.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    // Code `code`
    t = t.replace(/`([^`]+)`/g, "<code class='rounded bg-black/40 px-1 py-0.5 text-amber-200 font-mono text-xs'>$1</code>");
    // Newlines
    t = t.replace(/\n/g, "<br>");
    return t;
  }

  // ── Send Handler ───────────────────────────────────────────────────────────
  form.onsubmit = async (e) => {
    e.preventDefault();
    const msg = input.value.trim();
    if (!msg) return;

    appendUserMsg(msg);
    input.value = "";
    sendBtn.disabled = true;

    // Show temporary thinking indicator
    const thinkingEl = document.createElement("div");
    thinkingEl.className = "flex items-center gap-2 text-stone-400 text-xs italic";
    thinkingEl.innerHTML = `<span>✨</span> <span>DJ Co-Pilot is thinking…</span>`;
    messagesEl.append(thinkingEl);
    scrollDown();

    try {
      const res = await api("/api/agent/chat", { message: msg, history });
      thinkingEl.remove();

      history.push({ role: "user", content: msg });
      history.push({ role: "assistant", content: res.reply || "" });
      if (history.length > 10) history = history.slice(-10);

      appendAgentMsg(res.reply || "Done!", res.tool_calls || [], res.proposals || []);
    } catch (err) {
      thinkingEl.remove();
      appendAgentMsg(`❌ Failed: ${err.message || "Could not reach AI Co-Pilot"}`, []);
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  };
})();
