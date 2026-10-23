// Pre-song intro card, shared by the control panel and the projector: who sings what, in which
// mode, and a big 5…1 countdown. The control panel owns the countdown (intro-run.js); this file
// only draws what it is told, so every screen shows the same number at the same moment.
// Needs common.js. createIntro({hint}) -> { show({entry, left, mode, names}), hide(), visible }
const INTRO_MODES = { off: "🎤 Sing along", party: "✨ Party mode", hard: "🏆 Score mode", battle: "⚔️ Battle / Duet" };

function createIntro({ hint = false } = {}) {
  const card = el("div", "fixed inset-0 z-40 hidden cursor-pointer flex-col items-center justify-center gap-[2.5vh] bg-black/80 p-8 text-center backdrop-blur-sm");
  card.innerHTML = `
    <p data-i="mode" class="rounded-full bg-amber-400/15 px-5 py-1.5 text-[clamp(.9rem,1.5vw,1.6rem)] font-bold uppercase tracking-[0.3em] text-gold ring-1 ring-amber-400/40"></p>
    <p class="text-[clamp(.8rem,1.2vw,1.3rem)] uppercase tracking-[0.45em] text-stone-300">Get ready</p>
    <h2 data-i="names" class="font-display max-w-[90%] text-[clamp(2rem,6vw,6.5rem)] font-black leading-tight"></h2>
    <p data-i="title" class="max-w-[85%] truncate text-[clamp(1.1rem,2.4vw,2.6rem)] font-semibold"></p>
    <p data-i="artist" class="max-w-[85%] truncate text-[clamp(.9rem,1.5vw,1.6rem)] text-stone-300"></p>
    <p data-i="count" class="font-display mic-glow text-[clamp(5rem,16vw,16rem)] font-black leading-none text-gold"></p>
    <p data-i="hint" class="text-sm text-stone-400">Click, or press Enter, to start now</p>`;
  document.body.append(card);
  const part = (k) => card.querySelector(`[data-i="${k}"]`);
  part("hint").classList.toggle("hidden", !hint);
  let shownCount = null;

  // Battle: both mic names face off ("Player 2" until somebody joins); otherwise the singer(s)
  function nameLine(entry, mode, names) {
    if (mode !== "battle") return singers(entry);
    const [one, two] = names?.length ? names : [entry.singer];
    return `${one} ⚔️ ${two || entry.partner?.name || "Player 2"}`;
  }

  function show({ entry, left, mode, names }) {
    if (!entry) return;
    part("mode").textContent = INTRO_MODES[mode] || INTRO_MODES.off;
    part("names").textContent = nameLine(entry, mode, names);
    part("title").textContent = entry.title;
    part("artist").textContent = entry.channel || "";
    const count = Math.max(1, Math.ceil(left));
    if (count !== shownCount) {   // each new number pops in
      shownCount = count;
      part("count").textContent = count;
      part("count").animate?.([{ transform: "scale(1.5)", opacity: 0.2 }, { transform: "scale(1)", opacity: 1 }],
                              { duration: 380, easing: "cubic-bezier(.2,.9,.3,1.2)" });
    }
    card.classList.replace("hidden", "flex");
  }

  function hide() { shownCount = null; card.classList.replace("flex", "hidden"); }

  return { show, hide, card, get visible() { return card.classList.contains("flex"); } };
}
