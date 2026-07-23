#include "config_identity_guard.h"
#include "dropbear_config.generated.hpp"
#include "safety_supervisor.h"

#include <stdint.h>

#include <cstring>
#include <iostream>
#include <string_view>

namespace generated = myactuator::generated::dropbear;
namespace safety = myactuator::safety;

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

uint8_t HexNibble(char value) {
    if (value >= '0' && value <= '9') {
        return static_cast<uint8_t>(value - '0');
    }
    if (value >= 'a' && value <= 'f') {
        return static_cast<uint8_t>(value - 'a' + 10);
    }
    return 0xffU;
}

safety::ConfigIdentity GeneratedIdentity() {
    safety::ConfigIdentity result = {};
    const std::string_view id = generated::kConfigurationId;
    CHECK(id.size() <= safety::kConfigIdCapacity);
    result.config_id.length = static_cast<uint8_t>(id.size());
    std::memcpy(result.config_id.bytes, id.data(), id.size());

    const std::string_view digest = generated::kCanonicalDigest;
    CHECK(digest.size() == safety::kSha256DigestSize * 2U);
    for (size_t index = 0; index < safety::kSha256DigestSize; ++index) {
        const uint8_t high = HexNibble(digest[index * 2U]);
        const uint8_t low = HexNibble(digest[index * 2U + 1U]);
        CHECK(high <= 0x0fU);
        CHECK(low <= 0x0fU);
        result.digest.bytes[index] = static_cast<uint8_t>((high << 4U) | low);
    }
    result.revision = generated::kConfigurationRevision;
    result.schema_version = 1U;
    return result;
}

safety::Prerequisites Prerequisites(bool configuration_valid) {
    safety::Prerequisites prerequisites;
    prerequisites.configuration_valid = configuration_valid;
    prerequisites.expected_nodes_present = true;
    prerequisites.transport_ready = true;
    prerequisites.safety_interlock_ready = true;
    prerequisites.external_faults_clear = true;
    prerequisites.motor_off_confirmed = true;
    return prerequisites;
}

}  // namespace

int main() {
    CHECK(generated::kConfigurationState == "incomplete_observation");
    CHECK(!generated::kMotionEnableAllowed);
    CHECK(generated::kJoints.size() == 12U);
    CHECK(generated::kActuators.size() == 12U);

    const safety::ConfigIdentity identity = GeneratedIdentity();
    safety::ConfigCandidate candidate = {};
    candidate.identity = identity;
    candidate.generation = 1U;
    candidate.validity_deadline_ms = 1000U;
    candidate.structural_validated = true;
    candidate.semantic_validated = true;
    candidate.motion_allowed = generated::kMotionEnableAllowed;
    candidate.authorization_class = safety::AuthorizationClass::OBSERVE_ONLY;

    safety::ConfigExpectation expectation = {};
    expectation.identity = identity;
    expectation.generation = candidate.generation;
    safety::GenerationCommitToken token = {};
    token.generation = candidate.generation;
    token.bytes[0] = 1U;

    safety::SchemaCompatibilityPolicy policy = {1U, 1U};
    safety::ConfigIdentityGuard guard(policy);
    CHECK(guard.stageCandidate(0U, candidate, expectation, token) ==
          safety::ConfigDecision::MOTION_NOT_ALLOWED);
    CHECK(!guard.snapshot().active_present);
    CHECK(guard.commitStaged(0U, token) ==
          safety::ConfigDecision::NO_STAGED_CANDIDATE);

    safety::Configuration supervisor_config(
        0x12345678U, 1U, 100U, 10U, 1U << 1U, 1U << 1U);
    safety::SafetySupervisor supervisor(supervisor_config);
    CHECK(supervisor.completeBoot(0U, Prerequisites(false)) ==
          safety::Result::PREREQUISITES_NOT_MET);
    CHECK(!supervisor.outputsPermitted());

    if (failures != 0) {
        std::cerr << failures << " of " << checks << " checks failed\n";
        return 1;
    }
    std::cout << "GENERATED_CONFIG_GUARD_OK " << checks << " checks\n";
    return 0;
}
