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
TOOL = ROOT / "tools/generate_evidence_review_queue.py"
OUTPUT = ROOT / "generated/myactuator/evidence_review/queue.json"
HTML = ROOT / "generated/myactuator/evidence_review/index.html"
SCHEMA = ROOT / "schemas/myactuator-evidence-review-queue.schema.json"

spec = importlib.util.spec_from_file_location(
    "evidence_review_queue_generator_test_module", TOOL
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class EvidenceReviewQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = json.loads(OUTPUT.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_schema_digest_sources_and_complete_domain_partition(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.value)
        manager.validate(copy.deepcopy(self.value))
        self.assertEqual(145, len(self.value["items"]))
        self.assertEqual(
            {
                "cad_articulation": 53,
                "can_adapter": 1,
                "dropbear_graph_authority": 1,
                "dropbear_source_authority": 1,
                "installed_inventory": 1,
                "plant_evidence": 44,
                "protocol_applicability": 44,
            },
            dict(Counter(item["domain"] for item in self.value["items"])),
        )
        self.assertEqual(9, len(self.value["sources"]))

    def test_current_queue_states_are_explicit_and_zero_authority(self) -> None:
        self.assertEqual(
            {
                "authorization_needed": 1,
                "dependency_blocked": 2,
                "exact_tuple_evidence_needed": 34,
                "ready_for_extraction": 44,
                "ready_for_review": 41,
                "reviewer_assignment_needed": 1,
                "source_acquisition_needed": 10,
                "source_or_partition_needed": 12,
            },
            self.value["summary"]["state_counts"],
        )
        self.assertEqual(0, self.value["summary"]["accepted_item_count"])
        self.assertEqual(0, self.value["summary"]["assigned_item_count"])
        self.assertEqual(
            0,
            self.value["summary"]["physical_action_permitted_count"],
        )
        self.assertTrue(
            all(
                not item["support_granted"]
                and not item["physical_motion_authority"]
                and not item["physical_action_permitted"]
                for item in self.value["items"]
            )
        )

    def test_protocol_cad_and_plant_work_is_actionable_not_collapsed(self) -> None:
        protocols = [
            item
            for item in self.value["items"]
            if item["domain"] == "protocol_applicability"
        ]
        self.assertEqual(
            {34: 1, 10: 1},
            {
                sum(
                    item["state"] == "exact_tuple_evidence_needed"
                    for item in protocols
                ): 1,
                sum(
                    item["state"] == "source_acquisition_needed"
                    for item in protocols
                ): 1,
            },
        )
        cad = [
            item
            for item in self.value["items"]
            if item["domain"] == "cad_articulation"
        ]
        self.assertEqual(
            689,
            sum(item["metrics"]["unanswered_question_count"] for item in cad),
        )
        plants = [
            item
            for item in self.value["items"]
            if item["domain"] == "plant_evidence"
        ]
        self.assertEqual(
            1496,
            sum(item["metrics"]["missing_parameter_count"] for item in plants),
        )
        self.assertEqual(
            176,
            sum(
                item["metrics"]["missing_operating_envelope_count"]
                for item in plants
            ),
        )

    def test_dependency_edges_preserve_source_graph_and_inventory_adapter_order(
        self,
    ) -> None:
        streams = {
            item["domain"]: item for item in self.value["workstreams"]
        }
        self.assertEqual(
            [streams["dropbear_source_authority"]["workstream_id"]],
            streams["dropbear_graph_authority"][
                "dependency_workstream_ids"
            ],
        )
        self.assertEqual(
            [streams["installed_inventory"]["workstream_id"]],
            streams["can_adapter"]["dependency_workstream_ids"],
        )
        self.assertEqual(
            [streams["installed_inventory"]["workstream_id"]],
            streams["protocol_applicability"][
                "dependency_workstream_ids"
            ],
        )

    def test_submitted_assignments_require_complete_independent_humans(
        self,
    ) -> None:
        assignment_path = ROOT / "assets/myactuator/reviewer_assignments.json"
        value = json.loads(assignment_path.read_text(encoding="utf-8"))
        value["record_state"] = "submitted"
        for index, row in enumerate(value["assignments"]):
            row["assignee_id"] = f"human-reviewer-{index:02d}"
            row["organization_or_team"] = f"qualified-team-{index:02d}"
            row["competence_evidence_refs"] = [
                f"evidence/competence-{index:02d}.json"
            ]
            row["acknowledged"] = True
            row["due_at_utc"] = "2026-08-15T00:00:00Z"
        value["summary"] = {
            "role_count": 17,
            "assigned_role_count": 17,
            "acknowledged_role_count": 17,
            "assignment_complete": True,
        }
        manager.set_digest(value)
        manager.validate_assignments(copy.deepcopy(value))
        conflict = copy.deepcopy(value)
        by_role = {
            row["role_id"]: row for row in conflict["assignments"]
        }
        by_role["protocol_decision_reviewer"]["assignee_id"] = by_role[
            "protocol_evidence_submitter"
        ]["assignee_id"]
        manager.set_digest(conflict)
        with self.assertRaises(manager.EvidenceReviewQueueError):
            manager.validate_assignments(conflict)

    def test_digest_source_item_and_authority_mutations_fail(self) -> None:
        mutations = []
        digest = copy.deepcopy(self.value)
        digest["integrity"]["record_sha256"] = "0" * 64
        mutations.append(digest)
        source = copy.deepcopy(self.value)
        source["sources"][0]["sha256"] = "0" * 64
        manager.set_digest(source)
        mutations.append(source)
        item = copy.deepcopy(self.value)
        item["items"][0]["item_id"] = "reviewitem-" + "0" * 20
        manager.set_digest(item)
        mutations.append(item)
        authority = copy.deepcopy(self.value)
        authority["items"][0]["physical_action_permitted"] = True
        manager.set_digest(authority)
        mutations.append(authority)
        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                manager.EvidenceReviewQueueError
            ):
                manager.validate(value)

    def test_failed_generation_preserves_last_valid_outputs(self) -> None:
        before_json = OUTPUT.read_bytes()
        before_html = HTML.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            bad = Path(temporary) / "assignments.json"
            bad.write_text("{}\n", encoding="utf-8")
            sources = manager.SOURCES
            try:
                manager.SOURCES = (*sources[:-1], bad)
                with self.assertRaises(manager.EvidenceReviewQueueError):
                    manager.build()
            finally:
                manager.SOURCES = sources
        self.assertEqual(before_json, OUTPUT.read_bytes())
        self.assertEqual(before_html, HTML.read_bytes())


if __name__ == "__main__":
    unittest.main()
