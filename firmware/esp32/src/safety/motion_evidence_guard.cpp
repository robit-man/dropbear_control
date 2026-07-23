#include "motion_evidence_guard.h"

namespace myactuator {
namespace safety {

namespace {

static const uint32_t kAlwaysRequiredFields =
    FEEDBACK_POSITION | FEEDBACK_VELOCITY | FEEDBACK_TEMPERATURE |
    FEEDBACK_BUS_VOLTAGE | FEEDBACK_FOLLOWING_ERROR;
static const uint32_t kEffortFields =
    FEEDBACK_Q_AXIS_CURRENT | FEEDBACK_OUTPUT_EFFORT;
static const uint32_t kCommandableFields =
    FEEDBACK_POSITION | FEEDBACK_VELOCITY | FEEDBACK_Q_AXIS_CURRENT |
    FEEDBACK_OUTPUT_EFFORT;

bool EvidenceClassValid(MotionEvidenceClass value) {
    return value == MotionEvidenceClass::SYNTHETIC_FIXTURE ||
           value == MotionEvidenceClass::PHYSICAL_REVIEWED;
}

bool DigestNonzero(const uint8_t* digest) {
    uint8_t aggregate = 0;
    for (size_t index = 0; index < kSha256DigestSize; ++index) {
        aggregate |= digest[index];
    }
    return aggregate != 0;
}

bool DigestsEqual(const uint8_t* left, const uint8_t* right) {
    uint8_t difference = 0;
    for (size_t index = 0; index < kSha256DigestSize; ++index) {
        difference |= left[index] ^ right[index];
    }
    return difference == 0;
}

bool ConfigIdValid(const BoundedConfigId& id) {
    if (id.length == 0U || id.length > kConfigIdCapacity) {
        return false;
    }
    for (size_t index = 0; index < kConfigIdCapacity; ++index) {
        if (index < id.length) {
            if (id.bytes[index] == '\0') {
                return false;
            }
        } else if (id.bytes[index] != '\0') {
            return false;
        }
    }
    return true;
}

bool ConfigReferenceValid(const ConfigReference& config) {
    return ConfigIdValid(config.identity.config_id) &&
           DigestNonzero(config.identity.digest.bytes) &&
           config.identity.revision != 0U &&
           config.identity.schema_version != 0U &&
           config.generation != 0U &&
           config.authorization_class == AuthorizationClass::MOTION;
}

bool EvidenceConfigMatches(const EvidenceConfigBinding& evidence,
                           const ConfigReference& config) {
    return evidence.generation == config.generation &&
           DigestsEqual(evidence.digest, config.identity.digest.bytes);
}

bool SingleBit(uint32_t value) {
    return value != 0U && (value & (value - 1U)) == 0U;
}

uint8_t CountBits(uint32_t value) {
    uint8_t count = 0;
    while (value != 0U) {
        count = static_cast<uint8_t>(count + (value & 1U));
        value >>= 1U;
    }
    return count;
}

uint32_t RequiredFieldAt(uint32_t mask, uint8_t ordinal) {
    uint8_t found = 0;
    for (uint8_t bit = 0; bit < 32U; ++bit) {
        const uint32_t candidate = 1UL << bit;
        if ((mask & candidate) == 0U) {
            continue;
        }
        if (found == ordinal) {
            return candidate;
        }
        ++found;
    }
    return 0U;
}

int64_t FeedbackValue(const FeedbackFaultContext& feedback,
                      uint32_t field) {
    switch (field) {
        case FEEDBACK_POSITION:
            return feedback.position_urad;
        case FEEDBACK_VELOCITY:
            return feedback.velocity_urad_s;
        case FEEDBACK_Q_AXIS_CURRENT:
            return feedback.q_axis_current_ma;
        case FEEDBACK_OUTPUT_EFFORT:
            return feedback.output_effort_unm;
        case FEEDBACK_TEMPERATURE:
            return feedback.temperature_mk;
        case FEEDBACK_BUS_VOLTAGE:
            return feedback.bus_voltage_mv;
        case FEEDBACK_FOLLOWING_ERROR:
            return feedback.following_error_urad;
        default:
            return 0;
    }
}

MotionAdmissionResult Decision(MotionEvidenceDecision decision,
                               uint16_t joint_token,
                               uint32_t field) {
    MotionAdmissionResult result = {};
    result.decision = decision;
    result.config_decision = ConfigDecision::ALLOWED;
    result.supervisor_result = Result::OK;
    result.joint_token = joint_token;
    result.field = field;
    return result;
}

bool PolicyValid(const MotionEvidencePolicy& policy) {
    if (policy.required_joint_count == 0U ||
        policy.required_joint_count > kMaximumMotionEvidenceJoints ||
        (policy.required_field_mask & ~kKnownFeedbackMask) != 0U ||
        (policy.required_field_mask & kAlwaysRequiredFields) !=
            kAlwaysRequiredFields ||
        (policy.required_field_mask & kEffortFields) == 0U ||
        CountBits(policy.required_field_mask) >
            kMaximumMotionLimitsPerJoint ||
        policy.maximum_sample_age_ms == 0U ||
        policy.maximum_receive_age_ms == 0U ||
        policy.maximum_sample_age_ms <
            policy.maximum_receive_age_ms ||
        !EvidenceClassValid(policy.required_evidence_class)) {
        return false;
    }

    for (uint8_t index = 0; index < policy.required_joint_count; ++index) {
        const MotionEvidenceBinding& binding =
            policy.required_joints[index];
        if (binding.joint_token == 0U ||
            binding.actuator_token == 0U) {
            return false;
        }
        for (uint8_t previous = 0; previous < index; ++previous) {
            if (binding.joint_token ==
                    policy.required_joints[previous].joint_token ||
                binding.actuator_token ==
                    policy.required_joints[previous].actuator_token) {
                return false;
            }
        }
    }
    return true;
}

}  // namespace

MotionEvidencePolicy::MotionEvidencePolicy(
    const MotionEvidenceBinding* joints,
    size_t joint_count,
    uint32_t feedback_and_limit_fields,
    uint64_t maximum_sample_age,
    uint64_t maximum_receive_age,
    MotionEvidenceClass evidence_class)
    : required_joints(),
      required_joint_count(0),
      required_field_mask(feedback_and_limit_fields),
      maximum_sample_age_ms(maximum_sample_age),
      maximum_receive_age_ms(maximum_receive_age),
      required_evidence_class(evidence_class) {
    if (joints == NULL || joint_count > kMaximumMotionEvidenceJoints) {
        return;
    }
    required_joint_count = static_cast<uint8_t>(joint_count);
    for (size_t index = 0; index < joint_count; ++index) {
        required_joints[index] = joints[index];
    }
}

const char* MotionEvidenceDecisionName(MotionEvidenceDecision decision) {
    switch (decision) {
        case MotionEvidenceDecision::ALLOWED:
            return "ALLOWED";
        case MotionEvidenceDecision::INVALID_GUARD:
            return "INVALID_GUARD";
        case MotionEvidenceDecision::CLOCK_REGRESSION:
            return "CLOCK_REGRESSION";
        case MotionEvidenceDecision::CONFIG_REFERENCE_INVALID:
            return "CONFIG_REFERENCE_INVALID";
        case MotionEvidenceDecision::EVIDENCE_BANK_MISSING:
            return "EVIDENCE_BANK_MISSING";
        case MotionEvidenceDecision::JOINT_COUNT_MISMATCH:
            return "JOINT_COUNT_MISMATCH";
        case MotionEvidenceDecision::JOINT_BINDING_MISMATCH:
            return "JOINT_BINDING_MISMATCH";
        case MotionEvidenceDecision::CONFIG_BINDING_MISMATCH:
            return "CONFIG_BINDING_MISMATCH";
        case MotionEvidenceDecision::CALIBRATION_PROVENANCE_INVALID:
            return "CALIBRATION_PROVENANCE_INVALID";
        case MotionEvidenceDecision::CALIBRATION_GENERATION_INVALID:
            return "CALIBRATION_GENERATION_INVALID";
        case MotionEvidenceDecision::EVIDENCE_CLASS_MISMATCH:
            return "EVIDENCE_CLASS_MISMATCH";
        case MotionEvidenceDecision::REQUIRED_SOURCE_MISSING:
            return "REQUIRED_SOURCE_MISSING";
        case MotionEvidenceDecision::FUSION_INVALID:
            return "FUSION_INVALID";
        case MotionEvidenceDecision::SOURCE_FAULT:
            return "SOURCE_FAULT";
        case MotionEvidenceDecision::SOURCE_QUALITY_INVALID:
            return "SOURCE_QUALITY_INVALID";
        case MotionEvidenceDecision::FEEDBACK_GENERATION_INVALID:
            return "FEEDBACK_GENERATION_INVALID";
        case MotionEvidenceDecision::FEEDBACK_MASK_INVALID:
            return "FEEDBACK_MASK_INVALID";
        case MotionEvidenceDecision::SAMPLE_TIME_FUTURE:
            return "SAMPLE_TIME_FUTURE";
        case MotionEvidenceDecision::RECEIVE_TIME_FUTURE:
            return "RECEIVE_TIME_FUTURE";
        case MotionEvidenceDecision::FEEDBACK_TIME_ORDER_INVALID:
            return "FEEDBACK_TIME_ORDER_INVALID";
        case MotionEvidenceDecision::SAMPLE_STALE:
            return "SAMPLE_STALE";
        case MotionEvidenceDecision::RECEIVE_STALE:
            return "RECEIVE_STALE";
        case MotionEvidenceDecision::LIMIT_COUNT_MISMATCH:
            return "LIMIT_COUNT_MISMATCH";
        case MotionEvidenceDecision::LIMIT_FIELD_ORDER_INVALID:
            return "LIMIT_FIELD_ORDER_INVALID";
        case MotionEvidenceDecision::LIMIT_BINDING_MISMATCH:
            return "LIMIT_BINDING_MISMATCH";
        case MotionEvidenceDecision::LIMIT_CONFIG_MISMATCH:
            return "LIMIT_CONFIG_MISMATCH";
        case MotionEvidenceDecision::LIMIT_PROVENANCE_INVALID:
            return "LIMIT_PROVENANCE_INVALID";
        case MotionEvidenceDecision::LIMIT_GENERATION_INVALID:
            return "LIMIT_GENERATION_INVALID";
        case MotionEvidenceDecision::LIMIT_INTERVAL_INVALID:
            return "LIMIT_INTERVAL_INVALID";
        case MotionEvidenceDecision::LIMIT_NOT_YET_VALID:
            return "LIMIT_NOT_YET_VALID";
        case MotionEvidenceDecision::LIMIT_EXPIRED:
            return "LIMIT_EXPIRED";
        case MotionEvidenceDecision::LIMIT_BOUNDS_MISSING:
            return "LIMIT_BOUNDS_MISSING";
        case MotionEvidenceDecision::LIMIT_BOUNDS_REVERSED:
            return "LIMIT_BOUNDS_REVERSED";
        case MotionEvidenceDecision::LIMIT_COORDINATE_MISMATCH:
            return "LIMIT_COORDINATE_MISMATCH";
        case MotionEvidenceDecision::FEEDBACK_BELOW_LIMIT:
            return "FEEDBACK_BELOW_LIMIT";
        case MotionEvidenceDecision::FEEDBACK_ABOVE_LIMIT:
            return "FEEDBACK_ABOVE_LIMIT";
        case MotionEvidenceDecision::SETPOINT_MISSING:
            return "SETPOINT_MISSING";
        case MotionEvidenceDecision::SETPOINT_FIELD_INVALID:
            return "SETPOINT_FIELD_INVALID";
        case MotionEvidenceDecision::SETPOINT_BINDING_MISMATCH:
            return "SETPOINT_BINDING_MISMATCH";
        case MotionEvidenceDecision::SETPOINT_CONFIG_MISMATCH:
            return "SETPOINT_CONFIG_MISMATCH";
        case MotionEvidenceDecision::SETPOINT_COORDINATE_MISMATCH:
            return "SETPOINT_COORDINATE_MISMATCH";
        case MotionEvidenceDecision::SETPOINT_BELOW_LIMIT:
            return "SETPOINT_BELOW_LIMIT";
        case MotionEvidenceDecision::SETPOINT_ABOVE_LIMIT:
            return "SETPOINT_ABOVE_LIMIT";
        case MotionEvidenceDecision::CONFIG_DENIED:
            return "CONFIG_DENIED";
        case MotionEvidenceDecision::SUPERVISOR_DENIED:
            return "SUPERVISOR_DENIED";
    }
    return "UNKNOWN_MOTION_EVIDENCE_DECISION";
}

EvidenceCoordinate ExpectedCoordinateForFeedbackField(uint32_t field) {
    switch (field) {
        case FEEDBACK_POSITION:
        case FEEDBACK_VELOCITY:
        case FEEDBACK_FOLLOWING_ERROR:
            return EvidenceCoordinate::CANONICAL_JOINT;
        case FEEDBACK_Q_AXIS_CURRENT:
            return EvidenceCoordinate::Q_AXIS_ELECTRICAL;
        case FEEDBACK_OUTPUT_EFFORT:
            return EvidenceCoordinate::ACTUATOR_OUTPUT;
        case FEEDBACK_TEMPERATURE:
            return EvidenceCoordinate::DRIVE_CASE;
        case FEEDBACK_BUS_VOLTAGE:
            return EvidenceCoordinate::DC_BUS;
        default:
            return EvidenceCoordinate::UNKNOWN;
    }
}

bool MotionAdmissionResult::allowed() const {
    return decision == MotionEvidenceDecision::ALLOWED &&
           config_checked &&
           config_decision == ConfigDecision::ALLOWED &&
           supervisor_checked &&
           supervisor_result == Result::OK;
}

MotionEvidenceGuard::MotionEvidenceGuard(
    SafetySupervisor* supervisor,
    ConfigIdentityGuard* config_guard,
    const MotionEvidencePolicy& policy)
    : supervisor_(supervisor),
      config_guard_(config_guard),
      policy_(policy),
      valid_(supervisor != NULL && config_guard != NULL &&
             PolicyValid(policy)),
      time_initialized_(false),
      last_now_ms_(0) {}

bool MotionEvidenceGuard::valid() const {
    return valid_;
}

MotionAdmissionResult MotionEvidenceGuard::evaluateEvidence(
    uint64_t now_ms,
    const ConfigReference& config,
    const MotionEvidenceBank* evidence,
    const MotionSetpoint* setpoint,
    bool setpoint_required) {
    if (!valid_) {
        return Decision(MotionEvidenceDecision::INVALID_GUARD, 0, 0);
    }
    if (time_initialized_ && now_ms < last_now_ms_) {
        return Decision(MotionEvidenceDecision::CLOCK_REGRESSION, 0, 0);
    }
    time_initialized_ = true;
    last_now_ms_ = now_ms;

    if (!ConfigReferenceValid(config)) {
        return Decision(MotionEvidenceDecision::CONFIG_REFERENCE_INVALID,
                        0, 0);
    }
    if (evidence == NULL) {
        return Decision(MotionEvidenceDecision::EVIDENCE_BANK_MISSING,
                        0, 0);
    }
    if (evidence->joint_count != policy_.required_joint_count) {
        return Decision(MotionEvidenceDecision::JOINT_COUNT_MISMATCH,
                        0, 0);
    }

    const uint8_t required_limit_count =
        CountBits(policy_.required_field_mask);
    for (uint8_t joint_index = 0;
         joint_index < policy_.required_joint_count;
         ++joint_index) {
        const MotionEvidenceBinding& expected =
            policy_.required_joints[joint_index];
        const JointMotionEvidence& joint =
            evidence->joints[joint_index];
        if (joint.joint_token != expected.joint_token ||
            joint.actuator_token != expected.actuator_token) {
            return Decision(
                MotionEvidenceDecision::JOINT_BINDING_MISMATCH,
                expected.joint_token, 0);
        }
        if (!EvidenceConfigMatches(joint.config, config)) {
            return Decision(
                MotionEvidenceDecision::CONFIG_BINDING_MISMATCH,
                joint.joint_token, 0);
        }
        if (!DigestNonzero(joint.calibration_digest)) {
            return Decision(
                MotionEvidenceDecision::CALIBRATION_PROVENANCE_INVALID,
                joint.joint_token, 0);
        }
        if (joint.calibration_generation == 0U) {
            return Decision(
                MotionEvidenceDecision::CALIBRATION_GENERATION_INVALID,
                joint.joint_token, 0);
        }
        if (joint.evidence_class !=
            policy_.required_evidence_class) {
            return Decision(
                MotionEvidenceDecision::EVIDENCE_CLASS_MISMATCH,
                joint.joint_token, 0);
        }
        if (!joint.required_sources_present) {
            return Decision(
                MotionEvidenceDecision::REQUIRED_SOURCE_MISSING,
                joint.joint_token, 0);
        }
        if (!joint.fusion_valid) {
            return Decision(MotionEvidenceDecision::FUSION_INVALID,
                            joint.joint_token, 0);
        }
        if (joint.source_fault) {
            return Decision(MotionEvidenceDecision::SOURCE_FAULT,
                            joint.joint_token, 0);
        }
        if (!joint.quality_valid) {
            return Decision(
                MotionEvidenceDecision::SOURCE_QUALITY_INVALID,
                joint.joint_token, 0);
        }
        if (joint.feedback.sample_generation == 0U) {
            return Decision(
                MotionEvidenceDecision::FEEDBACK_GENERATION_INVALID,
                joint.joint_token, 0);
        }
        if ((joint.feedback.valid_mask & ~kKnownFeedbackMask) != 0U ||
            (joint.feedback.valid_mask &
             policy_.required_field_mask) !=
                policy_.required_field_mask) {
            return Decision(
                MotionEvidenceDecision::FEEDBACK_MASK_INVALID,
                joint.joint_token, 0);
        }
        if (joint.feedback.sampled_at_ms > now_ms) {
            return Decision(
                MotionEvidenceDecision::SAMPLE_TIME_FUTURE,
                joint.joint_token, 0);
        }
        if (joint.feedback.received_at_ms > now_ms) {
            return Decision(
                MotionEvidenceDecision::RECEIVE_TIME_FUTURE,
                joint.joint_token, 0);
        }
        if (joint.feedback.received_at_ms <
            joint.feedback.sampled_at_ms) {
            return Decision(
                MotionEvidenceDecision::FEEDBACK_TIME_ORDER_INVALID,
                joint.joint_token, 0);
        }
        if (now_ms - joint.feedback.sampled_at_ms >
            policy_.maximum_sample_age_ms) {
            return Decision(MotionEvidenceDecision::SAMPLE_STALE,
                            joint.joint_token, 0);
        }
        if (now_ms - joint.feedback.received_at_ms >
            policy_.maximum_receive_age_ms) {
            return Decision(MotionEvidenceDecision::RECEIVE_STALE,
                            joint.joint_token, 0);
        }
        if (joint.limit_count != required_limit_count) {
            return Decision(
                MotionEvidenceDecision::LIMIT_COUNT_MISMATCH,
                joint.joint_token, 0);
        }

        for (uint8_t limit_index = 0;
             limit_index < required_limit_count;
             ++limit_index) {
            const uint32_t expected_field =
                RequiredFieldAt(policy_.required_field_mask,
                                limit_index);
            const TypedLimitSnapshot& limit =
                joint.limits[limit_index];
            if (!SingleBit(limit.field) ||
                limit.field != expected_field) {
                return Decision(
                    MotionEvidenceDecision::LIMIT_FIELD_ORDER_INVALID,
                    joint.joint_token, expected_field);
            }
            if (limit.joint_token != joint.joint_token ||
                limit.actuator_token != joint.actuator_token) {
                return Decision(
                    MotionEvidenceDecision::LIMIT_BINDING_MISMATCH,
                    joint.joint_token, limit.field);
            }
            if (!EvidenceConfigMatches(limit.config, config)) {
                return Decision(
                    MotionEvidenceDecision::LIMIT_CONFIG_MISMATCH,
                    joint.joint_token, limit.field);
            }
            if (!DigestNonzero(limit.provenance_digest)) {
                return Decision(
                    MotionEvidenceDecision::LIMIT_PROVENANCE_INVALID,
                    joint.joint_token, limit.field);
            }
            if (limit.generation == 0U) {
                return Decision(
                    MotionEvidenceDecision::LIMIT_GENERATION_INVALID,
                    joint.joint_token, limit.field);
            }
            if (limit.evidence_class !=
                policy_.required_evidence_class) {
                return Decision(
                    MotionEvidenceDecision::EVIDENCE_CLASS_MISMATCH,
                    joint.joint_token, limit.field);
            }
            if (limit.valid_until_ms <= limit.valid_from_ms) {
                return Decision(
                    MotionEvidenceDecision::LIMIT_INTERVAL_INVALID,
                    joint.joint_token, limit.field);
            }
            if (now_ms < limit.valid_from_ms) {
                return Decision(
                    MotionEvidenceDecision::LIMIT_NOT_YET_VALID,
                    joint.joint_token, limit.field);
            }
            if (now_ms > limit.valid_until_ms) {
                return Decision(
                    MotionEvidenceDecision::LIMIT_EXPIRED,
                    joint.joint_token, limit.field);
            }
            if (!limit.has_lower && !limit.has_upper) {
                return Decision(
                    MotionEvidenceDecision::LIMIT_BOUNDS_MISSING,
                    joint.joint_token, limit.field);
            }
            if (limit.has_lower && limit.has_upper &&
                limit.lower_value > limit.upper_value) {
                return Decision(
                    MotionEvidenceDecision::LIMIT_BOUNDS_REVERSED,
                    joint.joint_token, limit.field);
            }
            if (limit.coordinate !=
                ExpectedCoordinateForFeedbackField(limit.field)) {
                return Decision(
                    MotionEvidenceDecision::LIMIT_COORDINATE_MISMATCH,
                    joint.joint_token, limit.field);
            }

            const int64_t value =
                FeedbackValue(joint.feedback, limit.field);
            if (limit.has_lower && value < limit.lower_value) {
                return Decision(
                    MotionEvidenceDecision::FEEDBACK_BELOW_LIMIT,
                    joint.joint_token, limit.field);
            }
            if (limit.has_upper && value > limit.upper_value) {
                return Decision(
                    MotionEvidenceDecision::FEEDBACK_ABOVE_LIMIT,
                    joint.joint_token, limit.field);
            }
        }
    }

    if (!setpoint_required) {
        return Decision(MotionEvidenceDecision::ALLOWED, 0, 0);
    }
    if (setpoint == NULL) {
        return Decision(MotionEvidenceDecision::SETPOINT_MISSING, 0, 0);
    }
    if (!SingleBit(setpoint->field) ||
        (setpoint->field & kCommandableFields) == 0U ||
        (setpoint->field & policy_.required_field_mask) == 0U) {
        return Decision(MotionEvidenceDecision::SETPOINT_FIELD_INVALID,
                        setpoint->joint_token, setpoint->field);
    }
    if (!EvidenceConfigMatches(setpoint->config, config)) {
        return Decision(MotionEvidenceDecision::SETPOINT_CONFIG_MISMATCH,
                        setpoint->joint_token, setpoint->field);
    }
    if (setpoint->coordinate !=
        ExpectedCoordinateForFeedbackField(setpoint->field)) {
        return Decision(
            MotionEvidenceDecision::SETPOINT_COORDINATE_MISMATCH,
            setpoint->joint_token, setpoint->field);
    }

    const JointMotionEvidence* selected_joint = NULL;
    for (uint8_t index = 0;
         index < policy_.required_joint_count;
         ++index) {
        const JointMotionEvidence& candidate =
            evidence->joints[index];
        if (candidate.joint_token == setpoint->joint_token &&
            candidate.actuator_token == setpoint->actuator_token) {
            selected_joint = &candidate;
            break;
        }
    }
    if (selected_joint == NULL) {
        return Decision(
            MotionEvidenceDecision::SETPOINT_BINDING_MISMATCH,
            setpoint->joint_token, setpoint->field);
    }

    const TypedLimitSnapshot* selected_limit = NULL;
    for (uint8_t index = 0;
         index < selected_joint->limit_count;
         ++index) {
        if (selected_joint->limits[index].field ==
            setpoint->field) {
            selected_limit = &selected_joint->limits[index];
            break;
        }
    }
    if (selected_limit == NULL) {
        return Decision(MotionEvidenceDecision::SETPOINT_FIELD_INVALID,
                        setpoint->joint_token, setpoint->field);
    }
    if (selected_limit->has_lower &&
        setpoint->value < selected_limit->lower_value) {
        return Decision(MotionEvidenceDecision::SETPOINT_BELOW_LIMIT,
                        setpoint->joint_token, setpoint->field);
    }
    if (selected_limit->has_upper &&
        setpoint->value > selected_limit->upper_value) {
        return Decision(MotionEvidenceDecision::SETPOINT_ABOVE_LIMIT,
                        setpoint->joint_token, setpoint->field);
    }

    return Decision(MotionEvidenceDecision::ALLOWED,
                    setpoint->joint_token, setpoint->field);
}

MotionAdmissionResult MotionEvidenceGuard::enable(
    uint64_t now_ms,
    const MessageStamp& stamp,
    const ConfigReference& config,
    const MotionEvidenceBank* evidence) {
    MotionAdmissionResult result =
        evaluateEvidence(now_ms, config, evidence, NULL, false);
    if (result.decision != MotionEvidenceDecision::ALLOWED) {
        return result;
    }

    result.config_checked = true;
    result.config_decision =
        config_guard_->authorizeArm(now_ms, config);
    if (result.config_decision != ConfigDecision::ALLOWED) {
        result.decision = MotionEvidenceDecision::CONFIG_DENIED;
        return result;
    }

    result.supervisor_checked = true;
    result.supervisor_result =
        supervisor_->enable(now_ms, stamp);
    if (result.supervisor_result != Result::OK) {
        result.decision = MotionEvidenceDecision::SUPERVISOR_DENIED;
        return result;
    }
    return result;
}

MotionAdmissionResult MotionEvidenceGuard::authorizeCommand(
    uint64_t now_ms,
    const MessageStamp& stamp,
    const CommandAdmissionProof& proof,
    const MotionEvidenceBank* evidence,
    const MotionSetpoint* setpoint) {
    MotionAdmissionResult result =
        evaluateEvidence(now_ms, proof.config, evidence, setpoint, true);
    if (result.decision != MotionEvidenceDecision::ALLOWED) {
        return result;
    }

    result.config_checked = true;
    result.config_decision =
        config_guard_->authorizeTransmit(now_ms, proof);
    if (result.config_decision != ConfigDecision::ALLOWED) {
        result.decision = MotionEvidenceDecision::CONFIG_DENIED;
        return result;
    }

    result.supervisor_checked = true;
    result.supervisor_result =
        supervisor_->authorizeCommand(now_ms, stamp);
    if (result.supervisor_result != Result::OK) {
        result.decision = MotionEvidenceDecision::SUPERVISOR_DENIED;
        return result;
    }
    return result;
}

}  // namespace safety
}  // namespace myactuator
