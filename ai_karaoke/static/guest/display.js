// Small per-device display options from the guest ⚙ popup, kept in this browser (localStorage):
// larger text (html.guest-big, guest/layout.css) and keeping the screen awake while your song
// is on stage or up next (the Wake Lock API: only on https:// pages and in browsers that have
// it, so on the plain-HTTP Wi-Fi link the option says why it is off).
// Needs common.js (el, store, toast).
// GuestDisplay.mySongUp(bool) with every queue update; GuestDisplay.editor() -> block for ⚙.
const GuestDisplay = (() => {
  const supported = "wakeLock" in navigator;
  const on = (k) => store(k) === "1";
  let lock = null, asking = false, wanted = false;

  const applyBig = () => document.documentElement.classList.toggle("guest-big", on("guest_big_text"));
  applyBig();

  // Hold the lock only while it is wanted and the page is in front (hidden pages lose it anyway)
  async function sync() {
    const want = supported && wanted && on("guest_wake") && document.visibilityState === "visible";
    if (want && !lock && !asking) {
      asking = true;
      try {
        lock = await navigator.wakeLock.request("screen");
        lock.addEventListener("release", () => { lock = null; });
      } catch { lock = null; }
      asking = false;
      if (!(wanted && on("guest_wake"))) sync();   // changed while we were asking
    } else if (!want && lock) {
      const old = lock;
      lock = null;
      old.release().catch(() => {});
    }
  }
  document.addEventListener("visibilitychange", sync);

  function mySongUp(yes) {
    if (wanted === Boolean(yes)) return;
    wanted = Boolean(yes);
    sync();
  }

  function toggle(label, help, key, onSet, disabled = false) {
    const row = el("label", `flex items-start gap-3 py-1 ${disabled ? "opacity-50" : "cursor-pointer"}`);
    const box = Object.assign(el("input", "mt-1 h-5 w-5 shrink-0 accent-amber-400"), { type: "checkbox", checked: on(key), disabled });
    box.onchange = () => { store(key, box.checked ? "1" : "0"); onSet(); };
    const text = el("span", "min-w-0 text-sm");
    text.append(el("span", "block font-semibold text-stone-200", label), el("span", "block text-xs text-stone-400", help));
    row.append(box, text);
    return row;
  }

  function editor() {
    const box = el("div", "space-y-2");
    box.append(
      toggle("Larger text", "Bigger letters and buttons on this device.", "guest_big_text", applyBig),
      toggle("Keep the screen awake for my song",
        supported ? "While your song is on stage or up next, this phone won't dim or lock."
          : "Not available here: it needs the secure https:// link and a browser that supports it.",
        "guest_wake", () => { sync(); if (on("guest_wake")) toast("The screen stays on while your song is up"); }, !supported));
    return box;
  }

  return { mySongUp, editor };
})();
