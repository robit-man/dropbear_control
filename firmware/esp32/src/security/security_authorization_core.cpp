#include "security_authorization_core.h"

#include <string.h>

namespace myactuator {
namespace security {
namespace {

bool RoleValid(Role value) {
    const uint8_t raw = static_cast<uint8_t>(value);
    return raw >= static_cast<uint8_t>(Role::OBSERVER) &&
           raw <= static_cast<uint8_t>(Role::EVIDENCE_REVIEWER);
}

bool ActionValid(Action value) {
    const uint8_t raw = static_cast<uint8_t>(value);
    return raw >= static_cast<uint8_t>(Action::READ_STATE) &&
           raw <= static_cast<uint8_t>(Action::SUBMIT_EVIDENCE);
}

bool TargetValid(Target value) {
    const uint8_t raw = static_cast<uint8_t>(value);
    return raw >= static_cast<uint8_t>(Target::OFFLINE) &&
           raw <= static_cast<uint8_t>(Target::PHYSICAL_REMOTE);
}

bool SafetyStateValid(SafetyState value) {
    return static_cast<uint8_t>(value) <=
           static_cast<uint8_t>(SafetyState::FAULT);
}

bool RoleAllows(Role role, Action action) {
    switch (role) {
        case Role::OBSERVER:
            return action == Action::READ_STATE;
        case Role::DIAGNOSTIC_OPERATOR:
            return action == Action::READ_STATE ||
                   action == Action::READ_DIAGNOSTICS;
        case Role::OPERATOR:
            return action == Action::READ_STATE ||
                   action == Action::READ_DIAGNOSTICS ||
                   action == Action::SUBMIT_MOTION ||
                   action == Action::REQUEST_DISABLE;
        case Role::SAFETY_OPERATOR:
            return action == Action::READ_STATE ||
                   action == Action::READ_DIAGNOSTICS ||
                   action == Action::REQUEST_DISABLE ||
                   action == Action::RESET_FAULT;
        case Role::CONFIGURATION_MANAGER:
            return action == Action::READ_STATE ||
                   action == Action::READ_DIAGNOSTICS ||
                   action == Action::STAGE_CONFIG ||
                   action == Action::ACTIVATE_CONFIG;
        case Role::FIRMWARE_MANAGER:
            return action == Action::READ_STATE ||
                   action == Action::READ_DIAGNOSTICS ||
                   action == Action::STAGE_FIRMWARE ||
                   action == Action::ACTIVATE_FIRMWARE;
        case Role::EVIDENCE_REVIEWER:
            return action == Action::READ_STATE ||
                   action == Action::READ_DIAGNOSTICS ||
                   action == Action::SUBMIT_EVIDENCE;
    }
    return false;
}

bool IsPhysical(Target target) {
    return target == Target::PHYSICAL_LOCAL ||
           target == Target::PHYSICAL_REMOTE;
}

bool RequiresBinding(Action action) {
    return action == Action::SUBMIT_MOTION ||
           action == Action::RESET_FAULT ||
           action == Action::STAGE_CONFIG ||
           action == Action::ACTIVATE_CONFIG ||
           action == Action::STAGE_FIRMWARE ||
           action == Action::ACTIVATE_FIRMWARE;
}

bool IsArtifactAction(Action action) {
    return action == Action::STAGE_CONFIG ||
           action == Action::ACTIVATE_CONFIG ||
           action == Action::STAGE_FIRMWARE ||
           action == Action::ACTIVATE_FIRMWARE;
}

bool IsActivation(Action action) {
    return action == Action::ACTIVATE_CONFIG ||
           action == Action::ACTIVATE_FIRMWARE;
}

bool IsRemoteAdmin(Action action) {
    return action == Action::RESET_FAULT ||
           action == Action::STAGE_CONFIG ||
           action == Action::ACTIVATE_CONFIG ||
           action == Action::STAGE_FIRMWARE ||
           action == Action::ACTIVATE_FIRMWARE;
}

void CopyDigest(Digest* destination, const Digest& source) {
    memcpy(destination->bytes, source.bytes, kDigestSize);
}

}  // namespace

bool DigestValid(const Digest& value) {
    uint8_t combined = 0U;
    for (size_t index = 0U; index < kDigestSize; ++index)
        combined = static_cast<uint8_t>(combined | value.bytes[index]);
    return combined != 0U;
}

bool DigestEqual(const Digest& left, const Digest& right) {
    uint8_t difference = 0U;
    for (size_t index = 0U; index < kDigestSize; ++index)
        difference = static_cast<uint8_t>(
            difference | static_cast<uint8_t>(left.bytes[index] ^
                                              right.bytes[index]));
    return difference == 0U;
}

const char* DecisionCodeName(DecisionCode code) {
    switch (code) {
        case DecisionCode::PASS_TO_NEXT_GATE:
            return "PASS_TO_NEXT_GATE";
        case DecisionCode::INVALID_REQUEST:
            return "INVALID_REQUEST";
        case DecisionCode::NOT_AUTHENTICATED:
            return "NOT_AUTHENTICATED";
        case DecisionCode::IDENTITY_REVOKED:
            return "IDENTITY_REVOKED";
        case DecisionCode::SESSION_NOT_YET_VALID:
            return "SESSION_NOT_YET_VALID";
        case DecisionCode::SESSION_EXPIRED:
            return "SESSION_EXPIRED";
        case DecisionCode::SESSION_MISMATCH:
            return "SESSION_MISMATCH";
        case DecisionCode::REPLAY_OR_REORDER:
            return "REPLAY_OR_REORDER";
        case DecisionCode::ROLE_ACTION_DENIED:
            return "ROLE_ACTION_DENIED";
        case DecisionCode::PHYSICAL_ACTUATION_DISABLED:
            return "PHYSICAL_ACTUATION_DISABLED";
        case DecisionCode::REMOTE_PHYSICAL_DISABLED:
            return "REMOTE_PHYSICAL_DISABLED";
        case DecisionCode::REMOTE_ADMIN_DISABLED:
            return "REMOTE_ADMIN_DISABLED";
        case DecisionCode::LOCAL_PRESENCE_REQUIRED:
            return "LOCAL_PRESENCE_REQUIRED";
        case DecisionCode::CONFIG_BINDING_MISSING:
            return "CONFIG_BINDING_MISSING";
        case DecisionCode::CONFIG_MISMATCH:
            return "CONFIG_MISMATCH";
        case DecisionCode::SOURCE_BINDING_MISSING:
            return "SOURCE_BINDING_MISSING";
        case DecisionCode::SOURCE_MISMATCH:
            return "SOURCE_MISMATCH";
        case DecisionCode::GRAPH_BINDING_MISSING:
            return "GRAPH_BINDING_MISSING";
        case DecisionCode::GRAPH_MISMATCH:
            return "GRAPH_MISMATCH";
        case DecisionCode::LEASE_REQUIRED:
            return "LEASE_REQUIRED";
        case DecisionCode::SAFETY_ADMISSION_REQUIRED:
            return "SAFETY_ADMISSION_REQUIRED";
        case DecisionCode::ARTIFACT_INTEGRITY_REQUIRED:
            return "ARTIFACT_INTEGRITY_REQUIRED";
        case DecisionCode::ROLLBACK_PROTECTION_REQUIRED:
            return "ROLLBACK_PROTECTION_REQUIRED";
        case DecisionCode::INDEPENDENT_APPROVAL_REQUIRED:
            return "INDEPENDENT_APPROVAL_REQUIRED";
        case DecisionCode::APPROVER_NOT_DISTINCT:
            return "APPROVER_NOT_DISTINCT";
        case DecisionCode::APPROVER_ROLE_DENIED:
            return "APPROVER_ROLE_DENIED";
        case DecisionCode::APPROVAL_SCOPE_MISMATCH:
            return "APPROVAL_SCOPE_MISMATCH";
        case DecisionCode::AUDIT_UNAVAILABLE:
            return "AUDIT_UNAVAILABLE";
        case DecisionCode::AUDIT_CAPACITY_EXHAUSTED:
            return "AUDIT_CAPACITY_EXHAUSTED";
    }
    return "UNKNOWN_DECISION_CODE";
}

AuthorizationEngine::AuthorizationEngine(
    const AuthorizationPolicy& policy, const IdentityAssertion& identity,
    size_t normal_audit_capacity, size_t safe_audit_capacity)
    : policy_(policy),
      identity_(identity),
      normal_capacity_(normal_audit_capacity),
      safe_capacity_(safe_audit_capacity),
      normal_size_(0U),
      safe_size_(0U),
      safe_overwrite_count_(0U),
      unaudited_denial_count_(0U),
      last_sequence_(0U),
      ordinal_(0U),
      normal_audit_ready_(true),
      safe_audit_ready_(true),
      capacity_configuration_valid_(
          normal_audit_capacity > 0U &&
          normal_audit_capacity <= kMaximumNormalAuditCapacity &&
          safe_audit_capacity > 0U &&
          safe_audit_capacity <= kMaximumSafeAuditCapacity) {
    if (!capacity_configuration_valid_) {
        normal_capacity_ = 1U;
        safe_capacity_ = 1U;
    }
    memset(normal_audit_, 0, sizeof(normal_audit_));
    memset(safe_audit_, 0, sizeof(safe_audit_));
}

void AuthorizationEngine::setAuditHealth(bool normal_ready, bool safe_ready) {
    normal_audit_ready_ = normal_ready;
    safe_audit_ready_ = safe_ready;
}

AuthorizationResult AuthorizationEngine::authorize(
    const AuthorizationRequest& request) {
    bool sequence_committed = false;
    DecisionCode code = evaluate(request, &sequence_committed);
    bool safe_pass = code == DecisionCode::PASS_TO_NEXT_GATE &&
                     request.action == Action::REQUEST_DISABLE;
    if (code == DecisionCode::PASS_TO_NEXT_GATE) {
        if (safe_pass && !safe_audit_ready_) {
            code = DecisionCode::AUDIT_UNAVAILABLE;
            safe_pass = false;
        } else if (!safe_pass && !normal_audit_ready_) {
            code = DecisionCode::AUDIT_UNAVAILABLE;
        } else if (!safe_pass && normal_size_ >= normal_capacity_) {
            code = DecisionCode::AUDIT_CAPACITY_EXHAUSTED;
        }
    }

    const AuditEvent record = event(request, code);
    bool stored = false;
    if (safe_pass) {
        storeSafe(record);
        stored = true;
    } else if (normal_audit_ready_) {
        stored = storeNormal(record);
    }
    if (!stored) ++unaudited_denial_count_;

    AuthorizationResult result = {};
    result.code = code;
    result.audit_stored = stored;
    result.audit_event = record;
    result.sequence_committed = sequence_committed;
    result.proceed_to_next_gate =
        code == DecisionCode::PASS_TO_NEXT_GATE;
    result.motion_authorized = false;
    return result;
}

DecisionCode AuthorizationEngine::evaluate(
    const AuthorizationRequest& request, bool* sequence_committed) {
    *sequence_committed = false;
    if (!capacity_configuration_valid_ || !RoleValid(identity_.role) ||
        !ActionValid(request.action) ||
        !TargetValid(request.target) ||
        !SafetyStateValid(request.safety_state) ||
        !DigestValid(policy_.expected_config_digest) ||
        !DigestValid(policy_.expected_source_generation_digest) ||
        !DigestValid(policy_.expected_graph_generation_digest) ||
        !DigestValid(identity_.actor_digest) ||
        !DigestValid(identity_.session_digest) ||
        !DigestValid(identity_.authentication_context_digest) ||
        !DigestValid(request.session_digest) ||
        !DigestValid(request.correlation_digest) ||
        identity_.valid_until_ns <= identity_.valid_from_ns ||
        request.sequence == 0U)
        return DecisionCode::INVALID_REQUEST;
    if (!identity_.authenticated) return DecisionCode::NOT_AUTHENTICATED;
    if (identity_.revoked) return DecisionCode::IDENTITY_REVOKED;
    if (request.now_ns < identity_.valid_from_ns)
        return DecisionCode::SESSION_NOT_YET_VALID;
    if (request.now_ns >= identity_.valid_until_ns)
        return DecisionCode::SESSION_EXPIRED;
    if (!DigestEqual(request.session_digest, identity_.session_digest))
        return DecisionCode::SESSION_MISMATCH;
    if (request.sequence <= last_sequence_)
        return DecisionCode::REPLAY_OR_REORDER;

    last_sequence_ = request.sequence;
    *sequence_committed = true;
    if (!RoleAllows(identity_.role, request.action))
        return DecisionCode::ROLE_ACTION_DENIED;

    const bool physical = IsPhysical(request.target);
    if (request.action == Action::SUBMIT_MOTION && physical) {
        if (!policy_.physical_actuation_enabled)
            return DecisionCode::PHYSICAL_ACTUATION_DISABLED;
        if (request.target == Target::PHYSICAL_REMOTE &&
            !policy_.remote_physical_actuation_enabled)
            return DecisionCode::REMOTE_PHYSICAL_DISABLED;
    }
    if (request.target == Target::PHYSICAL_REMOTE &&
        IsRemoteAdmin(request.action) &&
        !policy_.remote_administration_enabled)
        return DecisionCode::REMOTE_ADMIN_DISABLED;
    if (physical &&
        (request.action == Action::RESET_FAULT ||
         request.action == Action::ACTIVATE_CONFIG ||
         request.action == Action::ACTIVATE_FIRMWARE) &&
        !request.local_presence_verified)
        return DecisionCode::LOCAL_PRESENCE_REQUIRED;

    if (RequiresBinding(request.action)) {
        if (!DigestValid(request.config_digest))
            return DecisionCode::CONFIG_BINDING_MISSING;
        if (!DigestEqual(request.config_digest,
                         policy_.expected_config_digest))
            return DecisionCode::CONFIG_MISMATCH;
        if (!DigestValid(request.source_generation_digest))
            return DecisionCode::SOURCE_BINDING_MISSING;
        if (!DigestEqual(request.source_generation_digest,
                         policy_.expected_source_generation_digest))
            return DecisionCode::SOURCE_MISMATCH;
        if (!DigestValid(request.graph_generation_digest))
            return DecisionCode::GRAPH_BINDING_MISSING;
        if (!DigestEqual(request.graph_generation_digest,
                         policy_.expected_graph_generation_digest))
            return DecisionCode::GRAPH_MISMATCH;
    }

    if (request.action == Action::SUBMIT_MOTION) {
        if (!request.lease_valid) return DecisionCode::LEASE_REQUIRED;
        if (!request.safety_admission_ready)
            return DecisionCode::SAFETY_ADMISSION_REQUIRED;
    }

    if (IsArtifactAction(request.action) &&
        (!DigestValid(request.artifact_digest) ||
         !request.artifact_integrity_verified))
        return DecisionCode::ARTIFACT_INTEGRITY_REQUIRED;

    if (IsActivation(request.action)) {
        if (!request.rollback_guard_verified)
            return DecisionCode::ROLLBACK_PROTECTION_REQUIRED;
        const ApprovalAssertion& approval = request.approval;
        if (!request.approval_present || !approval.authenticated ||
            approval.revoked ||
            request.now_ns < approval.valid_from_ns ||
            request.now_ns >= approval.valid_until_ns ||
            !DigestValid(approval.actor_digest) ||
            !DigestValid(approval.authentication_context_digest) ||
            !DigestValid(approval.scope_digest))
            return DecisionCode::INDEPENDENT_APPROVAL_REQUIRED;
        if (DigestEqual(approval.actor_digest, identity_.actor_digest))
            return DecisionCode::APPROVER_NOT_DISTINCT;
        if (approval.role != Role::EVIDENCE_REVIEWER)
            return DecisionCode::APPROVER_ROLE_DENIED;
        if (!DigestEqual(approval.scope_digest, request.artifact_digest))
            return DecisionCode::APPROVAL_SCOPE_MISMATCH;
    }
    return DecisionCode::PASS_TO_NEXT_GATE;
}

AuditEvent AuthorizationEngine::event(
    const AuthorizationRequest& request, DecisionCode decision) {
    AuditEvent value = {};
    value.ordinal = ++ordinal_;
    CopyDigest(&value.actor_digest, identity_.actor_digest);
    CopyDigest(&value.session_digest, identity_.session_digest);
    CopyDigest(&value.correlation_digest, request.correlation_digest);
    CopyDigest(&value.authentication_context_digest,
               identity_.authentication_context_digest);
    value.action = request.action;
    value.target = request.target;
    value.role = identity_.role;
    value.decision = decision;
    value.safety_state = request.safety_state;
    value.sequence = request.sequence;
    value.monotonic_time_ns = request.now_ns;
    CopyDigest(&value.config_digest, request.config_digest);
    CopyDigest(&value.source_generation_digest,
               request.source_generation_digest);
    CopyDigest(&value.graph_generation_digest,
               request.graph_generation_digest);
    CopyDigest(&value.artifact_digest, request.artifact_digest);
    value.lease_valid = request.lease_valid;
    value.safety_admission_ready = request.safety_admission_ready;
    return value;
}

bool AuthorizationEngine::storeNormal(const AuditEvent& value) {
    if (normal_size_ >= normal_capacity_) return false;
    normal_audit_[normal_size_++] = value;
    return true;
}

void AuthorizationEngine::storeSafe(const AuditEvent& value) {
    if (safe_size_ < safe_capacity_) {
        safe_audit_[safe_size_++] = value;
        return;
    }
    for (size_t index = 1U; index < safe_size_; ++index)
        safe_audit_[index - 1U] = safe_audit_[index];
    safe_audit_[safe_size_ - 1U] = value;
    ++safe_overwrite_count_;
}

size_t AuthorizationEngine::normalAuditSize() const { return normal_size_; }
size_t AuthorizationEngine::safeAuditSize() const { return safe_size_; }
uint64_t AuthorizationEngine::safeAuditOverwriteCount() const {
    return safe_overwrite_count_;
}
uint64_t AuthorizationEngine::unauditedDenialCount() const {
    return unaudited_denial_count_;
}
uint64_t AuthorizationEngine::lastSequence() const { return last_sequence_; }
const AuditEvent* AuthorizationEngine::normalAuditAt(size_t index) const {
    return index < normal_size_ ? &normal_audit_[index] : NULL;
}
const AuditEvent* AuthorizationEngine::safeAuditAt(size_t index) const {
    return index < safe_size_ ? &safe_audit_[index] : NULL;
}

static_assert(sizeof(AuthorizationEngine) <= 8192U,
              "security authorization engine exceeds ESP32 memory budget");

}  // namespace security
}  // namespace myactuator
