import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const calibrationSource = await readFile(new URL("../js/hardware_calibration.js", import.meta.url), "utf8");
const {
  HARDWARE_DEFAULT_STANCE_CALIBRATION,
  HARDWARE_TO_USD_DIRECTION,
  projectHardwareDegrees,
} = await import(`data:text/javascript;base64,${Buffer.from(calibrationSource).toString("base64")}`);


for (const joint of ["hip_pitch", "knee"]) {
  const datum = HARDWARE_DEFAULT_STANCE_CALIBRATION.sides.right[joint].rawDatumDeg;
  const projected = projectHardwareDegrees(
    "right", joint, datum + 5, null, "motor_control_aligned",
  );
  assert.equal(HARDWARE_TO_USD_DIRECTION.right[joint], -1);
  assert.equal(projected.direction, -1);
  assert.equal(
    projected.mechanismDegrees,
    projected.calibration.referenceDeg - 5,
    `right ${joint} must move opposite encoder-positive in the USD`,
  );
}

const rightYaw = projectHardwareDegrees(
  "right", "hip_yaw", 5, null, "motor_control_aligned",
);
assert.equal(rightYaw.direction, -1);
assert.equal(rightYaw.mechanismDegrees, -5);

for (const [side, joint] of [["left", "knee"], ["right", "hip_roll"]]) {
  const datum = HARDWARE_DEFAULT_STANCE_CALIBRATION.sides[side][joint].rawDatumDeg;
  const projected = projectHardwareDegrees(
    side, joint, datum + 5, null, "motor_control_aligned",
  );
  assert.equal(projected.direction, 1, `${side} ${joint} must retain encoder-positive USD direction`);
  assert.equal(projected.mechanismDegrees, projected.calibration.referenceDeg + 5);
}

console.log("ok hardware-to-USD direction mapping");
