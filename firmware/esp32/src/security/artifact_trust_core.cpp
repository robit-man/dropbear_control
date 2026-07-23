#include "artifact_trust_core.h"

#include <string.h>

namespace myactuator {
namespace artifact_trust {
namespace {

bool ArtifactKindValid(ArtifactKind value) {
    const uint8_t raw = static_cast<uint8_t>(value);
    return raw >= static_cast<uint8_t>(ArtifactKind::CONFIGURATION) &&
           raw <= static_cast<uint8_t>(ArtifactKind::GENERATED_EVIDENCE);
}

bool KeyPurposeValid(KeyPurpose value) {
    const uint8_t raw = static_cast<uint8_t>(value);
    return raw >= static_cast<uint8_t>(KeyPurpose::CONFIG_RELEASE) &&
           raw <= static_cast<uint8_t>(KeyPurpose::EVIDENCE_RELEASE);
}

bool AlgorithmValid(VerificationAlgorithm value) {
    const uint8_t raw = static_cast<uint8_t>(value);
    return raw >= static_cast<uint8_t>(
                      VerificationAlgorithm::
                          PLATFORM_SECURE_BOOT_V2_RSA_PSS_SHA256) &&
           raw <= static_cast<uint8_t>(VerificationAlgorithm::ED25519);
}

bool PassDecision(ArtifactDecision code) {
    return code == ArtifactDecision::PASS_STAGED ||
           code == ArtifactDecision::PASS_COMMITTED ||
           code == ArtifactDecision::PASS_ABORTED ||
           code == ArtifactDecision::PASS_RESTORED;
}

}  // namespace

bool TrustDigestValid(const TrustDigest& value) {
    uint8_t combined = 0U;
    for (size_t index = 0U; index < kTrustDigestSize; ++index)
        combined = static_cast<uint8_t>(combined | value.bytes[index]);
    return combined != 0U;
}

bool TrustDigestEqual(const TrustDigest& left, const TrustDigest& right) {
    uint8_t difference = 0U;
    for (size_t index = 0U; index < kTrustDigestSize; ++index)
        difference = static_cast<uint8_t>(
            difference |
            static_cast<uint8_t>(left.bytes[index] ^ right.bytes[index]));
    return difference == 0U;
}

PersistentState EmptyPersistentState(bool available, bool integrity_verified) {
    PersistentState value = {};
    value.available = available;
    value.integrity_verified = integrity_verified;
    return value;
}

ArtifactTrustEngine::ArtifactTrustEngine(
    const ArtifactPolicy& policy, const PersistentState& persistent_state)
    : policy_(policy),
      active_(persistent_state),
      staged_(),
      stage_present_(false) {}

ArtifactResult ArtifactTrustEngine::result(ArtifactDecision code,
                                           bool active_changed) const {
    ArtifactResult output = {};
    output.code = code;
    output.stage_present = stage_present_;
    output.active_changed = active_changed;
    output.active_generation = active_.generation;
    output.proceed_to_next_gate = PassDecision(code);
    output.motion_authorized = false;
    return output;
}

ArtifactDecision ArtifactTrustEngine::evaluateStage(
    const ArtifactCandidate& candidate,
    const VerificationAssertion* assertion) const {
    if (!ArtifactKindValid(candidate.kind) ||
        !KeyPurposeValid(candidate.purpose) ||
        !AlgorithmValid(candidate.algorithm) ||
        !TrustDigestValid(candidate.transaction_digest) ||
        !TrustDigestValid(candidate.artifact_digest) ||
        !TrustDigestValid(candidate.target_digest) ||
        !TrustDigestValid(candidate.envelope_schema_digest) ||
        !TrustDigestValid(candidate.key_id_digest) ||
        candidate.deployment_sequence == 0U || candidate.security_epoch == 0U)
        return ArtifactDecision::INVALID_REQUEST;
    if (stage_present_) return ArtifactDecision::STAGE_OCCUPIED;
    if (!policy_.platform_profile_selected)
        return ArtifactDecision::PLATFORM_PROFILE_NOT_SELECTED;
    if (!policy_.trust_anchor_present)
        return ArtifactDecision::TRUST_ANCHOR_MISSING;
    if (!policy_.verifier_bound)
        return ArtifactDecision::VERIFIER_NOT_BOUND;
    if (assertion == NULL ||
        !TrustDigestValid(assertion->assertion_digest) ||
        !TrustDigestValid(assertion->adapter_id_digest))
        return ArtifactDecision::VERIFICATION_ASSERTION_MISSING;
    if (!assertion->signature_valid)
        return ArtifactDecision::SIGNATURE_INVALID;
    if (!assertion->chain_valid) return ArtifactDecision::CHAIN_INVALID;
    if (assertion->key_revoked) return ArtifactDecision::KEY_REVOKED;
    if (candidate.algorithm != policy_.expected_algorithm ||
        assertion->algorithm != candidate.algorithm)
        return ArtifactDecision::ALGORITHM_MISMATCH;
    if (!TrustDigestEqual(candidate.key_id_digest,
                          policy_.expected_key_id_digest) ||
        !TrustDigestEqual(assertion->key_id_digest,
                          candidate.key_id_digest))
        return ArtifactDecision::KEY_ID_MISMATCH;
    if (candidate.purpose != policy_.expected_purpose ||
        assertion->purpose != candidate.purpose)
        return ArtifactDecision::KEY_PURPOSE_MISMATCH;
    if (candidate.kind != policy_.expected_kind ||
        assertion->kind != candidate.kind)
        return ArtifactDecision::ARTIFACT_KIND_MISMATCH;
    if (!TrustDigestEqual(candidate.target_digest,
                          policy_.expected_target_digest) ||
        !TrustDigestEqual(assertion->target_digest,
                          candidate.target_digest))
        return ArtifactDecision::TARGET_MISMATCH;
    if (!TrustDigestEqual(assertion->artifact_digest,
                          candidate.artifact_digest))
        return ArtifactDecision::DIGEST_MISMATCH;
    if (!TrustDigestEqual(candidate.envelope_schema_digest,
                          policy_.expected_envelope_schema_digest) ||
        !TrustDigestEqual(assertion->envelope_schema_digest,
                          candidate.envelope_schema_digest))
        return ArtifactDecision::ENVELOPE_MISMATCH;
    if (!policy_.persistent_store_bound || !active_.available)
        return ArtifactDecision::PERSISTENT_STATE_UNAVAILABLE;
    if (!active_.integrity_verified)
        return ArtifactDecision::PERSISTENT_STATE_UNTRUSTED;
    if (active_.generation > 0U &&
        (!TrustDigestValid(active_.active_artifact_digest) ||
         !TrustDigestValid(active_.committed_transaction_digest) ||
         !TrustDigestEqual(active_.target_digest,
                           policy_.expected_target_digest) ||
         !TrustDigestEqual(active_.envelope_schema_digest,
                           policy_.expected_envelope_schema_digest) ||
         !TrustDigestEqual(active_.key_id_digest,
                           policy_.expected_key_id_digest) ||
         active_.kind != policy_.expected_kind ||
         active_.purpose != policy_.expected_purpose ||
         active_.algorithm != policy_.expected_algorithm))
        return ArtifactDecision::PERSISTENT_STATE_UNTRUSTED;
    if (candidate.security_epoch < policy_.minimum_security_epoch ||
        candidate.security_epoch < active_.security_epoch)
        return ArtifactDecision::SECURITY_EPOCH_ROLLBACK;
    if (candidate.deployment_sequence == active_.deployment_sequence) {
        if (TrustDigestValid(active_.active_artifact_digest) &&
            !TrustDigestEqual(candidate.artifact_digest,
                              active_.active_artifact_digest))
            return ArtifactDecision::DUPLICATE_VERSION_DIGEST_CONFLICT;
        return ArtifactDecision::DEPLOYMENT_SEQUENCE_ROLLBACK;
    }
    if (candidate.deployment_sequence < active_.deployment_sequence)
        return ArtifactDecision::DEPLOYMENT_SEQUENCE_ROLLBACK;
    return ArtifactDecision::PASS_STAGED;
}

ArtifactResult ArtifactTrustEngine::stage(
    const ArtifactCandidate& candidate,
    const VerificationAssertion* assertion) {
    const ArtifactDecision code = evaluateStage(candidate, assertion);
    if (code == ArtifactDecision::PASS_STAGED) {
        staged_ = candidate;
        stage_present_ = true;
    }
    return result(code, false);
}

ArtifactDecision ArtifactTrustEngine::evaluateCommit(
    const TrustDigest& transaction_digest,
    const DurableCommitReceipt& durable,
    const AuditCommitReceipt& audit) const {
    if (!stage_present_) return ArtifactDecision::NO_STAGED_TRANSACTION;
    if (!TrustDigestValid(transaction_digest) ||
        !TrustDigestEqual(transaction_digest, staged_.transaction_digest))
        return ArtifactDecision::TRANSACTION_MISMATCH;
    if (!policy_.persistent_store_bound || !active_.available)
        return ArtifactDecision::PERSISTENT_STATE_UNAVAILABLE;
    if (!active_.integrity_verified)
        return ArtifactDecision::PERSISTENT_STATE_UNTRUSTED;
    if (!durable.write_completed || !durable.readback_verified ||
        !TrustDigestEqual(durable.transaction_digest,
                          staged_.transaction_digest) ||
        !TrustDigestEqual(durable.artifact_digest, staged_.artifact_digest) ||
        durable.deployment_sequence != staged_.deployment_sequence ||
        durable.security_epoch != staged_.security_epoch)
        return ArtifactDecision::DURABLE_RECEIPT_INVALID;
    if (durable.previous_generation != active_.generation ||
        durable.next_generation != active_.generation + 1U)
        return ArtifactDecision::GENERATION_MISMATCH;
    if (!policy_.durable_audit_bound || !audit.durable ||
        !TrustDigestValid(audit.audit_event_digest) ||
        !TrustDigestEqual(audit.transaction_digest,
                          staged_.transaction_digest) ||
        !TrustDigestEqual(audit.artifact_digest, staged_.artifact_digest) ||
        audit.committed_generation != durable.next_generation)
        return ArtifactDecision::AUDIT_RECEIPT_INVALID;
    return ArtifactDecision::PASS_COMMITTED;
}

ArtifactResult ArtifactTrustEngine::commit(
    const TrustDigest& transaction_digest,
    const DurableCommitReceipt& durable_receipt,
    const AuditCommitReceipt& audit_receipt) {
    const ArtifactDecision code =
        evaluateCommit(transaction_digest, durable_receipt, audit_receipt);
    if (code != ArtifactDecision::PASS_COMMITTED)
        return result(code, false);
    active_.available = true;
    active_.integrity_verified = true;
    active_.active_artifact_digest = staged_.artifact_digest;
    active_.committed_transaction_digest = staged_.transaction_digest;
    active_.target_digest = staged_.target_digest;
    active_.envelope_schema_digest = staged_.envelope_schema_digest;
    active_.key_id_digest = staged_.key_id_digest;
    active_.kind = staged_.kind;
    active_.purpose = staged_.purpose;
    active_.algorithm = staged_.algorithm;
    active_.generation = durable_receipt.next_generation;
    active_.deployment_sequence = staged_.deployment_sequence;
    active_.security_epoch = staged_.security_epoch;
    stage_present_ = false;
    memset(&staged_, 0, sizeof(staged_));
    return result(ArtifactDecision::PASS_COMMITTED, true);
}

ArtifactResult ArtifactTrustEngine::abort(
    const TrustDigest& transaction_digest) {
    if (!stage_present_)
        return result(ArtifactDecision::NO_STAGED_TRANSACTION, false);
    if (!TrustDigestValid(transaction_digest) ||
        !TrustDigestEqual(transaction_digest, staged_.transaction_digest))
        return result(ArtifactDecision::TRANSACTION_MISMATCH, false);
    stage_present_ = false;
    memset(&staged_, 0, sizeof(staged_));
    return result(ArtifactDecision::PASS_ABORTED, false);
}

ArtifactResult ArtifactTrustEngine::restore(const RebootSnapshot& snapshot) {
    stage_present_ = false;
    memset(&staged_, 0, sizeof(staged_));
    active_ = EmptyPersistentState(snapshot.state.available, false);
    const PersistentState& state = snapshot.state;
    if (!policy_.platform_profile_selected ||
        !policy_.trust_anchor_present || !policy_.verifier_bound ||
        !policy_.persistent_store_bound || !policy_.durable_audit_bound ||
        !state.available || !state.integrity_verified ||
        !snapshot.durable_commit_verified ||
        !snapshot.audit_commit_verified ||
        !TrustDigestValid(state.active_artifact_digest) ||
        !TrustDigestValid(state.committed_transaction_digest) ||
        !TrustDigestEqual(state.target_digest,
                          policy_.expected_target_digest) ||
        !TrustDigestEqual(state.envelope_schema_digest,
                          policy_.expected_envelope_schema_digest) ||
        !TrustDigestEqual(state.key_id_digest,
                          policy_.expected_key_id_digest) ||
        state.kind != policy_.expected_kind ||
        state.purpose != policy_.expected_purpose ||
        state.algorithm != policy_.expected_algorithm ||
        state.generation == 0U || state.deployment_sequence == 0U ||
        state.security_epoch < policy_.minimum_security_epoch)
        return result(ArtifactDecision::REBOOT_SNAPSHOT_INVALID, false);
    active_ = state;
    return result(ArtifactDecision::PASS_RESTORED, true);
}

bool ArtifactTrustEngine::stagePresent() const { return stage_present_; }

const ArtifactCandidate* ArtifactTrustEngine::stagedCandidate() const {
    return stage_present_ ? &staged_ : NULL;
}

const PersistentState& ArtifactTrustEngine::activeState() const {
    return active_;
}

const char* ArtifactDecisionName(ArtifactDecision code) {
    switch (code) {
        case ArtifactDecision::PASS_STAGED:
            return "PASS_STAGED";
        case ArtifactDecision::PASS_COMMITTED:
            return "PASS_COMMITTED";
        case ArtifactDecision::PASS_ABORTED:
            return "PASS_ABORTED";
        case ArtifactDecision::PASS_RESTORED:
            return "PASS_RESTORED";
        case ArtifactDecision::INVALID_REQUEST:
            return "INVALID_REQUEST";
        case ArtifactDecision::PLATFORM_PROFILE_NOT_SELECTED:
            return "PLATFORM_PROFILE_NOT_SELECTED";
        case ArtifactDecision::TRUST_ANCHOR_MISSING:
            return "TRUST_ANCHOR_MISSING";
        case ArtifactDecision::VERIFIER_NOT_BOUND:
            return "VERIFIER_NOT_BOUND";
        case ArtifactDecision::VERIFICATION_ASSERTION_MISSING:
            return "VERIFICATION_ASSERTION_MISSING";
        case ArtifactDecision::SIGNATURE_INVALID:
            return "SIGNATURE_INVALID";
        case ArtifactDecision::CHAIN_INVALID:
            return "CHAIN_INVALID";
        case ArtifactDecision::KEY_REVOKED:
            return "KEY_REVOKED";
        case ArtifactDecision::ALGORITHM_MISMATCH:
            return "ALGORITHM_MISMATCH";
        case ArtifactDecision::KEY_ID_MISMATCH:
            return "KEY_ID_MISMATCH";
        case ArtifactDecision::KEY_PURPOSE_MISMATCH:
            return "KEY_PURPOSE_MISMATCH";
        case ArtifactDecision::ARTIFACT_KIND_MISMATCH:
            return "ARTIFACT_KIND_MISMATCH";
        case ArtifactDecision::TARGET_MISMATCH:
            return "TARGET_MISMATCH";
        case ArtifactDecision::DIGEST_MISMATCH:
            return "DIGEST_MISMATCH";
        case ArtifactDecision::ENVELOPE_MISMATCH:
            return "ENVELOPE_MISMATCH";
        case ArtifactDecision::PERSISTENT_STATE_UNAVAILABLE:
            return "PERSISTENT_STATE_UNAVAILABLE";
        case ArtifactDecision::PERSISTENT_STATE_UNTRUSTED:
            return "PERSISTENT_STATE_UNTRUSTED";
        case ArtifactDecision::SECURITY_EPOCH_ROLLBACK:
            return "SECURITY_EPOCH_ROLLBACK";
        case ArtifactDecision::DEPLOYMENT_SEQUENCE_ROLLBACK:
            return "DEPLOYMENT_SEQUENCE_ROLLBACK";
        case ArtifactDecision::DUPLICATE_VERSION_DIGEST_CONFLICT:
            return "DUPLICATE_VERSION_DIGEST_CONFLICT";
        case ArtifactDecision::STAGE_OCCUPIED:
            return "STAGE_OCCUPIED";
        case ArtifactDecision::NO_STAGED_TRANSACTION:
            return "NO_STAGED_TRANSACTION";
        case ArtifactDecision::TRANSACTION_MISMATCH:
            return "TRANSACTION_MISMATCH";
        case ArtifactDecision::DURABLE_RECEIPT_INVALID:
            return "DURABLE_RECEIPT_INVALID";
        case ArtifactDecision::AUDIT_RECEIPT_INVALID:
            return "AUDIT_RECEIPT_INVALID";
        case ArtifactDecision::GENERATION_MISMATCH:
            return "GENERATION_MISMATCH";
        case ArtifactDecision::REBOOT_SNAPSHOT_INVALID:
            return "REBOOT_SNAPSHOT_INVALID";
    }
    return "UNKNOWN";
}

}  // namespace artifact_trust
}  // namespace myactuator
