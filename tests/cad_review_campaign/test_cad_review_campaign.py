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
TOOL = ROOT / "tools/generate_cad_review_campaign.py"
OUTPUT = ROOT / "generated/myactuator/cad/campaign/campaign.json"
INDEX = ROOT / "generated/myactuator/cad/campaign/index.html"
SCHEMA = ROOT / "schemas/myactuator-cad-review-campaign.schema.json"

spec = importlib.util.spec_from_file_location(
    "cad_review_campaign_generator_test_module", TOOL
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class CadReviewCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = json.loads(OUTPUT.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_schema_exact_coverage_and_denial_summary(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.value)
        manager.validate(copy.deepcopy(self.value))
        self.assertEqual(
            {
                "accepted_configuration_count": 0,
                "assembly_configuration_count": 26,
                "blocked_re_source_or_specialized_partition_count": 12,
                "browser_releasable_configuration_count": 0,
                "candidate_export_available_count": 1,
                "configuration_count": 53,
                "currently_packet_reviewable_count": 41,
                "duplicate_geometry_configuration_count": 10,
                "duplicate_geometry_group_count": 5,
                "flattened_configuration_count": 27,
                "model_count": 44,
                "question_count_per_configuration": 13,
                "shell_only_configuration_count": 5,
                "unanswered_question_count": 689,
                "variant_count": 53,
            },
            self.value["summary"],
        )
        self.assertFalse(self.value["accepted_configuration_ids"])
        self.assertFalse(self.value["support_granted"])
        self.assertFalse(self.value["physical_motion_authority"])

    def test_every_configuration_and_variant_appears_exactly_once(self) -> None:
        configurations = self.value["configurations"]
        self.assertEqual(
            53, len({item["configuration_id"] for item in configurations})
        )
        self.assertEqual(53, len({item["variant_id"] for item in configurations}))
        self.assertEqual(
            44, len({(item["series"], item["model"]) for item in configurations})
        )
        ledger = json.loads(
            (ROOT / "assets/myactuator/cad_review.json").read_text()
        )
        self.assertEqual(
            {
                item["configuration_id"]: item["source_variant_ids"][0]
                for item in ledger["geometry_configurations"]
            },
            {
                item["configuration_id"]: item["variant_id"]
                for item in configurations
            },
        )

    def test_packet_records_and_hashes_join_both_source_structures(self) -> None:
        assembly = json.loads(
            (
                ROOT
                / "generated/myactuator/cad/review_packet_manifest.json"
            ).read_text()
        )
        flattened = json.loads(
            (
                ROOT
                / "generated/myactuator/cad/flattened_partition_manifest.json"
            ).read_text()
        )
        expected = {
            item["variant_id"]: (
                "assembly_member_packet",
                item["packet_json_sha256"],
            )
            for item in assembly["packets"]
        }
        expected.update(
            {
                item["variant_id"]: (
                    "flattened_component_packet",
                    item["packet_json_sha256"],
                )
                for item in flattened["packets"]
            }
        )
        actual = {
            item["variant_id"]: (
                item["packet_evidence"]["packet_kind"],
                item["packet_evidence"]["packet_json_sha256"],
            )
            for item in self.value["configurations"]
        }
        self.assertEqual(expected, actual)
        self.assertTrue(
            all(
                item["packet_evidence"]["local_materialization_required"]
                and not item["packet_evidence"]["redistributable"]
                for item in self.value["configurations"]
            )
        )

    def test_every_configuration_has_the_same_13_unanswered_questions(self) -> None:
        question_ids = [
            item["question_id"] for item in self.value["question_catalog"]
        ]
        self.assertEqual(13, len(question_ids))
        self.assertEqual(13, len(set(question_ids)))
        for item in self.value["configurations"]:
            self.assertEqual(
                question_ids,
                [row["question_id"] for row in item["question_responses"]],
            )
            self.assertTrue(
                all(
                    row["state"] == "unanswered"
                    and row["response"] is None
                    and row["evidence_refs"] == []
                    for row in item["question_responses"]
                )
            )

    def test_review_lanes_partition_assembly_and_flattened_risk(self) -> None:
        lanes = Counter(
            item["candidate_state"]["review_lane"]
            for item in self.value["configurations"]
        )
        self.assertEqual(
            {
                "assembly_member_semantic_review": 26,
                "flattened_disconnected_component_partition": 15,
                "flattened_face_partition_or_re_source": 2,
                "flattened_high_component_partition_or_re_source": 5,
                "shell_healing_or_re_source": 5,
            },
            dict(lanes),
        )
        self.assertEqual(
            41,
            sum(
                item["candidate_state"]["packet_reviewable_now"]
                for item in self.value["configurations"]
            ),
        )

    def test_shell_only_sources_are_blocked_not_collision_candidates(self) -> None:
        shells = [
            item
            for item in self.value["configurations"]
            if item["candidate_state"]["flattened_component_kind"] == "shell"
        ]
        self.assertEqual(5, len(shells))
        self.assertTrue(
            all(
                item["candidate_state"]["review_lane"]
                == "shell_healing_or_re_source"
                and not item["candidate_state"]["packet_reviewable_now"]
                and not item["accepted_asset"]
                for item in shells
            )
        )

    def test_duplicate_geometry_keeps_ten_independent_configurations(self) -> None:
        grouped = Counter(
            item["duplicate_geometry_group_id"]
            for item in self.value["configurations"]
            if item["duplicate_geometry_group_id"] is not None
        )
        self.assertEqual(5, len(grouped))
        self.assertEqual({2}, set(grouped.values()))
        for group in grouped:
            rows = [
                item
                for item in self.value["configurations"]
                if item["duplicate_geometry_group_id"] == group
            ]
            self.assertEqual(2, len({item["configuration_id"] for item in rows}))
            self.assertEqual(2, len({item["variant_id"] for item in rows}))

    def test_local_index_is_complete_static_and_network_free(self) -> None:
        page = INDEX.read_text(encoding="utf-8")
        folded = page.casefold()
        for forbidden in (
            "http://",
            "https://",
            "fetch(",
            "xmlhttprequest",
            "<script",
            "/home/",
        ):
            self.assertNotIn(forbidden, folded)
        for item in self.value["configurations"]:
            self.assertIn(item["configuration_id"], page)
            for path in (
                item["packet_evidence"]["overview_path"],
                item["packet_evidence"]["sheet_path"],
                item["packet_evidence"]["packet_json_path"],
            ):
                self.assertIn(manager.local_href(path), page)

    def test_mutations_cannot_answer_promote_merge_escape_or_change_lane(self) -> None:
        mutations = []
        answered = copy.deepcopy(self.value)
        response = answered["configurations"][0]["question_responses"][0]
        response.update(state="resolved", response="guessed", evidence_refs=["x"])
        manager.set_digest(answered)
        mutations.append(answered)
        accepted = copy.deepcopy(self.value)
        accepted["configurations"][0]["accepted_asset"] = True
        manager.set_digest(accepted)
        mutations.append(accepted)
        merged = copy.deepcopy(self.value)
        duplicate = next(
            item
            for item in merged["configurations"]
            if item["duplicate_geometry_group_id"] is not None
        )
        duplicate["duplicate_geometry_group_id"] = None
        manager.set_digest(merged)
        mutations.append(merged)
        escaped = copy.deepcopy(self.value)
        escaped["configurations"][0]["packet_evidence"][
            "packet_json_path"
        ] = "../../vendor.step"
        manager.set_digest(escaped)
        mutations.append(escaped)
        lane = copy.deepcopy(self.value)
        assembly = next(
            item
            for item in lane["configurations"]
            if item["source_structure"] == "assembly"
        )
        assembly["candidate_state"]["review_lane"] = (
            "flattened_disconnected_component_partition"
        )
        manager.set_digest(lane)
        mutations.append(lane)
        count = copy.deepcopy(self.value)
        count["summary"]["accepted_configuration_count"] = 1
        manager.set_digest(count)
        mutations.append(count)
        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                manager.CadReviewCampaignError
            ):
                manager.validate(value, verify_sources=False)

    def test_source_drift_and_failed_build_preserve_both_outputs(self) -> None:
        before_json = OUTPUT.read_bytes()
        before_html = INDEX.read_bytes()
        changed = copy.deepcopy(self.value)
        changed["sources"]["catalog_sha256"] = "0" * 64
        manager.set_digest(changed)
        with self.assertRaises(manager.CadReviewCampaignError):
            manager.validate(changed)
        with tempfile.TemporaryDirectory() as temporary:
            bad_ledger = Path(temporary) / "cad_review.json"
            bad_ledger.write_text("{}\n", encoding="utf-8")
            original = manager.LEDGER
            try:
                manager.LEDGER = bad_ledger
                with self.assertRaises(
                    (KeyError, manager.CadReviewCampaignError)
                ):
                    manager.build()
            finally:
                manager.LEDGER = original
        self.assertEqual(before_json, OUTPUT.read_bytes())
        self.assertEqual(before_html, INDEX.read_bytes())


if __name__ == "__main__":
    unittest.main()
