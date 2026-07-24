import assert from "node:assert/strict";
import {
  ALTERNATING_STEP_KEYFRAMES,
  ALTERNATING_STEP_PERIOD_S,
  CONTROLLER_PINS,
  DROPBEAR_SOURCE,
  DropbearSim,
  JOINT_DEFINITIONS,
  TASKS,
  sampleAlternatingStep,
} from "../js/dropbear.js";
import {
  DROPBEAR_USD_BINDINGS,
  DROPBEAR_USD_SOURCE,
  dropbearUsdBinding,
} from "../js/dropbear_usd.js";

const expectedIds = Array.from({ length: 12 }, (_, index) => 0x141 + index);

assert.equal(DROPBEAR_SOURCE.commit, "13cf5ecaa39b8b89c794fe905dcea0490cfa7726");
assert.equal(JOINT_DEFINITIONS.length, 12);
assert.deepEqual(JOINT_DEFINITIONS.map((joint) => joint.id), expectedIds);
assert.deepEqual(
  JOINT_DEFINITIONS.filter((joint) => joint.sensorPin == null).map((joint) => `${joint.side}:${joint.key}`),
  ["left:hip_yaw", "right:hip_yaw"],
);

const pin = (gpio) => CONTROLLER_PINS.find((entry) => entry.gpio === gpio);
assert.equal(CONTROLLER_PINS.length, 19);
assert.equal(pin(5)?.role, "MCP2515 chip select");
assert.equal(pin(17)?.role, "MCP2515 interrupt");
assert.equal(pin(21)?.role, "IMU SDA");
assert.equal(pin(22)?.role, "IMU SCL");
assert.deepEqual(
  [14, 27, 26, 25, 33].map((gpio) => pin(gpio)?.bus),
  ["ADC", "ADC", "ADC", "ADC", "ADC"],
);
assert.equal(pin(18)?.inferred, true);
assert.equal(pin(32)?.optional, true);
assert.deepEqual(TASKS.map((task) => task.periodMs), [1, 10, 10, 10]);
assert.equal(ALTERNATING_STEP_PERIOD_S, 2.8);
assert.equal(Math.max(...ALTERNATING_STEP_KEYFRAMES.map((frame) => frame.knee)), 52);
const heelStrike = sampleAlternatingStep(0, "left");
assert.equal(heelStrike.targets.knee, 180);
assert.equal(heelStrike.targets.hip_pitch, 143);
assert.equal(heelStrike.contact, 1);
const heelPrepare = sampleAlternatingStep(ALTERNATING_STEP_PERIOD_S * 0.94, "left");
assert.equal(heelPrepare.mode, "heel prepare");
assert.equal(heelPrepare.targets.knee, 180);
assert.equal(heelPrepare.targets.hip_pitch, 143);
assert.ok(heelPrepare.contact < heelStrike.contact);
const loading = sampleAlternatingStep(ALTERNATING_STEP_PERIOD_S * 0.12, "left");
assert.equal(loading.mode, "loading");
assert.ok(loading.targets.hip_pitch > heelStrike.targets.hip_pitch);
const pushOff = sampleAlternatingStep(ALTERNATING_STEP_PERIOD_S * 0.54, "left");
assert.equal(pushOff.mode, "push off");
assert.equal(pushOff.targets.hip_pitch, 202);
const highKnee = sampleAlternatingStep(ALTERNATING_STEP_PERIOD_S * 0.68, "left");
assert.equal(highKnee.mode, "high knee");
assert.equal(highKnee.targets.knee, 232);
assert.equal(highKnee.targets.hip_pitch, 151);
assert.ok(highKnee.targets.outer_calf !== highKnee.targets.inner_calf);
assert.equal(
  Math.min(...ALTERNATING_STEP_KEYFRAMES.map((frame) => frame.hipPitch)),
  -37,
);
const opposingLeg = sampleAlternatingStep(ALTERNATING_STEP_PERIOD_S * 0.68, "right");
assert.equal(highKnee.swing, true);
assert.equal(opposingLeg.swing, false);
for (let index = 0; index < 100; index += 1) {
  for (const side of ["left", "right"]) {
    const gait = sampleAlternatingStep(ALTERNATING_STEP_PERIOD_S * index / 100, side);
    assert.ok(gait.targets.knee >= 180);
    assert.ok(gait.targets.knee <= 360);
  }
}

assert.equal(DROPBEAR_USD_SOURCE.commit, "3c37aedce6d445205671d5714d05ae28b8c90e2c");
assert.equal(DROPBEAR_USD_SOURCE.license, "CC-BY-NC-SA-4.0");
assert.deepEqual(DROPBEAR_USD_BINDINGS.map((binding) => binding.canId), expectedIds);
assert.deepEqual(
  DROPBEAR_USD_BINDINGS.map((binding) => binding.usdJoint),
  [
    "LL_Revolute81",
    "LL_Revolute67",
    "RL_Revolute67",
    "RL_Revolute81",
    "LL_knee_actuator_joint",
    "LL_hip_joint",
    "RL_hip_joint",
    "RL_knee_actuator_joint",
    "PG_left_leg_roll",
    "PG_left_leg_pitch",
    "PG_right_leg_pitch",
    "PG_right_leg_roll",
  ],
);
assert.deepEqual(
  DROPBEAR_USD_BINDINGS.filter((binding) => binding.motor === "RMD-X8").map((binding) => binding.canLabel),
  ["0x141", "0x142", "0x143", "0x144"],
);
assert.equal(DROPBEAR_USD_BINDINGS.some((binding) => binding.closure), false);
assert.equal(dropbearUsdBinding(0x14A)?.firmwareJoint, "hip_roll");

const sim = new DropbearSim();
assert.equal(sim.playMode, false);
assert.equal(sim.firmwarePlayDefault, true);
assert.equal(sim.canBitrate, 1_000_000);
assert.equal(sim.getJoint("knee", "left").minAngle, 180);
assert.equal(sim.getJoint("knee", "right").maxAngle, 360);
sim.setJointTarget(0x145, 90, true);
assert.equal(sim.getJoint("knee", "left").desiredPosition, 180);

const guardedAngle = sim.joints[0].angle;
for (let index = 0; index < 30; index += 1) sim.step(0.01);
assert.equal(sim.joints[0].angle, guardedAngle);
assert.equal(sim.canUtilization, 0);

sim.setScenario("walk");
let maxWalkKnee = 180;
for (let index = 0; index < 220; index += 1) {
  sim.step(0.01);
  maxWalkKnee = Math.max(
    maxWalkKnee,
    sim.getJoint("knee", "left").angle,
    sim.getJoint("knee", "right").angle,
  );
}
assert.equal(sim.playMode, true);
assert.ok(sim.joints.some((joint) => Math.abs(joint.angle - 180) > 0.5));
assert.ok(sim.joints.some((joint) => Math.abs(joint.torque) > 0.01));
assert.equal(Number(sim.canUtilization.toFixed(2)), 15.36);
assert.ok(sim.controllers.left.adcReads > 0);
assert.match(sim.controllers.left.csv, /^-?\d+\.\d(,-?\d+\.\d){4}$/);
assert.ok(sim.getJoint("knee", "left").angle >= 180);
assert.ok(sim.getJoint("knee", "right").angle >= 180);
assert.ok(maxWalkKnee > 202);

let response = sim.command("torque left hip_yaw 125");
assert.equal(response.ok, true);
assert.equal(sim.getJoint("hip_yaw", "left").command, 1.25);

response = sim.command("impedance right knee 1 205 4.5", "right");
assert.equal(response.ok, true);
assert.equal(sim.getJoint("knee", "right").desiredPosition, 205);
assert.equal(sim.getJoint("knee", "right").desiredVelocity, 4.5);
response = sim.command("impedance right knee 1 120 0", "right");
assert.equal(response.ok, true);
assert.equal(sim.getJoint("knee", "right").desiredPosition, 180);
response = sim.command("constrain knee 0 100", "right");
assert.equal(response.ok, false);

response = sim.command("torque center knee 100");
assert.equal(response.ok, false);
response = sim.command("nonsense");
assert.equal(response.ok, false);

sim.injectFault("can");
assert.equal(sim.faults.canDrop, true);
assert.equal(sim.controllers.left.canOnline, false);
sim.injectFault("can");
assert.equal(sim.faults.canDrop, false);
assert.equal(sim.controllers.right.canOnline, true);

response = sim.command("stop");
assert.equal(response.ok, true);
assert.equal(sim.playMode, false);
sim.step(0.01);
assert.equal(Number(sim.canUtilization.toFixed(2)), 15.36);
sim.step(0.01);
assert.equal(sim.canUtilization, 0);

console.log("DROPBEAR DIGITAL TWIN TESTS PASSED");
