import assert from "node:assert/strict";

import {
  HARDWARE_DEFAULT_STANCE_CALIBRATION,
  projectHardwareDegrees,
} from "../js/hardware_calibration.js";

assert.equal(HARDWARE_DEFAULT_STANCE_CALIBRATION.units, "degrees");
assert.equal(HARDWARE_DEFAULT_STANCE_CALIBRATION.capture.mode, "read_only");

const knee = projectHardwareDegrees("right", "knee", 213);
assert.equal(knee.calibrated, true);
assert.ok(Math.abs(knee.mechanismDegrees - 17.188734) < 1e-6);
assert.ok(Math.abs(knee.renderDegrees - 197.188734) < 1e-6);
assert.equal(knee.withinUsdLimits, true);

const kneeMovedFiveDegrees = projectHardwareDegrees("right", "knee", 218);
assert.ok(Math.abs(kneeMovedFiveDegrees.mechanismDegrees - (17.188734 + 5)) < 1e-6);

const wrapped = projectHardwareDegrees("left", "outer_calf", 359);
assert.equal(wrapped.mechanismDegrees, -126);
assert.equal(wrapped.withinUsdLimits, false);

const left = projectHardwareDegrees("left", "knee", 28);
assert.equal(left.calibrated, true);
assert.ok(Math.abs(left.mechanismDegrees - 17.188734) < 1e-6);
assert.equal(left.withinUsdLimits, true);

const unstableRightInner = projectHardwareDegrees("right", "inner_calf", 72);
assert.equal(unstableRightInner.withinUsdLimits, true);
assert.equal(unstableRightInner.calibration.captureQuality, "unstable_bimodal_reading");

const motorWithoutZero = projectHardwareDegrees("left", "knee", 100, null, "motor_native");
assert.equal(motorWithoutZero.calibrated, false);

const motorZero = {
  capturedAt: "2026-09-15T21:01:00Z",
  sides: { left: { motorJoints: { knee: { motorPositionDeg: 100 }, hip_yaw: { motorPositionDeg: 42 } } } },
};
const motorKnee = projectHardwareDegrees("left", "knee", 105, motorZero, "motor_native");
assert.equal(motorKnee.calibrated, true);
assert.ok(Math.abs(motorKnee.mechanismDegrees - 22.188734) < 1e-6);
const motorYaw = projectHardwareDegrees("left", "hip_yaw", 45, motorZero, "motor_native");
assert.equal(motorYaw.calibrated, true);
assert.equal(motorYaw.mechanismDegrees, 3);

console.log("HARDWARE CALIBRATION TESTS PASSED");
