#include "config_identity_guard.h"

namespace myactuator {
namespace safety {

namespace {

bool ConfigIdsEqual(const BoundedConfigId& left,
                    const BoundedConfigId& right) {
    if (left.length != right.length) {
        return false;
    }
    uint8_t difference = 0;
    for (size_t index = 0; index < kConfigIdCapacity; ++index) {
        difference |= static_cast<uint8_t>(left.bytes[index]) ^
                      static_cast<uint8_t>(right.bytes[index]);
    }
    return difference == 0;
}

bool DigestsEqual(const Sha256Digest& left, const Sha256Digest& right) {
    uint8_t difference = 0;
    for (size_t index = 0; index < kSha256DigestSize; ++index) {
        difference |= left.bytes[index] ^ right.bytes[index];
    }
    return difference == 0;
}

bool TokensEqual(const GenerationCommitToken& left,
                 const GenerationCommitToken& right) {
    if (left.generation != right.generation) {
        return false;
    }
    uint8_t difference = 0;
    for (size_t index = 0; index < kCommitTokenSize; ++index) {
        difference |= left.bytes[index] ^ right.bytes[index];
    }
    return difference == 0;
}

bool TokenValid(const GenerationCommitToken& token) {
    if (token.generation == 0) {
        return false;
    }
    uint8_t aggregate = 0;
    for (size_t index = 0; index < kCommitTokenSize; ++index) {
        aggregate |= token.bytes[index];
    }
    return aggregate != 0;
}

bool ConfigIdValid(const BoundedConfigId& id) {
    if (id.length == 0 || id.length > kConfigIdCapacity) {
        return false;
    }
    for (size_t index = 0; index < kConfigIdCapacity; ++index) {
        if (index < id.length) {
            if (id.bytes[index] == '\0') {
                return false;
            }
        } else if (id.bytes[index] != '\0') {
            // Canonical zero padding prevents two byte representations of the
            // same bounded identifier.
            return false;
        }
    }
    return true;
}

bool DigestValid(const Sha256Digest& digest) {
    uint8_t aggregate = 0;
    for (size_t index = 0; index < kSha256DigestSize; ++index) {
        aggregate |= digest.bytes[index];
    }
    return aggregate != 0;
}

}  // namespace

const char* DecisionCode(ConfigDecision decision) {
    switch (decision) {
        case ConfigDecision::ALLOWED:
            return "ALLOWED";
        case ConfigDecision::CLOCK_REGRESSION:
            return "CLOCK_REGRESSION";
        case ConfigDecision::SCHEMA_POLICY_INVALID:
            return "SCHEMA_POLICY_INVALID";
        case ConfigDecision::IDENTITY_INVALID:
            return "IDENTITY_INVALID";
        case ConfigDecision::CONFIG_ID_MISMATCH:
            return "CONFIG_ID_MISMATCH";
        case ConfigDecision::DIGEST_MISMATCH:
            return "DIGEST_MISMATCH";
        case ConfigDecision::REVISION_MISMATCH:
            return "REVISION_MISMATCH";
        case ConfigDecision::SCHEMA_MISMATCH:
            return "SCHEMA_MISMATCH";
        case ConfigDecision::GENERATION_MISMATCH:
            return "GENERATION_MISMATCH";
        case ConfigDecision::STRUCTURAL_VALIDATION_MISSING:
            return "STRUCTURAL_VALIDATION_MISSING";
        case ConfigDecision::SEMANTIC_VALIDATION_MISSING:
            return "SEMANTIC_VALIDATION_MISSING";
        case ConfigDecision::MOTION_NOT_ALLOWED:
            return "MOTION_NOT_ALLOWED";
        case ConfigDecision::AUTHORIZATION_CLASS_DENIED:
            return "AUTHORIZATION_CLASS_DENIED";
        case ConfigDecision::VALIDITY_DEADLINE_INVALID:
            return "VALIDITY_DEADLINE_INVALID";
        case ConfigDecision::REVISION_NOT_MONOTONIC:
            return "REVISION_NOT_MONOTONIC";
        case ConfigDecision::GENERATION_NOT_MONOTONIC:
            return "GENERATION_NOT_MONOTONIC";
        case ConfigDecision::COMMIT_TOKEN_INVALID:
            return "COMMIT_TOKEN_INVALID";
        case ConfigDecision::NO_STAGED_CANDIDATE:
            return "NO_STAGED_CANDIDATE";
        case ConfigDecision::COMMIT_TOKEN_MISMATCH:
            return "COMMIT_TOKEN_MISMATCH";
        case ConfigDecision::NO_ACTIVE_CONFIG:
            return "NO_ACTIVE_CONFIG";
        case ConfigDecision::REVOKED:
            return "REVOKED";
        case ConfigDecision::CONFIG_EXPIRED:
            return "CONFIG_EXPIRED";
        case ConfigDecision::COMMAND_GENERATION_INVALID:
            return "COMMAND_GENERATION_INVALID";
        case ConfigDecision::COMMAND_GENERATION_REPLAYED:
            return "COMMAND_GENERATION_REPLAYED";
    }
    return "UNKNOWN_CONFIG_DECISION";
}

ConfigIdentityGuard::ConfigIdentityGuard(
    const SchemaCompatibilityPolicy& policy)
    : policy_(policy),
      policy_valid_(policy.minimum_version != 0 &&
                    policy.maximum_version >= policy.minimum_version),
      active_present_(false),
      staged_present_(false),
      revoked_(false),
      active_(),
      staged_(),
      staged_token_(),
      highest_staged_revision_(0),
      highest_staged_generation_(0),
      last_command_generation_(0),
      time_initialized_(false),
      last_now_ms_(0) {}

ConfigDecision ConfigIdentityGuard::observeTime(uint64_t now_ms) {
    if (time_initialized_ && now_ms < last_now_ms_) {
        revoked_ = true;
        clearStaged();
        return ConfigDecision::CLOCK_REGRESSION;
    }
    time_initialized_ = true;
    last_now_ms_ = now_ms;
    return ConfigDecision::ALLOWED;
}

bool ConfigIdentityGuard::schemaCompatible(uint16_t schema_version) const {
    return policy_valid_ && schema_version >= policy_.minimum_version &&
           schema_version <= policy_.maximum_version;
}

ConfigDecision ConfigIdentityGuard::validateIdentity(
    const ConfigIdentity& identity) const {
    if (!ConfigIdValid(identity.config_id) || !DigestValid(identity.digest) ||
        identity.revision == 0 || identity.schema_version == 0) {
        return ConfigDecision::IDENTITY_INVALID;
    }
    return ConfigDecision::ALLOWED;
}

ConfigDecision ConfigIdentityGuard::compareIdentity(
    const ConfigIdentity& actual, const ConfigIdentity& expected) const {
    if (!ConfigIdsEqual(actual.config_id, expected.config_id)) {
        return ConfigDecision::CONFIG_ID_MISMATCH;
    }
    if (!DigestsEqual(actual.digest, expected.digest)) {
        return ConfigDecision::DIGEST_MISMATCH;
    }
    if (actual.revision != expected.revision) {
        return ConfigDecision::REVISION_MISMATCH;
    }
    if (actual.schema_version != expected.schema_version) {
        return ConfigDecision::SCHEMA_MISMATCH;
    }
    return ConfigDecision::ALLOWED;
}

void ConfigIdentityGuard::clearStaged() {
    staged_present_ = false;
    staged_ = ConfigCandidate();
    staged_token_ = GenerationCommitToken();
}

ConfigDecision ConfigIdentityGuard::stageCandidate(
    uint64_t now_ms, const ConfigCandidate& candidate,
    const ConfigExpectation& expectation,
    const GenerationCommitToken& commit_token) {
    ConfigDecision decision = observeTime(now_ms);
    if (decision != ConfigDecision::ALLOWED) {
        return decision;
    }

    // A new staging attempt invalidates any abandoned staged transaction but
    // cannot alter the currently active configuration.
    clearStaged();
    if (!policy_valid_) {
        return ConfigDecision::SCHEMA_POLICY_INVALID;
    }
    decision = validateIdentity(candidate.identity);
    if (decision != ConfigDecision::ALLOWED) {
        return decision;
    }
    decision = validateIdentity(expectation.identity);
    if (decision != ConfigDecision::ALLOWED) {
        return decision;
    }
    decision = compareIdentity(candidate.identity, expectation.identity);
    if (decision != ConfigDecision::ALLOWED) {
        return decision;
    }
    if (candidate.generation == 0 ||
        candidate.generation != expectation.generation) {
        return ConfigDecision::GENERATION_MISMATCH;
    }
    if (!candidate.structural_validated) {
        return ConfigDecision::STRUCTURAL_VALIDATION_MISSING;
    }
    if (!candidate.semantic_validated) {
        return ConfigDecision::SEMANTIC_VALIDATION_MISSING;
    }
    if (!schemaCompatible(candidate.identity.schema_version)) {
        return ConfigDecision::SCHEMA_MISMATCH;
    }
    if (!candidate.motion_allowed) {
        return ConfigDecision::MOTION_NOT_ALLOWED;
    }
    if (candidate.authorization_class != AuthorizationClass::MOTION) {
        return ConfigDecision::AUTHORIZATION_CLASS_DENIED;
    }
    if (candidate.validity_deadline_ms <= now_ms) {
        return ConfigDecision::VALIDITY_DEADLINE_INVALID;
    }
    if (candidate.identity.revision <= highest_staged_revision_) {
        return ConfigDecision::REVISION_NOT_MONOTONIC;
    }
    if (candidate.generation <= highest_staged_generation_) {
        return ConfigDecision::GENERATION_NOT_MONOTONIC;
    }
    if (!TokenValid(commit_token) ||
        commit_token.generation != candidate.generation) {
        return ConfigDecision::COMMIT_TOKEN_INVALID;
    }

    staged_ = candidate;
    staged_token_ = commit_token;
    staged_present_ = true;
    highest_staged_revision_ = candidate.identity.revision;
    highest_staged_generation_ = candidate.generation;
    return ConfigDecision::ALLOWED;
}

ConfigDecision ConfigIdentityGuard::commitStaged(
    uint64_t now_ms, const GenerationCommitToken& commit_token) {
    ConfigDecision decision = observeTime(now_ms);
    if (decision != ConfigDecision::ALLOWED) {
        return decision;
    }
    if (!staged_present_) {
        return ConfigDecision::NO_STAGED_CANDIDATE;
    }
    if (staged_.validity_deadline_ms <= now_ms) {
        clearStaged();
        return ConfigDecision::VALIDITY_DEADLINE_INVALID;
    }
    if (!TokenValid(commit_token)) {
        return ConfigDecision::COMMIT_TOKEN_INVALID;
    }
    if (!TokensEqual(commit_token, staged_token_)) {
        return commit_token.generation == staged_.generation
                   ? ConfigDecision::COMMIT_TOKEN_MISMATCH
                   : ConfigDecision::GENERATION_MISMATCH;
    }

    active_ = staged_;
    active_present_ = true;
    revoked_ = false;
    last_command_generation_ = 0;
    clearStaged();
    return ConfigDecision::ALLOWED;
}

ConfigDecision ConfigIdentityGuard::revoke(uint64_t now_ms) {
    ConfigDecision decision = observeTime(now_ms);
    if (decision != ConfigDecision::ALLOWED) {
        return decision;
    }
    revoked_ = true;
    clearStaged();
    return ConfigDecision::ALLOWED;
}

ConfigDecision ConfigIdentityGuard::activeUsable(uint64_t now_ms) const {
    if (!active_present_) {
        return ConfigDecision::NO_ACTIVE_CONFIG;
    }
    if (revoked_) {
        return ConfigDecision::REVOKED;
    }
    if (now_ms >= active_.validity_deadline_ms) {
        return ConfigDecision::CONFIG_EXPIRED;
    }
    return ConfigDecision::ALLOWED;
}

ConfigDecision ConfigIdentityGuard::compareReference(
    const ConfigReference& reference) const {
    ConfigDecision decision = compareIdentity(reference.identity,
                                              active_.identity);
    if (decision != ConfigDecision::ALLOWED) {
        return decision;
    }
    if (reference.generation != active_.generation) {
        return ConfigDecision::GENERATION_MISMATCH;
    }
    if (reference.authorization_class != active_.authorization_class ||
        reference.authorization_class != AuthorizationClass::MOTION) {
        return ConfigDecision::AUTHORIZATION_CLASS_DENIED;
    }
    return ConfigDecision::ALLOWED;
}

ConfigDecision ConfigIdentityGuard::authorizeArm(
    uint64_t now_ms, const ConfigReference& reference) {
    ConfigDecision decision = observeTime(now_ms);
    if (decision != ConfigDecision::ALLOWED) {
        return decision;
    }
    decision = activeUsable(now_ms);
    if (decision != ConfigDecision::ALLOWED) {
        return decision;
    }
    return compareReference(reference);
}

ConfigDecision ConfigIdentityGuard::authorizeTransmit(
    uint64_t now_ms, const CommandAdmissionProof& proof) {
    ConfigDecision decision = observeTime(now_ms);
    if (decision != ConfigDecision::ALLOWED) {
        return decision;
    }
    decision = activeUsable(now_ms);
    if (decision != ConfigDecision::ALLOWED) {
        return decision;
    }
    decision = compareReference(proof.config);
    if (decision != ConfigDecision::ALLOWED) {
        return decision;
    }
    if (proof.command_generation == 0) {
        return ConfigDecision::COMMAND_GENERATION_INVALID;
    }
    if (proof.command_generation <= last_command_generation_) {
        return ConfigDecision::COMMAND_GENERATION_REPLAYED;
    }
    last_command_generation_ = proof.command_generation;
    return ConfigDecision::ALLOWED;
}

ConfigGuardSnapshot ConfigIdentityGuard::snapshot() const {
    ConfigGuardSnapshot result = {};
    result.active_present = active_present_;
    result.staged_present = staged_present_;
    result.revoked = revoked_;
    result.usable_at_last_observed_time =
        active_present_ && !revoked_ &&
        last_now_ms_ < active_.validity_deadline_ms;
    result.active = active_;
    result.last_command_generation = last_command_generation_;
    return result;
}

}  // namespace safety
}  // namespace myactuator
