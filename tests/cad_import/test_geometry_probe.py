from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "generated" / "myactuator" / "cad" / "geometry_probe.json"


class GeometryProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    def test_every_exact_source_imported_and_remains_unsupported(self) -> None:
        summary = self.report["summary"]
        self.assertEqual(summary["models"], 44)
        self.assertEqual(summary["variants"], 53)
        self.assertEqual(summary["unique_geometries_probed"], 48)
        self.assertEqual(summary["imports_succeeded"], 53)
        self.assertEqual(summary["valid_topologies"], 53)
        self.assertEqual(summary["visual_tessellation_candidates"], 53)
        self.assertEqual(summary["supported_models"], 0)
        self.assertTrue(all(not item["simulation_supported"] for item in self.report["variants"]))

    def test_five_shell_only_variants_are_not_collision_candidates(self) -> None:
        shell_only = [item for item in self.report["variants"] if item["topology"]["solids"] == 0]
        self.assertEqual(len(shell_only), 5)
        self.assertEqual(
            sorted((item["series"], item["model"]) for item in shell_only),
            [
                ("CEM", "CEM-25"),
                ("CEM", "CEM-45"),
                ("FL-FLO", "FL-85-23"),
                ("RMD-X", "X6-8"),
                ("RMD-X", "X6-8"),
            ],
        )
        for item in shell_only:
            self.assertTrue(item["readiness"]["requires_healing_or_solidification"])
            self.assertFalse(item["readiness"]["closed_solid_collision_candidate"])
            self.assertGreater(item["topology"]["faces"], 0)

    def test_closed_solid_candidates_still_require_member_review(self) -> None:
        with_solids = [item for item in self.report["variants"] if item["topology"]["solids"] > 0]
        self.assertEqual(len(with_solids), 48)
        for item in with_solids:
            self.assertTrue(item["readiness"]["closed_solid_collision_candidate"])
            self.assertTrue(item["readiness"]["requires_semantic_member_review"])
            self.assertFalse(item["member_identity_preserved"])
            self.assertFalse(item["housing_member_identified"])
            self.assertFalse(item["output_member_identified"])
            self.assertFalse(item["joint_axis_identified"])

    def test_duplicate_geometry_reuse_preserves_all_source_rows(self) -> None:
        reused = [
            item for item in self.report["variants"] if item["geometry_reused_from_variant_id"] is not None
        ]
        self.assertEqual(len(reused), 5)
        by_id = {item["variant_id"]: item for item in self.report["variants"]}
        for item in reused:
            source = by_id[item["geometry_reused_from_variant_id"]]
            self.assertEqual(item["step_sha256"], source["step_sha256"])
            self.assertNotEqual(item["vendor_relative_path"], source["vendor_relative_path"])

    def test_metre_token_outlier_is_not_silently_rescaled_by_review(self) -> None:
        outlier = next(
            item
            for item in self.report["variants"]
            if (item["series"], item["model"]) == ("FL-FLO", "FL-85-23")
        )
        self.assertEqual(outlier["length_unit_candidate"], "metre")
        self.assertEqual(outlier["occt_internal_bbox_mm"]["size"], [84.998490479, 122.08160133, 48.436786424])
        self.assertFalse(outlier["simulation_supported"])

    def test_report_is_bound_to_inspection_and_toolchain(self) -> None:
        self.assertEqual(
            self.report["inspection_report_sha256"],
            hashlib.sha256(
                (ROOT / "generated" / "myactuator" / "cad" / "step_inspection.json").read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(
            self.report["toolchain_lock_sha256"],
            hashlib.sha256((ROOT / "tools" / "cad-toolchain-lock.json").read_bytes()).hexdigest(),
        )
        self.assertEqual(self.report["evidence_class"], "offline-cad-import")
        self.assertFalse(self.report["source_geometry_interpreted_semantically"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

