// Host app frame: the header (tablet + laptop: Stage / Library tabs, ＋ Add song, Settings, the
// Co-Pilot drawer button on tablets, player / controller chip, host badge) and the phone's bottom
// tab bar (Stage · Queue · ＋ Add · Co-Pilot · More). Markup only, written into the empty
// #host-header / #host-tabs of host.html before any script that looks for these ids runs.
// Buttons say what they do with data-go="<view>" (host/router.js) or data-act="<action>"
// (host/views.js); nothing is wired here. Needs nothing.
document.getElementById("host-header").innerHTML = `
  <img src="/static/img/microphone.png" alt="" class="mic-glow h-8 w-auto -rotate-12 shrink-0">
  <span class="hide-tablet font-display truncate text-lg font-black text-gold max-w-[14rem]" data-title>Karaoke Night</span>
  <nav class="flex shrink-0 gap-1 rounded-xl bg-black/50 p-1 text-sm font-bold ring-1 ring-white/10" aria-label="Views">
    <button type="button" data-go="stage" class="host-nav rounded-lg px-3 py-1.5" title="Control panel">🎤 Stage</button>
    <button type="button" data-go="library" class="host-nav rounded-lg px-3 py-1.5" title="Song library (B)">📚 Library</button>
  </nav>
  <div class="min-w-0 flex-1"></div>
  <button type="button" data-act="custom" class="shrink-0 rounded-xl bg-amber-500/10 border border-amber-400/30 px-3 py-1.5 text-sm font-semibold text-gold hover:bg-amber-500/20" title="Upload audio file or link">📁 Load song</button>
  <button type="button" data-act="add" class="btn-gold shrink-0 rounded-xl px-3 py-1.5 text-sm" title="Add a song to the queue (A or /)">＋ Add song</button>
  <button type="button" data-go="copilot" class="only-tablet shrink-0 rounded-xl bg-white/10 px-3 py-1.5 text-sm font-semibold hover:bg-white/20" title="DJ Co-Pilot (Ctrl+J)">✨ Co-Pilot</button>
  <button type="button" data-act="settings" class="shrink-0 rounded-xl bg-white/10 px-3 py-1.5 text-sm font-semibold hover:bg-white/20" title="Settings (,)">⚙️<span class="hide-tablet"> Settings</span></button>
  <button type="button" data-act="mode" data-mode-chip class="shrink-0 rounded-xl bg-white/10 px-3 py-1.5 text-sm font-semibold hover:bg-white/20"></button>
  <span id="host-badge-slot" class="shrink-0"></span>`;

document.getElementById("host-tabs").innerHTML = `
  <button type="button" data-go="stage" class="host-tab"><span class="text-xl">🎤</span><span>Stage</span></button>
  <button type="button" data-go="queue" class="host-tab"><span class="text-xl">📋</span><span>Queue</span></button>
  <button type="button" data-act="add" class="host-tab host-tab-add"><span class="text-2xl leading-none">＋</span><span>Add</span></button>
  <button type="button" data-go="copilot" class="host-tab"><span class="text-xl">✨</span><span>Co-Pilot</span></button>
  <button type="button" data-act="more" class="host-tab"><span class="text-xl">☰</span><span>More</span></button>`;
