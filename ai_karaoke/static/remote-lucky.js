// Guest phone: "Good luck" — a random ready song under the chosen tag, never one that is
// queued or playing, and preferably not one sung in the last hour. Shown as a card with Add.
// Needs common.js, remote-library.js; lastState and addSong come from remote.js / remote-search.js.
$("btn-lucky").onclick = () => rollLuckySong();

function rollLuckySong() {
  const allTagged = filterCachedSongs(activeTag);
  if (!allTagged.length) {
    toast(`No ready songs under ${activeTag}`, false);
    return;
  }

  // Exclude songs currently in queue or currently playing
  const activeIds = new Set(
    [lastState.now_playing?.song_id, ...lastState.queue.map((e) => e.song_id)].filter(Boolean)
  );
  const free = allTagged.filter((s) => !activeIds.has(s.id));

  if (!free.length) {
    toast(`All songs under ${activeTag} are already queued or playing!`, false);
    return;
  }

  // Exclude songs played in the last hour (3600 seconds)
  const now = Date.now() / 1000;
  const RECENT_SECONDS = 3600;
  const fresh = free.filter((s) => !s.played_at || (now - Number(s.played_at)) > RECENT_SECONDS);

  // If there are fresh songs, pick from them; otherwise fall back to available free songs
  const pool = fresh.length ? fresh : free;
  const song = pool[Math.floor(Math.random() * pool.length)];
  const card = $("lucky-card");

  const header = el("div", "flex items-center justify-between text-xs text-amber-300 font-bold mb-1");
  header.append(
    el("span", "flex items-center gap-1", "🎲 Accidental Song Pick"),
    Object.assign(el("button", "text-stone-400 hover:text-stone-200 px-1", "✕"), {
      onclick: () => card.classList.add("hidden"),
    })
  );

  const body = el("div", "flex items-center gap-3");
  const img = Object.assign(el("img", "h-14 w-20 shrink-0 rounded-lg object-cover"), {
    src: song.thumbnail || thumbFor(song.id),
    alt: "",
    loading: "lazy",
  });
  const info = el("div", "min-w-0 flex-1");
  const displayTitle = song.artist && song.clean_title ? `${song.artist} – ${song.clean_title}` : song.title;
  info.append(
    el("p", "truncate text-sm font-bold text-amber-100", displayTitle),
    el("p", "truncate text-xs text-stone-400", [song.genre, song.decade, "⚡ Instant", song.duration ? fmt(song.duration) : ""].filter(Boolean).join(" · "))
  );
  const btnAdd = el("button", "btn-gold shrink-0 rounded-lg px-3 py-1.5 text-xs font-bold", "Add");
  btnAdd.onclick = () => addSong(song, btnAdd);
  body.append(img, info, btnAdd);

  card.replaceChildren(header, body);
  card.className = "p-3 rounded-xl bg-gradient-to-br from-amber-500/10 via-stone-900 to-amber-950/20 border border-amber-500/30 space-y-2";
  card.classList.remove("hidden");
  toast(`🎲 Picked: ${displayTitle}`);
}
