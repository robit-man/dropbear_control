#pragma once

#include <stddef.h>
#include <stdint.h>

namespace myactuator {
namespace safety {

// This guard performs bounded identity comparisons and admission state only.
// A trusted external loader must calculate/verify SHA-256 and perform the
// structural and semantic validation represented by ConfigCandidate flags.
// The guard deliberately contains no cryptographic implementation.

static const size_t kConfigIdCapacity = 32;
static const size_t kSha256DigestSize = 32;
static const size_t kCommitTokenSize = 16;

enum class AuthorizationClass : uint8_t {
    NONE = 0,
    OBSERVE_ONLY = 1,
    MOTION = 2,
};

// Explicit values and DecisionCode() strings are a stable adapter contract.
enum class ConfigDecision : uint8_t {
    ALLOWED = 0,
    CLOCK_REGRESSION = 1,
    SCHEMA_POLICY_INVALID = 2,
    IDENTITY_INVALID = 3,
    CONFIG_ID_MISMATCH = 4,
    DIGEST_MISMATCH = 5,
    REVISION_MISMATCH = 6,
    SCHEMA_MISMATCH = 7,
    GENERATION_MISMATCH = 8,
    STRUCTURAL_VALIDATION_MISSING = 9,
    SEMANTIC_VALIDATION_MISSING = 10,
    MOTION_NOT_ALLOWED = 11,
    AUTHORIZATION_CLASS_DENIED = 12,
    VALIDITY_DEADLINE_INVALID = 13,
    REVISION_NOT_MONOTONIC = 14,
    GENERATION_NOT_MONOTONIC = 15,
    COMMIT_TOKEN_INVALID = 16,
    NO_STAGED_CANDIDATE = 17,
    COMMIT_TOKEN_MISMATCH = 18,
    NO_ACTIVE_CONFIG = 19,
    REVOKED = 20,
    CONFIG_EXPIRED = 21,
    COMMAND_GENERATION_INVALID = 22,
    COMMAND_GENERATION_REPLAYED = 23,
};

const char* DecisionCode(ConfigDecision decision);

struct BoundedConfigId {
    uint8_t length;
    char bytes[kConfigIdCapacity];
};

struct Sha256Digest {
    uint8_t bytes[kSha256DigestSize];
};

struct ConfigIdentity {
    BoundedConfigId config_id;
    Sha256Digest digest;
    uint64_t revision;
    uint16_t schema_version;
};

struct SchemaCompatibilityPolicy {
    uint16_t minimum_version;
    uint16_t maximum_version;
};

struct ConfigCandidate {
    ConfigIdentity identity;
    uint64_t generation;
    uint64_t validity_deadline_ms;
    bool structural_validated;
    bool semantic_validated;
    bool motion_allowed;
    AuthorizationClass authorization_class;
};

// The expectation is a trusted, out-of-band value supplied by the loader.
// Supplying the candidate as its own expectation provides no authenticity.
struct ConfigExpectation {
    ConfigIdentity identity;
    uint64_t generation;
};

struct GenerationCommitToken {
    uint64_t generation;
    uint8_t bytes[kCommitTokenSize];
};

struct ConfigReference {
    ConfigIdentity identity;
    uint64_t generation;
    AuthorizationClass authorization_class;
};

struct CommandAdmissionProof {
    ConfigReference config;
    uint64_t command_generation;
};

struct ConfigGuardSnapshot {
    bool active_present;
    bool staged_present;
    bool revoked;
    bool usable_at_last_observed_time;
    ConfigCandidate active;
    uint64_t last_command_generation;
};

class ConfigIdentityGuard {
public:
    explicit ConfigIdentityGuard(const SchemaCompatibilityPolicy& policy);

    // Staging never changes the active configuration. A successful commit is
    // one assignment of the fully validated staged record. An unsuccessful
    // stage or commit leaves the previous active record unchanged.
    ConfigDecision stageCandidate(uint64_t now_ms,
                                  const ConfigCandidate& candidate,
                                  const ConfigExpectation& expectation,
                                  const GenerationCommitToken& commit_token);
    ConfigDecision commitStaged(uint64_t now_ms,
                                const GenerationCommitToken& commit_token);

    // Revoke is local and immediate. It does not claim that hardware was
    // disabled; the adapter must propagate denial into the SafetySupervisor
    // prerequisites and physical shutdown path.
    ConfigDecision revoke(uint64_t now_ms);

    ConfigDecision authorizeArm(uint64_t now_ms,
                                const ConfigReference& reference);
    ConfigDecision authorizeTransmit(uint64_t now_ms,
                                     const CommandAdmissionProof& proof);

    ConfigGuardSnapshot snapshot() const;

private:
    SchemaCompatibilityPolicy policy_;
    bool policy_valid_;
    bool active_present_;
    bool staged_present_;
    bool revoked_;
    ConfigCandidate active_;
    ConfigCandidate staged_;
    GenerationCommitToken staged_token_;
    uint64_t highest_staged_revision_;
    uint64_t highest_staged_generation_;
    uint64_t last_command_generation_;
    bool time_initialized_;
    uint64_t last_now_ms_;

    ConfigDecision observeTime(uint64_t now_ms);
    ConfigDecision validateIdentity(const ConfigIdentity& identity) const;
    ConfigDecision compareIdentity(const ConfigIdentity& actual,
                                   const ConfigIdentity& expected) const;
    ConfigDecision compareReference(const ConfigReference& reference) const;
    ConfigDecision activeUsable(uint64_t now_ms) const;
    bool schemaCompatible(uint16_t schema_version) const;
    void clearStaged();
};

}  // namespace safety
}  // namespace myactuator
