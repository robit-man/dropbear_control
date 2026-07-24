const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const lerp = (start, end, amount) => start + (end - start) * amount;

function interpolateArray(left = [], right = [], amount = 0) {
  return left.map((value, index) => lerp(value, right[index] ?? value, amount));
}

function interpolateFrame(left, right, amount) {
  const baseKeys = ["height", "x", "vx", "roll", "pitch"];
  return {
    time: lerp(left.time, right.time, amount),
    phase: lerp(left.phase ?? 0, right.phase ?? 0, amount),
    q: interpolateArray(left.q, right.q, amount),
    dq: interpolateArray(left.dq, right.dq, amount),
    contactLoadsKg: interpolateArray(
      left.contactLoadsKg,
      right.contactLoadsKg,
      amount,
    ),
    base: Object.fromEntries(
      baseKeys.map((key) => [
        key,
        lerp(left.base?.[key] ?? 0, right.base?.[key] ?? 0, amount),
      ]),
    ),
  };
}

export class RLPolicyPlayer {
  constructor({ onFrame = () => {}, onState = () => {} } = {}) {
    this.onFrame = onFrame;
    this.onState = onState;
    this.policy = null;
    this.playing = false;
    this.loop = false;
    this.elapsed = 0;
    this.speed = 1;
  }

  async load(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`policy HTTP ${response.status}`);
    const policy = await response.json();
    this.setPolicy(policy, url);
    return policy;
  }

  setPolicy(policy, source = "memory") {
    if (policy?.schema !== "dropbear-walk-policy-v2") {
      throw new Error("unsupported policy schema");
    }
    if (!Array.isArray(policy.frames) || policy.frames.length < 2) {
      throw new Error("policy has no playable frame sequence");
    }
    if (policy.jointOrder?.length !== 22) {
      throw new Error("policy must expose the exact 22-motor ordering");
    }
    this.policy = policy;
    this.source = source;
    this.elapsed = 0;
    this.playing = false;
    this.loop = false;
    this._emitFrame();
    this.onState(this.snapshot());
  }

  play() {
    if (!this.policy) return false;
    if (this.elapsed >= this.duration) this.elapsed = 0;
    this.playing = true;
    this.onState(this.snapshot());
    return true;
  }

  pause() {
    this.playing = false;
    this.onState(this.snapshot());
  }

  seek(seconds) {
    this.elapsed = clamp(Number(seconds) || 0, 0, this.duration);
    this._emitFrame();
    this.onState(this.snapshot());
  }

  update(dt) {
    if (!this.playing || !this.policy) return;
    this.elapsed += Math.max(0, Number(dt) || 0) * this.speed;
    if (this.elapsed >= this.duration) {
      if (this.loop && this.duration > 0) this.elapsed %= this.duration;
      else {
        this.elapsed = this.duration;
        this.playing = false;
      }
    }
    this._emitFrame();
    this.onState(this.snapshot());
  }

  _emitFrame() {
    if (!this.policy) return;
    const frames = this.policy.frames;
    let upper = frames.findIndex((frame) => frame.time >= this.elapsed);
    if (upper < 0) upper = frames.length - 1;
    if (upper === 0) {
      this.onFrame(frames[0], this.policy);
      return;
    }
    const left = frames[upper - 1];
    const right = frames[upper];
    const span = Math.max(1e-6, right.time - left.time);
    this.onFrame(
      interpolateFrame(left, right, (this.elapsed - left.time) / span),
      this.policy,
    );
  }

  get duration() {
    return this.policy?.frames?.at(-1)?.time || 0;
  }

  snapshot() {
    return {
      loaded: Boolean(this.policy),
      playing: this.playing,
      elapsed: this.elapsed,
      duration: this.duration,
      source: this.source || null,
      evaluation: this.policy?.evaluation || null,
      config: this.policy?.config || null,
    };
  }
}
