from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from myactuator_lib.trace_interchange import validate_trace


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/run_rigid_body_benchmark.py"
REPORT_SCHEMA = json.loads(
    (ROOT / "schemas/rigid-body-benchmark-report.schema.json").read_text()
)
LOCK_SCHEMA = json.loads(
    (ROOT / "schemas/rigid-body-engine-lock.schema.json").read_text()
)

spec = importlib.util.spec_from_file_location("rigid_body_benchmark_tool", TOOL)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class RigidBodyBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Draft202012Validator.check_schema(REPORT_SCHEMA)
        Draft202012Validator.check_schema(LOCK_SCHEMA)
        (
            cls.trace,
            cls.trace_bytes,
            cls.report,
            cls.report_bytes,
        ) = module.generate()

    def test_engine_lock_is_exact_and_denies_production_selection(self) -> None:
        lock = module.load_engine_lock()
        self.assertEqual("3.6.0", lock["executed_engine"]["version"])
        self.assertEqual(3, len(lock["candidates"]))
        self.assertEqual(
            1,
            sum(
                candidate["benchmark_status"]
                == "executed_generic_fixture"
                for candidate in lock["candidates"]
            ),
        )
        self.assertFalse(lock["claims"]["production_engine_selected"])
        self.assertFalse(lock["claims"]["canonical_dropbear"])

    def test_all_ten_cases_pass_with_generic_evidence_only(self) -> None:
        self.assertEqual("PASS", self.report["summary"]["result"])
        self.assertEqual(10, self.report["summary"]["passed_case_count"])
        self.assertGreaterEqual(
            self.report["cases"]["fixed_step_articulation"][
                "maximum_drive_joint_response_rad"
            ],
            0.1,
        )
        self.assertFalse(
            self.report["cases"]["unavailable_dropbear_descriptor"][
                "runtime_loadable"
            ]
        )
        self.assertEqual(
            0,
            self.report["cases"]["canonical_scene_admission"][
                "active_graph_count"
            ],
        )
        self.assertFalse(self.report["claims"]["production_engine_selected"])
        self.assertFalse(self.report["claims"]["exact_model_fidelity"])

    def test_trace_is_deterministic_typed_and_nonphysical(self) -> None:
        validate_trace(self.trace)
        self.assertTrue(self.trace["claims"]["generic_fixture_only"])
        self.assertEqual(9, self.trace["summary"]["command_count"])
        self.assertEqual(753, self.trace["summary"]["state_count"])
        self.assertEqual(
            {"generic-drive-joint", "generic-loop-joint-a", "generic-loop-joint-b"},
            {state["actuator_id"] for state in self.trace["states"]},
        )
        self.assertTrue(
            all(state["validity"] == "valid" for state in self.trace["states"])
        )
        self.assertFalse(self.trace["claims"]["canonical_dropbear"])
        self.assertFalse(self.trace["claims"]["support_granted"])

    def test_repeated_generation_is_byte_equal(self) -> None:
        trace, trace_bytes, report, report_bytes = module.generate()
        self.assertEqual(self.trace, trace)
        self.assertEqual(self.trace_bytes, trace_bytes)
        self.assertEqual(self.report, report)
        self.assertEqual(self.report_bytes, report_bytes)

    def test_report_mutation_and_authority_promotion_deny(self) -> None:
        mutations = [
            lambda value: value["cases"]["closed_chain"].__setitem__(
                "maximum_equality_residual_m", 1.0
            ),
            lambda value: value["summary"].__setitem__("passed_case_count", 9),
            lambda value: value["claims"].__setitem__(
                "production_engine_selected", True
            ),
            lambda value: value["dropbear"].__setitem__(
                "canonical_scene_executed", True
            ),
            lambda value: value["integrity"].__setitem__(
                "record_sha256", "0" * 64
            ),
        ]
        for mutation in mutations:
            value = copy.deepcopy(self.report)
            mutation(value)
            with self.assertRaises(module.RigidBodyBenchmarkError):
                module.validate_report(
                    value,
                    trace=self.trace,
                    trace_bytes=self.trace_bytes,
                )

    def test_lock_digest_or_binary_identity_mutation_denies(self) -> None:
        lock = module.load_engine_lock()
        mutations = [
            lambda value: value["executed_engine"].__setitem__(
                "version", "3.6.1"
            ),
            lambda value: value["executed_engine"]["binaries"][0].__setitem__(
                "sha256", "f" * 64
            ),
            lambda value: value["claims"].__setitem__(
                "production_engine_selected", True
            ),
        ]
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "lock.json"
            for mutation in mutations:
                value = copy.deepcopy(lock)
                mutation(value)
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(module.RigidBodyBenchmarkError):
                    module.load_engine_lock(path)


if __name__ == "__main__":
    unittest.main()
