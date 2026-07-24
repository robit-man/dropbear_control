import assert from "node:assert/strict";
import { VerticalGroundConstraint } from "../js/vertical_ground_constraint.js";

const guide = new VerticalGroundConstraint({ massKg: 42 });
let state = guide.solve({
  left: { heelZ: 0.115, toeZ: 0.115 },
  right: { heelZ: 0.116, toeZ: 0.116 },
});

assert.equal(state.valid, true);
assert.equal(state.guide, "Z_ONLY");
assert.ok(Math.abs(state.offsetZ + 0.115) < 1e-9);
assert.equal(state.left.contact, true);
assert.equal(state.right.contact, true);
assert.ok(Math.abs(state.left.loadKg + state.right.loadKg - 42) < 1e-9);

state = guide.solve({
  left: { heelZ: 0.115, toeZ: 0.117 },
  right: { heelZ: 0.180, toeZ: 0.182 },
}, 0.01);
assert.equal(state.left.contact, true);
assert.equal(state.right.contact, false);
assert.equal(state.left.heelContact, true);
assert.ok(state.left.heelLoadKg > state.left.toeLoadKg);
assert.ok(state.right.footHeightMm > 60);

state = guide.solve({
  left: { heelZ: 0.140, toeZ: 0.142 },
  right: { heelZ: 0.141, toeZ: 0.143 },
}, 0.02);
assert.ok(state.offsetZ > -0.14);
assert.ok(state.velocityZ < 0);

state = guide.solve({
  left: { heelZ: 0.100, toeZ: 0.102 },
  right: { heelZ: 0.141, toeZ: 0.143 },
}, 0.01);
assert.equal(state.constrained, true);
assert.ok(state.left.footHeightMm < 1e-6);
assert.ok(state.offsetZ >= -0.1000001);

guide.reset();
assert.equal(guide.lastState.valid, false);

console.log("VERTICAL GROUND CONSTRAINT TESTS PASSED");
