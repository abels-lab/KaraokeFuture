// Control panel, centre column: the stage preview (#idle when nobody sings, #stage with the
// muted video + lyrics while a song plays), the display / game / microphone controls and the
// navigation card. Markup only, written into host.html's empty #col-center before the scripts
// that use these ids (tv-now.js, tv-side.js, game-panel.js, intro-run.js, mic-setup.js). The ids
// are a contract with those scripts and the Co-Pilot's hide / show tool: never rename one.
// #hw-controls (microphones, game) is the player's: host/host.css hides it in controller mode.
// Needs nothing.
document.getElementById("col-center").innerHTML = `
  <div id="preview-card" class="panel relative flex min-h-0 flex-1 flex-col overflow-hidden">
    <section id="idle" class="flex flex-1 flex-col items-center justify-center p-6 text-center transition-all">
      <img id="idle-mic" src="/static/img/microphone.png" alt="" class="mic-glow w-40 -rotate-6 transition-all duration-300">
      <h1 class="font-display mt-4 text-4xl font-black text-gold transition-all duration-300" data-title>Golden Mic Karaoke</h1>
      <p class="mt-2 text-lg text-stone-200 transition-all duration-300">Scan with your phone and pick a song</p>
      <div id="idle-qr-panel" class="hidden">
        <img id="qr-big" alt="" class="hidden">
        <p id="qr-url-big" class="hidden"></p>
      </div>
      <section id="loading" class="mt-4 hidden w-full justify-center max-h-[35vh] overflow-y-auto scrollbar-none"></section>
    </section>

    <section id="stage" class="hidden flex min-h-0 flex-1 flex-col h-full w-full">
      <div id="monitor" class="relative min-h-0 flex-1 w-full h-full overflow-hidden rounded-2xl">
        <video id="stage-video" muted playsinline preload="auto"
               class="absolute inset-0 h-full w-full object-cover opacity-0 transition-opacity duration-700"></video>
        <div class="absolute inset-0 video-shade"></div>
        <div data-lyrics-box class="lyric-shadow relative flex h-full flex-col items-center justify-end gap-4 px-8 pb-8 text-center">
          <p id="countdown" class="min-h-[2rem] text-2xl font-bold text-gold"></p>
          <p id="line-main" class="text-[clamp(1.4rem,2.5vw,2.6rem)] font-extrabold leading-tight transition-opacity"></p>
          <p id="line-next" class="text-[clamp(1.4rem,2.5vw,2.6rem)] font-extrabold leading-tight transition-opacity"></p>
          <p id="no-lyrics" class="hidden text-2xl text-stone-200">No lyrics found — freestyle! 🎶</p>
        </div>
      </div>
    </section>
  </div>

  <div id="display-panel" class="panel p-3.5 space-y-2.5 shrink-0">
    <div class="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-gold">
      <span>Display & Hardware Controls</span>
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
      <button id="btn-video" class="tap flex items-center justify-center gap-1.5 rounded-lg bg-white/10 px-3 py-2 text-xs font-semibold text-stone-200 hover:bg-white/20 transition" title="Music video on / off (V)">
        🎬 Video on / off
      </button>
      <button id="btn-lyrics" class="tap flex items-center justify-center gap-1.5 rounded-lg bg-white/10 px-3 py-2 text-xs font-semibold text-stone-200 hover:bg-white/20 transition" title="Lyrics: highlighted → plain → off (L)">
        📝 Lyrics: <span id="lyrics-mode"></span>
      </button>
      <button id="open-screen" class="tap btn-gold flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs transition shadow-sm" title="Open projector screen in new window">
        📽 Projector screen
      </button>
    </div>
    <p id="screens" class="text-center text-xs text-stone-400">No projector screen connected</p>

    <!-- Dynamic Co-Pilot Custom Controls (SFX, settings toggles, custom buttons) -->
    <div id="custom-controls" class="flex flex-wrap gap-2 empty:hidden"></div>

    <div id="hw-controls" class="border-t border-white/10 pt-2 space-y-2">
      <div id="game-controls" class="flex items-center gap-2">
        <button id="open-mics" class="tap flex-1 rounded-lg bg-white/10 px-3 py-2 text-sm font-semibold text-stone-200 hover:bg-white/20">🎤 Microphones</button>
      </div>
      <div id="mic-live" class="hidden space-y-1 text-xs"></div>
    </div>
  </div>

  <div id="nav-panel" class="panel p-3.5 space-y-2.5 shrink-0 text-xs">
    <div class="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-gold">
      <span>Navigation & Shortcuts</span>
    </div>
    <div class="flex items-center justify-between gap-2 flex-wrap">
      <div class="flex items-center gap-2 flex-wrap">
        <a href="#library" data-go="library" class="tap inline-flex items-center rounded-lg bg-white/10 px-3 py-1.5 font-semibold text-stone-200 hover:bg-white/20 transition">📚 Library</a>
        <a href="/settings" data-act="settings" class="tap inline-flex items-center rounded-lg bg-white/10 px-3 py-1.5 font-semibold text-stone-200 hover:bg-white/20 transition" title="Settings">⚙️ Settings</a>
        <a href="/remote" target="_blank" class="tap inline-flex items-center rounded-lg bg-white/10 px-3 py-1.5 font-semibold text-stone-200 hover:bg-white/20 transition" title="Remote control">📱 Remote</a>
        <a id="support-link" href="https://github.com/sponsors/abels-lab" target="_blank" rel="noopener" class="tap inline-flex items-center rounded-lg bg-amber-500/15 border border-amber-400/30 px-3 py-1.5 font-semibold text-gold hover:bg-amber-500/25 transition" title="Support AI Karaoke / Buy the creator a coffee">☕ Buy me a coffee</a>
      </div>
      <span class="hide-phone font-mono text-stone-400 text-[11px]" title="Space play/pause · P/N previous/next · ←/→ seek · V video · L lyrics · F fullscreen · A or / add song · B library · , settings">Space · P / N · ← → · V · L · F · A · B</span>
    </div>

    <div id="custom-nav-controls" class="flex flex-wrap gap-2 empty:hidden"></div>

    <a id="pin-hint" href="/settings" data-act="settings" class="hidden block rounded-lg bg-amber-900/50 px-3 py-2 text-center text-amber-200 hover:bg-amber-900/70 transition">
      🔑 Set a host PIN to manage the party from your phone
    </a>
  </div>`;
