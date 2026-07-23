import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  admitSimulatorSelection,
  simulatorReadinessSummary,
  validateSimulatorRuntimeCatalog,
} from "../js/simulator_runtime.js";

const catalog = JSON.parse(
  await readFile(
    new URL("../assets/simulator_runtime_catalog.generated.json", import.meta.url),
    "utf8",
  ),
);
const model = catalog.models[0];
const base = {
  catalogGenerationSha256: catalog.integrity.record_sha256,
  modelKey: model.model_key,
  series: model.series,
  model: model.model,
  configurationId: model.configuration_ids[0],
  backendId: "browser-toy-demo-v1",
  backendKind: "toy_demo",
  useCase: "catalog_demo",
  requireExactModelFidelity: false,
  requirePhysicalValidation: false,
  requireDropbearWholeRobot: false,
};

assert.equal(validateSimulatorRuntimeCatalog(catalog), true);
assert.deepEqual(simulatorReadinessSummary(catalog), {
  catalogGenerationSha256: catalog.integrity.record_sha256,
  modelCount: 44,
  configurationCount: 53,
  exactModelReadyCount: 0,
  browserArticulatedAssetReadyCount: 0,
  dropbearWholeRobotReady: false,
  physicalIoEnabled: false,
  supportGranted: false,
});

const allowed = admitSimulatorSelection(catalog, base);
assert.equal(allowed.allowed, true);
assert.equal(allowed.backend.evidenceClass, "synthetic-demo-no-physical-fidelity");
assert.equal(allowed.exactModelFidelity, false);
assert.equal(allowed.physicalIo, false);
assert.equal("asset" in allowed, false);

assert.equal(
  admitSimulatorSelection(catalog, {
    ...base,
    catalogGenerationSha256: "0".repeat(64),
  }).reason,
  "stale_catalog_generation",
);
assert.equal(
  admitSimulatorSelection(catalog, {
    ...base,
    configurationId: catalog.models[1].configuration_ids[0],
  }).reason,
  "configuration_not_found",
);
assert.equal(
  admitSimulatorSelection(catalog, {
    ...base,
    backendKind: "protocol_emulator",
  }).reason,
  "backend_kind_mismatch",
);
assert.equal(
  admitSimulatorSelection(catalog, {
    ...base,
    requireExactModelFidelity: true,
  }).reason,
  "exact_model_fidelity_unavailable",
);

for (const mutation of [
  (value) => { value.support_granted = true; },
  (value) => { value.models[0].source_step_runtime_asset = true; },
  (value) => { value.models[0].configuration_ids.push(value.models[1].configuration_ids[0]); },
  (value) => { value.backends[0].command_capable = true; },
  (value) => { value.backends[1].models_actuator_dynamics = true; },
  (value) => { value.dropbear.whole_robot_runtime_ready = true; },
]) {
  const tampered = structuredClone(catalog);
  mutation(tampered);
  assert.throws(
    () => validateSimulatorRuntimeCatalog(tampered),
    /SIMULATOR_CATALOG_/,
  );
}

const serialized = JSON.stringify(catalog).toLowerCase();
for (const forbidden of [
  "/home/",
  "file://",
  "www.myactuator.com",
  "archive_url",
  "relative_path",
  "evidence_path",
]) {
  assert.equal(serialized.includes(forbidden), false);
}

console.log("SIMULATOR RUNTIME BROWSER TESTS PASSED");
