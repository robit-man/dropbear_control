from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "manage_cad_review_decisions", ROOT / "tools/manage_cad_review_decisions.py"
)
manager = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(manager)


class CadReviewDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hypothesis_path = next((ROOT / "assets/myactuator/cad_hypotheses").glob("*.json"))
        cls.context = manager.context_for_hypothesis(cls.hypothesis_path)
        cls.draft = manager.build_template(cls.hypothesis_path)

    def validate(self, decision: dict) -> None:
        manager.validate_decision(decision, self.context)

    def accepted_fixture(self) -> dict:
        decision = copy.deepcopy(self.draft)
        decision["record_state"] = "submitted"
        decision["reviewer"] = {
            "reviewer_id": "independent-review-fixture",
            "independence_attested": True,
            "reviewed_at": "2026-07-22T20:00:00Z",
            "review_assertion": "Test fixture assertion; not a real project review.",
            "signature_evidence_refs": ["tests/cad_review_decision/synthetic-reviewer-fixture"],
        }
        decision["disposition"] = "accept_geometry"
        decision["semantic_review_complete"] = True
        for name in ("member_review", "unit_review", "frame_review", "joint_review"):
            decision[name]["status"] = "reviewed"
        decision["member_review"]["rationale"] = "Synthetic test-only membership rationale."
        decision["frame_review"]["rationale"] = "Synthetic test-only frame rationale."
        decision["joint_review"]["rationale"] = "Synthetic test-only joint rationale."
        for item in decision["question_responses"]:
            item["resolution"] = "resolved"
            item["response"] = "Synthetic test-only answer."
            item["evidence_refs"] = ["tests/cad_review_decision/synthetic-answer-fixture"]
        return decision

    def test_generated_draft_is_canonical_unanswered_and_support_false(self) -> None:
        self.validate(copy.deepcopy(self.draft))
        tracked = json.loads(
            (
                ROOT
                / "generated/myactuator/cad/review_decision_templates"
                / f"{self.draft['variant_id']}.json"
            ).read_text()
        )
        self.assertEqual(tracked, self.draft)
        self.assertFalse(tracked["semantic_review_complete"])
        self.assertFalse(tracked["support_granted"])

    def test_acceptance_fixture_requires_every_review_and_answer(self) -> None:
        self.validate(self.accepted_fixture())
        unanswered = self.accepted_fixture()
        unanswered["question_responses"][0]["resolution"] = "unanswered"
        unanswered["question_responses"][0]["response"] = None
        unanswered["question_responses"][0]["evidence_refs"] = []
        with self.assertRaises(manager.DecisionError):
            self.validate(unanswered)
        unreviewed = self.accepted_fixture()
        unreviewed["member_review"]["status"] = "candidate"
        with self.assertRaises(manager.DecisionError):
            self.validate(unreviewed)

    def test_automation_or_nonindependent_reviewer_cannot_sign(self) -> None:
        automated = self.accepted_fixture()
        automated["reviewer"]["reviewer_id"] = "codex-automated-reviewer"
        with self.assertRaises(manager.DecisionError):
            self.validate(automated)
        dependent = self.accepted_fixture()
        dependent["reviewer"]["independence_attested"] = False
        with self.assertRaises(manager.DecisionError):
            self.validate(dependent)

    def test_member_overlap_missing_occurrence_and_hash_drift_fail(self) -> None:
        overlap = self.accepted_fixture()
        overlap["member_review"]["housing_occurrences"].append(
            overlap["member_review"]["output_occurrences"][0]
        )
        with self.assertRaises(manager.DecisionError):
            self.validate(overlap)
        missing = self.accepted_fixture()
        missing["member_review"]["housing_occurrences"].pop()
        with self.assertRaises(manager.DecisionError):
            self.validate(missing)
        drift = self.accepted_fixture()
        drift["source_hashes"]["candidate_export_report_sha256"] = "0" * 64
        with self.assertRaises(manager.DecisionError):
            self.validate(drift)

    def test_nonrigid_or_wrong_axis_frame_fails(self) -> None:
        nonrigid = self.accepted_fixture()
        nonrigid["frame_review"]["source_to_canonical"][0] = 2.0
        with self.assertRaises(manager.DecisionError):
            self.validate(nonrigid)
        wrong_axis = self.accepted_fixture()
        wrong_axis["joint_review"]["axis_unit"] = [1.0, 0.0, 0.0]
        with self.assertRaises(manager.DecisionError):
            self.validate(wrong_axis)

    def test_nonaccept_submission_cannot_claim_complete_review(self) -> None:
        decision = self.accepted_fixture()
        decision["disposition"] = "needs_more_evidence"
        decision["semantic_review_complete"] = False
        self.validate(decision)
        decision["semantic_review_complete"] = True
        with self.assertRaises(manager.DecisionError):
            self.validate(decision)

    def test_decision_schema_forbids_support_and_unknown_fields(self) -> None:
        support = self.accepted_fixture()
        support["support_granted"] = True
        with self.assertRaises(manager.DecisionError):
            self.validate(support)
        extra = self.accepted_fixture()
        extra["automatic_accept"] = True
        with self.assertRaises(manager.DecisionError):
            self.validate(extra)


if __name__ == "__main__":
    unittest.main()
