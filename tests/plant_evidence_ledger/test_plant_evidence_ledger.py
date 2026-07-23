from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from tools import manage_plant_candidate_decisions as decisions


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/generate_plant_evidence_ledger.py"
OUTPUT = (
    ROOT / "generated/myactuator/plant/evidence_ledger/ledger.json"
)
LEDGER_SCHEMA = (
    ROOT / "schemas/myactuator-plant-evidence-ledger.schema.json"
)
FACT_SCHEMA = ROOT / "schemas/myactuator-plant-source-fact.schema.json"

spec = importlib.util.spec_from_file_location(
    "plant_evidence_ledger_generator_test_module",
    TOOL,
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class PlantEvidenceLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = json.loads(OUTPUT.read_text(encoding="utf-8"))
        cls.ledger_schema = json.loads(
            LEDGER_SCHEMA.read_text(encoding="utf-8")
        )
        cls.fact_schema = json.loads(
            FACT_SCHEMA.read_text(encoding="utf-8")
        )
        cls.applicability = json.loads(
            manager.APPLICABILITY.read_text(encoding="utf-8")
        )
        cls.models = {
            item["model_key"]: item
            for item in cls.applicability["models"]
        }
        cls.occurrences = {
            item["occurrence_id"]: item
            for item in cls.applicability[
                "document_file_occurrences"
            ]
        }
        cls.candidate_manuals = {
            item["model_key"]: set(
                next(
                    model["candidate_product_manual_occurrence_ids"]
                    for model in cls.value["models"]
                    if model["model_key"] == item["model_key"]
                )
            )
            for item in cls.applicability["models"]
        }
        cls.candidate_registry = json.loads(
            manager.CANDIDATE_REGISTRY.read_text(encoding="utf-8")
        )
        cls.candidate_index = {
            candidate["candidate_id"]: (table, candidate)
            for table in cls.candidate_registry["model_tables"]
            for candidate in table["candidates"]
        }
        cls.candidate_registry_sha256 = manager.sha_file(
            manager.CANDIDATE_REGISTRY
        )

    def example_fact(self) -> dict:
        table, candidate = self.candidate_index[
            "plantspeccandidate-10343b7196c9e64f5e7e"
        ]
        submission = {
            "submission_id": (
                "plantcandidatesubmission-11111111111111111111"
            ),
            "submitted_at_utc": "2026-07-23T00:00:00Z",
            "extractor": {
                "role_id": "plant_source_extractor",
                "actor_id": "test-extractor",
                "organization_or_team": "test-extraction-team",
                "assignment_register_revision": 1,
                "competence_evidence_refs": [
                    "evidence://test/extractor-competence"
                ],
            },
            "proposal": {
                "fact": {
                    "target": {
                        "requirement_kind": "parameter",
                        "domain": "electrical",
                        "name": "phase_inductance_h",
                        "canonical_unit": "H",
                    },
                    "observation": {
                        "shape": "scalar",
                        "source_value": 0.05,
                        "source_unit": "mH",
                        "normalized_value": 0.00005,
                        "normalized_unit": "H",
                        "conversion": {
                            "kind": "exact_linear_si",
                            "scale": 0.001,
                            "offset": 0.0,
                            "expression": "mH * 0.001 = H",
                        },
                    },
                    "source_interpretation": {
                        "selected_number_indices": [0],
                        "qualifier_resolution": None,
                        "annotation_resolution": None,
                        "alternative_resolution": None,
                    },
                    "evidence_class": "official_stated",
                    "extraction_method": "machine_text_assisted",
                    "uncertainty": {
                        "class": "transcribed_display_resolution",
                        "lower": -0.000005,
                        "upper": 0.000005,
                        "unit": "H",
                        "coverage_probability": 1.0,
                    },
                    "operating_condition": {
                        "supply_voltage_v": None,
                        "ambient_temperature_k": None,
                        "rotation_direction": "not_stated",
                        "notes": None,
                    },
                }
            },
        }
        event = {
            "event_id": "plantcandidateevent-22222222222222222222",
            "reviewer": {
                "role_id": "plant_fact_reviewer",
                "actor_id": "test-reviewer",
                "organization_or_team": "test-review-team",
                "assignment_register_revision": 1,
                "competence_evidence_refs": [
                    "evidence://test/reviewer-competence"
                ],
                "reviewed_at_utc": "2026-07-23T01:00:00Z",
                "decision_assertion": "Synthetic test-only review.",
                "signature_evidence_refs": [
                    "evidence://test/reviewer-signature"
                ],
            },
        }
        return decisions.materialize_fact(
            submission=submission,
            event=event,
            table=table,
            candidate=candidate,
            candidate_registry_sha256=self.candidate_registry_sha256,
            registry_generation_sha256="3" * 64,
        )

    def validate_fact(self, fact: dict) -> None:
        manager.validate_source_fact(
            fact,
            fact_schema=self.fact_schema,
            models=self.models,
            occurrences=self.occurrences,
            candidate_manuals_by_model=self.candidate_manuals,
            candidate_index=self.candidate_index,
            candidate_registry_sha256=self.candidate_registry_sha256,
        )

    def test_schema_and_tracked_ledger_are_exact_and_model_complete(
        self,
    ) -> None:
        Draft202012Validator.check_schema(self.ledger_schema)
        Draft202012Validator(self.ledger_schema).validate(self.value)
        manager.validate(copy.deepcopy(self.value))
        self.assertEqual(
            {
                "accepted_source_fact_count": 0,
                "candidate_model_manual_relationship_count": 106,
                "candidate_product_manual_occurrence_count": 15,
                "correlated_model_count": 0,
                "missing_operating_envelope_requirement_count": 176,
                "missing_parameter_requirement_count": 1496,
                "model_count": 44,
                "model_operating_envelope_requirement_count": 176,
                "model_parameter_requirement_count": 1496,
                "parameter_domain_count": 7,
                "required_operating_envelope_field_count": 4,
                "required_parameter_field_count": 34,
                "runtime_plant_count": 0,
                "source_fact_complete_model_count": 0,
                "source_fact_count": 0,
                "supported_model_count": 0,
                "unreviewed_source_fact_count": 0,
            },
            self.value["summary"],
        )

    def test_all_1672_requirements_are_explicit_null_blockers(self) -> None:
        self.assertEqual(44, len(self.value["models"]))
        for model in self.value["models"]:
            self.assertEqual(34, len(model["parameter_evidence"]))
            self.assertEqual(
                4,
                len(model["operating_envelope_evidence"]),
            )
            for state in (
                model["parameter_evidence"]
                + model["operating_envelope_evidence"]
            ):
                self.assertEqual("missing", state["status"])
                self.assertIsNone(state["selected_fact_id"])
                self.assertIsNone(state["value"])
                self.assertIsNone(state["uncertainty"])
                self.assertEqual(
                    ["exact_model_source_fact_missing"],
                    state["blockers"],
                )
            self.assertFalse(model["source_fact_complete"])
            self.assertFalse(model["correlation_complete"])
            self.assertFalse(model["support_granted"])

    def test_requirement_matrix_matches_runtime_plant_contract(self) -> None:
        plant_tool = ROOT / "tools/generate_plant_registry.py"
        plant_spec = importlib.util.spec_from_file_location(
            "plant_registry_contract_test_module",
            plant_tool,
        )
        assert plant_spec is not None and plant_spec.loader is not None
        plant = importlib.util.module_from_spec(plant_spec)
        sys.modules[plant_spec.name] = plant
        plant_spec.loader.exec_module(plant)
        expected = {
            f"{domain}.{name}": unit
            for domain, fields in plant.EXPECTED_UNITS.items()
            for name, unit in fields.items()
        }
        actual = {
            item["field_id"]: item["canonical_unit"]
            for item in self.value["parameter_catalog"]
        }
        self.assertEqual(expected, actual)
        self.assertEqual(
            plant.EXPECTED_ENVELOPE_UNITS,
            {
                item["name"]: item["canonical_unit"]
                for item in self.value["operating_envelope_catalog"]
            },
        )

    def test_candidate_manual_relationships_preserve_generation_and_prefix(
        self,
    ) -> None:
        counts = {
            model["model"]: len(
                model["candidate_product_manual_occurrence_ids"]
            )
            for model in self.value["models"]
        }
        self.assertTrue(
            all(counts[name] == 4 for name in counts if name.startswith("X"))
        )
        self.assertTrue(
            all(counts[name] == 1 for name in counts if name.startswith("L-"))
        )
        self.assertTrue(
            all(
                counts[name] == 2
                for name in counts
                if name.startswith(("FL-", "FLO-", "RH-", "CEM-", "H-"))
            )
        )
        manuals = {
            item["document_occurrence_id"]: item
            for item in self.value["candidate_product_manuals"]
        }
        fl = next(
            model for model in self.value["models"] if model["model"] == "FL-38-08"
        )
        flo = next(
            model
            for model in self.value["models"]
            if model["model"] == "FLO-50-15"
        )
        self.assertEqual(
            {"FL-user-manual"},
            {
                manuals[identifier]["document_set"]
                for identifier in fl[
                    "candidate_product_manual_occurrence_ids"
                ]
            },
        )
        self.assertEqual(
            {"FLO-user-manual"},
            {
                manuals[identifier]["document_set"]
                for identifier in flo[
                    "candidate_product_manual_occurrence_ids"
                ]
            },
        )

    def test_only_lifecycle_materialized_accepted_fact_can_fill_a_value(
        self,
    ) -> None:
        fact = self.example_fact()
        Draft202012Validator(
            self.fact_schema,
            format_checker=FormatChecker(),
        ).validate(fact)
        self.validate_fact(fact)
        definition = next(
            item
            for item in self.value["parameter_catalog"]
            if item["field_id"] == "electrical.phase_inductance_h"
        )
        state = manager._requirement_state(definition, [fact])
        self.assertEqual("accepted_source_fact", state["status"])
        self.assertEqual(0.00005, state["value"])
        self.assertEqual([], state["blockers"])

    def test_accepted_fact_requires_independent_review_and_uncertainty(
        self,
    ) -> None:
        fact = self.example_fact()
        self.validate_fact(fact)
        definition = next(
            item
            for item in self.value["parameter_catalog"]
            if item["field_id"] == "electrical.phase_inductance_h"
        )
        state = manager._requirement_state(definition, [fact])
        self.assertEqual("accepted_source_fact", state["status"])
        self.assertEqual(0.00005, state["value"])
        same_reviewer = copy.deepcopy(fact)
        same_reviewer["review"]["reviewer"]["actor_id"] = (
            "test-extractor"
        )
        with self.assertRaisesRegex(
            manager.PlantEvidenceLedgerError,
            "not independent",
        ):
            self.validate_fact(same_reviewer)
        unknown = copy.deepcopy(fact)
        unknown["evidence"]["uncertainty"] = {
            "class": "transcribed_display_resolution",
            "lower": 0.000006,
            "upper": -0.000006,
            "unit": "H",
            "coverage_probability": 1.0,
        }
        with self.assertRaisesRegex(
            manager.PlantEvidenceLedgerError,
            "inverted uncertainty",
        ):
            self.validate_fact(unknown)

    def test_wrong_source_hash_model_or_family_source_denies(self) -> None:
        fact = self.example_fact()
        wrong_hash = copy.deepcopy(fact)
        wrong_hash["provenance"]["file_sha256"] = "0" * 64
        wrong_hash["fact_id"] = manager.expected_fact_id(wrong_hash)
        with self.assertRaisesRegex(
            manager.PlantEvidenceLedgerError,
            "SHA-256 mismatch",
        ):
            self.validate_fact(wrong_hash)

        wrong_model = copy.deepcopy(fact)
        target_model = next(
            item
            for item in self.applicability["models"]
            if item["model"] == "CEM-25"
        )
        wrong_model["model_identity"] = {
            "model_key": target_model["model_key"],
            "series": target_model["series"],
            "model": target_model["model"],
            "package_revision": target_model["package_revision"],
        }
        wrong_model["fact_id"] = manager.expected_fact_id(wrong_model)
        with self.assertRaisesRegex(
            manager.PlantEvidenceLedgerError,
            "candidate table/model binding mismatch",
        ):
            self.validate_fact(wrong_model)

    def test_unit_conversion_shape_and_fit_promotion_mutations_deny(
        self,
    ) -> None:
        conversion = self.example_fact()
        conversion["observation"]["normalized_value"] = 0.62
        conversion["fact_id"] = manager.expected_fact_id(conversion)
        with self.assertRaisesRegex(
            manager.PlantEvidenceLedgerError,
            "conversion mismatch",
        ):
            self.validate_fact(conversion)

        shape = self.example_fact()
        shape["target"] = {
            "requirement_kind": "operating_envelope",
            "domain": "operating_envelope",
            "name": "supply_voltage_v",
            "canonical_unit": "V",
        }
        shape["observation"]["normalized_unit"] = "V"
        shape["observation"]["source_unit"] = "V"
        shape["fact_id"] = manager.expected_fact_id(shape)
        with self.assertRaisesRegex(
            manager.PlantEvidenceLedgerError,
            "requires range",
        ):
            self.validate_fact(shape)

        fitted = self.example_fact()
        fitted["evidence"]["class"] = "fitted_identification"
        fitted["evidence"]["extraction_method"] = "identification_fit"
        with self.assertRaisesRegex(
            manager.PlantEvidenceLedgerError,
            "source fact schema failure",
        ):
            self.validate_fact(fitted)

    def test_digest_summary_and_value_leak_mutations_deny(self) -> None:
        mutations = []
        digest = copy.deepcopy(self.value)
        digest["integrity"]["record_sha256"] = "0" * 64
        mutations.append((digest, "digest drift"))
        summary = copy.deepcopy(self.value)
        summary["summary"]["missing_parameter_requirement_count"] -= 1
        manager.set_digest(summary)
        mutations.append((summary, "summary drift"))
        leak = copy.deepcopy(self.value)
        leak["models"][0]["parameter_evidence"][0]["value"] = 1.0
        manager.set_digest(leak)
        mutations.append((leak, "value leakage"))
        for value, pattern in mutations:
            with self.subTest(pattern=pattern), self.assertRaisesRegex(
                manager.PlantEvidenceLedgerError,
                pattern,
            ):
                manager.validate(value, verify_sources=False)

    def test_failed_source_fact_generation_preserves_existing_output(
        self,
    ) -> None:
        fact = self.example_fact()
        fact["model_identity"]["model"] = "NOT-A-CATALOG-MODEL"
        fact["fact_id"] = manager.expected_fact_id(fact)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            facts = root / "facts"
            facts.mkdir()
            fact_path = facts / f"{fact['fact_id']}.json"
            fact_path.write_text(
                manager.canonical_json(fact),
                encoding="utf-8",
            )
            output = root / "ledger.json"
            output.write_text("sentinel\n", encoding="utf-8")
            old_directory = manager.FACT_DIRECTORY
            old_output = manager.OUTPUT
            try:
                manager.FACT_DIRECTORY = facts
                manager.OUTPUT = output
                with self.assertRaises(
                    manager.PlantEvidenceLedgerError
                ):
                    manager.check_or_write(check=False)
            finally:
                manager.FACT_DIRECTORY = old_directory
                manager.OUTPUT = old_output
            self.assertEqual(
                "sentinel\n",
                output.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
