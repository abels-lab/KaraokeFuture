// Projector chat overlay: the host's and DJ Co-Pilot's messages pop up top-left for a few seconds
// (Settings screen_chat_enabled / _duration / _size / _opacity). Needs common.js (Settings, $).
// createScreenChat(root) -> { addMessage({id, sender, name, text}) }
function createScreenChat(root) {
  if (!root) return { addMessage: () => {} };
  const messagesEl = $("screen-chat-messages") || root;
  const seenIds = new Set();
  let hideTimer = null;
  const MAX_MESSAGES = 4;

  function escapeText(str) {
    return String(str || "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[m]);
  }

  function formatText(text) {
    if (!text) return "";
    let t = escapeText(text);
    t = t.replace(/\*\*(.*?)\*\*/g, "<strong class='text-white font-semibold'>$1</strong>");
    t = t.replace(/`([^`]+)`/g, "<code class='rounded bg-black/50 px-1 py-0.5 text-amber-200 font-mono text-[10px]'>$1</code>");
    t = t.replace(/\n+/g, "<br>");
    return t;
  }

  function getOpacityVal() {
    const raw = Settings.get("screen_chat_opacity", 85);
    return Math.max(0.1, Math.min(1.0, (Number(raw) || 85) / 100));
  }

  function getSizeConfig() {
    const size = Settings.get("screen_chat_size", "small");
    if (size === "large") {
      return { maxW: "max-w-[32rem]", badgeClass: "text-[14px]", bodyClass: "text-[16px]" };
    }
    if (size === "medium") {
      return { maxW: "max-w-[27rem]", badgeClass: "text-[12px]", bodyClass: "text-[14px]" };
    }
    return { maxW: "max-w-[22rem]", badgeClass: "text-[11px]", bodyClass: "text-[12px]" };
  }

  function applySettings() {
    const enabled = Settings.get("screen_chat_enabled", true);
    if (!enabled) {
      root.style.opacity = "0";
      root.style.pointerEvents = "none";
      if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    }
    const { maxW, badgeClass, bodyClass } = getSizeConfig();
    root.classList.remove("max-w-[22rem]", "max-w-[27rem]", "max-w-[32rem]");
    root.classList.add(maxW);

    const opacityVal = getOpacityVal();
    messagesEl.querySelectorAll(".screen-chat-card").forEach((card) => {
      card.style.backgroundColor = `rgba(18, 18, 22, ${opacityVal})`;
      const badge = card.querySelector(".chat-badge");
      if (badge) badge.className = badge.className.replace(/text-\[\d+px\]/, badgeClass);
      const body = card.querySelector(".chat-body");
      if (body) body.className = body.className.replace(/text-\[\d+px\]/, bodyClass);
    });
  }

  Settings.onChange?.(applySettings);
  applySettings();

  function addMessage(msg) {
    if (!msg || !msg.text) return;
    if (!Settings.get("screen_chat_enabled", true)) return;

    const dedupKey = msg.id || `${msg.sender}:${String(msg.text).slice(0, 40)}`;
    if (seenIds.has(dedupKey)) return;
    seenIds.add(dedupKey);
    if (seenIds.size > 50) {
      const first = seenIds.values().next().value;
      seenIds.delete(first);
    }

    const isAgent = msg.sender === "agent";
    const senderName = isAgent ? "DJ Co-Pilot" : (msg.name || "Host");
    const badgeColor = isAgent ? "text-purple-300" : "text-amber-300";
    const borderColor = isAgent ? "border-purple-500/40" : "border-amber-500/40";
    const icon = isAgent ? "✨" : "🎤";

    const { maxW, badgeClass, bodyClass } = getSizeConfig();
    root.classList.remove("max-w-[22rem]", "max-w-[27rem]", "max-w-[32rem]");
    root.classList.add(maxW);

    const opacityVal = getOpacityVal();
    const card = document.createElement("div");
    card.className = `screen-chat-card rounded-xl backdrop-blur-md border ${borderColor} px-3 py-2 shadow-2xl transition-all duration-300`;
    card.style.backgroundColor = `rgba(18, 18, 22, ${opacityVal})`;
    card.innerHTML = `
      <div class="chat-badge flex items-center gap-1.5 ${badgeColor} ${badgeClass} font-bold uppercase tracking-wider">
        <span>${icon}</span>
        <span>${escapeText(senderName)}</span>
      </div>
      <div class="chat-body mt-0.5 ${bodyClass} leading-snug text-stone-200 break-words font-normal">
        ${formatText(msg.text)}
      </div>
    `;

    messagesEl.appendChild(card);

    while (messagesEl.children.length > MAX_MESSAGES) {
      messagesEl.firstElementChild.remove();
    }

    root.style.opacity = "1";
    root.style.pointerEvents = "auto";

    const durationSec = Math.max(1, Number(Settings.get("screen_chat_duration", 7)) || 7);

    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      root.style.opacity = "0";
      root.style.pointerEvents = "none";
    }, durationSec * 1000);
  }

  return { addMessage };
}
