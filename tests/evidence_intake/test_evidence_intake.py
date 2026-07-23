from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "generate_evidence_intake",
    ROOT / "tools/generate_evidence_intake.py",
)
assert SPEC and SPEC.loader
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)

MANIFEST = ROOT / "generated/myactuator/evidence_intake/manifest.json"
PACKETS = ROOT / "generated/myactuator/evidence_intake/packets"
INDEX = ROOT / "generated/myactuator/evidence_intake/index.html"


class EvidenceIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.packets = {
            entry["packet_id"]: json.loads(
                (PACKETS / f"{entry['packet_id']}.json").read_text(
                    encoding="utf-8"
                )
            )
            for entry in cls.value["packets"]
        }
        cls.campaign = json.loads(
            (
                ROOT
                / "generated/myactuator/cad/campaign/campaign.json"
            ).read_text(encoding="utf-8")
        )
        cls.ledger = json.loads(
            (
                ROOT
                / "generated/myactuator/plant/evidence_ledger/ledger.json"
            ).read_text(encoding="utf-8")
        )
        cls.spec_candidates = json.loads(
            (
                ROOT
                / "generated/myactuator/plant/spec_candidates/registry.json"
            ).read_text(encoding="utf-8")
        )

    def test_schemas_manifest_digest_sources_and_exact_summary(self) -> None:
        for path in (manager.PACKET_SCHEMA, manager.MANIFEST_SCHEMA):
            Draft202012Validator.check_schema(
                json.loads(path.read_text(encoding="utf-8"))
            )
        manager.validate_manifest(self.value, packets=self.packets)
        self.assertEqual(
            {
                "packet_count": 97,
                "cad_packet_count": 53,
                "plant_packet_count": 44,
                "ready_packet_count": 85,
                "blocked_packet_count": 12,
                "task_count": 2361,
                "cad_task_count": 689,
                "plant_task_count": 1672,
                "assigned_packet_count": 0,
                "accepted_packet_count": 0,
                "physical_action_permitted_count": 0,
            },
            self.value["summary"],
        )
        self.assertEqual(manager.global_source_records(), self.value["sources"])
        manager.generate(check=True)

    def test_all_53_cad_packets_preserve_questions_lanes_and_sources(self) -> None:
        packets = [
            packet
            for packet in self.packets.values()
            if packet["packet_kind"] == "cad_semantic_review"
        ]
        by_subject = {
            packet["subject"]["subject_id"]: packet for packet in packets
        }
        self.assertEqual(
            {
                row["configuration_id"]
                for row in self.campaign["configurations"]
            },
            set(by_subject),
        )
        self.assertEqual(
            41,
            sum(
                packet["workflow"]["readiness"] == "ready_for_review"
                for packet in packets
            ),
        )
        self.assertEqual(
            12,
            sum(
                packet["workflow"]["readiness"]
                == "source_or_partition_needed"
                for packet in packets
            ),
        )
        expected_questions = [
            row["question_id"] for row in self.campaign["question_catalog"]
        ]
        for configuration in self.campaign["configurations"]:
            packet = by_subject[configuration["configuration_id"]]
            self.assertEqual(
                configuration["variant_id"],
                packet["subject"]["variant_id"],
            )
            self.assertEqual(
                expected_questions,
                [task["task_id"] for task in packet["tasks"]],
            )
            self.assertTrue(
                all(
                    task["response"] is None
                    and not task["response_evidence_refs"]
                    and not task["candidate_evidence_refs"]
                    for task in packet["tasks"]
                )
            )
            kinds = {
                binding["source_kind"]
                for binding in packet["source_bindings"]
            }
            self.assertTrue(
                {"vendor_step", "review_packet", "review_image"} <= kinds
            )

    def test_all_44_plant_packets_preserve_1672_exact_requirements(self) -> None:
        packets = [
            packet
            for packet in self.packets.values()
            if packet["packet_kind"] == "plant_source_extraction"
        ]
        by_subject = {
            packet["subject"]["subject_id"]: packet for packet in packets
        }
        self.assertEqual(
            {row["model_key"] for row in self.ledger["models"]},
            set(by_subject),
        )
        manual_ids = {
            row["document_occurrence_id"]
            for row in self.ledger["candidate_product_manuals"]
        }
        candidate_tables = {
            row["model_identity"]["model_key"]: row
            for row in self.spec_candidates["model_tables"]
        }
        referenced_candidate_ids = set()
        for model in self.ledger["models"]:
            packet = by_subject[model["model_key"]]
            expected = [
                *model["parameter_evidence"],
                *model["operating_envelope_evidence"],
            ]
            self.assertEqual(38, len(packet["tasks"]))
            self.assertEqual(
                [row["field_id"] for row in expected],
                [task["task_id"] for task in packet["tasks"]],
            )
            self.assertEqual(
                [row["expected_unit"] for row in expected],
                [task["canonical_unit"] for task in packet["tasks"]],
            )
            self.assertEqual(
                set(model["candidate_product_manual_occurrence_ids"]),
                {
                    binding["occurrence_id"]
                    for binding in packet["source_bindings"]
                    if binding["source_kind"] == "vendor_pdf"
                },
            )
            self.assertTrue(
                {
                    binding["occurrence_id"]
                    for binding in packet["source_bindings"]
                    if binding["source_kind"] == "vendor_pdf"
                }
                <= manual_ids
            )
            registry_bindings = [
                binding
                for binding in packet["source_bindings"]
                if binding["source_kind"]
                == "plant_spec_candidate_registry"
            ]
            self.assertEqual(1, len(registry_bindings))
            self.assertEqual(
                candidate_tables[model["model_key"]]["table_id"],
                registry_bindings[0]["occurrence_id"],
            )
            candidate_target = {
                candidate["candidate_id"]: candidate["mapping"][
                    "target_field_id"
                ]
                for candidate in candidate_tables[model["model_key"]][
                    "candidates"
                ]
                if candidate["mapping"]["target_field_id"] is not None
            }
            packet_refs = {
                candidate_id
                for task in packet["tasks"]
                for candidate_id in task["candidate_evidence_refs"]
            }
            self.assertEqual(set(candidate_target), packet_refs)
            for task in packet["tasks"]:
                self.assertEqual(
                    {
                        identifier
                        for identifier, target in candidate_target.items()
                        if target == task["task_id"]
                    },
                    set(task["candidate_evidence_refs"]),
                )
            referenced_candidate_ids.update(packet_refs)
        self.assertEqual(406, len(referenced_candidate_ids))

    def test_every_bound_local_source_is_present_and_hash_exact(self) -> None:
        for packet in self.packets.values():
            manager.validate_packet(packet)
            for binding in packet["source_bindings"]:
                path = ROOT / binding["local_path"]
                self.assertTrue(path.is_file())
                self.assertEqual(
                    binding["sha256"],
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )

    def test_draft_response_source_digest_and_authority_mutations_deny(self) -> None:
        baseline = next(iter(self.packets.values()))
        mutations = []

        response = copy.deepcopy(baseline)
        response["tasks"][0]["response"] = "fabricated"
        manager.set_digest(response)
        mutations.append((response, False))

        source = copy.deepcopy(baseline)
        source["source_bindings"][0]["sha256"] = "a" * 64
        manager.set_digest(source)
        mutations.append((source, True))

        task = copy.deepcopy(baseline)
        task["tasks"].pop()
        manager.set_digest(task)
        mutations.append((task, False))

        support = copy.deepcopy(baseline)
        support["support_granted"] = True
        manager.set_digest(support)
        mutations.append((support, False))

        digest = copy.deepcopy(baseline)
        digest["integrity"]["record_sha256"] = "0" * 64
        mutations.append((digest, False))

        for mutation, verify_sources in mutations:
            with self.subTest(
                mutation=mutation["integrity"]["record_sha256"][:8]
            ), self.assertRaises(manager.EvidenceIntakeError):
                manager.validate_packet(
                    mutation,
                    verify_sources=verify_sources,
                )

    def test_failed_input_build_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "evidence_intake"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("preserve\n", encoding="utf-8")
            bad_campaign = root / "campaign.json"
            bad_campaign.write_text("{}\n", encoding="utf-8")
            old_output = manager.OUTPUT_DIR
            old_campaign = manager.CAD_CAMPAIGN
            try:
                manager.OUTPUT_DIR = output
                manager.CAD_CAMPAIGN = bad_campaign
                with self.assertRaises(
                    (manager.EvidenceIntakeError, KeyError)
                ):
                    manager.generate(check=False)
            finally:
                manager.OUTPUT_DIR = old_output
                manager.CAD_CAMPAIGN = old_campaign
            self.assertEqual("preserve\n", sentinel.read_text(encoding="utf-8"))
            self.assertEqual([sentinel], list(output.iterdir()))

    def test_local_index_and_file_set_are_complete_and_network_free(self) -> None:
        text = INDEX.read_text(encoding="utf-8")
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)
        self.assertIn("Generated handoff only.", text)
        self.assertIn("2361", text)
        expected = {
            "manifest.json",
            "index.html",
            *{
                f"packets/{packet_id}.json"
                for packet_id in self.packets
            },
        }
        self.assertEqual(
            expected,
            {
                path.relative_to(manager.OUTPUT_DIR).as_posix()
                for path in manager.OUTPUT_DIR.rglob("*")
                if path.is_file()
            },
        )


if __name__ == "__main__":
    unittest.main()
