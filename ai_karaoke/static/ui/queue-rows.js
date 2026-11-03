// Queue list rows shared by the control panel (tv-side.js) and the guest remote (my-queue.js):
// a waiting entry with reorder / remove buttons (drag and drop for the host), and a played one.
// Needs common.js (el, api, fail, toast, iconButton, thumbFor, singers, STATUS); lyrics.js optional.
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
