import assert from "node:assert/strict";

import { DropbearSim } from "../js/dropbear.js";
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
    schema: "dropbear-passive-observation-v1",
    mode: "read_only",
    writeCapable: false,
    txBytes: 0,
    complete: true,
    sides: {
      left: side("left", leftSequence, [194, 72, 10, 213, 146]),
      right: side("right", rightSequence, [125, 188, 89, 28, 169]),
    },
  };
}

const sim = new DropbearSim();
sim.setScenario("walk");
const result = applyHardwareObservation(sim, snapshot(), 1_000);
assert.equal(result.appliedJoints, 8);
assert.equal(sim.playMode, false);
assert.equal(sim.scenario, "hardware-observation");
assert.equal(sim.getJoint("outer_calf", "left").observationValid, true);
assert.equal(sim.getJoint("inner_calf", "left").observationValid, false);
assert.equal(sim.getJoint("inner_calf", "left").observationSource, "esp32_external_absolute_unstable");
assert.equal(sim.getJoint("outer_calf", "right").angle, 180);
assert.ok(Math.abs(sim.getJoint("inner_calf", "right").angle - 168.540844) < 1e-6);
assert.equal(sim.getJoint("knee", "right").observationValid, false);
assert.equal(sim.getJoint("knee", "right").observationSource, "esp32_external_absolute_unstable");
assert.equal(sim.getJoint("knee", "right").observationRawDeg, 28);
assert.ok(Math.abs(sim.getJoint("knee", "right").observationMechanismDeg - 17.188734) < 1e-6);
assert.equal(sim.getJoint("hip_yaw", "left").observationValid, false);
assert.equal(sim.controllers.left.csv, "194,72,10,213,146");

const outOfEnvelope = snapshot(2, 2);
outOfEnvelope.sides.right.joints.right_outer_calf.positionDeg = 300;
const guardedSim = new DropbearSim();
const guarded = applyHardwareObservation(guardedSim, outOfEnvelope, 1_050);
assert.equal(guarded.appliedJoints, 7);
assert.equal(guardedSim.getJoint("outer_calf", "right").observationValid, false);
assert.equal(guardedSim.getJoint("outer_calf", "right").observationRawDeg, 300);
assert.ok(guarded.unavailableJoints.includes("right_outer_calf"));

const next = snapshot(2, 2);
next.sides.right.joints.right_outer_calf.positionDeg = 127;
applyHardwareObservation(sim, next, 1_100);
assert.equal(sim.getJoint("outer_calf", "right").velocity, 20);

const notSilent = snapshot();
notSilent.txBytes = 1;
assert.throws(() => validateHardwareObservation(notSilent), /not byte-silent/);

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
