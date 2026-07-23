from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from myactuator_lib import simulation_runtime
from myactuator_lib.simulation_runtime import (
    SimulationAdmissionReason,
    SimulationRuntimeCatalog,
    SimulationRuntimeError,
    SimulationSelection,
    SimulationUseCase,
)


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/generate_simulator_runtime_catalog.py"
OUTPUT = ROOT / "generated/myactuator/simulator/runtime_catalog.json"
WEB_OUTPUT = ROOT / "web/assets/simulator_runtime_catalog.generated.json"
SCHEMA = ROOT / "schemas/myactuator-simulator-runtime-catalog.schema.json"

spec = importlib.util.spec_from_file_location(
    "simulator_runtime_catalog_test_module", TOOL
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class SimulatorRuntimeCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = json.loads(OUTPUT.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        cls.catalog = SimulationRuntimeCatalog.load()

    def selection(
        self,
        *,
        backend_id: str,
        backend_kind: str,
        use_case: SimulationUseCase,
        exact: bool = False,
        physical: bool = False,
        whole_robot: bool = False,
    ) -> SimulationSelection:
        model = self.value["models"][0]
        return SimulationSelection(
            catalog_generation_sha256=self.catalog.generation_sha256,
            model_key=model["model_key"],
            series=model["series"],
            model=model["model"],
            configuration_id=model["configuration_ids"][0],
            backend_id=backend_id,
            backend_kind=backend_kind,
            use_case=use_case,
            require_exact_model_fidelity=exact,
            require_physical_validation=physical,
            require_dropbear_whole_robot=whole_robot,
        )

    def test_tracked_catalog_is_exact_complete_and_denial_only(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.value)
        manager.validate(copy.deepcopy(self.value))
        self.assertEqual(44, self.catalog.model_count)
        self.assertEqual(5, self.catalog.backend_count)
        summary = self.value["summary"]
        self.assertEqual(53, summary["source_variant_count"])
        self.assertEqual(53, summary["geometry_configuration_count"])
        self.assertEqual(0, summary["exact_model_geometry_ready_count"])
        self.assertEqual(0, summary["exact_model_plant_ready_count"])
        self.assertEqual(0, summary["exact_model_simulation_ready_count"])
        self.assertEqual(0, summary["physically_correlated_plant_count"])
        self.assertEqual(0, summary["browser_articulated_asset_ready_count"])
        self.assertEqual(0, summary["dropbear_whole_robot_ready_count"])
        self.assertFalse(self.value["support_granted"])
        self.assertFalse(self.value["physical_motion_authority"])
        self.assertFalse(self.value["physical_io_enabled"])

    def test_all_models_losslessly_partition_53_configurations_and_variants(self) -> None:
        configurations = [
            identifier
            for model in self.value["models"]
            for identifier in model["configuration_ids"]
        ]
        variants = [
            identifier
            for model in self.value["models"]
            for identifier in model["source_variant_ids"]
        ]
        self.assertEqual(53, len(configurations))
        self.assertEqual(53, len(set(configurations)))
        self.assertEqual(53, len(variants))
        self.assertEqual(53, len(set(variants)))
        self.assertTrue(
            all(
                model["source_step_evidence_present"]
                and not model["source_step_runtime_asset"]
                and not model[
                    "protocol_model_firmware_applicability_verified"
                ]
                for model in self.value["models"]
            )
        )

    def test_backend_profiles_keep_five_evidence_classes_distinct(self) -> None:
        backends = {
            value["backend_id"]: value for value in self.value["backends"]
        }
        replay = backends["canonical-recorded-state-replay-v1"]
        protocol = backends["rmd-v44-protocol-emulator"]
        toy = backends["browser-toy-demo-v1"]
        synthetic = backends["synthetic-electromechanical-fixed-step-v1"]
        rigid = backends["dropbear-rigid-body-unavailable-v1"]
        self.assertFalse(replay["command_capable"])
        self.assertEqual(["recorded_replay"], replay["allowed_use_cases"])
        self.assertTrue(protocol["models_protocol_state"])
        self.assertFalse(protocol["models_actuator_dynamics"])
        self.assertFalse(toy["deterministic_virtual_time"])
        self.assertTrue(synthetic["models_actuator_dynamics"])
        self.assertFalse(synthetic["exact_model_applicability_verified"])
        self.assertFalse(rigid["runtime_loadable"])
        self.assertEqual([], rigid["allowed_use_cases"])
        self.assertTrue(all(not value["physical_io"] for value in backends.values()))

    def test_explicit_synthetic_protocol_toy_and_replay_use_cases_admit(self) -> None:
        cases = (
            (
                "canonical-recorded-state-replay-v1",
                "recorded_replay",
                SimulationUseCase.RECORDED_REPLAY,
                False,
            ),
            (
                "rmd-v44-protocol-emulator",
                "protocol_emulator",
                SimulationUseCase.PROTOCOL_STATE_SIL,
                True,
            ),
            (
                "browser-toy-demo-v1",
                "toy_demo",
                SimulationUseCase.CATALOG_DEMO,
                True,
            ),
            (
                "synthetic-electromechanical-fixed-step-v1",
                "synthetic_actuator_plant",
                SimulationUseCase.SYNTHETIC_PLANT_SIL,
                True,
            ),
        )
        for backend_id, kind, use_case, command_capable in cases:
            with self.subTest(backend_id=backend_id):
                decision = self.catalog.admit(
                    self.selection(
                        backend_id=backend_id,
                        backend_kind=kind,
                        use_case=use_case,
                    )
                )
                self.assertTrue(decision.allowed)
                self.assertEqual(
                    SimulationAdmissionReason.ALLOWED, decision.reason
                )
                self.assertEqual(command_capable, decision.command_capable)
                self.assertFalse(decision.exact_model_fidelity)
                self.assertFalse(decision.physically_validated)
                self.assertFalse(decision.physical_io)

    def test_exact_model_whole_robot_and_rigid_body_fidelity_deny(self) -> None:
        exact = self.catalog.admit(
            self.selection(
                backend_id="synthetic-electromechanical-fixed-step-v1",
                backend_kind="synthetic_actuator_plant",
                use_case=SimulationUseCase.SYNTHETIC_PLANT_SIL,
                exact=True,
            )
        )
        self.assertEqual(
            SimulationAdmissionReason.EXACT_MODEL_FIDELITY_UNAVAILABLE,
            exact.reason,
        )
        rigid = self.catalog.admit(
            self.selection(
                backend_id="dropbear-rigid-body-unavailable-v1",
                backend_kind="rigid_body",
                use_case=SimulationUseCase.WHOLE_ROBOT_RIGID_BODY,
                whole_robot=True,
            )
        )
        self.assertEqual(
            SimulationAdmissionReason.BACKEND_NOT_LOADABLE, rigid.reason
        )
        self.assertFalse(self.catalog.dropbear_whole_robot_ready)

    def test_exact_lookup_has_no_family_alias_default_or_cross_config_fallback(self) -> None:
        first = self.value["models"][0]
        self.assertEqual(
            first,
            self.catalog.model(
                first["model_key"],
                series=first["series"],
                model=first["model"],
            ),
        )
        with self.assertRaises(SimulationRuntimeError):
            self.catalog.model(
                first["model_key"], series="RMD-X", model="X"
            )
        with self.assertRaises(SimulationRuntimeError):
            self.catalog.model(
                "model-" + "0" * 20,
                series=first["series"],
                model=first["model"],
            )
        wrong_configuration = self.value["models"][1]["configuration_ids"][0]
        changed = copy.deepcopy(
            self.selection(
                backend_id="browser-toy-demo-v1",
                backend_kind="toy_demo",
                use_case=SimulationUseCase.CATALOG_DEMO,
            )
        )
        object.__setattr__(changed, "configuration_id", wrong_configuration)
        decision = self.catalog.admit(changed)
        self.assertEqual(
            SimulationAdmissionReason.CONFIGURATION_NOT_FOUND,
            decision.reason,
        )

    def test_stale_generation_backend_kind_and_use_case_deny_distinctly(self) -> None:
        base = self.selection(
            backend_id="rmd-v44-protocol-emulator",
            backend_kind="protocol_emulator",
            use_case=SimulationUseCase.PROTOCOL_STATE_SIL,
        )
        stale = copy.deepcopy(base)
        object.__setattr__(stale, "catalog_generation_sha256", "0" * 64)
        self.assertEqual(
            SimulationAdmissionReason.STALE_CATALOG_GENERATION,
            self.catalog.admit(stale).reason,
        )
        kind = copy.deepcopy(base)
        object.__setattr__(kind, "backend_kind", "toy_demo")
        self.assertEqual(
            SimulationAdmissionReason.BACKEND_KIND_MISMATCH,
            self.catalog.admit(kind).reason,
        )
        use_case = copy.deepcopy(base)
        object.__setattr__(
            use_case, "use_case", SimulationUseCase.SYNTHETIC_PLANT_SIL
        )
        self.assertEqual(
            SimulationAdmissionReason.USE_CASE_NOT_SUPPORTED,
            self.catalog.admit(use_case).reason,
        )

    def test_browser_projection_is_byte_equal_and_contains_no_path_or_url(self) -> None:
        self.assertEqual(OUTPUT.read_bytes(), WEB_OUTPUT.read_bytes())
        text = WEB_OUTPUT.read_text(encoding="utf-8").casefold()
        for forbidden in (
            "/home/",
            "file://",
            "www.myactuator.com",
            "archive_url",
            "relative_path",
            "evidence_path",
        ):
            self.assertNotIn(forbidden, text)

    def test_digest_counts_claims_and_semantic_promotions_deny(self) -> None:
        mutations = []
        digest = copy.deepcopy(self.value)
        digest["integrity"]["record_sha256"] = "0" * 64
        mutations.append(digest)
        count = copy.deepcopy(self.value)
        count["summary"]["exact_model_geometry_ready_count"] = 1
        manager.set_digest(count)
        mutations.append(count)
        step = copy.deepcopy(self.value)
        step["models"][0]["source_step_runtime_asset"] = True
        manager.set_digest(step)
        mutations.append(step)
        simulation = copy.deepcopy(self.value)
        simulation["models"][0]["fidelity"][
            "exact_model_simulation_ready"
        ] = True
        manager.set_digest(simulation)
        mutations.append(simulation)
        authority = copy.deepcopy(self.value)
        authority["support_granted"] = True
        manager.set_digest(authority)
        mutations.append(authority)
        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                (manager.SimulatorCatalogError, SimulationRuntimeError)
            ):
                manager.validate(value, verify_sources=False)

    def test_source_tamper_and_failed_generation_preserve_outputs(self) -> None:
        before = OUTPUT.read_bytes()
        before_web = WEB_OUTPUT.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_files = {}
            for source_id, source in simulation_runtime.DEFAULT_SOURCE_FILES.items():
                destination = root / source.name
                destination.write_bytes(source.read_bytes())
                source_files[source_id] = destination
            source_files["catalog_sha256"].write_bytes(b"tampered\n")
            with self.assertRaises(SimulationRuntimeError):
                SimulationRuntimeCatalog(
                    copy.deepcopy(self.value),
                    copy.deepcopy(self.schema),
                    source_files=source_files,
                )
        broken = copy.deepcopy(self.value)
        broken["models"].pop()
        manager.set_digest(broken)
        with self.assertRaises(manager.SimulatorCatalogError):
            manager.validate(broken, verify_sources=False)
        self.assertEqual(before, OUTPUT.read_bytes())
        self.assertEqual(before_web, WEB_OUTPUT.read_bytes())


if __name__ == "__main__":
    unittest.main()
