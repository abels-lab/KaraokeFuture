// Guest remote: the party login (name + password), log out, and the 🔑 Host button in the header.
// A new name registers on the spot; a known name needs its password. The session lives in an
// HttpOnly cookie, so this script never sees it. The form is the first thing a guest sees until
// they are in; who they are and Log out then live in the ⚙ popup (guest/settings-popup.js).
// The note under the form says whether this link is encrypted: the home Wi-Fi link is plain
// HTTP, the Tailscale Funnel link is HTTPS. Needs common.js and auth.js.
// GuestLogin.focus() shows and focuses the form; GuestLogin.logout() asks, then logs out.
const GuestLogin = (() => {
  const form = $("login");
  form.innerHTML = `
    <p class="font-display text-xl font-bold text-gold">Join the party</p>
    <p class="text-sm text-stone-300">Pick a singer name and a password. A new name is yours for the night;
      use the same name and password to come back on another phone.</p>
    <input data-k="name" maxlength="32" autocomplete="username" placeholder="Singer name, e.g. Freddie" required
           class="w-full rounded-xl border border-white/10 bg-black/50 px-4 py-3 text-lg outline-none focus:border-amber-400">
    <input data-k="pass" type="password" minlength="4" maxlength="64" autocomplete="current-password" placeholder="Password (4+ characters)" required
           class="w-full rounded-xl border border-white/10 bg-black/50 px-4 py-3 text-lg outline-none focus:border-amber-400">
    <button data-k="go" class="btn-gold tap w-full rounded-xl py-3">Let's sing</button>
    <p data-k="note" class="text-xs"></p>`;
  const part = (k) => form.querySelector(`[data-k="${k}"]`);
  const secure = location.protocol === "https:";
  part("note").className = `text-xs ${secure ? "text-emerald-200/80" : "text-amber-200/80"}`;
  part("note").textContent = secure
    ? "🔒 This link is encrypted (HTTPS via Tailscale Funnel). Still, make up a new password for the party — don't reuse a real one."
    : "⚠ This is a party login over the home Wi-Fi without encryption (plain HTTP). Make up a new password — don't reuse one you use anywhere else. The HTTPS (Tailscale Funnel) link, if the host shares it, is encrypted.";
  $("header").insertBefore(hostBadge(), $("header").querySelector("button"));   // before ＋ and ⚙

  function paint(me) {
    const in_ = Boolean(me.guest || me.admin);
    form.classList.toggle("hidden", in_);
    document.body.classList.toggle("guest-out", !in_);
    if (!in_ && !part("name").value) part("name").value = store("singer") || ""; // the old free-text name
  }
  Auth.onChange(paint);
  paint(Auth.me);

  form.onsubmit = async (e) => {
    e.preventDefault();
    const name = part("name").value.trim();
    part("go").disabled = true;
    try {
      Auth.set(await api("/api/auth/login", { method: "POST", body: { name, password: part("pass").value } }));
      store("singer", name);
      part("pass").value = "";
      toast(`Welcome, ${Auth.me.guest?.name || name}!`);
    } catch (err) { fail(err); }
    part("go").disabled = false;
  };

  async function logout() {
    if (!confirm("Log out on this device? Your songs stay in the queue; log in again with the same name and password.")) return false;
    await api("/api/auth/logout", { method: "POST" }).catch(fail);
    await Auth.load();
    return true;
  }

  function focus() {
    form.classList.remove("hidden");
    form.scrollIntoView({ behavior: "smooth", block: "start" });
    part(part("name").value ? "pass" : "name").focus({ preventScroll: true });
  }

  return { focus, logout };
})();
