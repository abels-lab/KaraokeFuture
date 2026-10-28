// Control panel sidebar and controls: the queue with each singer's choices, projector count,
// transport buttons, display buttons and the QR code. Same in player and controller mode: the
// buttons talk to the Deck (tv.js or host/controller.js, set by host/boot.js) only when clicked.
// Needs common.js, auth.js, guide.js, mics.js, mic-setup.js and the markup (host/markup-*.js).
// Exposes renderSide(queue, played, screens, current) for both decks' "state" handling.

let activeSideTab = "upcoming"; // "upcoming" | "played" | "all"
function setSideTab(tab) {
  activeSideTab = tab;
  const isUp = tab === "upcoming", isPlayed = tab === "played", isAll = tab === "all";
  $("section-upcoming")?.classList.toggle("hidden", !isUp);
  $("section-played")?.classList.toggle("hidden", !isPlayed);
  $("section-all")?.classList.toggle("hidden", !isAll);

  const activeCls = "flex-1 flex items-center justify-center gap-1.5 rounded-lg py-1.5 transition-all bg-amber-400 text-stone-950 shadow-sm";
  const idleCls = "flex-1 flex items-center justify-center gap-1.5 rounded-lg py-1.5 transition-all text-stone-400 hover:text-stone-200";

  if ($("tab-side-upcoming")) $("tab-side-upcoming").className = isUp ? activeCls : idleCls;
  if ($("tab-side-played")) $("tab-side-played").className = isPlayed ? activeCls : idleCls;
  if ($("tab-side-all")) $("tab-side-all").className = isAll ? activeCls : idleCls;
}
$("tab-side-upcoming")?.addEventListener("click", () => setSideTab("upcoming"));
$("tab-side-played")?.addEventListener("click", () => setSideTab("played"));
$("tab-side-all")?.addEventListener("click", () => setSideTab("all"));

function renderSide(queue = [], played = [], screens = 0, current = null) {
  $("screens").textContent = screens ? `📽 ${screens} projector screen${screens > 1 ? "s" : ""} connected` : "No projector screen connected";
  $("screens").classList.toggle("text-emerald-400", screens > 0);

  const totalAll = queue.length + played.length + (current ? 1 : 0);
  if ($("queue-count")) $("queue-count").textContent = queue.length;
  if ($("played-count")) $("played-count").textContent = played.length;
  if ($("all-count")) $("all-count").textContent = totalAll;
  if ($("all-up-count")) $("all-up-count").textContent = queue.length;
  if ($("all-played-count")) $("all-played-count").textContent = played.length;

  // Previous song button with real label
  const prev = played.length > 0 ? played[played.length - 1] : null;
  if ($("btn-prev")) {
    $("btn-prev").disabled = !prev;
    if ($("btn-prev-label")) $("btn-prev-label").textContent = prev ? prev.title : "None";
    $("btn-prev").title = prev ? `Previous: ${prev.title} (${singers(prev)}) (P)` : "No previous song in history";
  }

  // Next song button with real label
  const next = queue.length > 0 ? queue[0] : null;
  if ($("btn-next")) {
    $("btn-next").disabled = !next;
    if ($("btn-next-label")) $("btn-next-label").textContent = next ? next.title : "Queue empty";
    $("btn-next").title = next ? `Next: ${next.title} (${singers(next)}) (N)` : "No upcoming song";
  }

  // 1. Upcoming list
  if ($("queue-empty")) $("queue-empty").classList.toggle("hidden", queue.length > 0);
  if ($("queue")) $("queue").replaceChildren(...queue.map((e, i) => queueRow(e, i, queue.length, { extras: choiceBadge(e) })));

  // 2. Played list (most recently played first)
  const revPlayed = [...played].reverse();
  if ($("played-empty")) $("played-empty").classList.toggle("hidden", played.length > 0);
  if ($("played-list")) $("played-list").replaceChildren(...revPlayed.map((e, i) => playedRow(e, i)));

  // 3. Whole queue timeline (All)
  if ($("all-now-card")) {
    if (current) {
      const card = el("div", "flex items-center gap-3 rounded-xl bg-amber-500/15 p-2.5 ring-1 ring-amber-400/40");
      card.append(Object.assign(el("img", "h-11 w-14 shrink-0 rounded-lg object-cover ring-1 ring-amber-400/50"), {
        src: current.thumbnail || thumbFor(current.song_id), alt: ""
      }));
      const cinfo = el("div", "min-w-0 flex-1 space-y-0.5");
      cinfo.append(
        el("p", "truncate text-xs font-bold text-amber-200", current.title),
        el("p", "truncate text-[11px] text-stone-300", `🎤 ${singers(current)}`)
      );
      card.append(cinfo, el("span", "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold bg-amber-400 text-stone-950", "Now Singing"));
      $("all-now-card").replaceChildren(card);
      $("all-now-box")?.classList.remove("hidden");
    } else {
      $("all-now-box")?.classList.add("hidden");
    }
  }
  if ($("all-queue-list")) $("all-queue-list").replaceChildren(...queue.map((e, i) => queueRow(e, i, queue.length, { extras: choiceBadge(e) })));
  if ($("all-played-list")) $("all-played-list").replaceChildren(...revPlayed.map((e, i) => playedRow(e, i)));
}

// The singer's own choices for their song (set on their phone), shown to the host
const MODE_LABEL = { party: "✨", score: "🏆", battle: "⚔️" };
const choiceBadge = (e) => (e.mode || Number.isFinite(e.guide)
  ? [el("span", "shrink-0 text-[11px] text-stone-300", [MODE_LABEL[e.mode], Number.isFinite(e.guide) ? `🗣${e.guide}%` : ""].filter(Boolean).join(" "))]
  : []);

// ── Controls & startup (guide-vocal slider: guide.js, keyboard: host/keys.js) ──
// Each button asks the Deck: the player acts at once, the controller asks the laptop (REST)
$("btn-prev").onclick = () => Deck?.prev();
$("btn-play").onclick = () => Deck?.toggle();
$("btn-restart").onclick = () => Deck?.restart();
$("btn-back").onclick = () => Deck?.seekBy(-10);
$("btn-fwd").onclick = () => Deck?.seekBy(10);
$("btn-next").onclick = () => Deck?.next();

$("unlock").onclick = () => {
  $("unlock").classList.add("hidden");
  Deck?.play();
  // Audio input also needs this first click; restart the mics if they were on last time
  if (store("micsOn") === "1") Mics.start().then(() => micStrip?.render()).catch((err) => toast(`Microphones: ${err.message}`, false));
};
$("open-mics").onclick = () => openMicSetup();

// Both are settings for every screen (only the host may change them): music video on / off, lyrics mode
const setLook = (values) => api("/api/settings", { method: "PUT", body: { values } }).then(() => Settings.load()).catch(fail);
const LYRICS_NEXT = { full: "plain", plain: "off", off: "full" }, LYRICS_LABEL = { full: "", plain: "plain", off: "off" };
$("btn-video").onclick = () => setLook({ show_video: !Settings.get("show_video", true) });
$("btn-lyrics").onclick = () => setLook({ lyrics_mode: LYRICS_NEXT[Settings.get("lyrics_mode", "full")] || "full" });
Settings.onChange(() => {
  $("btn-video").classList.toggle("opacity-40", !Settings.get("show_video", true));
  $("lyrics-mode").textContent = LYRICS_LABEL[Settings.get("lyrics_mode", "full")] || "";
});

// A separate window: drag it onto the projector, then click it (or press F) for fullscreen
$("open-screen").onclick = () => window.open("/screen", "karaoke-screen", "popup,width=1280,height=720");

api("/api/info").then(({ qr, remote_url: url }) => {
  $("qr").src = qr; $("qr-big").src = qr; $("qr-url").textContent = url; $("qr-url-big").textContent = url;
}).catch(() => {});
// First run: until a host PIN exists only this laptop can manage the party
Auth.onChange(({ pin_set: pinSet, laptop }) => $("pin-hint").classList.toggle("hidden", pinSet || !laptop));
Guide.refresh();
