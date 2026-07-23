from __future__ import annotations

import html
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CadReviewWorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = json.loads(
            next(
                (ROOT / "generated/myactuator/cad/review_decision_templates").glob(
                    "*.json"
                )
            ).read_text()
        )
        cls.directory = (
            ROOT
            / "generated/myactuator/cad/review_workbenches"
            / cls.template["variant_id"]
        )
        cls.page = (cls.directory / "index.html").read_text()
        cls.readme = (cls.directory / "README.md").read_text()

    def test_workbench_embeds_exact_template_members_and_questions(self) -> None:
        match = re.search(
            r'<script type="application/json" id="workbench-data">(.*?)</script>',
            self.page,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        data = json.loads(html.unescape(match.group(1)))
        self.assertEqual(data["template"], self.template)
        occurrences = {item["occurrence"] for item in data["members"]}
        expected = set(self.template["member_review"]["housing_occurrences"]) | set(
            self.template["member_review"]["output_occurrences"]
        )
        self.assertEqual(occurrences, expected)
        self.assertEqual(
            [item["question"] for item in data["template"]["question_responses"]],
            [item["question"] for item in self.template["question_responses"]],
        )

    def test_workbench_is_local_only_and_preserves_support_false(self) -> None:
        folded = self.page.casefold()
        self.assertNotIn("fetch(", folded)
        self.assertNotIn("xmlhttprequest", folded)
        self.assertNotIn("<form", folded)
        self.assertNotIn("http://", folded)
        self.assertNotIn("https://", folded)
        self.assertIn("d.support_granted = false", self.page)
        self.assertIn("has not been accepted or applied", self.page)

    def test_workbench_requires_reviewer_answers_rationales_and_validation(self) -> None:
        for token in (
            "independence attestation",
            "acceptance requires member, frame and joint rationales",
            "is not resolved with response/evidence",
            "manage_cad_review_decisions.py --validate",
        ):
            self.assertIn(token, self.page + self.readme)

    def test_all_local_evidence_paths_exist_in_current_workspace(self) -> None:
        for relative in (
            f"../../review_packets/{self.template['variant_id']}/overview.png",
            f"../../review_packets/{self.template['variant_id']}/member-sheet.png",
            f"../../candidate_exports/{self.template['variant_id']}/pose-+0deg.png",
            f"../../candidate_exports/{self.template['variant_id']}/pose--30deg.png",
            f"../../candidate_exports/{self.template['variant_id']}/pose-+30deg.png",
        ):
            self.assertIn(relative, self.page)
            self.assertTrue((self.directory / relative).resolve().is_file())


if __name__ == "__main__":
    unittest.main()
