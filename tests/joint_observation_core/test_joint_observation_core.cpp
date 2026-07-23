#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <limits>

#include "hostlink_v1.h"
#include "joint_observation_core.h"

namespace host = myactuator::hostlink_v1;
namespace rt = myactuator::runtime;

namespace {

int failures = 0;
#define CHECK(condition) do { if (!(condition)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

void Set(host::Text* output, const char* value) {
    CHECK(host::SetText(output, value, strlen(value)) == host::Status::OK);
}

host::Sha256 Digest(uint8_t seed) {
    host::Sha256 value = {};
    for (size_t index = 0U; index < sizeof(value.bytes); ++index)
        value.bytes[index] = static_cast<uint8_t>(seed + index);
    return value;
}

host::ConfigIdentity Config() {
    host::ConfigIdentity value = {};
    Set(&value.identity, "dropbear-prototype-observation");
    Set(&value.revision, "1");
    value.sha256 = Digest(1U);
    return value;
}

rt::CalibrationSnapshot Calibration(
    rt::ObservationSourceKind source = rt::ObservationSourceKind::EXTERNAL_ABSOLUTE,
    const char* sensor = "left-hip-roll-external") {
    rt::CalibrationSnapshot value = {};
    Set(&value.record_id, "synthetic-left-hip-roll-r1");
    Set(&value.canonical_joint_name, "left_hip_roll");
    Set(&value.actuator_id, "actuator-left-hip-roll");
    Set(&value.sensor_id, sensor);
    value.configuration = Config();
    value.subject_digest = Digest(2U);
    value.record_digest = Digest(3U);
    value.generation = 7U;
    value.valid_from_ns = 100U;
    value.valid_until_ns = 1000U;
    value.evidence_class = rt::CalibrationEvidenceClass::SYNTHETIC_FIXTURE;
    value.source_kind = source;
    value.raw_unit = rt::RawObservationUnit::COUNT;
    value.raw_zero = 0.0;
    value.joint_zero_rad = 0.0;
    value.native_output_zero_rad = 0.0;
    value.raw_to_joint_scale_rad_per_unit = 2.0 * M_PI / 4096.0;
    value.motor_to_joint_sign = 1;
    value.output_per_motor_ratio = 0.1;
    value.wrap_enabled = true;
    value.raw_period = 4096.0;
    value.canonical_period_rad = 2.0 * M_PI;
    value.wrap_interval = rt::WrapInterval::CENTERED;
    if (source == rt::ObservationSourceKind::NATIVE_MOTOR ||
        source == rt::ObservationSourceKind::NATIVE_OUTPUT) {
        value.raw_unit = rt::RawObservationUnit::RADIAN;
        value.wrap_enabled = false;
        value.raw_period = 0.0;
        value.canonical_period_rad = 0.0;
        value.wrap_interval = rt::WrapInterval::NONE;
    }
    return value;
}

rt::RawJointObservation Sample(
    rt::ObservationSourceKind source = rt::ObservationSourceKind::EXTERNAL_ABSOLUTE,
    const char* sensor = "left-hip-roll-external") {
    rt::RawJointObservation value = {};
    Set(&value.canonical_joint_name, "left_hip_roll");
    Set(&value.actuator_id, "actuator-left-hip-roll");
    Set(&value.sensor_id, sensor);
    value.configuration = Config();
    value.source_kind = source;
    value.raw_unit = source == rt::ObservationSourceKind::NATIVE_MOTOR ||
                             source == rt::ObservationSourceKind::NATIVE_OUTPUT
                         ? rt::RawObservationUnit::RADIAN
                         : rt::RawObservationUnit::COUNT;
    value.sequence = 1U;
    value.sample_time_ns = 800U;
    value.receive_time_ns = 850U;
    value.raw_value = 1024.0;
    value.source_fault = false;
    value.quality_valid = true;
    return value;
}

rt::ObservationPolicy ObservationPolicy() {
    rt::ObservationPolicy value = {};
    value.maximum_sample_age_ns = 200U;
    value.maximum_receive_age_ns = 150U;
    value.required_evidence_class = rt::CalibrationEvidenceClass::SYNTHETIC_FIXTURE;
    return value;
}

rt::ConvertedJointObservation Convert(
    rt::ObservationSourceKind source,
    const char* sensor,
    double raw) {
    rt::RawJointObservation sample = Sample(source, sensor);
    sample.raw_value = raw;
    rt::ConvertedJointObservation output = {};
    CHECK(rt::ConvertJointObservation(Calibration(source, sensor), sample,
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::OK);
    return output;
}

rt::ReconciliationPolicy ReconciliationPolicy(
    rt::ReconciliationMode mode =
        rt::ReconciliationMode::REQUIRE_BOTH_PREFER_EXTERNAL) {
    rt::ReconciliationPolicy value = {};
    Set(&value.canonical_joint_name, "left_hip_roll");
    Set(&value.actuator_id, "actuator-left-hip-roll");
    Set(&value.external_sensor_id, "left-hip-roll-external");
    Set(&value.native_sensor_id, "left-hip-roll-native");
    value.configuration = Config();
    value.generation = 3U;
    value.mode = mode;
    value.required_evidence_class =
        rt::CalibrationEvidenceClass::SYNTHETIC_FIXTURE;
    value.maximum_disagreement_rad = 0.1;
    return value;
}

bool Near(double left, double right) { return fabs(left - right) < 1.0e-10; }

void TestCalibrationAndConversion() {
    rt::ConvertedJointObservation output = {};
    CHECK(rt::ValidateCalibrationSnapshot(Calibration()) == rt::ObservationCode::OK);
    CHECK(rt::ConvertJointObservation(Calibration(), Sample(),
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::OK);
    CHECK(Near(output.joint_position_rad, M_PI / 2.0));
    CHECK(output.sample_age_ns == 100U);
    CHECK(output.receive_age_ns == 50U);
    CHECK(output.calibration_generation == 7U);

    rt::RawJointObservation wrapped = Sample();
    wrapped.raw_value = 4095.0;
    CHECK(rt::ConvertJointObservation(Calibration(), wrapped,
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::OK);
    CHECK(Near(output.joint_position_rad, -2.0 * M_PI / 4096.0));

    rt::CalibrationSnapshot native_cal = Calibration(
        rt::ObservationSourceKind::NATIVE_MOTOR, "left-hip-roll-native");
    native_cal.motor_to_joint_sign = -1;
    rt::RawJointObservation native = Sample(
        rt::ObservationSourceKind::NATIVE_MOTOR, "left-hip-roll-native");
    native.raw_value = 2.0;
    CHECK(rt::ConvertJointObservation(native_cal, native,
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::OK);
    CHECK(Near(output.joint_position_rad, -0.2));
}

void TestCalibrationValidation() {
    rt::CalibrationSnapshot value = Calibration();
    value.generation = 0U;
    CHECK(rt::ValidateCalibrationSnapshot(value) ==
          rt::ObservationCode::CALIBRATION_INVALID);
    value = Calibration();
    value.record_digest = host::Sha256();
    CHECK(rt::ValidateCalibrationSnapshot(value) ==
          rt::ObservationCode::CALIBRATION_INVALID);
    value = Calibration();
    value.motor_to_joint_sign = 0;
    CHECK(rt::ValidateCalibrationSnapshot(value) ==
          rt::ObservationCode::CALIBRATION_INVALID);
    value = Calibration();
    value.canonical_period_rad = 7.0;
    CHECK(rt::ValidateCalibrationSnapshot(value) ==
          rt::ObservationCode::CALIBRATION_INVALID);
    value = Calibration();
    value.raw_zero = std::numeric_limits<double>::quiet_NaN();
    CHECK(rt::ValidateCalibrationSnapshot(value) ==
          rt::ObservationCode::CALIBRATION_INVALID);
}

void TestIdentityUnitsEvidenceAndQuality() {
    rt::ConvertedJointObservation output = {};
    rt::RawJointObservation sample = Sample();
    Set(&sample.sensor_id, "another-sensor");
    CHECK(rt::ConvertJointObservation(Calibration(), sample,
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::IDENTITY_MISMATCH);
    sample = Sample();
    sample.source_kind = rt::ObservationSourceKind::EXTERNAL_INCREMENTAL;
    CHECK(rt::ConvertJointObservation(Calibration(), sample,
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::SOURCE_KIND_MISMATCH);
    sample = Sample();
    sample.raw_unit = rt::RawObservationUnit::VOLT;
    CHECK(rt::ConvertJointObservation(Calibration(), sample,
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::UNIT_MISMATCH);
    rt::ObservationPolicy policy = ObservationPolicy();
    policy.required_evidence_class = rt::CalibrationEvidenceClass::PHYSICAL_BENCH;
    CHECK(rt::ConvertJointObservation(Calibration(), Sample(), policy, 900U,
                                      &output) ==
          rt::ObservationCode::EVIDENCE_CLASS_MISMATCH);
    sample = Sample();
    sample.source_fault = true;
    CHECK(rt::ConvertJointObservation(Calibration(), sample,
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::SOURCE_FAULT);
    sample = Sample();
    sample.quality_valid = false;
    CHECK(rt::ConvertJointObservation(Calibration(), sample,
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::SOURCE_QUALITY_INVALID);
}

void TestTimeDenialsAndBoundaries() {
    rt::ConvertedJointObservation output = {};
    CHECK(rt::ConvertJointObservation(Calibration(), Sample(),
                                      ObservationPolicy(), 99U, &output) ==
          rt::ObservationCode::CALIBRATION_NOT_YET_VALID);
    CHECK(rt::ConvertJointObservation(Calibration(), Sample(),
                                      ObservationPolicy(), 1001U, &output) ==
          rt::ObservationCode::CALIBRATION_EXPIRED);
    rt::RawJointObservation sample = Sample();
    sample.sample_time_ns = 901U;
    CHECK(rt::ConvertJointObservation(Calibration(), sample,
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::SAMPLE_TIME_FUTURE);
    sample = Sample();
    sample.receive_time_ns = 901U;
    CHECK(rt::ConvertJointObservation(Calibration(), sample,
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::RECEIVE_TIME_FUTURE);
    sample = Sample();
    sample.receive_time_ns = 799U;
    CHECK(rt::ConvertJointObservation(Calibration(), sample,
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::TIME_ORDER_INVALID);
    sample = Sample();
    sample.sample_time_ns = 699U;
    CHECK(rt::ConvertJointObservation(Calibration(), sample,
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::SAMPLE_STALE);
    sample = Sample();
    sample.sample_time_ns = 700U;
    sample.receive_time_ns = 750U;
    CHECK(rt::ConvertJointObservation(Calibration(), sample,
                                      ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::OK);
    sample = Sample();
    sample.sample_time_ns = 99U;
    sample.receive_time_ns = 100U;
    rt::ObservationPolicy wide = ObservationPolicy();
    wide.maximum_sample_age_ns = 1000U;
    wide.maximum_receive_age_ns = 1000U;
    CHECK(rt::ConvertJointObservation(Calibration(), sample, wide, 900U,
                                      &output) ==
          rt::ObservationCode::SAMPLE_OUTSIDE_CALIBRATION_VALIDITY);
}

void TestStreamReplayAndRegression() {
    rt::ObservationStreamGuard stream;
    rt::ConvertedJointObservation output = {};
    CHECK(!stream.initialized());
    CHECK(stream.convert(Calibration(), Sample(), ObservationPolicy(), 900U,
                         &output) == rt::ObservationCode::OK);
    CHECK(stream.initialized());
    rt::RawJointObservation next = Sample();
    next.sequence = 2U;
    next.sample_time_ns = 810U;
    next.receive_time_ns = 860U;
    CHECK(stream.convert(Calibration(), next, ObservationPolicy(), 900U,
                         &output) == rt::ObservationCode::OK);
    CHECK(stream.convert(Calibration(), next, ObservationPolicy(), 900U,
                         &output) == rt::ObservationCode::SEQUENCE_REPLAY);
    CHECK(output.sequence == 0U);

    next.sequence = 3U;
    next.sample_time_ns = 809U;
    CHECK(stream.convert(Calibration(), next, ObservationPolicy(), 900U,
                         &output) ==
          rt::ObservationCode::SAMPLE_TIME_REGRESSION);
    next.sample_time_ns = 820U;
    next.receive_time_ns = 859U;
    CHECK(stream.convert(Calibration(), next, ObservationPolicy(), 900U,
                         &output) ==
          rt::ObservationCode::RECEIVE_TIME_REGRESSION);
    next.receive_time_ns = 870U;
    rt::CalibrationSnapshot older = Calibration();
    older.generation = 6U;
    CHECK(stream.convert(older, next, ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::CALIBRATION_GENERATION_REGRESSION);
    stream.reset();
    CHECK(!stream.initialized());
    CHECK(stream.convert(older, next, ObservationPolicy(), 900U, &output) ==
          rt::ObservationCode::OK);
}

void TestReconciliationIsExplicitAndNeverAverages() {
    const rt::ConvertedJointObservation external = Convert(
        rt::ObservationSourceKind::EXTERNAL_ABSOLUTE,
        "left-hip-roll-external", 64.0);
    const rt::ConvertedJointObservation native = Convert(
        rt::ObservationSourceKind::NATIVE_OUTPUT,
        "left-hip-roll-native", external.joint_position_rad + 0.05);
    rt::ReconciledJointObservation output = {};
    CHECK(rt::ReconcileJointObservations(ReconciliationPolicy(), &external,
                                         &native, &output) ==
          rt::ReconciliationCode::OK);
    CHECK(Near(output.joint_position_rad, external.joint_position_rad));
    CHECK(Near(output.disagreement_rad, 0.05));
    CHECK(output.external_present && output.native_present);
    CHECK(rt::ReconcileJointObservations(
              ReconciliationPolicy(
                  rt::ReconciliationMode::REQUIRE_BOTH_PREFER_NATIVE),
              &external, &native, &output) == rt::ReconciliationCode::OK);
    CHECK(Near(output.joint_position_rad, native.joint_position_rad));
}

void TestMissingHipYawAndDisagreementStayVisible() {
    const rt::ConvertedJointObservation native = Convert(
        rt::ObservationSourceKind::NATIVE_OUTPUT,
        "left-hip-roll-native", 0.0);
    rt::ReconciledJointObservation output = {};
    CHECK(rt::ReconcileJointObservations(ReconciliationPolicy(), NULL, &native,
                                         &output) ==
          rt::ReconciliationCode::EXTERNAL_REQUIRED);
    CHECK(rt::ReconcileJointObservations(
              ReconciliationPolicy(rt::ReconciliationMode::NATIVE_ONLY), NULL,
              &native, &output) == rt::ReconciliationCode::OK);
    rt::ConvertedJointObservation external = Convert(
        rt::ObservationSourceKind::EXTERNAL_ABSOLUTE,
        "left-hip-roll-external", 1024.0);
    CHECK(rt::ReconcileJointObservations(ReconciliationPolicy(), &external,
                                         &native, &output) ==
          rt::ReconciliationCode::DISAGREEMENT_EXCEEDED);
}

void TestPolicyIdentityEvidenceAndAlias() {
    rt::ConvertedJointObservation external = Convert(
        rt::ObservationSourceKind::EXTERNAL_ABSOLUTE,
        "left-hip-roll-external", 0.0);
    rt::ConvertedJointObservation native = Convert(
        rt::ObservationSourceKind::NATIVE_OUTPUT,
        "left-hip-roll-native", 0.0);
    rt::ReconciledJointObservation output = {};
    rt::ReconciliationPolicy policy = ReconciliationPolicy();
    policy.generation = 0U;
    CHECK(rt::ReconcileJointObservations(policy, &external, &native, &output) ==
          rt::ReconciliationCode::POLICY_INVALID);
    policy = ReconciliationPolicy();
    policy.native_sensor_id = policy.external_sensor_id;
    CHECK(rt::ReconcileJointObservations(policy, &external, &native, &output) ==
          rt::ReconciliationCode::SENSOR_ALIAS_FORBIDDEN);
    policy = ReconciliationPolicy();
    Set(&external.actuator_id, "actuator-right-hip-roll");
    CHECK(rt::ReconcileJointObservations(policy, &external, &native, &output) ==
          rt::ReconciliationCode::OBSERVATION_IDENTITY_MISMATCH);
    external = Convert(rt::ObservationSourceKind::EXTERNAL_ABSOLUTE,
                       "left-hip-roll-external", 0.0);
    native.evidence_class = rt::CalibrationEvidenceClass::PHYSICAL_BENCH;
    CHECK(rt::ReconcileJointObservations(policy, &external, &native, &output) ==
          rt::ReconciliationCode::EVIDENCE_CLASS_MISMATCH);
}

rt::PositionLimitSnapshot Limit() {
    rt::PositionLimitSnapshot value = {};
    Set(&value.canonical_joint_name, "left_hip_roll");
    Set(&value.actuator_id, "actuator-left-hip-roll");
    value.configuration = Config();
    value.provenance_digest = Digest(4U);
    value.generation = 2U;
    value.valid_from_ns = 100U;
    value.valid_until_ns = 1000U;
    value.has_lower = true;
    value.has_upper = true;
    value.lower_rad = -1.0;
    value.upper_rad = 1.0;
    return value;
}

void TestPositionLimit() {
    rt::ReconciledJointObservation observation = {};
    observation.canonical_joint_name = Limit().canonical_joint_name;
    observation.actuator_id = Limit().actuator_id;
    observation.configuration = Config();
    observation.joint_position_rad = 0.0;
    CHECK(rt::CheckPositionLimit(Limit(), observation, 500U) ==
          rt::PositionLimitCode::OK);
    observation.joint_position_rad = -1.0;
    CHECK(rt::CheckPositionLimit(Limit(), observation, 500U) ==
          rt::PositionLimitCode::OK);
    observation.joint_position_rad = -1.01;
    CHECK(rt::CheckPositionLimit(Limit(), observation, 500U) ==
          rt::PositionLimitCode::BELOW_LOWER);
    observation.joint_position_rad = 1.01;
    CHECK(rt::CheckPositionLimit(Limit(), observation, 500U) ==
          rt::PositionLimitCode::ABOVE_UPPER);
    CHECK(rt::CheckPositionLimit(Limit(), observation, 99U) ==
          rt::PositionLimitCode::NOT_YET_VALID);
    CHECK(rt::CheckPositionLimit(Limit(), observation, 1001U) ==
          rt::PositionLimitCode::EXPIRED);
    rt::PositionLimitSnapshot invalid = Limit();
    invalid.lower_rad = 2.0;
    CHECK(rt::CheckPositionLimit(invalid, observation, 500U) ==
          rt::PositionLimitCode::SNAPSHOT_INVALID);
}

void TestSharedGoldenCorpus() {
    FILE* file = fopen(
        "tests/joint_observation_core/golden_runtime.jsonl", "rb");
    CHECK(file != NULL);
    if (file == NULL) return;
    char line[512] = {};
    size_t count = 0U;
    while (fgets(line, sizeof(line), file) != NULL) {
        char case_id[96] = {};
        char expected_code[64] = {};
        char expected_numeric[64] = {};
        char operation[32] = {};
        char variant[64] = {};
        const int parsed = sscanf(
            line,
            "{\"case\":\"%95[^\"]\",\"expected_code\":\"%63[^\"]\",\"expected_numeric\":\"%63[^\"]\",\"operation\":\"%31[^\"]\",\"variant\":\"%63[^\"]\"}",
            case_id, expected_code, expected_numeric, operation, variant);
        CHECK(parsed == 5);
        if (parsed != 5) continue;
        const char* actual_code = "UNSET";
        bool has_numeric = false;
        double actual_numeric = 0.0;

        if (strcmp(operation, "convert") == 0) {
            rt::CalibrationSnapshot cal = Calibration();
            rt::RawJointObservation raw = Sample();
            rt::ObservationPolicy policy = ObservationPolicy();
            uint64_t now = 900U;
            if (strcmp(variant, "external_centered_wrap") == 0) {
                raw.raw_value = 4095.0;
            } else if (strcmp(variant, "native_motor_negative") == 0) {
                cal = Calibration(rt::ObservationSourceKind::NATIVE_MOTOR,
                                  "left-hip-roll-native");
                cal.motor_to_joint_sign = -1;
                raw = Sample(rt::ObservationSourceKind::NATIVE_MOTOR,
                             "left-hip-roll-native");
                raw.raw_value = 2.0;
            } else if (strcmp(variant, "native_output") == 0) {
                cal = Calibration(rt::ObservationSourceKind::NATIVE_OUTPUT,
                                  "left-hip-roll-native");
                raw = Sample(rt::ObservationSourceKind::NATIVE_OUTPUT,
                             "left-hip-roll-native");
                raw.raw_value = 0.25;
            } else if (strcmp(variant, "synthetic_plant") == 0) {
                cal = Calibration(rt::ObservationSourceKind::SYNTHETIC_PLANT,
                                  "synthetic-sensor");
                raw = Sample(rt::ObservationSourceKind::SYNTHETIC_PLANT,
                             "synthetic-sensor");
            } else if (strcmp(variant, "calibration_invalid") == 0) {
                cal.generation = 0U;
            } else if (strcmp(variant, "identity_mismatch") == 0) {
                Set(&raw.sensor_id, "another-sensor");
            } else if (strcmp(variant, "source_mismatch") == 0) {
                raw.source_kind =
                    rt::ObservationSourceKind::EXTERNAL_INCREMENTAL;
            } else if (strcmp(variant, "unit_mismatch") == 0) {
                raw.raw_unit = rt::RawObservationUnit::VOLT;
            } else if (strcmp(variant, "evidence_mismatch") == 0) {
                policy.required_evidence_class =
                    rt::CalibrationEvidenceClass::PHYSICAL_BENCH;
            } else if (strcmp(variant, "not_yet_valid") == 0) {
                now = 99U;
            } else if (strcmp(variant, "expired") == 0) {
                now = 1001U;
            } else if (strcmp(variant, "sample_future") == 0) {
                raw.sample_time_ns = 901U;
            } else if (strcmp(variant, "receive_future") == 0) {
                raw.receive_time_ns = 901U;
            } else if (strcmp(variant, "time_order") == 0) {
                raw.receive_time_ns = 799U;
            } else if (strcmp(variant, "sample_stale") == 0) {
                raw.sample_time_ns = 699U;
            } else if (strcmp(variant, "receive_stale") == 0) {
                raw.sample_time_ns = 700U;
                raw.receive_time_ns = 749U;
            } else if (strcmp(variant, "source_fault") == 0) {
                raw.source_fault = true;
            } else if (strcmp(variant, "quality_invalid") == 0) {
                raw.quality_valid = false;
            } else if (strcmp(variant, "sample_outside_calibration") == 0) {
                raw.sample_time_ns = 99U;
                raw.receive_time_ns = 100U;
                policy.maximum_sample_age_ns = 1000U;
                policy.maximum_receive_age_ns = 1000U;
            }
            rt::ConvertedJointObservation output = {};
            const rt::ObservationCode code = rt::ConvertJointObservation(
                cal, raw, policy, now, &output);
            actual_code = rt::ObservationCodeName(code);
            if (code == rt::ObservationCode::OK) {
                has_numeric = true;
                actual_numeric = output.joint_position_rad;
            }
        } else if (strcmp(operation, "stream") == 0) {
            rt::ObservationStreamGuard stream;
            rt::ConvertedJointObservation output = {};
            CHECK(stream.convert(Calibration(), Sample(), ObservationPolicy(),
                                 900U, &output) == rt::ObservationCode::OK);
            rt::RawJointObservation raw = Sample();
            raw.sequence = 2U;
            raw.sample_time_ns = 810U;
            raw.receive_time_ns = 860U;
            rt::CalibrationSnapshot cal = Calibration();
            if (strcmp(variant, "sequence_replay") == 0)
                raw.sequence = 1U;
            else if (strcmp(variant, "sample_regression") == 0)
                raw.sample_time_ns = 799U;
            else if (strcmp(variant, "receive_regression") == 0)
                raw.receive_time_ns = 849U;
            else if (strcmp(variant,
                            "calibration_generation_regression") == 0)
                cal.generation = 6U;
            actual_code = rt::ObservationCodeName(stream.convert(
                cal, raw, ObservationPolicy(), 900U, &output));
        } else if (strcmp(operation, "reconcile") == 0) {
            rt::ConvertedJointObservation external = Convert(
                rt::ObservationSourceKind::EXTERNAL_ABSOLUTE,
                "left-hip-roll-external", 0.0);
            rt::ConvertedJointObservation native = Convert(
                rt::ObservationSourceKind::NATIVE_OUTPUT,
                "left-hip-roll-native", 0.05);
            const rt::ConvertedJointObservation* external_ptr = &external;
            const rt::ConvertedJointObservation* native_ptr = &native;
            rt::ReconciliationPolicy policy = ReconciliationPolicy();
            if (strcmp(variant, "external_only") == 0) {
                policy = ReconciliationPolicy(
                    rt::ReconciliationMode::EXTERNAL_ONLY);
                native_ptr = NULL;
            } else if (strcmp(variant, "native_only") == 0) {
                policy = ReconciliationPolicy(
                    rt::ReconciliationMode::NATIVE_ONLY);
                external_ptr = NULL;
            } else if (strcmp(variant, "prefer_native") == 0) {
                policy = ReconciliationPolicy(
                    rt::ReconciliationMode::REQUIRE_BOTH_PREFER_NATIVE);
            } else if (strcmp(variant, "external_missing") == 0) {
                external_ptr = NULL;
            } else if (strcmp(variant, "native_missing") == 0) {
                native_ptr = NULL;
            } else if (strcmp(variant, "sensor_alias") == 0) {
                policy.native_sensor_id = policy.external_sensor_id;
            } else if (strcmp(variant, "disagreement") == 0) {
                native.joint_position_rad = 1.0;
            }
            rt::ReconciledJointObservation output = {};
            const rt::ReconciliationCode code =
                rt::ReconcileJointObservations(policy, external_ptr,
                                               native_ptr, &output);
            actual_code = rt::ReconciliationCodeName(code);
            if (code == rt::ReconciliationCode::OK) {
                has_numeric = true;
                actual_numeric = output.joint_position_rad;
            }
        } else if (strcmp(operation, "limit") == 0) {
            rt::PositionLimitSnapshot limit = Limit();
            rt::ReconciledJointObservation observation = {};
            observation.canonical_joint_name = limit.canonical_joint_name;
            observation.actuator_id = limit.actuator_id;
            observation.configuration = Config();
            observation.joint_position_rad = 0.0;
            uint64_t now = 500U;
            if (strcmp(variant, "below") == 0)
                observation.joint_position_rad = -1.01;
            else if (strcmp(variant, "above") == 0)
                observation.joint_position_rad = 1.01;
            else if (strcmp(variant, "not_yet_valid") == 0)
                now = 99U;
            else if (strcmp(variant, "expired") == 0)
                now = 1001U;
            else if (strcmp(variant, "invalid_snapshot") == 0)
                limit.lower_rad = 2.0;
            else if (strcmp(variant, "identity_mismatch") == 0)
                Set(&observation.actuator_id,
                    "actuator-right-hip-roll");
            const rt::PositionLimitCode code =
                rt::CheckPositionLimit(limit, observation, now);
            actual_code = rt::PositionLimitCodeName(code);
            if (code == rt::PositionLimitCode::OK) {
                has_numeric = true;
                actual_numeric = observation.joint_position_rad;
            }
        }
        CHECK(strcmp(actual_code, expected_code) == 0);
        if (strcmp(expected_numeric, "NONE") == 0) {
            CHECK(!has_numeric);
        } else {
            CHECK(has_numeric);
            CHECK(Near(actual_numeric, strtod(expected_numeric, NULL)));
        }
        ++count;
    }
    CHECK(!ferror(file));
    fclose(file);
    CHECK(count == 39U);
}

void TestNamesAndNullOutputs() {
    for (uint8_t raw = 0U;
         raw <= static_cast<uint8_t>(rt::ObservationCode::CONVERSION_NONFINITE);
         ++raw)
        CHECK(strcmp(rt::ObservationCodeName(
                         static_cast<rt::ObservationCode>(raw)),
                     "UNKNOWN_OBSERVATION_CODE") != 0);
    for (uint8_t raw = 0U;
         raw <= static_cast<uint8_t>(rt::ReconciliationCode::DISAGREEMENT_EXCEEDED);
         ++raw)
        CHECK(strcmp(rt::ReconciliationCodeName(
                         static_cast<rt::ReconciliationCode>(raw)),
                     "UNKNOWN_RECONCILIATION_CODE") != 0);
    CHECK(rt::ConvertJointObservation(Calibration(), Sample(),
                                      ObservationPolicy(), 900U, NULL) ==
          rt::ObservationCode::NULL_OUTPUT);
    CHECK(rt::ReconcileJointObservations(ReconciliationPolicy(), NULL, NULL,
                                         NULL) ==
          rt::ReconciliationCode::NULL_OUTPUT);
}

}  // namespace

int main() {
    TestCalibrationAndConversion();
    TestCalibrationValidation();
    TestIdentityUnitsEvidenceAndQuality();
    TestTimeDenialsAndBoundaries();
    TestStreamReplayAndRegression();
    TestReconciliationIsExplicitAndNeverAverages();
    TestMissingHipYawAndDisagreementStayVisible();
    TestPolicyIdentityEvidenceAndAlias();
    TestPositionLimit();
    TestSharedGoldenCorpus();
    TestNamesAndNullOutputs();
    if (failures != 0) return 1;
    printf("JOINT_OBSERVATION_CORE_OK\n");
    return 0;
}
