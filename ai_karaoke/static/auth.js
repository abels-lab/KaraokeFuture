// Who this device is (host / logged-in guest / viewer) and the host-PIN dialog. Needs common.js.
// Pages only hide what they can't use; the server enforces every permission itself.
// Auth.me = {admin, laptop, guest: {id, name} | null, pin_set}; Auth.onChange(fn) after each load.
const Auth = (() => {
  let me = { admin: false, laptop: false, guest: null, pin_set: false };
  const listeners = [];
  const set = (m) => { me = m; listeners.forEach((fn) => fn(m)); return m; };
  const load = () => api("/api/auth/me").then(set).catch(() => me);

  // ── Host PIN dialog ─────────────────────────────────────────────────────────
  const m = el("div", "fixed inset-0 z-50 hidden items-end justify-center bg-black/75 p-3 sm:items-center");
  m.innerHTML = `
    <form class="panel w-full max-w-sm space-y-3 p-5">
      <h2 class="font-display text-xl font-bold text-gold">🔑 Host PIN</h2>
      <p data-k="hint" class="text-sm text-stone-300">Enter the host PIN to manage songs, lyrics, settings and the whole queue on this device.</p>
      <input data-k="pin" type="password" inputmode="numeric" autocomplete="off" pattern="\\d{4,12}" maxlength="12" required
        placeholder="PIN" class="w-full rounded-xl border border-white/10 bg-black/50 px-4 py-3 text-center font-mono text-2xl tracking-[0.4em] outline-none focus:border-amber-400">
      <div class="flex gap-2">
        <button type="button" data-k="cancel" class="flex-1 rounded-xl bg-white/10 py-3 font-semibold">Cancel</button>
        <button data-k="ok" class="btn-gold flex-1 rounded-xl py-3">Unlock</button>
      </div>
    </form>`;
  document.body.append(m);
  const part = (k) => m.querySelector(`[data-k="${k}"]`);
  const close = () => m.classList.replace("flex", "hidden");
  part("cancel").onclick = close;
  m.onclick = (e) => { if (e.target === m) close(); };
  m.querySelector("form").onsubmit = async (e) => {
    e.preventDefault();
    part("ok").disabled = true;
    try {
      set(await api("/api/auth/admin", { method: "POST", body: { pin: part("pin").value } }));
      toast("Host mode on for this device");
      close();
    } catch (err) { fail(err); part("pin").select(); }
    part("ok").disabled = false;
  };

  function unlock() {
    if (!me.pin_set) { toast("No host PIN yet — set one on the laptop's Settings page", false); return; }
    part("pin").value = "";
    m.classList.replace("hidden", "flex");
    part("pin").focus();
  }

  const owns = (entry) => Boolean(entry && me.guest && entry.owner === me.guest.id);
  load();
  return { load, unlock, owns, get me() { return me; }, onChange: (fn) => listeners.push(fn), set };
})();

// "🔑 Host" button for page headers: unlocks host mode, or shows 👑 when already host
function hostBadge() {
  const b = el("button", "rounded-lg bg-white/10 px-3 py-1.5 text-sm font-semibold hover:bg-white/20");
  const paint = (me) => {
    b.textContent = me.admin ? "👑 Host" : "🔑 Host";
    b.title = me.admin ? (me.laptop ? "This laptop runs the karaoke: you're the host" : "Host mode is on for this device")
      : "Enter the host PIN";
  };
  b.onclick = () => (Auth.me.admin ? toast(b.title) : Auth.unlock());
  Auth.onChange(paint);
  paint(Auth.me);
  return b;
}
