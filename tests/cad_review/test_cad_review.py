from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "validate_cad_review", ROOT / "tools" / "validate_cad_review.py"
)
assert SPEC is not None and SPEC.loader is not None
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def artifact(path: str, digest_byte: str) -> dict[str, object]:
    return {"path": path, "sha256": digest_byte * 64, "bytes": 123}


class CadReviewLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inspection = review.load_json(review.INSPECTION)
        cls.baseline = review.load_json(review.LEDGER)

    def accepted_ledger(self, structure: str = "assembly") -> tuple[dict, dict]:
        ledger = copy.deepcopy(self.baseline)
        inspection_variant = next(
            item for item in self.inspection["variants"] if item["manifest_structure"] == structure
        )
        item = next(
            variant for variant in ledger["variants"] if variant["variant_id"] == inspection_variant["variant_id"]
        )
        if structure == "assembly":
            refs = [f"#{product['entity_id']}" for product in inspection_variant["products"][:2]]
            self.assertEqual(len(refs), 2)
            method = "assembly_product_entities"
            evidence = ["reviews/example/member-selection.png"]
        else:
            refs = ["partition:housing", "partition:output"]
            method = "reviewed_partition"
            evidence = ["reviews/example/partition-front.png", "reviews/example/partition-section.png"]

        item.update(
            {
                "review_status": "accepted_local",
                "reviewer": "test-reviewer",
                "reviewed_at": "2026-07-22T12:00:00Z",
                "review_evidence_refs": ["reviews/example/review.md"],
                "redistribution_status": "local_only",
                "denial_reason": "accepted by synthetic validator fixture only",
            }
        )
        candidate = inspection_variant["length_unit_candidate"]
        item["unit"] = {
            "status": "reviewed",
            "source_length_unit": candidate,
            "scale_to_m": {"millimetre": 0.001, "metre": 1.0}[candidate],
            "override_rationale": None,
            "evidence_refs": ["reviews/example/unit-check.png"],
        }
        item["members"] = {
            "status": "reviewed",
            "method": method,
            "housing_refs": [refs[0]],
            "output_refs": [refs[1]],
            "evidence_refs": evidence,
        }
        item["frame"] = {
            "status": "reviewed",
            "source_to_canonical": [
                1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0,
            ],
            "evidence_refs": ["reviews/example/frame-check.png"],
        }
        item["joint"] = {
            "status": "reviewed",
            "joint_type": "continuous",
            "origin_m": [0.0, 0.0, 0.0],
            "axis_unit": [0.0, 0.0, 1.0],
            "positive_direction": "right-hand rule about +Z in canonical frame",
            "zero_definition": "reviewed source pose",
            "evidence_refs": ["reviews/example/axis-check.png"],
        }
        item["artifacts"] = {
            "status": "verified",
            "source_variant_sha256": item["step_sha256"],
            "toolchain_lock_sha256": "a" * 64,
            "housing_step": artifact("artifacts/example/housing.step", "b"),
            "output_step": artifact("artifacts/example/output.step", "c"),
            "housing_glb": artifact("artifacts/example/housing.glb", "d"),
            "output_glb": artifact("artifacts/example/output.glb", "e"),
            "collision_glb": artifact("artifacts/example/collision.glb", "f"),
            "visual_evidence_refs": [
                "reviews/example/zero.png",
                "reviews/example/rotated.png",
            ],
        }
        model = next(
            model
            for model in ledger["models"]
            if (model["series"], model["model"]) == (item["series"], item["model"])
        )
        configuration = next(
            configuration
            for configuration in ledger["geometry_configurations"]
            if configuration["source_variant_ids"] == [item["variant_id"]]
        )
        configuration.update(
            {
                "selector_status": "reviewed",
                "selector_key": "synthetic_fixture",
                "selector_dimensions": [],
                "canonical_variant_id": item["variant_id"],
                "status": "accepted_local",
                "reviewer": "test-reviewer",
                "reviewed_at": "2026-07-22T12:00:00Z",
                "evidence_refs": ["reviews/example/configuration-selector.md"],
                "denial_reason": "accepted by synthetic validator fixture only",
            }
        )
        model_configurations = [
            candidate
            for candidate in ledger["geometry_configurations"]
            if (candidate["series"], candidate["model"]) == (item["series"], item["model"])
        ]
        model.update(
            {
                "status": (
                    "supported_local"
                    if len(model_configurations) == 1
                    else "partially_supported_local"
                ),
                "denial_reason": "local synthetic validation fixture",
            }
        )
        return ledger, item

    def test_baseline_covers_53_variants_44_models_and_supports_zero(self) -> None:
        review.validate_ledger(self.baseline, self.inspection)
        report = review.build_support_report(self.baseline)
        self.assertEqual(report["summary"]["variants"], 53)
        self.assertEqual(report["summary"]["geometry_configurations"], 53)
        self.assertEqual(report["summary"]["models"], 44)
        self.assertEqual(report["summary"]["supported_models"], 0)
        self.assertEqual(report["summary"]["variant_statuses"], {"unreviewed": 53})
        self.assertEqual(report["summary"]["configuration_statuses"], {"unsupported": 53})
        self.assertEqual(report["summary"]["model_statuses"], {"unsupported": 44})

    def test_complete_synthetic_assembly_and_flattened_reviews_validate(self) -> None:
        for structure in ("assembly", "flattened"):
            with self.subTest(structure=structure):
                ledger, _ = self.accepted_ledger(structure)
                review.validate_ledger(ledger, self.inspection)

    def test_source_identity_drift_is_rejected(self) -> None:
        ledger = copy.deepcopy(self.baseline)
        ledger["variants"][0]["step_sha256"] = "0" * 64
        with self.assertRaisesRegex(review.CadReviewError, "source identity mismatch"):
            review.validate_ledger(ledger, self.inspection)

    def test_unreviewed_row_cannot_smuggle_authority(self) -> None:
        for mutation in ("reviewer", "unit", "artifacts"):
            ledger = copy.deepcopy(self.baseline)
            item = ledger["variants"][0]
            if mutation == "reviewer":
                item["reviewer"] = "someone"
            elif mutation == "unit":
                item["unit"]["status"] = "reviewed"
            else:
                item["artifacts"]["status"] = "verified"
            with self.subTest(mutation=mutation):
                with self.assertRaises(review.CadReviewError):
                    review.validate_ledger(ledger, self.inspection)

    def test_zero_axis_nonrigid_transform_and_missing_output_fail(self) -> None:
        mutations = []
        ledger, item = self.accepted_ledger()
        item["joint"]["axis_unit"] = [0.0, 0.0, 0.0]
        mutations.append(ledger)
        ledger, item = self.accepted_ledger()
        item["frame"]["source_to_canonical"][0] = 2.0
        mutations.append(ledger)
        ledger, item = self.accepted_ledger()
        item["artifacts"]["output_step"] = None
        mutations.append(ledger)
        for candidate in mutations:
            with self.assertRaises(review.CadReviewError):
                review.validate_ledger(candidate, self.inspection)

    def test_housing_and_output_must_be_disjoint_and_distinct(self) -> None:
        ledger, item = self.accepted_ledger()
        item["members"]["output_refs"] = list(item["members"]["housing_refs"])
        with self.assertRaisesRegex(review.CadReviewError, "disjoint"):
            review.validate_ledger(ledger, self.inspection)
        ledger, item = self.accepted_ledger()
        item["artifacts"]["output_glb"]["sha256"] = item["artifacts"]["housing_glb"]["sha256"]
        with self.assertRaisesRegex(review.CadReviewError, "GLB artifacts are identical"):
            review.validate_ledger(ledger, self.inspection)

    def test_assembly_refs_must_exist_and_flattened_requires_partition_evidence(self) -> None:
        ledger, item = self.accepted_ledger("assembly")
        item["members"]["output_refs"] = ["#999999999"]
        with self.assertRaisesRegex(review.CadReviewError, "unknown product"):
            review.validate_ledger(ledger, self.inspection)
        ledger, item = self.accepted_ledger("flattened")
        item["members"]["method"] = "assembly_product_entities"
        with self.assertRaisesRegex(review.CadReviewError, "reviewed partition"):
            review.validate_ledger(ledger, self.inspection)
        ledger, item = self.accepted_ledger("flattened")
        item["members"]["evidence_refs"] = item["members"]["evidence_refs"][:1]
        with self.assertRaisesRegex(review.CadReviewError, "at least 2"):
            review.validate_ledger(ledger, self.inspection)

    def test_unit_candidate_override_requires_reason_and_exact_scale(self) -> None:
        ledger, item = self.accepted_ledger()
        item["unit"]["source_length_unit"] = "metre"
        item["unit"]["scale_to_m"] = 1.0
        with self.assertRaisesRegex(review.CadReviewError, "override requires rationale"):
            review.validate_ledger(ledger, self.inspection)
        ledger, item = self.accepted_ledger()
        item["unit"]["scale_to_m"] = 1.0
        with self.assertRaisesRegex(review.CadReviewError, "unit scale"):
            review.validate_ledger(ledger, self.inspection)

    def test_model_support_cannot_exceed_variant_acceptance(self) -> None:
        ledger = copy.deepcopy(self.baseline)
        variant = ledger["variants"][0]
        model = next(
            item
            for item in ledger["models"]
            if (item["series"], item["model"]) == (variant["series"], variant["model"])
        )
        model["status"] = "supported_local"
        with self.assertRaisesRegex(review.CadReviewError, "model status"):
            review.validate_ledger(ledger, self.inspection)

    def test_configuration_selectors_cover_each_variant_exactly_once(self) -> None:
        source_ids = [
            source_id
            for configuration in self.baseline["geometry_configurations"]
            for source_id in configuration["source_variant_ids"]
        ]
        self.assertEqual(len(source_ids), 53)
        self.assertEqual(len(source_ids), len(set(source_ids)))
        ledger = copy.deepcopy(self.baseline)
        ledger["geometry_configurations"][1]["source_variant_ids"] = list(
            ledger["geometry_configurations"][0]["source_variant_ids"]
        )
        with self.assertRaises(review.CadReviewError):
            review.validate_ledger(ledger, self.inspection)

    def test_unresolved_selector_cannot_merge_duplicate_geometry_provenance(self) -> None:
        ledger = copy.deepcopy(self.baseline)
        by_hash = {}
        for item in ledger["variants"]:
            by_hash.setdefault(item["step_sha256"], []).append(item["variant_id"])
        pair = next(ids for ids in by_hash.values() if len(ids) == 2)
        first = next(c for c in ledger["geometry_configurations"] if c["source_variant_ids"] == [pair[0]])
        second = next(c for c in ledger["geometry_configurations"] if c["source_variant_ids"] == [pair[1]])
        first["source_variant_ids"] = pair
        ledger["geometry_configurations"].remove(second)
        model = next(
            item
            for item in ledger["models"]
            if (item["series"], item["model"]) == (first["series"], first["model"])
        )
        model["configuration_ids"].remove(second["configuration_id"])
        with self.assertRaisesRegex(review.CadReviewError, "unresolved selector cannot merge"):
            review.validate_ledger(ledger, self.inspection)

        first.update(
            {
                "selector_status": "reviewed",
                "selector_key": "geometry_equivalent_package_revisions",
                "selector_dimensions": [
                    {
                        "name": "geometry_equivalence",
                        "value": "byte_identical",
                        "evidence_refs": ["reviews/equivalence/hash-proof.json"],
                    }
                ],
                "canonical_variant_id": pair[0],
                "status": "candidate",
                "reviewer": "test-reviewer",
                "reviewed_at": "2026-07-22T12:00:00Z",
                "evidence_refs": ["reviews/equivalence/review.md"],
            }
        )
        review.validate_ledger(ledger, self.inspection)

    def test_duplicate_geometry_does_not_inherit_a_review(self) -> None:
        ledger, accepted = self.accepted_ledger("flattened")
        same_hash = [
            item for item in ledger["variants"] if item["step_sha256"] == accepted["step_sha256"]
        ]
        if len(same_hash) == 2:
            other = next(item for item in same_hash if item["variant_id"] != accepted["variant_id"])
            self.assertEqual(other["review_status"], "unreviewed")
        review.validate_ledger(ledger, self.inspection)

    def test_schema_rejects_unknown_fields_and_report_is_reproducible(self) -> None:
        ledger = copy.deepcopy(self.baseline)
        ledger["variants"][0]["invented"] = True
        with self.assertRaisesRegex(review.CadReviewError, "schema"):
            review.validate_ledger(ledger, self.inspection)
        report = review.build_support_report(self.baseline)
        path = ROOT / "generated" / "myactuator" / "cad" / "support_report.json"
        self.assertEqual(path.read_text(encoding="utf-8"), review.canonical_json(report))


if __name__ == "__main__":
    unittest.main(verbosity=2)
