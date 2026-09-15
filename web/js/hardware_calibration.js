const RIGHT_DEFAULT_STANCE = Object.freeze({
  outer_calf: Object.freeze({
    rawDatumDeg: 125,
    referenceDeg: 0,
    lowerDeg: -60,
    upperDeg: 50,
    observedRangeDeg: Object.freeze([119, 130]),
  }),
  inner_calf: Object.freeze({
    rawDatumDeg: 188,
    referenceDeg: -11.459156,
    lowerDeg: -50,
    upperDeg: 60,
    observedRangeDeg: Object.freeze([175, 197]),
  }),
  hip_pitch: Object.freeze({
    rawDatumDeg: 89,
    referenceDeg: 0,
    lowerDeg: -50,
    upperDeg: 30,
    observedRangeDeg: Object.freeze([86, 92]),
  }),
  knee: Object.freeze({
    rawDatumDeg: 28,
    referenceDeg: 17.188734,
    lowerDeg: 0,
    upperDeg: 30,
    observedRangeDeg: Object.freeze([25, 31]),
  }),
  hip_roll: Object.freeze({
    rawDatumDeg: 169,
    referenceDeg: -5.729578,
    lowerDeg: -30,
    upperDeg: 15,
    observedRangeDeg: Object.freeze([164, 173]),
  }),
});

export const HARDWARE_DEFAULT_STANCE_CALIBRATION = Object.freeze({
  schema: "dropbear-default-stance-calibration-v1",
  units: "degrees",
  source: Object.freeze({
    repository: "https://github.com/robit-man/dropbear-locomotion",
    commit: "a397be863fed2d328c2e8f62c3db2f1e23575eb1",
    usdSha256: "45586414b065cd982d487cbd868fe982108b3b8ccec64d3dfcf629652ed8db0f",
  }),
  capture: Object.freeze({
    side: "right",
    mode: "read_only",
    sampleCount: 86,
    uniqueSequences: 86,
    durationSeconds: 5,
    capturedAt: "2026-09-14T17:56:00-07:00",
    estimator: "median",
  }),
  sides: Object.freeze({
    left: null,
    right: RIGHT_DEFAULT_STANCE,
  }),
  directionEvidence: "provisional_positive_until_read_only_motion_validation",
});

function shortestDegreeDelta(next, previous) {
  return ((next - previous + 540) % 360) - 180;
}

export function projectHardwareDegrees(side, firmwareJoint, rawDegrees) {
  const calibration = HARDWARE_DEFAULT_STANCE_CALIBRATION.sides[side]?.[firmwareJoint];
  if (!calibration || !Number.isFinite(rawDegrees)) {
    return Object.freeze({
      calibrated: false,
      rawDegrees,
      mechanismDegrees: null,
      renderDegrees: null,
      withinUsdLimits: false,
      calibration: calibration || null,
    });
  }
  const mechanismDegrees = calibration.referenceDeg
    + shortestDegreeDelta(rawDegrees, calibration.rawDatumDeg);
  return Object.freeze({
    calibrated: true,
    rawDegrees,
    mechanismDegrees,
    // DropbearSim retains 180 degrees as its internal zero. Robot3D then
    // converts this value back to the signed USD coordinate.
    renderDegrees: 180 + mechanismDegrees,
    withinUsdLimits: mechanismDegrees >= calibration.lowerDeg
      && mechanismDegrees <= calibration.upperDeg,
    calibration,
  });
}
