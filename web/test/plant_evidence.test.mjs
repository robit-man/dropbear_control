import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { MotorSim } from "../js/sim.js";
import { BROWSER_TOY_BACKEND, PLANT_REGISTRY_SHA256 } from "../js/plant_backends.generated.js";
import {
  LEGACY_VARIANTS,
  MOTOR_SERIES,
  TOY_PLANT_EVIDENCE,
  assertToySimulationSpec,
  defaultFleet,
} from "../js/motors.js";

const plantRegistryBytes = readFileSync(new URL("../../generated/myactuator/plant/runtime_registry.json", import.meta.url));
const plantRegistry = JSON.parse(plantRegistryBytes);
assert.equal(createHash("sha256").update(plantRegistryBytes).digest("hex"), PLANT_REGISTRY_SHA256);
assert.deepEqual(
  plantRegistry.backends.find((item) => item.backend_id === "browser-toy-demo-v1"),
  BROWSER_TOY_BACKEND,
);
assert.equal(plantRegistry.summary.models, 44);
assert.equal(plantRegistry.summary.runtime_loadable_parameter_sets, 0);

for (const spec of [...Object.values(MOTOR_SERIES), ...Object.values(LEGACY_VARIANTS)]) {
  assert.equal(assertToySimulationSpec(spec), true);
  assert.equal(spec.simulationEvidenceClass, "synthetic-demo-no-physical-fidelity");
  assert.equal(spec.simulationBackendId, "browser-toy-demo-v1");
  assert.equal(spec.simulationBackendKind, "toy_demo");
  assert.equal(spec.simulationSubstitutionScope, "browser-visualization-only");
  assert.equal(spec.simulationParameterSetId, null);
  assert.equal(spec.physicalPlantSupported, false);
  assert.equal(spec.physicalParameterSource, null);
  assert.equal(spec.physicalValidationEvidence, null);
}

for (const spec of defaultFleet()) {
  const motor = new MotorSim(spec);
  assert.equal(motor.evidenceClass, TOY_PLANT_EVIDENCE.simulationEvidenceClass);
  assert.equal(motor.backendId, BROWSER_TOY_BACKEND.backend_id);
  assert.equal(motor.backendKind, BROWSER_TOY_BACKEND.kind);
  assert.equal(motor.parameterSetId, null);
  assert.equal(motor.physicalPlantSupported, false);
}

const baseline = {
  id: 1,
  series: "RMD-X",
  model: "not-a-physical-identity",
  ...MOTOR_SERIES["RMD-X"],
};
assert.throws(
  () => new MotorSim({ ...baseline, simulationBackendId: "actuator-invented" }),
  /EXACT_TOY_BACKEND_IDENTITY_REQUIRED/,
);
assert.throws(
  () => new MotorSim({ ...baseline, simulationEvidenceClass: undefined }),
  /SIMULATION_EVIDENCE_CLASS_REQUIRED/,
);
assert.throws(
  () => new MotorSim({ ...baseline, physicalPlantSupported: true }),
  /UNSUPPORTED_PHYSICAL_PLANT_CLAIM/,
);
assert.throws(
  () => new MotorSim({ ...baseline, physicalParameterSource: "invented" }),
  /UNSUPPORTED_PHYSICAL_PLANT_CLAIM/,
);

console.log("PLANT EVIDENCE TESTS PASSED");
