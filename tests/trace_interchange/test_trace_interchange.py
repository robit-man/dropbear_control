from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from myactuator_lib import (
    actuator_plant,
    plant_runtime_adapter_v2,
    simulation_runtime,
)
from myactuator_lib.simulation_runtime import (
    SimulationRuntimeCatalog,
    SimulationSelection,
    SimulationUseCase,
)
from myactuator_lib.simulation_session import (
    ResetRequest,
    SimulationCommand,
    SimulationCommandMode,
    SimulationSession,
    SourcedPlantV2Engine,
    SyntheticPlantEngine,
)
from myactuator_lib.trace_interchange import (
    TraceInterchangeError,
    build_trace,
    build_session_trace,
    canonical_json,
    chain_events,
    compare_inputs_and_dispositions,
    load_trace,
    validate_trace,
    write_trace,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "schemas/simulation-trace-interchange.schema.json").read_text()
)
PARAMETERS = ROOT / "tests/plant_core/synthetic_parameter_set.json"
EXPORTER_SHA256 = hashlib.sha256(
    (ROOT / "host/myactuator_lib/trace_interchange.py").read_bytes()
).hexdigest()
SOURCED_V2_TRACE_SHA256 = (
    "1257214ab285ce52c8022f1d5dc98edcf5dec40c232987f594dea333f7c979b9"
)


class TraceInterchangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Draft202012Validator.check_schema(SCHEMA)
        cls.catalog = SimulationRuntimeCatalog.load()
        cls.model = cls.catalog._value["models"][0]
        cls.parameters = actuator_plant.SyntheticParameterSet.load(PARAMETERS)
        from tests.plant_runtime_adapter_v2 import (
            test_plant_runtime_adapter_v2 as adapter_v2_tests,
        )

        fixture = adapter_v2_tests.Fixture()
        _, contracts = adapter_v2_tests.generator.build_from_inputs(
            **fixture.inputs()
        )
        cls.v2_executable = plant_runtime_adapter_v2.load_contract(
            next(iter(contracts.values()))
        )
        v2_value = copy.deepcopy(cls.catalog._value)
        v2_value["backends"].append(
            {
                "backend_id": cls.v2_executable.backend_id,
                "kind": "actuator_plant",
                "evidence_class": "sil-plant-sourced",
                "substitution_scope": "single-actuator-mechanics",
                "runtime_loadable": True,
                "command_capable": True,
                "deterministic_virtual_time": True,
                "models_protocol_state": False,
                "models_actuator_dynamics": True,
                "models_rigid_body": False,
                "exact_model_applicability_verified": True,
                "physically_validated": False,
                "physical_io": False,
                "parameter_set_id": cls.v2_executable.plant_id,
                "runtime_contract_id": cls.v2_executable.contract_id,
                "allowed_use_cases": ["exact_model_plant_sil"],
                "blockers": [],
            }
        )
        first = v2_value["models"][0]
        first["plant"].update(
            status="sourced",
            plant_ids=[cls.v2_executable.plant_id],
        )
        first["fidelity"].update(
            exact_model_geometry_ready=True,
            exact_model_plant_ready=True,
            exact_model_simulation_ready=True,
        )
        first["admitted_exact_model_backend_ids"] = [
            cls.v2_executable.backend_id
        ]
        v2_value["summary"].update(
            backend_descriptor_count=6,
            runtime_loadable_backend_count=5,
            exact_model_geometry_ready_count=1,
            exact_model_plant_ready_count=1,
            exact_model_simulation_ready_count=1,
        )
        v2_value["integrity"]["record_sha256"] = simulation_runtime._digest(
            v2_value
        )
        cls.v2_catalog = SimulationRuntimeCatalog(
            v2_value,
            json.loads(
                simulation_runtime.DEFAULT_SCHEMA.read_text(encoding="utf-8")
            ),
        )

    def run_session(self, *, target: float = 0.75) -> SimulationSession:
        selection = SimulationSelection(
            self.catalog.generation_sha256,
            self.model["model_key"],
            self.model["series"],
            self.model["model"],
            self.model["configuration_ids"][0],
            "synthetic-electromechanical-fixed-step-v1",
            "synthetic_actuator_plant",
            SimulationUseCase.SYNTHETIC_PLANT_SIL,
            False,
            False,
            False,
        )
        session = SimulationSession(
            catalog=self.catalog,
            selection=selection,
            engine=SyntheticPlantEngine(self.parameters),
        )
        session.configure(ResetRequest(17))
        session.activate()
        session.submit(
            SimulationCommand(
                self.catalog.generation_sha256,
                session.reset_generation,
                1,
                "sim-actuator-1",
                0,
                10,
                SimulationCommandMode.QAXIS_CURRENT,
                target,
                "A",
                2.0,
            )
        )
        session.advance(5)
        session.read()
        session.deactivate()
        return session

    def export(self, *, target: float = 0.75) -> dict:
        return build_session_trace(
            self.run_session(target=target),
            fixture_id="synthetic-actuator-trace-fixture",
            tick_period_ns=1_000_000,
            producer_source_sha256=EXPORTER_SHA256,
        )

    def export_v2(self) -> dict:
        model = self.v2_catalog._value["models"][0]
        selection = SimulationSelection(
            self.v2_catalog.generation_sha256,
            model["model_key"],
            model["series"],
            model["model"],
            model["configuration_ids"][0],
            self.v2_executable.backend_id,
            "actuator_plant",
            SimulationUseCase.EXACT_MODEL_PLANT_SIL,
            True,
            False,
            False,
        )
        session = SimulationSession(
            catalog=self.v2_catalog,
            selection=selection,
            engine=SourcedPlantV2Engine(self.v2_executable),
        )
        session.configure(ResetRequest(9182))
        session.activate()
        session.submit(
            SimulationCommand(
                self.v2_catalog.generation_sha256,
                session.reset_generation,
                1,
                "sim-actuator-1",
                0,
                12,
                SimulationCommandMode.QAXIS_CURRENT,
                1.0,
                "A",
                2.0,
            )
        )
        session.advance(8)
        session.read()
        session.deactivate()
        return build_session_trace(
            session,
            fixture_id="sourced-v2-actuator-trace-fixture",
            tick_period_ns=1_000_000,
            producer_source_sha256=EXPORTER_SHA256,
        )

    def test_session_export_is_schema_valid_canonical_and_deterministic(self) -> None:
        first = self.export()
        second = self.export()
        self.assertEqual(first, second)
        self.assertEqual(1, first["summary"]["command_count"])
        self.assertEqual(1, first["summary"]["state_count"])
        self.assertEqual(1, first["summary"]["accepted_command_count"])
        self.assertFalse(first["claims"]["canonical_dropbear"])
        self.assertFalse(first["claims"]["support_granted"])
        self.assertFalse(first["claims"]["exact_model_fidelity"])
        validate_trace(first)
        self.assertEqual(first, json.loads(canonical_json(first)))

    def test_round_trip_is_atomic_and_byte_stable(self) -> None:
        value = self.export()
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "trace.json"
            write_trace(path, value)
            self.assertEqual(canonical_json(value), path.read_bytes())
            self.assertEqual(value, load_trace(path))

    def test_sourced_v2_round_trip_binds_contract_and_provenance(self) -> None:
        first = self.export_v2()
        second = self.export_v2()
        self.assertEqual(first, second)
        self.assertEqual(
            SOURCED_V2_TRACE_SHA256,
            first["integrity"]["record_sha256"],
        )
        self.assertEqual(
            self.v2_executable.backend_id,
            first["backend"]["backend_id"],
        )
        self.assertEqual("actuator_plant", first["backend"]["backend_kind"])
        self.assertTrue(first["claims"]["exact_model_fidelity"])
        self.assertFalse(first["claims"]["physically_validated"])
        self.assertFalse(first["claims"]["support_granted"])
        self.assertFalse(first["claims"]["physical_motion_authority"])
        state = first["states"][0]
        self.assertIn(
            f"runtime-contract-v2:{self.v2_executable.contract_id}",
            state["provenance_refs"],
        )
        self.assertTrue(
            set(self.v2_executable.provenance_refs).issubset(
                state["provenance_refs"]
            )
        )
        self.assertTrue(
            any(
                reference.startswith("capture:")
                for reference in state["provenance_refs"]
            )
        )
        validate_trace(first)
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "sourced-v2-trace.json"
            write_trace(path, first)
            self.assertEqual(canonical_json(first), path.read_bytes())
            self.assertEqual(first, load_trace(path))

    def test_event_projection_and_nested_hash_mutations_deny(self) -> None:
        baseline = self.export()
        mutations = [
            lambda value: value["events"][1].__setitem__("sequence", 99),
            lambda value: value["events"][2].__setitem__(
                "previous_sha256", "0" * 64
            ),
            lambda value: value["events"][-2]["payload"]["state"][
                "engine_state"
            ].__setitem__("position_rad", 123.0),
            lambda value: value["commands"][0].__setitem__("target_si", 1.25),
            lambda value: value["states"][0].__setitem__("validity", "missing"),
            lambda value: value["summary"].__setitem__("event_count", 999),
            lambda value: value["integrity"].__setitem__(
                "event_chain_sha256", "f" * 64
            ),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                value = copy.deepcopy(baseline)
                mutation(value)
                with self.assertRaises(TraceInterchangeError):
                    validate_trace(value)

    def test_schema_and_semantics_deny_authority_promotions(self) -> None:
        baseline = self.export()
        mutations = [
            lambda value: value["claims"].__setitem__(
                "canonical_dropbear", True
            ),
            lambda value: value["claims"].__setitem__(
                "support_granted", True
            ),
            lambda value: value["claims"].__setitem__(
                "physical_motion_authority", True
            ),
            lambda value: value["backend"].__setitem__(
                "exact_model_fidelity", True
            ),
            lambda value: value["backend"].__setitem__("physical_io", True),
            lambda value: value["subject"].__setitem__(
                "kind", "generic_rigid_body_fixture"
            ),
        ]
        for mutation in mutations:
            value = copy.deepcopy(baseline)
            mutation(value)
            with self.assertRaises(TraceInterchangeError):
                validate_trace(value)

    def test_cross_backend_contract_compares_inputs_and_dispositions_only(self) -> None:
        first = self.export()
        second = copy.deepcopy(first)
        state_event = next(
            event for event in second["events"] if event["kind"] == "state-read"
        )
        state_event["payload"]["state"]["engine_state"]["position_rad"] += 1e-9
        previous = "0" * 64
        for event in second["events"]:
            event["previous_sha256"] = previous
            body = {key: item for key, item in event.items() if key != "record_sha256"}
            event["record_sha256"] = hashlib.sha256(canonical_json(body)).hexdigest()
            previous = event["record_sha256"]
        second = self._rebuild_integrity(second)
        compare_inputs_and_dispositions(first, second)

        different_input = self.export(target=0.5)
        with self.assertRaises(TraceInterchangeError):
            compare_inputs_and_dispositions(first, different_input)

    def test_future_canonical_scene_requires_exact_backend_and_all_generations(self) -> None:
        events = chain_events(
            [
                (
                    0,
                    "configured",
                    {
                        "fixture_id": "accepted-scene-fixture",
                        "seed": 0,
                    },
                )
            ]
        )
        subject = {
            "kind": "canonical_dropbear_scene",
            "subject_id": "subject-dropbear-revision-one",
            "fixture_id": "accepted-scene-fixture",
            "model_key": None,
            "series": None,
            "model": None,
            "configuration_id": None,
            "evidence_class": "accepted-exact-scene",
            "graph_submission_id": "submission-reviewed-graph-one",
            "cad_registry_sha256": "a" * 64,
            "plant_registry_sha256": "b" * 64,
        }
        backend = {
            "backend_id": "accepted-rigid-body-backend",
            "backend_kind": "rigid_body",
            "engine_name": "Synthetic accepted-transition fixture",
            "engine_version": "1",
            "engine_binary_sha256": "c" * 64,
            "use_case": "whole_robot_rigid_body",
            "deterministic_virtual_time": True,
            "command_capable": True,
            "exact_model_fidelity": True,
            "physically_validated": False,
            "physical_io": False,
        }
        generations = {
            "catalog_sha256": "d" * 64,
            "source_registry_sha256": "e" * 64,
            "graph_registry_sha256": "f" * 64,
        }
        value = build_trace(
            producer={
                "name": "accepted-transition-test",
                "version": "1",
                "source_sha256": "9" * 64,
            },
            subject=subject,
            backend=backend,
            source_generations=generations,
            tick_period_ns=1_000_000,
            seed=0,
            reset_generation=1,
            initial_state_sha256="8" * 64,
            events=events,
        )
        self.assertTrue(value["claims"]["canonical_dropbear"])
        self.assertTrue(value["claims"]["exact_model_fidelity"])
        self.assertFalse(value["claims"]["support_granted"])

        missing_generation = copy.deepcopy(generations)
        missing_generation["graph_registry_sha256"] = None
        with self.assertRaises(TraceInterchangeError):
            build_trace(
                producer=value["producer"],
                subject=subject,
                backend=backend,
                source_generations=missing_generation,
                tick_period_ns=1_000_000,
                seed=0,
                reset_generation=1,
                initial_state_sha256="8" * 64,
                events=events,
            )

    @staticmethod
    def _rebuild_integrity(value: dict) -> dict:
        return build_trace(
            producer=value["producer"],
            subject=value["subject"],
            backend=value["backend"],
            source_generations=value["source_generations"],
            tick_period_ns=value["clock"]["tick_period_ns"],
            seed=value["reset"]["seed"],
            reset_generation=value["reset"]["reset_generation"],
            initial_state_sha256=value["reset"]["initial_state_sha256"],
            events=value["events"],
        )


if __name__ == "__main__":
    unittest.main()
