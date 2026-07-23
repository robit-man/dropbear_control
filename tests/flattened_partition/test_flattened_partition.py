from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from flattened_partition_common import AUTHORITY_FIELDS, disposition  # noqa: E402


class FlattenedPartitionTests(unittest.TestCase):
    def test_fail_closed_dispositions_cover_topology_shapes(self) -> None:
        self.assertEqual(
            disposition("shell", 8),
            "blocked_shell_only_re_source_or_reviewed_healing_required",
        )
        self.assertEqual(
            disposition("solid", 1),
            "blocked_inseparable_single_solid_re_source_or_face_partition_required",
        )
        self.assertEqual(
            disposition("solid", 2),
            "candidate_disconnected_solids_manual_partition_required",
        )
        self.assertEqual(
            disposition("solid", 517),
            "blocked_high_component_count_partition_ui_or_better_source_required",
        )

    def test_tracked_manifest_covers_all_flattened_variants_without_support(self) -> None:
        inspection = json.loads(
            (ROOT / "generated/myactuator/cad/step_inspection.json").read_text()
        )
        manifest = json.loads(
            (ROOT / "generated/myactuator/cad/flattened_partition_manifest.json").read_text()
        )
        expected = sorted(
            variant["variant_id"]
            for variant in inspection["variants"]
            if variant["manifest_structure"] == "flattened"
        )
        self.assertEqual(len(expected), 27)
        self.assertEqual(
            [packet["variant_id"] for packet in manifest["packets"]], expected
        )
        self.assertEqual(manifest["shell_only_variant_count"], 5)
        self.assertEqual(manifest["support_granted_count"], 0)
        self.assertTrue(
            all(
                packet["candidate_partition_only"]
                and packet["support_granted"] is False
                for packet in manifest["packets"]
            )
        )

    def test_partition_authority_fields_are_explicit(self) -> None:
        self.assertEqual(
            AUTHORITY_FIELDS,
            (
                "stable_component_ids_are_semantic",
                "housing_member_identified",
                "output_member_identified",
                "joint_axis_identified",
                "simulation_supported",
            ),
        )


if __name__ == "__main__":
    unittest.main()
