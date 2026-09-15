import assert from "node:assert/strict";

import { captureSoftwareZero } from "../js/hardware_calibration.js";
import {
  ANGLE_RECORDING_COLUMNS,
  angleRecordingCsv,
  observationRecordingRows,
} from "../js/hardware_recording.js";

const sensorNames = ["outer_calf", "inner_calf", "hip_pitch", "knee", "hip_roll"];
const values = { left: [194, 72, 10, 213, 146], right: [125, 188, 89, 28, 169] };
const payload = {
  mode: "read_only",
  writeCapable: false,
  txBytes: 0,
  sides: Object.fromEntries(["left", "right"].map((side, sideIndex) => [side, {
    fresh: true,
    configuredPath: `/dev/serial/${side}`,
    sequence: sideIndex + 10,
    ageMs: 4,
    joints: Object.fromEntries(sensorNames.map((joint, index) => [`${side}_${joint}`, {
      canId: `0x14${index}`,
      positionDeg: values[side][index],
    }])),
    motorJoints: Object.fromEntries([
      ...sensorNames,
      "hip_yaw",
    ].map((joint) => [`${side}_${joint}`, {
      positionDeg: null,
      available: false,
      status: "not_emitted_by_deployed_firmware",
    }])),
  }])),
};

const zero = captureSoftwareZero(payload, 7, "2026-09-15T08:00:00Z");
const rows = observationRecordingRows(payload, zero, 1234, "2026-09-15T08:00:01Z");
assert.equal(rows.length, 12);
assert.equal(rows.find((row) => row.side === "left" && row.joint === "knee").external_zeroed_deg, 0);
assert.equal(rows.find((row) => row.joint === "hip_yaw").external_raw_deg, null);
assert.equal(rows.every((row) => row.motor_native_available === false), true);
assert.equal(rows.every((row) => row.motor_native_deg === null), true);
assert.match(rows[0].motor_native_status, /not_emitted/);

payload.sides.left.motorJoints.left_knee.positionDeg = 100;
payload.sides.left.motorJoints.left_knee.available = true;
const motorZero = captureSoftwareZero(payload, 7, "2026-09-15T08:00:02Z");
payload.sides.left.motorJoints.left_knee.positionDeg = 104;
const motorRows = observationRecordingRows(payload, motorZero, 1235, "2026-09-15T08:00:03Z");
const motorKnee = motorRows.find((row) => row.side === "left" && row.joint === "knee");
assert.equal(motorKnee.motor_native_deg, 104);
assert.equal(motorKnee.motor_native_zeroed_deg, 4);
assert.equal(motorKnee.motor_native_available, true);

const csv = angleRecordingCsv(rows);
assert.equal(csv.split("\n")[0], ANGLE_RECORDING_COLUMNS.join(","));
assert.match(csv, /motor_native_deg,motor_native_zeroed_deg,motor_native_available,motor_native_status/);
assert.equal(csv.trim().split("\n").length, 13);

console.log("HARDWARE RECORDING TESTS PASSED");
