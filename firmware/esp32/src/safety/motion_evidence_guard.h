#pragma once

// Allocation-free final motion-evidence admission.
//
// This core composes already reviewed calibration/observation/limit evidence
// with ConfigIdentityGuard and SafetySupervisor. It performs no I/O, does not
// load or authenticate evidence, and does not prove physical motor-off. A
// trusted adapter must publish one coherent bank and call this boundary at the
// final arm/command decision. Synthetic evidence is suitable only for an
// explicitly synthetic supervisor/transport environment.

#include <stddef.h>
#include <stdint.h>

#include "config_identity_guard.h"
#include "fault_evidence.h"
#include "safety_supervisor.h"

namespace myactuator {
namespace safety {

static const size_t kMaximumMotionEvidenceJoints = 12;
static const size_t kMaximumMotionLimitsPerJoint = 7;

enum class MotionEvidenceClass : uint8_t {
    SYNTHETIC_FIXTURE = 1,
    PHYSICAL_REVIEWED = 2,
};

enum class EvidenceCoordinate : uint8_t {
    UNKNOWN = 0,
    CANONICAL_JOINT = 1,
    Q_AXIS_ELECTRICAL = 2,
    ACTUATOR_OUTPUT = 3,
    DRIVE_CASE = 4,
    DC_BUS = 5,
    MOTOR_SHAFT = 6,
    SENSOR_RAW = 7,
};

struct MotionEvidenceBinding {
    uint16_t joint_token;
    uint16_t actuator_token;
};

struct EvidenceConfigBinding {
    uint64_t generation;
    uint8_t digest[kSha256DigestSize];
};

struct TypedLimitSnapshot {
    uint16_t joint_token;
    uint16_t actuator_token;
    uint32_t field;
    EvidenceCoordinate coordinate;
    EvidenceConfigBinding config;
    uint8_t provenance_digest[kSha256DigestSize];
    uint64_t generation;
    uint64_t valid_from_ms;
    uint64_t valid_until_ms;
    MotionEvidenceClass evidence_class;
    bool has_lower;
    bool has_upper;
    int64_t lower_value;
    int64_t upper_value;
};

struct JointMotionEvidence {
    uint16_t joint_token;
    uint16_t actuator_token;
    EvidenceConfigBinding config;
    uint8_t calibration_digest[kSha256DigestSize];
    uint64_t calibration_generation;
    MotionEvidenceClass evidence_class;
    bool required_sources_present;
    bool fusion_valid;
    bool source_fault;
    bool quality_valid;
    FeedbackFaultContext feedback;
    uint8_t limit_count;
    TypedLimitSnapshot limits[kMaximumMotionLimitsPerJoint];
};

struct MotionEvidenceBank {
    uint8_t joint_count;
    JointMotionEvidence joints[kMaximumMotionEvidenceJoints];
};

struct MotionSetpoint {
    uint16_t joint_token;
    uint16_t actuator_token;
    uint32_t field;
    EvidenceCoordinate coordinate;
    EvidenceConfigBinding config;
    int64_t value;
};

struct MotionEvidencePolicy {
    MotionEvidenceBinding required_joints[kMaximumMotionEvidenceJoints];
    uint8_t required_joint_count;
    uint32_t required_field_mask;
    uint64_t maximum_sample_age_ms;
    uint64_t maximum_receive_age_ms;
    MotionEvidenceClass required_evidence_class;

    MotionEvidencePolicy(const MotionEvidenceBinding* joints,
                         size_t joint_count,
                         uint32_t feedback_and_limit_fields,
                         uint64_t maximum_sample_age,
                         uint64_t maximum_receive_age,
                         MotionEvidenceClass evidence_class);
};

enum class MotionEvidenceDecision : uint8_t {
    ALLOWED = 0,
    INVALID_GUARD = 1,
    CLOCK_REGRESSION = 2,
    CONFIG_REFERENCE_INVALID = 3,
    EVIDENCE_BANK_MISSING = 4,
    JOINT_COUNT_MISMATCH = 5,
    JOINT_BINDING_MISMATCH = 6,
    CONFIG_BINDING_MISMATCH = 7,
    CALIBRATION_PROVENANCE_INVALID = 8,
    CALIBRATION_GENERATION_INVALID = 9,
    EVIDENCE_CLASS_MISMATCH = 10,
    REQUIRED_SOURCE_MISSING = 11,
    FUSION_INVALID = 12,
    SOURCE_FAULT = 13,
    SOURCE_QUALITY_INVALID = 14,
    FEEDBACK_GENERATION_INVALID = 15,
    FEEDBACK_MASK_INVALID = 16,
    SAMPLE_TIME_FUTURE = 17,
    RECEIVE_TIME_FUTURE = 18,
    FEEDBACK_TIME_ORDER_INVALID = 19,
    SAMPLE_STALE = 20,
    RECEIVE_STALE = 21,
    LIMIT_COUNT_MISMATCH = 22,
    LIMIT_FIELD_ORDER_INVALID = 23,
    LIMIT_BINDING_MISMATCH = 24,
    LIMIT_CONFIG_MISMATCH = 25,
    LIMIT_PROVENANCE_INVALID = 26,
    LIMIT_GENERATION_INVALID = 27,
    LIMIT_INTERVAL_INVALID = 28,
    LIMIT_NOT_YET_VALID = 29,
    LIMIT_EXPIRED = 30,
    LIMIT_BOUNDS_MISSING = 31,
    LIMIT_BOUNDS_REVERSED = 32,
    LIMIT_COORDINATE_MISMATCH = 33,
    FEEDBACK_BELOW_LIMIT = 34,
    FEEDBACK_ABOVE_LIMIT = 35,
    SETPOINT_MISSING = 36,
    SETPOINT_FIELD_INVALID = 37,
    SETPOINT_BINDING_MISMATCH = 38,
    SETPOINT_CONFIG_MISMATCH = 39,
    SETPOINT_COORDINATE_MISMATCH = 40,
    SETPOINT_BELOW_LIMIT = 41,
    SETPOINT_ABOVE_LIMIT = 42,
    CONFIG_DENIED = 43,
    SUPERVISOR_DENIED = 44,
};

const char* MotionEvidenceDecisionName(MotionEvidenceDecision decision);
EvidenceCoordinate ExpectedCoordinateForFeedbackField(uint32_t field);

struct MotionAdmissionResult {
    MotionEvidenceDecision decision;
    bool config_checked;
    ConfigDecision config_decision;
    bool supervisor_checked;
    Result supervisor_result;
    uint16_t joint_token;
    uint32_t field;

    bool allowed() const;
};

class MotionEvidenceGuard {
public:
    MotionEvidenceGuard(SafetySupervisor* supervisor,
                        ConfigIdentityGuard* config_guard,
                        const MotionEvidencePolicy& policy);

    bool valid() const;

    // Evidence is evaluated before either mutable downstream guard. Therefore
    // an evidence denial cannot consume a supervisor message sequence or a
    // configuration command generation.
    MotionAdmissionResult enable(
        uint64_t now_ms,
        const MessageStamp& stamp,
        const ConfigReference& config,
        const MotionEvidenceBank* evidence);

    MotionAdmissionResult authorizeCommand(
        uint64_t now_ms,
        const MessageStamp& stamp,
        const CommandAdmissionProof& proof,
        const MotionEvidenceBank* evidence,
        const MotionSetpoint* setpoint);

private:
    SafetySupervisor* supervisor_;
    ConfigIdentityGuard* config_guard_;
    MotionEvidencePolicy policy_;
    bool valid_;
    bool time_initialized_;
    uint64_t last_now_ms_;

    MotionAdmissionResult evaluateEvidence(
        uint64_t now_ms,
        const ConfigReference& config,
        const MotionEvidenceBank* evidence,
        const MotionSetpoint* setpoint,
        bool setpoint_required);
};

}  // namespace safety
}  // namespace myactuator
