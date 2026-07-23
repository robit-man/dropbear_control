from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from myactuator_lib.plant_models import (
    BackendAdmissionReason,
    BackendKind,
    PlantApplicability,
    PlantRegistryError,
    SimulationBackendRegistry,
)


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "generated/myactuator/plant/runtime_registry.json"
SCHEMA_PATH = ROOT / "schemas/myactuator-plant-registry.schema.json"
SPEC = importlib.util.spec_from_file_location(
    "generate_plant_registry", ROOT / "tools/generate_plant_registry.py"
)
generator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(generator)


def synthetic_parameter_set() -> dict:
    envelope_id = "nominal-envelope"
    parameters = {}
    sources = []
    fact_ids = []
    fact_hashes = {}

    def source_for(field_id: str) -> str:
        identifier = "plantfact-" + hashlib.sha256(
            field_id.encode("utf-8")
        ).hexdigest()[:20]
        fact_ids.append(identifier)
        fact_hashes[identifier] = hashlib.sha256(
            ("fact:" + field_id).encode("utf-8")
        ).hexdigest()
        sources.append(
            {
                "source_id": identifier,
                "kind": "reviewed_source_fact",
                "locator": f"synthetic-fixture/{field_id}",
                "revision": "fixture-decision-generation",
                "sha256": fact_hashes[identifier],
                "claim_scope": field_id,
                "acquired_at_utc": "2026-07-22T00:00:00Z",
            }
        )
        return identifier

    for group, fields in generator.EXPECTED_UNITS.items():
        parameters[group] = {}
        for name, unit in fields.items():
            field_id = f"{group}.{name}"
            source_id = source_for(field_id)
            value = 0.9 if "efficiency" in name else 1.0
            if name == "max_continuous_output_torque_nm":
                value = 10.0
            elif name == "max_peak_output_torque_nm":
                value = 20.0
            parameters[group][name] = {
                "value": value,
                "unit": unit,
                "uncertainty": {
                    "kind": "bounded_interval",
                    "lower": value * 0.9,
                    "upper": value * 1.1,
                    "unit": unit,
                    "coverage_probability": 1.0,
                },
                "source_refs": [source_id],
                "applicability_envelope_refs": [envelope_id],
                "validation_class": "official_specification",
            }
    envelope_sources = {
        name: source_for(f"operating_envelope.{name}")
        for name in generator.EXPECTED_ENVELOPE_UNITS
    }

    def range_value(
        name: str, minimum: float, maximum: float, unit: str
    ) -> dict:
        return {
            "minimum": minimum,
            "maximum": maximum,
            "unit": unit,
            "uncertainty": {
                "kind": "bounded_interval",
                "lower": minimum,
                "upper": maximum,
                "unit": unit,
                "coverage_probability": 1.0,
            },
            "source_refs": [envelope_sources[name]],
            "validation_class": "official_specification",
        }

    return {
        "plant_id": "plant-x12-320-reva-fw123-v44-can-iq",
        "parameter_revision": 1,
        "status": "sourced",
        "runtime_loadable": True,
        "runtime_adapter_id": "plant-adapter-deterministic-fixed-step-v1",
        "runtime_contract_id": "plantruntime-" + "8" * 20,
        "support_granted": False,
        "physical_motion_authority": False,
        "applicability": {
            "series": "RMD-X",
            "model": "X12-320",
            "hardware_revision": "rev-a",
            "drive_firmware": "fw-1.2.3",
            "protocol_version": "rmd-can-v4.4-2023-10-25",
            "transport": "can-classic-1mbit",
            "control_mode": "iq-control",
        },
        "model_forms": {
            "electrical": "dq-lumped-v1",
            "mechanical": "two-inertia-output-v1",
            "transmission": "ratio-efficiency-compliance-v1",
            "friction_backlash": "coulomb-viscous-deadzone-v1",
            "saturation": "current-speed-torque-duration-v1",
            "thermal": "two-node-rc-v1",
            "sensor": "quantized-biased-noisy-v1",
            "latency": "bounded-delay-jitter-v1",
            "integrator": "semi-implicit-euler-v1",
        },
        "sources": sources,
        "operating_envelopes": [
            {
                "envelope_id": envelope_id,
                "supply_voltage_v": range_value(
                    "supply_voltage_v", 40.0, 52.0, "V"
                ),
                "ambient_temperature_k": range_value(
                    "ambient_temperature_k", 273.15, 323.15, "K"
                ),
                "output_speed_rad_s": range_value(
                    "output_speed_rad_s", -10.0, 10.0, "rad/s"
                ),
                "output_torque_nm": range_value(
                    "output_torque_nm", -20.0, 20.0, "N*m"
                ),
                "rotation_direction": "bidirectional",
            }
        ],
        "parameters": parameters,
        "validation": {
            "class": "source_only",
            "evidence_refs": [],
            "scenario_ids": [],
            "validated_at_utc": None,
        },
        "assembly": {
            "assembly_registry_artifact_id": (
                "myactuator-plant-parameter-set-registry"
            ),
            "assembly_registry_generation_sha256": "1" * 64,
            "protocol_applicability_registry_sha256": "2" * 64,
            "accepted_protocol_decision_ids": [
                "protocoldecision-" + "3" * 20
            ],
            "candidate_decision_registry_sha256": "4" * 64,
            "candidate_decision_registry_generation_sha256": "5" * 64,
            "source_fact_ids": fact_ids,
            "source_fact_sha256": fact_hashes,
            "source_fact_set_sha256": "6" * 64,
            "materializer_sha256": "7" * 64,
            "physical_correlation_evidence_present": False,
        },
    }


def registry_with_parameter_set(base: dict, item: dict) -> dict:
    registry = copy.deepcopy(base)
    registry["parameter_sets"] = [copy.deepcopy(item)]
    registry["source_hashes"]["parameter_set_sha256"] = {item["plant_id"]: "b" * 64}
    registry["source_hashes"]["runtime_contract_sha256"] = {
        item["runtime_contract_id"]: "c" * 64
    }
    coverage = next(
        value
        for value in registry["model_coverage"]
        if (value["series"], value["model"])
        == (item["applicability"]["series"], item["applicability"]["model"])
    )
    coverage.update(status="sourced", plant_ids=[item["plant_id"]], denial_reason=None)
    registry["backends"].append(
        {
            "backend_id": f"actuator-{item['plant_id']}",
            "kind": "actuator_plant",
            "evidence_class": "sil-plant-sourced",
            "runtime_loadable": True,
            "models_physical_dynamics": True,
            "physically_validated": False,
            "parameter_set_id": item["plant_id"],
            "runtime_contract_id": item["runtime_contract_id"],
            "substitution_scope": "single-actuator-mechanics",
        }
    )
    registry["summary"].update(
        sourced_parameter_sets=1,
        runtime_loadable_parameter_sets=1,
        physically_validated_parameter_sets=0,
        backend_descriptors=len(registry["backends"]),
    )
    return registry


class PlantRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_baseline_schema_and_model_complete_denial(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema, format_checker=FormatChecker()).validate(self.registry)
        generator.validate_registry(copy.deepcopy(self.registry))
        self.assertEqual(self.registry["summary"]["models"], 44)
        self.assertEqual(self.registry["summary"]["sourced_parameter_sets"], 0)
        self.assertEqual(self.registry["summary"]["runtime_loadable_parameter_sets"], 0)
        self.assertEqual(len(self.registry["model_coverage"]), 44)
        self.assertTrue(all(item["status"] == "unsupported" for item in self.registry["model_coverage"]))

    def test_complete_synthetic_parameter_contract_passes_without_support(self) -> None:
        item = synthetic_parameter_set()
        generator._parameter_validator(self.schema).validate(item)
        generator.validate_parameter_set(item)
        values = list(generator.parameter_items(item))
        self.assertEqual(len(values), 34)
        self.assertFalse(item["support_granted"])
        self.assertEqual(item["validation"]["class"], "source_only")

    def test_schema_requires_every_parameter_domain_and_evidence_field(self) -> None:
        validator = generator._parameter_validator(self.schema)
        for group in generator.EXPECTED_UNITS:
            broken = synthetic_parameter_set()
            del broken["parameters"][group]
            with self.subTest(group=group), self.assertRaises(ValidationError):
                validator.validate(broken)
        broken = synthetic_parameter_set()
        del broken["parameters"]["thermal"]["max_case_temperature_k"]["uncertainty"]
        with self.assertRaises(ValidationError):
            validator.validate(broken)

    def test_semantics_reject_unit_uncertainty_reference_and_wildcard_drift(self) -> None:
        mutations = []
        wrong_unit = synthetic_parameter_set()
        wrong_unit["parameters"]["electrical"]["phase_resistance_ohm"]["unit"] = "mohm"
        mutations.append(wrong_unit)
        outside = synthetic_parameter_set()
        outside["parameters"]["mechanical"]["rotor_inertia_kg_m2"]["uncertainty"]["upper"] = 0.5
        mutations.append(outside)
        unknown_source = synthetic_parameter_set()
        unknown_source["parameters"]["sensor"]["current_noise_stddev_a"]["source_refs"] = ["missing-source"]
        mutations.append(unknown_source)
        wildcard = synthetic_parameter_set()
        wildcard["applicability"]["drive_firmware"] = "latest"
        mutations.append(wildcard)
        for index, item in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(generator.PlantRegistryError):
                generator.validate_parameter_set(item)

    def test_toy_and_protocol_backends_are_distinct_and_nonphysical(self) -> None:
        registry = SimulationBackendRegistry(self.registry)
        replay = registry.resolve(
            "canonical-recorded-state-replay-v1",
            BackendKind.RECORDED_REPLAY,
        )
        toy = registry.resolve("browser-toy-demo-v1", BackendKind.TOY_DEMO)
        protocol = registry.resolve("rmd-v44-protocol-emulator", BackendKind.PROTOCOL_EMULATOR)
        synthetic = registry.resolve(
            "synthetic-electromechanical-fixed-step-v1",
            BackendKind.SYNTHETIC_ACTUATOR_PLANT,
        )
        self.assertTrue(replay.allowed)
        self.assertTrue(toy.allowed)
        self.assertTrue(protocol.allowed)
        self.assertTrue(synthetic.allowed)
        self.assertEqual(
            replay.backend.substitution_scope,  # type: ignore[union-attr]
            "host-state-replay-only",
        )
        self.assertFalse(replay.backend.models_physical_dynamics)  # type: ignore[union-attr]
        self.assertFalse(toy.backend.models_physical_dynamics)  # type: ignore[union-attr]
        self.assertFalse(protocol.backend.models_physical_dynamics)  # type: ignore[union-attr]
        self.assertTrue(synthetic.backend.models_physical_dynamics)  # type: ignore[union-attr]
        self.assertFalse(synthetic.backend.physically_validated)  # type: ignore[union-attr]
        rigid = registry.resolve(
            "dropbear-rigid-body-unavailable-v1",
            BackendKind.RIGID_BODY,
        )
        self.assertFalse(rigid.allowed)
        self.assertEqual(
            rigid.reason, BackendAdmissionReason.BACKEND_NOT_LOADABLE
        )
        mismatch = registry.resolve("browser-toy-demo-v1", BackendKind.ACTUATOR_PLANT)
        self.assertEqual(mismatch.reason, BackendAdmissionReason.BACKEND_KIND_MISMATCH)

    def test_no_plant_backend_or_family_fallback_exists_in_baseline(self) -> None:
        registry = SimulationBackendRegistry(self.registry)
        selection = PlantApplicability(
            "RMD-X", "X12-320", "rev-a", "fw-1.2.3",
            "rmd-can-v4.4-2023-10-25", "can-classic-1mbit", "iq-control",
        )
        decision = registry.resolve(
            "actuator-plant-x12-320-reva-fw123-v44-can-iq",
            BackendKind.ACTUATOR_PLANT,
            applicability=selection,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, BackendAdmissionReason.BACKEND_NOT_FOUND)
        self.assertEqual(registry.parameter_set_count, 0)

    def test_synthetic_plant_requires_all_seven_exact_applicability_fields(self) -> None:
        item = synthetic_parameter_set()
        value = registry_with_parameter_set(self.registry, item)
        generator.validate_registry(copy.deepcopy(value))
        registry = SimulationBackendRegistry(value)
        exact = PlantApplicability(**item["applicability"])
        backend_id = f"actuator-{item['plant_id']}"
        admitted = registry.resolve(backend_id, BackendKind.ACTUATOR_PLANT, applicability=exact)
        self.assertTrue(admitted.allowed, admitted)
        self.assertIsNotNone(admitted.parameter_set)
        self.assertFalse(admitted.parameter_set["support_granted"])  # type: ignore[index]
        wrong = PlantApplicability(
            exact.series, exact.model, exact.hardware_revision, "fw-1.2.4",
            exact.protocol_version, exact.transport, exact.control_mode,
        )
        denied = registry.resolve(backend_id, BackendKind.ACTUATOR_PLANT, applicability=wrong)
        self.assertEqual(denied.reason, BackendAdmissionReason.PLANT_APPLICABILITY_MISMATCH)
        missing = registry.resolve(backend_id, BackendKind.ACTUATOR_PLANT)
        self.assertEqual(missing.reason, BackendAdmissionReason.PLANT_APPLICABILITY_REQUIRED)

    def test_malformed_backend_parameter_binding_is_rejected(self) -> None:
        broken = copy.deepcopy(self.registry)
        broken["backends"][0]["models_physical_dynamics"] = True
        with self.assertRaises(PlantRegistryError):
            SimulationBackendRegistry(broken)

    def test_runtime_rechecks_generated_fact_and_envelope_provenance(self) -> None:
        item = synthetic_parameter_set()
        value = registry_with_parameter_set(self.registry, item)
        SimulationBackendRegistry(value)
        mutations = []
        missing_fact = copy.deepcopy(value)
        missing_fact["parameter_sets"][0]["assembly"]["source_fact_ids"].pop()
        mutations.append(missing_fact)
        hand_source = copy.deepcopy(value)
        hand_source["parameter_sets"][0]["sources"][0]["kind"] = (
            "official_datasheet"
        )
        mutations.append(hand_source)
        wrong_parameter_source = copy.deepcopy(value)
        wrong_parameter_source["parameter_sets"][0]["parameters"][
            "electrical"
        ]["phase_resistance_ohm"]["source_refs"] = [
            "plantfact-" + "f" * 20
        ]
        mutations.append(wrong_parameter_source)
        wrong_envelope_source = copy.deepcopy(value)
        wrong_envelope_source["parameter_sets"][0]["operating_envelopes"][0][
            "supply_voltage_v"
        ]["source_refs"] = ["plantfact-" + "e" * 20]
        mutations.append(wrong_envelope_source)
        for index, broken in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                PlantRegistryError
            ):
                SimulationBackendRegistry(broken)
        broken = copy.deepcopy(self.registry)
        broken["backends"].append(
            {
                "backend_id": "orphan-plant",
                "kind": "actuator_plant",
                "evidence_class": "sil-plant-sourced",
                "runtime_loadable": True,
                "models_physical_dynamics": True,
                "physically_validated": False,
                "parameter_set_id": "plant-missing",
                "substitution_scope": "single-actuator-mechanics",
            }
        )
        with self.assertRaises(PlantRegistryError):
            SimulationBackendRegistry(broken)

    def test_v2_contract_joins_as_exact_sourced_backend(self) -> None:
        from tests.plant_runtime_adapter_v2.test_plant_runtime_adapter_v2 import (
            Fixture as V2Fixture,
        )

        fixture = V2Fixture()
        fixture.sources["parameter_set_registry_sha256"] = generator.sha256(
            generator.PARAMETER_SET_REGISTRY
        )
        v2_registry, v2_contracts = (
            fixture.generator_result
            if hasattr(fixture, "generator_result")
            else (None, None)
        )
        if v2_registry is None:
            from tests.plant_runtime_adapter_v2 import (
                test_plant_runtime_adapter_v2 as v2_tests,
            )

            v2_registry, v2_contracts = (
                v2_tests.generator.build_from_inputs(**fixture.inputs())
            )
        contract = next(iter(v2_contracts.values()))
        entry = v2_registry["contracts"][0]
        v2_hashes = {
            contract["contract_id"]: entry["contract_sha256"]
        }
        v1_registry = copy.deepcopy(
            json.loads(
                generator.RUNTIME_ADAPTER_REGISTRY.read_text(
                    encoding="utf-8"
                )
            )
        )
        v1_registry["sources"][
            "parameter_set_registry_sha256"
        ] = generator.sha256(generator.PARAMETER_SET_REGISTRY)
        v1_registry["sources"][
            "parameter_set_registry_generation_sha256"
        ] = fixture.parameter_registry["registry_generation_sha256"]
        v1_registry["contracts"] = []

        with (
            mock.patch.object(
                generator,
                "load_parameter_set_registry",
                return_value=fixture.parameter_registry,
            ),
            mock.patch.object(
                generator,
                "load_parameter_sets",
                return_value=(
                    [fixture.parameter_set],
                    fixture.parameter_hashes,
                ),
            ),
            mock.patch.object(
                generator,
                "load_runtime_adapter_registry",
                return_value=(v1_registry, {}, {}),
            ),
            mock.patch.object(
                generator,
                "load_runtime_adapter_v2_registry",
                return_value=(v2_registry, v2_contracts, v2_hashes),
            ),
        ):
            joined = generator.build_registry()

        parameter_set = joined["parameter_sets"][0]
        self.assertTrue(parameter_set["runtime_loadable"])
        self.assertEqual(
            parameter_set["runtime_adapter_id"],
            "plant-adapter-deterministic-event-scheduled-v2",
        )
        self.assertEqual(
            parameter_set["runtime_contract_id"],
            contract["contract_id"],
        )
        backend = next(
            item
            for item in joined["backends"]
            if item["kind"] == "actuator_plant"
        )
        self.assertEqual(backend["backend_id"], contract["backend_id"])
        self.assertEqual(
            backend["runtime_contract_id"],
            contract["contract_id"],
        )
        runtime = SimulationBackendRegistry(joined)
        admitted = runtime.resolve(
            contract["backend_id"],
            BackendKind.ACTUATOR_PLANT,
            applicability=PlantApplicability(
                **fixture.parameter_set["applicability"]
            ),
        )
        self.assertTrue(admitted.allowed)
        self.assertFalse(admitted.parameter_set["support_granted"])

    def test_two_active_adapter_versions_for_one_plant_fail_closed(
        self,
    ) -> None:
        plant_id = "plant-collision"
        v1_registry = {
            "contracts": [
                {
                    "plant_id": plant_id,
                    "contract_id": "plantruntime-" + "1" * 20,
                }
            ],
            "sources": {
                "parameter_set_registry_sha256": "a" * 64,
                "parameter_set_registry_generation_sha256": "b" * 64,
            },
        }
        v2_registry = {
            "contracts": [
                {
                    "plant_id": plant_id,
                    "contract_id": "plantruntimev2-" + "2" * 20,
                }
            ],
            "sources": copy.deepcopy(v1_registry["sources"]),
        }
        parameter_registry = {
            "registry_generation_sha256": "b" * 64
        }
        with (
            mock.patch.object(
                generator,
                "load_parameter_set_registry",
                return_value=parameter_registry,
            ),
            mock.patch.object(
                generator,
                "load_parameter_sets",
                return_value=([], {}),
            ),
            mock.patch.object(
                generator,
                "sha256",
                return_value="a" * 64,
            ),
            mock.patch.object(
                generator,
                "load_runtime_adapter_registry",
                return_value=(
                    v1_registry,
                    {"plantruntime-" + "1" * 20: {}},
                    {"plantruntime-" + "1" * 20: "c" * 64},
                ),
            ),
            mock.patch.object(
                generator,
                "load_runtime_adapter_v2_registry",
                return_value=(
                    v2_registry,
                    {"plantruntimev2-" + "2" * 20: {}},
                    {"plantruntimev2-" + "2" * 20: "d" * 64},
                ),
            ),
            self.assertRaisesRegex(
                generator.PlantRegistryError,
                "multiple active runtime adapter versions",
            ),
        ):
            generator.build_registry()


if __name__ == "__main__":
    unittest.main()
