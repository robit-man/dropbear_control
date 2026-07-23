#include "joint_observation_core.h"

#include <math.h>
#include <string.h>

namespace myactuator {
namespace runtime {
namespace {

bool TextValid(const hostlink_v1::Text& value) {
    return value.size > 0U && value.size <= hostlink_v1::kMaxTextBytes;
}

bool TextSame(const hostlink_v1::Text& left, const hostlink_v1::Text& right) {
    return left.size == right.size &&
           memcmp(left.bytes, right.bytes, left.size) == 0;
}

bool DigestNonzero(const hostlink_v1::Sha256& value) {
    uint8_t combined = 0U;
    for (size_t index = 0U; index < sizeof(value.bytes); ++index) {
        combined = static_cast<uint8_t>(combined | value.bytes[index]);
    }
    return combined != 0U;
}

bool ConfigValid(const hostlink_v1::ConfigIdentity& value) {
    return TextValid(value.identity) && TextValid(value.revision) &&
           DigestNonzero(value.sha256);
}

bool ConfigSame(const hostlink_v1::ConfigIdentity& left,
                const hostlink_v1::ConfigIdentity& right) {
    return TextSame(left.identity, right.identity) &&
           TextSame(left.revision, right.revision) &&
           memcmp(left.sha256.bytes, right.sha256.bytes,
                  sizeof(left.sha256.bytes)) == 0;
}

bool SourceKindValid(ObservationSourceKind value) {
    return value >= ObservationSourceKind::EXTERNAL_ABSOLUTE &&
           value <= ObservationSourceKind::SYNTHETIC_PLANT;
}

bool UnitValid(RawObservationUnit value) {
    return value >= RawObservationUnit::COUNT &&
           value <= RawObservationUnit::DEGREE;
}

bool EvidenceValid(CalibrationEvidenceClass value) {
    return value == CalibrationEvidenceClass::SYNTHETIC_FIXTURE ||
           value == CalibrationEvidenceClass::PHYSICAL_BENCH;
}

bool ObservationIdentitySame(const ConvertedJointObservation& value,
                             const ReconciliationPolicy& policy,
                             const hostlink_v1::Text& sensor_id) {
    return TextSame(value.canonical_joint_name, policy.canonical_joint_name) &&
           TextSame(value.actuator_id, policy.actuator_id) &&
           TextSame(value.sensor_id, sensor_id) &&
           ConfigSame(value.configuration, policy.configuration);
}

double WrapRaw(double delta, double period, WrapInterval interval) {
    double wrapped = fmod(delta, period);
    if (wrapped < 0.0) {
        wrapped += period;
    }
    if (interval == WrapInterval::CENTERED && wrapped > period * 0.5) {
        wrapped -= period;
    }
    return wrapped;
}

}  // namespace

const char* ObservationCodeName(ObservationCode code) {
    switch (code) {
        case ObservationCode::OK: return "OK";
        case ObservationCode::NULL_OUTPUT: return "NULL_OUTPUT";
        case ObservationCode::CALIBRATION_INVALID: return "CALIBRATION_INVALID";
        case ObservationCode::SAMPLE_INVALID: return "SAMPLE_INVALID";
        case ObservationCode::IDENTITY_MISMATCH: return "IDENTITY_MISMATCH";
        case ObservationCode::SOURCE_KIND_MISMATCH: return "SOURCE_KIND_MISMATCH";
        case ObservationCode::UNIT_MISMATCH: return "UNIT_MISMATCH";
        case ObservationCode::EVIDENCE_CLASS_MISMATCH: return "EVIDENCE_CLASS_MISMATCH";
        case ObservationCode::CALIBRATION_NOT_YET_VALID: return "CALIBRATION_NOT_YET_VALID";
        case ObservationCode::CALIBRATION_EXPIRED: return "CALIBRATION_EXPIRED";
        case ObservationCode::SAMPLE_TIME_FUTURE: return "SAMPLE_TIME_FUTURE";
        case ObservationCode::RECEIVE_TIME_FUTURE: return "RECEIVE_TIME_FUTURE";
        case ObservationCode::TIME_ORDER_INVALID: return "TIME_ORDER_INVALID";
        case ObservationCode::SAMPLE_STALE: return "SAMPLE_STALE";
        case ObservationCode::RECEIVE_STALE: return "RECEIVE_STALE";
        case ObservationCode::SOURCE_FAULT: return "SOURCE_FAULT";
        case ObservationCode::SOURCE_QUALITY_INVALID: return "SOURCE_QUALITY_INVALID";
        case ObservationCode::SAMPLE_OUTSIDE_CALIBRATION_VALIDITY: return "SAMPLE_OUTSIDE_CALIBRATION_VALIDITY";
        case ObservationCode::SEQUENCE_REPLAY: return "SEQUENCE_REPLAY";
        case ObservationCode::SAMPLE_TIME_REGRESSION: return "SAMPLE_TIME_REGRESSION";
        case ObservationCode::RECEIVE_TIME_REGRESSION: return "RECEIVE_TIME_REGRESSION";
        case ObservationCode::CALIBRATION_GENERATION_REGRESSION: return "CALIBRATION_GENERATION_REGRESSION";
        case ObservationCode::CONVERSION_NONFINITE: return "CONVERSION_NONFINITE";
    }
    return "UNKNOWN_OBSERVATION_CODE";
}

ObservationCode ValidateCalibrationSnapshot(const CalibrationSnapshot& value) {
    if (!TextValid(value.record_id) || !TextValid(value.canonical_joint_name) ||
        !TextValid(value.actuator_id) || !TextValid(value.sensor_id) ||
        !ConfigValid(value.configuration) || !DigestNonzero(value.subject_digest) ||
        !DigestNonzero(value.record_digest) || value.generation == 0U ||
        value.valid_until_ns <= value.valid_from_ns ||
        !EvidenceValid(value.evidence_class) || !SourceKindValid(value.source_kind) ||
        !UnitValid(value.raw_unit) || !isfinite(value.raw_zero) ||
        !isfinite(value.joint_zero_rad) || !isfinite(value.native_output_zero_rad) ||
        !isfinite(value.raw_to_joint_scale_rad_per_unit) ||
        value.raw_to_joint_scale_rad_per_unit == 0.0 ||
        (value.motor_to_joint_sign != -1 && value.motor_to_joint_sign != 1) ||
        !isfinite(value.output_per_motor_ratio) || value.output_per_motor_ratio <= 0.0) {
        return ObservationCode::CALIBRATION_INVALID;
    }
    if (value.wrap_enabled) {
        if (!isfinite(value.raw_period) || value.raw_period <= 0.0 ||
            !isfinite(value.canonical_period_rad) ||
            value.canonical_period_rad <= 0.0 ||
            (value.wrap_interval != WrapInterval::ZERO_TO_PERIOD &&
             value.wrap_interval != WrapInterval::CENTERED) ||
            fabs(fabs(value.raw_to_joint_scale_rad_per_unit) * value.raw_period -
                 value.canonical_period_rad) > 1.0e-9) {
            return ObservationCode::CALIBRATION_INVALID;
        }
    } else if (value.wrap_interval != WrapInterval::NONE ||
               value.raw_period != 0.0 || value.canonical_period_rad != 0.0) {
        return ObservationCode::CALIBRATION_INVALID;
    }
    return ObservationCode::OK;
}

ObservationCode ConvertJointObservation(
    const CalibrationSnapshot& calibration,
    const RawJointObservation& sample,
    const ObservationPolicy& policy,
    uint64_t now_ns,
    ConvertedJointObservation* output) {
    if (output == NULL) return ObservationCode::NULL_OUTPUT;
    *output = ConvertedJointObservation();
    if (ValidateCalibrationSnapshot(calibration) != ObservationCode::OK)
        return ObservationCode::CALIBRATION_INVALID;
    if (!TextValid(sample.canonical_joint_name) || !TextValid(sample.actuator_id) ||
        !TextValid(sample.sensor_id) || !ConfigValid(sample.configuration) ||
        !SourceKindValid(sample.source_kind) || !UnitValid(sample.raw_unit) ||
        sample.sequence == 0U || !isfinite(sample.raw_value) ||
        policy.maximum_sample_age_ns == 0U ||
        policy.maximum_receive_age_ns == 0U ||
        !EvidenceValid(policy.required_evidence_class)) {
        return ObservationCode::SAMPLE_INVALID;
    }
    if (!TextSame(calibration.canonical_joint_name, sample.canonical_joint_name) ||
        !TextSame(calibration.actuator_id, sample.actuator_id) ||
        !TextSame(calibration.sensor_id, sample.sensor_id) ||
        !ConfigSame(calibration.configuration, sample.configuration))
        return ObservationCode::IDENTITY_MISMATCH;
    if (calibration.source_kind != sample.source_kind)
        return ObservationCode::SOURCE_KIND_MISMATCH;
    if (calibration.raw_unit != sample.raw_unit)
        return ObservationCode::UNIT_MISMATCH;
    if (calibration.evidence_class != policy.required_evidence_class)
        return ObservationCode::EVIDENCE_CLASS_MISMATCH;
    if (now_ns < calibration.valid_from_ns)
        return ObservationCode::CALIBRATION_NOT_YET_VALID;
    if (now_ns > calibration.valid_until_ns)
        return ObservationCode::CALIBRATION_EXPIRED;
    if (sample.sample_time_ns > now_ns) return ObservationCode::SAMPLE_TIME_FUTURE;
    if (sample.receive_time_ns > now_ns) return ObservationCode::RECEIVE_TIME_FUTURE;
    if (sample.receive_time_ns < sample.sample_time_ns)
        return ObservationCode::TIME_ORDER_INVALID;
    if (sample.sample_time_ns < calibration.valid_from_ns ||
        sample.sample_time_ns > calibration.valid_until_ns)
        return ObservationCode::SAMPLE_OUTSIDE_CALIBRATION_VALIDITY;
    const uint64_t sample_age = now_ns - sample.sample_time_ns;
    const uint64_t receive_age = now_ns - sample.receive_time_ns;
    if (sample_age > policy.maximum_sample_age_ns)
        return ObservationCode::SAMPLE_STALE;
    if (receive_age > policy.maximum_receive_age_ns)
        return ObservationCode::RECEIVE_STALE;
    if (sample.source_fault) return ObservationCode::SOURCE_FAULT;
    if (!sample.quality_valid) return ObservationCode::SOURCE_QUALITY_INVALID;

    double delta = sample.raw_value;
    double position = 0.0;
    if (sample.source_kind == ObservationSourceKind::NATIVE_MOTOR) {
        delta -= calibration.native_output_zero_rad;
        position = calibration.joint_zero_rad +
                   static_cast<double>(calibration.motor_to_joint_sign) *
                       calibration.output_per_motor_ratio * delta;
    } else if (sample.source_kind == ObservationSourceKind::NATIVE_OUTPUT) {
        delta -= calibration.native_output_zero_rad;
        position = calibration.joint_zero_rad +
                   static_cast<double>(calibration.motor_to_joint_sign) * delta;
    } else {
        delta -= calibration.raw_zero;
        if (calibration.wrap_enabled)
            delta = WrapRaw(delta, calibration.raw_period,
                            calibration.wrap_interval);
        position = calibration.joint_zero_rad +
                   static_cast<double>(calibration.motor_to_joint_sign) *
                       calibration.raw_to_joint_scale_rad_per_unit * delta;
    }
    if (!isfinite(position)) return ObservationCode::CONVERSION_NONFINITE;

    output->canonical_joint_name = sample.canonical_joint_name;
    output->actuator_id = sample.actuator_id;
    output->sensor_id = sample.sensor_id;
    output->configuration = sample.configuration;
    output->calibration_record_id = calibration.record_id;
    output->source_kind = sample.source_kind;
    output->evidence_class = calibration.evidence_class;
    output->calibration_generation = calibration.generation;
    output->sequence = sample.sequence;
    output->sample_time_ns = sample.sample_time_ns;
    output->receive_time_ns = sample.receive_time_ns;
    output->sample_age_ns = sample_age;
    output->receive_age_ns = receive_age;
    output->joint_position_rad = position;
    return ObservationCode::OK;
}

ObservationStreamGuard::ObservationStreamGuard() { reset(); }

void ObservationStreamGuard::reset() {
    initialized_ = false;
    canonical_joint_name_ = hostlink_v1::Text();
    actuator_id_ = hostlink_v1::Text();
    sensor_id_ = hostlink_v1::Text();
    configuration_ = hostlink_v1::ConfigIdentity();
    calibration_generation_ = 0U;
    sequence_ = 0U;
    sample_time_ns_ = 0U;
    receive_time_ns_ = 0U;
}

bool ObservationStreamGuard::initialized() const { return initialized_; }

ObservationCode ObservationStreamGuard::convert(
    const CalibrationSnapshot& calibration,
    const RawJointObservation& sample,
    const ObservationPolicy& policy,
    uint64_t now_ns,
    ConvertedJointObservation* output) {
    if (output == NULL) return ObservationCode::NULL_OUTPUT;
    *output = ConvertedJointObservation();
    ConvertedJointObservation candidate = {};
    const ObservationCode converted = ConvertJointObservation(
        calibration, sample, policy, now_ns, &candidate);
    if (converted != ObservationCode::OK) return converted;
    if (initialized_) {
        if (!TextSame(candidate.canonical_joint_name, canonical_joint_name_) ||
            !TextSame(candidate.actuator_id, actuator_id_) ||
            !TextSame(candidate.sensor_id, sensor_id_) ||
            !ConfigSame(candidate.configuration, configuration_))
            return ObservationCode::IDENTITY_MISMATCH;
        if (candidate.calibration_generation < calibration_generation_)
            return ObservationCode::CALIBRATION_GENERATION_REGRESSION;
        if (candidate.sequence <= sequence_)
            return ObservationCode::SEQUENCE_REPLAY;
        if (candidate.sample_time_ns < sample_time_ns_)
            return ObservationCode::SAMPLE_TIME_REGRESSION;
        if (candidate.receive_time_ns < receive_time_ns_)
            return ObservationCode::RECEIVE_TIME_REGRESSION;
    }
    initialized_ = true;
    canonical_joint_name_ = candidate.canonical_joint_name;
    actuator_id_ = candidate.actuator_id;
    sensor_id_ = candidate.sensor_id;
    configuration_ = candidate.configuration;
    calibration_generation_ = candidate.calibration_generation;
    sequence_ = candidate.sequence;
    sample_time_ns_ = candidate.sample_time_ns;
    receive_time_ns_ = candidate.receive_time_ns;
    *output = candidate;
    return ObservationCode::OK;
}

const char* ReconciliationCodeName(ReconciliationCode code) {
    switch (code) {
        case ReconciliationCode::OK: return "OK";
        case ReconciliationCode::NULL_OUTPUT: return "NULL_OUTPUT";
        case ReconciliationCode::POLICY_INVALID: return "POLICY_INVALID";
        case ReconciliationCode::EXTERNAL_REQUIRED: return "EXTERNAL_REQUIRED";
        case ReconciliationCode::NATIVE_REQUIRED: return "NATIVE_REQUIRED";
        case ReconciliationCode::OBSERVATION_IDENTITY_MISMATCH: return "OBSERVATION_IDENTITY_MISMATCH";
        case ReconciliationCode::EVIDENCE_CLASS_MISMATCH: return "EVIDENCE_CLASS_MISMATCH";
        case ReconciliationCode::SENSOR_ALIAS_FORBIDDEN: return "SENSOR_ALIAS_FORBIDDEN";
        case ReconciliationCode::DISAGREEMENT_EXCEEDED: return "DISAGREEMENT_EXCEEDED";
    }
    return "UNKNOWN_RECONCILIATION_CODE";
}

ReconciliationCode ReconcileJointObservations(
    const ReconciliationPolicy& policy,
    const ConvertedJointObservation* external,
    const ConvertedJointObservation* native,
    ReconciledJointObservation* output) {
    if (output == NULL) return ReconciliationCode::NULL_OUTPUT;
    *output = ReconciledJointObservation();
    if (!TextValid(policy.canonical_joint_name) || !TextValid(policy.actuator_id) ||
        !TextValid(policy.external_sensor_id) || !TextValid(policy.native_sensor_id) ||
        !ConfigValid(policy.configuration) || policy.generation == 0U ||
        policy.mode < ReconciliationMode::EXTERNAL_ONLY ||
        policy.mode > ReconciliationMode::REQUIRE_BOTH_PREFER_NATIVE ||
        !EvidenceValid(policy.required_evidence_class) ||
        !isfinite(policy.maximum_disagreement_rad) ||
        policy.maximum_disagreement_rad < 0.0)
        return ReconciliationCode::POLICY_INVALID;
    if (TextSame(policy.external_sensor_id, policy.native_sensor_id))
        return ReconciliationCode::SENSOR_ALIAS_FORBIDDEN;
    const bool need_external = policy.mode != ReconciliationMode::NATIVE_ONLY;
    const bool need_native = policy.mode != ReconciliationMode::EXTERNAL_ONLY;
    if (need_external && external == NULL)
        return ReconciliationCode::EXTERNAL_REQUIRED;
    if (need_native && native == NULL)
        return ReconciliationCode::NATIVE_REQUIRED;
    if (external != NULL &&
        !ObservationIdentitySame(*external, policy, policy.external_sensor_id))
        return ReconciliationCode::OBSERVATION_IDENTITY_MISMATCH;
    if (native != NULL &&
        !ObservationIdentitySame(*native, policy, policy.native_sensor_id))
        return ReconciliationCode::OBSERVATION_IDENTITY_MISMATCH;
    if ((external != NULL && external->evidence_class != policy.required_evidence_class) ||
        (native != NULL && native->evidence_class != policy.required_evidence_class))
        return ReconciliationCode::EVIDENCE_CLASS_MISMATCH;

    double disagreement = 0.0;
    if (external != NULL && native != NULL) {
        disagreement = fabs(external->joint_position_rad - native->joint_position_rad);
        if (!isfinite(disagreement) || disagreement > policy.maximum_disagreement_rad)
            return ReconciliationCode::DISAGREEMENT_EXCEEDED;
    }
    const ConvertedJointObservation* selected = external;
    if (policy.mode == ReconciliationMode::NATIVE_ONLY ||
        policy.mode == ReconciliationMode::REQUIRE_BOTH_PREFER_NATIVE)
        selected = native;
    output->canonical_joint_name = policy.canonical_joint_name;
    output->actuator_id = policy.actuator_id;
    output->configuration = policy.configuration;
    output->policy_generation = policy.generation;
    output->mode = policy.mode;
    output->selected_source_kind = selected->source_kind;
    output->selected_sensor_id = selected->sensor_id;
    output->selected_sample_time_ns = selected->sample_time_ns;
    output->joint_position_rad = selected->joint_position_rad;
    output->external_present = external != NULL;
    output->native_present = native != NULL;
    output->external_position_rad = external != NULL ? external->joint_position_rad : 0.0;
    output->native_position_rad = native != NULL ? native->joint_position_rad : 0.0;
    output->disagreement_rad = disagreement;
    return ReconciliationCode::OK;
}

const char* PositionLimitCodeName(PositionLimitCode code) {
    switch (code) {
        case PositionLimitCode::OK: return "OK";
        case PositionLimitCode::SNAPSHOT_INVALID: return "SNAPSHOT_INVALID";
        case PositionLimitCode::OBSERVATION_IDENTITY_MISMATCH: return "OBSERVATION_IDENTITY_MISMATCH";
        case PositionLimitCode::NOT_YET_VALID: return "NOT_YET_VALID";
        case PositionLimitCode::EXPIRED: return "EXPIRED";
        case PositionLimitCode::BELOW_LOWER: return "BELOW_LOWER";
        case PositionLimitCode::ABOVE_UPPER: return "ABOVE_UPPER";
    }
    return "UNKNOWN_POSITION_LIMIT_CODE";
}

PositionLimitCode CheckPositionLimit(
    const PositionLimitSnapshot& limit,
    const ReconciledJointObservation& observation,
    uint64_t now_ns) {
    if (!TextValid(limit.canonical_joint_name) || !TextValid(limit.actuator_id) ||
        !ConfigValid(limit.configuration) || !DigestNonzero(limit.provenance_digest) ||
        limit.generation == 0U || limit.valid_until_ns <= limit.valid_from_ns ||
        (!limit.has_lower && !limit.has_upper) ||
        (limit.has_lower && !isfinite(limit.lower_rad)) ||
        (limit.has_upper && !isfinite(limit.upper_rad)) ||
        (limit.has_lower && limit.has_upper && limit.lower_rad > limit.upper_rad))
        return PositionLimitCode::SNAPSHOT_INVALID;
    if (!TextSame(limit.canonical_joint_name, observation.canonical_joint_name) ||
        !TextSame(limit.actuator_id, observation.actuator_id) ||
        !ConfigSame(limit.configuration, observation.configuration) ||
        !isfinite(observation.joint_position_rad))
        return PositionLimitCode::OBSERVATION_IDENTITY_MISMATCH;
    if (now_ns < limit.valid_from_ns) return PositionLimitCode::NOT_YET_VALID;
    if (now_ns > limit.valid_until_ns) return PositionLimitCode::EXPIRED;
    if (limit.has_lower && observation.joint_position_rad < limit.lower_rad)
        return PositionLimitCode::BELOW_LOWER;
    if (limit.has_upper && observation.joint_position_rad > limit.upper_rad)
        return PositionLimitCode::ABOVE_UPPER;
    return PositionLimitCode::OK;
}

}  // namespace runtime
}  // namespace myactuator
