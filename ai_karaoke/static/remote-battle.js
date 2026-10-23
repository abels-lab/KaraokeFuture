// Guest phone: Battle / Duet. On somebody else's battle song you can join as the second singer
// (mic 2) — while it waits in the queue, or during its intro countdown once it's on stage. The
// second singer, the song's owner and the host can free mic 2 again. The server decides
// (routers/battle.py); these buttons only appear where it will likely say yes.
// Needs common.js + auth.js. Battle.controls(entry, {playing}) -> elements for a row / the
// now-playing card; Battle.onIntro(msg) with every "intro" message from the control panel.
const Battle = (() => {
  let intro = { uid: null, left: 0, at: 0 };
  const listeners = [];
  const me = () => Auth.me.guest;
  const inIntro = (uid) => intro.uid === uid && intro.left > 0 && performance.now() - intro.at < 1500;

  const join = (e) => api(`/api/queue/${e.uid}/join`, { method: "POST" })
    .then(() => toast(`You're singing with ${e.singer} — grab mic 2!`)).catch(fail);
  const leave = (e) => api(`/api/queue/${e.uid}/partner`, { method: "DELETE" })
    .then(() => toast("Mic 2 is free again")).catch(fail);

  function controls(e, { playing = false } = {}) {
    if (e?.mode !== "battle") return [];
    const open = !playing || inIntro(e.uid);   // a song already under way can't be joined
    const mine = Boolean(me() && e.partner?.id === me().id);
    if (e.partner && open && (mine || Auth.me.admin || Auth.owns(e))) {
      return [iconButton(mine ? "Leave battle" : "Free mic 2", mine ? "Don't sing this one after all" : `Remove ${e.partner.name} from this song`,
        () => leave(e), "hover:bg-red-800")];
    }
    if (!e.partner && open && me() && !Auth.owns(e)) {
      return [iconButton(playing ? "⚔️ Join before it starts!" : "⚔️ Join", `Sing this with ${e.singer} on mic 2`, () => join(e), "bg-teal-700 font-semibold hover:bg-teal-600")];
    }
    if (!e.partner && open) return [el("span", "shrink-0 rounded-full bg-teal-900/60 px-2 py-0.5 text-[11px] text-teal-200", "⚔️ mic 2 free")];
    return [];
  }

  function onIntro(m) {
    intro = { uid: m.uid, left: Number(m.left) || 0, at: performance.now() };
    listeners.forEach((fn) => fn(intro));
  }
  // The countdown's last message may never come (control panel closed): re-check now and then
  setInterval(() => { if (intro.uid && !inIntro(intro.uid)) { intro.uid = null; listeners.forEach((fn) => fn(intro)); } }, 1000);

  return { controls, onIntro, inIntro, onChange: (fn) => listeners.push(fn) };
})();
