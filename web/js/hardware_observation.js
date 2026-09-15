import { projectHardwareDegrees } from "./hardware_calibration.js";

const SCHEMA = "dropbear-passive-observation-v1";
const SIDES = Object.freeze(["left", "right"]);
const SAMPLE_ORDER = Object.freeze([
  "outer_calf",
  "inner_calf",
  "hip_pitch",
  "knee",
  "hip_roll",
]);

const previousBySim = new WeakMap();

function finite(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function shortestDegreeDelta(next, previous) {
  return ((next - previous + 540) % 360) - 180;
}

export function validateHardwareObservation(payload) {
  if (!payload || payload.schema !== SCHEMA) {
    throw new Error("unsupported hardware observation schema");
  }
  if (payload.mode !== "read_only" || payload.writeCapable !== false || payload.txBytes !== 0) {
    throw new Error("hardware observation endpoint is not byte-silent");
  }
  if (!payload.sides || typeof payload.sides !== "object") {
    throw new Error("hardware observation sides are missing");
  }
  const result = { complete: true, availableSides: [], sides: {} };
  for (const side of SIDES) {
    const sample = payload.sides[side];
    if (!sample || sample.fresh !== true || !Number.isInteger(sample.sequence) || sample.sequence <= 0) {
      result.complete = false;
      result.sides[side] = null;
      continue;
    }
    const expectedNames = SAMPLE_ORDER.map((joint) => `${side}_${joint}`);
    const joints = {};
    for (const name of expectedNames) {
      const observation = sample.joints?.[name];
      if (!observation || !finite(observation.positionDeg) || observation.positionDeg < 0 || observation.positionDeg > 360) {
        throw new Error(`${name} observation is invalid`);
      }
      joints[name] = observation;
    }
    result.sides[side] = {
      sequence: sample.sequence,
      ageMs: finite(sample.ageMs) ? sample.ageMs : null,
      rawLine: String(sample.rawLine || ""),
      joints,
    };
    result.availableSides.push(side);
  }
  return result;
}

export function applyHardwareObservation(sim, payload, nowMs = performance.now()) {
  const validated = validateHardwareObservation(payload);
  if (validated.availableSides.length === 0) {
    throw new Error("at least one leg observation must be fresh before applying hardware state");
  }
  let previous = previousBySim.get(sim);
  if (!previous) {
    previous = new Map();
    previousBySim.set(sim, previous);
  }

  for (const joint of sim.joints) {
    joint.observationValid = false;
    joint.observationAgeMs = null;
    joint.observationSource = "unavailable";
    joint.observationRawDeg = null;
    joint.observationMechanismDeg = null;
    joint.observationCalibration = null;
  }
  for (const side of SIDES) {
    sim.controllers[side].serialConnected = false;
  }

  let appliedJoints = 0;
  const unavailableJoints = ["left_hip_yaw", "right_hip_yaw"];
  for (const side of SIDES) {
    const sample = validated.sides[side];
    if (!sample) {
      unavailableJoints.push(...SAMPLE_ORDER.map((joint) => `${side}_${joint}`));
      continue;
    }
    sim.controllers[side].csv = sample.rawLine;
    sim.controllers[side].serialConnected = true;
    sim.controllers[side].serialLines = sample.sequence;
    for (const firmwareJoint of SAMPLE_ORDER) {
      const canonicalName = `${side}_${firmwareJoint}`;
      const observation = sample.joints[canonicalName];
      const target = sim.getJoint(firmwareJoint, side);
      if (!target) continue;
      const position = observation.positionDeg;
      const projection = projectHardwareDegrees(side, firmwareJoint, position);
      if (!projection.calibrated) {
        unavailableJoints.push(canonicalName);
        continue;
      }
      const prior = previous.get(canonicalName);
      const dtSeconds = prior ? Math.max(0.001, (nowMs - prior.nowMs) / 1000) : 0;
      target.velocity = prior && sample.sequence !== prior.sequence
        ? Math.max(-720, Math.min(720, shortestDegreeDelta(position, prior.position) / dtSeconds))
        : 0;
      target.angle = projection.renderDegrees;
      target.rawAngle = position % 360;
      target.torque = 0;
      target.command = 0;
      target.observationValid = true;
      target.observationAgeMs = sample.ageMs;
      target.observationSource = "esp32_external_absolute";
      target.observationRawDeg = position;
      target.observationMechanismDeg = projection.mechanismDegrees;
      target.observationCalibration = projection.calibration;
      target.observationOutOfEnvelope = !projection.withinUsdLimits;
      previous.set(canonicalName, { position, sequence: sample.sequence, nowMs });
      appliedJoints += 1;
    }
  }
  sim.playMode = false;
  sim.canUtilization = 0;
  sim.canFramesWindow = 0;
  sim.scenario = "hardware-observation";
  return {
    appliedJoints,
    availableSides: [...validated.availableSides],
    unavailableJoints,
    sequences: {
      left: validated.sides.left?.sequence || 0,
      right: validated.sides.right?.sequence || 0,
    },
  };
}

export function clearHardwareObservationHistory(sim) {
  previousBySim.delete(sim);
  for (const joint of sim.joints) {
    joint.observationValid = false;
    joint.observationAgeMs = null;
    joint.observationSource = "unavailable";
    joint.observationOutOfEnvelope = false;
    joint.observationRawDeg = null;
    joint.observationMechanismDeg = null;
    joint.observationCalibration = null;
  }
}

export const HARDWARE_OBSERVATION_SCHEMA = SCHEMA;
