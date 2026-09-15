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

const wrapped = projectHardwareDegrees("right", "outer_calf", 359);
assert.equal(wrapped.mechanismDegrees, -126);
assert.equal(wrapped.withinUsdLimits, false);

const left = projectHardwareDegrees("left", "knee", 28);
assert.equal(left.calibrated, false);
assert.equal(left.mechanismDegrees, null);

console.log("HARDWARE CALIBRATION TESTS PASSED");
