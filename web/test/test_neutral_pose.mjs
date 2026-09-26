import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const dropbearSource = await readFile(new URL("../js/dropbear.js", import.meta.url), "utf8");
const { DropbearSim } = await import(
  `data:text/javascript;base64,${Buffer.from(dropbearSource).toString("base64")}`
);

const sim = new DropbearSim();
for (const side of ["left", "right"]) {
  const knee = sim.getJoint("knee", side);
  assert.equal(knee.angle, 180, `${side} knee must initialize at its 180° mechanical lock datum`);
  assert.equal(knee.desiredPosition, 180, `${side} knee neutral target must remain locked`);
}

sim.setScenario("neutral");
for (const side of ["left", "right"]) {
  assert.equal(sim.getJoint("knee", side).desiredPosition, 180);
}

console.log("ok neutral knees initialize locked");
