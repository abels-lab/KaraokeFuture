// "Party & host PIN" block of the settings panel: the host PIN (set or changed only on the
// laptop) and "Wipe Party DB" (the host, on any device). Moved here from the settings page's
// party-admin.js so it no longer needs page ids. The server enforces both rules itself.
// Needs common.js and auth.js. createPartyPanel() -> <section> that repaints on every Auth change.
function createPartyPanel() {
  const box = el("section", "panel space-y-3 p-4");
  box.innerHTML = `
    <h2 class="font-display text-xl font-bold text-gold">Party &amp; host PIN</h2>
    <p data-k="status" class="text-sm text-stone-300"></p>
    <form data-k="pin-form" class="hidden flex flex-wrap gap-2">
      <input data-k="pin" type="password" inputmode="numeric" pattern="\\d{4,12}" maxlength="12" required autocomplete="new-password"
             placeholder="New PIN (4–12 digits)" class="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/50 px-3 py-2 font-mono outline-none focus:border-amber-400">
      <button class="btn-gold rounded-xl px-4 py-2 text-sm">Save PIN</button>
    </form>
    <div data-k="wipe-box" class="hidden flex flex-wrap items-center gap-3 border-t border-white/10 pt-3">
      <p class="min-w-[14rem] flex-1 text-sm text-stone-400">New party? Forget every guest login and their waiting songs.
        Cached songs, lyrics, settings and the host PIN stay.</p>
      <button data-k="wipe" type="button" class="rounded-xl bg-red-900/70 px-4 py-2 text-sm font-semibold hover:bg-red-800">🧹 Wipe Party DB</button>
    </div>`;
  const part = (k) => box.querySelector(`[data-k="${k}"]`);

  function paint({ admin, laptop, pin_set: pinSet }) {
    part("status").textContent = !pinSet
      ? (laptop ? "No host PIN yet: only this laptop can manage the party. Set one to manage it from your phone too."
                : "No host PIN yet — only the laptop running the karaoke can manage the party.")
      : laptop ? "A host PIN is set. Changing it signs every other device out of host mode."
      : admin ? "Host mode is on for this device (the PIN can only be changed on the laptop)."
      : "Enter the host PIN to manage the party from this device.";
    part("pin-form").classList.toggle("hidden", !laptop);
    part("wipe-box").classList.toggle("hidden", !admin);
  }

  part("pin-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      Auth.set(await api("/api/auth/pin", { method: "PUT", body: { pin: part("pin").value } }));
      part("pin").value = "";
      toast("Host PIN saved");
    } catch (err) { fail(err); }
  };

  part("wipe").onclick = async () => {
    if (!(await Confirm.ask({ title: "Wipe the party?", ok: "🧹 Wipe Party DB", type: "WIPE",
      message: "Every guest login and session is deleted and their waiting songs leave the queue. This can't be undone.\n"
        + "Cached songs, lyrics, settings and the host PIN stay." }))) return;
    try {
      const { guests, songs_removed: removed } = await api("/api/party/wipe", { method: "POST" });
      toast(`Party wiped: ${guests} guest${guests === 1 ? "" : "s"}, ${removed} queued song${removed === 1 ? "" : "s"} removed`);
      Auth.load();
    } catch (err) { fail(err); }
  };

  Auth.onChange(paint);
  paint(Auth.me);
  return box;
}
