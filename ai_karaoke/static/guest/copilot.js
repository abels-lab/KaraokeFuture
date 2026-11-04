// Guest remote: the DJ Co-Pilot chat, a bottom sheet on phones (a dialog on bigger screens) behind
// the round ✨ button. Logged-in guests may use it when the host switched on Settings → AI Co-Pilot →
// "Guests may talk to the Co-Pilot" (agent_guest_chat, a client setting: Settings.onChange); the
// host always may. The server (routers/agent.py) checks the same and runs every tool with the
// asker's own rights. Bubbles and tool chips come from agent-render.js (createAgentRender). The chat
// lives in sessionStorage per guest, so a reload or a trip to another tab keeps it.
// Needs common.js, auth.js, agent-render.js, ui/popup.js, remote-login.js.
// GuestCopilot.open(); the ✨ button opens it through guest/app.js (data-open="copilot").
const GuestCopilot = (() => {
  const KEEP = 40, TURNS = 10;   // bubbles kept for the session; turns of history sent along
  const fab = Object.assign(el("button", "copilot-fab btn-gold tap hidden", "✨"), { type: "button", title: "Ask the DJ Co-Pilot" });
  fab.dataset.open = "copilot";
  fab.setAttribute("aria-label", "Ask the DJ Co-Pilot");
  document.body.append(fab);

  const root = el("div", "copilot flex flex-col gap-2");
  const box = el("div", "copilot-log space-y-3 pr-1");
  box.setAttribute("aria-live", "polite");
  const form = el("form", "flex items-center gap-2");
  const input = Object.assign(el("input", "min-w-0 flex-1 rounded-xl border border-white/10 bg-black/50 px-3 py-2.5 text-base outline-none focus:border-amber-400"),
    { type: "text", maxLength: 1000, placeholder: "Ask for a song…", autocomplete: "off", enterKeyHint: "send" });
  input.setAttribute("aria-label", "Message to the DJ Co-Pilot");
  const send = Object.assign(el("button", "btn-gold tap shrink-0 rounded-xl px-4 py-2.5 text-sm font-bold", "Send"), { type: "submit" });
  const status = el("p", "min-h-[1rem] text-xs text-stone-400");
  form.append(input, send);
  root.append(box, status, form);
  const render = createAgentRender(box);

  let log = [], history = [], key = "", busy = false, popup = null;
  const allowed = () => Boolean(Auth.me.admin || Settings.get("agent_guest_chat", false));
  const loggedIn = () => Boolean(Auth.me.admin || Auth.me.guest);
  const storageKey = () => `copilot-chat:${Auth.me.guest ? `guest-${Auth.me.guest.id}` : Auth.me.admin ? "host" : "nobody"}`;
  const load = (k) => { try { return JSON.parse(sessionStorage.getItem(k)) || {}; } catch { return {}; } };
  const save = () => { try { sessionStorage.setItem(key, JSON.stringify({ log, history })); } catch { /* private mode */ } };
  const scrollDown = () => { box.scrollTop = box.scrollHeight; };
  const toLogin = () => { Popup.closeAll(); setTimeout(GuestLogin.focus, 50); };

  function intro() {
    const style = Auth.me.admin || Settings.get("agent_guest_style", false);
    const node = el("div", "space-y-1 rounded-2xl border border-white/10 bg-white/5 p-3 text-sm text-stone-300");
    node.append(el("p", "font-semibold text-gold", "👋 Hi! I'm the DJ Co-Pilot."),
      el("p", "", `Ask me in your own words: "queue Bohemian Rhapsody for me", "when am I up?", "skip my song"${style ? ', "make the party neon"' : ""}.`));
    return node;
  }

  function paintLog() {
    box.replaceChildren(intro());
    log.forEach((m) => (m.who === "user" ? render.user(m.text) : render.agent(m.text, m.tools)));
    scrollDown();
  }

  // A friendly line that isn't part of the conversation (not kept, not sent back to the model)
  function note(text, action = null) {
    const node = el("div", "flex flex-wrap items-center gap-2 rounded-xl border border-amber-400/30 bg-amber-950/50 px-3 py-2 text-sm text-amber-100");
    node.append(el("span", "min-w-0 flex-1", text));
    if (action) node.append(Object.assign(el("button", "btn-gold tap rounded-lg px-3 py-1 text-xs font-bold", action[0]), { type: "button", onclick: action[1] }));
    box.append(node);
    scrollDown();
  }

  const FRIENDLY = {
    401: ["🔑 Log in with your singer name first, then ask me again.", ["Log in", toLogin]],
    403: ["🔒 The host hasn't opened the DJ Co-Pilot to guests right now."],
    429: ["⏳ Easy there! One message every few seconds, then try again."],
  };

  function paint() {
    const k = storageKey();
    if (k !== key) {   // logged in, out or as someone else: their own chat
      key = k;
      ({ log = [], history = [] } = load(k));
      paintLog();
    }
    fab.classList.toggle("hidden", !allowed());
    document.body.classList.toggle("copilot-on", allowed());
    const why = !allowed() ? "🔒 The host has closed the chat for now." : !loggedIn() ? "🔑 Log in with your singer name to chat." : "";
    status.textContent = why || (busy ? "✨ Thinking…" : Auth.me.admin ? "" : "It can queue songs for you and manage your own songs.");
    status.classList.toggle("text-amber-200", Boolean(why));
    input.disabled = Boolean(why);
    send.disabled = Boolean(why) || busy;
    send.textContent = busy ? "…" : "Send";
  }
  Auth.onChange(paint);
  Settings.onChange(paint);
  paint();

  form.onsubmit = async (e) => {
    e.preventDefault();
    const msg = input.value.trim();
    if (!msg || busy) return;
    busy = true;
    paint();
    input.value = "";
    const mine = render.user(msg);
    const thinking = render.thinking();
    try {
      const res = await api("/api/agent/chat", { method: "POST", body: { message: msg, history } });
      const reply = res.reply || "Done!";
      render.agent(reply, res.tool_calls || []);
      log = [...log, { who: "user", text: msg }, { who: "agent", text: reply, tools: res.tool_calls || [] }].slice(-KEEP);
      history = [...history, { role: "user", content: msg }, { role: "assistant", content: res.reply || "" }].slice(-TURNS);
      save();
    } catch (err) {
      mine.remove();   // not sent: the words go back into the box to try again
      if (!input.value) input.value = msg;
      const [text, action] = FRIENDLY[err.status] || [`😕 The DJ Co-Pilot couldn't answer: ${err.message || "try again"}.`];
      note(text, action);
      if (err.status === 401) Auth.load();
      if (err.status === 403) Settings.load();
    } finally {
      thinking.remove();
      busy = false;
      paint();
      if (popup && !matchMedia("(pointer: coarse)").matches) input.focus();
    }
  };

  function open() {
    if (Popup.depth) return;
    paint();
    popup = Popup.open({ title: "✨ DJ Co-Pilot", content: root, size: "md", onClose: () => { popup = null; } });
    scrollDown();
    if (!input.disabled && !matchMedia("(pointer: coarse)").matches) input.focus();
  }

  return { open };
})();
