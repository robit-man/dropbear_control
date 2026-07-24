import assert from "node:assert/strict";

import { RLPolicyPlayer } from "../js/rl_policy.js";

const frames = [
  {
    time: 0,
    phase: 0,
    q: Array(22).fill(0),
    dq: Array(22).fill(0),
    contactLoadsKg: [21, 0, 21, 0],
    base: { height: 0.8, x: 0, vx: 0, roll: 0, pitch: 0 },
  },
  {
    time: 1,
    phase: 0.5,
    q: Array(22).fill(1),
    dq: Array(22).fill(2),
    contactLoadsKg: [0, 21, 0, 21],
    base: { height: 0.7, x: 0.2, vx: 0.3, roll: 0.1, pitch: -0.1 },
  },
];
const seen = [];
const player = new RLPolicyPlayer({ onFrame: (frame) => seen.push(frame) });
player.setPolicy({
  schema: "dropbear-walk-policy-v2",
  jointOrder: Array.from({ length: 22 }, (_, index) => `joint_${index}`),
  config: { verticalConstraint: false },
  frames,
});
player.seek(0.5);
assert.equal(seen.at(-1).q.length, 22);
assert.equal(seen.at(-1).q[0], 0.5);
assert.equal(seen.at(-1).base.height, 0.75);
assert.deepEqual(seen.at(-1).contactLoadsKg, [10.5, 10.5, 10.5, 10.5]);

player.loop = true;
player.play();
player.update(1.2);
assert.equal(player.playing, true);
assert.ok(player.elapsed < player.duration);

console.log("RL POLICY PLAYER TESTS PASSED");
