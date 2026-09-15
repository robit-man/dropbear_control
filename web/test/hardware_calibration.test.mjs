import assert from "node:assert/strict";

import {
  HARDWARE_DEFAULT_STANCE_CALIBRATION,
  projectHardwareDegrees,
} from "../js/hardware_calibration.js";

assert.equal(HARDWARE_DEFAULT_STANCE_CALIBRATION.units, "degrees");
assert.equal(HARDWARE_DEFAULT_STANCE_CALIBRATION.capture.mode, "read_only");

const knee = projectHardwareDegrees("right", "knee", 28);
assert.equal(knee.calibrated, true);
assert.ok(Math.abs(knee.mechanismDegrees - 17.188734) < 1e-6);
assert.ok(Math.abs(knee.renderDegrees - 197.188734) < 1e-6);
assert.equal(knee.withinUsdLimits, true);

const kneeMovedFiveDegrees = projectHardwareDegrees("right", "knee", 33);
assert.ok(Math.abs(kneeMovedFiveDegrees.mechanismDegrees - (17.188734 + 5)) < 1e-6);

const wrapped = projectHardwareDegrees("right", "outer_calf", 359);
assert.equal(wrapped.mechanismDegrees, -126);
assert.equal(wrapped.withinUsdLimits, false);

const left = projectHardwareDegrees("left", "knee", 213);
assert.equal(left.calibrated, true);
assert.ok(Math.abs(left.mechanismDegrees - 17.188734) < 1e-6);
assert.equal(left.withinUsdLimits, true);

const unstableLeftInner = projectHardwareDegrees("left", "inner_calf", 188);
assert.equal(unstableLeftInner.withinUsdLimits, false);
assert.equal(unstableLeftInner.calibration.captureQuality, "unstable_bimodal_reading");

console.log("HARDWARE CALIBRATION TESTS PASSED");
