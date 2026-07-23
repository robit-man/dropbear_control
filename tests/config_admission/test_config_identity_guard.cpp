#include "config_identity_guard.h"
#include "safety_supervisor.h"

#include <stdint.h>

#include <cstring>
#include <iostream>

namespace cfg = myactuator::safety;

namespace {

int checks = 0;
int failures = 0;

#define CHECK(condition)                                                        \
    do {                                                                        \
        ++checks;                                                               \
        if (!(condition)) {                                                     \
            ++failures;                                                         \
            std::cerr << "FAIL " << __FILE__ << ':' << __LINE__ << ": "       \
                      << #condition << '\n';                                   \
        }                                                                       \
    } while (false)

const uint32_t kSession = 0xA55A1234UL;

cfg::SchemaCompatibilityPolicy Policy(uint16_t minimum = 1,
                                      uint16_t maximum = 2) {
    cfg::SchemaCompatibilityPolicy policy = {minimum, maximum};
    return policy;
}

cfg::ConfigIdentity Identity(const char* id,
                             uint8_t digest_seed,
                             uint64_t revision,
                             uint16_t schema = 1) {
    cfg::ConfigIdentity identity = {};
    const size_t length = std::strlen(id);
    CHECK(length <= cfg::kConfigIdCapacity);
    identity.config_id.length = static_cast<uint8_t>(length);
    std::memcpy(identity.config_id.bytes, id, length);
    for (size_t index = 0; index < cfg::kSha256DigestSize; ++index) {
        identity.digest.bytes[index] =
            static_cast<uint8_t>(digest_seed + index);
    }
    identity.revision = revision;
    identity.schema_version = schema;
    return identity;
}

cfg::ConfigCandidate Candidate(const cfg::ConfigIdentity& identity,
                               uint64_t generation,
                               uint64_t deadline_ms) {
    cfg::ConfigCandidate candidate = {};
    candidate.identity = identity;
    candidate.generation = generation;
    candidate.validity_deadline_ms = deadline_ms;
    candidate.structural_validated = true;
    candidate.semantic_validated = true;
    candidate.motion_allowed = true;
    candidate.authorization_class = cfg::AuthorizationClass::MOTION;
    return candidate;
}

cfg::ConfigExpectation Expectation(const cfg::ConfigCandidate& candidate) {
    cfg::ConfigExpectation expectation = {};
    expectation.identity = candidate.identity;
    expectation.generation = candidate.generation;
    return expectation;
}

cfg::GenerationCommitToken Token(uint64_t generation, uint8_t seed) {
    cfg::GenerationCommitToken token = {};
    token.generation = generation;
    for (size_t index = 0; index < cfg::kCommitTokenSize; ++index) {
        token.bytes[index] = static_cast<uint8_t>(seed + index);
    }
    return token;
}

cfg::ConfigReference Reference(const cfg::ConfigCandidate& candidate) {
    cfg::ConfigReference reference = {};
    reference.identity = candidate.identity;
    reference.generation = candidate.generation;
    reference.authorization_class = candidate.authorization_class;
    return reference;
}

cfg::CommandAdmissionProof Proof(const cfg::ConfigCandidate& candidate,
                                 uint64_t command_generation) {
    cfg::CommandAdmissionProof proof = {};
    proof.config = Reference(candidate);
    proof.command_generation = command_generation;
    return proof;
}

cfg::Configuration SupervisorConfiguration() {
    return cfg::Configuration(kSession, 10, 1000, 20, 0x1, 0x1);
}

cfg::Prerequisites Prerequisites(bool configuration_valid) {
    cfg::Prerequisites prerequisites;
    prerequisites.configuration_valid = configuration_valid;
    prerequisites.expected_nodes_present = true;
    prerequisites.transport_ready = true;
    prerequisites.safety_interlock_ready = true;
    prerequisites.external_faults_clear = true;
    prerequisites.motor_off_confirmed = true;
    return prerequisites;
}

bool SameIdentity(const cfg::ConfigIdentity& left,
                  const cfg::ConfigIdentity& right) {
    return std::memcmp(&left, &right, sizeof(left)) == 0;
}

void Activate(cfg::ConfigIdentityGuard* guard,
              const cfg::ConfigCandidate& candidate,
              const cfg::GenerationCommitToken& token,
              uint64_t now_ms = 0) {
    CHECK(guard->stageCandidate(now_ms, candidate, Expectation(candidate), token) ==
          cfg::ConfigDecision::ALLOWED);
    CHECK(guard->commitStaged(now_ms, token) == cfg::ConfigDecision::ALLOWED);
}

void TestFixedSizeAndStableDecisionCodes() {
    static_assert(sizeof(cfg::Sha256Digest) == 32,
                  "SHA-256 identity must remain exactly 32 bytes");
    static_assert(sizeof(((cfg::BoundedConfigId*)0)->bytes) == 32,
                  "configuration ID storage must remain bounded");
    static_assert(sizeof(((cfg::GenerationCommitToken*)0)->bytes) == 16,
                  "commit token storage must remain bounded");

    CHECK(static_cast<uint8_t>(cfg::ConfigDecision::ALLOWED) == 0);
    CHECK(static_cast<uint8_t>(cfg::ConfigDecision::NO_ACTIVE_CONFIG) == 19);
    CHECK(static_cast<uint8_t>(cfg::ConfigDecision::COMMAND_GENERATION_REPLAYED) ==
          23);
    CHECK(std::strcmp(cfg::DecisionCode(cfg::ConfigDecision::DIGEST_MISMATCH),
                      "DIGEST_MISMATCH") == 0);
    CHECK(std::strcmp(cfg::DecisionCode(cfg::ConfigDecision::REVOKED),
                      "REVOKED") == 0);
    CHECK(std::strcmp(cfg::DecisionCode(
                          cfg::ConfigDecision::COMMAND_GENERATION_REPLAYED),
                      "COMMAND_GENERATION_REPLAYED") == 0);
}

void TestBootHasNoTrustedActiveConfigurationAndNoAutoEnable() {
    cfg::ConfigIdentityGuard guard(Policy());
    const cfg::ConfigCandidate candidate = Candidate(Identity("dropbear", 1, 1),
                                                     1, 100);
    CHECK(!guard.snapshot().active_present);
    CHECK(!guard.snapshot().usable_at_last_observed_time);
    CHECK(guard.authorizeArm(0, Reference(candidate)) ==
          cfg::ConfigDecision::NO_ACTIVE_CONFIG);
    CHECK(guard.authorizeTransmit(0, Proof(candidate, 1)) ==
          cfg::ConfigDecision::NO_ACTIVE_CONFIG);

    cfg::SafetySupervisor supervisor(SupervisorConfiguration());
    CHECK(supervisor.state() == cfg::State::BOOT);
    Activate(&guard, candidate, Token(1, 0x10));
    // Config activation is intentionally separate from motor safety state.
    CHECK(supervisor.state() == cfg::State::BOOT);
    CHECK(!supervisor.outputsPermitted());
}

void TestSchemaAndExternalValidationAreMandatory() {
    const cfg::ConfigCandidate base = Candidate(Identity("dropbear", 1, 1),
                                                1, 100);
    const cfg::GenerationCommitToken token = Token(1, 0x20);

    cfg::ConfigIdentityGuard invalid_policy(Policy(0, 1));
    CHECK(invalid_policy.stageCandidate(0, base, Expectation(base), token) ==
          cfg::ConfigDecision::SCHEMA_POLICY_INVALID);

    cfg::ConfigCandidate unsupported = base;
    unsupported.identity.schema_version = 3;
    cfg::ConfigIdentityGuard schema_guard(Policy());
    CHECK(schema_guard.stageCandidate(0, unsupported,
                                      Expectation(unsupported), token) ==
          cfg::ConfigDecision::SCHEMA_MISMATCH);

    cfg::ConfigCandidate structural = base;
    structural.structural_validated = false;
    cfg::ConfigIdentityGuard structural_guard(Policy());
    CHECK(structural_guard.stageCandidate(0, structural,
                                          Expectation(structural), token) ==
          cfg::ConfigDecision::STRUCTURAL_VALIDATION_MISSING);

    cfg::ConfigCandidate semantic = base;
    semantic.semantic_validated = false;
    cfg::ConfigIdentityGuard semantic_guard(Policy());
    CHECK(semantic_guard.stageCandidate(0, semantic, Expectation(semantic),
                                        token) ==
          cfg::ConfigDecision::SEMANTIC_VALIDATION_MISSING);

    cfg::ConfigCandidate no_motion = base;
    no_motion.motion_allowed = false;
    cfg::ConfigIdentityGuard motion_guard(Policy());
    CHECK(motion_guard.stageCandidate(0, no_motion, Expectation(no_motion),
                                      token) ==
          cfg::ConfigDecision::MOTION_NOT_ALLOWED);

    cfg::ConfigCandidate observe = base;
    observe.authorization_class = cfg::AuthorizationClass::OBSERVE_ONLY;
    cfg::ConfigIdentityGuard authorization_guard(Policy());
    CHECK(authorization_guard.stageCandidate(0, observe, Expectation(observe),
                                             token) ==
          cfg::ConfigDecision::AUTHORIZATION_CLASS_DENIED);

    cfg::ConfigCandidate expired = base;
    expired.validity_deadline_ms = 10;
    cfg::ConfigIdentityGuard expiry_guard(Policy());
    CHECK(expiry_guard.stageCandidate(10, expired, Expectation(expired),
                                     token) ==
          cfg::ConfigDecision::VALIDITY_DEADLINE_INVALID);

    CHECK(!schema_guard.snapshot().active_present);
    CHECK(!structural_guard.snapshot().active_present);
    CHECK(!semantic_guard.snapshot().active_present);
    CHECK(!motion_guard.snapshot().active_present);
    CHECK(!authorization_guard.snapshot().active_present);
    CHECK(!expiry_guard.snapshot().active_present);
}

void TestIdentityExpectationMustMatchExactly() {
    const cfg::ConfigCandidate base = Candidate(Identity("dropbear", 3, 1),
                                                1, 100);
    const cfg::GenerationCommitToken token = Token(1, 0x30);

    struct Case {
        cfg::ConfigExpectation expectation;
        cfg::ConfigDecision decision;
    };
    Case cases[5] = {};
    for (size_t index = 0; index < 5; ++index) {
        cases[index].expectation = Expectation(base);
    }
    cases[0].expectation.identity.config_id.bytes[0] = 'x';
    cases[0].decision = cfg::ConfigDecision::CONFIG_ID_MISMATCH;
    cases[1].expectation.identity.digest.bytes[7] ^= 0x80;
    cases[1].decision = cfg::ConfigDecision::DIGEST_MISMATCH;
    cases[2].expectation.identity.revision = 2;
    cases[2].decision = cfg::ConfigDecision::REVISION_MISMATCH;
    cases[3].expectation.identity.schema_version = 2;
    cases[3].decision = cfg::ConfigDecision::SCHEMA_MISMATCH;
    cases[4].expectation.generation = 2;
    cases[4].decision = cfg::ConfigDecision::GENERATION_MISMATCH;

    for (size_t index = 0; index < 5; ++index) {
        cfg::ConfigIdentityGuard guard(Policy());
        CHECK(guard.stageCandidate(0, base, cases[index].expectation, token) ==
              cases[index].decision);
        CHECK(!guard.snapshot().active_present);
    }
}

void TestInvalidIdentityAndTokenAreRejected() {
    cfg::ConfigCandidate candidate = Candidate(Identity("dropbear", 1, 1),
                                               1, 100);
    cfg::GenerationCommitToken token = Token(1, 0x40);

    candidate.identity.config_id.length = 0;
    cfg::ConfigIdentityGuard id_guard(Policy());
    CHECK(id_guard.stageCandidate(0, candidate, Expectation(candidate), token) ==
          cfg::ConfigDecision::IDENTITY_INVALID);

    candidate = Candidate(Identity("dropbear", 1, 1), 1, 100);
    std::memset(candidate.identity.digest.bytes, 0,
                sizeof(candidate.identity.digest.bytes));
    cfg::ConfigIdentityGuard digest_guard(Policy());
    CHECK(digest_guard.stageCandidate(0, candidate, Expectation(candidate),
                                      token) ==
          cfg::ConfigDecision::IDENTITY_INVALID);

    candidate = Candidate(Identity("dropbear", 1, 1), 1, 100);
    std::memset(token.bytes, 0, sizeof(token.bytes));
    cfg::ConfigIdentityGuard token_guard(Policy());
    CHECK(token_guard.stageCandidate(0, candidate, Expectation(candidate),
                                     token) ==
          cfg::ConfigDecision::COMMIT_TOKEN_INVALID);
}

void TestAtomicUpdateRollbackAndExactCommitCorrelation() {
    cfg::ConfigIdentityGuard guard(Policy());
    const cfg::ConfigCandidate first = Candidate(Identity("dropbear", 1, 1),
                                                 1, 100);
    Activate(&guard, first, Token(1, 0x10));

    const cfg::ConfigCandidate second = Candidate(Identity("dropbear", 2, 2),
                                                  2, 200);
    const cfg::GenerationCommitToken second_token = Token(2, 0x20);
    CHECK(guard.stageCandidate(1, second, Expectation(second), second_token) ==
          cfg::ConfigDecision::ALLOWED);

    cfg::GenerationCommitToken wrong_bytes = second_token;
    wrong_bytes.bytes[4] ^= 0x01;
    CHECK(guard.commitStaged(1, wrong_bytes) ==
          cfg::ConfigDecision::COMMIT_TOKEN_MISMATCH);
    cfg::ConfigGuardSnapshot snapshot = guard.snapshot();
    CHECK(snapshot.active_present);
    CHECK(snapshot.staged_present);
    CHECK(SameIdentity(snapshot.active.identity, first.identity));
    CHECK(snapshot.active.generation == first.generation);

    CHECK(guard.commitStaged(2, Token(3, 0x20)) ==
          cfg::ConfigDecision::GENERATION_MISMATCH);
    CHECK(SameIdentity(guard.snapshot().active.identity, first.identity));
    CHECK(guard.commitStaged(2, second_token) == cfg::ConfigDecision::ALLOWED);
    snapshot = guard.snapshot();
    CHECK(!snapshot.staged_present);
    CHECK(SameIdentity(snapshot.active.identity, second.identity));
    CHECK(snapshot.active.generation == 2);

    const cfg::ConfigCandidate expires_before_commit =
        Candidate(Identity("dropbear", 3, 3), 3, 4);
    const cfg::GenerationCommitToken third_token = Token(3, 0x30);
    CHECK(guard.stageCandidate(3, expires_before_commit,
                               Expectation(expires_before_commit),
                               third_token) == cfg::ConfigDecision::ALLOWED);
    CHECK(guard.commitStaged(4, third_token) ==
          cfg::ConfigDecision::VALIDITY_DEADLINE_INVALID);
    snapshot = guard.snapshot();
    CHECK(!snapshot.staged_present);
    CHECK(SameIdentity(snapshot.active.identity, second.identity));
    CHECK(snapshot.active.generation == 2);
}

void TestInvalidOrStaleCandidateNeverReplacesActive() {
    cfg::ConfigIdentityGuard guard(Policy());
    const cfg::ConfigCandidate active = Candidate(Identity("dropbear", 5, 5),
                                                  5, 500);
    Activate(&guard, active, Token(5, 0x50));

    cfg::ConfigCandidate invalid = Candidate(Identity("dropbear", 6, 6),
                                             6, 600);
    invalid.semantic_validated = false;
    CHECK(guard.stageCandidate(1, invalid, Expectation(invalid),
                               Token(6, 0x60)) ==
          cfg::ConfigDecision::SEMANTIC_VALIDATION_MISSING);
    CHECK(SameIdentity(guard.snapshot().active.identity, active.identity));
    CHECK(guard.commitStaged(1, Token(6, 0x60)) ==
          cfg::ConfigDecision::NO_STAGED_CANDIDATE);

    const cfg::ConfigCandidate stale_revision =
        Candidate(Identity("dropbear", 7, 5), 6, 600);
    CHECK(guard.stageCandidate(2, stale_revision,
                               Expectation(stale_revision), Token(6, 0x61)) ==
          cfg::ConfigDecision::REVISION_NOT_MONOTONIC);
    CHECK(SameIdentity(guard.snapshot().active.identity, active.identity));

    const cfg::ConfigCandidate stale_generation =
        Candidate(Identity("dropbear", 8, 6), 5, 600);
    CHECK(guard.stageCandidate(2, stale_generation,
                               Expectation(stale_generation), Token(5, 0x62)) ==
          cfg::ConfigDecision::GENERATION_NOT_MONOTONIC);
    CHECK(SameIdentity(guard.snapshot().active.identity, active.identity));
}

void TestArmAndTransmitRequireExactActiveIdentity() {
    cfg::ConfigIdentityGuard guard(Policy());
    const cfg::ConfigCandidate active = Candidate(Identity("dropbear", 9, 4),
                                                  7, 100);
    Activate(&guard, active, Token(7, 0x70));
    const cfg::ConfigReference exact = Reference(active);
    CHECK(guard.authorizeArm(1, exact) == cfg::ConfigDecision::ALLOWED);

    cfg::ConfigReference altered = exact;
    altered.identity.config_id.bytes[1] ^= 0x01;
    CHECK(guard.authorizeArm(1, altered) ==
          cfg::ConfigDecision::CONFIG_ID_MISMATCH);
    altered = exact;
    altered.identity.digest.bytes[31] ^= 0x01;
    CHECK(guard.authorizeArm(1, altered) == cfg::ConfigDecision::DIGEST_MISMATCH);
    altered = exact;
    --altered.identity.revision;
    CHECK(guard.authorizeArm(1, altered) ==
          cfg::ConfigDecision::REVISION_MISMATCH);
    altered = exact;
    altered.identity.schema_version = 2;
    CHECK(guard.authorizeArm(1, altered) == cfg::ConfigDecision::SCHEMA_MISMATCH);
    altered = exact;
    --altered.generation;
    CHECK(guard.authorizeArm(1, altered) ==
          cfg::ConfigDecision::GENERATION_MISMATCH);
    altered = exact;
    altered.authorization_class = cfg::AuthorizationClass::OBSERVE_ONLY;
    CHECK(guard.authorizeArm(1, altered) ==
          cfg::ConfigDecision::AUTHORIZATION_CLASS_DENIED);

    CHECK(guard.authorizeTransmit(2, Proof(active, 0)) ==
          cfg::ConfigDecision::COMMAND_GENERATION_INVALID);
    CHECK(guard.authorizeTransmit(2, Proof(active, 5)) ==
          cfg::ConfigDecision::ALLOWED);
    CHECK(guard.authorizeTransmit(2, Proof(active, 5)) ==
          cfg::ConfigDecision::COMMAND_GENERATION_REPLAYED);
    CHECK(guard.authorizeTransmit(2, Proof(active, 4)) ==
          cfg::ConfigDecision::COMMAND_GENERATION_REPLAYED);
    CHECK(guard.authorizeTransmit(2, Proof(active, 6)) ==
          cfg::ConfigDecision::ALLOWED);
    CHECK(guard.snapshot().last_command_generation == 6);
}

void TestExpiryRevokeAndClockRegressionDenyImmediately() {
    const cfg::ConfigCandidate active = Candidate(Identity("dropbear", 3, 1),
                                                  1, 20);
    cfg::ConfigIdentityGuard expiry(Policy());
    Activate(&expiry, active, Token(1, 0x10), 10);
    CHECK(expiry.authorizeArm(19, Reference(active)) ==
          cfg::ConfigDecision::ALLOWED);
    CHECK(expiry.authorizeArm(20, Reference(active)) ==
          cfg::ConfigDecision::CONFIG_EXPIRED);
    CHECK(expiry.authorizeTransmit(20, Proof(active, 1)) ==
          cfg::ConfigDecision::CONFIG_EXPIRED);

    cfg::ConfigIdentityGuard revoked(Policy());
    Activate(&revoked, active, Token(1, 0x11), 10);
    CHECK(revoked.revoke(11) == cfg::ConfigDecision::ALLOWED);
    CHECK(revoked.snapshot().revoked);
    CHECK(revoked.authorizeArm(11, Reference(active)) ==
          cfg::ConfigDecision::REVOKED);
    CHECK(revoked.authorizeTransmit(11, Proof(active, 1)) ==
          cfg::ConfigDecision::REVOKED);

    cfg::ConfigIdentityGuard clock(Policy());
    Activate(&clock, active, Token(1, 0x12), 10);
    CHECK(clock.authorizeArm(15, Reference(active)) ==
          cfg::ConfigDecision::ALLOWED);
    CHECK(clock.authorizeArm(14, Reference(active)) ==
          cfg::ConfigDecision::CLOCK_REGRESSION);
    CHECK(clock.snapshot().revoked);
    CHECK(clock.authorizeArm(16, Reference(active)) ==
          cfg::ConfigDecision::REVOKED);
}

void TestCompositionWithSafetySupervisor() {
    const cfg::ConfigCandidate active = Candidate(Identity("dropbear", 4, 1),
                                                  1, 100);
    const cfg::ConfigReference reference = Reference(active);

    // Missing configuration cannot satisfy the supervisor prerequisite.
    cfg::ConfigIdentityGuard missing(Policy());
    cfg::SafetySupervisor missing_supervisor(SupervisorConfiguration());
    const bool missing_allowed =
        missing.authorizeArm(0, reference) == cfg::ConfigDecision::ALLOWED;
    CHECK(!missing_allowed);
    CHECK(missing_supervisor.completeBoot(0, Prerequisites(missing_allowed)) ==
          cfg::Result::PREREQUISITES_NOT_MET);
    CHECK(missing_supervisor.state() == cfg::State::DISCOVERY);
    CHECK(!missing_supervisor.outputsPermitted());

    cfg::ConfigIdentityGuard guard(Policy());
    Activate(&guard, active, Token(1, 0x20));
    cfg::SafetySupervisor supervisor(SupervisorConfiguration());
    const bool arm_allowed =
        guard.authorizeArm(0, reference) == cfg::ConfigDecision::ALLOWED;
    CHECK(supervisor.completeBoot(0, Prerequisites(arm_allowed)) ==
          cfg::Result::OK);
    CHECK(supervisor.acquireLease(0, cfg::MessageStamp(1, kSession, 1), 50) ==
          cfg::Result::OK);
    CHECK(supervisor.enable(0, cfg::MessageStamp(1, kSession, 2)) ==
          cfg::Result::OK);
    CHECK(supervisor.outputsPermitted());

    // Tamper and stale config references are denied before the supervisor TX
    // sequence is consumed.
    cfg::CommandAdmissionProof tampered = Proof(active, 1);
    tampered.config.identity.digest.bytes[0] ^= 1;
    CHECK(guard.authorizeTransmit(1, tampered) ==
          cfg::ConfigDecision::DIGEST_MISMATCH);
    cfg::CommandAdmissionProof stale = Proof(active, 1);
    stale.config.generation = 0;
    CHECK(guard.authorizeTransmit(1, stale) ==
          cfg::ConfigDecision::GENERATION_MISMATCH);
    CHECK(supervisor.state() == cfg::State::ENABLED);

    CHECK(guard.authorizeTransmit(1, Proof(active, 1)) ==
          cfg::ConfigDecision::ALLOWED);
    CHECK(supervisor.authorizeCommand(
              1, cfg::MessageStamp(1, kSession, 3)) == cfg::Result::OK);
    CHECK(guard.authorizeTransmit(1, Proof(active, 1)) ==
          cfg::ConfigDecision::COMMAND_GENERATION_REPLAYED);

    // Revocation immediately closes the guard and is explicitly propagated
    // into the independent supervisor prerequisite boundary.
    CHECK(guard.revoke(2) == cfg::ConfigDecision::ALLOWED);
    CHECK(guard.authorizeTransmit(2, Proof(active, 2)) ==
          cfg::ConfigDecision::REVOKED);
    CHECK(guard.authorizeArm(2, reference) == cfg::ConfigDecision::REVOKED);
    CHECK(supervisor.updatePrerequisites(2, Prerequisites(false)) ==
          cfg::Result::PREREQUISITES_NOT_MET);
    CHECK(supervisor.state() == cfg::State::FAULT);
    CHECK(!supervisor.outputsPermitted());
}

}  // namespace

int main() {
    TestFixedSizeAndStableDecisionCodes();
    TestBootHasNoTrustedActiveConfigurationAndNoAutoEnable();
    TestSchemaAndExternalValidationAreMandatory();
    TestIdentityExpectationMustMatchExactly();
    TestInvalidIdentityAndTokenAreRejected();
    TestAtomicUpdateRollbackAndExactCommitCorrelation();
    TestInvalidOrStaleCandidateNeverReplacesActive();
    TestArmAndTransmitRequireExactActiveIdentity();
    TestExpiryRevokeAndClockRegressionDenyImmediately();
    TestCompositionWithSafetySupervisor();

    if (failures != 0) {
        std::cerr << failures << " of " << checks << " checks failed\n";
        return 1;
    }
    std::cout << "CONFIG_IDENTITY_GUARD_OK " << checks << " checks\n";
    return 0;
}
