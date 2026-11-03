// The ready-to-sing songs (already processed, they start instantly) as plain data: filtering by
// tag pill and typed words, which tag pills to offer, and the "Good luck" random pick. Kept free
// of the page so the search panel (ui/search-panel.js) can live on any page or in a popup.
// Same rules as the guest remote (remote-library.js, remote-lucky.js). Needs nothing.
// ReadySongs.filter(songs, tag, text), .pills(songs, genres, decades), .pick(songs, busyIds, tag),
// .busy(songs, queueState) -> Set of ids, .name(song)
const ReadySongs = (() => {
  const RECENT_SECONDS = 3600;   // "Good luck" prefers songs nobody sang in the last hour
  const DECADES = ["80s", "90s", "2000s", "2010s", "70s", "2020s"];
  const fold = (s) => s.toLowerCase().replace(/ё/g, "е");

  // Does a song carry this tag? (genre, decade, language, its own tags, or the two specials)
  function hasTag(s, tag) {
    const t = tag.toLowerCase();
    return (s.genre && s.genre.toLowerCase() === t) || (s.decade && s.decade.toLowerCase() === t)
      || (s.language && s.language.toLowerCase() === t) || (Array.isArray(s.tags) && s.tags.includes(t))
      || (t === "russian" && s.language === "ru") || (t === "duet" && (s.tags || []).includes("duet"));
  }

  // Songs under the tag ("all" = every one) whose names hold every typed word
  function filter(songs, tag = "all", text = "") {
    let pool = tag && tag !== "all" ? songs.filter((s) => hasTag(s, tag)) : songs;
    const words = fold(text).split(/\s+/).filter(Boolean);
    if (words.length) {
      pool = pool.filter((s) => {
        const hay = fold(`${s.artist || ""} ${s.clean_title || ""} ${s.title || ""} ${s.channel || ""} ${s.genre || ""}`);
        return words.every((w) => hay.includes(w));
      });
    }
    return pool;
  }

  // Pills: All, decades in a fixed order, the genres, then Russian / Duets when any song has them
  function pills(songs, genres = [], decades = []) {
    const out = [{ tag: "all", label: "✨ All" }];
    for (const d of DECADES) if (decades.includes(d)) out.push({ tag: d, label: d });
    for (const g of genres) out.push({ tag: g, label: g });
    if (songs.some((s) => s.language === "ru")) out.push({ tag: "russian", label: "🇷🇺 Russian" });
    if (songs.some((s) => (s.tags || []).includes("duet"))) out.push({ tag: "duet", label: "🎤 Duets" });
    return out;
  }

  // A random song that is not queued or playing (busyIds), preferably not sung in the last hour.
  // Returns { song } or { problem } with a sentence for a toast.
  function pick(songs, busyIds, tagName = "all") {
    if (!songs.length) return { problem: `No ready songs under ${tagName}` };
    const free = songs.filter((s) => !busyIds.has(s.id));
    if (!free.length) return { problem: `All songs under ${tagName} are already queued or playing!` };
    const now = Date.now() / 1000;
    const fresh = free.filter((s) => !s.played_at || now - Number(s.played_at) > RECENT_SECONDS);
    const pool = fresh.length ? fresh : free;
    return { song: pool[Math.floor(Math.random() * pool.length)] };
  }

  // Ids of the songs queued or playing: from a queue state {now_playing, queue}, or without one
  // from the library's own in_queue / playing flags (a little older)
  function busy(songs, state) {
    if (!state) return new Set(songs.filter((s) => s.in_queue || s.playing).map((s) => s.id));
    return new Set([state.now_playing?.song_id, ...(state.queue || []).map((e) => e.song_id)].filter(Boolean));
  }

  const name = (s) => (s.artist && s.clean_title ? `${s.artist} – ${s.clean_title}` : s.title);
  return { filter, pills, pick, busy, name };
})();
