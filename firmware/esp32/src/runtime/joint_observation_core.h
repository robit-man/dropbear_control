#pragma once

// Allocation-free calibration, timestamp-validity and joint-observation
// reconciliation. This core performs no I/O and cannot authorize motion.

#include <stdint.h>

#include "../hostlink/hostlink_v1.h"

namespace myactuator {
namespace runtime {

enum class ObservationSourceKind : uint8_t {
    EXTERNAL_ABSOLUTE = 1,
    EXTERNAL_INCREMENTAL,
    NATIVE_MOTOR,
    NATIVE_OUTPUT,
    SYNTHETIC_PLANT,
};

enum class RawObservationUnit : uint8_t {
    COUNT = 1,
    VOLT,
    RADIAN,
    DEGREE,
};

enum class CalibrationEvidenceClass : uint8_t {
    SYNTHETIC_FIXTURE = 1,
    PHYSICAL_BENCH,
};

enum class WrapInterval : uint8_t {
    NONE = 0,
    ZERO_TO_PERIOD,
    CENTERED,
};

struct CalibrationSnapshot {
    hostlink_v1::Text record_id;
    hostlink_v1::Text canonical_joint_name;
    hostlink_v1::Text actuator_id;
    hostlink_v1::Text sensor_id;
    hostlink_v1::ConfigIdentity configuration;
    hostlink_v1::Sha256 subject_digest;
    hostlink_v1::Sha256 record_digest;
    uint32_t generation;
    uint64_t valid_from_ns;
    uint64_t valid_until_ns;
    CalibrationEvidenceClass evidence_class;
    ObservationSourceKind source_kind;
    RawObservationUnit raw_unit;
    double raw_zero;
    double joint_zero_rad;
    double native_output_zero_rad;
    double raw_to_joint_scale_rad_per_unit;
    int8_t motor_to_joint_sign;
    double output_per_motor_ratio;
    bool wrap_enabled;
    double raw_period;
    double canonical_period_rad;
    WrapInterval wrap_interval;
};

struct RawJointObservation {
    hostlink_v1::Text canonical_joint_name;
    hostlink_v1::Text actuator_id;
    hostlink_v1::Text sensor_id;
    hostlink_v1::ConfigIdentity configuration;
    ObservationSourceKind source_kind;
    RawObservationUnit raw_unit;
    uint64_t sequence;
    uint64_t sample_time_ns;
    uint64_t receive_time_ns;
    double raw_value;
    bool source_fault;
    bool quality_valid;
};

struct ObservationPolicy {
    uint64_t maximum_sample_age_ns;
    uint64_t maximum_receive_age_ns;
    CalibrationEvidenceClass required_evidence_class;
};

struct ConvertedJointObservation {
    hostlink_v1::Text canonical_joint_name;
    hostlink_v1::Text actuator_id;
    hostlink_v1::Text sensor_id;
    hostlink_v1::ConfigIdentity configuration;
    hostlink_v1::Text calibration_record_id;
    ObservationSourceKind source_kind;
    CalibrationEvidenceClass evidence_class;
    uint32_t calibration_generation;
    uint64_t sequence;
    uint64_t sample_time_ns;
    uint64_t receive_time_ns;
    uint64_t sample_age_ns;
    uint64_t receive_age_ns;
    double joint_position_rad;
};

enum class ObservationCode : uint8_t {
    OK = 0,
    NULL_OUTPUT,
    CALIBRATION_INVALID,
    SAMPLE_INVALID,
    IDENTITY_MISMATCH,
    SOURCE_KIND_MISMATCH,
    UNIT_MISMATCH,
    EVIDENCE_CLASS_MISMATCH,
    CALIBRATION_NOT_YET_VALID,
    CALIBRATION_EXPIRED,
    SAMPLE_TIME_FUTURE,
    RECEIVE_TIME_FUTURE,
    TIME_ORDER_INVALID,
    SAMPLE_STALE,
    RECEIVE_STALE,
    SOURCE_FAULT,
    SOURCE_QUALITY_INVALID,
    SAMPLE_OUTSIDE_CALIBRATION_VALIDITY,
    SEQUENCE_REPLAY,
    SAMPLE_TIME_REGRESSION,
    RECEIVE_TIME_REGRESSION,
    CALIBRATION_GENERATION_REGRESSION,
    CONVERSION_NONFINITE,
};

const char* ObservationCodeName(ObservationCode code);
ObservationCode ValidateCalibrationSnapshot(const CalibrationSnapshot& value);
ObservationCode ConvertJointObservation(
    const CalibrationSnapshot& calibration,
    const RawJointObservation& sample,
    const ObservationPolicy& policy,
    uint64_t now_ns,
    ConvertedJointObservation* output);

// Adds stateful per-stream replay/order enforcement around the pure
// conversion. A denial never advances the window or exposes a partial output.
class ObservationStreamGuard {
public:
    ObservationStreamGuard();
    void reset();
    bool initialized() const;
    ObservationCode convert(const CalibrationSnapshot& calibration,
                            const RawJointObservation& sample,
                            const ObservationPolicy& policy,
                            uint64_t now_ns,
                            ConvertedJointObservation* output);

private:
    bool initialized_;
    hostlink_v1::Text canonical_joint_name_;
    hostlink_v1::Text actuator_id_;
    hostlink_v1::Text sensor_id_;
    hostlink_v1::ConfigIdentity configuration_;
    uint32_t calibration_generation_;
    uint64_t sequence_;
    uint64_t sample_time_ns_;
    uint64_t receive_time_ns_;
};

enum class ReconciliationMode : uint8_t {
    EXTERNAL_ONLY = 1,
    NATIVE_ONLY,
    REQUIRE_BOTH_PREFER_EXTERNAL,
    REQUIRE_BOTH_PREFER_NATIVE,
};

struct ReconciliationPolicy {
    hostlink_v1::Text canonical_joint_name;
    hostlink_v1::Text actuator_id;
    hostlink_v1::Text external_sensor_id;
    hostlink_v1::Text native_sensor_id;
    hostlink_v1::ConfigIdentity configuration;
    uint32_t generation;
    ReconciliationMode mode;
    CalibrationEvidenceClass required_evidence_class;
    double maximum_disagreement_rad;
};

struct ReconciledJointObservation {
    hostlink_v1::Text canonical_joint_name;
    hostlink_v1::Text actuator_id;
    hostlink_v1::ConfigIdentity configuration;
    uint32_t policy_generation;
    ReconciliationMode mode;
    ObservationSourceKind selected_source_kind;
    hostlink_v1::Text selected_sensor_id;
    uint64_t selected_sample_time_ns;
    double joint_position_rad;
    bool external_present;
    bool native_present;
    double external_position_rad;
    double native_position_rad;
    double disagreement_rad;
};

enum class ReconciliationCode : uint8_t {
    OK = 0,
    NULL_OUTPUT,
    POLICY_INVALID,
    EXTERNAL_REQUIRED,
    NATIVE_REQUIRED,
    OBSERVATION_IDENTITY_MISMATCH,
    EVIDENCE_CLASS_MISMATCH,
    SENSOR_ALIAS_FORBIDDEN,
    DISAGREEMENT_EXCEEDED,
};

const char* ReconciliationCodeName(ReconciliationCode code);
ReconciliationCode ReconcileJointObservations(
    const ReconciliationPolicy& policy,
    const ConvertedJointObservation* external,
    const ConvertedJointObservation* native,
    ReconciledJointObservation* output);

struct PositionLimitSnapshot {
    hostlink_v1::Text canonical_joint_name;
    hostlink_v1::Text actuator_id;
    hostlink_v1::ConfigIdentity configuration;
    hostlink_v1::Sha256 provenance_digest;
    uint32_t generation;
    uint64_t valid_from_ns;
    uint64_t valid_until_ns;
    bool has_lower;
    bool has_upper;
    double lower_rad;
    double upper_rad;
};

enum class PositionLimitCode : uint8_t {
    OK = 0,
    SNAPSHOT_INVALID,
    OBSERVATION_IDENTITY_MISMATCH,
    NOT_YET_VALID,
    EXPIRED,
    BELOW_LOWER,
    ABOVE_UPPER,
};

const char* PositionLimitCodeName(PositionLimitCode code);
PositionLimitCode CheckPositionLimit(
    const PositionLimitSnapshot& limit,
    const ReconciledJointObservation& observation,
    uint64_t now_ns);

}  // namespace runtime
}  // namespace myactuator
