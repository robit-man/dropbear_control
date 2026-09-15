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
      left: side("left", leftSequence, [181, 182, 183, 204, 185]),
      right: side("right", rightSequence, [186, 187, 188, 209, 190]),
    },
  };
}

const sim = new DropbearSim();
sim.setScenario("walk");
const result = applyHardwareObservation(sim, snapshot(), 1_000);
assert.equal(result.appliedJoints, 10);
assert.deepEqual(result.unavailableJoints, ["left_hip_yaw", "right_hip_yaw"]);
assert.equal(sim.playMode, false);
assert.equal(sim.scenario, "hardware-observation");
assert.equal(sim.getJoint("outer_calf", "left").angle, 181);
assert.equal(sim.getJoint("knee", "right").angle, 209);
assert.equal(sim.getJoint("hip_yaw", "left").observationValid, false);
assert.equal(sim.controllers.left.csv, "181,182,183,204,185");

const next = snapshot(2, 2);
next.sides.left.joints.left_outer_calf.positionDeg = 183;
applyHardwareObservation(sim, next, 1_100);
assert.equal(sim.getJoint("outer_calf", "left").velocity, 20);

const notSilent = snapshot();
notSilent.txBytes = 1;
assert.throws(() => validateHardwareObservation(notSilent), /not byte-silent/);

const missingSide = snapshot();
missingSide.sides.right.fresh = false;
assert.equal(validateHardwareObservation(missingSide).complete, false);
const partialSim = new DropbearSim();
const partial = applyHardwareObservation(partialSim, missingSide);
assert.equal(partial.appliedJoints, 5);
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
