// Real-time pitch + loudness of one microphone (AudioWorklet thread, one instance per singer).
// YIN on a 64 ms window, downsampled to 16 kHz; posts {pitch: MIDI float | 0, clarity: 0..1,
// db: loudness dBFS} 50 times a second — the same 20 ms grid as the reference melody.
const RATE = 16000, WINDOW = 1024, HOP = 320, MIN_HZ = 70, MAX_HZ = 1000, THRESHOLD = 0.15;

class PitchTracker extends AudioWorkletProcessor {
  constructor() {
    super();
    this.factor = Math.max(1, Math.round(sampleRate / RATE)); // 48 kHz -> 16 kHz
    this.rate = sampleRate / this.factor;
    this.ring = new Float32Array(WINDOW); // circular: no per-sample shifting
    this.buf = new Float32Array(WINDOW);  // straightened copy, built only when analysing
    this.write = 0; this.filled = 0; this.sinceHop = 0; this.acc = 0; this.accN = 0;
    this.diff = new Float32Array(Math.ceil(this.rate / MIN_HZ) + 2);
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i++) {
      this.acc += channel[i]; // box-filter decimation: good enough for the singing voice
      if (++this.accN < this.factor) continue;
      this.push(this.acc / this.factor);
      this.acc = 0; this.accN = 0;
    }
    return true;
  }

  push(sample) {
    this.ring[this.write] = sample;
    this.write = (this.write + 1) % WINDOW;
    if (this.filled < WINDOW) this.filled++;
    if (++this.sinceHop >= HOP && this.filled === WINDOW) {
      this.sinceHop = 0;
      this.buf.set(this.ring.subarray(this.write));                 // oldest samples first
      this.buf.set(this.ring.subarray(0, this.write), WINDOW - this.write);
      this.port.postMessage(this.analyse());
    }
  }

  analyse() {
    const x = this.buf, d = this.diff;
    let energy = 0;
    for (let i = 0; i < WINDOW; i++) energy += x[i] * x[i];
    const db = 10 * Math.log10(energy / WINDOW + 1e-12);
    const minTau = Math.floor(this.rate / MAX_HZ), maxTau = Math.min(d.length - 1, Math.floor(this.rate / MIN_HZ));
    const span = WINDOW - maxTau;
    // YIN: difference function -> cumulative mean normalised difference
    let running = 0;
    d[0] = 1;
    for (let tau = 1; tau <= maxTau; tau++) {
      let sum = 0;
      for (let j = 0; j < span; j++) { const delta = x[j] - x[j + tau]; sum += delta * delta; }
      running += sum;
      d[tau] = running > 0 ? (sum * tau) / running : 1;
    }
    let best = -1;
    for (let tau = minTau; tau <= maxTau; tau++) {
      if (d[tau] < THRESHOLD) { // first dip under the threshold, then walk to its bottom
        while (tau + 1 <= maxTau && d[tau + 1] < d[tau]) tau++;
        best = tau;
        break;
      }
    }
    if (best < 0) return { pitch: 0, clarity: 0, db };
    // Parabolic interpolation for sub-sample precision
    const a = d[best - 1] ?? d[best], b = d[best], c = d[best + 1] ?? d[best];
    const shift = (a + c - 2 * b) !== 0 ? (a - c) / (2 * (a + c - 2 * b)) : 0;
    const hz = this.rate / (best + shift);
    return { pitch: 69 + 12 * Math.log2(hz / 440), clarity: 1 - b, db };
  }
}

registerProcessor("pitch-tracker", PitchTracker);
