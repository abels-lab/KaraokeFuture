// Control panel sidebar and controls: the queue with each singer's choices, projector count,
// transport buttons, keyboard shortcuts and the QR code. Load just BEFORE tv.js: its handlers
// use tv.js's player (play, seekTo, send…) only when clicked, while tv.js's first WebSocket
// message already needs renderSide.
function renderSide(queue, screens) {
  $("screens").textContent = screens ? `📽 ${screens} projector screen${screens > 1 ? "s" : ""} connected` : "No projector screen connected";
  $("screens").classList.toggle("text-emerald-400", screens > 0);
  $("queue-count").textContent = queue.length;
  $("queue-empty").classList.toggle("hidden", queue.length > 0);
  $("queue").replaceChildren(...queue.map((e, i) => queueRow(e, i, queue.length, { extras: choiceBadge(e) })));
}
// The singer's own choices for their song (set on their phone), shown to the host
const MODE_LABEL = { party: "✨", score: "🏆", battle: "⚔️" };
const choiceBadge = (e) => (e.mode || Number.isFinite(e.guide)
  ? [el("span", "shrink-0 text-[11px] text-stone-300", [MODE_LABEL[e.mode], Number.isFinite(e.guide) ? `🗣${e.guide}%` : ""].filter(Boolean).join(" "))]
  : []);

// ── Controls & startup (guide-vocal slider: guide.js) ─────────────────────
$("btn-play").onclick = () => (inst.paused ? play() : pause());
$("btn-restart").onclick = () => onControl("restart");
$("btn-back").onclick = () => seekTo(inst.currentTime - 10);
$("btn-fwd").onclick = () => seekTo(inst.currentTime + 10);
$("btn-skip").onclick = () => send({ type: "control", action: "skip" });
$("unlock").onclick = () => {
  $("unlock").classList.add("hidden");
  play();
  // Audio input also needs this first click; restart the mics if they were on last time
  if (store("micsOn") === "1") Mics.start().then(() => micStrip?.render()).catch((err) => toast(`Microphones: ${err.message}`, false));
};
$("open-mics").onclick = () => openMicSetup();
// Both are settings for every screen (this laptop is host): music video on / off, lyrics mode
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
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" && e.target.type !== "range") return;
  if (IntroRun.running && (e.key === "Enter" || e.key === "Escape")) { e.preventDefault(); IntroRun.skip(); }
  else if (e.code === "Space") { e.preventDefault(); $("btn-play").click(); }   // during the intro: start now
  else if (e.key === "ArrowLeft") { e.preventDefault(); seekTo(inst.currentTime - 5); }
  else if (e.key === "ArrowRight") { e.preventDefault(); seekTo(inst.currentTime + 5); }
  else if (e.key === "n") $("btn-skip").click();
  else if (e.key === "v") $("btn-video").click();
  else if (e.key === "l") $("btn-lyrics").click();
  else if (e.key === "f") document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
});

api("/api/info").then(({ qr, remote_url: url }) => {
  $("qr").src = $("qr-big").src = qr; $("qr-url").textContent = $("qr-url-big").textContent = url;
});
// First run: until a host PIN exists only this laptop can manage the party
api("/api/auth/me").then(({ pin_set: pinSet }) => $("pin-hint").classList.toggle("hidden", pinSet)).catch(() => {});
Guide.refresh();
