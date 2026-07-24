const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

function finitePatch(rawFeet, side, patch) {
  const value = Number(rawFeet?.[side]?.[patch]);
  return Number.isFinite(value) ? value : null;
}

export class VerticalGroundConstraint {
  constructor({
    groundZ = 0,
    massKg = 42,
    gravity = 9.80665,
    contactBandM = 0.004,
    maxFallSpeedMps = 1.4,
  } = {}) {
    this.groundZ = groundZ;
    this.massKg = massKg;
    this.gravity = gravity;
    this.contactBandM = contactBandM;
    this.maxFallSpeedMps = maxFallSpeedMps;
    this.reset();
  }

  reset() {
    this.initialized = false;
    this.offsetZ = 0;
    this.velocityZ = 0;
    this.lastState = {
      valid: false,
      guide: "Z_ONLY",
      offsetZ: 0,
      velocityZ: 0,
      constrained: false,
      left: this._emptyFoot(),
      right: this._emptyFoot(),
    };
  }

  _emptyFoot() {
    return {
      contact: false,
      heelContact: false,
      toeContact: false,
      footHeightMm: 0,
      heelHeightMm: 0,
      toeHeightMm: 0,
      loadKg: 0,
      heelLoadKg: 0,
      toeLoadKg: 0,
    };
  }

  solve(rawFeet, dtSeconds = 0) {
    const patches = [];
    for (const side of ["left", "right"]) {
      for (const patch of ["heelZ", "toeZ"]) {
        const value = finitePatch(rawFeet, side, patch);
        if (value != null) patches.push({ side, patch, value });
      }
    }
    if (patches.length !== 4) {
      this.lastState = {
        ...this.lastState,
        valid: false,
        left: this._emptyFoot(),
        right: this._emptyFoot(),
      };
      return this.lastState;
    }

    const rawMinimum = Math.min(...patches.map((entry) => entry.value));
    if (!this.initialized) {
      this.offsetZ = this.groundZ - rawMinimum;
      this.velocityZ = 0;
      this.initialized = true;
    } else {
      const dt = clamp(Number(dtSeconds) || 0, 0, 0.08);
      if (dt > 0) {
        this.velocityZ = Math.max(
          -this.maxFallSpeedMps,
          this.velocityZ - this.gravity * dt,
        );
        this.offsetZ += this.velocityZ * dt;
      }
      const penetration = this.groundZ - (rawMinimum + this.offsetZ);
      if (penetration > 0) {
        this.offsetZ += penetration;
        this.velocityZ = 0;
      }
    }

    const heights = patches.map((entry) => ({
      ...entry,
      height: Math.max(0, entry.value + this.offsetZ - this.groundZ),
    }));
    const weights = heights.map((entry) => (
      clamp(1 - entry.height / this.contactBandM, 0, 1)
    ));
    const weightTotal = weights.reduce((sum, value) => sum + value, 0);
    const normalLoads = weights.map((weight) => (
      weightTotal > 0 ? this.massKg * weight / weightTotal : 0
    ));
    const constrained = heights.some((entry) => entry.height <= 1e-7);
    const footState = {};

    for (const side of ["left", "right"]) {
      const heelIndex = heights.findIndex((entry) => entry.side === side && entry.patch === "heelZ");
      const toeIndex = heights.findIndex((entry) => entry.side === side && entry.patch === "toeZ");
      const heelHeight = heights[heelIndex].height;
      const toeHeight = heights[toeIndex].height;
      const heelLoad = normalLoads[heelIndex];
      const toeLoad = normalLoads[toeIndex];
      footState[side] = {
        contact: heelLoad + toeLoad > 0.05,
        heelContact: heelLoad > 0.05,
        toeContact: toeLoad > 0.05,
        footHeightMm: Math.min(heelHeight, toeHeight) * 1000,
        heelHeightMm: heelHeight * 1000,
        toeHeightMm: toeHeight * 1000,
        loadKg: heelLoad + toeLoad,
        heelLoadKg: heelLoad,
        toeLoadKg: toeLoad,
      };
    }

    this.lastState = {
      valid: true,
      guide: "Z_ONLY",
      offsetZ: this.offsetZ,
      velocityZ: this.velocityZ,
      constrained,
      left: footState.left,
      right: footState.right,
    };
    return this.lastState;
  }
}
