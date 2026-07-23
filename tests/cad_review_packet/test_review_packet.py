from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from cad_review_packet_common import AUTHORITY_FIELDS, candidate_score  # noqa: E402


class CadReviewPacketTests(unittest.TestCase):
    def test_candidate_score_is_ranking_only_and_multilingual(self) -> None:
        self.assertEqual(candidate_score("输出法兰 D"), (20, ["输出", "法兰"]))
        self.assertEqual(candidate_score("Output Shaft"), (19, ["output", "shaft"]))
        self.assertEqual(candidate_score("转子组件"), (5, ["转子"]))
        self.assertEqual(candidate_score("housing screw"), (-12, ["screw", "housing"]))
        self.assertEqual(candidate_score(None), (0, []))

    def test_tracked_manifest_has_exact_fail_closed_assembly_coverage(self) -> None:
        inspection = json.loads(
            (ROOT / "generated/myactuator/cad/step_inspection.json").read_text()
        )
        manifest = json.loads(
            (ROOT / "generated/myactuator/cad/review_packet_manifest.json").read_text()
        )
        expected = sorted(
            variant["variant_id"]
            for variant in inspection["variants"]
            if variant["manifest_structure"] == "assembly"
        )
        self.assertEqual(len(expected), 26)
        self.assertEqual(
            [packet["variant_id"] for packet in manifest["packets"]], expected
        )
        self.assertEqual(manifest["support_granted_count"], 0)
        self.assertTrue(
            all(
                packet["candidate_visuals_only"]
                and packet["support_granted"] is False
                for packet in manifest["packets"]
            )
        )

    def test_packet_authority_fields_are_explicit(self) -> None:
        self.assertEqual(
            AUTHORITY_FIELDS,
            (
                "heuristic_selects_output",
                "housing_member_identified",
                "output_member_identified",
                "joint_axis_identified",
                "simulation_supported",
            ),
        )


if __name__ == "__main__":
    unittest.main()
