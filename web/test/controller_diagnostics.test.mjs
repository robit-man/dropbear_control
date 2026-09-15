import assert from "node:assert/strict";

import { classifyControllerSide } from "../js/controller_diagnostics.js";

const right = classifyControllerSide("right", {
  state: "observing",
  fresh: true,
  decodedLines: 42,
  rejectedLines: 0,
  readErrors: 0,
  ageMs: 2,
  sequence: 42,
});
assert.equal(right.transport, "success");
assert.equal(right.stream, "success");
assert.equal(right.calibration, "success");

const silentLeft = classifyControllerSide("left", {
  state: "observing",
  fresh: false,
  decodedLines: 0,
  rejectedLines: 0,
  readErrors: 0,
});
assert.equal(silentLeft.transport, "degraded");
assert.equal(silentLeft.stream, "degraded");
assert.equal(silentLeft.calibration, "unknown");

const failed = classifyControllerSide("left", {
  state: "error",
  fresh: false,
  readErrors: 1,
});
assert.equal(failed.transport, "fail");

console.log("controller diagnostic classification passed");
