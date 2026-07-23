#pragma once

// Allocation-free signed-artifact transaction semantics.
//
// This core performs no cryptography, persistence, audit I/O, update I/O, or
// motion authorization. Future vetted adapters must produce the verification
// assertions and durable receipts consumed here.

#include <stddef.h>
#include <stdint.h>

namespace myactuator {
namespace artifact_trust {

static const size_t kTrustDigestSize = 32U;

struct TrustDigest {
    uint8_t bytes[kTrustDigestSize];
};

enum class ArtifactKind : uint8_t {
    CONFIGURATION = 1,
    CALIBRATION = 2,
    FIRMWARE = 3,
    GENERATED_EVIDENCE = 4,
};

enum class KeyPurpose : uint8_t {
    CONFIG_RELEASE = 1,
    CALIBRATION_RELEASE = 2,
    FIRMWARE_RELEASE = 3,
    EVIDENCE_RELEASE = 4,
};

enum class VerificationAlgorithm : uint8_t {
    PLATFORM_SECURE_BOOT_V2_RSA_PSS_SHA256 = 1,
    ECDSA_P256_SHA256 = 2,
    ED25519 = 3,
};

enum class ArtifactDecision : uint8_t {
    PASS_STAGED = 0,
    PASS_COMMITTED = 1,
    PASS_ABORTED = 2,
    PASS_RESTORED = 3,
    INVALID_REQUEST = 4,
    PLATFORM_PROFILE_NOT_SELECTED = 5,
    TRUST_ANCHOR_MISSING = 6,
    VERIFIER_NOT_BOUND = 7,
    VERIFICATION_ASSERTION_MISSING = 8,
    SIGNATURE_INVALID = 9,
    CHAIN_INVALID = 10,
    KEY_REVOKED = 11,
    ALGORITHM_MISMATCH = 12,
    KEY_ID_MISMATCH = 13,
    KEY_PURPOSE_MISMATCH = 14,
    ARTIFACT_KIND_MISMATCH = 15,
    TARGET_MISMATCH = 16,
    DIGEST_MISMATCH = 17,
    ENVELOPE_MISMATCH = 18,
    PERSISTENT_STATE_UNAVAILABLE = 19,
    PERSISTENT_STATE_UNTRUSTED = 20,
    SECURITY_EPOCH_ROLLBACK = 21,
    DEPLOYMENT_SEQUENCE_ROLLBACK = 22,
    DUPLICATE_VERSION_DIGEST_CONFLICT = 23,
    STAGE_OCCUPIED = 24,
    NO_STAGED_TRANSACTION = 25,
    TRANSACTION_MISMATCH = 26,
    DURABLE_RECEIPT_INVALID = 27,
    AUDIT_RECEIPT_INVALID = 28,
    GENERATION_MISMATCH = 29,
    REBOOT_SNAPSHOT_INVALID = 30,
};

struct ArtifactPolicy {
    bool platform_profile_selected;
    bool trust_anchor_present;
    bool verifier_bound;
    bool persistent_store_bound;
    bool durable_audit_bound;
    ArtifactKind expected_kind;
    KeyPurpose expected_purpose;
    VerificationAlgorithm expected_algorithm;
    TrustDigest expected_key_id_digest;
    TrustDigest expected_target_digest;
    TrustDigest expected_envelope_schema_digest;
    uint64_t minimum_security_epoch;
};

struct ArtifactCandidate {
    TrustDigest transaction_digest;
    TrustDigest artifact_digest;
    TrustDigest target_digest;
    TrustDigest envelope_schema_digest;
    TrustDigest key_id_digest;
    ArtifactKind kind;
    KeyPurpose purpose;
    VerificationAlgorithm algorithm;
    uint64_t deployment_sequence;
    uint64_t security_epoch;
};

struct VerificationAssertion {
    TrustDigest assertion_digest;
    TrustDigest adapter_id_digest;
    TrustDigest artifact_digest;
    TrustDigest target_digest;
    TrustDigest envelope_schema_digest;
    TrustDigest key_id_digest;
    ArtifactKind kind;
    KeyPurpose purpose;
    VerificationAlgorithm algorithm;
    bool signature_valid;
    bool chain_valid;
    bool key_revoked;
};

struct PersistentState {
    bool available;
    bool integrity_verified;
    TrustDigest active_artifact_digest;
    TrustDigest committed_transaction_digest;
    TrustDigest target_digest;
    TrustDigest envelope_schema_digest;
    TrustDigest key_id_digest;
    ArtifactKind kind;
    KeyPurpose purpose;
    VerificationAlgorithm algorithm;
    uint64_t generation;
    uint64_t deployment_sequence;
    uint64_t security_epoch;
};

struct DurableCommitReceipt {
    TrustDigest transaction_digest;
    TrustDigest artifact_digest;
    uint64_t previous_generation;
    uint64_t next_generation;
    uint64_t deployment_sequence;
    uint64_t security_epoch;
    bool write_completed;
    bool readback_verified;
};

struct AuditCommitReceipt {
    TrustDigest transaction_digest;
    TrustDigest artifact_digest;
    uint64_t committed_generation;
    TrustDigest audit_event_digest;
    bool durable;
};

struct RebootSnapshot {
    PersistentState state;
    bool durable_commit_verified;
    bool audit_commit_verified;
};

struct ArtifactResult {
    ArtifactDecision code;
    bool stage_present;
    bool active_changed;
    uint64_t active_generation;
    bool proceed_to_next_gate;
    bool motion_authorized;
};

class ArtifactTrustEngine {
   public:
    ArtifactTrustEngine(const ArtifactPolicy& policy,
                        const PersistentState& persistent_state);

    ArtifactResult stage(const ArtifactCandidate& candidate,
                         const VerificationAssertion* assertion);
    ArtifactResult commit(const TrustDigest& transaction_digest,
                          const DurableCommitReceipt& durable_receipt,
                          const AuditCommitReceipt& audit_receipt);
    ArtifactResult abort(const TrustDigest& transaction_digest);
    ArtifactResult restore(const RebootSnapshot& snapshot);

    bool stagePresent() const;
    const ArtifactCandidate* stagedCandidate() const;
    const PersistentState& activeState() const;

   private:
    ArtifactDecision evaluateStage(
        const ArtifactCandidate& candidate,
        const VerificationAssertion* assertion) const;
    ArtifactDecision evaluateCommit(
        const TrustDigest& transaction_digest,
        const DurableCommitReceipt& durable_receipt,
        const AuditCommitReceipt& audit_receipt) const;
    ArtifactResult result(ArtifactDecision code, bool active_changed) const;

    ArtifactPolicy policy_;
    PersistentState active_;
    ArtifactCandidate staged_;
    bool stage_present_;
};

PersistentState EmptyPersistentState(bool available, bool integrity_verified);
bool TrustDigestValid(const TrustDigest& value);
bool TrustDigestEqual(const TrustDigest& left, const TrustDigest& right);
const char* ArtifactDecisionName(ArtifactDecision code);

}  // namespace artifact_trust
}  // namespace myactuator
