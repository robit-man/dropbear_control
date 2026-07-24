import assert from "node:assert/strict";
import { ForceGroundContact } from "../js/force_ground_contact.js";

const contact = new ForceGroundContact({ massKg: 56.2289776 });
const airborne = contact.solve({
  left: { heelZ: 0.05, toeZ: 0.05 },
  right: { heelZ: 0.05, toeZ: 0.05 },
}, -0.4, 0.02);
assert.equal(airborne.normalForceN, 0);
assert.ok(Math.abs(airborne.verticalAccelerationMps2 + 9.80665) < 1e-9);

const impact = contact.solve({
  left: { heelZ: -0.001, toeZ: 0.0002 },
  right: { heelZ: -0.0004, toeZ: 0.0003 },
}, -0.7, 0.02);
assert.ok(impact.normalForceN > 56.2289776 * 9.80665);
assert.equal(impact.correctionZ, 0.001);
assert.ok(impact.left.heelHeightMm >= 0);
assert.ok(impact.right.heelHeightMm >= 0);
assert.ok(impact.left.loadKg + impact.right.loadKg > 0);
assert.equal(impact.guide, "FREE_ROOT_FORCE_CONTACT");

console.log("FORCE GROUND CONTACT TESTS PASSED");
