from __future__ import annotations

import dataclasses
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from myactuator_lib.support import (
    ArtifactHash,
    CatalogIdentity,
    ConflictingRecordError,
    DenialCode,
    DependencyEvidence,
    DuplicateRecordError,
    EvidenceLevel,
    RegistryPolicy,
    SupportKey,
    SupportRecord,
    SupportRegistry,
    ValidationError,
)


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "assets" / "myactuator" / "catalog.tsv"
NOW = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)


def make_key(**changes: str) -> SupportKey:
    values = {
        "model": "X6-60",
        "hardware_revision": "rev-a",
        "drive_firmware": "fw-1.2.3",
        "protocol_version": "V4.4-260520",
        "transport": "classic-can-1mbps",
        "control_mode": "position-absolute",
    }
    values.update(changes)
    return SupportKey(**values)


def make_dependency(**changes: object) -> DependencyEvidence:
    values = {
        "dependency_id": "gateway-build",
        "evidence_level": EvidenceLevel.HIL,
        "required_level": EvidenceLevel.HIL,
        "source_ids": ("source:gateway-test-plan",),
        "evidence_ids": ("evidence:gateway-hil-001",),
        "valid_from_utc": NOW - timedelta(days=1),
        "stale_after_utc": NOW + timedelta(days=30),
        "valid_until_utc": NOW + timedelta(days=60),
    }
    values.update(changes)
    return DependencyEvidence(**values)


def make_record(**changes: object) -> SupportRecord:
    values = {
        "key": make_key(),
        "evidence_level": EvidenceLevel.HIL,
        "source_ids": ("source:tuple-test-plan",),
        "evidence_ids": ("evidence:tuple-hil-001",),
        "code_hashes": (ArtifactHash("host-code", "1" * 64),),
        "config_hashes": (ArtifactHash("robot-config", "2" * 64),),
        "valid_from_utc": NOW - timedelta(days=1),
        "stale_after_utc": NOW + timedelta(days=30),
        "valid_until_utc": NOW + timedelta(days=60),
        "capabilities": frozenset({"position-command", "status-read"}),
        "dependency_evidence": (make_dependency(),),
    }
    values.update(changes)
    return SupportRecord(**values)


def codes(decision: object) -> tuple[DenialCode, ...]:
    return decision.denial_codes


class ExactTupleTests(unittest.TestCase):
    def test_all_six_fields_participate_in_exact_identity(self) -> None:
        registry = SupportRegistry()
        record = make_record()
        registry.add_support_record(record)

        variants = {
            "model": "X6-61",
            "hardware_revision": "rev-b",
            "drive_firmware": "fw-1.2.4",
            "protocol_version": "V4.4-260521",
            "transport": "classic-can-500kbps",
            "control_mode": "speed",
        }
        for field_name, different_value in variants.items():
            with self.subTest(field=field_name):
                candidate = dataclasses.replace(record.key, **{field_name: different_value})
                decision = registry.query(
                    candidate,
                    "position-command",
                    powered=False,
                    now_utc=NOW,
                )
                self.assertFalse(decision.allowed)
                self.assertIn(DenialCode.NO_EXACT_SUPPORT_RECORD, codes(decision))

    def test_matching_is_case_sensitive_and_has_no_family_fallback(self) -> None:
        registry = SupportRegistry()
        registry.add_support_record(make_record())
        for candidate in (
            make_key(model="x6-60"),
            make_key(model="RMD-X"),
            make_key(drive_firmware="fw-1.2.3-hotfix"),
        ):
            decision = registry.query(
                candidate, "position-command", powered=False, now_utc=NOW
            )
            self.assertFalse(decision.allowed)
            self.assertEqual(
                decision.denial_codes, (DenialCode.NO_EXACT_SUPPORT_RECORD,)
            )

    def test_unknown_and_wildcard_tuple_values_are_rejected(self) -> None:
        invalid_values = (
            "",
            " unknown",
            "unknown",
            "UNSPECIFIED",
            "N/A",
            "any",
            "latest",
            "*",
            "fw-?",
            "fw-[12]",
            "4.x",
            "x.4",
            "fw-unknown-build",
            ">=1.2.3",
            "1.2.3||1.2.4",
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    make_key(drive_firmware=value)

    def test_a_real_model_name_containing_x_is_not_a_wildcard(self) -> None:
        self.assertEqual(make_key(model="X6-60").model, "X6-60")


class EvidenceModelTests(unittest.TestCase):
    def test_levels_are_distinct_and_strictly_ordered(self) -> None:
        levels = list(EvidenceLevel)
        self.assertEqual(
            levels,
            [
                EvidenceLevel.CATALOGED,
                EvidenceLevel.OFFLINE,
                EvidenceLevel.SIL,
                EvidenceLevel.BENCH,
                EvidenceLevel.HIL,
                EvidenceLevel.ROBOT_RELEASE,
            ],
        )
        self.assertEqual([int(level) for level in levels], list(range(6)))

    def test_higher_dependency_evidence_does_not_promote_record(self) -> None:
        registry = SupportRegistry(RegistryPolicy(EvidenceLevel.BENCH))
        record = make_record(evidence_level=EvidenceLevel.OFFLINE)
        registry.add_support_record(record)
        decision = registry.query(
            record.key,
            "position-command",
            powered=False,
            required_evidence=EvidenceLevel.HIL,
            now_utc=NOW,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.evidence_level, EvidenceLevel.OFFLINE)
        self.assertIn(DenialCode.REQUIRED_EVIDENCE_NOT_MET, codes(decision))

    def test_evidence_record_requires_provenance_hashes_and_capabilities(self) -> None:
        invalid_changes = (
            {"source_ids": ()},
            {"evidence_ids": ()},
            {"code_hashes": ()},
            {"config_hashes": ()},
            {"capabilities": frozenset()},
        )
        for changes in invalid_changes:
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    make_record(**changes)

    def test_duplicate_provenance_and_artifact_names_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            make_record(source_ids=("source:a", "source:a"))
        duplicate_hashes = (
            ArtifactHash("same", "1" * 64),
            ArtifactHash("same", "2" * 64),
        )
        with self.assertRaises(ValidationError):
            make_record(code_hashes=duplicate_hashes)

    def test_sha256_is_validated_and_canonicalized(self) -> None:
        artifact = ArtifactHash("code", "A" * 64)
        self.assertEqual(artifact.sha256, "a" * 64)
        for digest in ("a" * 63, "a" * 65, "z" * 64):
            with self.subTest(digest=digest):
                with self.assertRaises(ValidationError):
                    ArtifactHash("code", digest)

    def test_evidence_windows_must_be_ordered_utc(self) -> None:
        with self.assertRaises(ValidationError):
            make_record(valid_from_utc=NOW.replace(tzinfo=None))
        with self.assertRaises(ValidationError):
            make_record(valid_from_utc=NOW.astimezone(timezone(timedelta(hours=1))))
        with self.assertRaises(ValidationError):
            make_record(stale_after_utc=NOW - timedelta(days=2))
        with self.assertRaises(ValidationError):
            make_record(
                stale_after_utc=NOW + timedelta(days=2),
                valid_until_utc=NOW + timedelta(days=1),
            )


class CollisionTests(unittest.TestCase):
    def test_identical_support_record_is_rejected_as_duplicate(self) -> None:
        registry = SupportRegistry()
        record = make_record()
        registry.add_support_record(record)
        with self.assertRaises(DuplicateRecordError):
            registry.add_support_record(record)

    def test_same_key_with_different_evidence_is_rejected_as_conflict(self) -> None:
        registry = SupportRegistry()
        record = make_record()
        registry.add_support_record(record)
        conflicting = dataclasses.replace(
            record, evidence_ids=("evidence:tuple-hil-002",)
        )
        with self.assertRaises(ConflictingRecordError):
            registry.add_support_record(conflicting)

    def test_catalog_duplicate_and_conflict_are_rejected(self) -> None:
        identity = CatalogIdentity(
            "RMD-X",
            "X6-60",
            "260703",
            "https://example.invalid/x6-60.zip",
            "source:catalog",
        )
        registry = SupportRegistry()
        registry.add_catalog_identity(identity)
        with self.assertRaises(DuplicateRecordError):
            registry.add_catalog_identity(identity)
        with self.assertRaises(ConflictingRecordError):
            registry.add_catalog_identity(
                dataclasses.replace(identity, package_revision="260704")
            )


class QueryDecisionTests(unittest.TestCase):
    def test_capability_must_be_explicitly_declared(self) -> None:
        registry = SupportRegistry()
        record = make_record()
        registry.add_support_record(record)
        decision = registry.query(
            record.key, "torque-command", powered=False, now_utc=NOW
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.denial_codes, (DenialCode.CAPABILITY_NOT_DECLARED,))

    def test_valid_nonpowered_query_is_allowed(self) -> None:
        registry = SupportRegistry()
        record = make_record(evidence_level=EvidenceLevel.OFFLINE)
        registry.add_support_record(record)
        decision = registry.query(
            record.key,
            "status-read",
            powered=False,
            required_evidence=EvidenceLevel.OFFLINE,
            now_utc=NOW,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.denial_reasons, ())
        self.assertEqual(decision.evidence_level, EvidenceLevel.OFFLINE)

    def test_record_validity_and_staleness_have_explicit_denials(self) -> None:
        cases = (
            (
                make_record(valid_from_utc=NOW + timedelta(days=1)),
                NOW,
                DenialCode.EVIDENCE_NOT_YET_VALID,
            ),
            (
                make_record(stale_after_utc=NOW - timedelta(hours=1)),
                NOW,
                DenialCode.EVIDENCE_STALE,
            ),
            (
                make_record(
                    valid_from_utc=NOW - timedelta(days=3),
                    stale_after_utc=NOW - timedelta(days=2),
                    valid_until_utc=NOW - timedelta(days=1),
                ),
                NOW,
                DenialCode.EVIDENCE_EXPIRED,
            ),
        )
        for record, evaluated_at, expected in cases:
            with self.subTest(expected=expected):
                registry = SupportRegistry()
                registry.add_support_record(record)
                decision = registry.query(
                    record.key,
                    "status-read",
                    powered=False,
                    now_utc=evaluated_at,
                )
                self.assertFalse(decision.allowed)
                self.assertIn(expected, codes(decision))

    def test_boundaries_are_inclusive_and_one_microsecond_later_is_stale(self) -> None:
        record = make_record(stale_after_utc=NOW, valid_until_utc=NOW)
        registry = SupportRegistry()
        registry.add_support_record(record)
        at_boundary = registry.query(
            record.key, "status-read", powered=False, now_utc=NOW
        )
        after_boundary = registry.query(
            record.key,
            "status-read",
            powered=False,
            now_utc=NOW + timedelta(microseconds=1),
        )
        self.assertTrue(at_boundary.allowed)
        self.assertFalse(after_boundary.allowed)
        self.assertIn(DenialCode.EVIDENCE_STALE, codes(after_boundary))
        self.assertIn(DenialCode.EVIDENCE_EXPIRED, codes(after_boundary))

    def test_dependency_level_and_time_fail_closed_with_dependency_id(self) -> None:
        dependencies = (
            make_dependency(
                evidence_level=EvidenceLevel.OFFLINE,
                required_level=EvidenceLevel.SIL,
            ),
            make_dependency(
                dependency_id="future-dependency",
                valid_from_utc=NOW + timedelta(days=1),
                stale_after_utc=NOW + timedelta(days=2),
                valid_until_utc=NOW + timedelta(days=3),
            ),
            make_dependency(
                dependency_id="expired-dependency",
                valid_from_utc=NOW - timedelta(days=3),
                stale_after_utc=NOW - timedelta(days=2),
                valid_until_utc=NOW - timedelta(days=1),
            ),
        )
        record = make_record(dependency_evidence=dependencies)
        registry = SupportRegistry()
        registry.add_support_record(record)
        decision = registry.query(
            record.key, "status-read", powered=False, now_utc=NOW
        )
        self.assertFalse(decision.allowed)
        self.assertIn(DenialCode.DEPENDENCY_REQUIRED_EVIDENCE_NOT_MET, codes(decision))
        self.assertIn(DenialCode.DEPENDENCY_EVIDENCE_NOT_YET_VALID, codes(decision))
        self.assertIn(DenialCode.DEPENDENCY_EVIDENCE_STALE, codes(decision))
        self.assertIn(DenialCode.DEPENDENCY_EVIDENCE_EXPIRED, codes(decision))
        self.assertEqual(
            {reason.dependency_id for reason in decision.denial_reasons},
            {"gateway-build", "future-dependency", "expired-dependency"},
        )


class PoweredAuthorizationTests(unittest.TestCase):
    def test_powered_floor_can_only_be_a_hardware_evidence_level(self) -> None:
        for level in (
            EvidenceLevel.CATALOGED,
            EvidenceLevel.OFFLINE,
            EvidenceLevel.SIL,
        ):
            with self.subTest(level=level):
                with self.assertRaises(ValidationError):
                    RegistryPolicy(level)
        for level in (
            EvidenceLevel.BENCH,
            EvidenceLevel.HIL,
            EvidenceLevel.ROBOT_RELEASE,
        ):
            self.assertEqual(RegistryPolicy(level).minimum_powered_evidence, level)

    def test_cataloged_offline_and_sil_never_authorize_powered_actuation(self) -> None:
        for level in (
            EvidenceLevel.CATALOGED,
            EvidenceLevel.OFFLINE,
            EvidenceLevel.SIL,
        ):
            with self.subTest(level=level):
                registry = SupportRegistry(RegistryPolicy(EvidenceLevel.BENCH))
                record = make_record(evidence_level=level)
                registry.add_support_record(record)
                decision = registry.query(
                    record.key,
                    "position-command",
                    powered=True,
                    required_evidence=EvidenceLevel.CATALOGED,
                    now_utc=NOW,
                )
                self.assertFalse(decision.allowed)
                self.assertIn(DenialCode.POWERED_EVIDENCE_NOT_HARDWARE, codes(decision))

    def test_configurable_hardware_floor_is_enforced(self) -> None:
        bench_record = make_record(evidence_level=EvidenceLevel.BENCH)
        bench_registry = SupportRegistry(RegistryPolicy(EvidenceLevel.BENCH))
        bench_registry.add_support_record(bench_record)
        self.assertTrue(
            bench_registry.query(
                bench_record.key,
                "position-command",
                powered=True,
                now_utc=NOW,
            ).allowed
        )

        default_registry = SupportRegistry()
        default_registry.add_support_record(bench_record)
        denied = default_registry.query(
            bench_record.key,
            "position-command",
            powered=True,
            now_utc=NOW,
        )
        self.assertFalse(denied.allowed)
        self.assertIn(DenialCode.POWERED_EVIDENCE_BELOW_POLICY, codes(denied))

        release_registry = SupportRegistry(RegistryPolicy(EvidenceLevel.ROBOT_RELEASE))
        hil_record = make_record(evidence_level=EvidenceLevel.HIL)
        release_registry.add_support_record(hil_record)
        denied = release_registry.query(
            hil_record.key,
            "position-command",
            powered=True,
            now_utc=NOW,
        )
        self.assertFalse(denied.allowed)
        self.assertIn(DenialCode.POWERED_EVIDENCE_BELOW_POLICY, codes(denied))

    def test_default_hil_record_with_live_dependency_is_allowed(self) -> None:
        registry = SupportRegistry()
        record = make_record()
        registry.add_support_record(record)
        decision = registry.query(
            record.key, "position-command", powered=True, now_utc=NOW
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.denial_reasons, ())

    def test_powered_record_without_dependencies_is_explicitly_denied(self) -> None:
        registry = SupportRegistry()
        record = make_record(dependency_evidence=())
        registry.add_support_record(record)
        decision = registry.query(
            record.key, "position-command", powered=True, now_utc=NOW
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(
            decision.denial_codes,
            (DenialCode.POWERED_DEPENDENCY_EVIDENCE_MISSING,),
        )


class CatalogImportTests(unittest.TestCase):
    def test_real_catalog_loads_44_identities_and_zero_support_records(self) -> None:
        registry = SupportRegistry.from_catalog_tsv(CATALOG)
        self.assertEqual(registry.catalog_identity_count, 44)
        self.assertEqual(len({item.model for item in registry.catalog_identities}), 44)
        self.assertEqual(registry.support_record_count, 0)
        self.assertEqual(registry.support_records, ())
        self.assertTrue(
            all(
                item.evidence_level is EvidenceLevel.CATALOGED
                and item.supports_powered_actuation is False
                for item in registry.catalog_identities
            )
        )

    def test_all_44_catalog_models_remain_denied_for_powered_actuation(self) -> None:
        registry = SupportRegistry.from_catalog_tsv(CATALOG)
        denied_models = []
        for identity in registry.catalog_identities:
            key = make_key(model=identity.model)
            decision = registry.query(
                key, "position-command", powered=True, now_utc=NOW
            )
            self.assertFalse(decision.allowed)
            self.assertEqual(
                decision.denial_codes,
                (
                    DenialCode.CATALOG_IDENTITY_ONLY,
                    DenialCode.NO_EXACT_SUPPORT_RECORD,
                ),
            )
            denied_models.append(identity.model)
        self.assertEqual(len(denied_models), 44)
        self.assertEqual(registry.support_record_count, 0)

    def test_catalog_import_does_not_override_an_exact_support_record(self) -> None:
        registry = SupportRegistry.from_catalog_tsv(CATALOG)
        record = make_record()
        registry.add_support_record(record)
        self.assertEqual(registry.catalog_identity_count, 44)
        self.assertEqual(registry.support_record_count, 1)
        self.assertEqual(
            registry.query(
                record.key, "position-command", powered=True, now_utc=NOW
            ).evidence_level,
            EvidenceLevel.HIL,
        )

    def test_catalog_schema_is_strict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.tsv"
            path.write_text(
                "series\tmodel\tpackage_revision\nRMD-X\tX6-60\t260703\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValidationError):
                SupportRegistry.from_catalog_tsv(path)


if __name__ == "__main__":
    unittest.main()
