"""Portable fail-closed signed-artifact transaction semantics.

This module implements no cryptography and performs no persistence or I/O.
It consumes exact assertions and durable receipts produced by future vetted
platform adapters. Passing a stage or commit never grants physical support,
I/O, or motor motion.

The numeric enums and decision order mirror
``firmware/esp32/src/security/artifact_trust_core``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import IntEnum


ZERO_DIGEST = "0" * 64


class ArtifactKind(IntEnum):
    CONFIGURATION = 1
    CALIBRATION = 2
    FIRMWARE = 3
    GENERATED_EVIDENCE = 4


class KeyPurpose(IntEnum):
    CONFIG_RELEASE = 1
    CALIBRATION_RELEASE = 2
    FIRMWARE_RELEASE = 3
    EVIDENCE_RELEASE = 4


class VerificationAlgorithm(IntEnum):
    PLATFORM_SECURE_BOOT_V2_RSA_PSS_SHA256 = 1
    ECDSA_P256_SHA256 = 2
    ED25519 = 3


class ArtifactDecision(IntEnum):
    PASS_STAGED = 0
    PASS_COMMITTED = 1
    PASS_ABORTED = 2
    PASS_RESTORED = 3
    INVALID_REQUEST = 4
    PLATFORM_PROFILE_NOT_SELECTED = 5
    TRUST_ANCHOR_MISSING = 6
    VERIFIER_NOT_BOUND = 7
    VERIFICATION_ASSERTION_MISSING = 8
    SIGNATURE_INVALID = 9
    CHAIN_INVALID = 10
    KEY_REVOKED = 11
    ALGORITHM_MISMATCH = 12
    KEY_ID_MISMATCH = 13
    KEY_PURPOSE_MISMATCH = 14
    ARTIFACT_KIND_MISMATCH = 15
    TARGET_MISMATCH = 16
    DIGEST_MISMATCH = 17
    ENVELOPE_MISMATCH = 18
    PERSISTENT_STATE_UNAVAILABLE = 19
    PERSISTENT_STATE_UNTRUSTED = 20
    SECURITY_EPOCH_ROLLBACK = 21
    DEPLOYMENT_SEQUENCE_ROLLBACK = 22
    DUPLICATE_VERSION_DIGEST_CONFLICT = 23
    STAGE_OCCUPIED = 24
    NO_STAGED_TRANSACTION = 25
    TRANSACTION_MISMATCH = 26
    DURABLE_RECEIPT_INVALID = 27
    AUDIT_RECEIPT_INVALID = 28
    GENERATION_MISMATCH = 29
    REBOOT_SNAPSHOT_INVALID = 30


def _digest_valid(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value != ZERO_DIGEST
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True)
class ArtifactPolicy:
    platform_profile_selected: bool
    trust_anchor_present: bool
    verifier_bound: bool
    persistent_store_bound: bool
    durable_audit_bound: bool
    expected_kind: ArtifactKind
    expected_purpose: KeyPurpose
    expected_algorithm: VerificationAlgorithm
    expected_key_id_digest: str
    expected_target_digest: str
    expected_envelope_schema_digest: str
    minimum_security_epoch: int


@dataclass(frozen=True)
class ArtifactCandidate:
    transaction_digest: str
    artifact_digest: str
    target_digest: str
    envelope_schema_digest: str
    key_id_digest: str
    kind: ArtifactKind
    purpose: KeyPurpose
    algorithm: VerificationAlgorithm
    deployment_sequence: int
    security_epoch: int


@dataclass(frozen=True)
class VerificationAssertion:
    assertion_digest: str
    adapter_id_digest: str
    artifact_digest: str
    target_digest: str
    envelope_schema_digest: str
    key_id_digest: str
    kind: ArtifactKind
    purpose: KeyPurpose
    algorithm: VerificationAlgorithm
    signature_valid: bool
    chain_valid: bool
    key_revoked: bool


@dataclass(frozen=True)
class PersistentState:
    available: bool
    integrity_verified: bool
    active_artifact_digest: str
    committed_transaction_digest: str
    target_digest: str
    envelope_schema_digest: str
    key_id_digest: str
    kind: ArtifactKind | int
    purpose: KeyPurpose | int
    algorithm: VerificationAlgorithm | int
    generation: int
    deployment_sequence: int
    security_epoch: int


@dataclass(frozen=True)
class DurableCommitReceipt:
    transaction_digest: str
    artifact_digest: str
    previous_generation: int
    next_generation: int
    deployment_sequence: int
    security_epoch: int
    write_completed: bool
    readback_verified: bool


@dataclass(frozen=True)
class AuditCommitReceipt:
    transaction_digest: str
    artifact_digest: str
    committed_generation: int
    audit_event_digest: str
    durable: bool


@dataclass(frozen=True)
class RebootSnapshot:
    state: PersistentState
    durable_commit_verified: bool
    audit_commit_verified: bool


@dataclass(frozen=True)
class ArtifactResult:
    code: ArtifactDecision
    stage_present: bool
    active_changed: bool
    active_generation: int
    proceed_to_next_gate: bool
    motion_authorized: bool = False

    def __post_init__(self) -> None:
        if self.motion_authorized:
            raise ValueError("artifact trust core cannot grant motion authority")
        expected = self.code in {
            ArtifactDecision.PASS_STAGED,
            ArtifactDecision.PASS_COMMITTED,
            ArtifactDecision.PASS_ABORTED,
            ArtifactDecision.PASS_RESTORED,
        }
        if self.proceed_to_next_gate != expected:
            raise ValueError("artifact result/decision mismatch")


def empty_persistent_state(
    *, available: bool = True, integrity_verified: bool = True
) -> PersistentState:
    return PersistentState(
        available=available,
        integrity_verified=integrity_verified,
        active_artifact_digest=ZERO_DIGEST,
        committed_transaction_digest=ZERO_DIGEST,
        target_digest=ZERO_DIGEST,
        envelope_schema_digest=ZERO_DIGEST,
        key_id_digest=ZERO_DIGEST,
        kind=0,
        purpose=0,
        algorithm=0,
        generation=0,
        deployment_sequence=0,
        security_epoch=0,
    )


class ArtifactTrustEngine:
    """One artifact-kind transaction coordinator with no I/O capability."""

    def __init__(
        self, policy: ArtifactPolicy, persistent_state: PersistentState
    ) -> None:
        self.policy = policy
        self._active = persistent_state
        self._staged: ArtifactCandidate | None = None

    @property
    def active_state(self) -> PersistentState:
        return self._active

    @property
    def staged_candidate(self) -> ArtifactCandidate | None:
        return self._staged

    def _result(
        self,
        code: ArtifactDecision,
        *,
        active_changed: bool = False,
    ) -> ArtifactResult:
        return ArtifactResult(
            code=code,
            stage_present=self._staged is not None,
            active_changed=active_changed,
            active_generation=self._active.generation,
            proceed_to_next_gate=code
            in {
                ArtifactDecision.PASS_STAGED,
                ArtifactDecision.PASS_COMMITTED,
                ArtifactDecision.PASS_ABORTED,
                ArtifactDecision.PASS_RESTORED,
            },
        )

    def stage(
        self,
        candidate: ArtifactCandidate,
        assertion: VerificationAssertion | None,
    ) -> ArtifactResult:
        code = self._evaluate_stage(candidate, assertion)
        if code == ArtifactDecision.PASS_STAGED:
            self._staged = candidate
        return self._result(code)

    def _evaluate_stage(
        self,
        candidate: ArtifactCandidate,
        assertion: VerificationAssertion | None,
    ) -> ArtifactDecision:
        try:
            kind = ArtifactKind(candidate.kind)
            purpose = KeyPurpose(candidate.purpose)
            algorithm = VerificationAlgorithm(candidate.algorithm)
        except (TypeError, ValueError):
            return ArtifactDecision.INVALID_REQUEST
        if (
            not _digest_valid(candidate.transaction_digest)
            or not _digest_valid(candidate.artifact_digest)
            or not _digest_valid(candidate.target_digest)
            or not _digest_valid(candidate.envelope_schema_digest)
            or not _digest_valid(candidate.key_id_digest)
            or candidate.deployment_sequence <= 0
            or candidate.security_epoch <= 0
        ):
            return ArtifactDecision.INVALID_REQUEST
        if self._staged is not None:
            return ArtifactDecision.STAGE_OCCUPIED
        if not self.policy.platform_profile_selected:
            return ArtifactDecision.PLATFORM_PROFILE_NOT_SELECTED
        if not self.policy.trust_anchor_present:
            return ArtifactDecision.TRUST_ANCHOR_MISSING
        if not self.policy.verifier_bound:
            return ArtifactDecision.VERIFIER_NOT_BOUND
        if assertion is None:
            return ArtifactDecision.VERIFICATION_ASSERTION_MISSING
        if (
            not _digest_valid(assertion.assertion_digest)
            or not _digest_valid(assertion.adapter_id_digest)
        ):
            return ArtifactDecision.VERIFICATION_ASSERTION_MISSING
        if not assertion.signature_valid:
            return ArtifactDecision.SIGNATURE_INVALID
        if not assertion.chain_valid:
            return ArtifactDecision.CHAIN_INVALID
        if assertion.key_revoked:
            return ArtifactDecision.KEY_REVOKED
        if (
            algorithm != self.policy.expected_algorithm
            or assertion.algorithm != algorithm
        ):
            return ArtifactDecision.ALGORITHM_MISMATCH
        if (
            candidate.key_id_digest != self.policy.expected_key_id_digest
            or assertion.key_id_digest != candidate.key_id_digest
        ):
            return ArtifactDecision.KEY_ID_MISMATCH
        if (
            purpose != self.policy.expected_purpose
            or assertion.purpose != purpose
        ):
            return ArtifactDecision.KEY_PURPOSE_MISMATCH
        if kind != self.policy.expected_kind or assertion.kind != kind:
            return ArtifactDecision.ARTIFACT_KIND_MISMATCH
        if (
            candidate.target_digest != self.policy.expected_target_digest
            or assertion.target_digest != candidate.target_digest
        ):
            return ArtifactDecision.TARGET_MISMATCH
        if assertion.artifact_digest != candidate.artifact_digest:
            return ArtifactDecision.DIGEST_MISMATCH
        if (
            candidate.envelope_schema_digest
            != self.policy.expected_envelope_schema_digest
            or assertion.envelope_schema_digest
            != candidate.envelope_schema_digest
        ):
            return ArtifactDecision.ENVELOPE_MISMATCH
        if (
            not self.policy.persistent_store_bound
            or not self._active.available
        ):
            return ArtifactDecision.PERSISTENT_STATE_UNAVAILABLE
        if not self._active.integrity_verified:
            return ArtifactDecision.PERSISTENT_STATE_UNTRUSTED
        if self._active.generation > 0 and (
            not _digest_valid(self._active.active_artifact_digest)
            or not _digest_valid(self._active.committed_transaction_digest)
            or self._active.target_digest
            != self.policy.expected_target_digest
            or self._active.envelope_schema_digest
            != self.policy.expected_envelope_schema_digest
            or self._active.key_id_digest
            != self.policy.expected_key_id_digest
            or self._active.kind != self.policy.expected_kind
            or self._active.purpose != self.policy.expected_purpose
            or self._active.algorithm != self.policy.expected_algorithm
        ):
            return ArtifactDecision.PERSISTENT_STATE_UNTRUSTED
        if (
            candidate.security_epoch < self.policy.minimum_security_epoch
            or candidate.security_epoch < self._active.security_epoch
        ):
            return ArtifactDecision.SECURITY_EPOCH_ROLLBACK
        if candidate.deployment_sequence == self._active.deployment_sequence:
            if (
                _digest_valid(self._active.active_artifact_digest)
                and candidate.artifact_digest
                != self._active.active_artifact_digest
            ):
                return ArtifactDecision.DUPLICATE_VERSION_DIGEST_CONFLICT
            return ArtifactDecision.DEPLOYMENT_SEQUENCE_ROLLBACK
        if candidate.deployment_sequence < self._active.deployment_sequence:
            return ArtifactDecision.DEPLOYMENT_SEQUENCE_ROLLBACK
        return ArtifactDecision.PASS_STAGED

    def commit(
        self,
        transaction_digest: str,
        durable_receipt: DurableCommitReceipt,
        audit_receipt: AuditCommitReceipt,
    ) -> ArtifactResult:
        code = self._evaluate_commit(
            transaction_digest, durable_receipt, audit_receipt
        )
        if code != ArtifactDecision.PASS_COMMITTED:
            return self._result(code)
        assert self._staged is not None
        candidate = self._staged
        self._active = PersistentState(
            available=True,
            integrity_verified=True,
            active_artifact_digest=candidate.artifact_digest,
            committed_transaction_digest=candidate.transaction_digest,
            target_digest=candidate.target_digest,
            envelope_schema_digest=candidate.envelope_schema_digest,
            key_id_digest=candidate.key_id_digest,
            kind=candidate.kind,
            purpose=candidate.purpose,
            algorithm=candidate.algorithm,
            generation=durable_receipt.next_generation,
            deployment_sequence=candidate.deployment_sequence,
            security_epoch=candidate.security_epoch,
        )
        self._staged = None
        return self._result(
            ArtifactDecision.PASS_COMMITTED, active_changed=True
        )

    def _evaluate_commit(
        self,
        transaction_digest: str,
        durable: DurableCommitReceipt,
        audit: AuditCommitReceipt,
    ) -> ArtifactDecision:
        if self._staged is None:
            return ArtifactDecision.NO_STAGED_TRANSACTION
        candidate = self._staged
        if (
            not _digest_valid(transaction_digest)
            or transaction_digest != candidate.transaction_digest
        ):
            return ArtifactDecision.TRANSACTION_MISMATCH
        if (
            not self.policy.persistent_store_bound
            or not self._active.available
        ):
            return ArtifactDecision.PERSISTENT_STATE_UNAVAILABLE
        if not self._active.integrity_verified:
            return ArtifactDecision.PERSISTENT_STATE_UNTRUSTED
        if (
            not durable.write_completed
            or not durable.readback_verified
            or durable.transaction_digest != candidate.transaction_digest
            or durable.artifact_digest != candidate.artifact_digest
            or durable.deployment_sequence != candidate.deployment_sequence
            or durable.security_epoch != candidate.security_epoch
        ):
            return ArtifactDecision.DURABLE_RECEIPT_INVALID
        if (
            durable.previous_generation != self._active.generation
            or durable.next_generation != self._active.generation + 1
        ):
            return ArtifactDecision.GENERATION_MISMATCH
        if (
            not self.policy.durable_audit_bound
            or not audit.durable
            or not _digest_valid(audit.audit_event_digest)
            or audit.transaction_digest != candidate.transaction_digest
            or audit.artifact_digest != candidate.artifact_digest
            or audit.committed_generation != durable.next_generation
        ):
            return ArtifactDecision.AUDIT_RECEIPT_INVALID
        return ArtifactDecision.PASS_COMMITTED

    def abort(self, transaction_digest: str) -> ArtifactResult:
        if self._staged is None:
            return self._result(ArtifactDecision.NO_STAGED_TRANSACTION)
        if (
            not _digest_valid(transaction_digest)
            or transaction_digest != self._staged.transaction_digest
        ):
            return self._result(ArtifactDecision.TRANSACTION_MISMATCH)
        self._staged = None
        return self._result(ArtifactDecision.PASS_ABORTED)

    def restore(self, snapshot: RebootSnapshot) -> ArtifactResult:
        self._staged = None
        self._active = empty_persistent_state(
            available=snapshot.state.available,
            integrity_verified=False,
        )
        state = snapshot.state
        if (
            not self.policy.platform_profile_selected
            or not self.policy.trust_anchor_present
            or not self.policy.verifier_bound
            or not self.policy.persistent_store_bound
            or not self.policy.durable_audit_bound
            or not state.available
            or not state.integrity_verified
            or not snapshot.durable_commit_verified
            or not snapshot.audit_commit_verified
            or not _digest_valid(state.active_artifact_digest)
            or not _digest_valid(state.committed_transaction_digest)
            or state.target_digest != self.policy.expected_target_digest
            or state.envelope_schema_digest
            != self.policy.expected_envelope_schema_digest
            or state.key_id_digest != self.policy.expected_key_id_digest
            or state.kind != self.policy.expected_kind
            or state.purpose != self.policy.expected_purpose
            or state.algorithm != self.policy.expected_algorithm
            or state.generation <= 0
            or state.deployment_sequence <= 0
            or state.security_epoch < self.policy.minimum_security_epoch
        ):
            return self._result(ArtifactDecision.REBOOT_SNAPSHOT_INVALID)
        self._active = replace(state)
        return self._result(
            ArtifactDecision.PASS_RESTORED, active_changed=True
        )
