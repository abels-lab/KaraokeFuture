// Settings page: the host PIN (set or changed only on the laptop) and "Wipe Party DB".
// Needs common.js and auth.js; the server enforces both rules itself.
function paintParty({ admin, laptop, pin_set: pinSet }) {
  $("pin-status").textContent = !pinSet
    ? (laptop ? "No host PIN yet: only this laptop can manage the party. Set one to manage it from your phone too."
              : "No host PIN yet — only the laptop running the karaoke can manage the party.")
    : laptop ? "A host PIN is set. Changing it signs every other device out of host mode."
    : admin ? "Host mode is on for this device (the PIN can only be changed on the laptop)."
    : "Enter the host PIN to manage the party from this device.";
  $("pin-form").classList.toggle("hidden", !laptop);
  $("wipe-box").classList.toggle("hidden", !admin);
}
Auth.onChange(paintParty);

$("pin-form").onsubmit = async (e) => {
  e.preventDefault();
  try {
    Auth.set(await api("/api/auth/pin", { method: "PUT", body: { pin: $("pin-new").value } }));
    $("pin-new").value = "";
    toast("Host PIN saved");
  } catch (err) { fail(err); }
};

$("wipe").onclick = async () => {
  if (!confirm("Wipe the party?\nEvery guest login and session is deleted and their waiting songs leave the queue.\n"
    + "Cached songs, lyrics, settings and the host PIN stay.")) return;
  try {
    const { guests, songs_removed: removed } = await api("/api/party/wipe", { method: "POST" });
    toast(`Party wiped: ${guests} guest${guests === 1 ? "" : "s"}, ${removed} queued song${removed === 1 ? "" : "s"} removed`);
    Auth.load();
  } catch (err) { fail(err); }
};
