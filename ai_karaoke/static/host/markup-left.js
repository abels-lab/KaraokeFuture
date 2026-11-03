// Control panel, left column: the "Join the queue" QR card and the DJ Co-Pilot chat (agent.js).
// Markup only, written into host.html's empty #col-left before the scripts that use these ids.
// The ids are a contract: tv-side.js, agent.js and the Co-Pilot's customize_control_panel tool
// (services/agent.py: hide / show by id) look for them, so never rename one.
// On a tablet the chat becomes a slide-over drawer (host/host.css), closed with #agent-close.
// Needs nothing.
document.getElementById("col-left").innerHTML = `
  <div id="qr-card" class="panel flex items-center gap-4 p-4 shrink-0">
    <img id="qr" alt="QR code" class="h-20 w-20 shrink-0 rounded-xl bg-white p-1 shadow-md">
    <div class="min-w-0 flex-1">
      <p class="font-display text-lg font-bold text-gold leading-snug">Join the queue</p>
      <p id="qr-url" class="break-all font-mono text-xs text-stone-300 mt-1"></p>
      <p class="text-[11px] text-stone-400 mt-0.5">Scan or visit link to pick songs</p>
    </div>
  </div>

  <aside id="agent-drawer" class="panel flex min-h-0 flex-1 flex-col overflow-hidden">
    <header class="flex items-center justify-between border-b border-white/10 px-4 py-3 shrink-0">
      <div class="flex items-center gap-2.5 min-w-0">
        <span class="text-xl shrink-0">✨</span>
        <div class="min-w-0">
          <h2 class="font-display text-base font-bold text-gold leading-tight truncate">DJ Co-Pilot</h2>
          <p class="text-[11px] text-stone-400 truncate">Queue songs, tweak styles & live actions</p>
        </div>
      </div>
      <div class="flex items-center gap-1 shrink-0">
        <!-- Legacy toggle buttons kept as hidden dummies so agent.js / external calls never error -->
        <button id="agent-mode-toggle" class="hidden" type="button"></button>
        <button id="agent-side-toggle" class="hidden" type="button"></button>
        <button id="agent-clear" class="tap-square rounded-lg p-1.5 text-stone-400 hover:bg-white/10 hover:text-stone-200 transition" title="Clear chat history" type="button">🗑️</button>
        <button id="agent-close" class="only-tablet tap-square rounded-lg bg-white/10 px-2.5 py-1.5 text-sm hover:bg-white/20" title="Close the Co-Pilot" type="button">✕</button>
      </div>
    </header>

    <div id="agent-messages" class="flex-1 space-y-3 overflow-y-auto p-4 scrollbar-none text-xs">
      <div class="rounded-xl bg-white/5 p-3 border border-white/10 text-stone-300 space-y-1.5">
        <p class="font-semibold text-gold">👋 Hey! I'm your Karaoke Co-Pilot.</p>
        <p>You can speak or type commands, for example:</p>
        <ul class="space-y-0.5 text-stone-400 list-disc list-inside">
          <li><i>"Queue Queen Bohemian Rhapsody for Alice"</i></li>
          <li><i>"Switch to adaptive theme with lime accent"</i></li>
          <li><i>"Skip the current song"</i></li>
        </ul>
      </div>
    </div>

    <footer class="border-t border-white/10 p-3 shrink-0">
      <form id="agent-form" class="flex items-center gap-2">
        <button type="button" id="agent-mic" class="grid h-10 w-10 tap-square shrink-0 place-items-center rounded-xl bg-white/10 text-lg transition hover:bg-white/20 active:scale-95 text-stone-300" title="Hold/click to speak (Voice DJ)">🎤</button>
        <input type="text" id="agent-input" class="min-w-0 flex-1 rounded-xl bg-white/10 px-3 py-2 text-xs text-stone-100 placeholder-stone-500 focus:outline-none focus:ring-2 focus:ring-amber-400 tap" placeholder="Ask DJ Co-Pilot or command..." autocomplete="off">
        <button type="submit" id="agent-send" class="grid h-10 w-10 tap-square shrink-0 place-items-center rounded-xl btn-gold text-base transition hover:brightness-110 active:scale-95 disabled:opacity-40" title="Send (Enter)">➤</button>
      </form>
    </footer>
  </aside>`;
