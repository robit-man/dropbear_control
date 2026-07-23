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

from myactuator_lib import protocol_applicability
from myactuator_lib import protocol_applicability_decision
from myactuator_lib.protocol_applicability import (
    ProtocolAdmissionReason,
    ProtocolApplicabilityError,
    ProtocolApplicabilityRegistry,
    ProtocolApplicabilitySelection,
)


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/generate_protocol_applicability_registry.py"
OUTPUT = (
    ROOT / "generated/myactuator/protocol_applicability/registry.json"
)
SCHEMA = (
    ROOT / "schemas/myactuator-protocol-applicability-registry.schema.json"
)

spec = importlib.util.spec_from_file_location(
    "protocol_applicability_generator_test_module", TOOL
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class ProtocolApplicabilityRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = json.loads(OUTPUT.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        cls.registry = ProtocolApplicabilityRegistry.load()
        cls.occurrences = {
            item["occurrence_id"]: item
            for item in cls.value["document_file_occurrences"]
        }

    def x_model(self) -> dict:
        return next(
            item for item in self.value["models"] if item["model"] == "X12-320"
        )

    def selection(self) -> ProtocolApplicabilitySelection:
        model = self.x_model()
        occurrence = next(
            self.occurrences[identifier]
            for identifier in model["candidate_protocol_occurrence_ids"]
            if self.occurrences[identifier]["source_claim"]["revision"] == "V4.4"
        )
        return ProtocolApplicabilitySelection(
            registry_generation_sha256=self.registry.generation_sha256,
            model_key=model["model_key"],
            series=model["series"],
            model=model["model"],
            protocol_occurrence_id=occurrence["occurrence_id"],
            hardware_revision="drive-v3-rev-a",
            drive_firmware="fw-2026.04.25",
            protocol_revision="V4.4",
            transport="classic_can",
            control_mode="torque-closed-loop-0xA1",
            installed_unit_id="dropbear-left-knee-unit-01",
        )

    def accepted_decision(self) -> dict:
        model = self.x_model()
        occurrence = next(
            self.occurrences[identifier]
            for identifier in model["candidate_protocol_occurrence_ids"]
            if self.occurrences[identifier]["source_claim"]["revision"] == "V4.4"
            and "CAN BUS" in self.occurrences[identifier]["file_name"]
        )
        package = next(
            item
            for item in self.value["document_packages"]
            if item["package_id"] == occurrence["package_id"]
        )
        value = protocol_applicability_decision.template(
            model,
            occurrence,
            package,
            hardware_revision="drive-v3-rev-a",
            drive_firmware="fw-2026.04.25",
            installed_unit_id="dropbear-left-knee-unit-01",
            transport="classic_can",
            control_mode="torque-closed-loop-0xA1",
        )
        value["record_state"] = "submitted"
        value["evidence"] = {
            "submitter_id": "capture-operator-alpha",
            "inventory": {
                "artifact_ref": "evidence/u0-inventory.json",
                "artifact_sha256": "1" * 64,
                "entry_id": "dropbear-left-knee-unit-01",
            },
            "source_review": {
                "reviewer_id": "source-reviewer-beta",
                "reviewed_at_utc": "2026-07-23T01:00:00Z",
                "locator": "V4.4 cover and command table A1",
                "evidence_refs": ["evidence/source-review.pdf"],
            },
            "capture": {
                "observation_class": "command_response",
                "manifest_ref": "evidence/capture-manifest.json",
                "manifest_sha256": "2" * 64,
                "trace_sha256": "3" * 64,
                "observed_at_utc": "2026-07-23T02:00:00Z",
            },
            "rationale": (
                "Exact installed tuple returned the source-defined A1 response."
            ),
            "evidence_refs": [
                "evidence/u0-inventory.json",
                "evidence/capture-manifest.json",
            ],
        }
        value["review"] = {
            "status": "accepted",
            "reviewer_id": "decision-reviewer-gamma",
            "organization_or_team": "independent-controls-lab",
            "independence_attested": True,
            "reviewed_at_utc": "2026-07-23T03:00:00Z",
            "decision_note": (
                "Source, inventory, and command-response identities agree."
            ),
            "signature_evidence_refs": ["evidence/review-signature.txt"],
        }
        value["disposition"] = "accept_applicability"
        value["applicability_established"] = True
        protocol_applicability_decision.set_digest(value)
        protocol_applicability_decision.validate(
            value,
            model,
            occurrence,
            package,
        )
        return value

    def test_schema_and_tracked_registry_are_exact_complete_and_zero_acceptance(
        self,
    ) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.value)
        manager.validate(copy.deepcopy(self.value))
        self.assertEqual(44, self.registry.model_count)
        self.assertEqual(9, self.registry.package_count)
        self.assertEqual(32, self.registry.file_occurrence_count)
        self.assertEqual(0, self.registry.accepted_applicability_count)
        self.assertEqual(
            {
                "accepted_applicability_count": 0,
                "accepted_model_count": 0,
                "candidate_model_package_relationship_count": 72,
                "candidate_model_protocol_relationship_count": 83,
                "document_file_occurrence_count": 32,
                "document_package_count": 9,
                "model_count": 44,
                "source_claim_scope_counts": {
                    "drive_manual": 3,
                    "fieldbus_protocol": 3,
                    "motor_motion_protocol": 7,
                    "product_manual": 15,
                    "sensor_interface": 3,
                    "setup_manual": 1,
                },
                "supported_model_count": 0,
                "unique_document_file_count": 23,
            },
            self.value["summary"],
        )
        self.assertFalse(self.value["support_granted"])
        self.assertFalse(self.value["physical_motion_authority"])

    def test_all_32_occurrences_are_partitioned_and_duplicate_bytes_survive(
        self,
    ) -> None:
        listed = [
            identifier
            for package in self.value["document_packages"]
            for identifier in package["file_occurrence_ids"]
        ]
        self.assertEqual(32, len(listed))
        self.assertEqual(32, len(set(listed)))
        self.assertEqual(set(self.occurrences), set(listed))
        by_hash = Counter(
            item["file_sha256"]
            for item in self.value["document_file_occurrences"]
        )
        self.assertEqual(
            3,
            by_hash[
                "15731a29c60771f0066fa0b2c7a7609de76edc53fbc8757035d2389d7a5dc3d2"
            ],
        )
        duplicate = [
            item
            for item in self.value["document_file_occurrences"]
            if item["file_sha256"]
            == "15731a29c60771f0066fa0b2c7a7609de76edc53fbc8757035d2389d7a5dc3d2"
        ]
        self.assertEqual(3, len({item["occurrence_id"] for item in duplicate}))
        self.assertEqual(
            {"RH", "CEM", "RMD-H"},
            {item["series"] for item in duplicate},
        )

    def test_protocol_sensor_and_manual_scopes_cannot_alias(self) -> None:
        scopes = Counter(
            item["source_claim"]["document_scope"]
            for item in self.value["document_file_occurrences"]
        )
        self.assertEqual(manager.EXPECTED_SCOPE_COUNTS, dict(scopes))
        sensors = [
            item
            for item in self.value["document_file_occurrences"]
            if item["source_claim"]["document_scope"] == "sensor_interface"
        ]
        self.assertEqual(3, len(sensors))
        self.assertTrue(
            all(
                item["source_claim"]["command_scope"]
                == "sensor_electrical_interface"
                and not item["source_claim"]["transports"]
                and not item["source_claim"]["applicability_authority"]
                for item in sensors
            )
        )
        candidate_ids = {
            identifier
            for model in self.value["models"]
            for identifier in model["candidate_protocol_occurrence_ids"]
        }
        self.assertTrue(
            all(item["occurrence_id"] not in candidate_ids for item in sensors)
        )

    def test_rmd_x_generation_ambiguity_is_preserved_without_fallback(self) -> None:
        model = self.x_model()
        sources = self.registry.candidate_sources(
            model["model_key"], series="RMD-X", model="X12-320"
        )
        self.assertEqual(
            [
                "X-V2-protocol-manual",
                "X-V3-protocol-manual",
                "X-V4-protocol-manual",
            ],
            [item["document_set"] for item in sources["packages"]],
        )
        self.assertEqual(
            ["V4.2", "V4.2", "V4.4", "V2.0-260425"],
            [
                item["source_claim"]["revision"]
                for item in sources["protocols"]
            ],
        )
        self.assertTrue(
            all(not item["applicability_authority"] for item in sources["packages"])
        )

    def test_fl_and_flo_receive_separate_manual_sets_and_no_protocol(self) -> None:
        for model_name, document_set in (
            ("FL-38-08", "FL-user-manual"),
            ("FLO-50-15", "FLO-user-manual"),
        ):
            model = next(
                item for item in self.value["models"] if item["model"] == model_name
            )
            sources = self.registry.candidate_sources(
                model["model_key"], series="FL-FLO", model=model_name
            )
            self.assertEqual(
                [document_set],
                [item["document_set"] for item in sources["packages"]],
            )
            self.assertEqual([], sources["protocols"])
            self.assertIn(
                "candidate_motor_control_protocol_source_missing",
                model["blockers"],
            )

    def test_exact_complete_selection_still_denies_without_decision(self) -> None:
        decision = self.registry.admit(self.selection())
        self.assertFalse(decision.allowed)
        self.assertEqual(
            ProtocolAdmissionReason.NO_ACCEPTED_APPLICABILITY,
            decision.reason,
        )
        self.assertIn(
            "exact_tuple_has_no_accepted_applicability_decision",
            decision.blockers,
        )
        with self.assertRaises(protocol_applicability.ProtocolApplicabilityDenied):
            decision.require()

    def test_stale_model_source_revision_and_transport_deny_distinctly(self) -> None:
        base = self.selection()
        mutations = []
        stale = copy.deepcopy(base)
        object.__setattr__(stale, "registry_generation_sha256", "0" * 64)
        mutations.append(
            (stale, ProtocolAdmissionReason.STALE_REGISTRY_GENERATION)
        )
        identity = copy.deepcopy(base)
        object.__setattr__(identity, "model", "X6-60")
        mutations.append(
            (identity, ProtocolAdmissionReason.MODEL_IDENTITY_MISMATCH)
        )
        source = copy.deepcopy(base)
        foreign = next(
            item["candidate_protocol_occurrence_ids"][0]
            for item in self.value["models"]
            if item["series"] == "RMD-H"
        )
        object.__setattr__(source, "protocol_occurrence_id", foreign)
        mutations.append(
            (source, ProtocolAdmissionReason.PROTOCOL_SOURCE_NOT_CANDIDATE)
        )
        revision = copy.deepcopy(base)
        object.__setattr__(revision, "protocol_revision", "V4.2")
        mutations.append(
            (revision, ProtocolAdmissionReason.PROTOCOL_IDENTITY_MISMATCH)
        )
        transport = copy.deepcopy(base)
        object.__setattr__(transport, "transport", "ethercat")
        mutations.append(
            (transport, ProtocolAdmissionReason.TRANSPORT_NOT_DECLARED)
        )
        for selection, reason in mutations:
            with self.subTest(reason=reason):
                self.assertEqual(reason, self.registry.admit(selection).reason)

    def test_non_exact_latest_or_unknown_tuple_fields_are_rejected(self) -> None:
        fields = (
            "hardware_revision",
            "drive_firmware",
            "control_mode",
            "installed_unit_id",
        )
        for field in fields:
            values = self.selection().__dict__.copy()
            values[field] = "latest"
            with self.subTest(field=field), self.assertRaises(
                ProtocolApplicabilityError
            ):
                ProtocolApplicabilitySelection(**values)

    def test_digest_count_scope_relation_and_authority_mutations_deny(self) -> None:
        mutations = []
        digest = copy.deepcopy(self.value)
        digest["integrity"]["record_sha256"] = "0" * 64
        mutations.append(digest)
        count = copy.deepcopy(self.value)
        count["summary"]["document_file_occurrence_count"] = 31
        manager.set_digest(count)
        mutations.append(count)
        sensor = copy.deepcopy(self.value)
        sensor_row = next(
            item
            for item in sensor["document_file_occurrences"]
            if item["source_claim"]["document_scope"] == "sensor_interface"
        )
        sensor_row["source_claim"]["command_scope"] = "motor_motion_control"
        manager.set_digest(sensor)
        mutations.append(sensor)
        cross_package = copy.deepcopy(self.value)
        cross_package["models"][0]["candidate_protocol_occurrence_ids"].append(
            next(
                item["candidate_protocol_occurrence_ids"][0]
                for item in cross_package["models"]
                if item["series"] == "RMD-H"
            )
        )
        manager.set_digest(cross_package)
        mutations.append(cross_package)
        authority = copy.deepcopy(self.value)
        authority["support_granted"] = True
        manager.set_digest(authority)
        mutations.append(authority)
        unknown = copy.deepcopy(self.value)
        unknown["unexpected"] = True
        manager.set_digest(unknown)
        mutations.append(unknown)
        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                (manager.ProtocolApplicabilityRegistryError, ProtocolApplicabilityError)
            ):
                try:
                    manager.validate(value, verify_sources=False)
                except manager.ProtocolApplicabilityRegistryError:
                    raise
                ProtocolApplicabilityRegistry(
                    value,
                    copy.deepcopy(self.schema),
                )

    def test_reviewed_exact_tuple_can_admit_without_granting_motor_support(
        self,
    ) -> None:
        accepted = self.accepted_decision()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / f"{accepted['decision_id']}.json"
            path.write_bytes(
                protocol_applicability_decision.canonical_bytes(accepted)
            )
            original = manager.DECISION_DIRECTORY
            try:
                manager.DECISION_DIRECTORY = directory
                value = manager.build()
                manager.validate(value, decision_directory=directory)
            finally:
                manager.DECISION_DIRECTORY = original
            registry = ProtocolApplicabilityRegistry(
                value,
                copy.deepcopy(self.schema),
                decision_directory=directory,
            )
            base = self.selection().__dict__.copy()
            base["registry_generation_sha256"] = registry.generation_sha256
            selection = ProtocolApplicabilitySelection(**base)
            admission = registry.admit(selection)
            self.assertTrue(admission.allowed)
            self.assertEqual(ProtocolAdmissionReason.ALLOWED, admission.reason)
            self.assertEqual(accepted["decision_id"], admission.decision_id)
            self.assertFalse(admission.support_granted)
            self.assertFalse(admission.physical_motion_authority)
            admission.require()
            self.assertEqual(1, registry.accepted_applicability_count)
            model = next(
                item
                for item in value["models"]
                if item["model_key"] == selection.model_key
            )
            self.assertEqual("accepted", model["applicability_status"])
            self.assertEqual(
                [accepted["decision_id"]],
                model["accepted_decision_ids"],
            )
            wrong = base.copy()
            wrong["installed_unit_id"] = "dropbear-left-knee-unit-02"
            denied = registry.admit(ProtocolApplicabilitySelection(**wrong))
            self.assertFalse(denied.allowed)
            self.assertEqual(
                ProtocolAdmissionReason.NO_ACCEPTED_APPLICABILITY,
                denied.reason,
            )

    def test_listen_only_self_review_and_source_drift_cannot_accept(self) -> None:
        accepted = self.accepted_decision()
        mutations = []
        listen_only = copy.deepcopy(accepted)
        listen_only["evidence"]["capture"]["observation_class"] = "listen_only"
        protocol_applicability_decision.set_digest(listen_only)
        mutations.append(listen_only)
        self_review = copy.deepcopy(accepted)
        self_review["review"]["reviewer_id"] = self_review["evidence"][
            "submitter_id"
        ]
        protocol_applicability_decision.set_digest(self_review)
        mutations.append(self_review)
        source_drift = copy.deepcopy(accepted)
        source_drift["subject"]["protocol_file_sha256"] = "4" * 64
        source_drift["decision_id"] = (
            protocol_applicability_decision.decision_id_for(
                source_drift["subject"]
            )
        )
        protocol_applicability_decision.set_digest(source_drift)
        mutations.append(source_drift)
        model = self.x_model()
        occurrence = self.occurrences[
            accepted["subject"]["protocol_occurrence_id"]
        ]
        package = next(
            item
            for item in self.value["document_packages"]
            if item["package_id"] == occurrence["package_id"]
        )
        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                protocol_applicability_decision.ProtocolApplicabilityDecisionError
            ):
                protocol_applicability_decision.validate(
                    value,
                    model,
                    occurrence,
                    package,
                )

    def test_source_drift_revokes_and_failed_build_preserves_output(self) -> None:
        before = OUTPUT.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_files = {}
            for source_id, source in (
                protocol_applicability.DEFAULT_SOURCE_FILES.items()
            ):
                destination = root / f"{source_id}.tsv"
                destination.write_bytes(source.read_bytes())
                source_files[source_id] = destination
            source_files["documents_sha256"].write_bytes(b"tampered\n")
            with self.assertRaises(ProtocolApplicabilityError):
                ProtocolApplicabilityRegistry(
                    copy.deepcopy(self.value),
                    copy.deepcopy(self.schema),
                    source_files=source_files,
                )
        with tempfile.TemporaryDirectory() as temporary:
            bad_claims = Path(temporary) / "source_claims.tsv"
            bad_claims.write_text(
                manager.SOURCE_CLAIMS.read_text(encoding="utf-8").splitlines()[0]
                + "\n",
                encoding="utf-8",
            )
            original = manager.SOURCE_CLAIMS
            try:
                manager.SOURCE_CLAIMS = bad_claims
                with self.assertRaises(
                    manager.ProtocolApplicabilityRegistryError
                ):
                    manager.build()
            finally:
                manager.SOURCE_CLAIMS = original
        self.assertEqual(before, OUTPUT.read_bytes())


if __name__ == "__main__":
    unittest.main()
