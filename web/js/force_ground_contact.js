const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

function patchValue(rawFeet, side, patch) {
  const value = Number(rawFeet?.[side]?.[patch]);
  return Number.isFinite(value) ? value : null;
}

/**
 * Unilateral compliant ground contact for the browser free-root preview.
 *
 * This integrates normal forces (N), gravity (m/s²), and the authored total
 * USD mass. A final position projection is only a non-penetration safety
 * barrier; it does not synthesize the displayed contact load.
 */
export class ForceGroundContact {
  constructor({
    massKg = 56.2289776,
    gravity = 9.80665,
    stiffnessNpm = 240000,
    dampingNsPm = 2400,
    contactSlopM = 0.00065,
    maxLoadG = 4,
  } = {}) {
    this.massKg = massKg;
    this.gravity = gravity;
    this.stiffnessNpm = stiffnessNpm;
    this.dampingNsPm = dampingNsPm;
    this.contactSlopM = contactSlopM;
    this.maxNormalForceN = massKg * gravity * maxLoadG;
    this.reset();
  }

  reset() {
    this.previousHeights = null;
    this.lastState = {
      valid: false,
      guide: "FREE_ROOT_FORCE_CONTACT",
      normalForceN: 0,
      verticalAccelerationMps2: -this.gravity,
      penetrationM: 0,
      correctionZ: 0,
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

  solve(rawFeet, rootVelocityZ = 0, dtSeconds = 0) {
    const patches = [
      ["left", "heelZ"],
      ["left", "toeZ"],
      ["right", "heelZ"],
      ["right", "toeZ"],
    ].map(([side, patch]) => ({
      side,
      patch,
      height: patchValue(rawFeet, side, patch),
    }));
    if (patches.some((entry) => entry.height == null)) {
      this.reset();
      return this.lastState;
    }

    const dt = clamp(Number(dtSeconds) || 0, 0, 0.08);
    const heights = patches.map((entry) => Number(entry.height));
    const velocities = heights.map((height, index) => {
      if (dt > 1e-5 && this.previousHeights) {
        return (height - this.previousHeights[index]) / dt;
      }
      return Number(rootVelocityZ) || 0;
    });
    this.previousHeights = heights;

    const forces = heights.map((height, index) => {
      const compression = Math.max(0, this.contactSlopM - height);
      if (compression <= 0) return 0;
      const damping = -this.dampingNsPm * Math.min(0, velocities[index]);
      return Math.max(0, this.stiffnessNpm * compression + damping);
    });
    const rawForce = forces.reduce((sum, force) => sum + force, 0);
    const forceScale = rawForce > this.maxNormalForceN
      ? this.maxNormalForceN / rawForce
      : 1;
    const normalForces = forces.map((force) => force * forceScale);
    const normalForceN = normalForces.reduce((sum, force) => sum + force, 0);
    const minimumHeight = Math.min(...heights);
    const penetrationM = Math.max(0, -minimumHeight);
    const correctionZ = penetrationM;

    const correctedHeights = heights.map((height) => Math.max(0, height + correctionZ));
    const loadsKg = normalForces.map((force) => force / this.gravity);
    const foot = (offset) => {
      const heelLoadKg = loadsKg[offset];
      const toeLoadKg = loadsKg[offset + 1];
      const heelHeightM = correctedHeights[offset];
      const toeHeightM = correctedHeights[offset + 1];
      return {
        contact: heelLoadKg + toeLoadKg > 0.01,
        heelContact: heelLoadKg > 0.01,
        toeContact: toeLoadKg > 0.01,
        footHeightMm: Math.min(heelHeightM, toeHeightM) * 1000,
        heelHeightMm: heelHeightM * 1000,
        toeHeightMm: toeHeightM * 1000,
        loadKg: heelLoadKg + toeLoadKg,
        heelLoadKg,
        toeLoadKg,
      };
    };
    this.lastState = {
      valid: true,
      guide: "FREE_ROOT_FORCE_CONTACT",
      normalForceN,
      verticalAccelerationMps2: normalForceN / this.massKg - this.gravity,
      penetrationM,
      correctionZ,
      constrained: false,
      left: foot(0),
      right: foot(2),
    };
    return this.lastState;
  }
}
