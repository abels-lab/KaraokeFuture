// Guest phone: party login (name + password), log out, and the 🔑 Host button.
// A new name registers on the spot; a known name needs its password. The session lives in an
// HttpOnly cookie, so this script never sees it. Needs common.js and auth.js.
$("header").append(hostBadge());

function paintLogin(me) {
  const in_ = Boolean(me.guest || me.admin);
  $("login").classList.toggle("hidden", in_);
  $("me-bar").classList.toggle("hidden", !in_);
  $("guest-tools").classList.toggle("hidden", !in_);
  $("me-name").textContent = me.guest?.name || (me.admin ? "Host" : "");
  if (!in_ && !$("login-name").value) $("login-name").value = store("singer") || ""; // the old free-text name
}
Auth.onChange(paintLogin);

$("login").onsubmit = async (e) => {
  e.preventDefault();
  const name = $("login-name").value.trim();
  $("login-btn").disabled = true;
  try {
    Auth.set(await api("/api/auth/login", { method: "POST", body: { name, password: $("login-pass").value } }));
    store("singer", name);
    $("login-pass").value = "";
    toast(`Welcome, ${Auth.me.guest?.name || name}!`);
  } catch (err) { fail(err); }
  $("login-btn").disabled = false;
};

$("logout").onclick = async () => {
  if (!confirm("Log out on this phone? Your songs stay in the queue; log in again with the same name and password.")) return;
  await api("/api/auth/logout", { method: "POST" }).catch(fail);
  Auth.load();
};
