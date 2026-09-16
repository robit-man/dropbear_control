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
const MOTOR_ORDER = Object.freeze([...SAMPLE_ORDER, "hip_yaw"]);

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
    const motorJoints = {};
    for (const joint of MOTOR_ORDER) {
      const name = `${side}_${joint}`;
      const observation = sample.motorJoints?.[name];
      if (!observation) continue;
      if (observation.available === true && !finite(observation.positionDeg)) {
        throw new Error(`${name} motor-native observation is invalid`);
      }
      motorJoints[name] = observation;
    }
    result.sides[side] = {
      sequence: sample.sequence,
      ageMs: finite(sample.ageMs) ? sample.ageMs : null,
      rawLine: String(sample.rawLine || ""),
      joints,
      motorJoints,
    };
    result.availableSides.push(side);
  }
  return result;
}

export function applyHardwareObservation(sim, payload, nowMs = performance.now(), softwareZero = null) {
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
    joint.observationModelApplied = false;
    joint.observationAgeMs = null;
    joint.observationSource = "unavailable";
    joint.observationRawDeg = null;
    joint.observationExternalDeg = null;
    joint.observationMotorDeg = null;
    joint.observationPositionSource = "unavailable";
    joint.observationZeroedDeg = null;
    joint.observationMechanismDeg = null;
    joint.observationCalibration = null;
  }
  for (const side of SIDES) {
    sim.controllers[side].serialConnected = false;
  }

  let appliedJoints = 0;
  let observedJoints = 0;
  const unavailableJoints = [];
  const heldJoints = [];
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
      const externalPosition = observation.positionDeg;
      const motorObservation = sample.motorJoints?.[canonicalName];
      const motorPosition = motorObservation?.available === true && finite(motorObservation.positionDeg)
        ? motorObservation.positionDeg
        : null;
      const motorDatum = Number(softwareZero?.sides?.[side]?.motorJoints?.[firmwareJoint]?.motorPositionDeg);
      const useMotorNative = motorPosition !== null && Number.isFinite(motorDatum);
      const position = useMotorNative ? motorPosition : externalPosition;
      const positionSource = useMotorNative ? "motor_native" : "external_absolute";
      const projection = projectHardwareDegrees(side, firmwareJoint, position, softwareZero, positionSource);
      if (!projection.calibrated) {
        unavailableJoints.push(canonicalName);
        continue;
      }
      const prior = previous.get(canonicalName);
      const dtSeconds = prior ? Math.max(0.001, (nowMs - prior.nowMs) / 1000) : 0;
      target.velocity = prior && prior.positionSource === positionSource && sample.sequence !== prior.sequence
        ? Math.max(-720, Math.min(720, shortestDegreeDelta(position, prior.position) / dtSeconds))
        : 0;
      target.rawAngle = ((position % 360) + 360) % 360;
      target.torque = 0;
      target.command = 0;
      target.observationAgeMs = sample.ageMs;
      target.observationRawDeg = position;
      target.observationExternalDeg = externalPosition;
      target.observationMotorDeg = motorPosition;
      target.observationPositionSource = positionSource;
      target.observationZeroedDeg = projection.zeroedDegrees;
      target.observationMechanismDeg = projection.mechanismDegrees;
      target.observationCalibration = projection.calibration;
      target.observationOutOfEnvelope = !projection.withinUsdLimits;
      target.observationValid = true;
      target.observationModelApplied = false;
      observedJoints += 1;
      if (String(projection.calibration.captureQuality || "").startsWith("unstable")) {
        target.observationSource = `esp32_${positionSource}_unstable`;
        heldJoints.push(canonicalName);
        continue;
      }
      if (!projection.withinUsdLimits) {
        target.observationSource = `esp32_${positionSource}_out_of_envelope`;
        heldJoints.push(canonicalName);
        continue;
      }
      target.angle = projection.renderDegrees;
      target.observationModelApplied = true;
      target.observationSource = `esp32_${positionSource}`;
      previous.set(canonicalName, {
        position,
        positionSource,
        sequence: sample.sequence,
        nowMs,
      });
      appliedJoints += 1;
    }

    const yawName = `${side}_hip_yaw`;
    const yawMotor = sample.motorJoints?.[yawName];
    const yawPosition = yawMotor?.available === true && finite(yawMotor.positionDeg)
      ? yawMotor.positionDeg
      : null;
    const yawDatum = Number(softwareZero?.sides?.[side]?.motorJoints?.hip_yaw?.motorPositionDeg);
    if (yawPosition === null || !Number.isFinite(yawDatum)) {
      unavailableJoints.push(yawName);
      continue;
    }
    const yawTarget = sim.getJoint("hip_yaw", side);
    const projection = projectHardwareDegrees(side, "hip_yaw", yawPosition, softwareZero, "motor_native");
    if (!yawTarget || !projection.calibrated) {
      unavailableJoints.push(yawName);
      continue;
    }
    const prior = previous.get(yawName);
    const dtSeconds = prior ? Math.max(0.001, (nowMs - prior.nowMs) / 1000) : 0;
    yawTarget.velocity = prior && sample.sequence !== prior.sequence
      ? Math.max(-720, Math.min(720, shortestDegreeDelta(yawPosition, prior.position) / dtSeconds))
      : 0;
    yawTarget.rawAngle = ((yawPosition % 360) + 360) % 360;
    yawTarget.torque = 0;
    yawTarget.command = 0;
    yawTarget.observationAgeMs = sample.ageMs;
    yawTarget.observationRawDeg = yawPosition;
    yawTarget.observationExternalDeg = null;
    yawTarget.observationMotorDeg = yawPosition;
    yawTarget.observationPositionSource = "motor_native";
    yawTarget.observationZeroedDeg = projection.zeroedDegrees;
    yawTarget.observationMechanismDeg = projection.mechanismDegrees;
    yawTarget.observationCalibration = projection.calibration;
    yawTarget.observationOutOfEnvelope = !projection.withinUsdLimits;
    yawTarget.observationValid = true;
    observedJoints += 1;
    if (!projection.withinUsdLimits) {
      yawTarget.observationModelApplied = false;
      yawTarget.observationSource = "esp32_motor_native_out_of_envelope";
      heldJoints.push(yawName);
      continue;
    }
    yawTarget.angle = projection.renderDegrees;
    yawTarget.observationModelApplied = true;
    yawTarget.observationSource = "esp32_motor_native";
    previous.set(yawName, {
      position: yawPosition,
      positionSource: "motor_native",
      sequence: sample.sequence,
      nowMs,
    });
    appliedJoints += 1;
  }
  sim.playMode = false;
  sim.canUtilization = 0;
  sim.canFramesWindow = 0;
  sim.scenario = "hardware-observation";
  return {
    appliedJoints,
    observedJoints,
    availableSides: [...validated.availableSides],
    unavailableJoints,
    heldJoints,
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
    joint.observationModelApplied = false;
    joint.observationAgeMs = null;
    joint.observationSource = "unavailable";
    joint.observationOutOfEnvelope = false;
    joint.observationRawDeg = null;
    joint.observationExternalDeg = null;
    joint.observationMotorDeg = null;
    joint.observationPositionSource = "unavailable";
    joint.observationZeroedDeg = null;
    joint.observationMechanismDeg = null;
    joint.observationCalibration = null;
  }
}

export const HARDWARE_OBSERVATION_SCHEMA = SCHEMA;
