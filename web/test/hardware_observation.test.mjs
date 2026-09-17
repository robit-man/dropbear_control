import assert from "node:assert/strict";

import { DropbearSim } from "../js/dropbear.js";
import { captureSoftwareZero } from "../js/hardware_calibration.js";
import {
  applyHardwareObservation,
  validateHardwareObservation,
} from "../js/hardware_observation.js";

function joint(side, firmwareJoint, positionDeg) {
  return {
    canonicalName: `${side}_${firmwareJoint}`,
    firmwareJoint,
    positionDeg,
  };
}

function side(sideName, sequence, values) {
  const names = ["outer_calf", "inner_calf", "hip_pitch", "knee", "hip_roll"];
  return {
    fresh: true,
    sequence,
    ageMs: 12,
    rawLine: values.join(","),
    joints: Object.fromEntries(names.map((name, index) => [
      `${sideName}_${name}`,
      joint(sideName, name, values[index]),
    ])),
  };
}

function snapshot(leftSequence = 1, rightSequence = 1) {
  return {
    schema: "dropbear-hardware-observation-v2",
    mode: "read_only_with_diagnostic_queries",
    writeCapable: false,
    motionWriteCapable: false,
    txBytes: 0,
    complete: true,
    sides: {
      left: side("left", leftSequence, [125, 188, 89, 28, 169]),
      right: side("right", rightSequence, [194, 72, 10, 213, 146]),
    },
  };
}

function attachMotorTelemetry(payload, leftValues, rightValues) {
  const names = ["outer_calf", "inner_calf", "hip_pitch", "knee", "hip_yaw", "hip_roll"];
  for (const [sideName, values] of [["left", leftValues], ["right", rightValues]]) {
    payload.sides[sideName].motorJoints = Object.fromEntries(names.map((name, index) => [
      `${sideName}_${name}`,
      {
        canonicalName: `${sideName}_${name}`,
        available: Number.isFinite(values[index]),
        positionDeg: Number.isFinite(values[index]) ? values[index] : null,
        source: "rmd_v44_multi_turn_angle",
      },
    ]));
  }
  return payload;
}

const sim = new DropbearSim();
sim.setScenario("walk");
const result = applyHardwareObservation(sim, snapshot(), 1_000);
assert.equal(result.appliedJoints, 8);
assert.equal(sim.playMode, false);
assert.equal(sim.scenario, "hardware-observation");
assert.equal(sim.getJoint("outer_calf", "left").observationValid, true);
assert.equal(sim.getJoint("inner_calf", "right").observationValid, true);
assert.equal(sim.getJoint("inner_calf", "right").observationModelApplied, false);
assert.equal(sim.getJoint("inner_calf", "right").observationSource, "esp32_external_absolute_unstable");
assert.equal(sim.getJoint("outer_calf", "right").angle, 180);
assert.ok(Math.abs(sim.getJoint("inner_calf", "left").angle - 168.540844) < 1e-6);
assert.equal(sim.getJoint("knee", "left").observationValid, true);
assert.equal(sim.getJoint("knee", "left").observationModelApplied, false);
assert.equal(sim.getJoint("knee", "left").observationSource, "esp32_external_absolute_unstable");
assert.equal(sim.getJoint("knee", "left").observationRawDeg, 28);
assert.ok(Math.abs(sim.getJoint("knee", "left").observationMechanismDeg - 17.188734) < 1e-6);
assert.equal(sim.getJoint("hip_yaw", "left").observationValid, false);
assert.equal(sim.controllers.left.csv, "125,188,89,28,169");

const zeroPayload = snapshot();
const zero = captureSoftwareZero(zeroPayload, 7, "2026-09-15T21:00:00Z");
const zeroedSim = new DropbearSim();
const zeroed = applyHardwareObservation(zeroedSim, zeroPayload, 1_020, zero);
assert.equal(zeroed.observedJoints, 10);
assert.equal(zeroed.appliedJoints, 10);
assert.equal(zeroedSim.getJoint("knee", "left").observationModelApplied, true);
assert.equal(zeroedSim.getJoint("inner_calf", "right").observationModelApplied, true);

const nativeDatumPayload = attachMotorTelemetry(
  snapshot(3, 3),
  [100, 110, 120, 130, 140, 150],
  [200, 210, 220, 230, 240, 250],
);
const nativeZero = captureSoftwareZero(nativeDatumPayload, 7, "2026-09-15T21:01:00Z");
const nativeMovedPayload = attachMotorTelemetry(
  snapshot(4, 4),
  [100, 110, 120, 134, 143, 150],
  [200, 210, 220, 230, 238, 250],
);
const nativeSim = new DropbearSim();
const nativeResult = applyHardwareObservation(nativeSim, nativeMovedPayload, 1_040, nativeZero);
assert.equal(nativeResult.observedJoints, 12);
assert.equal(nativeResult.appliedJoints, 12);
assert.equal(nativeSim.getJoint("knee", "left").observationPositionSource, "motor_native");
assert.equal(nativeSim.getJoint("knee", "left").observationRawDeg, 134);
assert.equal(nativeSim.getJoint("knee", "left").observationExternalDeg, 28);
assert.ok(Math.abs(nativeSim.getJoint("knee", "left").observationMechanismDeg - 21.188734) < 1e-6);
assert.equal(nativeSim.getJoint("hip_yaw", "left").observationValid, true);
assert.equal(nativeSim.getJoint("hip_yaw", "left").observationPositionSource, "motor_native");
assert.equal(nativeSim.getJoint("hip_yaw", "left").observationMechanismDeg, 3);
assert.equal(nativeSim.getJoint("hip_yaw", "right").observationMechanismDeg, -2);

const outOfEnvelope = snapshot(2, 2);
outOfEnvelope.sides.left.joints.left_outer_calf.positionDeg = 300;
const guardedSim = new DropbearSim();
const guarded = applyHardwareObservation(guardedSim, outOfEnvelope, 1_050);
assert.equal(guarded.appliedJoints, 7);
assert.equal(guardedSim.getJoint("outer_calf", "left").observationValid, true);
assert.equal(guardedSim.getJoint("outer_calf", "left").observationModelApplied, false);
assert.equal(guardedSim.getJoint("outer_calf", "left").observationRawDeg, 300);
assert.ok(guarded.heldJoints.includes("left_outer_calf"));

const next = snapshot(2, 2);
next.sides.left.joints.left_outer_calf.positionDeg = 127;
applyHardwareObservation(sim, next, 1_100);
assert.equal(sim.getJoint("outer_calf", "left").velocity, 20);

const notSilent = snapshot();
notSilent.txBytes = 1;
assert.equal(validateHardwareObservation(notSilent).complete, true);
notSilent.motionWriteCapable = true;
assert.throws(() => validateHardwareObservation(notSilent), /physical motion output/);

const alignedPayload = attachMotorTelemetry(
  snapshot(5, 5),
  [10, 20, 30, 40, 50, 60],
  [70, 80, 90, 100, 110, 120],
);
for (const sideName of ["left", "right"]) {
  for (const [name, motor] of Object.entries(alignedPayload.sides[sideName].motorJoints)) {
    const jointName = name.slice(sideName.length + 1);
    motor.controlPositionDeg = jointName === "hip_yaw"
      ? 0 : alignedPayload.sides[sideName].joints[name]?.positionDeg;
    motor.controlAvailable = true;
    motor.alignmentFault = false;
  }
}
const alignedSim = new DropbearSim();
const alignedResult = applyHardwareObservation(alignedSim, alignedPayload, 1_060, null);
assert.equal(alignedResult.appliedJoints, 12);
assert.equal(alignedResult.observedJoints, 12);
assert.equal(alignedSim.getJoint("outer_calf", "left").observationPositionSource, "motor_control_aligned");
assert.equal(alignedSim.getJoint("hip_yaw", "right").observationPositionSource, "motor_control_aligned");
assert.equal(alignedSim.getJoint("hip_yaw", "right").observationMechanismDeg, 0);

const missingSide = snapshot();
missingSide.sides.right.fresh = false;
assert.equal(validateHardwareObservation(missingSide).complete, false);
const partialSim = new DropbearSim();
const partial = applyHardwareObservation(partialSim, missingSide);
assert.equal(partial.appliedJoints, 4);
assert.deepEqual(partial.availableSides, ["left"]);
assert.equal(partialSim.getJoint("knee", "left").observationValid, true);
assert.equal(partialSim.getJoint("knee", "right").observationValid, false);
assert.ok(partial.unavailableJoints.includes("right_knee"));

const noFreshSide = snapshot();
noFreshSide.sides.left.fresh = false;
noFreshSide.sides.right.fresh = false;
assert.throws(
  () => applyHardwareObservation(new DropbearSim(), noFreshSide),
  /at least one leg observation must be fresh/,
);

console.log("HARDWARE OBSERVATION TESTS PASSED");
