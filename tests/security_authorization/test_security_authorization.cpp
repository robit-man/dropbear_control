#include <stdio.h>
#include <string.h>

#include "security_authorization_core.h"

namespace sec = myactuator::security;

namespace {

int failures = 0;
#define CHECK(value)                                                         \
    do {                                                                     \
        if (!(value)) {                                                      \
            fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__,       \
                    __LINE__, #value);                                       \
            ++failures;                                                      \
        }                                                                    \
    } while (0)

sec::Digest Digest(uint8_t value) {
    sec::Digest output = {};
    for (size_t index = 0U; index < sec::kDigestSize; ++index)
        output.bytes[index] = value;
    return output;
}

sec::AuthorizationPolicy Policy() {
    sec::AuthorizationPolicy value = {};
    value.expected_config_digest = Digest(4U);
    value.expected_source_generation_digest = Digest(5U);
    value.expected_graph_generation_digest = Digest(6U);
    value.physical_actuation_enabled = false;
    value.remote_physical_actuation_enabled = false;
    value.remote_administration_enabled = false;
    return value;
}

sec::IdentityAssertion Identity() {
    sec::IdentityAssertion value = {};
    value.actor_digest = Digest(1U);
    value.session_digest = Digest(2U);
    value.authentication_context_digest = Digest(3U);
    value.role = sec::Role::OPERATOR;
    value.authenticated = true;
    value.revoked = false;
    value.valid_from_ns = 100U;
    value.valid_until_ns = 1000U;
    return value;
}

sec::ApprovalAssertion Approval() {
    sec::ApprovalAssertion value = {};
    value.actor_digest = Digest(9U);
    value.authentication_context_digest = Digest(10U);
    value.role = sec::Role::EVIDENCE_REVIEWER;
    value.authenticated = true;
    value.revoked = false;
    value.valid_from_ns = 100U;
    value.valid_until_ns = 1000U;
    value.scope_digest = Digest(8U);
    return value;
}

sec::AuthorizationRequest Request() {
    sec::AuthorizationRequest value = {};
    value.action = sec::Action::SUBMIT_MOTION;
    value.target = sec::Target::PHYSICAL_REMOTE;
    value.safety_state = sec::SafetyState::ENABLED;
    value.session_digest = Digest(2U);
    value.correlation_digest = Digest(7U);
    value.sequence = 1U;
    value.now_ns = 500U;
    value.config_digest = Digest(4U);
    value.source_generation_digest = Digest(5U);
    value.graph_generation_digest = Digest(6U);
    value.artifact_digest = Digest(8U);
    value.lease_valid = true;
    value.safety_admission_ready = true;
    value.local_presence_verified = true;
    value.artifact_integrity_verified = true;
    value.rollback_guard_verified = true;
    value.approval_present = true;
    value.approval = Approval();
    return value;
}

sec::DecisionCode RunVariant(const char* variant) {
    sec::AuthorizationPolicy policy = Policy();
    sec::IdentityAssertion identity = Identity();
    sec::AuthorizationRequest request = Request();
    size_t normal_capacity = 16U;
    bool prefill = false;
    bool replay = false;
    bool normal_ready = true;
    bool safe_ready = true;

    if (strcmp(variant, "observer_read") == 0) {
        identity.role = sec::Role::OBSERVER;
        request.action = sec::Action::READ_STATE;
        request.target = sec::Target::OFFLINE;
    } else if (strcmp(variant, "diagnostic_read") == 0) {
        identity.role = sec::Role::DIAGNOSTIC_OPERATOR;
        request.action = sec::Action::READ_DIAGNOSTICS;
    } else if (strcmp(variant, "simulation_motion") == 0) {
        request.target = sec::Target::SIMULATION;
    } else if (strcmp(variant, "physical_remote_enabled") == 0) {
        policy.physical_actuation_enabled = true;
        policy.remote_physical_actuation_enabled = true;
    } else if (strcmp(variant, "safe_disable") == 0) {
        request.action = sec::Action::REQUEST_DISABLE;
    } else if (strcmp(variant, "config_activation") == 0) {
        identity.role = sec::Role::CONFIGURATION_MANAGER;
        request.action = sec::Action::ACTIVATE_CONFIG;
        request.target = sec::Target::PHYSICAL_LOCAL;
    } else if (strcmp(variant, "firmware_activation") == 0) {
        identity.role = sec::Role::FIRMWARE_MANAGER;
        request.action = sec::Action::ACTIVATE_FIRMWARE;
        request.target = sec::Target::PHYSICAL_LOCAL;
    } else if (strcmp(variant, "evidence_submit") == 0) {
        identity.role = sec::Role::EVIDENCE_REVIEWER;
        request.action = sec::Action::SUBMIT_EVIDENCE;
        request.target = sec::Target::OFFLINE;
    } else if (strcmp(variant, "unauthenticated") == 0) {
        identity.authenticated = false;
    } else if (strcmp(variant, "revoked") == 0) {
        identity.revoked = true;
    } else if (strcmp(variant, "session_not_yet_valid") == 0) {
        request.now_ns = 99U;
    } else if (strcmp(variant, "session_expired") == 0) {
        request.now_ns = 1000U;
    } else if (strcmp(variant, "session_mismatch") == 0) {
        request.session_digest = Digest(11U);
    } else if (strcmp(variant, "replay") == 0) {
        request.target = sec::Target::SIMULATION;
        replay = true;
    } else if (strcmp(variant, "role_denied") == 0) {
        identity.role = sec::Role::DIAGNOSTIC_OPERATOR;
        request.target = sec::Target::SIMULATION;
    } else if (strcmp(variant, "physical_disabled") == 0) {
    } else if (strcmp(variant, "remote_physical_disabled") == 0) {
        policy.physical_actuation_enabled = true;
    } else if (strcmp(variant, "remote_admin_disabled") == 0) {
        identity.role = sec::Role::CONFIGURATION_MANAGER;
        request.action = sec::Action::STAGE_CONFIG;
    } else if (strcmp(variant, "local_presence") == 0) {
        identity.role = sec::Role::CONFIGURATION_MANAGER;
        request.action = sec::Action::ACTIVATE_CONFIG;
        request.target = sec::Target::PHYSICAL_LOCAL;
        request.local_presence_verified = false;
    } else if (strcmp(variant, "config_missing") == 0) {
        request.target = sec::Target::SIMULATION;
        request.config_digest = Digest(0U);
    } else if (strcmp(variant, "config_mismatch") == 0) {
        request.target = sec::Target::SIMULATION;
        request.config_digest = Digest(11U);
    } else if (strcmp(variant, "source_missing") == 0) {
        request.target = sec::Target::SIMULATION;
        request.source_generation_digest = Digest(0U);
    } else if (strcmp(variant, "source_mismatch") == 0) {
        request.target = sec::Target::SIMULATION;
        request.source_generation_digest = Digest(11U);
    } else if (strcmp(variant, "graph_missing") == 0) {
        request.target = sec::Target::SIMULATION;
        request.graph_generation_digest = Digest(0U);
    } else if (strcmp(variant, "graph_mismatch") == 0) {
        request.target = sec::Target::SIMULATION;
        request.graph_generation_digest = Digest(11U);
    } else if (strcmp(variant, "lease_missing") == 0) {
        request.target = sec::Target::SIMULATION;
        request.lease_valid = false;
    } else if (strcmp(variant, "safety_missing") == 0) {
        request.target = sec::Target::SIMULATION;
        request.safety_admission_ready = false;
    } else if (strcmp(variant, "artifact_integrity") == 0) {
        identity.role = sec::Role::CONFIGURATION_MANAGER;
        request.action = sec::Action::STAGE_CONFIG;
        request.target = sec::Target::OFFLINE;
        request.artifact_integrity_verified = false;
    } else if (strcmp(variant, "rollback_missing") == 0) {
        identity.role = sec::Role::CONFIGURATION_MANAGER;
        request.action = sec::Action::ACTIVATE_CONFIG;
        request.target = sec::Target::OFFLINE;
        request.rollback_guard_verified = false;
    } else if (strcmp(variant, "approval_missing") == 0) {
        identity.role = sec::Role::CONFIGURATION_MANAGER;
        request.action = sec::Action::ACTIVATE_CONFIG;
        request.target = sec::Target::OFFLINE;
        request.approval_present = false;
    } else if (strcmp(variant, "approval_same_actor") == 0) {
        identity.role = sec::Role::CONFIGURATION_MANAGER;
        request.action = sec::Action::ACTIVATE_CONFIG;
        request.target = sec::Target::OFFLINE;
        request.approval.actor_digest = Digest(1U);
    } else if (strcmp(variant, "approval_wrong_role") == 0) {
        identity.role = sec::Role::CONFIGURATION_MANAGER;
        request.action = sec::Action::ACTIVATE_CONFIG;
        request.target = sec::Target::OFFLINE;
        request.approval.role = sec::Role::SAFETY_OPERATOR;
    } else if (strcmp(variant, "approval_scope") == 0) {
        identity.role = sec::Role::CONFIGURATION_MANAGER;
        request.action = sec::Action::ACTIVATE_CONFIG;
        request.target = sec::Target::OFFLINE;
        request.approval.scope_digest = Digest(11U);
    } else if (strcmp(variant, "audit_unavailable") == 0) {
        request.target = sec::Target::SIMULATION;
        normal_ready = false;
    } else if (strcmp(variant, "safe_audit_unavailable") == 0) {
        request.action = sec::Action::REQUEST_DISABLE;
        safe_ready = false;
    } else if (strcmp(variant, "audit_full") == 0) {
        identity.role = sec::Role::DIAGNOSTIC_OPERATOR;
        request.action = sec::Action::READ_STATE;
        request.target = sec::Target::OFFLINE;
        request.sequence = 2U;
        normal_capacity = 1U;
        prefill = true;
    } else if (strcmp(variant, "invalid_request") == 0) {
        identity.authenticated = false;
        request.correlation_digest = Digest(0U);
    } else {
        CHECK(false);
    }

    sec::AuthorizationEngine engine(policy, identity, normal_capacity, 2U);
    engine.setAuditHealth(normal_ready, safe_ready);
    if (prefill) {
        sec::AuthorizationRequest first = Request();
        first.action = sec::Action::READ_STATE;
        first.target = sec::Target::OFFLINE;
        CHECK(engine.authorize(first).code ==
              sec::DecisionCode::PASS_TO_NEXT_GATE);
    }
    if (replay)
        CHECK(engine.authorize(request).code ==
              sec::DecisionCode::PASS_TO_NEXT_GATE);
    const sec::AuthorizationResult result = engine.authorize(request);
    CHECK(!result.motion_authorized);
    CHECK(result.proceed_to_next_gate ==
          (result.code == sec::DecisionCode::PASS_TO_NEXT_GATE));
    return result.code;
}

bool Extract(const char* line, const char* prefix, char* output,
             size_t output_size) {
    const char* start = strstr(line, prefix);
    if (start == NULL) return false;
    start += strlen(prefix);
    const char* end = strchr(start, '"');
    if (end == NULL) return false;
    const size_t length = static_cast<size_t>(end - start);
    if (length == 0U || length >= output_size) return false;
    memcpy(output, start, length);
    output[length] = '\0';
    return true;
}

void TestSharedCorpus() {
    FILE* file =
        fopen("tests/security_authorization/golden_authorization.jsonl", "rb");
    CHECK(file != NULL);
    if (file == NULL) return;
    char line[512] = {};
    char variant[96] = {};
    char expected[96] = {};
    size_t count = 0U;
    while (fgets(line, sizeof(line), file) != NULL) {
        CHECK(strchr(line, '\n') != NULL);
        CHECK(Extract(line, "\"variant\":\"", variant, sizeof(variant)));
        CHECK(Extract(line, "\"expected_code\":\"", expected,
                      sizeof(expected)));
        const sec::DecisionCode actual = RunVariant(variant);
        CHECK(strcmp(sec::DecisionCodeName(actual), expected) == 0);
        ++count;
    }
    CHECK(!ferror(file));
    fclose(file);
    CHECK(count == 37U);
}

void TestRoleMatrixClosed() {
    static const bool expected[7][10] = {
        {true, false, false, false, false, false, false, false, false, false},
        {true, true, false, false, false, false, false, false, false, false},
        {true, true, true, true, false, false, false, false, false, false},
        {true, true, false, true, true, false, false, false, false, false},
        {true, true, false, false, false, true, true, false, false, false},
        {true, true, false, false, false, false, false, true, true, false},
        {true, true, false, false, false, false, false, false, false, true},
    };
    for (uint8_t role_index = 0U; role_index < 7U; ++role_index) {
        for (uint8_t action_index = 0U; action_index < 10U; ++action_index) {
            sec::IdentityAssertion identity = Identity();
            identity.role = static_cast<sec::Role>(role_index + 1U);
            sec::AuthorizationRequest request = Request();
            request.action = static_cast<sec::Action>(action_index + 1U);
            request.target = request.action == sec::Action::SUBMIT_MOTION
                                 ? sec::Target::SIMULATION
                                 : sec::Target::OFFLINE;
            sec::AuthorizationEngine engine(Policy(), identity, 2U, 1U);
            const sec::DecisionCode code = engine.authorize(request).code;
            CHECK((code != sec::DecisionCode::ROLE_ACTION_DENIED) ==
                  expected[role_index][action_index]);
        }
    }
}

void TestSequenceAndAuditLanes() {
    sec::IdentityAssertion diagnostic = Identity();
    diagnostic.role = sec::Role::DIAGNOSTIC_OPERATOR;
    sec::AuthorizationEngine replay_engine(Policy(), diagnostic, 3U, 1U);
    sec::AuthorizationRequest denied = Request();
    denied.target = sec::Target::SIMULATION;
    const sec::AuthorizationResult first = replay_engine.authorize(denied);
    CHECK(first.code == sec::DecisionCode::ROLE_ACTION_DENIED);
    CHECK(first.sequence_committed);
    denied.action = sec::Action::READ_STATE;
    denied.target = sec::Target::OFFLINE;
    const sec::AuthorizationResult replayed = replay_engine.authorize(denied);
    CHECK(replayed.code == sec::DecisionCode::REPLAY_OR_REORDER);
    CHECK(!replayed.sequence_committed);

    sec::AuthorizationEngine engine(Policy(), Identity(), 1U, 2U);
    sec::AuthorizationRequest request = Request();
    request.action = sec::Action::READ_DIAGNOSTICS;
    request.target = sec::Target::OFFLINE;
    CHECK(engine.authorize(request).code ==
          sec::DecisionCode::PASS_TO_NEXT_GATE);
    request.sequence = 2U;
    CHECK(engine.authorize(request).code ==
          sec::DecisionCode::AUDIT_CAPACITY_EXHAUSTED);
    for (uint64_t sequence = 3U; sequence <= 5U; ++sequence) {
        request.action = sec::Action::REQUEST_DISABLE;
        request.target = sec::Target::PHYSICAL_REMOTE;
        request.sequence = sequence;
        const sec::AuthorizationResult result = engine.authorize(request);
        CHECK(result.code == sec::DecisionCode::PASS_TO_NEXT_GATE);
        CHECK(result.audit_stored);
    }
    CHECK(engine.normalAuditSize() == 1U);
    CHECK(engine.safeAuditSize() == 2U);
    CHECK(engine.safeAuditOverwriteCount() == 1U);
    CHECK(engine.safeAuditAt(0U)->sequence == 4U);
    CHECK(engine.safeAuditAt(1U)->sequence == 5U);
}

void TestAuditContextAndClosedEnums() {
    sec::IdentityAssertion identity = Identity();
    identity.role = sec::Role::CONFIGURATION_MANAGER;
    sec::AuthorizationRequest request = Request();
    request.action = sec::Action::ACTIVATE_CONFIG;
    request.target = sec::Target::PHYSICAL_LOCAL;
    sec::AuthorizationEngine engine(Policy(), identity, 2U, 1U);
    const sec::AuthorizationResult result = engine.authorize(request);
    CHECK(result.code == sec::DecisionCode::PASS_TO_NEXT_GATE);
    CHECK(result.audit_stored);
    CHECK(sec::DigestEqual(result.audit_event.actor_digest,
                           identity.actor_digest));
    CHECK(sec::DigestEqual(result.audit_event.session_digest,
                           identity.session_digest));
    CHECK(sec::DigestEqual(result.audit_event.config_digest,
                           request.config_digest));
    CHECK(sec::DigestEqual(result.audit_event.source_generation_digest,
                           request.source_generation_digest));
    CHECK(sec::DigestEqual(result.audit_event.graph_generation_digest,
                           request.graph_generation_digest));
    CHECK(sec::DigestEqual(result.audit_event.artifact_digest,
                           request.artifact_digest));
    CHECK(result.audit_event.safety_state == sec::SafetyState::ENABLED);
    CHECK(result.audit_event.decision ==
          sec::DecisionCode::PASS_TO_NEXT_GATE);
    for (uint8_t raw = 0U;
         raw <=
         static_cast<uint8_t>(sec::DecisionCode::AUDIT_CAPACITY_EXHAUSTED);
         ++raw)
        CHECK(strcmp(sec::DecisionCodeName(
                         static_cast<sec::DecisionCode>(raw)),
                     "UNKNOWN_DECISION_CODE") != 0);
    CHECK(strcmp(sec::DecisionCodeName(
                     static_cast<sec::DecisionCode>(255U)),
                 "UNKNOWN_DECISION_CODE") == 0);
    sec::AuthorizationEngine invalid_capacity(Policy(), Identity(), 17U, 1U);
    CHECK(invalid_capacity.authorize(Request()).code ==
          sec::DecisionCode::INVALID_REQUEST);
    CHECK(sizeof(sec::AuthorizationEngine) <= 8192U);
}

}  // namespace

int main() {
    TestSharedCorpus();
    TestRoleMatrixClosed();
    TestSequenceAndAuditLanes();
    TestAuditContextAndClosedEnums();
    if (failures != 0) return 1;
    printf("SECURITY_AUTHORIZATION_CORE_OK\n");
    return 0;
}
