// Shared by every page: DOM + formatting helpers, API calls, WebSocket, toasts, queue rows.
const $ = (id) => document.getElementById(id);
const el = (tag, className = "", text = "") => Object.assign(document.createElement(tag), { className, textContent: text });
const fmt = (s) => Number.isFinite(s) && s >= 0 ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "0:00";
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
function connectWS(role, onMessage) {
  let ws = null;
  const send = (msg) => ws && ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(msg));
  const open = () => {
    ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws?role=${role}`);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "settings") Settings.load();   // changed on the Settings page
      onMessage(msg);
    };
    ws.onclose = () => setTimeout(open, 2000);
  };
  open();
  setInterval(() => send({ type: "ping" }), 20000);
  return send;
}

let toastTimer = null;
function toast(text, ok = true) {
  let t = $("toast");
  if (!t) {
    t = el("div", "pointer-events-none fixed inset-x-4 bottom-6 z-50 mx-auto max-w-md rounded-xl px-4 py-3 text-center font-semibold shadow-2xl transition duration-300");
    t.id = "toast";
    document.body.append(t);
  }
  t.textContent = text;
  t.classList.toggle("bg-emerald-700", ok);
  t.classList.toggle("bg-red-800", !ok);
  t.style.opacity = "1"; t.style.transform = "none";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.style.opacity = "0"; t.style.transform = "translateY(1.5rem)"; }, 2600);
}
const fail = (err) => toast(err.message, false);

function iconButton(label, title, onclick, extra = "") {
  const b = el("button", `shrink-0 rounded-lg bg-white/10 px-2 py-1 text-xs hover:bg-white/20 active:bg-white/30 disabled:opacity-25 ${extra}`, label);
  b.title = title;
  b.onclick = onclick;
  return b;
}

// Transport icons as inline SVG (emoji like ⏪ render as blue tiles on Windows)
const ICON = {
  play: "M8 5v14l11-7z", pause: "M6 5h4v14H6zM14 5h4v14h-4z", restart: "M6 6h2v12H6zM9.5 12 18 6v12z",
  skip: "M16 6h2v12h-2zM6 18l8.5-6L6 6z", back: "M11 18V6l-8.5 6zM20 18V6l-8.5 6z", fwd: "M13 6v12l8.5-6zM4 18l8.5-6L4 6z",
};
const svg = (name) => `<svg viewBox="0 0 24 24" class="h-5 w-5 fill-current" aria-hidden="true"><path d="${ICON[name]}"/></svg>`;
const setIcon = (btn, name) => { btn.querySelector("svg")?.remove(); btn.insertAdjacentHTML("afterbegin", svg(name)); };
document.querySelectorAll("[data-icon]").forEach((b) => setIcon(b, b.dataset.icon));

// One queue entry: title on its own line, then singer + status + sing-next / up / down / remove
function queueRow(e, i, total, { thumb = true, extras = [] } = {}) {
  const [label, color] = STATUS[e.status] || [e.status, "bg-stone-600"];
  const li = el("li", "flex items-center gap-3 rounded-xl bg-black/45 p-2 ring-1 ring-white/5");
  if (thumb) li.append(Object.assign(el("img", "h-12 w-16 shrink-0 rounded-lg object-cover"), { src: e.thumbnail, alt: "" }));
  const info = el("div", "min-w-0 flex-1 space-y-1");
  const meta = el("div", "flex items-center gap-1");
  info.append(el("p", "truncate text-sm font-semibold", `${i + 1}. ${e.title}`), meta);
  const move = (direction) => api(`/api/queue/${e.uid}/move`, { method: "POST", body: { direction } }).catch(fail);
  const top = iconButton("⤒", "Sing next", () => move("top"));
  const up = iconButton("▲", "Move up", () => move("up"));
  const down = iconButton("▼", "Move down", () => move("down"));
  top.disabled = up.disabled = i === 0;
  down.disabled = i === total - 1;
  const del = iconButton("✕", "Remove from queue", () => api(`/api/queue/${e.uid}`, { method: "DELETE" }).catch(fail), "hover:bg-red-800");
  meta.append(el("span", "min-w-0 flex-1 truncate text-xs text-stone-400", `🎤 ${e.singer}${e.error ? " — " + e.error : ""}`),
    el("span", `shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${color}`, label), ...extras, top, up, down, del);
  li.append(info);
  return li;
}
