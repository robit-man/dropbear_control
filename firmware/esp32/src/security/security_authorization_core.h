#pragma once

// Allocation-free post-authentication authorization and audit core.
//
// This core does not authenticate credentials, establish a secure transport,
// verify signatures, authorize motion, or perform I/O. A vetted upstream
// adapter must produce IdentityAssertion/ApprovalAssertion values. PASS only
// permits evaluation by the later config, lease, safety, limit, scheduler, and
// protocol gates.

#include <stddef.h>
#include <stdint.h>

namespace myactuator {
namespace security {

static const size_t kDigestSize = 32U;
static const size_t kMaximumNormalAuditCapacity = 16U;
static const size_t kMaximumSafeAuditCapacity = 4U;

struct Digest {
    uint8_t bytes[kDigestSize];
};

enum class Role : uint8_t {
    OBSERVER = 1,
    DIAGNOSTIC_OPERATOR = 2,
    OPERATOR = 3,
    SAFETY_OPERATOR = 4,
    CONFIGURATION_MANAGER = 5,
    FIRMWARE_MANAGER = 6,
    EVIDENCE_REVIEWER = 7,
};

enum class Action : uint8_t {
    READ_STATE = 1,
    READ_DIAGNOSTICS = 2,
    SUBMIT_MOTION = 3,
    REQUEST_DISABLE = 4,
    RESET_FAULT = 5,
    STAGE_CONFIG = 6,
    ACTIVATE_CONFIG = 7,
    STAGE_FIRMWARE = 8,
    ACTIVATE_FIRMWARE = 9,
    SUBMIT_EVIDENCE = 10,
};

enum class Target : uint8_t {
    OFFLINE = 1,
    SIMULATION = 2,
    PHYSICAL_LOCAL = 3,
    PHYSICAL_REMOTE = 4,
};

enum class SafetyState : uint8_t {
    BOOT = 0,
    DISCOVERY = 1,
    DISABLED = 2,
    ARMED = 3,
    ENABLED = 4,
    SHUTDOWN = 5,
    FAULT = 6,
};

enum class DecisionCode : uint8_t {
    PASS_TO_NEXT_GATE = 0,
    INVALID_REQUEST = 1,
    NOT_AUTHENTICATED = 2,
    IDENTITY_REVOKED = 3,
    SESSION_NOT_YET_VALID = 4,
    SESSION_EXPIRED = 5,
    SESSION_MISMATCH = 6,
    REPLAY_OR_REORDER = 7,
    ROLE_ACTION_DENIED = 8,
    PHYSICAL_ACTUATION_DISABLED = 9,
    REMOTE_PHYSICAL_DISABLED = 10,
    REMOTE_ADMIN_DISABLED = 11,
    LOCAL_PRESENCE_REQUIRED = 12,
    CONFIG_BINDING_MISSING = 13,
    CONFIG_MISMATCH = 14,
    SOURCE_BINDING_MISSING = 15,
    SOURCE_MISMATCH = 16,
    GRAPH_BINDING_MISSING = 17,
    GRAPH_MISMATCH = 18,
    LEASE_REQUIRED = 19,
    SAFETY_ADMISSION_REQUIRED = 20,
    ARTIFACT_INTEGRITY_REQUIRED = 21,
    ROLLBACK_PROTECTION_REQUIRED = 22,
    INDEPENDENT_APPROVAL_REQUIRED = 23,
    APPROVER_NOT_DISTINCT = 24,
    APPROVER_ROLE_DENIED = 25,
    APPROVAL_SCOPE_MISMATCH = 26,
    AUDIT_UNAVAILABLE = 27,
    AUDIT_CAPACITY_EXHAUSTED = 28,
};

struct AuthorizationPolicy {
    Digest expected_config_digest;
    Digest expected_source_generation_digest;
    Digest expected_graph_generation_digest;
    bool physical_actuation_enabled;
    bool remote_physical_actuation_enabled;
    bool remote_administration_enabled;
};

struct IdentityAssertion {
    Digest actor_digest;
    Digest session_digest;
    Digest authentication_context_digest;
    Role role;
    bool authenticated;
    bool revoked;
    uint64_t valid_from_ns;
    uint64_t valid_until_ns;
};

struct ApprovalAssertion {
    Digest actor_digest;
    Digest authentication_context_digest;
    Role role;
    bool authenticated;
    bool revoked;
    uint64_t valid_from_ns;
    uint64_t valid_until_ns;
    Digest scope_digest;
};

struct AuthorizationRequest {
    Action action;
    Target target;
    SafetyState safety_state;
    Digest session_digest;
    Digest correlation_digest;
    uint64_t sequence;
    uint64_t now_ns;
    Digest config_digest;
    Digest source_generation_digest;
    Digest graph_generation_digest;
    Digest artifact_digest;
    bool lease_valid;
    bool safety_admission_ready;
    bool local_presence_verified;
    bool artifact_integrity_verified;
    bool rollback_guard_verified;
    bool approval_present;
    ApprovalAssertion approval;
};

struct AuditEvent {
    uint64_t ordinal;
    Digest actor_digest;
    Digest session_digest;
    Digest correlation_digest;
    Digest authentication_context_digest;
    Action action;
    Target target;
    Role role;
    DecisionCode decision;
    SafetyState safety_state;
    uint64_t sequence;
    uint64_t monotonic_time_ns;
    Digest config_digest;
    Digest source_generation_digest;
    Digest graph_generation_digest;
    Digest artifact_digest;
    bool lease_valid;
    bool safety_admission_ready;
};

struct AuthorizationResult {
    DecisionCode code;
    bool audit_stored;
    AuditEvent audit_event;
    bool sequence_committed;
    bool proceed_to_next_gate;
    bool motion_authorized;
};

class AuthorizationEngine {
   public:
    AuthorizationEngine(const AuthorizationPolicy& policy,
                        const IdentityAssertion& identity,
                        size_t normal_audit_capacity,
                        size_t safe_audit_capacity);

    void setAuditHealth(bool normal_ready, bool safe_ready);
    AuthorizationResult authorize(const AuthorizationRequest& request);

    size_t normalAuditSize() const;
    size_t safeAuditSize() const;
    uint64_t safeAuditOverwriteCount() const;
    uint64_t unauditedDenialCount() const;
    uint64_t lastSequence() const;
    const AuditEvent* normalAuditAt(size_t index) const;
    const AuditEvent* safeAuditAt(size_t index) const;

   private:
    DecisionCode evaluate(const AuthorizationRequest& request,
                          bool* sequence_committed);
    AuditEvent event(const AuthorizationRequest& request,
                     DecisionCode decision);
    bool storeNormal(const AuditEvent& value);
    void storeSafe(const AuditEvent& value);

    AuthorizationPolicy policy_;
    IdentityAssertion identity_;
    size_t normal_capacity_;
    size_t safe_capacity_;
    AuditEvent normal_audit_[kMaximumNormalAuditCapacity];
    AuditEvent safe_audit_[kMaximumSafeAuditCapacity];
    size_t normal_size_;
    size_t safe_size_;
    uint64_t safe_overwrite_count_;
    uint64_t unaudited_denial_count_;
    uint64_t last_sequence_;
    uint64_t ordinal_;
    bool normal_audit_ready_;
    bool safe_audit_ready_;
    bool capacity_configuration_valid_;
};

bool DigestValid(const Digest& value);
bool DigestEqual(const Digest& left, const Digest& right);
const char* DecisionCodeName(DecisionCode code);

}  // namespace security
}  // namespace myactuator
