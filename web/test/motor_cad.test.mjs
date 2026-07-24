import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../..");
const manifest = JSON.parse(
  await readFile(resolve(root, "web/assets/cad/dropbear-motor-cad.json"), "utf8"),
);

assert.equal(manifest.schema, "dropbear-motor-cad-v1");
assert.deepEqual(Object.keys(manifest.motors).sort(), ["x10-s2", "x8-pro"]);
assert.equal(manifest.motors["x8-pro"].dropbearClass, "RMD-X8");
assert.equal(manifest.motors["x8-pro"].axis, "y");
assert.deepEqual(manifest.motors["x8-pro"].axisVector, [0, 1, 0]);
assert.equal(manifest.motors["x10-s2"].dropbearClass, "RMD-X10");
assert.equal(manifest.motors["x10-s2"].axis, "z");
assert.deepEqual(manifest.motors["x10-s2"].axisVector, [0, 0, 1]);

for (const record of Object.values(manifest.motors)) {
  const source = await readFile(resolve(root, record.sourceRelativePath));
  assert.equal(createHash("sha256").update(source).digest("hex"), record.sourceStepSha256);
  assert.equal(record.outputSolidCount, 1);
  assert.ok(record.housingSolidCount >= 1);
  assert.ok(record.housingTriangles > 1000);
  assert.ok(record.outputTriangles > 1000);
  assert.equal(record.visualPartitionOnly, true);
  assert.equal(record.acceptedDynamicsAuthority, false);
  for (const role of ["housing", "output"]) {
    const glb = await readFile(resolve(root, `web/assets/cad/${record.key}/${role}.glb`));
    assert.equal(glb.subarray(0, 4).toString("ascii"), "glTF");
    assert.ok(glb.length > 10_000);
  }
}

const viewer = await readFile(resolve(root, "web/js/cad_viewer.js"), "utf8");
assert.match(viewer, /this\.outputGroup\.rotation\[axis\] = angle/);
assert.match(viewer, /dropbear-motor-cad\.json/);

console.log("DROPBEAR MOTOR CAD TESTS PASSED");
