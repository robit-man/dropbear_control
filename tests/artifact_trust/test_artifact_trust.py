from __future__ import annotations

import dataclasses
import json
import unittest
from pathlib import Path

from myactuator_lib.artifact_trust import (
    ZERO_DIGEST,
    ArtifactCandidate,
    ArtifactDecision,
    ArtifactKind,
    ArtifactPolicy,
    ArtifactTrustEngine,
    AuditCommitReceipt,
    DurableCommitReceipt,
    KeyPurpose,
    PersistentState,
    RebootSnapshot,
    VerificationAlgorithm,
    VerificationAssertion,
    empty_persistent_state,
)


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests/artifact_trust/golden_artifact_trust.jsonl"
D1, D2, D3, D4, D5, D6, D7, D8, D9, DA, DB, DC = (
    character * 64 for character in "123456789abc"
)


def policy(**changes):
    value = ArtifactPolicy(
        platform_profile_selected=True,
        trust_anchor_present=True,
        verifier_bound=True,
        persistent_store_bound=True,
        durable_audit_bound=True,
        expected_kind=ArtifactKind.CONFIGURATION,
        expected_purpose=KeyPurpose.CONFIG_RELEASE,
        expected_algorithm=VerificationAlgorithm.ED25519,
        expected_key_id_digest=D5,
        expected_target_digest=D3,
        expected_envelope_schema_digest=D4,
        minimum_security_epoch=3,
    )
    return dataclasses.replace(value, **changes)


def candidate(**changes):
    value = ArtifactCandidate(
        transaction_digest=D1,
        artifact_digest=D2,
        target_digest=D3,
        envelope_schema_digest=D4,
        key_id_digest=D5,
        kind=ArtifactKind.CONFIGURATION,
        purpose=KeyPurpose.CONFIG_RELEASE,
        algorithm=VerificationAlgorithm.ED25519,
        deployment_sequence=11,
        security_epoch=3,
    )
    return dataclasses.replace(value, **changes)


def assertion(**changes):
    value = VerificationAssertion(
        assertion_digest=D6,
        adapter_id_digest=D7,
        artifact_digest=D2,
        target_digest=D3,
        envelope_schema_digest=D4,
        key_id_digest=D5,
        kind=ArtifactKind.CONFIGURATION,
        purpose=KeyPurpose.CONFIG_RELEASE,
        algorithm=VerificationAlgorithm.ED25519,
        signature_valid=True,
        chain_valid=True,
        key_revoked=False,
    )
    return dataclasses.replace(value, **changes)


def active(**changes):
    value = PersistentState(
        available=True,
        integrity_verified=True,
        active_artifact_digest=D9,
        committed_transaction_digest=DA,
        target_digest=D3,
        envelope_schema_digest=D4,
        key_id_digest=D5,
        kind=ArtifactKind.CONFIGURATION,
        purpose=KeyPurpose.CONFIG_RELEASE,
        algorithm=VerificationAlgorithm.ED25519,
        generation=5,
        deployment_sequence=10,
        security_epoch=3,
    )
    return dataclasses.replace(value, **changes)


def durable(**changes):
    value = DurableCommitReceipt(
        transaction_digest=D1,
        artifact_digest=D2,
        previous_generation=5,
        next_generation=6,
        deployment_sequence=11,
        security_epoch=3,
        write_completed=True,
        readback_verified=True,
    )
    return dataclasses.replace(value, **changes)


def audit(**changes):
    value = AuditCommitReceipt(
        transaction_digest=D1,
        artifact_digest=D2,
        committed_generation=6,
        audit_event_digest=DB,
        durable=True,
    )
    return dataclasses.replace(value, **changes)


def snapshot(**changes):
    value = RebootSnapshot(
        state=active(),
        durable_commit_verified=True,
        audit_commit_verified=True,
    )
    return dataclasses.replace(value, **changes)


def run_variant(variant: str) -> ArtifactDecision:
    selected_policy = policy()
    selected_candidate = candidate()
    selected_assertion: VerificationAssertion | None = assertion()
    selected_active = active()
    selected_durable = durable()
    selected_audit = audit()
    operation = "stage"
    pre_stage = False
    selected_snapshot = snapshot()

    if variant == "pass_stage":
        pass
    elif variant == "profile_not_selected":
        selected_policy = policy(platform_profile_selected=False)
    elif variant == "anchor_missing":
        selected_policy = policy(trust_anchor_present=False)
    elif variant == "verifier_missing":
        selected_policy = policy(verifier_bound=False)
    elif variant == "assertion_missing":
        selected_assertion = None
    elif variant == "signature_invalid":
        selected_assertion = assertion(signature_valid=False)
    elif variant == "chain_invalid":
        selected_assertion = assertion(chain_valid=False)
    elif variant == "key_revoked":
        selected_assertion = assertion(key_revoked=True)
    elif variant == "algorithm_mismatch":
        selected_assertion = assertion(
            algorithm=VerificationAlgorithm.ECDSA_P256_SHA256
        )
    elif variant == "key_id_mismatch":
        selected_assertion = assertion(key_id_digest=DC)
    elif variant == "purpose_mismatch":
        selected_assertion = assertion(
            purpose=KeyPurpose.CALIBRATION_RELEASE
        )
    elif variant == "kind_mismatch":
        selected_assertion = assertion(kind=ArtifactKind.CALIBRATION)
    elif variant == "target_mismatch":
        selected_assertion = assertion(target_digest=DC)
    elif variant == "digest_mismatch":
        selected_assertion = assertion(artifact_digest=DC)
    elif variant == "envelope_mismatch":
        selected_assertion = assertion(envelope_schema_digest=DC)
    elif variant == "persistent_unavailable":
        selected_active = active(available=False)
    elif variant == "persistent_untrusted":
        selected_active = active(integrity_verified=False)
    elif variant == "security_epoch_rollback":
        selected_candidate = candidate(security_epoch=2)
    elif variant == "deployment_sequence_rollback":
        selected_candidate = candidate(deployment_sequence=9)
    elif variant == "duplicate_version_conflict":
        selected_candidate = candidate(deployment_sequence=10)
    elif variant == "invalid_request":
        selected_candidate = candidate(transaction_digest=ZERO_DIGEST)
    elif variant == "stage_occupied":
        pre_stage = True
        selected_candidate = candidate(
            transaction_digest=DC, deployment_sequence=12
        )
    elif variant == "pass_commit":
        operation, pre_stage = "commit", True
    elif variant == "commit_without_stage":
        operation = "commit"
    elif variant == "commit_transaction_mismatch":
        operation, pre_stage = "commit_mismatch", True
    elif variant == "durable_write_incomplete":
        operation, pre_stage = "commit", True
        selected_durable = durable(write_completed=False)
    elif variant == "durable_readback_missing":
        operation, pre_stage = "commit", True
        selected_durable = durable(readback_verified=False)
    elif variant == "durable_transaction_mismatch":
        operation, pre_stage = "commit", True
        selected_durable = durable(transaction_digest=DC)
    elif variant == "durable_artifact_mismatch":
        operation, pre_stage = "commit", True
        selected_durable = durable(artifact_digest=DC)
    elif variant == "durable_sequence_mismatch":
        operation, pre_stage = "commit", True
        selected_durable = durable(deployment_sequence=12)
    elif variant == "durable_epoch_mismatch":
        operation, pre_stage = "commit", True
        selected_durable = durable(security_epoch=4)
    elif variant == "previous_generation_mismatch":
        operation, pre_stage = "commit", True
        selected_durable = durable(previous_generation=4)
    elif variant == "next_generation_mismatch":
        operation, pre_stage = "commit", True
        selected_durable = durable(next_generation=7)
    elif variant == "audit_adapter_missing":
        operation, pre_stage = "commit", True
        selected_policy = policy(durable_audit_bound=False)
    elif variant == "audit_not_durable":
        operation, pre_stage = "commit", True
        selected_audit = audit(durable=False)
    elif variant == "audit_transaction_mismatch":
        operation, pre_stage = "commit", True
        selected_audit = audit(transaction_digest=DC)
    elif variant == "audit_artifact_mismatch":
        operation, pre_stage = "commit", True
        selected_audit = audit(artifact_digest=DC)
    elif variant == "audit_generation_mismatch":
        operation, pre_stage = "commit", True
        selected_audit = audit(committed_generation=7)
    elif variant == "audit_digest_missing":
        operation, pre_stage = "commit", True
        selected_audit = audit(audit_event_digest=ZERO_DIGEST)
    elif variant == "pass_abort":
        operation, pre_stage = "abort", True
    elif variant == "abort_without_stage":
        operation = "abort"
    elif variant == "abort_transaction_mismatch":
        operation, pre_stage = "abort_mismatch", True
    elif variant == "pass_restore":
        operation = "restore"
    elif variant == "restore_integrity_missing":
        operation = "restore"
        selected_snapshot = snapshot(
            state=active(integrity_verified=False)
        )
    elif variant == "restore_durable_missing":
        operation = "restore"
        selected_snapshot = snapshot(durable_commit_verified=False)
    elif variant == "restore_audit_missing":
        operation = "restore"
        selected_snapshot = snapshot(audit_commit_verified=False)
    elif variant == "restore_epoch_rollback":
        operation = "restore"
        selected_snapshot = snapshot(state=active(security_epoch=2))
    elif variant == "restore_digest_missing":
        operation = "restore"
        selected_snapshot = snapshot(
            state=active(active_artifact_digest=ZERO_DIGEST)
        )
    else:
        raise AssertionError(f"unknown corpus variant: {variant}")

    engine = ArtifactTrustEngine(selected_policy, selected_active)
    if pre_stage:
        result = engine.stage(candidate(), assertion())
        assert result.code == ArtifactDecision.PASS_STAGED
    if operation == "stage":
        result = engine.stage(selected_candidate, selected_assertion)
    elif operation == "commit":
        result = engine.commit(D1, selected_durable, selected_audit)
    elif operation == "commit_mismatch":
        result = engine.commit(DC, selected_durable, selected_audit)
    elif operation == "abort":
        result = engine.abort(D1)
    elif operation == "abort_mismatch":
        result = engine.abort(DC)
    elif operation == "restore":
        result = engine.restore(selected_snapshot)
    else:
        raise AssertionError(operation)
    assert result.motion_authorized is False
    return result.code


class ArtifactTrustTests(unittest.TestCase):
    def records(self):
        return [
            json.loads(line)
            for line in CORPUS.read_text().splitlines()
            if line
        ]

    def test_shared_corpus_has_exact_unique_python_results(self):
        records = self.records()
        self.assertEqual(48, len(records))
        self.assertEqual(
            len(records), len({row["variant"] for row in records})
        )
        for record in records:
            with self.subTest(record["variant"]):
                self.assertEqual(
                    ArtifactDecision[record["expected_code"]],
                    run_variant(record["variant"]),
                )

    def test_stage_never_changes_active_and_commit_failures_are_retryable(self):
        engine = ArtifactTrustEngine(policy(), active())
        before = engine.active_state
        staged = engine.stage(candidate(), assertion())
        self.assertEqual(ArtifactDecision.PASS_STAGED, staged.code)
        self.assertEqual(before, engine.active_state)
        self.assertFalse(staged.active_changed)
        failed = engine.commit(
            D1, durable(readback_verified=False), audit()
        )
        self.assertEqual(
            ArtifactDecision.DURABLE_RECEIPT_INVALID, failed.code
        )
        self.assertEqual(before, engine.active_state)
        self.assertEqual(candidate(), engine.staged_candidate)
        committed = engine.commit(D1, durable(), audit())
        self.assertEqual(ArtifactDecision.PASS_COMMITTED, committed.code)
        self.assertTrue(committed.active_changed)
        self.assertIsNone(engine.staged_candidate)
        self.assertEqual(6, engine.active_state.generation)
        self.assertEqual(D2, engine.active_state.active_artifact_digest)
        self.assertEqual(D1, engine.active_state.committed_transaction_digest)

    def test_abort_preserves_active_and_requires_exact_transaction(self):
        engine = ArtifactTrustEngine(policy(), active())
        before = engine.active_state
        engine.stage(candidate(), assertion())
        denied = engine.abort(DC)
        self.assertEqual(ArtifactDecision.TRANSACTION_MISMATCH, denied.code)
        self.assertIsNotNone(engine.staged_candidate)
        passed = engine.abort(D1)
        self.assertEqual(ArtifactDecision.PASS_ABORTED, passed.code)
        self.assertEqual(before, engine.active_state)
        self.assertIsNone(engine.staged_candidate)

    def test_reboot_reconstructs_only_verified_committed_snapshot(self):
        engine = ArtifactTrustEngine(
            policy(), empty_persistent_state()
        )
        denied = engine.restore(
            snapshot(state=active(integrity_verified=False))
        )
        self.assertEqual(
            ArtifactDecision.REBOOT_SNAPSHOT_INVALID, denied.code
        )
        self.assertFalse(engine.active_state.integrity_verified)
        self.assertEqual(0, engine.active_state.generation)
        passed = engine.restore(snapshot())
        self.assertEqual(ArtifactDecision.PASS_RESTORED, passed.code)
        self.assertEqual(active(), engine.active_state)
        denied = engine.restore(snapshot(state=active(target_digest=DC)))
        self.assertEqual(
            ArtifactDecision.REBOOT_SNAPSHOT_INVALID, denied.code
        )

    def test_all_artifact_kinds_require_matching_distinct_purpose(self):
        combinations = (
            (ArtifactKind.CONFIGURATION, KeyPurpose.CONFIG_RELEASE),
            (ArtifactKind.CALIBRATION, KeyPurpose.CALIBRATION_RELEASE),
            (ArtifactKind.FIRMWARE, KeyPurpose.FIRMWARE_RELEASE),
            (ArtifactKind.GENERATED_EVIDENCE, KeyPurpose.EVIDENCE_RELEASE),
        )
        for kind, purpose in combinations:
            selected_policy = policy(
                expected_kind=kind, expected_purpose=purpose
            )
            selected_candidate = candidate(kind=kind, purpose=purpose)
            selected_assertion = assertion(kind=kind, purpose=purpose)
            engine = ArtifactTrustEngine(
                selected_policy, empty_persistent_state()
            )
            self.assertEqual(
                ArtifactDecision.PASS_STAGED,
                engine.stage(selected_candidate, selected_assertion).code,
            )

    def test_core_exposes_assertions_not_crypto_or_private_key_bytes(self):
        fields = {
            field.name
            for structure in (
                ArtifactPolicy,
                ArtifactCandidate,
                VerificationAssertion,
                DurableCommitReceipt,
                AuditCommitReceipt,
            )
            for field in dataclasses.fields(structure)
        }
        self.assertFalse(
            fields
            & {
                "private_key",
                "secret",
                "signature_bytes",
                "public_key_bytes",
                "credential",
            }
        )
        source = (
            ROOT / "host/myactuator_lib/artifact_trust.py"
        ).read_text()
        for forbidden in (
            "from cryptography",
            "import cryptography",
            "import nacl",
            "import Crypto",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
