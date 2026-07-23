from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/generate_plant_spec_candidates.py"
OUTPUT = (
    ROOT / "generated/myactuator/plant/spec_candidates/registry.json"
)
HTML_OUTPUT = (
    ROOT / "generated/myactuator/plant/spec_candidates/index.html"
)
SCHEMA = (
    ROOT
    / "schemas/myactuator-plant-spec-candidate-registry.schema.json"
)
PLAN = ROOT / "assets/myactuator/plant_spec_extraction_plan.json"

spec = importlib.util.spec_from_file_location(
    "plant_spec_candidate_generator_test_module",
    TOOL,
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class PlantSpecCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = json.loads(OUTPUT.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        cls.applicability = json.loads(
            manager.PROTOCOL_APPLICABILITY.read_text(encoding="utf-8")
        )
        cls.plant_ledger = json.loads(
            (
                ROOT
                / "generated/myactuator/plant/evidence_ledger/ledger.json"
            ).read_text(encoding="utf-8")
        )

    @staticmethod
    def redigest(value: dict) -> None:
        manager.set_digest(value)

    @staticmethod
    def table(value: dict, model: str) -> dict:
        return next(
            item
            for item in value["model_tables"]
            if item["model_identity"]["model"] == model
        )

    @classmethod
    def candidate(
        cls,
        value: dict,
        model: str,
        property_id: str,
    ) -> dict:
        return next(
            item
            for item in cls.table(value, model)["candidates"]
            if item["source_property_id"] == property_id
        )

    def test_schema_registry_and_summary_are_exact(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.value)
        manager.validate(copy.deepcopy(self.value))
        self.assertEqual(
            {
                "accepted_candidate_count": 0,
                "candidate_count": 531,
                "direct_label_unit_mapping_candidate_count": 89,
                "manual_occurrence_count": 15,
                "model_count": 44,
                "model_with_candidate_count": 44,
                "page_count": 215,
                "product_spec_manual_count": 9,
                "runtime_admissible_candidate_count": 0,
                "semantic_review_mapping_candidate_count": 317,
                "unmapped_candidate_count": 125,
                "unreviewed_candidate_count": 531,
            },
            self.value["summary"],
        )

    def test_all_fifteen_manuals_and_pages_are_hash_bound(self) -> None:
        self.assertEqual(15, len(self.value["manuals"]))
        pages = [
            page
            for manual in self.value["manuals"]
            for page in manual["pages"]
        ]
        self.assertEqual(215, len(pages))
        self.assertEqual(
            1,
            sum(
                page["text_status"] == "no_extractable_text"
                for page in pages
            ),
        )
        for manual in self.value["manuals"]:
            self.assertEqual(
                list(range(1, manual["page_count"] + 1)),
                [page["pdf_page_index"] for page in manual["pages"]],
            )
            self.assertFalse(
                Path(manual["vendor_relative_path"]).is_absolute()
            )
            self.assertNotIn(
                "..",
                Path(manual["vendor_relative_path"]).parts,
            )
            source = (
                manager.DOCUMENT_ROOT / manual["vendor_relative_path"]
            )
            self.assertEqual(manual["bytes"], source.stat().st_size)
            self.assertEqual(
                manual["file_sha256"],
                manager.sha_file(source),
            )

    def test_plan_selects_every_exact_model_once_without_family_fallback(
        self,
    ) -> None:
        selections, sources = manager.load_and_validate_plan(
            registry=self.applicability
        )
        self.assertEqual(44, len(selections))
        self.assertEqual(9, len(sources))
        self.assertEqual(
            {item["model"] for item in self.applicability["models"]},
            set(selections),
        )
        plan = json.loads(PLAN.read_text(encoding="utf-8"))
        plan["sources"][0]["tables"][0]["model"] = "X6"
        with mock.patch.object(manager, "load_json", return_value=plan):
            with self.assertRaisesRegex(
                manager.PlantSpecCandidateError,
                "every catalog model exactly once",
            ):
                manager.load_and_validate_plan(
                    registry=self.applicability
                )

    def test_model_tables_retain_exact_source_header_page_and_coordinates(
        self,
    ) -> None:
        self.assertEqual(44, len(self.value["model_tables"]))
        for table in self.value["model_tables"]:
            self.assertEqual(
                table["model_identity"]["model"],
                table["model_header_text"],
            )
            self.assertGreaterEqual(len(table["candidates"]), 8)
            self.assertFalse(table["runtime_admissible"])
            self.assertEqual(0, table["accepted_candidate_count"])
            self.assertIn(
                "independent_manual_applicability_review_missing",
                table["applicability_blockers"],
            )
            manual = next(
                item
                for item in self.value["manuals"]
                if item["document_occurrence_id"]
                == table["document_occurrence_id"]
            )
            self.assertEqual(
                manual["pages"][table["pdf_page_index"] - 1][
                    "text_sha256"
                ],
                table["page_text_sha256"],
            )

    def test_cross_family_samples_preserve_raw_values_and_ambiguity(
        self,
    ) -> None:
        x12 = self.candidate(self.value, "X12-320", "gear_ratio")
        self.assertEqual("20", x12["source"]["value_text"])
        self.assertEqual([20.0], x12["parse"]["numbers"])
        self.assertEqual(
            "candidate_direct_label_unit_match",
            x12["mapping"]["status"],
        )
        rh14 = self.candidate(self.value, "RH-14", "gear_ratio")
        self.assertEqual("50 ｜100", rh14["source"]["value_text"])
        self.assertEqual("alternatives", rh14["parse"]["kind"])
        self.assertEqual([50.0, 100.0], rh14["parse"]["numbers"])
        self.assertIn(
            "source_value_not_single_scalar",
            rh14["mapping"]["blockers"],
        )
        l4005 = self.candidate(
            self.value,
            "L-4005",
            "rotor_inertia",
        )
        self.assertEqual("gcm 2", l4005["source"]["unit_text"])
        self.assertEqual([56.0], l4005["parse"]["numbers"])
        self.assertEqual(
            1e-7,
            l4005["mapping"]["conversion"]["scale"],
        )
        temperature = self.candidate(
            self.value,
            "L-4005",
            "working_temperature",
        )
        self.assertEqual("range", temperature["parse"]["kind"])
        self.assertEqual([-20.0, 55.0], temperature["parse"]["numbers"])
        fl = self.candidate(
            self.value,
            "FL-50-08",
            "motor_phase_resistance",
        )
        self.assertEqual("0.62", fl["source"]["value_text"])
        flo = self.candidate(
            self.value,
            "FLO-50-15",
            "torque_constant",
        )
        self.assertEqual("0.07", flo["source"]["value_text"])

    def test_every_candidate_is_parsed_unreviewed_and_non_authoritative(
        self,
    ) -> None:
        identifiers: set[str] = set()
        for table in self.value["model_tables"]:
            properties: set[str] = set()
            for candidate in table["candidates"]:
                self.assertNotEqual("unparsed", candidate["parse"]["kind"])
                self.assertEqual(
                    {
                        "decision_note": None,
                        "reviewed_at_utc": None,
                        "reviewer_id": None,
                        "status": "unreviewed",
                    },
                    candidate["review"],
                )
                self.assertNotIn(
                    candidate["candidate_id"],
                    identifiers,
                )
                identifiers.add(candidate["candidate_id"])
                self.assertNotIn(
                    candidate["source_property_id"],
                    properties,
                )
                properties.add(candidate["source_property_id"])
        self.assertEqual(531, len(identifiers))
        self.assertFalse(self.value["runtime_plant_admission"])
        self.assertFalse(self.value["support_granted"])
        self.assertFalse(self.value["physical_motion_authority"])

    def test_mapping_keeps_semantics_units_and_shapes_distinct(self) -> None:
        phase = self.candidate(
            self.value,
            "FLO-70-15",
            "phase_inductance",
        )
        self.assertEqual(
            "candidate_semantic_review_required",
            phase["mapping"]["status"],
        )
        self.assertIn(
            "line_or_phase_basis_not_explicit",
            phase["mapping"]["blockers"],
        )
        module = self.candidate(
            self.value,
            "X12-320",
            "module_torque_constant",
        )
        self.assertIn(
            "module_vs_motor_shaft_definition_unresolved",
            module["mapping"]["blockers"],
        )
        voltage = self.candidate(
            self.value,
            "H-70-15",
            "input_voltage",
        )
        self.assertIsNone(voltage["mapping"]["target_field_id"])
        self.assertIn(
            "scalar_voltage_cannot_fill_required_range",
            voltage["mapping"]["blockers"],
        )
        peak = self.candidate(
            self.value,
            "CEM-45",
            "peak_torque",
        )
        self.assertIn(
            "peak_duration_not_stated",
            peak["mapping"]["blockers"],
        )

    def test_candidate_page_target_identity_and_authority_mutations_deny(
        self,
    ) -> None:
        candidate_id = copy.deepcopy(self.value)
        candidate_id["model_tables"][0]["candidates"][0][
            "candidate_id"
        ] = "plantspeccandidate-" + "0" * 20
        self.redigest(candidate_id)
        with self.assertRaisesRegex(
            manager.PlantSpecCandidateError,
            "stable candidate identity drift",
        ):
            manager.validate(candidate_id, verify_sources=False)

        page = copy.deepcopy(self.value)
        page["model_tables"][0]["page_text_sha256"] = "0" * 64
        self.redigest(page)
        with self.assertRaisesRegex(
            manager.PlantSpecCandidateError,
            "page text digest drift",
        ):
            manager.validate(page, verify_sources=False)

        target = copy.deepcopy(self.value)
        target["model_tables"][0]["candidates"][0]["mapping"][
            "target_field_id"
        ] = "electrical.fabricated_value"
        self.redigest(target)
        with self.assertRaisesRegex(
            manager.PlantSpecCandidateError,
            "unknown runtime target field",
        ):
            manager.validate(target, verify_sources=False)

        authority = copy.deepcopy(self.value)
        authority["runtime_plant_admission"] = True
        self.redigest(authority)
        with self.assertRaisesRegex(
            manager.PlantSpecCandidateError,
            "registry schema failure",
        ):
            manager.validate(authority, verify_sources=False)

    def test_source_digest_and_environment_drift_deny(self) -> None:
        source = copy.deepcopy(self.value)
        source["sources"]["catalog_sha256"] = "0" * 64
        self.redigest(source)
        with self.assertRaisesRegex(
            manager.PlantSpecCandidateError,
            "registry source digests drift",
        ):
            manager.validate(source)
        lock = json.loads(
            manager.ENVIRONMENT_LOCK.read_text(encoding="utf-8")
        )
        lock["expected_version"] = "0.0.0"
        original = manager.load_json

        def fake_load(path: Path) -> dict:
            if path == manager.ENVIRONMENT_LOCK:
                return lock
            return original(path)

        with mock.patch.object(manager, "load_json", side_effect=fake_load):
            with self.assertRaisesRegex(
                manager.PlantSpecCandidateError,
                "!= locked",
            ):
                manager.check_environment()

    def test_repeated_build_is_byte_stable_and_outputs_are_local_only(
        self,
    ) -> None:
        rebuilt = manager.build()
        self.assertEqual(self.value, rebuilt)
        self.assertEqual(
            OUTPUT.read_text(encoding="utf-8"),
            manager.canonical_json(rebuilt),
        )
        rendered = HTML_OUTPUT.read_text(encoding="utf-8")
        self.assertEqual(rendered, manager.render_html(rebuilt))
        self.assertNotIn("http://", rendered)
        self.assertNotIn("https://", rendered)
        self.assertNotIn(str(ROOT), OUTPUT.read_text(encoding="utf-8"))

    def test_existing_plant_ledger_remains_zero_fact_and_zero_runtime(
        self,
    ) -> None:
        summary = self.plant_ledger["summary"]
        self.assertEqual(0, summary["source_fact_count"])
        self.assertEqual(0, summary["accepted_source_fact_count"])
        self.assertEqual(0, summary["runtime_plant_count"])
        self.assertEqual(1496, summary["missing_parameter_requirement_count"])
        self.assertEqual(
            176,
            summary["missing_operating_envelope_requirement_count"],
        )
        self.assertFalse(self.plant_ledger["support_granted"])
        self.assertFalse(
            self.plant_ledger["physical_motion_authority"]
        )


if __name__ == "__main__":
    unittest.main()
