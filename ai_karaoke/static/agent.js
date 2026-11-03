// DJ Co-Pilot: the host's AI assistant in the control panel (left column on the laptop, a
// slide-over drawer on tablets, its own tab on phones — host/host.css). Typed or spoken
// (agent-voice.js) messages go to /api/agent/chat with the last few turns of history; the answer,
// the tools it ran and any proposed backend change are drawn by agent-render.js. Ctrl+J focuses
// the box (host/keys.js). Its UI tools (customize_control_panel) arrive as WS "ui_config" → TvUi.
// The projector's chat overlay (screen.js) gets each turn from the server (WS "chat" to screens);
// No extra BroadcastChannel copy here: the projector would show every message twice.
// Needs common.js, agent-render.js, agent-voice.js and the markup (host/markup-left.js).
(() => {
  const form = $("agent-form"), input = $("agent-input"), sendBtn = $("agent-send");
  if (!$("agent-drawer") || !input) return;
  let history = [];

  $("agent-toggle").onclick = () => input.focus();   // legacy hidden button: still focuses the chat
  $("agent-clear").onclick = () => { history = []; AgentRender.clear(); };
  AgentVoice.init({ button: $("agent-mic"), input, form });

  form.onsubmit = async (e) => {
    e.preventDefault();
    const msg = input.value.trim();
    if (!msg) return;
    AgentRender.user(msg);
    input.value = "";
    sendBtn.disabled = true;
    const thinking = AgentRender.thinking();
    try {
      const res = await api("/api/agent/chat", { method: "POST", body: { message: msg, history } });
      thinking.remove();
      history.push({ role: "user", content: msg });
      history.push({ role: "assistant", content: res.reply || "" });
      if (history.length > 10) history = history.slice(-10);
      AgentRender.agent(res.reply || "Done!", res.tool_calls || [], res.proposals || []);
    } catch (err) {
      thinking.remove();
      AgentRender.agent(`❌ Failed: ${err.message || "Could not reach AI Co-Pilot"}`, []);
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  };
})();
