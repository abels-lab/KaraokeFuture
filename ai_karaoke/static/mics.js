// Microphones on the laptop (e.g. an audio interface with two mics = one stereo input).
// Each singer = device + channel; a pitch worklet per singer emits 50 frames per second:
// {player, pitch (MIDI | 0), clarity 0..1, db, at (performance.now())}. Needs common.js.
const MIC_DEFAULTS = [
  { name: "Singer 1", deviceId: "", channel: "left", latency: 120 },
  { name: "Singer 2", deviceId: "off", channel: "right", latency: 120 },
];
const NOTE_NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
const noteName = (midi) => midi > 0 ? `${NOTE_NAMES[Math.round(midi) % 12]}${Math.floor(Math.round(midi) / 12) - 1}` : "–";

const Mics = (() => {
  let ctx = null, nodes = [];
  const streams = new Map(), listeners = [];
  const load = () => {
    try {
      const saved = JSON.parse(store("mics"));
      if (Array.isArray(saved) && saved.length === 2) return saved;
    } catch { /* first run or blocked storage */ }
    return MIC_DEFAULTS.map((p) => ({ ...p }));
  };
  const config = load();
  const save = () => store("mics", JSON.stringify(config));

  async function devices() {
    // Device names are only visible after the browser has been allowed to use a microphone
    const list = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput");
    if (list.length && !list[0].label) {
      (await navigator.mediaDevices.getUserMedia({ audio: true })).getTracks().forEach((t) => t.stop());
      return (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput");
    }
    return list;
  }

  async function stream(deviceId) {
    if (!streams.has(deviceId)) {
      streams.set(deviceId, await navigator.mediaDevices.getUserMedia({ audio: {
        deviceId: deviceId ? { exact: deviceId } : undefined, channelCount: { ideal: 2 },
        // Browser voice processing would treat singing over music as noise to remove
        echoCancellation: false, noiseSuppression: false, autoGainControl: false,
      } }));
    }
    return streams.get(deviceId);
  }

  async function start() {
    stop();
    ctx = new AudioContext({ latencyHint: "interactive" });
    await ctx.audioWorklet.addModule("/static/pitch-worklet.js");
    const sink = ctx.createGain();          // keeps the graph pulling audio; never audible
    sink.gain.value = 0;
    sink.connect(ctx.destination);
    for (const [player, p] of config.entries()) {
      if (p.deviceId === "off") continue;
      const source = ctx.createMediaStreamSource(await stream(p.deviceId));
      const node = new AudioWorkletNode(ctx, "pitch-tracker",
        { channelCount: 1, channelCountMode: "explicit", channelInterpretation: "speakers" });
      if (p.channel === "mix") {
        source.connect(node);               // mono mic, or both channels mixed
      } else {
        const split = ctx.createChannelSplitter(2);
        source.connect(split);
        split.connect(node, p.channel === "right" ? 1 : 0);
      }
      node.connect(sink);
      node.port.onmessage = (e) => {
        const frame = { player, ...e.data, at: performance.now() };
        listeners.forEach((fn) => fn(frame));
      };
      nodes.push(node);
    }
    store("micsOn", "1");
  }

  function stop() {
    nodes.forEach((n) => n.disconnect());
    nodes = [];
    streams.forEach((s) => s.getTracks().forEach((t) => t.stop()));
    streams.clear();
    ctx?.close();
    ctx = null;
  }

  return {
    config, devices, start,
    stop: () => { stop(); store("micsOn", "0"); },
    update(player, patch) { Object.assign(config[player], patch); save(); },
    onFrame: (fn) => listeners.push(fn),
    get running() { return Boolean(ctx); },
    get active() { return config.map((p, i) => (p.deviceId === "off" ? -1 : i)).filter((i) => i >= 0); },
  };
})();
