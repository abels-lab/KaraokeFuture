// End-of-song results card. Party: always positive, "% good vocalist" (never below 52).
// Hard: points, stats, winner, and a verdict — honest levels, or (opt-in) roast metaphors.
const PARTY_TITLES = [
  [0.85, "Superstar!", "The crowd is on its feet"], [0.7, "Natural talent", "Smooth, confident, golden"],
  [0.5, "Rising star", "That's how legends start"], [0, "Brave soul", "Pure fun — and that's what counts"],
];
const VERDICTS = [ // [threshold, roast metaphor, plain level]
  [0.9, "Opera diva 🎭", "Professional level"], [0.78, "Studio vocalist 🎙️", "Advanced"],
  [0.65, "Pub legend 🍻", "Solid"], [0.5, "Shower star 🚿", "Getting there"],
  [0.35, "Car-radio crooner 🚗", "Beginner"], [0.2, "Cat on a hot tin roof 🐈", "Beginner"],
  [0, "A dying duck 🦆", "Keep practising"],
];
const partyPercent = (overall) => {   // never below the Settings page's party minimum (default 52)
  const floor = Math.min(98, Settings.get("party_min_percent", 52));
  return Math.round(floor + (98 - floor) * Math.min(1, overall / 0.85));
};
const pick = (table, x) => table.find(([min]) => x >= min);
const pct = (x) => (x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`);

function resultsCard({ mode, roast, results }) {
  const card = el("div", "panel mx-auto flex max-w-5xl flex-col items-center gap-6 px-10 py-8 text-center");
  card.append(el("p", "text-sm font-semibold uppercase tracking-[0.35em] text-gold", mode === "hard" ? "Final score" : "What a performance"));
  const row = el("div", "flex flex-wrap justify-center gap-10");
  const ranked = [...results].sort((a, b) => b.points - a.points);
  results.forEach((r, i) => {
    const col = el("div", "flex min-w-[14rem] flex-col items-center gap-1");
    col.append(el("p", "font-display text-3xl font-bold", r.name));
    if (mode === "hard") {
      const [, metaphor, level] = pick(VERDICTS, r.overall);
      const points = el("p", "font-display text-7xl font-black", r.points.toLocaleString());
      points.style.color = PLAYER_COLORS[i];
      col.append(points, el("p", "text-2xl font-semibold text-gold", roast ? metaphor : level),
        el("p", "font-mono text-sm text-stone-300",
          `pitch ${pct(r.pitch)} · timing ${pct(r.timing)} · dynamics ${pct(r.amp)}`),
        el("p", "font-mono text-sm text-stone-400", `notes ${r.notesHit}/${r.notesTotal} · best combo ${r.bestStreak}`));
    } else {
      const [, title, line] = pick(PARTY_TITLES, r.overall);
      col.append(el("p", "font-display text-8xl font-black text-gold mic-glow", `${partyPercent(r.overall)}%`),
        el("p", "text-sm uppercase tracking-widest text-stone-300", "good vocalist"),
        el("p", "mt-2 text-3xl font-bold", title), el("p", "text-lg text-stone-300", line));
    }
    row.append(col);
  });
  card.append(row);
  if (mode === "hard" && ranked.length > 1 && ranked[0].points !== ranked[1].points) {
    card.append(el("p", "text-2xl font-bold text-gold",
      `🏆 ${ranked[0].name} wins by ${(ranked[0].points - ranked[1].points).toLocaleString()} points`));
  }
  return card;
}
