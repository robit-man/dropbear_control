from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
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
    "plant_runtime_adapter_generator_under_test",
    ROOT / "tools/generate_plant_runtime_adapters.py",
)
assembly_tests = load_module(
    "plant_parameter_set_fixture_for_runtime_adapter",
    ROOT / "tests/plant_parameter_sets/test_plant_parameter_sets.py",
)
adapter = generator.adapter
from myactuator_lib.simulation_runtime import (
    SimulationSelection,
    SimulationUseCase,
)
from myactuator_lib.simulation_session import (
    ResetRequest,
    SimulationCommand,
    SimulationCommandMode,
    SimulationSessionError,
    SourcedPlantEngine,
)


def set_fact(fixture, field_id: str, value: float) -> None:
    fact = fixture.facts[field_id]
    fact["observation"]["normalized_value"] = value
    fact["evidence"]["uncertainty"].update(
        lower=value,
        upper=value,
    )


class Fixture:
    def __init__(self) -> None:
        source = assembly_tests.Fixture()
        set_fact(
            source,
            "transmission.reverse_efficiency_ratio",
            assembly_tests.PARAMETER_VALUES[
                "transmission.forward_efficiency_ratio"
            ],
        )
        for field_id in (
            "sensor.position_noise_stddev_rad",
            "sensor.velocity_noise_stddev_rad_s",
            "sensor.current_noise_stddev_a",
            "latency.command_delay_s",
            "latency.delay_jitter_s",
        ):
            set_fact(source, field_id, 0.0)
        set_fact(source, "latency.state_sample_period_s", 0.001)
        registry, sets = source.generator_result = (
            assembly_tests.generator.build_from_inputs(**source.inputs())
        )
        assert len(sets) == 1
        self.parameter_registry = registry
        self.parameter_sets = sets
        self.plant_id = next(iter(sets))
        self.parameter_set = sets[self.plant_id]
        self.parameter_hashes = {
            self.plant_id: generator.sha_bytes(
                generator.canonical_json(self.parameter_set).encode("utf-8")
            )
        }
        subject = {
            "plant_id": self.plant_id,
            "parameter_set_sha256": self.parameter_hashes[self.plant_id],
            "assembly_registry_generation_sha256": self.parameter_set[
                "assembly"
            ]["assembly_registry_generation_sha256"],
            "adapter_id": adapter.ADAPTER_ID,
            "applicability": copy.deepcopy(
                self.parameter_set["applicability"]
            ),
        }
        self.profile = {
            "schema_version": "myactuator-plant-runtime-profile/1",
            "profile_id": generator.profile_id_for(subject),
            "record_state": "submitted",
            "subject": subject,
            "execution": {
                "torque_regime": "continuous_only",
                "supply_voltage_v": 48.0,
                "ambient_temperature_k": 298.15,
                "rotation_direction": "positive",
                "position_lower_rad": -3.141592653589793,
                "position_upper_rad": 3.141592653589793,
                "output_load_torque_bound_nm": 5.0,
                "transmission_damping_nm_s_per_rad": 1.0,
                "current_controller_kp_v_per_a": 2.0,
                "derate_start_temperature_k": 350.0,
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
                "rationale": "Synthetic fixture proves adapter mechanics only.",
            },
            "authority": {
                "support_granted": False,
                "physical_motion_authority": False,
                "physical_validation_claimed": False,
            },
            "integrity": {"record_sha256": "0" * 64},
        }
        generator.set_digest(self.profile)
        self.profiles = {self.profile["profile_id"]: self.profile}
        self.profile_hashes = {
            self.profile["profile_id"]: generator.sha_bytes(
                generator.canonical_json(self.profile).encode("utf-8")
            )
        }
        self.sources = {
            "catalog_sha256": "1" * 64,
            "parameter_set_registry_sha256": "2" * 64,
            "adapter_implementation_sha256": "3" * 64,
            "plant_implementation_sha256": "4" * 64,
            "profile_schema_sha256": "5" * 64,
        }
        self.catalog = generator.load_catalog()

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

    def refresh_profile(self) -> None:
        generator.set_digest(self.profile)
        self.profile_hashes[self.profile["profile_id"]] = (
            generator.sha_bytes(
                generator.canonical_json(self.profile).encode("utf-8")
            )
        )


class PlantRuntimeAdapterTests(unittest.TestCase):
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
        self.assertTrue(
            all(item["blockers"] for item in registry["model_coverage"])
        )

    def test_complete_synthetic_reviewed_profile_materializes_contract(
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
        self.assertEqual(38, len(contract["source_semantics"]))
        self.assertEqual(0.001, executable.parameters.time_step_s)
        self.assertEqual(2, executable.parameters.sensor_latency_steps)
        self.assertEqual(0.9, executable.parameters.gear_efficiency)
        self.assertEqual(2.0, executable.parameters.maximum_motor_torque_nm)
        self.assertFalse(contract["validation"]["physically_validated"])
        self.assertFalse(contract["support_granted"])
        self.assertFalse(contract["physical_motion_authority"])

    def test_noise_delay_rate_direction_and_latency_representability_deny(
        self,
    ) -> None:
        mutations = []
        for group, name, value in (
            ("sensor", "position_noise_stddev_rad", 0.01),
            ("latency", "command_delay_s", 0.001),
            ("latency", "delay_jitter_s", 0.0001),
            ("latency", "state_sample_period_s", 0.002),
            ("latency", "feedback_delay_s", 0.0015),
        ):
            fixture = Fixture()
            fixture.parameter_set["parameters"][group][name]["value"] = value
            mutations.append(fixture)
        direction = Fixture()
        direction.profile["execution"]["rotation_direction"] = "bidirectional"
        direction.refresh_profile()
        direction.parameter_set["parameters"]["transmission"][
            "reverse_efficiency_ratio"
        ]["value"] = 0.8
        mutations.append(direction)
        for index, fixture in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                generator.PlantRuntimeAdapterRegistryError
            ):
                generator.build_from_inputs(**fixture.inputs())

    def test_operating_scenario_and_thermal_choices_fail_closed(self) -> None:
        mutations = []
        for field, value in (
            ("supply_voltage_v", 60.0),
            ("ambient_temperature_k", 500.0),
            ("position_lower_rad", 1.0),
            ("output_load_torque_bound_nm", 100.0),
            ("derate_start_temperature_k", 500.0),
        ):
            fixture = Fixture()
            fixture.profile["execution"][field] = value
            fixture.refresh_profile()
            mutations.append(fixture)
        for index, fixture in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                generator.PlantRuntimeAdapterRegistryError
            ):
                generator.build_from_inputs(**fixture.inputs())

    def test_subject_applicability_hash_and_review_identity_deny(self) -> None:
        cases = []
        for mutator in (
            lambda value: value["subject"].__setitem__(
                "parameter_set_sha256", "0" * 64
            ),
            lambda value: value["subject"]["applicability"].__setitem__(
                "model", "wrong-model"
            ),
            lambda value: value["review"].__setitem__(
                "reviewed_by",
                copy.deepcopy(value["review"]["prepared_by"]),
            ),
            lambda value: value["authority"].__setitem__(
                "support_granted", True
            ),
        ):
            fixture = Fixture()
            mutator(fixture.profile)
            fixture.refresh_profile()
            cases.append(fixture)
        for index, fixture in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(
                generator.PlantRuntimeAdapterRegistryError
            ):
                generator.build_from_inputs(**fixture.inputs())

    def test_contract_digest_semantics_parameters_and_guards_are_bound(
        self,
    ) -> None:
        fixture = Fixture()
        registry, contracts = generator.build_from_inputs(**fixture.inputs())
        contract = next(iter(contracts.values()))
        mutations = []
        digest = copy.deepcopy(contract)
        digest["integrity"]["record_sha256"] = "0" * 64
        mutations.append(digest)
        semantics = copy.deepcopy(contract)
        semantics["source_semantics"].pop()
        adapter.set_digest(semantics)
        mutations.append(semantics)
        parameter = copy.deepcopy(contract)
        parameter["engine_parameters"]["phase_resistance_ohm"] = -1.0
        adapter.set_digest(parameter)
        mutations.append(parameter)
        guard = copy.deepcopy(contract)
        guard["runtime_guards"]["continuous_only"] = False
        adapter.set_digest(guard)
        mutations.append(guard)
        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                adapter.PlantRuntimeAdapterError
            ):
                adapter.load_contract(value)

    def test_typed_sourced_engine_enforces_contract_identity_and_direction(
        self,
    ) -> None:
        fixture = Fixture()
        _, contracts = generator.build_from_inputs(**fixture.inputs())
        executable = adapter.load_contract(next(iter(contracts.values())))
        engine = SourcedPlantEngine(executable)
        applicability = executable.applicability_tuple
        selection = SimulationSelection(
            "a" * 64,
            assembly_tests.generator.model_key(
                applicability[0], applicability[1]
            ),
            applicability[0],
            applicability[1],
            "cadcfg-" + "b" * 20,
            executable.backend_id,
            "actuator_plant",
            SimulationUseCase.EXACT_MODEL_PLANT_SIL,
            True,
            False,
            False,
        )
        engine.configure(selection)
        initial = engine.reset(ResetRequest(7))
        self.assertEqual(0, initial.sample_tick)
        command = SimulationCommand(
            "a" * 64,
            1,
            1,
            "sim-actuator-1",
            0,
            2,
            SimulationCommandMode.QAXIS_CURRENT,
            1.0,
            "A",
            executable.parameters.maximum_qaxis_current_a,
        )
        engine.submit(command)
        engine.advance_one_tick()
        state = engine.read_state()
        self.assertEqual(1, state.sample_tick)
        self.assertIn(
            f"runtime-contract:{executable.contract_id}",
            state.provenance_refs,
        )
        reverse = copy.deepcopy(command)
        object.__setattr__(reverse, "target_si", -1.0)
        with self.assertRaisesRegex(
            SimulationSessionError, "direction"
        ):
            engine.submit(reverse)
        snapshot = engine.snapshot()
        snapshot["contract_id"] = "plantruntime-" + "0" * 20
        with self.assertRaisesRegex(
            SimulationSessionError, "contract mismatch"
        ):
            engine.restore(snapshot)

    def test_profile_removal_revokes_contract_and_changes_registry_digest(
        self,
    ) -> None:
        fixture = Fixture()
        accepted, contracts = generator.build_from_inputs(**fixture.inputs())
        self.assertEqual(1, len(contracts))
        fixture.profiles.clear()
        fixture.profile_hashes.clear()
        revoked, contracts = generator.build_from_inputs(**fixture.inputs())
        self.assertFalse(contracts)
        self.assertNotEqual(
            accepted["integrity"]["record_sha256"],
            revoked["integrity"]["record_sha256"],
        )

    def test_duplicate_profile_for_one_source_set_is_rejected(self) -> None:
        fixture = Fixture()
        duplicate = copy.deepcopy(fixture.profile)
        duplicate["profile_id"] = (
            "plantprofile-" + "f" * 20
        )
        duplicate["subject"] = copy.deepcopy(duplicate["subject"])
        duplicate["subject"]["adapter_id"] = adapter.ADAPTER_ID
        fixture.profiles[duplicate["profile_id"]] = duplicate
        fixture.profile_hashes[duplicate["profile_id"]] = (
            generator.sha_bytes(
                generator.canonical_json(duplicate).encode("utf-8")
            )
        )
        with self.assertRaises(generator.PlantRuntimeAdapterRegistryError):
            generator.build_from_inputs(**fixture.inputs())

    def test_transactional_output_replaces_stale_files(self) -> None:
        fixture = Fixture()
        registry, contracts = generator.build_from_inputs(**fixture.inputs())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "runtime_adapters"
            root.mkdir()
            (root / "stale.txt").write_text("stale", encoding="utf-8")
            original = generator.OUTPUT_ROOT
            try:
                generator.OUTPUT_ROOT = root
                generator._transactional_write(registry, contracts)
            finally:
                generator.OUTPUT_ROOT = original
            self.assertFalse((root / "stale.txt").exists())
            self.assertEqual(
                set(contracts),
                {
                    path.stem
                    for path in (root / "contracts").glob("*.json")
                },
            )


if __name__ == "__main__":
    unittest.main()
