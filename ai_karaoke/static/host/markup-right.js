// Control panel, right column: now singing + transport + guide-vocal slider, then the song queue
// (Up next / Played / All tabs). Markup only, written into host.html's empty #col-right before
// the scripts that use these ids (tv-now.js, tv-side.js, guide.js). The ids are a contract with
// those scripts and the Co-Pilot's hide / show tool: never rename one.
// #host-note: controller-mode notices (host/controller.js). The queue header's ＋ opens the
// Add song popup (data-act, host/views.js). Needs common.js (setIcon: its own [data-icon] pass
// ran before this markup existed).
document.getElementById("col-right").innerHTML = `
  <section id="now-playing-card" class="panel p-4 space-y-3 shrink-0">
    <div id="host-note" class="hidden rounded-xl px-3 py-2 text-xs"></div>
    <header class="flex items-center gap-3">
      <img src="/static/img/microphone.png" alt="" class="mic-glow h-10 w-auto -rotate-12 shrink-0">
      <div class="min-w-0 flex-1">
        <p class="text-[10px] font-bold uppercase tracking-[0.25em] text-gold">Now singing</p>
        <h2 id="np-singer" class="font-display truncate text-xl font-black">Nobody yet</h2>
        <p id="np-title" class="truncate text-xs text-stone-300">Pick a song to get started</p>
      </div>
      <button id="np-lyrics-btn" class="tap hidden shrink-0 rounded-lg bg-white/10 px-2.5 py-1.5 text-xs font-semibold text-stone-200 hover:bg-white/20 transition flex items-center gap-1" title="View or edit lyrics for now playing song">📝 <span>Lyrics</span></button>
    </header>

    <div class="flex items-center gap-2 font-mono text-xs text-stone-300">
      <span id="time-cur" class="w-10 text-right">0:00</span>
      <input id="seek" type="range" min="0" max="0" step="0.1" value="0" class="flex-1 tap" title="Drag to scrub">
      <span id="time-dur" class="w-10">0:00</span>
    </div>

    <div id="transport-bar" class="flex items-center justify-between gap-1.5 flex-wrap">
      <button id="btn-prev" class="flex h-10 flex-1 min-w-[90px] items-center justify-center gap-1 rounded-full bg-white/10 px-2.5 text-xs font-semibold hover:bg-white/20 disabled:opacity-30 disabled:pointer-events-none transition shrink-0" title="Previous song (P)">
        <svg viewBox="0 0 24 24" class="h-3.5 w-3.5 shrink-0 fill-current"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/></svg>
        <span class="btn-nav-prefix text-stone-400 font-normal shrink-0">Prev:</span>
        <span id="btn-prev-label" class="btn-nav-text truncate font-bold text-stone-200">None</span>
      </button>
      <button id="btn-restart" data-icon="restart" class="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-white/10 hover:bg-white/20 transition" title="Restart (0:00)"></button>
      <button id="btn-back" data-icon="back" class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs font-semibold hover:bg-white/20 transition" title="Back 10 s (←)">10</button>
      <button id="btn-play" data-icon="play" class="btn-gold grid h-11 w-11 shrink-0 place-items-center rounded-full shadow-lg transition" title="Play / pause (Space)"></button>
      <button id="btn-fwd" class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs font-semibold hover:bg-white/20 transition" title="Forward 10 s (→)">10<svg viewBox="0 0 24 24" class="h-3 w-3 fill-current"><path d="M13 6v12l8.5-6zM4 18l8.5-6L4 6z"/></svg></button>
      <button id="btn-next" class="flex h-10 flex-1 min-w-[90px] items-center justify-center gap-1 rounded-full bg-white/10 px-2.5 text-xs font-semibold hover:bg-white/20 disabled:opacity-30 disabled:pointer-events-none transition shrink-0" title="Next song (N)">
        <span class="btn-nav-prefix text-stone-400 font-normal shrink-0">Next:</span>
        <span id="btn-next-label" class="btn-nav-text truncate font-bold text-stone-200">Queue empty</span>
        <svg viewBox="0 0 24 24" class="h-3.5 w-3.5 shrink-0 fill-current"><path d="M6 18l8.5-6L6 6v12zM16 6h2v12h-2z"/></svg>
      </button>
      <div id="custom-transport-controls" class="flex items-center gap-1.5 flex-wrap empty:hidden"></div>
    </div>

    <div class="border-t border-white/10 pt-2">
      <div id="guide-control" class="flex items-center gap-2 text-xs text-stone-300">
        <span class="guide-title font-semibold text-gold">Guide</span>
        <input id="guide" type="range" min="0" max="100" step="1" value="20" class="guide-slider tap w-1/4 min-w-[5.5rem] max-w-[7.5rem]">
        <span id="guide-value" class="w-8 text-right font-mono font-bold">20%</span>
        <span id="guide-note" class="hidden rounded-full bg-amber-900/70 px-2 py-0.5 text-[10px] text-amber-200"
              title="Set by the singer on their phone; moving the slider changes only this song">choice</span>
      </div>
    </div>
  </section>

  <aside id="tv-sidebar" class="panel flex min-h-0 flex-1 flex-col gap-3 p-4 overflow-hidden">
    <div class="flex items-center gap-2 shrink-0">
      <div class="flex min-w-0 flex-1 rounded-xl bg-black/50 p-1 ring-1 ring-white/10 text-xs font-bold gap-1">
        <button id="tab-side-upcoming" type="button" class="flex-1 flex items-center justify-center gap-1.5 rounded-lg py-1.5 transition-all bg-amber-400 text-stone-950 shadow-sm">
          <span>📋 Up next</span>
          <span id="queue-count" class="rounded-full bg-black/25 px-1.5 py-0.2 text-[10px] font-mono font-bold">0</span>
        </button>
        <button id="tab-side-played" type="button" class="flex-1 flex items-center justify-center gap-1.5 rounded-lg py-1.5 transition-all text-stone-400 hover:text-stone-200">
          <span>⏮ Played</span>
          <span id="played-count" class="rounded-full bg-white/10 px-1.5 py-0.2 text-[10px] font-mono font-bold">0</span>
        </button>
        <button id="tab-side-all" type="button" class="flex-1 flex items-center justify-center gap-1.5 rounded-lg py-1.5 transition-all text-stone-400 hover:text-stone-200">
          <span>📑 All</span>
          <span id="all-count" class="rounded-full bg-white/10 px-1.5 py-0.2 text-[10px] font-mono font-bold">0</span>
        </button>
      </div>
      <button id="queue-add" type="button" data-act="add" class="tap-square btn-gold grid h-9 w-9 shrink-0 place-items-center rounded-xl text-lg leading-none" title="Add a song (A or /)">＋</button>
    </div>

    <div id="side-lists" class="min-h-0 flex-1 overflow-y-auto pr-1 space-y-3">
      <div id="section-upcoming" class="space-y-2">
        <ul id="queue" class="space-y-2"></ul>
        <p id="queue-empty" class="text-stone-400 text-xs text-center py-4">The queue is empty — tap ＋ or grab your phone!</p>
        <div id="autodj-mount"></div>
      </div>
      <div id="section-played" class="hidden space-y-2">
        <ul id="played-list" class="space-y-2"></ul>
        <p id="played-empty" class="text-stone-400 text-xs text-center py-4">No songs have played yet</p>
      </div>
      <div id="section-all" class="hidden space-y-3">
        <div id="all-now-box" class="space-y-1.5">
          <p class="text-[11px] font-bold uppercase tracking-wider text-amber-400">Now Singing</p>
          <div id="all-now-card"></div>
        </div>
        <div class="space-y-1.5">
          <p class="text-[11px] font-bold uppercase tracking-wider text-stone-400">Up Next (<span id="all-up-count">0</span>)</p>
          <ul id="all-queue-list" class="space-y-2"></ul>
        </div>
        <div class="space-y-1.5">
          <p class="text-[11px] font-bold uppercase tracking-wider text-stone-400">Already Played (<span id="all-played-count">0</span>)</p>
          <ul id="all-played-list" class="space-y-2"></ul>
        </div>
      </div>
    </div>
  </aside>`;
document.querySelectorAll("#col-right [data-icon]").forEach((b) => setIcon(b, b.dataset.icon));
