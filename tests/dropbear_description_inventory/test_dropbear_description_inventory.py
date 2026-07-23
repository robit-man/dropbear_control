from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import unittest
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / "references/Dropbear"
ARTIFACT = ROOT / "generated/dropbear_description/inventory.json"
SCHEMA = ROOT / "schemas/dropbear-description-inventory.schema.json"
PIN = "13cf5ecaa39b8b89c794fe905dcea0490cfa7726"


def git(*args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


class DropbearDescriptionInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_baseline_inventory_counts_are_exact_and_unpromoted(self):
        summary = self.value["summary"]
        self.assertEqual(198, summary["file_count"])
        self.assertEqual(96, summary["unique_object_count"])
        self.assertEqual(0, summary["runtime_ros_actuator_mapping_count"])
        self.assertFalse(summary["authoritative_description_selected"])
        self.assertFalse(summary["motion_enable_allowed"])
        self.assertEqual([], self.value["runtime_ros_actuator_mappings"])
        self.assertEqual(
            summary["file_count"],
            summary["source_candidate_count"]
            + summary["expanded_generated_candidate_count"]
            + summary["build_derivative_count"]
            + summary["install_derivative_count"],
        )

    def test_every_file_is_a_pinned_git_object_with_matching_sha_and_size(self):
        self.assertEqual(PIN, self.value["repository"]["commit"])
        self.assertEqual(PIN, git("rev-parse", "HEAD").decode().strip())
        for record in self.value["files"]:
            raw = git("show", f"{PIN}:{record['path']}")
            self.assertEqual(record["size_bytes"], len(raw))
            self.assertEqual(record["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(
                record["git_object_id"],
                git("rev-parse", f"{PIN}:{record['path']}").decode().strip(),
            )

    def test_derivatives_are_distinct_from_candidate_authority(self):
        counts = Counter(record["classification"] for record in self.value["files"])
        self.assertGreater(counts["source_candidate"], 0)
        self.assertGreater(counts["expanded_generated_candidate"], 0)
        self.assertEqual(0, counts["build_derivative"])
        self.assertGreater(counts["install_derivative"], 0)
        for record in self.value["files"]:
            if record["classification"].endswith("_derivative"):
                self.assertEqual("derivative_no_authority", record["authority"])
            else:
                self.assertEqual("candidate_observation_only", record["authority"])

    def test_exact_duplicates_and_drift_are_both_explicit(self):
        self.assertGreater(len(self.value["exact_duplicate_groups"]), 0)
        divergent = [
            group for group in self.value["logical_groups"]
            if group["status"] == "divergent"
        ]
        self.assertGreater(len(divergent), 0)
        leg_groups = [
            group for group in divergent
            if group["logical_key"].endswith("leg.xacro")
        ]
        self.assertTrue(leg_groups)
        self.assertTrue(
            any(
                "simplified" in path and any("detailed" in other for other in group["paths"])
                for group in leg_groups
                for path in group["paths"]
            )
        )

    def test_graph_observations_cover_required_fields(self):
        observations = [record["observations"] for record in self.value["objects"]]
        self.assertTrue(any(item["links"] for item in observations))
        self.assertTrue(any(item["joints"] for item in observations))
        self.assertTrue(
            any(
                joint["parent"] and joint["child"] and joint["axis_xyz"]
                for item in observations
                for joint in item["joints"]
            )
        )
        self.assertTrue(any(item["mesh_references"] for item in observations))
        self.assertTrue(any(item["mimic_edges"] for item in observations))
        self.assertTrue(any(item["ros2_control_joint_names"] for item in observations))
        self.assertTrue(any(item["controller_joint_names"] for item in observations))

    def test_review_questions_cover_all_actuators_and_two_cardinality_gaps(self):
        questions = self.value["review_questions"]
        mappings = [item for item in questions if item["kind"] == "actuator_mapping"]
        cardinality = [
            item for item in questions
            if item["kind"] == "cardinality_and_coupling"
        ]
        self.assertEqual(12, len(mappings))
        self.assertEqual(2, len(cardinality))
        self.assertTrue(
            any(item["kind"] == "mimic_or_coupling" for item in questions)
        )
        self.assertTrue(
            any(
                item["kind"] == "gazebo_loop_closure_candidate"
                for item in questions
            )
        )
        for item in questions:
            self.assertFalse(item["resolved"])
            self.assertIsNone(item["runtime_mapping_id"])

    def test_reconciliation_hash_and_configuration_digest_are_bound(self):
        record = self.value["reconciliation"]
        path = ROOT / record["path"]
        self.assertEqual(record["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        reconciliation = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            reconciliation["generated_from"]["canonical_configuration_digest"],
            record["canonical_configuration_digest"],
        )

    def test_schema_rejects_automated_authority_mapping_or_motion(self):
        mutations = [
            lambda value: value.__setitem__("authority", "canonical"),
            lambda value: value["summary"].__setitem__(
                "authoritative_description_selected", True
            ),
            lambda value: value["summary"].__setitem__(
                "runtime_ros_actuator_mapping_count", 1
            ),
            lambda value: value["summary"].__setitem__("motion_enable_allowed", True),
            lambda value: value["runtime_ros_actuator_mappings"].append(
                {"actuator": "guessed", "joint": "guessed"}
            ),
            lambda value: value["review_questions"][0].__setitem__("resolved", True),
        ]
        validator = Draft202012Validator(self.schema)
        for mutation in mutations:
            value = copy.deepcopy(self.value)
            mutation(value)
            self.assertTrue(list(validator.iter_errors(value)))


if __name__ == "__main__":
    unittest.main()
