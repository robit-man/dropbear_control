from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from myactuator_lib.dropbear_graph import (
    DropbearGraphAdmissionError,
    DropbearGraphProjectionSet,
)


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/generate_dropbear_graph_projections.py"
SCHEMA_PATH = ROOT / "schemas/dropbear-graph-projection.schema.json"
OUTPUT_ROOT = ROOT / "generated/dropbear_graph_projection"
STATUS_PATH = ROOT / "generated/dropbear_graph_review/status.json"
INVENTORY_PATH = ROOT / "generated/dropbear_description/inventory.json"

spec = importlib.util.spec_from_file_location(
    "dropbear_graph_projection_test_module", TOOL
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class DropbearGraphProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text())
        cls.projections = {
            kind: json.loads((OUTPUT_ROOT / f"{kind}.json").read_text())
            for kind in manager.VIEW_KINDS
        }
        cls.status_bytes = STATUS_PATH.read_bytes()
        cls.status = json.loads(cls.status_bytes)
        cls.inventory_bytes = INVENTORY_PATH.read_bytes()
        cls.inventory = json.loads(cls.inventory_bytes)
        decision_id = cls.projections["host"]["subject"]["graph_decision_id"]
        cls.template_path = (
            ROOT
            / "generated/dropbear_graph_review/templates"
            / f"{decision_id}.json"
        )
        cls.template_bytes = cls.template_path.read_bytes()
        cls.template = json.loads(cls.template_bytes)

    def consumer(self, projections=None):
        return DropbearGraphProjectionSet(
            projections or copy.deepcopy(self.projections),
            self.schema,
            self.status,
            self.status_bytes,
            self.inventory,
            self.inventory_bytes,
            self.template,
            self.template_bytes,
        )

    def test_four_generated_views_are_exact_and_have_common_denial_state(self):
        values = manager.build()
        self.assertEqual(set(manager.VIEW_KINDS), set(values))
        common = values["host"]
        for kind in manager.VIEW_KINDS:
            self.assertEqual(
                manager.canonical_bytes(values[kind]),
                (OUTPUT_ROOT / f"{kind}.json").read_bytes(),
            )
            self.assertEqual(common["subject"], values[kind]["subject"])
            self.assertEqual(common["summary"], values[kind]["summary"])
            self.assertEqual(common["blockers"], values[kind]["blockers"])
            self.assertFalse(values[kind]["support_granted"])
            self.assertFalse(values[kind]["physical_motion_authority"])

    def test_each_view_materializes_only_zero_status_outputs(self):
        expected = {
            "host": {
                "transform_count": 0,
                "actuator_mapping_count": 0,
                "command_handle_count": 0,
            },
            "ros": {
                "urdf_fragment_count": 0,
                "transmission_count": 0,
                "ros2_control_hardware_mapping_count": 0,
            },
            "simulator": {
                "authoritative_graph_count": 0,
                "physical_plant_count": 0,
                "actuator_mapping_count": 0,
            },
            "ui": {
                "exposed_local_path_count": 0,
                "downloadable_runtime_description_count": 0,
                "actuator_mapping_count": 0,
            },
        }
        for kind, fields in expected.items():
            self.assertTrue(self.projections[kind]["outputs"]["status_only"])
            for field, value in fields.items():
                self.assertEqual(value, self.projections[kind]["outputs"][field])

    def test_ui_projection_contains_no_path_or_runtime_description_payload(self):
        ui = self.projections["ui"]
        serialized = json.dumps(ui)
        self.assertNotIn("/home/", serialized)
        self.assertNotIn("generated/", serialized)
        self.assertNotIn(".urdf", serialized)
        self.assertNotIn(".xacro", serialized)
        self.assertNotIn("selected_files", serialized)
        self.assertEqual(0, ui["outputs"]["exposed_local_path_count"])

    def test_host_consumer_exposes_exact_denials_and_no_graph_objects(self):
        consumer = self.consumer()
        for kind in manager.VIEW_KINDS:
            view = consumer.view(kind)
            self.assertEqual(kind, view.view_kind)
            self.assertEqual(161, view.question_count)
            self.assertEqual(161, view.unanswered_question_count)
            self.assertEqual(0, view.canonical_graph_count)
            self.assertEqual(0, view.actuator_mapping_count)
            self.assertFalse(view.canonical_graph_admissible)
            self.assertFalse(view.support_granted)
            self.assertFalse(view.physical_motion_authority)
            self.assertTrue(view.blockers)
        with self.assertRaises(DropbearGraphAdmissionError):
            consumer.require_canonical_graph()

    def test_host_consumer_has_no_alias_prefix_case_or_family_fallback(self):
        consumer = self.consumer()
        for kind in ("HOST", "sim", "simulation", "ros2", "browser", ""):
            with self.assertRaises(DropbearGraphAdmissionError):
                consumer.view(kind)

    def test_missing_duplicate_or_mislabeled_view_denies(self):
        missing = copy.deepcopy(self.projections)
        missing.pop("ui")
        with self.assertRaises(DropbearGraphAdmissionError):
            self.consumer(missing)
        extra = copy.deepcopy(self.projections)
        extra["browser"] = copy.deepcopy(extra["ui"])
        with self.assertRaises(DropbearGraphAdmissionError):
            self.consumer(extra)
        mislabeled = copy.deepcopy(self.projections)
        mislabeled["ui"]["view_kind"] = "host"
        with self.assertRaises(DropbearGraphAdmissionError):
            self.consumer(mislabeled)

    def test_cross_view_subject_summary_or_blocker_disagreement_denies(self):
        mutations = [
            lambda values: values["ui"]["subject"].__setitem__(
                "inventory_sha256", "0" * 64
            ),
            lambda values: values["ros"]["summary"].__setitem__(
                "question_count", 160
            ),
            lambda values: values["simulator"]["blockers"].append(
                "invented-blocker"
            ),
        ]
        for mutation in mutations:
            values = copy.deepcopy(self.projections)
            mutation(values)
            with self.assertRaises(DropbearGraphAdmissionError):
                self.consumer(values)

    def test_status_inventory_and_template_hash_or_identity_drift_denies(self):
        with self.assertRaises(DropbearGraphAdmissionError):
            DropbearGraphProjectionSet(
                self.projections,
                self.schema,
                self.status,
                self.status_bytes + b" ",
                self.inventory,
                self.inventory_bytes,
                self.template,
                self.template_bytes,
            )
        wrong_inventory = copy.deepcopy(self.inventory)
        wrong_inventory["reconciliation"]["canonical_configuration_digest"] = (
            "0" * 64
        )
        with self.assertRaises(DropbearGraphAdmissionError):
            DropbearGraphProjectionSet(
                self.projections,
                self.schema,
                self.status,
                self.status_bytes,
                wrong_inventory,
                manager.canonical_bytes(wrong_inventory),
                self.template,
                self.template_bytes,
            )
        wrong_template = copy.deepcopy(self.template)
        wrong_template["record_state"] = "submitted"
        with self.assertRaises(DropbearGraphAdmissionError):
            DropbearGraphProjectionSet(
                self.projections,
                self.schema,
                self.status,
                self.status_bytes,
                self.inventory,
                self.inventory_bytes,
                wrong_template,
                self.template_bytes,
            )

    def test_schema_rejects_output_or_authority_promotions(self):
        validator = Draft202012Validator(self.schema)
        mutations = [
            lambda value: value["summary"].__setitem__(
                "canonical_graph_count", 1
            ),
            lambda value: value["summary"].__setitem__(
                "canonical_graph_admissible", True
            ),
            lambda value: value["outputs"].__setitem__(
                next(
                    key
                    for key in value["outputs"]
                    if key.endswith("_count")
                ),
                1,
            ),
            lambda value: value.__setitem__("support_granted", True),
            lambda value: value.__setitem__(
                "physical_motion_authority", True
            ),
        ]
        for kind in manager.VIEW_KINDS:
            for mutation in mutations:
                value = copy.deepcopy(self.projections[kind])
                mutation(value)
                self.assertTrue(
                    list(validator.iter_errors(value)), (kind, mutation)
                )

    def test_generator_owns_exclusive_output_namespace(self):
        original = manager.OUTPUT_ROOT
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                manager.OUTPUT_ROOT = root
                self.assertEqual(set(), manager.unexpected_paths())
                (root / "foreign.txt").write_text("not generator-owned")
                self.assertEqual({root / "foreign.txt"}, manager.unexpected_paths())
                with self.assertRaises(manager.GraphProjectionError):
                    manager.generate()
        finally:
            manager.OUTPUT_ROOT = original

    def test_cli_check_is_read_only_and_canonical(self):
        before = {
            kind: (OUTPUT_ROOT / f"{kind}.json").read_bytes()
            for kind in manager.VIEW_KINDS
        }
        result = subprocess.run(
            ["python3", str(TOOL), "--check"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertIn("views=4 questions=161 canonical=0 mappings=0", result.stdout)
        for kind, content in before.items():
            self.assertEqual(content, (OUTPUT_ROOT / f"{kind}.json").read_bytes())
            self.assertEqual(
                content,
                manager.canonical_bytes(json.loads(content)),
            )


if __name__ == "__main__":
    unittest.main()
