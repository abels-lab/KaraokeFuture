// Guest phone: the queue with your own songs highlighted and their controls — swap among your
// own songs (never ahead of anyone else), remove them, and per song the singing mode and the
// guide-vocal volume the control panel uses when it plays. Needs common.js, auth.js, lyrics.js.
const MODE_CHOICES = [["", "🎮 Host's choice"], ["party", "✨ Party"], ["score", "🏆 Score"], ["battle", "⚔️ Battle / Duet (2 mics)"]];
let lastQueue = [], lastPlayed = [], lastActivePlaylist = null, dragging = false;
let queueFilter = "all"; // "all" | "mine" | "played"

const savePrefs = (e, changes) => {
  Object.assign(e, changes);
  return api(`/api/queue/${e.uid}`, {
    method: "PATCH",
    body: { guide: e.guide !== undefined ? e.guide : null, mode: e.mode || null, ...changes }
  }).then(() => toast("Saved song settings")).catch(fail);
};

// Mode picker + guide slider for one queue entry (adjustable before song starts)
function songPrefs(e) {
  const box = el("div", "flex flex-wrap items-center gap-2 pt-1 text-xs text-stone-300");
  const mode = el("select", "rounded-lg bg-white/10 px-2 py-1 text-xs outline-none");
  mode.title = "Singing mode: party (friendly scoring), score (real pitch), battle (2 mics)";
  for (const [value, label] of MODE_CHOICES) mode.append(Object.assign(el("option", "bg-stone-900", label), { value }));
  mode.value = e.mode || "";
  mode.onchange = () => savePrefs(e, { mode: mode.value || null });

  const guideVal = Number.isFinite(e.guide) ? e.guide : Settings.get("guide_default", 20);
  const slider = Object.assign(el("input", "min-w-[5rem] flex-1 accent-amber-400"),
    { type: "range", min: 0, max: 100, step: 5, value: guideVal });
  slider.title = "Guide vocals: volume of the original singer (0% = mute, 100% = full)";
  const shown = el("span", "w-11 text-right font-mono font-semibold", Number.isFinite(e.guide) ? `${e.guide}%` : "default");
  slider.oninput = () => { dragging = true; shown.textContent = `${slider.value}%`; };
  slider.onchange = () => { dragging = false; savePrefs(e, { guide: Number(slider.value) }); };
  const reset = iconButton("↺", "Reset to host default volume", () => {
    delete e.guide;
    slider.value = Settings.get("guide_default", 20);
    shown.textContent = "default";
    savePrefs(e, { guide: null });
  });
  reset.disabled = !Number.isFinite(e.guide);
  box.append(mode, el("span", "", "🗣"), slider, shown, reset);
  return box;
}

function lyricsActionBtn(e) {
  const isTranscribed = needsLyrics(e);
  const isAdmin = Boolean(Auth.me?.admin);
  const label = isAdmin ? (isTranscribed ? "📝 Fix" : "📝 Lyrics") : "📖 Lyrics";
  const title = isAdmin ? (isTranscribed ? "Fix AI-transcribed lyrics" : "Edit lyrics") : "View lyrics";
  const cls = isTranscribed
    ? "bg-amber-900/80 text-amber-200 ring-1 ring-amber-500/50"
    : "bg-white/10 text-stone-200";
  return el("button", `rounded-lg px-2 py-1 text-xs font-semibold ${cls}`, label, {
    title,
    onclick: (ev) => {
      ev.stopPropagation();
      openLyrics(e);
    }
  });
}

function setQueueFilter(f) {
  queueFilter = f;
  const isAll = f === "all", isMine = f === "mine", isPlayed = f === "played";
  $("qfilter-all")?.classList.toggle("bg-amber-400", isAll);
  $("qfilter-all")?.classList.toggle("text-stone-950", isAll);
  $("qfilter-all")?.classList.toggle("bg-white/10", !isAll);
  $("qfilter-all")?.classList.toggle("text-stone-300", !isAll);

  $("qfilter-mine")?.classList.toggle("bg-amber-400", isMine);
  $("qfilter-mine")?.classList.toggle("text-stone-950", isMine);
  $("qfilter-mine")?.classList.toggle("bg-white/10", !isMine);
  $("qfilter-mine")?.classList.toggle("text-stone-300", !isMine);

  $("qfilter-played")?.classList.toggle("bg-amber-400", isPlayed);
  $("qfilter-played")?.classList.toggle("text-stone-950", isPlayed);
  $("qfilter-played")?.classList.toggle("bg-white/10", !isPlayed);
  $("qfilter-played")?.classList.toggle("text-stone-300", !isPlayed);
  renderQueue();
}

$("qfilter-all")?.addEventListener("click", () => setQueueFilter("all"));
$("qfilter-mine")?.addEventListener("click", () => setQueueFilter("mine"));
$("qfilter-played")?.addEventListener("click", () => setQueueFilter("played"));

function renderQueue(queue = lastQueue, played = lastPlayed, activePlaylist = lastActivePlaylist) {
  lastQueue = queue;
  lastPlayed = played;
  if (activePlaylist !== undefined) lastActivePlaylist = activePlaylist;
  if (dragging) return;   // don't redraw under the finger; the save redraws it
  const { admin } = Auth.me;
  const mine = queue.filter(Auth.owns);

  if ($("queue-count")) $("queue-count").textContent = queue.length;
  if ($("queue-mine-count")) $("queue-mine-count").textContent = mine.length;
  if ($("queue-played-count")) $("queue-played-count").textContent = played.length;
  const badge = $("tab-queue-badge");
  if (badge) {
    badge.textContent = queue.length;
    badge.className = `ml-1 rounded-full px-2 py-0.5 text-xs font-mono font-bold ${
      queue.length > 0 ? "bg-amber-400 text-stone-950" : "bg-white/10 text-stone-300"
    }`;
  }

  const empty = $("queue-empty");

  // If viewing already played songs
  if (queueFilter === "played") {
    const revPlayed = [...played].reverse();
    if (empty) {
      empty.classList.toggle("hidden", revPlayed.length > 0);
      if (revPlayed.length === 0) {
        if ($("empty-title")) $("empty-title").textContent = "No songs played yet";
        if ($("empty-sub")) $("empty-sub").textContent = "Songs that finished singing will appear here.";
      }
    }
    $("queue")?.replaceChildren(...revPlayed.map((e, i) => playedRow(e, i)));
    $("autodj-remote-box")?.classList.add("hidden");
    return;
  }

  const items = queueFilter === "mine" ? mine : queue;
  if (empty) {
    empty.classList.toggle("hidden", items.length > 0);
    if (items.length === 0) {
      if (queue.length === 0) {
        if (lastActivePlaylist) {
          if ($("empty-title")) $("empty-title").textContent = "Auto-DJ Active";
          if ($("empty-sub")) $("empty-sub").textContent = `Playing from ${lastActivePlaylist.name} (low priority). Claim a song below or search to sing next!`;
        } else {
          if ($("empty-title")) $("empty-title").textContent = "Nobody in line";
          if ($("empty-sub")) $("empty-sub").textContent = "Be the first to queue a song!";
        }
      } else {
        if ($("empty-title")) $("empty-title").textContent = "No songs queued by you";
        if ($("empty-sub")) $("empty-sub").textContent = `There are ${queue.length} other songs waiting in line.`;
      }
    }
  }

  $("queue")?.replaceChildren(...items.map((e) => {
    const own = Auth.owns(e);
    const canManage = admin || own;
    const pos = mine.indexOf(e);
    const idx = queue.indexOf(e);
    const row = queueRow(e, idx, queue.length, {
      thumb: false,
      extras: [...Battle.controls(e), lyricsActionBtn(e)],   // join / leave a battle (remote-battle.js)
      manage: admin ? "all" : own ? "mine" : null,
      first: admin ? idx === 0 : pos === 0,
      last: admin ? idx === queue.length - 1 : pos === mine.length - 1,
    });
    if (own) {
      row.classList.replace("ring-white/5", "ring-amber-400/60"); // yours stand out
    }
    if (canManage) {
      row.lastChild.append(songPrefs(e));
    }
    return row;
  }));

  // Auto-DJ Playlist Section on Remote (Expanded below singer queue)
  let autodjSection = $("autodj-remote-box");
  if (!autodjSection && $("queue")) {
    autodjSection = el("div", "mt-4 space-y-2");
    autodjSection.id = "autodj-remote-box";
    $("queue").parentElement.append(autodjSection);
  }
  if (autodjSection) {
    const hasActiveQueue = lastActivePlaylist && lastActivePlaylist.queue && lastActivePlaylist.queue.length > 0;
    if (queueFilter !== "played" && (hasActiveQueue || admin)) {
      autodjSection.classList.remove("hidden");
      autodjSection.replaceChildren();

      if (hasActiveQueue) {
        const wrapBox = el("div", "rounded-2xl bg-amber-500/10 border border-amber-400/25 p-3.5 space-y-2.5");
        
        // Header
        const header = el("div", "flex items-center justify-between gap-2 border-b border-amber-400/20 pb-2");
        const titleWrap = el("div", "min-w-0 flex-1");
        const tTitle = el("div", "flex items-center gap-1.5 font-bold text-amber-300 text-xs truncate");
        tTitle.append(
          el("span", "", "📻"),
          el("span", "truncate", `Auto-DJ: ${lastActivePlaylist.name}`)
        );
        const tSub = el("p", "text-[10px] text-stone-400 truncate mt-0.5", `${lastActivePlaylist.remaining} songs queued · Plays automatically when nobody is in line`);
        titleWrap.append(tTitle, tSub);

        const rightWrap = el("div", "flex items-center gap-1.5 shrink-0");
        if (admin) {
          const switchBtn = el("button", "rounded-lg bg-white/10 hover:bg-white/20 text-stone-200 px-2.5 py-1 text-[11px] font-bold transition flex items-center gap-1", "🔀 Manage");
          switchBtn.onclick = openPlaylistModal;
          const stopBtn = el("button", "rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 px-2 py-1 text-[11px] font-bold transition", "⏹ Stop");
          stopBtn.onclick = async () => {
            try {
              await api("/api/playlists/stop", { method: "POST" });
              toast("Stopped Auto-DJ playlist");
            } catch (err) {
              fail(err);
            }
          };
          rightWrap.append(switchBtn, stopBtn);
        } else {
          rightWrap.append(el("span", "rounded-full bg-white/10 text-stone-300 px-2 py-0.5 text-[10px] font-semibold", "Auto filler"));
        }
        header.append(titleWrap, rightWrap);

        // Expanded Song List (up to 15 items with scroll)
        const list = el("ul", "space-y-1.5 max-h-72 overflow-y-auto pr-1");
        const songsToShow = lastActivePlaylist.queue.slice(0, 15);
        for (const [idx, item] of songsToShow.entries()) {
          const row = el("li", "flex items-center justify-between gap-2 rounded-xl bg-black/40 border border-white/5 p-2 text-xs hover:border-amber-400/30 transition");
          const info = el("div", "min-w-0 flex-1 flex items-center gap-2");
          const num = el("span", "text-[10px] font-mono font-bold text-amber-400/80 w-5 text-center shrink-0", `${idx + 1}`);
          const trackText = el("div", "min-w-0 flex-1");
          trackText.append(
            el("p", "truncate font-semibold text-stone-200 text-xs", item.title || item.query),
            el("p", "truncate text-[10px] text-stone-400", item.artist ? `${item.artist} · Auto-DJ` : "Auto-DJ filler")
          );
          info.append(num, trackText);

          const claimBtn = el("button", "shrink-0 rounded-lg bg-amber-400/20 hover:bg-amber-400/30 text-amber-300 px-2.5 py-1 text-xs font-bold transition flex items-center gap-1", "🎤 Sing this!");
          claimBtn.title = "Add this song into your user queue to sing it next";
          claimBtn.onclick = async () => {
            try {
              await api("/api/playlists/promote", {
                method: "POST",
                body: { query: item.query || item.title, index: idx }
              });
              toast(`Added "${item.title || item.query}" to your queue!`);
            } catch (err) {
              fail(err);
            }
          };
          row.append(info, claimBtn);
          list.append(row);
        }

        wrapBox.append(header, list);

        if (lastActivePlaylist.remaining > 15) {
          const moreNote = el("p", "text-[10px] text-center text-stone-400 italic pt-1", `+ ${lastActivePlaylist.remaining - 15} more songs in playlist queue`);
          wrapBox.append(moreNote);
        }

        autodjSection.append(wrapBox);
      } else if (admin) {
        // Host view when no Auto-DJ playlist is currently running
        const idleBox = el("div", "rounded-2xl border border-dashed border-amber-400/30 bg-amber-400/5 p-4 text-xs space-y-2.5");
        const hTitle = el("div", "flex items-center justify-between font-bold text-amber-300");
        hTitle.append(
          el("span", "flex items-center gap-1.5", "📻 Auto-DJ: Idle"),
          el("span", "text-[10px] text-stone-400 font-normal", "Host control")
        );
        const hSub = el("p", "text-stone-300 text-xs", "No background playlist is currently active. Select or create a playlist to automatically play filler songs whenever nobody is waiting in line.");
        const hBtn = el("button", "rounded-xl bg-amber-400 hover:bg-amber-300 text-stone-950 font-bold px-4 py-2 transition text-xs flex items-center gap-1.5 shadow", "▶ Select / Manage Playlists");
        hBtn.onclick = openPlaylistModal;
        idleBox.append(hTitle, hSub, hBtn);
        autodjSection.append(idleBox);
      }
    } else {
      autodjSection.classList.add("hidden");
    }
  }
}

// ── Auto-DJ Playlists Modal & CRUD Dialog (Host) ──────────────────────────
function updatePlaylistSongsCount() {
  const textarea = $("playlist-form-songs");
  const countEl = $("playlist-form-count");
  if (!textarea || !countEl) return;
  const lines = textarea.value.split("\n").map(l => l.trim()).filter(Boolean);
  countEl.textContent = `${lines.length} song(s)`;
}

function showPlaylistListView() {
  $("playlist-view-list")?.classList.remove("hidden");
  $("playlist-view-form")?.classList.add("hidden");
  loadPlaylistList();
}

function showPlaylistFormView(playlist = null) {
  $("playlist-view-list")?.classList.add("hidden");
  $("playlist-view-form")?.classList.remove("hidden");

  const idInput = $("playlist-form-id");
  const nameInput = $("playlist-form-name");
  const descInput = $("playlist-form-desc");
  const songsTextarea = $("playlist-form-songs");
  const titleEl = $("playlist-form-title");

  if (playlist) {
    if (titleEl) titleEl.textContent = `Edit: ${playlist.name}`;
    if (idInput) idInput.value = playlist.id || "";
    if (nameInput) nameInput.value = playlist.name || "";
    if (descInput) descInput.value = playlist.description || "";
    if (songsTextarea) {
      const songLines = (playlist.songs || []).map(s => {
        if (typeof s === "string") return s;
        if (s.artist && s.title) return `${s.artist} - ${s.title}`;
        return s.title || s.query || "";
      }).filter(Boolean);
      songsTextarea.value = songLines.join("\n");
    }
  } else {
    if (titleEl) titleEl.textContent = "Create New Playlist";
    if (idInput) idInput.value = "";
    if (nameInput) nameInput.value = "";
    if (descInput) descInput.value = "";
    if (songsTextarea) songsTextarea.value = "";
  }
  updatePlaylistSongsCount();
  nameInput?.focus();
}

async function loadPlaylistList() {
  const list = $("playlist-modal-list");
  if (!list) return;
  list.innerHTML = '<div class="p-4 text-center text-stone-400 text-xs">Loading playlists...</div>';
  try {
    const data = await api("/api/playlists");
    const playlists = data.playlists || [];
    const activeId = data.active_playlist?.id || lastActivePlaylist?.id;
    if (playlists.length === 0) {
      list.innerHTML = '<div class="p-4 text-center text-stone-400 text-xs">No playlists found.</div>';
      return;
    }
    list.replaceChildren(...playlists.map(pl => {
      const isCurrent = pl.id === activeId;
      const card = el("div", `rounded-xl p-3 text-xs border transition flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 ${
        isCurrent ? "bg-amber-400/15 border-amber-400/50 shadow-sm" : "bg-white/5 border-white/10 hover:border-white/20"
      }`);

      const info = el("div", "min-w-0 flex-1 space-y-1");
      const nameRow = el("div", "flex flex-wrap items-center gap-1.5");
      nameRow.append(el("span", "font-bold text-sm text-stone-100 truncate", pl.name));
      if (isCurrent) {
        nameRow.append(el("span", "rounded-full bg-emerald-500/20 text-emerald-300 px-2 py-0.5 text-[10px] font-bold", "Playing"));
      }
      if (pl.is_built_in) {
        nameRow.append(el("span", "rounded-full bg-white/10 text-stone-300 px-1.5 py-0.5 text-[10px]", pl.rotation ? "Weekly Rotation" : "Built-in"));
      } else {
        nameRow.append(el("span", "rounded-full bg-amber-400/20 text-amber-300 px-1.5 py-0.5 text-[10px] font-semibold", "Custom"));
      }
      info.append(
        nameRow,
        el("p", "text-[11px] text-stone-400 line-clamp-1", pl.description || `${pl.count || 0} songs`),
        el("p", "text-[10px] text-stone-500 font-mono", `${pl.count || 0} songs`)
      );

      const actions = el("div", "flex items-center gap-1.5 shrink-0 flex-wrap justify-end");

      // Custom playlists can be edited or deleted
      if (!pl.is_built_in) {
        const editBtn = el("button", "rounded-lg bg-white/10 hover:bg-white/20 text-stone-200 px-2.5 py-1 text-xs font-semibold transition flex items-center gap-1", "✏️ Edit");
        editBtn.title = "Edit playlist name and songs";
        editBtn.onclick = async () => {
          try {
            const fullPl = await api(`/api/playlists/${pl.id}`);
            showPlaylistFormView(fullPl);
          } catch (err) {
            fail(err);
          }
        };

        const deleteBtn = el("button", "rounded-lg bg-red-500/15 hover:bg-red-500/25 text-red-300 px-2 py-1 text-xs font-semibold transition", "🗑️");
        deleteBtn.title = `Delete playlist "${pl.name}"`;
        deleteBtn.onclick = async () => {
          if (!confirm(`Are you sure you want to delete playlist "${pl.name}"?`)) return;
          try {
            await api(`/api/playlists/${pl.id}`, { method: "DELETE" });
            toast(`Deleted playlist "${pl.name}"`);
            loadPlaylistList();
          } catch (err) {
            fail(err);
          }
        };

        actions.append(editBtn, deleteBtn);
      }

      // Play / Active Button
      const playBtn = el("button", `rounded-lg px-3 py-1 font-bold transition text-xs flex items-center gap-1 ${
        isCurrent
          ? "bg-amber-400/20 text-amber-200 hover:bg-amber-400/30"
          : "bg-amber-400 hover:bg-amber-300 text-stone-950 shadow"
      }`, isCurrent ? "Active (Restart)" : "▶ Play");
      playBtn.onclick = async () => {
        try {
          await api(`/api/playlists/${pl.id}/play`, { method: "POST" });
          toast(`Started Auto-DJ with "${pl.name}"!`);
          $("playlist-modal")?.classList.replace("flex", "hidden");
        } catch (err) {
          fail(err);
        }
      };
      actions.append(playBtn);

      card.append(info, actions);
      return card;
    }));
  } catch (err) {
    list.innerHTML = `<div class="p-4 text-center text-rose-400 text-xs">${escapeHtml(err.message || String(err))}</div>`;
  }
}

async function openPlaylistModal() {
  const modal = $("playlist-modal");
  if (!modal) return;
  modal.classList.replace("hidden", "flex");
  showPlaylistListView();
}

async function savePlaylistFromForm() {
  const idInput = $("playlist-form-id");
  const nameInput = $("playlist-form-name");
  const descInput = $("playlist-form-desc");
  const songsTextarea = $("playlist-form-songs");

  const name = nameInput ? nameInput.value.trim() : "";
  if (!name) {
    alert("Please enter a playlist name.");
    nameInput?.focus();
    return;
  }

  const rawSongs = songsTextarea ? songsTextarea.value.split("\n").map(l => l.trim()).filter(Boolean) : [];
  if (rawSongs.length === 0) {
    alert("Please enter at least one song for the playlist.");
    songsTextarea?.focus();
    return;
  }

  const pid = idInput ? idInput.value.trim() : "";
  const description = descInput ? descInput.value.trim() : "";

  try {
    if (pid) {
      await api(`/api/playlists/${pid}`, {
        method: "PUT",
        body: { name, description, songs: rawSongs, action: "set" }
      });
      toast(`Updated playlist "${name}"!`);
    } else {
      await api("/api/playlists", {
        method: "POST",
        body: { name, description, songs: rawSongs }
      });
      toast(`Created playlist "${name}"!`);
    }
    showPlaylistListView();
  } catch (err) {
    fail(err);
  }
}

$("playlist-form-songs")?.addEventListener("input", updatePlaylistSongsCount);
$("playlist-btn-new")?.addEventListener("click", () => showPlaylistFormView(null));
$("playlist-form-back")?.addEventListener("click", showPlaylistListView);
$("playlist-form-cancel")?.addEventListener("click", showPlaylistListView);
$("playlist-form-save")?.addEventListener("click", savePlaylistFromForm);

$("playlist-modal-close")?.addEventListener("click", () => $("playlist-modal")?.classList.replace("flex", "hidden"));
$("playlist-modal-done")?.addEventListener("click", () => $("playlist-modal")?.classList.replace("flex", "hidden"));
$("playlist-modal")?.addEventListener("click", (e) => {
  if (e.target === $("playlist-modal")) $("playlist-modal")?.classList.replace("flex", "hidden");
});
$("playlist-modal-stop")?.addEventListener("click", async () => {
  try {
    await api("/api/playlists/stop", { method: "POST" });
    toast("Auto-DJ playlist stopped");
    $("playlist-modal")?.classList.replace("flex", "hidden");
  } catch (err) {
    fail(err);
  }
});
$("btn-remote-playlists")?.addEventListener("click", openPlaylistModal);
