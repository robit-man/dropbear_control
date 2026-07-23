from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/generate_coverage_dashboard.py"
OUTPUT = ROOT / "generated/myactuator/coverage_dashboard/dashboard.json"
HTML = ROOT / "generated/myactuator/coverage_dashboard/index.html"
SCHEMA = ROOT / "schemas/myactuator-coverage-dashboard.schema.json"

spec = importlib.util.spec_from_file_location(
    "coverage_dashboard_generator_test_module",
    TOOL,
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class CoverageDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = json.loads(OUTPUT.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_schema_digest_sources_and_exact_partitions(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.value)
        manager.validate(copy.deepcopy(self.value))
        self.assertEqual(24, len(self.value["sources"]))
        self.assertEqual(
            {
                "requirement_count": 77,
                "p0_requirement_count": 39,
                "p1_requirement_count": 37,
                "p2_requirement_count": 1,
                "catalog_test_count": 140,
                "test_exists_offline_count": 105,
                "test_exists_baseline_count": 0,
                "test_planned_count": 28,
                "test_physical_hold_count": 7,
                "work_package_count": 20,
                "phase_gate_count": 8,
                "model_count": 44,
                "cad_configuration_count": 53,
            },
            {
                key: self.value["summary"][key]
                for key in (
                    "requirement_count",
                    "p0_requirement_count",
                    "p1_requirement_count",
                    "p2_requirement_count",
                    "catalog_test_count",
                    "test_exists_offline_count",
                    "test_exists_baseline_count",
                    "test_planned_count",
                    "test_physical_hold_count",
                    "work_package_count",
                    "phase_gate_count",
                    "model_count",
                    "cad_configuration_count",
                )
            },
        )

    def test_trace_coverage_never_becomes_completion_or_gate_pass(self) -> None:
        requirements = self.value["requirements"]
        self.assertEqual(
            77,
            self.value["summary"]["structurally_traced_requirement_count"],
        )
        self.assertEqual(
            0,
            self.value["summary"]["completion_asserted_requirement_count"],
        )
        self.assertTrue(
            all(
                item["structurally_traced"]
                and not item["completion_asserted"]
                and item["planned_test_ids"]
                and item["work_package_ids"]
                and item["gate_ids"]
                for item in requirements
            )
        )
        self.assertTrue(
            all(not item["pass_asserted"] for item in self.value["phase_gates"])
        )
        aggregate = Counter()
        for item in self.value["tests"]:
            aggregate[item["status"]] += 1
        self.assertEqual(
            {
                "EXISTS-OFFLINE": 105,
                "PHYSICAL-HOLD": 7,
                "PLANNED": 28,
            },
            dict(aggregate),
        )

    def test_objective_criteria_expose_exact_met_and_blocked_frontier(self) -> None:
        criteria = {
            item["criterion_id"]: item
            for item in self.value["objective_criteria"]
        }
        self.assertEqual(
            {
                "requirements_trace_coverage",
                "vendor_models_catalogued",
                "step_configurations_acquired",
            },
            {identifier for identifier, item in criteria.items() if item["met"]},
        )
        self.assertEqual(15, len(criteria))
        self.assertEqual(
            3,
            self.value["summary"]["objective_criterion_met_count"],
        )
        self.assertFalse(self.value["summary"]["objective_evidence_complete"])
        exact_zeros = {
            "protocol_models_accepted": (0, 44),
            "cad_configurations_accepted": (0, 53),
            "plant_models_source_complete": (0, 44),
            "exact_model_simulation_ready": (0, 44),
            "dropbear_source_authority_active": (0, 1),
            "dropbear_canonical_graph_active": (0, 1),
            "dropbear_motion_ready_actuators": (0, 12),
            "reviewer_roles_assigned": (0, 17),
            "installed_motors_observed": (0, 12),
            "runtime_can_adapter_selected": (0, 1),
            "physical_evidence_tests_completed": (0, 7),
        }
        self.assertEqual(
            exact_zeros,
            {
                identifier: (
                    criteria[identifier]["observed_count"],
                    criteria[identifier]["required_count"],
                )
                for identifier in exact_zeros
            },
        )
        self.assertFalse(self.value["release_authorized"])
        self.assertFalse(self.value["support_granted"])
        self.assertFalse(self.value["physical_motion_authority"])
        self.assertFalse(self.value["physical_action_permitted"])

    def test_all_models_and_cad_configurations_remain_exact_and_unpromoted(
        self,
    ) -> None:
        models = self.value["models"]
        configurations = self.value["cad_configurations"]
        self.assertEqual(44, len({item["model_key"] for item in models}))
        self.assertEqual(
            53,
            len({item["configuration_id"] for item in configurations}),
        )
        self.assertEqual(
            {item["configuration_id"] for item in configurations},
            {
                configuration_id
                for model in models
                for configuration_id in model["configuration_ids"]
            },
        )
        self.assertTrue(
            all(
                not model["protocol_applicability_accepted"]
                and not model["exact_model_geometry_ready"]
                and not model["exact_model_plant_ready"]
                and not model["exact_model_simulation_ready"]
                and not model["physically_correlated_plant_ready"]
                for model in models
            )
        )
        self.assertEqual(
            689,
            sum(item["unanswered_question_count"] for item in configurations),
        )
        self.assertTrue(
            all(
                not item["accepted_asset"]
                and not item["browser_releasable"]
                and not item["support_granted"]
                for item in configurations
            )
        )

    def test_digest_source_projection_and_authority_mutations_fail(self) -> None:
        mutations = []
        digest = copy.deepcopy(self.value)
        digest["integrity"]["record_sha256"] = "0" * 64
        mutations.append(digest)
        source = copy.deepcopy(self.value)
        source["sources"][0]["sha256"] = "0" * 64
        manager.set_digest(source)
        mutations.append(source)
        projection = copy.deepcopy(self.value)
        projection["tests"][0]["status"] = "PLANNED"
        manager.set_digest(projection)
        mutations.append(projection)
        completion = copy.deepcopy(self.value)
        completion["requirements"][0]["completion_asserted"] = True
        manager.set_digest(completion)
        mutations.append(completion)
        authority = copy.deepcopy(self.value)
        authority["release_authorized"] = True
        manager.set_digest(authority)
        mutations.append(authority)
        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                manager.CoverageDashboardError
            ):
                manager.validate(value)

    def test_malformed_trace_or_source_digest_fails_before_output_change(
        self,
    ) -> None:
        before_json = OUTPUT.read_bytes()
        before_html = HTML.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            bad_trace = temporary_path / "trace.md"
            trace_text = manager.TRACEABILITY.read_text(encoding="utf-8")
            bad_trace.write_text(
                trace_text.replace(
                    "| SYS-001 |",
                    "| SYS-999 |",
                    1,
                ),
                encoding="utf-8",
            )
            original_trace = manager.TRACEABILITY
            try:
                manager.TRACEABILITY = bad_trace
                with self.assertRaises(manager.CoverageDashboardError):
                    manager.build()
            finally:
                manager.TRACEABILITY = original_trace

            bad_simulator = temporary_path / "runtime_catalog.json"
            simulator = json.loads(
                manager.SIMULATOR.read_text(encoding="utf-8")
            )
            simulator["summary"]["model_count"] = 43
            bad_simulator.write_text(
                json.dumps(simulator, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            original_simulator = manager.SIMULATOR
            try:
                manager.SIMULATOR = bad_simulator
                with self.assertRaises(manager.CoverageDashboardError):
                    manager.build()
            finally:
                manager.SIMULATOR = original_simulator

            bad_v2_adapter = temporary_path / "runtime_adapters_v2.json"
            v2_adapter = json.loads(
                manager.PLANT_RUNTIME_ADAPTERS_V2.read_text(
                    encoding="utf-8"
                )
            )
            v2_adapter["summary"]["runtime_contract_count"] = 1
            manager.set_digest(v2_adapter)
            bad_v2_adapter.write_text(
                json.dumps(v2_adapter, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            original_v2_adapter = manager.PLANT_RUNTIME_ADAPTERS_V2
            try:
                manager.PLANT_RUNTIME_ADAPTERS_V2 = bad_v2_adapter
                with self.assertRaises(manager.CoverageDashboardError):
                    manager.build()
            finally:
                manager.PLANT_RUNTIME_ADAPTERS_V2 = original_v2_adapter
        self.assertEqual(before_json, OUTPUT.read_bytes())
        self.assertEqual(before_html, HTML.read_bytes())

    def test_output_file_set_and_html_are_exact_and_network_free(self) -> None:
        manager.check_outputs(manager.expected_files(manager.build()))
        html_text = HTML.read_text(encoding="utf-8")
        self.assertNotIn("http://", html_text)
        self.assertNotIn("https://", html_text)
        self.assertNotIn("<script", html_text.lower())
        self.assertIn("Observation only.", html_text)
        self.assertIn("28</strong><br>tests planned", html_text)
        self.assertIn("7</strong><br>physical test holds", html_text)
        self.assertIn("0</strong><br>exact models simulation-ready", html_text)


if __name__ == "__main__":
    unittest.main()
