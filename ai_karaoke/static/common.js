// Shared by every page: DOM + formatting helpers, API calls, WebSocket, toasts, icons (queue rows: ui/queue-rows.js).
const $ = (id) => document.getElementById(id);
const el = (tag, className = "", text = "") => Object.assign(document.createElement(tag), { className, textContent: text });
const fmt = (s) => Number.isFinite(s) && s >= 0 ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "0:00";
// Fallback picture when the server sent none: YouTube ids have a fixed thumbnail URL ("sc_" ids don't)
const thumbFor = (id) => (/^[\w-]{11}$/.test(id || "") ? `https://i.ytimg.com/vi/${id}/hqdefault.jpg` : "/static/img/microphone.png");
// "Ann & Bob" when a second singer joined a battle song (entry.partner), else just the singer
const singers = (e) => (e?.partner ? `${e.singer} & ${e.partner.name}` : e?.singer || "");
// A "state" whose now-playing song has no audio yet (still downloading / separating) can't play:
// show it waiting at the front of the queue, so the loading screen tracks it until media arrives
const untilPlayable = (s) => (s.now_playing && !s.now_playing.media
  ? { ...s, now_playing: null, queue: [s.now_playing, ...(s.queue || [])] } : s);
const store = (k, v) => { try { return v === undefined ? localStorage.getItem(k) : localStorage.setItem(k, v); } catch { return null; } };

const STATUS = {
  waiting: ["Waiting", "bg-stone-600"], queued: ["Queued", "bg-stone-600"],
  downloading: ["Downloading", "bg-sky-800"], separating: ["Removing vocals", "bg-amber-700"],
  aligning: ["Syncing lyrics", "bg-orange-700"], melody: ["Reading the melody", "bg-orange-800"],
  ready: ["Ready", "bg-emerald-700"], error: ["Failed", "bg-red-800"],
};
const LYRICS_SOURCE = {
  synced: ["🌐 Online lyrics", "bg-emerald-900/70 text-emerald-200"],
  user: ["✍️ Pasted lyrics", "bg-amber-900/70 text-amber-200"],
  transcribed: ["👂 Transcribed", "bg-red-950/80 text-red-200"],
  ultrastar: ["🎤 UltraStar", "bg-sky-900/70 text-sky-200"],
};

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method, headers: body ? { "Content-Type": "application/json" } : {}, body: body && JSON.stringify(body),
  }).catch(() => null);
  if (!res) throw new Error("Server unreachable");
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map((x) => x.msg).join(", ") : d || `Error ${res.status}`);
  }
  return data;
}

// Browser-side settings (singing game, playback) from the Settings page; reloaded on every change.
// Settings.get(key, fallback) works before they arrive; onChange(fn) runs after each (re)load.
const Settings = (() => {
  let values = {}, ready = null;
  const listeners = [];
  const load = () => (ready = api("/api/settings/client")
    .then((v) => { values = v; listeners.forEach((fn) => fn(v)); return v; })
    .catch(() => values));
  load();
  return { load, get ready() { return ready; }, get: (key, fallback) => values[key] ?? fallback,
           onChange: (fn) => listeners.push(fn) };
})();

// Auto-reconnecting WebSocket; returns send(msg)
function connectWS(role, onMessage, onOpen) {
  let ws = null;
  const send = (msg) => ws && ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(msg));
  const open = () => {
    ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws?role=${role}`);
    ws.onopen = () => {
      onOpen?.();
    };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "settings") Settings.load();   // changed on the Settings page
      if (msg.type === "auth" && typeof Auth !== "undefined") Auth.load();   // party wiped / PIN changed
      if (msg.type === "denied") toast(msg.message, false);
      if (msg.type === "ui_config") {
        window.TvUi?.applyConfig?.(msg.config);
        return;
      }
      if (msg.type === "hot_css") {
        document.querySelectorAll('link[rel="stylesheet"]').forEach((link) => {
          const url = new URL(link.href);
          url.searchParams.set("_v", Date.now());
          link.href = url.toString();
        });
        return;
      }
      if (msg.type === "reload") {
        const isPlaying = (typeof inst !== "undefined" && inst && !inst.paused)
          || (typeof clock !== "undefined" && clock && !clock.paused && clock.uid);
        if (isPlaying) {
          window.__pendingReload = true;
          toast("Update ready — auto-refreshing after this song (click to reload now)", true, () => location.reload());
          return;
        }
        location.reload();
        return;
      }
      onMessage(msg);
    };
    ws.onclose = () => setTimeout(open, 1000);
  };
  open();
  setInterval(() => send({ type: "ping" }), 20000);
  return send;
}

let toastTimer = null;
function toast(text, ok = true, onClick = null) {
  let t = $("toast");
  if (!t) {
    t = el("div", "fixed inset-x-4 bottom-6 z-50 mx-auto max-w-md rounded-xl px-4 py-3 text-center font-semibold shadow-2xl transition duration-300");
    t.id = "toast";
    document.body.append(t);
  }
  t.textContent = text;
  t.classList.toggle("bg-emerald-700", ok);
  t.classList.toggle("bg-red-800", !ok);
  if (onClick) {
    t.classList.remove("pointer-events-none");
    t.classList.add("cursor-pointer");
    t.onclick = onClick;
  } else {
    t.classList.add("pointer-events-none");
    t.classList.remove("cursor-pointer");
    t.onclick = null;
  }
  t.style.opacity = "1"; t.style.transform = "none";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.style.opacity = "0"; t.style.transform = "translateY(1.5rem)"; }, 3500);
}
const fail = (err) => toast(err.message, false);

function iconButton(label, title, onclick, extra = "") {
  const b = el("button", `shrink-0 rounded-lg bg-white/10 px-2 py-1 text-xs hover:bg-white/20 active:bg-white/30 disabled:opacity-25 transition ${extra}`, label);
  b.title = title;
  b.onclick = onclick;
  return b;
}

// Transport icons as inline SVG (emoji like ⏪ render as blue tiles on Windows)
const ICON = {
  play: "M8 5v14l11-7z", pause: "M6 5h4v14H6zM14 5h4v14h-4z", restart: "M6 6h2v12H6zM9.5 12 18 6v12z",
  skip: "M16 6h2v12h-2zM6 18l8.5-6L6 6z", next: "M6 18l8.5-6L6 6v12zM16 6h2v12h-2z",
  prev: "M6 6h2v12H6zm3.5 6 8.5 6V6z", back: "M11 18V6l-8.5 6zM20 18V6l-8.5 6z", fwd: "M13 6v12l8.5-6zM4 18l8.5-6L4 6z",
};
const svg = (name) => `<svg viewBox="0 0 24 24" class="h-5 w-5 fill-current" aria-hidden="true"><path d="${ICON[name]}"/></svg>`;
const setIcon = (btn, name) => { btn.querySelector("svg")?.remove(); btn.insertAdjacentHTML("afterbegin", svg(name)); };
document.querySelectorAll("[data-icon]").forEach((b) => setIcon(b, b.dataset.icon));
