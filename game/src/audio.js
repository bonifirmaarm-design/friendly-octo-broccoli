// Sound, synthesised in the browser.
//
// Nothing is loaded from disk. A punch is a filtered noise burst over a
// falling sine; the crowd is a noise bed whose filter opens when something
// happens; the bell is two detuned partials with a long decay. Shipping
// samples would mean either finding licensed ones or recording them, and for
// impacts and a crowd wash the synthesised versions are indistinguishable at
// the level they sit in the mix.
//
// Browsers refuse to start audio until the user has interacted with the page,
// so the context is created lazily on the first click or keypress.

export class Audio {
  constructor() {
    this.ctx = null;
    this.master = null;
    this.crowd = null;
    this.enabled = true;
    this.noise = null;
  }

  start() {
    if (this.ctx) {
      if (this.ctx.state === 'suspended') this.ctx.resume();
      return;
    }
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) { this.enabled = false; return; }
    this.ctx = new Ctx();
    this.master = this.ctx.createGain();
    this.master.gain.value = 0.85;
    this.master.connect(this.ctx.destination);

    // One second of noise, looped: cheaper than generating it per hit.
    const frames = this.ctx.sampleRate;
    const buffer = this.ctx.createBuffer(1, frames, this.ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < frames; i++) data[i] = Math.random() * 2 - 1;
    this.noise = buffer;

    this.buildCrowd();
  }

  buildCrowd() {
    const source = this.ctx.createBufferSource();
    source.buffer = this.noise;
    source.loop = true;

    // Two filters: a low band for the body of the room, a resonant one that
    // opens up to make the crowd "lift" without changing the volume alone.
    const body = this.ctx.createBiquadFilter();
    body.type = 'lowpass';
    body.frequency.value = 700;
    const colour = this.ctx.createBiquadFilter();
    colour.type = 'bandpass';
    colour.frequency.value = 900;
    colour.Q.value = 0.7;

    const gain = this.ctx.createGain();
    gain.gain.value = 0.0;
    source.connect(body).connect(colour).connect(gain).connect(this.master);
    source.start();
    this.crowd = { gain, colour };
  }

  // level 0..1: the room between exchanges vs a roar after a knockdown.
  crowdLevel(level, seconds = 0.6) {
    if (!this.ctx) return;
    const now = this.ctx.currentTime;
    this.crowd.gain.gain.cancelScheduledValues(now);
    this.crowd.gain.gain.setTargetAtTime(0.02 + level * 0.20, now, seconds / 3);
    this.crowd.colour.frequency.cancelScheduledValues(now);
    this.crowd.colour.frequency.setTargetAtTime(700 + level * 1500, now, seconds / 3);
  }

  roar(strength = 1) {
    if (!this.ctx) return;
    this.crowdLevel(Math.min(1, 0.45 + strength * 0.55), 0.25);
    setTimeout(() => this.crowdLevel(0.25, 2.2), 1400);
  }

  burst({ tone = 180, noiseGain = 0.5, toneGain = 0.35, decay = 0.14,
    filter = 1800, sweep = 0.35 } = {}) {
    if (!this.ctx || !this.enabled) return;
    const now = this.ctx.currentTime;

    const src = this.ctx.createBufferSource();
    src.buffer = this.noise;
    src.playbackRate.value = 0.8 + Math.random() * 0.4;
    const band = this.ctx.createBiquadFilter();
    band.type = 'lowpass';
    band.frequency.setValueAtTime(filter, now);
    band.frequency.exponentialRampToValueAtTime(Math.max(120, filter * sweep),
      now + decay);
    const ng = this.ctx.createGain();
    ng.gain.setValueAtTime(noiseGain, now);
    ng.gain.exponentialRampToValueAtTime(0.0005, now + decay);
    src.connect(band).connect(ng).connect(this.master);
    src.start(now);
    src.stop(now + decay + 0.02);

    const osc = this.ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(tone, now);
    osc.frequency.exponentialRampToValueAtTime(tone * 0.45, now + decay);
    const og = this.ctx.createGain();
    og.gain.setValueAtTime(toneGain, now);
    og.gain.exponentialRampToValueAtTime(0.0005, now + decay);
    osc.connect(og).connect(this.master);
    osc.start(now);
    osc.stop(now + decay + 0.02);
  }

  punch(damage = 8) {
    const heavy = Math.min(1, damage / 18);
    this.burst({ tone: 150 - heavy * 40, noiseGain: 0.35 + heavy * 0.35,
      toneGain: 0.25 + heavy * 0.35, decay: 0.10 + heavy * 0.10,
      filter: 2600 - heavy * 900 });
  }

  kick(damage = 12) {
    const heavy = Math.min(1, damage / 20);
    this.burst({ tone: 110, noiseGain: 0.55, toneGain: 0.4,
      decay: 0.16 + heavy * 0.08, filter: 1500, sweep: 0.2 });
  }

  block() {
    this.burst({ tone: 320, noiseGain: 0.30, toneGain: 0.10, decay: 0.07,
      filter: 4200, sweep: 0.5 });
  }

  thud() {   // a body hitting the mat
    this.burst({ tone: 70, noiseGain: 0.6, toneGain: 0.5, decay: 0.30,
      filter: 700, sweep: 0.18 });
  }

  bell(count = 1) {
    if (!this.ctx || !this.enabled) return;
    for (let n = 0; n < count; n++) {
      const at = this.ctx.currentTime + n * 0.55;
      for (const [freq, gain] of [[840, 0.20], [1265, 0.12], [2100, 0.05]]) {
        const osc = this.ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.value = freq;
        const g = this.ctx.createGain();
        g.gain.setValueAtTime(0.0001, at);
        g.gain.exponentialRampToValueAtTime(gain, at + 0.006);
        g.gain.exponentialRampToValueAtTime(0.0001, at + 1.9);
        osc.connect(g).connect(this.master);
        osc.start(at);
        osc.stop(at + 2.0);
      }
    }
  }

  whistle() {   // the referee stepping in
    if (!this.ctx || !this.enabled) return;
    const now = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    osc.type = 'square';
    osc.frequency.setValueAtTime(2100, now);
    osc.frequency.setValueAtTime(2400, now + 0.09);
    const g = this.ctx.createGain();
    g.gain.setValueAtTime(0.0001, now);
    g.gain.exponentialRampToValueAtTime(0.12, now + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, now + 0.34);
    osc.connect(g).connect(this.master);
    osc.start(now);
    osc.stop(now + 0.36);
  }

  setEnabled(on) {
    this.enabled = on;
    if (this.master) this.master.gain.value = on ? 0.85 : 0.0;
  }
}
