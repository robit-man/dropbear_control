import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { proceduralFallbackEvidence, resolveReleasedCadAsset, validateCadRegistry } from "../js/cad_support.js";

const registry = JSON.parse(
  await readFile(new URL("../assets/cad_support.generated.json", import.meta.url), "utf8"),
);

assert.equal(validateCadRegistry(registry), true);
assert.equal(registry.summary.models, 44);
assert.equal(registry.summary.source_variants, 53);
assert.equal(registry.summary.geometry_configurations, 53);
assert.equal(registry.summary.accepted_configurations, 0);
assert.equal(registry.summary.browser_loadable_configurations, 0);
assert.equal(registry.summary.candidate_reports, 1);
assert.equal(registry.summary.dropbear_bound_cad_assets, 0);

assert.deepEqual(resolveReleasedCadAsset(registry, null), {
  supported: false,
  reason: "exact_configuration_required",
  asset: null,
});

const candidate = registry.configurations.find((item) => item.candidate_reports.length === 1);
assert.ok(candidate);
assert.deepEqual(
  resolveReleasedCadAsset(registry, {
    series: candidate.series,
    model: candidate.model,
    configurationId: candidate.configuration_id,
  }),
  { supported: false, reason: "candidate_not_reviewed_or_released", asset: null },
);

const tampered = structuredClone(registry);
tampered.configurations[0].browser_loadable = true;
tampered.configurations[0].assets = { housing_glb: {}, output_glb: {}, collision_glb: {} };
assert.throws(() => validateCadRegistry(tampered), /UNRELEASED_ASSET_EXPOSURE/);

assert.deepEqual(proceduralFallbackEvidence(), {
  evidenceClass: "toy-visual-only",
  physicalGeometry: false,
  collisionGeometry: false,
  actuatorPlant: false,
  supportGranted: false,
});

console.log("CAD SUPPORT TESTS PASSED");
