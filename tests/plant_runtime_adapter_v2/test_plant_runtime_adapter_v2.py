from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load_module(
    "plant_runtime_adapter_v2_generator_under_test",
    ROOT / "tools/generate_plant_runtime_adapters_v2.py",
)
assembly_tests = load_module(
    "plant_parameter_set_fixture_for_runtime_adapter_v2",
    ROOT / "tests/plant_parameter_sets/test_plant_parameter_sets.py",
)
adapter = generator.adapter

from myactuator_lib import actuator_plant_v2 as plant


class Fixture:
    def __init__(self) -> None:
        source = assembly_tests.Fixture()
        registry, sets = assembly_tests.generator.build_from_inputs(
            **source.inputs()
        )
        assert len(sets) == 1
        self.parameter_registry = registry
        self.parameter_sets = sets
        self.plant_id = next(iter(sets))
        self.parameter_set = sets[self.plant_id]
        self.parameter_hashes: dict[str, str] = {}
        self.profile: dict = {}
        self.profiles: dict[str, dict] = {}
        self.profile_hashes: dict[str, str] = {}
        self.sources = {
            "catalog_sha256": "1" * 64,
            "parameter_set_registry_sha256": "2" * 64,
            "adapter_implementation_sha256": "3" * 64,
            "plant_implementation_sha256": "4" * 64,
            "profile_schema_sha256": "5" * 64,
        }
        self.catalog = generator.load_catalog()
        self.refresh_parameter_binding(create=True)

    def refresh_parameter_binding(self, *, create: bool = False) -> None:
        parameter_hash = generator.sha_bytes(
            generator.canonical_json(self.parameter_set).encode("utf-8")
        )
        self.parameter_hashes = {self.plant_id: parameter_hash}
        subject = {
            "plant_id": self.plant_id,
            "parameter_set_sha256": parameter_hash,
            "assembly_registry_generation_sha256": self.parameter_set[
                "assembly"
            ]["assembly_registry_generation_sha256"],
            "adapter_id": adapter.ADAPTER_ID,
            "applicability": copy.deepcopy(
                self.parameter_set["applicability"]
            ),
        }
        if create:
            self.profile = {
                "schema_version": adapter.PROFILE_VERSION,
                "profile_id": "",
                "record_state": "submitted",
                "subject": subject,
                "execution": {
                    "torque_regime": "peak_one_shot_per_reset",
                    "jitter_application": "command_and_feedback",
                    "supply_voltage_v": 48.0,
                    "ambient_temperature_k": 298.15,
                    "rotation_direction": "bidirectional",
                    "position_lower_rad": -3.141592653589793,
                    "position_upper_rad": 3.141592653589793,
                    "output_load_torque_bound_nm": 12.0,
                    "transmission_damping_nm_s_per_rad": 1.0,
                    "current_controller_kp_v_per_a": 2.0,
                    "winding_derate_start_temperature_k": 370.0,
                    "case_derate_start_temperature_k": 360.0,
                },
                "review": {
                    "status": "accepted",
                    "prepared_by": {
                        "actor_id": "human-simulation-engineer",
                        "actor_type": "human",
                        "role": "simulation_engineer",
                    },
                    "reviewed_by": {
                        "actor_id": "human-controls-reviewer",
                        "actor_type": "human",
                        "role": "controls_safety_reviewer",
                    },
                    "reviewed_at_utc": "2026-07-23T12:00:00Z",
                    "rationale": (
                        "Synthetic fixture proves V2 adapter mechanics only."
                    ),
                },
                "authority": {
                    "support_granted": False,
                    "physical_motion_authority": False,
                    "physical_validation_claimed": False,
                },
                "integrity": {"record_sha256": "0" * 64},
            }
        else:
            self.profile["subject"] = subject
        self.refresh_profile()

    def refresh_profile(self) -> None:
        profile_id = generator.profile_id_for(self.profile["subject"])
        self.profile["profile_id"] = profile_id
        generator.set_digest(self.profile)
        self.profiles = {profile_id: self.profile}
        self.profile_hashes = {
            profile_id: generator.sha_bytes(
                generator.canonical_json(self.profile).encode("utf-8")
            )
        }

    def set_parameter(
        self,
        group: str,
        name: str,
        value: float,
    ) -> None:
        self.parameter_set["parameters"][group][name]["value"] = value
        self.refresh_parameter_binding()

    def inputs(self) -> dict:
        return {
            "catalog": self.catalog,
            "parameter_registry": self.parameter_registry,
            "parameter_sets": self.parameter_sets,
            "parameter_hashes": self.parameter_hashes,
            "profiles": self.profiles,
            "profile_hashes": self.profile_hashes,
            "sources": self.sources,
        }


class PlantRuntimeAdapterV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tracked = json.loads(
            generator.OUTPUT_REGISTRY.read_text(encoding="utf-8")
        )

    def test_tracked_baseline_is_schema_valid_complete_and_denial_only(
        self,
    ) -> None:
        schema = json.loads(
            generator.REGISTRY_SCHEMA.read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(self.tracked)
        registry, contracts = generator.build()
        self.assertFalse(contracts)
        self.assertEqual(44, registry["summary"]["model_count"])
        self.assertEqual(
            0,
            registry["summary"]["runtime_loadable_parameter_set_count"],
        )
        self.assertFalse(registry["support_granted"])
        self.assertFalse(registry["physical_motion_authority"])
        self.assertTrue(
            all(item["blockers"] for item in registry["model_coverage"])
        )

    def test_full_v2_source_semantics_materialize_exact_typed_contract(
        self,
    ) -> None:
        fixture = Fixture()
        profile_schema = json.loads(
            generator.PROFILE_SCHEMA.read_text(encoding="utf-8")
        )
        Draft202012Validator(profile_schema).validate(fixture.profile)
        registry, contracts = generator.build_from_inputs(**fixture.inputs())
        generator.validate(
            registry,
            contracts,
            parameter_sets=fixture.parameter_sets,
            parameter_hashes=fixture.parameter_hashes,
            profiles=fixture.profiles,
            profile_hashes=fixture.profile_hashes,
            catalog=fixture.catalog,
            verify_sources=False,
        )
        self.assertEqual(1, registry["summary"]["runtime_contract_count"])
        contract = next(iter(contracts.values()))
        executable = adapter.load_contract(contract)
        parameters = executable.configuration.parameters
        semantics = executable.configuration.semantics
        self.assertEqual(38, len(contract["source_semantics"]))
        self.assertTrue(
            all(
                item["disposition"] != "excluded"
                for item in contract["source_semantics"]
            )
        )
        self.assertEqual(
            len(adapter.EXECUTION_FIELDS),
            len(contract["execution_choices"]),
        )
        self.assertEqual(parameters.state_sample_period_s, 0.002)
        self.assertEqual(parameters.command_delay_s, 0.001)
        self.assertEqual(parameters.delay_jitter_s, 0.0001)
        self.assertEqual(parameters.forward_efficiency_ratio, 0.9)
        self.assertEqual(parameters.reverse_efficiency_ratio, 0.85)
        self.assertEqual(parameters.maximum_output_speed_rad_s, 8.0)
        self.assertEqual(parameters.output_load_torque_bound_nm, 12.0)
        self.assertEqual(
            semantics.torque_regime,
            "peak_one_shot_per_reset",
        )
        self.assertEqual(
            semantics.jitter_application,
            "command_and_feedback",
        )
        self.assertFalse(contract["validation"]["physically_validated"])
        self.assertFalse(contract["support_granted"])

        engine = plant.DeterministicActuatorPlantV2(
            executable.configuration,
            seed=19,
        )
        engine.submit(plant.PlantV2Command(1, 0, True, 1.0))
        for _ in range(5):
            result = engine.step(output_load_torque_nm=0.2)
        self.assertTrue(result.diagnostics.finite)
        self.assertGreaterEqual(
            result.diagnostics.active_command_sequence,
            1,
        )

    def test_v2_admits_semantics_that_v1_deliberately_rejects(self) -> None:
        fixture = Fixture()
        _, contracts = generator.build_from_inputs(**fixture.inputs())
        executable = adapter.load_contract(next(iter(contracts.values())))
        p = executable.configuration.parameters
        self.assertNotEqual(
            p.forward_efficiency_ratio,
            p.reverse_efficiency_ratio,
        )
        self.assertGreater(p.position_noise_stddev_rad, 0.0)
        self.assertGreater(p.command_delay_s, 0.0)
        self.assertNotEqual(
            p.state_sample_period_s,
            p.current_loop_period_s,
        )
        self.assertGreater(p.delay_jitter_s, 0.0)

    def test_source_rate_envelope_thermal_and_torque_choices_fail_closed(
        self,
    ) -> None:
        cases: list[Fixture] = []

        rate = Fixture()
        rate.set_parameter(
            "latency",
            "state_sample_period_s",
            0.0005,
        )
        cases.append(rate)

        supply = Fixture()
        supply.profile["execution"]["supply_voltage_v"] = 60.0
        supply.refresh_profile()
        cases.append(supply)

        thermal = Fixture()
        thermal.profile["execution"][
            "case_derate_start_temperature_k"
        ] = 400.0
        thermal.refresh_profile()
        cases.append(thermal)

        load = Fixture()
        load.profile["execution"]["output_load_torque_bound_nm"] = 16.0
        load.refresh_profile()
        cases.append(load)

        continuous = Fixture()
        continuous.profile["execution"]["torque_regime"] = "continuous_only"
        continuous.profile["execution"][
            "output_load_torque_bound_nm"
        ] = 12.0
        continuous.refresh_profile()
        cases.append(continuous)

        for index, fixture in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(
                generator.PlantRuntimeAdapterV2RegistryError
            ):
                generator.build_from_inputs(**fixture.inputs())

    def test_profile_review_subject_authority_and_closure_fail_closed(
        self,
    ) -> None:
        cases: list[Fixture] = []
        same_actor = Fixture()
        same_actor.profile["review"]["reviewed_by"] = copy.deepcopy(
            same_actor.profile["review"]["prepared_by"]
        )
        same_actor.refresh_profile()
        cases.append(same_actor)

        authority = Fixture()
        authority.profile["authority"]["support_granted"] = True
        authority.refresh_profile()
        cases.append(authority)

        applicability = Fixture()
        applicability.profile["subject"]["applicability"][
            "model"
        ] = "wrong-model"
        applicability.refresh_profile()
        cases.append(applicability)

        extra = Fixture()
        extra.profile["execution"]["family_default"] = 1
        extra.refresh_profile()
        cases.append(extra)

        for index, fixture in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(
                generator.PlantRuntimeAdapterV2RegistryError
            ):
                generator.build_from_inputs(**fixture.inputs())

    def test_contract_hash_configuration_semantics_and_authority_are_bound(
        self,
    ) -> None:
        fixture = Fixture()
        _, contracts = generator.build_from_inputs(**fixture.inputs())
        contract = next(iter(contracts.values()))
        mutations: list[dict] = []

        digest = copy.deepcopy(contract)
        digest["integrity"]["record_sha256"] = "0" * 64
        mutations.append(digest)

        parameter = copy.deepcopy(contract)
        parameter["engine_configuration"]["parameters"][
            "phase_resistance_ohm"
        ] = -1.0
        adapter.set_digest(parameter)
        mutations.append(parameter)

        semantics = copy.deepcopy(contract)
        semantics["source_semantics"].pop()
        adapter.set_digest(semantics)
        mutations.append(semantics)

        execution = copy.deepcopy(contract)
        execution["execution"]["rotation_direction"] = "positive"
        adapter.set_digest(execution)
        mutations.append(execution)

        authority = copy.deepcopy(contract)
        authority["physical_motion_authority"] = True
        adapter.set_digest(authority)
        mutations.append(authority)

        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                adapter.PlantRuntimeAdapterV2Error
            ):
                adapter.load_contract(value)

    def test_profile_and_parameter_content_hashes_are_verified(self) -> None:
        fixture = Fixture()
        profile_id = next(iter(fixture.profiles))
        arguments = {
            "parameter_set_sha256": fixture.parameter_hashes[
                fixture.plant_id
            ],
            "profile_sha256": fixture.profile_hashes[profile_id],
            "adapter_implementation_sha256": "3" * 64,
            "plant_implementation_sha256": "4" * 64,
            "profile_schema_sha256": "5" * 64,
        }
        altered_profile = copy.deepcopy(fixture.profile)
        altered_profile["review"]["rationale"] = "changed"
        with self.assertRaisesRegex(
            adapter.PlantRuntimeAdapterV2Error,
            "digest",
        ):
            adapter.adapt(
                fixture.parameter_set,
                altered_profile,
                **arguments,
            )
        altered_source = copy.deepcopy(fixture.parameter_set)
        altered_source["parameters"]["sensor"][
            "position_noise_stddev_rad"
        ]["value"] = 0.5
        with self.assertRaisesRegex(
            adapter.PlantRuntimeAdapterV2Error,
            "digest/content",
        ):
            adapter.adapt(
                altered_source,
                fixture.profile,
                **arguments,
            )

    def test_duplicate_profile_for_one_plant_is_forbidden(self) -> None:
        fixture = Fixture()
        duplicate = copy.deepcopy(fixture.profile)
        duplicate["execution"]["supply_voltage_v"] = 47.0
        adapter.set_digest(duplicate)
        duplicate_hash = generator.sha_bytes(
            generator.canonical_json(duplicate).encode("utf-8")
        )
        duplicate_key = next(iter(fixture.profiles)) + "-duplicate"
        fixture.profiles[duplicate_key] = duplicate
        fixture.profile_hashes[duplicate_key] = duplicate_hash
        with self.assertRaises(
            generator.PlantRuntimeAdapterV2RegistryError
        ):
            generator.build_from_inputs(**fixture.inputs())


if __name__ == "__main__":
    unittest.main()
