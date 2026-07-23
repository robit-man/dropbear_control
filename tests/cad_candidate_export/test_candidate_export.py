from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "validate_cad_candidate_reports", ROOT / "tools/validate_cad_candidate_reports.py"
)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)


class CadCandidateExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hypothesis_path = next((ROOT / "assets/myactuator/cad_hypotheses").glob("*.json"))
        cls.hypothesis = json.loads(cls.hypothesis_path.read_text())
        cls.report = json.loads(
            (
                ROOT
                / "generated/myactuator/cad/candidate_export_reports"
                / f"{cls.hypothesis['variant_id']}.json"
            ).read_text()
        )
        inspection = json.loads(
            (ROOT / "generated/myactuator/cad/step_inspection.json").read_text()
        )
        cls.source = next(
            item
            for item in inspection["variants"]
            if item["variant_id"] == cls.hypothesis["variant_id"]
        )

    def validate(self, report: dict) -> None:
        validator.validate_pair(
            self.hypothesis,
            self.hypothesis_path,
            report,
            self.source,
            check_local=False,
        )

    def test_baseline_candidate_is_real_articulated_but_unaccepted(self) -> None:
        self.validate(copy.deepcopy(self.report))
        self.assertFalse(self.report["semantic_review_complete"])
        self.assertFalse(self.report["accepted_asset"])
        self.assertFalse(self.report["support_granted"])

    def test_candidate_cannot_promote_support_or_drop_questions(self) -> None:
        promoted = copy.deepcopy(self.report)
        promoted["support_granted"] = True
        with self.assertRaises(validator.CandidateReportError):
            self.validate(promoted)
        incomplete = copy.deepcopy(self.report)
        incomplete["unresolved_questions"] = []
        with self.assertRaises(validator.CandidateReportError):
            self.validate(incomplete)

    def test_member_and_articulation_tamper_fail(self) -> None:
        members = copy.deepcopy(self.report)
        members["output_occurrences"].pop()
        with self.assertRaises(validator.CandidateReportError):
            self.validate(members)
        pose = copy.deepcopy(self.report)
        pose["articulation"]["poses"][0]["rigid_rotation_matches"] = False
        with self.assertRaises(validator.CandidateReportError):
            self.validate(pose)


if __name__ == "__main__":
    unittest.main()
