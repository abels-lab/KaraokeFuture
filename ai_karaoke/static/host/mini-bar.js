// Mini player: a slim "now singing" strip with play / pause and next, shown whenever the stage
// itself is out of sight — the Library view, and the phone's Queue and Co-Pilot tabs — so the
// host can keep the party going while browsing (host/host.css decides when it shows). A tap on
// the song goes back to the stage. It reads the Deck (player or controller) like tv-now.js does.
// Needs common.js, tv-now.js (Deck), host/router.js and #mini-bar in host.html.
(() => {
  const bar = $("mini-bar");
  bar.className = "panel mx-4 mt-3 flex shrink-0 items-center gap-3 px-3 py-2";
  bar.innerHTML = `
    <button type="button" data-k="song" class="tap flex min-w-0 flex-1 items-center gap-3 text-left" title="Back to the stage">
      <img data-k="thumb" alt="" src="/static/img/microphone.png" class="h-10 w-14 shrink-0 rounded-lg object-cover">
      <span class="min-w-0">
        <span data-k="singer" class="block truncate text-sm font-bold">Nobody yet</span>
        <span data-k="title" class="block truncate text-xs text-stone-400">Pick a song to get started</span>
      </span>
    </button>
    <span data-k="time" class="hide-phone shrink-0 font-mono text-xs text-stone-400"></span>
    <button type="button" data-k="play" class="btn-gold tap-square grid h-10 w-10 shrink-0 place-items-center rounded-full" title="Play / pause (Space)"></button>
    <button type="button" data-k="next" class="tap-square grid h-10 w-10 shrink-0 place-items-center rounded-full bg-white/10 hover:bg-white/20" title="Next song (N)"></button>`;
  const part = (k) => bar.querySelector(`[data-k="${k}"]`);
  setIcon(part("play"), "play");
  setIcon(part("next"), "next");
  part("song").onclick = () => Router.go("stage");
  part("play").onclick = () => Deck?.toggle();
  part("next").onclick = () => Deck?.next();

  let shownUid = null, shownPaused = null;
  function paint() {
    const entry = Deck?.current || null;
    if ((entry?.uid || null) !== shownUid) {
      shownUid = entry?.uid || null;
      part("singer").textContent = entry ? singers(entry) : "Nobody yet";
      part("title").textContent = entry ? entry.title : "Pick a song to get started";
      part("thumb").src = entry ? entry.thumbnail || thumbFor(entry.song_id) : "/static/img/microphone.png";
    }
    const paused = !entry || Deck.paused;
    if (paused !== shownPaused) { shownPaused = paused; setIcon(part("play"), paused ? "play" : "pause"); }
    part("time").textContent = entry ? `${fmt(Deck.time())}` : "";
  }
  setInterval(paint, 250);
})();
