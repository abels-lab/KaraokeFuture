// Something to laugh at while the next song is prepared ("Jokes while loading" setting): memes
// from static/img/fun and quips about the step the song is at, a new one every JOKE_SECONDS.
// The projector alternates memes and quips; the control panel's small card only shows quips.
// Needs common.js. createJokes(slot, compact) -> { run(shown, status) }
const JOKE_SECONDS = 9;
const QUIPS = {
  queued: ["Your song is in line. Use the time to pick your signature move.",
           "Karaoke rule #1: confidence beats pitch. Rule #2: see rule #1."],
  downloading: ["Fetching the track from the internet's jukebox…",
                "Downloading. Please don't start the chorus yet."],
  separating: ["Politely asking the original singer to leave the stage.",
               "Removing the vocals. The original singer is not taking it well.",
               "One 6 GB laptop GPU, doing the work of a whole recording studio."],
  aligning: ["Teaching the lyrics to keep up with the beat.",
             "Counting syllables so you don't have to."],
  melody: ["Writing down every note, so the game can judge you later.",
           "Measuring the melody. Hard-mode singers: start stretching."],
  any: ["Hydrate. The high notes are coming.", "Everyone sounds better after the second song.",
        "The guide-vocal slider is your friend. No judgement.", "Fun fact: the shower counts as rehearsal."],
};
const MEMES = [
  { img: "/static/img/fun/hank.jpg", top: "Every song in the world as karaoke", bottom: "…processed locally on my laptop's GPU" },
  { video: "/static/img/fun/servers.mp4", caption: "Meet the backstage crew. They work for electricity and applause." },
  { video: "/static/img/fun/flaming-mic.mp4", caption: "The last singer hit the high note. We're still putting out the mic." },
  { video: "/static/img/fun/club-lights.mp4", caption: "Lights: ready. Fog machine: ready. Your courage: buffering…" },
];

function createJokes(slot, compact) {
  let timer = null, status = "queued", turn = 0;
  const pick = (list) => list[Math.floor(Math.random() * list.length)];
  const quip = () => el("p", `italic text-stone-200 ${compact ? "text-sm" : "text-[clamp(1rem,1.6vw,1.8rem)]"}`,
    `“${pick([...(QUIPS[status] || []), ...QUIPS.any])}”`);

  function meme(m) {
    const box = el("figure", "mx-auto w-fit max-w-full space-y-2");
    if (m.img) {   // two-panel meme: a caption bar under each half, classic bold white letters
      const pic = el("div", "mx-auto w-fit overflow-hidden rounded-2xl bg-black ring-1 ring-white/15");   // as wide as the picture
      const bars = el("div", "grid w-0 min-w-full grid-cols-2 text-center font-black uppercase leading-tight text-white text-[clamp(.75rem,1.15vw,1.4rem)]");
      bars.append(el("p", "px-2 py-[1vh]", m.top), el("p", "px-2 py-[1vh]", m.bottom));
      pic.append(Object.assign(el("img", "block max-h-[24vh] w-auto"), { src: m.img, alt: "" }), bars);
      box.append(pic);
    } else {
      box.append(Object.assign(el("video", "max-h-[24vh] rounded-2xl ring-1 ring-white/15"),
        { src: m.video, autoplay: true, muted: true, loop: true, playsInline: true }));
      box.append(el("figcaption", "text-center text-[clamp(.9rem,1.4vw,1.6rem)] font-semibold text-stone-100", m.caption));
    }
    return box;
  }

  function show() {
    turn++;
    slot.replaceChildren(compact || turn % 2 ? quip() : meme(MEMES[(turn / 2) % MEMES.length]));
  }

  function run(shown, nextStatus) {
    status = nextStatus === "waiting" ? "queued" : nextStatus;
    if (!shown || !Settings.get("loading_jokes", true)) {
      clearInterval(timer); timer = null; slot.replaceChildren();
      return;
    }
    if (!timer) { turn = Math.floor(Math.random() * MEMES.length) * 2 + 1; show(); timer = setInterval(show, JOKE_SECONDS * 1000); }
  }
  return { run };
}
