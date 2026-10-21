// Control panel dialog: assign the laptop's microphones to singers and test them live.
// Needs common.js + mics.js. Exposes openMicSetup().
const micSetup = (() => {
  const m = el("div", "fixed inset-0 z-40 hidden items-center justify-center bg-black/75 p-4");
  m.innerHTML = `
    <div class="panel w-full max-w-3xl space-y-4 p-5">
      <div class="flex items-center justify-between">
        <h2 class="font-display text-2xl font-bold text-gold">🎤 Microphones</h2>
        <button data-k="close" class="rounded-lg bg-white/10 px-3 py-1.5 text-sm font-semibold">Done</button>
      </div>
      <p class="text-sm text-stone-400">An audio interface with two mics usually appears as one stereo input:
        mic 1 = <b>Left</b>, mic 2 = <b>Right</b>. Hum into each mic to check the meter and the note.</p>
      <div data-k="players" class="grid gap-3 sm:grid-cols-2"></div>
      <div class="flex items-center gap-3">
        <button data-k="start" class="btn-gold rounded-xl px-5 py-2.5">Start microphones</button>
        <button data-k="stop" class="rounded-xl bg-white/10 px-4 py-2.5 font-semibold">Stop</button>
        <span data-k="status" class="text-sm text-stone-400"></span>
      </div>
    </div>`;
  document.body.append(m);
  const part = (k) => m.querySelector(`[data-k="${k}"]`);
  const meters = [];

  function card(player, devices) {
    const p = Mics.config[player];
    const c = el("div", "space-y-2 rounded-xl bg-black/40 p-3 ring-1 ring-white/10");
    c.innerHTML = `
      <input data-f="name" maxlength="24" class="w-full rounded-lg bg-black/50 px-3 py-2 font-semibold outline-none ring-1 ring-white/10 focus:ring-amber-400">
      <select data-f="deviceId" class="w-full rounded-lg bg-black/50 px-3 py-2 text-sm ring-1 ring-white/10"></select>
      <select data-f="channel" class="w-full rounded-lg bg-black/50 px-3 py-2 text-sm ring-1 ring-white/10">
        <option value="left">Left channel (mic 1)</option><option value="right">Right channel (mic 2)</option>
        <option value="mix">Both channels / mono mic</option></select>
      <label class="flex items-center gap-2 text-xs text-stone-400">Latency
        <input data-f="latency" type="range" min="0" max="400" step="10" class="flex-1"><span data-v="latency" class="w-14 text-right font-mono"></span></label>
      <div class="flex items-center gap-3">
        <div class="h-2 flex-1 overflow-hidden rounded-full bg-white/10"><div data-v="level" class="h-full w-0 bg-gradient-to-r from-emerald-500 via-amber-400 to-red-500"></div></div>
        <span data-v="note" class="w-14 text-right font-mono text-lg text-gold">–</span>
      </div>`;
    const f = (k) => c.querySelector(`[data-f="${k}"]`);
    f("name").value = p.name;
    f("deviceId").replaceChildren(
      Object.assign(el("option", "", "Off (nobody on this mic)"), { value: "off" }),
      Object.assign(el("option", "", "Default microphone"), { value: "" }),
      ...devices.map((d) => Object.assign(el("option", "", d.label || "Microphone"), { value: d.deviceId })));
    f("deviceId").value = p.deviceId;
    f("channel").value = p.channel;
    f("latency").value = p.latency;
    c.querySelector('[data-v="latency"]').textContent = `${p.latency} ms`;
    f("name").oninput = () => Mics.update(player, { name: f("name").value.trim() || `Singer ${player + 1}` });
    f("deviceId").onchange = () => Mics.update(player, { deviceId: f("deviceId").value });
    f("channel").onchange = () => Mics.update(player, { channel: f("channel").value });
    f("latency").oninput = () => {
      Mics.update(player, { latency: Number(f("latency").value) });
      c.querySelector('[data-v="latency"]').textContent = `${f("latency").value} ms`;
    };
    meters[player] = { level: c.querySelector('[data-v="level"]'), note: c.querySelector('[data-v="note"]') };
    return c;
  }

  // Live meters: loudness bar + the note the mic hears right now
  Mics.onFrame(({ player, pitch, clarity, db }) => {
    const meter = meters[player];
    if (!meter || m.classList.contains("hidden")) return;
    meter.level.style.width = `${Math.max(0, Math.min(100, ((db + 60) / 60) * 100))}%`;
    meter.note.textContent = pitch && clarity > 0.6 && db > -50 ? noteName(pitch) : "–";
  });

  const status = () => {
    part("status").textContent = Mics.running ? `Listening on ${Mics.active.length} mic${Mics.active.length === 1 ? "" : "s"}` : "Microphones are off";
    micStrip?.render();
  };
  part("start").onclick = async () => {
    try { await Mics.start(); } catch (err) { toast(`Microphone error: ${err.message}`, false); }
    status();
  };
  part("stop").onclick = () => { Mics.stop(); status(); };
  part("close").onclick = () => m.classList.replace("flex", "hidden");
  m.onclick = (e) => { if (e.target === m) part("close").click(); };

  return async () => {
    let devices = [];
    try { devices = await Mics.devices(); } catch (err) { toast(`Microphone access was refused: ${err.message}`, false); }
    part("players").replaceChildren(card(0, devices), card(1, devices));
    status();
    m.classList.replace("hidden", "flex");
  };
})();

const openMicSetup = () => micSetup();

// Compact live strip in the control panel sidebar (#mic-live): one row per active singer
const micStrip = (() => {
  const box = $("mic-live"), rows = [];
  if (!box) return null;
  const render = () => {
    box.replaceChildren(...Mics.active.map((player) => {
      const row = el("div", "flex items-center gap-2");
      const level = el("div", "h-full w-0 bg-amber-400");
      const bar = el("div", "h-1.5 flex-1 overflow-hidden rounded-full bg-white/10");
      bar.append(level);
      const note = el("span", "w-10 text-right font-mono text-gold", "–");
      row.append(el("span", "w-20 truncate text-stone-300", Mics.config[player].name), bar, note);
      rows[player] = { level, note };
      return row;
    }));
    box.classList.toggle("hidden", !Mics.running);
  };
  let last = 0;
  Mics.onFrame(({ player, pitch, clarity, db, at }) => {
    if (!rows[player] || at - last < 60) return; // ~16 updates/s is plenty for a meter
    last = at;
    rows[player].level.style.width = `${Math.max(0, Math.min(100, ((db + 60) / 60) * 100))}%`;
    rows[player].note.textContent = pitch && clarity > 0.6 && db > -50 ? noteName(pitch) : "–";
  });
  return { render };
})();
