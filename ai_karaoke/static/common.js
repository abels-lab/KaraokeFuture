// Shared by every page: DOM + formatting helpers, API calls, WebSocket, toasts, queue rows.
const $ = (id) => document.getElementById(id);
const el = (tag, className = "", text = "") => Object.assign(document.createElement(tag), { className, textContent: text });
const fmt = (s) => Number.isFinite(s) && s >= 0 ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "0:00";
// Fallback picture when the server sent none: YouTube ids have a fixed thumbnail URL ("sc_" ids don't)
const thumbFor = (id) => (/^[\w-]{11}$/.test(id || "") ? `https://i.ytimg.com/vi/${id}/hqdefault.jpg` : "/static/img/microphone.png");
// "Ann & Bob" when a second singer joined a battle song (entry.partner), else just the singer
const singers = (e) => (e?.partner ? `${e.singer} & ${e.partner.name}` : e?.singer || "");
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

// One queue entry: title on its own line, then singer + status + sing-next / drag / remove.
// manage: "all" (host: drag handle to move anywhere) | "mine" (a guest's own song: swap among their own slots,
// first/last = its place among them) | null (someone else's: look only). The server checks too.
function queueRow(e, i, total, { thumb = true, extras = [], manage = "all", first = i === 0, last = i === total - 1 } = {}) {
  const [label, color] = STATUS[e.status] || [e.status, "bg-stone-600"];
  const li = el("li", "flex items-center gap-3 rounded-xl bg-black/45 p-2 ring-1 ring-white/5 transition-all");
  li.dataset.uid = e.uid;
  li.dataset.index = i;

  if (manage === "all") {
    const handle = el("div", "drag-handle cursor-grab active:cursor-grabbing p-1 text-stone-500 hover:text-amber-400 select-none shrink-0 transition flex items-center justify-center");
    handle.title = "Drag to reorder at any position";
    handle.innerHTML = `<svg viewBox="0 0 24 24" class="h-4 w-4 fill-current"><path d="M9 5a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm0 7a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm0 7a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm10-14a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm0 7a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm0 7a2 2 0 1 1-4 0 2 2 0 0 1 4 0z"/></svg>`;
    li.prepend(handle);

    handle.addEventListener("mousedown", () => { li.draggable = true; });
    handle.addEventListener("mouseup", () => { li.draggable = false; });
    
    li.addEventListener("dragstart", (ev) => {
      ev.dataTransfer.setData("text/plain", JSON.stringify({ uid: e.uid, index: i }));
      ev.dataTransfer.effectAllowed = "move";
      li.classList.add("opacity-40");
      document.body.classList.add("dragging-queue");
    });

    li.addEventListener("dragend", () => {
      li.draggable = false;
      li.classList.remove("opacity-40");
      document.body.classList.remove("dragging-queue");
      document.querySelectorAll(".drop-target-above, .drop-target-below").forEach((el) => {
        el.classList.remove("drop-target-above", "drop-target-below");
      });
    });

    li.addEventListener("dragover", (ev) => {
      ev.preventDefault();
      ev.dataTransfer.dropEffect = "move";
      const rect = li.getBoundingClientRect();
      const mid = rect.top + rect.height / 2;
      const isAbove = ev.clientY < mid;
      li.classList.toggle("drop-target-above", isAbove);
      li.classList.toggle("drop-target-below", !isAbove);
    });

    li.addEventListener("dragleave", () => {
      li.classList.remove("drop-target-above", "drop-target-below");
    });

    li.addEventListener("drop", (ev) => {
      ev.preventDefault();
      li.classList.remove("drop-target-above", "drop-target-below");
      try {
        const data = JSON.parse(ev.dataTransfer.getData("text/plain"));
        const srcUid = data.uid;
        const srcIdx = data.index;
        const rect = li.getBoundingClientRect();
        const isAbove = ev.clientY < rect.top + rect.height / 2;
        let targetIdx = isAbove ? i : i + 1;
        if (srcIdx < targetIdx) targetIdx--;
        if (srcIdx !== targetIdx && srcUid) {
          api(`/api/queue/${srcUid}/move`, {
            method: "POST",
            body: { to_index: targetIdx, scope: "all" }
          }).catch(fail);
        }
      } catch (err) {
        console.error("Drop error", err);
      }
    });
  }

  if (thumb) li.append(Object.assign(el("img", "h-12 w-16 shrink-0 rounded-lg object-cover"), { src: e.thumbnail || thumbFor(e.song_id), alt: "" }));
  const info = el("div", "min-w-0 flex-1 space-y-1");
  const meta = el("div", "flex items-center gap-1");
  info.append(el("p", "truncate text-sm font-semibold", `${i + 1}. ${e.title}`), meta);
  meta.append(el("span", "min-w-0 flex-1 truncate text-xs text-stone-400", `🎤 ${singers(e)}${e.error ? " — " + e.error : ""}`),
    el("span", `shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${color}`, label), ...extras);

  if (manage) {
    const scope = manage === "mine" ? "mine" : "all";
    const move = (direction) => api(`/api/queue/${e.uid}/move`, { method: "POST", body: { direction, scope } }).catch(fail);
    const top = iconButton("⤒", scope === "mine" ? "Make this your first song" : "Sing next", () => move("top"));
    const up = iconButton("▲", scope === "mine" ? "Swap with your earlier song" : "Move up", () => move("up"));
    const down = iconButton("▼", scope === "mine" ? "Swap with your later song" : "Move down", () => move("down"));
    const del = iconButton("✕", "Remove from queue", () => api(`/api/queue/${e.uid}`, { method: "DELETE" }).catch(fail), "hover:bg-red-800");
    top.disabled = up.disabled = first;
    down.disabled = last;
    if (typeof openLyrics === "function") {
      const lyr = iconButton("📝", "View or edit lyrics", () => openLyrics(e));
      meta.append(lyr);
    }
    meta.append(top, up, down, del);
  }
  li.append(info);
  return li;
}

// Row for an already played song: displays singer, title, with buttons to play immediately or return to queue.
function playedRow(e, i, { onPlay, onRequeue, onRemove } = {}) {
  const li = el("li", "flex items-center gap-2.5 rounded-xl bg-black/40 p-2 ring-1 ring-white/5 opacity-85 hover:opacity-100 transition group");
  li.append(Object.assign(el("img", "h-11 w-14 shrink-0 rounded-lg object-cover brightness-75 group-hover:brightness-95 transition"), {
    src: e.thumbnail || thumbFor(e.song_id), alt: ""
  }));
  const info = el("div", "min-w-0 flex-1 space-y-0.5");
  const meta = el("div", "flex items-center gap-1.5 flex-wrap");
  info.append(el("p", "truncate text-xs font-semibold text-stone-200", `${i + 1}. ${e.title}`), meta);
  meta.append(
    el("span", "min-w-0 flex-1 truncate text-[11px] text-stone-400", `🎤 ${singers(e)}`),
    el("span", "shrink-0 rounded-full px-1.5 py-0.2 text-[10px] font-semibold bg-stone-700/80 text-stone-300", "Played")
  );
  
  const actions = el("div", "flex items-center gap-1 shrink-0");
  const playBtn = iconButton("▶", "Play this song now", () => {
    if (onPlay) onPlay(e);
    else api(`/api/queue/${e.uid}/play`, { method: "POST" }).catch(fail);
  }, "hover:bg-amber-400 hover:text-stone-950 font-bold px-2 py-1");
  
  const reqBtn = iconButton("↩ Queue", "Add back to the queue", () => {
    if (onRequeue) onRequeue(e);
    else api(`/api/queue/${e.uid}/requeue`, { method: "POST" }).then(() => toast(`"${e.title}" back in queue`)).catch(fail);
  }, "bg-amber-900/40 text-amber-300 hover:bg-amber-800/70 font-semibold text-[11px] px-2 py-1");
  
  const delBtn = iconButton("✕", "Remove from history", () => {
    if (onRemove) onRemove(e);
    else api(`/api/queue/${e.uid}`, { method: "DELETE" }).catch(fail);
  }, "hover:bg-red-800 text-stone-400 px-1.5 py-1");
  
  actions.append(playBtn, reqBtn, delBtn);
  li.append(info, actions);
  return li;
}
