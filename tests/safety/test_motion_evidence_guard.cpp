#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "motion_evidence_guard.h"

namespace safety = myactuator::safety;

namespace {

int failures = 0;
uint64_t checks = 0;

#define CHECK(condition)                                                       \
    do {                                                                       \
        ++checks;                                                              \
        if (!(condition)) {                                                    \
            ++failures;                                                        \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__,          \
                    #condition);                                               \
        }                                                                      \
    } while (0)

const uint32_t kOwner = 1;
const uint32_t kSession = 0x5AFE7007UL;
const uint64_t kNow = 100;
const uint32_t kAllFields = safety::kKnownFeedbackMask;

const safety::MotionEvidenceBinding kBindings[] = {
    {11, 101},
    {12, 102},
};

safety::Prerequisites Ready() {
    safety::Prerequisites value;
    value.configuration_valid = true;
    value.expected_nodes_present = true;
    value.transport_ready = true;
    value.safety_interlock_ready = true;
    value.external_faults_clear = true;
    value.motor_off_confirmed = true;
    return value;
}

safety::ConfigCandidate Candidate() {
    safety::ConfigCandidate value = {};
    const char* id = "motion-evidence-test";
    value.identity.config_id.length =
        static_cast<uint8_t>(strlen(id));
    memcpy(value.identity.config_id.bytes, id, strlen(id));
    for (size_t index = 0;
         index < safety::kSha256DigestSize;
         ++index) {
        value.identity.digest.bytes[index] =
            static_cast<uint8_t>(index + 1U);
    }
    value.identity.revision = 3;
    value.identity.schema_version = 1;
    value.generation = 9;
    value.validity_deadline_ms = 1000;
    value.structural_validated = true;
    value.semantic_validated = true;
    value.motion_allowed = true;
    value.authorization_class =
        safety::AuthorizationClass::MOTION;
    return value;
}

safety::ConfigExpectation Expectation(
    const safety::ConfigCandidate& candidate) {
    safety::ConfigExpectation value = {};
    value.identity = candidate.identity;
    value.generation = candidate.generation;
    return value;
}

safety::GenerationCommitToken CommitToken() {
    safety::GenerationCommitToken value = {};
    value.generation = 9;
    for (size_t index = 0;
         index < safety::kCommitTokenSize;
         ++index) {
        value.bytes[index] =
            static_cast<uint8_t>(0xA0U + index);
    }
    return value;
}

safety::ConfigReference Reference(
    const safety::ConfigCandidate& candidate) {
    safety::ConfigReference value = {};
    value.identity = candidate.identity;
    value.generation = candidate.generation;
    value.authorization_class =
        safety::AuthorizationClass::MOTION;
    return value;
}

safety::EvidenceConfigBinding EvidenceConfig(
    const safety::ConfigReference& reference) {
    safety::EvidenceConfigBinding value = {};
    value.generation = reference.generation;
    memcpy(value.digest, reference.identity.digest.bytes,
           safety::kSha256DigestSize);
    return value;
}

int64_t LowerFor(uint32_t field) {
    switch (field) {
        case safety::FEEDBACK_POSITION:
            return -1000;
        case safety::FEEDBACK_VELOCITY:
            return -2000;
        case safety::FEEDBACK_Q_AXIS_CURRENT:
            return -10000;
        case safety::FEEDBACK_OUTPUT_EFFORT:
            return -1000000;
        case safety::FEEDBACK_TEMPERATURE:
            return 250000;
        case safety::FEEDBACK_BUS_VOLTAGE:
            return 40000;
        case safety::FEEDBACK_FOLLOWING_ERROR:
            return -1000;
        default:
            return 0;
    }
}

int64_t UpperFor(uint32_t field) {
    switch (field) {
        case safety::FEEDBACK_POSITION:
            return 1000;
        case safety::FEEDBACK_VELOCITY:
            return 2000;
        case safety::FEEDBACK_Q_AXIS_CURRENT:
            return 10000;
        case safety::FEEDBACK_OUTPUT_EFFORT:
            return 1000000;
        case safety::FEEDBACK_TEMPERATURE:
            return 350000;
        case safety::FEEDBACK_BUS_VOLTAGE:
            return 60000;
        case safety::FEEDBACK_FOLLOWING_ERROR:
            return 1000;
        default:
            return 0;
    }
}

int64_t NominalFor(uint32_t field) {
    switch (field) {
        case safety::FEEDBACK_POSITION:
            return 100;
        case safety::FEEDBACK_VELOCITY:
            return 200;
        case safety::FEEDBACK_Q_AXIS_CURRENT:
            return 300;
        case safety::FEEDBACK_OUTPUT_EFFORT:
            return 400;
        case safety::FEEDBACK_TEMPERATURE:
            return 300000;
        case safety::FEEDBACK_BUS_VOLTAGE:
            return 48000;
        case safety::FEEDBACK_FOLLOWING_ERROR:
            return 50;
        default:
            return 0;
    }
}

void SetFeedback(safety::FeedbackFaultContext* feedback,
                 uint32_t field,
                 int64_t value) {
    switch (field) {
        case safety::FEEDBACK_POSITION:
            feedback->position_urad = value;
            return;
        case safety::FEEDBACK_VELOCITY:
            feedback->velocity_urad_s = value;
            return;
        case safety::FEEDBACK_Q_AXIS_CURRENT:
            feedback->q_axis_current_ma = value;
            return;
        case safety::FEEDBACK_OUTPUT_EFFORT:
            feedback->output_effort_unm = value;
            return;
        case safety::FEEDBACK_TEMPERATURE:
            feedback->temperature_mk = value;
            return;
        case safety::FEEDBACK_BUS_VOLTAGE:
            feedback->bus_voltage_mv = value;
            return;
        case safety::FEEDBACK_FOLLOWING_ERROR:
            feedback->following_error_urad = value;
            return;
        default:
            return;
    }
}

safety::TypedLimitSnapshot Limit(
    const safety::MotionEvidenceBinding& binding,
    const safety::ConfigReference& reference,
    uint32_t field,
    uint8_t salt) {
    safety::TypedLimitSnapshot value = {};
    value.joint_token = binding.joint_token;
    value.actuator_token = binding.actuator_token;
    value.field = field;
    value.coordinate =
        safety::ExpectedCoordinateForFeedbackField(field);
    value.config = EvidenceConfig(reference);
    for (size_t index = 0;
         index < safety::kSha256DigestSize;
         ++index) {
        value.provenance_digest[index] =
            static_cast<uint8_t>(salt + index + 1U);
    }
    value.generation = static_cast<uint64_t>(salt) + 1U;
    value.valid_from_ms = 90;
    value.valid_until_ms = 110;
    value.evidence_class =
        safety::MotionEvidenceClass::SYNTHETIC_FIXTURE;
    value.has_lower = true;
    value.has_upper = true;
    value.lower_value = LowerFor(field);
    value.upper_value = UpperFor(field);
    return value;
}

safety::JointMotionEvidence JointEvidence(
    const safety::MotionEvidenceBinding& binding,
    const safety::ConfigReference& reference,
    uint8_t salt) {
    safety::JointMotionEvidence value = {};
    value.joint_token = binding.joint_token;
    value.actuator_token = binding.actuator_token;
    value.config = EvidenceConfig(reference);
    for (size_t index = 0;
         index < safety::kSha256DigestSize;
         ++index) {
        value.calibration_digest[index] =
            static_cast<uint8_t>(0x40U + salt + index);
    }
    value.calibration_generation =
        static_cast<uint64_t>(salt) + 1U;
    value.evidence_class =
        safety::MotionEvidenceClass::SYNTHETIC_FIXTURE;
    value.required_sources_present = true;
    value.fusion_valid = true;
    value.quality_valid = true;
    value.feedback.valid_mask = kAllFields;
    value.feedback.sample_generation =
        static_cast<uint64_t>(salt) + 20U;
    value.feedback.sampled_at_ms = 90;
    value.feedback.received_at_ms = 95;
    value.feedback.position_urad =
        NominalFor(safety::FEEDBACK_POSITION);
    value.feedback.velocity_urad_s =
        NominalFor(safety::FEEDBACK_VELOCITY);
    value.feedback.q_axis_current_ma =
        NominalFor(safety::FEEDBACK_Q_AXIS_CURRENT);
    value.feedback.output_effort_unm =
        NominalFor(safety::FEEDBACK_OUTPUT_EFFORT);
    value.feedback.temperature_mk =
        NominalFor(safety::FEEDBACK_TEMPERATURE);
    value.feedback.bus_voltage_mv =
        NominalFor(safety::FEEDBACK_BUS_VOLTAGE);
    value.feedback.following_error_urad =
        NominalFor(safety::FEEDBACK_FOLLOWING_ERROR);
    value.limit_count = 7;
    for (uint8_t index = 0; index < value.limit_count; ++index) {
        value.limits[index] =
            Limit(binding, reference, 1UL << index,
                  static_cast<uint8_t>(salt + index));
    }
    return value;
}

safety::MotionEvidenceBank EvidenceBank(
    const safety::ConfigReference& reference,
    const safety::MotionEvidenceBinding* bindings = kBindings,
    size_t count = 2) {
    safety::MotionEvidenceBank value = {};
    value.joint_count = static_cast<uint8_t>(count);
    for (size_t index = 0; index < count; ++index) {
        value.joints[index] =
            JointEvidence(bindings[index], reference,
                          static_cast<uint8_t>(index + 1U));
    }
    return value;
}

safety::MotionSetpoint PositionSetpoint(
    const safety::ConfigReference& reference) {
    safety::MotionSetpoint value = {};
    value.joint_token = kBindings[0].joint_token;
    value.actuator_token = kBindings[0].actuator_token;
    value.field = safety::FEEDBACK_POSITION;
    value.coordinate =
        safety::EvidenceCoordinate::CANONICAL_JOINT;
    value.config = EvidenceConfig(reference);
    value.value = 100;
    return value;
}

struct Harness {
    safety::Configuration supervisor_configuration;
    safety::SafetySupervisor supervisor;
    safety::ConfigCandidate candidate;
    safety::SchemaCompatibilityPolicy schema_policy;
    safety::ConfigIdentityGuard config_guard;
    safety::MotionEvidencePolicy evidence_policy;
    safety::MotionEvidenceGuard admission;
    const safety::MotionEvidenceBinding* bindings;
    size_t binding_count;

    Harness(const safety::MotionEvidenceBinding* required = kBindings,
            size_t count = 2)
        : supervisor_configuration(
              kSession, 1, 1000, 100,
              1UL << (kOwner - 1),
              1UL << (kOwner - 1)),
          supervisor(supervisor_configuration),
          candidate(Candidate()),
          schema_policy{1, 1},
          config_guard(schema_policy),
          evidence_policy(
              required, count, kAllFields, 10, 5,
              safety::MotionEvidenceClass::SYNTHETIC_FIXTURE),
          admission(&supervisor, &config_guard, evidence_policy),
          bindings(required),
          binding_count(count) {
        const safety::GenerationCommitToken token = CommitToken();
        CHECK(config_guard.stageCandidate(
                  0, candidate, Expectation(candidate), token) ==
              safety::ConfigDecision::ALLOWED);
        CHECK(config_guard.commitStaged(0, token) ==
              safety::ConfigDecision::ALLOWED);
        CHECK(supervisor.completeBoot(0, Ready()) ==
              safety::Result::OK);
        CHECK(supervisor.acquireLease(
                  0,
                  safety::MessageStamp(kOwner, kSession, 1),
                  1000) == safety::Result::OK);
        CHECK(admission.valid());
    }

    safety::ConfigReference reference() const {
        return Reference(candidate);
    }

    safety::MotionEvidenceBank goodBank() const {
        return EvidenceBank(reference(), bindings, binding_count);
    }

    safety::MotionAdmissionResult enableGood() {
        const safety::MotionEvidenceBank bank = goodBank();
        return admission.enable(
            kNow,
            safety::MessageStamp(kOwner, kSession, 2),
            reference(), &bank);
    }

    safety::CommandAdmissionProof proof(
        uint64_t generation) const {
        safety::CommandAdmissionProof value = {};
        value.config = reference();
        value.command_generation = generation;
        return value;
    }
};

void CheckDecision(const safety::MotionAdmissionResult& result,
                   safety::MotionEvidenceDecision expected,
                   uint16_t joint = 0,
                   uint32_t field = 0) {
    CHECK(result.decision == expected);
    CHECK(strcmp(safety::MotionEvidenceDecisionName(result.decision),
                 "UNKNOWN_MOTION_EVIDENCE_DECISION") != 0);
    if (joint != 0U) {
        CHECK(result.joint_token == joint);
    }
    if (field != 0U) {
        CHECK(result.field == field);
    }
}

void CheckArmEvidenceDenial(
    const safety::MotionEvidenceBank* bad_bank,
    safety::MotionEvidenceDecision expected,
    uint16_t joint = 0,
    uint32_t field = 0) {
    Harness harness;
    const safety::MotionAdmissionResult denied =
        harness.admission.enable(
            kNow,
            safety::MessageStamp(kOwner, kSession, 2),
            harness.reference(), bad_bank);
    CheckDecision(denied, expected, joint, field);
    CHECK(!denied.config_checked);
    CHECK(!denied.supervisor_checked);
    CHECK(!denied.allowed());
    CHECK(harness.supervisor.state() == safety::State::ARMED);
    CHECK(harness.config_guard.snapshot().last_command_generation == 0U);

    const safety::MotionEvidenceBank good = harness.goodBank();
    const safety::MotionAdmissionResult corrected =
        harness.admission.enable(
            kNow,
            safety::MessageStamp(kOwner, kSession, 2),
            harness.reference(), &good);
    CHECK(corrected.allowed());
    CHECK(harness.supervisor.state() == safety::State::ENABLED);
}

void CheckCommandEvidenceDenial(
    const safety::MotionEvidenceBank* bad_bank,
    const safety::MotionSetpoint* bad_setpoint,
    safety::MotionEvidenceDecision expected,
    uint16_t joint = 0,
    uint32_t field = 0) {
    Harness harness;
    CHECK(harness.enableGood().allowed());
    const safety::CommandAdmissionProof proof = harness.proof(1);
    const safety::MotionAdmissionResult denied =
        harness.admission.authorizeCommand(
            kNow,
            safety::MessageStamp(kOwner, kSession, 3),
            proof, bad_bank, bad_setpoint);
    CheckDecision(denied, expected, joint, field);
    CHECK(!denied.config_checked);
    CHECK(!denied.supervisor_checked);
    CHECK(!denied.allowed());
    CHECK(harness.supervisor.state() == safety::State::ENABLED);
    CHECK(harness.config_guard.snapshot().last_command_generation == 0U);

    const safety::MotionEvidenceBank good = harness.goodBank();
    const safety::MotionSetpoint setpoint =
        PositionSetpoint(harness.reference());
    const safety::MotionAdmissionResult corrected =
        harness.admission.authorizeCommand(
            kNow,
            safety::MessageStamp(kOwner, kSession, 3),
            proof, &good, &setpoint);
    CHECK(corrected.allowed());
    CHECK(harness.config_guard.snapshot().last_command_generation == 1U);
}

void TestGoodArmCommandAndInclusiveBoundaries() {
    Harness harness;
    safety::MotionEvidenceBank bank = harness.goodBank();
    for (uint8_t index = 0; index < 7U; ++index) {
        const uint32_t field = 1UL << index;
        SetFeedback(&bank.joints[0].feedback, field,
                    LowerFor(field));
    }
    bank.joints[0].limits[0].valid_until_ms = kNow;
    const safety::MotionAdmissionResult armed =
        harness.admission.enable(
            kNow,
            safety::MessageStamp(kOwner, kSession, 2),
            harness.reference(), &bank);
    CHECK(armed.allowed());
    CHECK(armed.config_checked);
    CHECK(armed.supervisor_checked);
    CHECK(harness.supervisor.outputsPermitted());

    safety::MotionSetpoint setpoint =
        PositionSetpoint(harness.reference());
    setpoint.value =
        bank.joints[0].limits[0].upper_value;
    const safety::MotionAdmissionResult commanded =
        harness.admission.authorizeCommand(
            kNow,
            safety::MessageStamp(kOwner, kSession, 3),
            harness.proof(1), &bank, &setpoint);
    CHECK(commanded.allowed());
    CHECK(commanded.joint_token == kBindings[0].joint_token);
    CHECK(commanded.field == safety::FEEDBACK_POSITION);

    CHECK(sizeof(safety::MotionEvidenceBank) <= 16384U);
}

void TestEveryFeedbackAndLimitBoundary() {
    for (uint8_t index = 0; index < 7U; ++index) {
        const uint32_t field = 1UL << index;
        {
            Harness harness;
            safety::MotionEvidenceBank bank = harness.goodBank();
            SetFeedback(&bank.joints[0].feedback, field,
                        LowerFor(field));
            CHECK(harness.admission.enable(
                      kNow,
                      safety::MessageStamp(kOwner, kSession, 2),
                      harness.reference(), &bank).allowed());
        }
        {
            Harness harness;
            safety::MotionEvidenceBank bank = harness.goodBank();
            SetFeedback(&bank.joints[0].feedback, field,
                        UpperFor(field));
            CHECK(harness.admission.enable(
                      kNow,
                      safety::MessageStamp(kOwner, kSession, 2),
                      harness.reference(), &bank).allowed());
        }
        {
            Harness harness;
            safety::MotionEvidenceBank bank = harness.goodBank();
            SetFeedback(&bank.joints[0].feedback, field,
                        LowerFor(field) - 1);
            const safety::MotionAdmissionResult result =
                harness.admission.enable(
                    kNow,
                    safety::MessageStamp(kOwner, kSession, 2),
                    harness.reference(), &bank);
            CheckDecision(
                result,
                safety::MotionEvidenceDecision::FEEDBACK_BELOW_LIMIT,
                kBindings[0].joint_token, field);
            CHECK(!result.config_checked);
        }
        {
            Harness harness;
            safety::MotionEvidenceBank bank = harness.goodBank();
            SetFeedback(&bank.joints[0].feedback, field,
                        UpperFor(field) + 1);
            const safety::MotionAdmissionResult result =
                harness.admission.enable(
                    kNow,
                    safety::MessageStamp(kOwner, kSession, 2),
                    harness.reference(), &bank);
            CheckDecision(
                result,
                safety::MotionEvidenceDecision::FEEDBACK_ABOVE_LIMIT,
                kBindings[0].joint_token, field);
            CHECK(!result.config_checked);
        }
    }
}

void TestArmEvidenceDenials() {
    CheckArmEvidenceDenial(
        NULL,
        safety::MotionEvidenceDecision::EVIDENCE_BANK_MISSING);

    safety::MotionEvidenceBank bank =
        EvidenceBank(Reference(Candidate()));
    bank.joint_count = 1;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::JOINT_COUNT_MISMATCH);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].joint_token = 99;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::JOINT_BINDING_MISMATCH,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].config.generation += 1;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::CONFIG_BINDING_MISMATCH,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    memset(bank.joints[0].calibration_digest, 0,
           safety::kSha256DigestSize);
    CheckArmEvidenceDenial(
        &bank,
        safety::MotionEvidenceDecision::CALIBRATION_PROVENANCE_INVALID,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].calibration_generation = 0;
    CheckArmEvidenceDenial(
        &bank,
        safety::MotionEvidenceDecision::CALIBRATION_GENERATION_INVALID,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].evidence_class =
        safety::MotionEvidenceClass::PHYSICAL_REVIEWED;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::EVIDENCE_CLASS_MISMATCH,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].required_sources_present = false;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::REQUIRED_SOURCE_MISSING,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].fusion_valid = false;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::FUSION_INVALID,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].source_fault = true;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::SOURCE_FAULT,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].quality_valid = false;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::SOURCE_QUALITY_INVALID,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].feedback.sample_generation = 0;
    CheckArmEvidenceDenial(
        &bank,
        safety::MotionEvidenceDecision::FEEDBACK_GENERATION_INVALID,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].feedback.valid_mask &=
        ~safety::FEEDBACK_TEMPERATURE;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::FEEDBACK_MASK_INVALID,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].feedback.valid_mask |= 1UL << 12;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::FEEDBACK_MASK_INVALID,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].feedback.sampled_at_ms = kNow + 1;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::SAMPLE_TIME_FUTURE,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].feedback.received_at_ms = kNow + 1;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::RECEIVE_TIME_FUTURE,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].feedback.sampled_at_ms = 96;
    bank.joints[0].feedback.received_at_ms = 95;
    CheckArmEvidenceDenial(
        &bank,
        safety::MotionEvidenceDecision::FEEDBACK_TIME_ORDER_INVALID,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].feedback.sampled_at_ms = 89;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::SAMPLE_STALE,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].feedback.received_at_ms = 94;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::RECEIVE_STALE,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].limit_count = 6;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::LIMIT_COUNT_MISMATCH,
        kBindings[0].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].limits[0].field =
        safety::FEEDBACK_VELOCITY;
    CheckArmEvidenceDenial(
        &bank,
        safety::MotionEvidenceDecision::LIMIT_FIELD_ORDER_INVALID,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].limits[0].actuator_token = 999;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::LIMIT_BINDING_MISMATCH,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].limits[0].config.digest[0] ^= 0x80U;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::LIMIT_CONFIG_MISMATCH,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    bank = EvidenceBank(Reference(Candidate()));
    memset(bank.joints[0].limits[0].provenance_digest, 0,
           safety::kSha256DigestSize);
    CheckArmEvidenceDenial(
        &bank,
        safety::MotionEvidenceDecision::LIMIT_PROVENANCE_INVALID,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].limits[0].generation = 0;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::LIMIT_GENERATION_INVALID,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].limits[0].valid_from_ms = 110;
    bank.joints[0].limits[0].valid_until_ms = 110;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::LIMIT_INTERVAL_INVALID,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].limits[0].valid_from_ms = 101;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::LIMIT_NOT_YET_VALID,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].limits[0].valid_until_ms = 99;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::LIMIT_EXPIRED,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].limits[0].has_lower = false;
    bank.joints[0].limits[0].has_upper = false;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::LIMIT_BOUNDS_MISSING,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].limits[0].lower_value = 2;
    bank.joints[0].limits[0].upper_value = 1;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::LIMIT_BOUNDS_REVERSED,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].limits[0].coordinate =
        safety::EvidenceCoordinate::MOTOR_SHAFT;
    CheckArmEvidenceDenial(
        &bank,
        safety::MotionEvidenceDecision::LIMIT_COORDINATE_MISMATCH,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[0].limits[0].evidence_class =
        safety::MotionEvidenceClass::PHYSICAL_REVIEWED;
    CheckArmEvidenceDenial(
        &bank, safety::MotionEvidenceDecision::EVIDENCE_CLASS_MISMATCH,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);
}

void TestCommandEvidenceAndSetpointDenials() {
    safety::MotionEvidenceBank bank =
        EvidenceBank(Reference(Candidate()));
    safety::MotionSetpoint setpoint =
        PositionSetpoint(Reference(Candidate()));

    bank.joints[1].feedback.sampled_at_ms = 89;
    CheckCommandEvidenceDenial(
        &bank, &setpoint,
        safety::MotionEvidenceDecision::SAMPLE_STALE,
        kBindings[1].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    bank.joints[1].limit_count = 0;
    CheckCommandEvidenceDenial(
        &bank, &setpoint,
        safety::MotionEvidenceDecision::LIMIT_COUNT_MISMATCH,
        kBindings[1].joint_token);

    bank = EvidenceBank(Reference(Candidate()));
    CheckCommandEvidenceDenial(
        &bank, NULL,
        safety::MotionEvidenceDecision::SETPOINT_MISSING);

    setpoint = PositionSetpoint(Reference(Candidate()));
    setpoint.field = safety::FEEDBACK_TEMPERATURE;
    setpoint.coordinate = safety::EvidenceCoordinate::DRIVE_CASE;
    CheckCommandEvidenceDenial(
        &bank, &setpoint,
        safety::MotionEvidenceDecision::SETPOINT_FIELD_INVALID,
        kBindings[0].joint_token, safety::FEEDBACK_TEMPERATURE);

    setpoint = PositionSetpoint(Reference(Candidate()));
    setpoint.field =
        safety::FEEDBACK_POSITION | safety::FEEDBACK_VELOCITY;
    CheckCommandEvidenceDenial(
        &bank, &setpoint,
        safety::MotionEvidenceDecision::SETPOINT_FIELD_INVALID,
        kBindings[0].joint_token, setpoint.field);

    setpoint = PositionSetpoint(Reference(Candidate()));
    setpoint.actuator_token = 999;
    CheckCommandEvidenceDenial(
        &bank, &setpoint,
        safety::MotionEvidenceDecision::SETPOINT_BINDING_MISMATCH,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    setpoint = PositionSetpoint(Reference(Candidate()));
    setpoint.config.generation += 1;
    CheckCommandEvidenceDenial(
        &bank, &setpoint,
        safety::MotionEvidenceDecision::SETPOINT_CONFIG_MISMATCH,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    setpoint = PositionSetpoint(Reference(Candidate()));
    setpoint.coordinate = safety::EvidenceCoordinate::MOTOR_SHAFT;
    CheckCommandEvidenceDenial(
        &bank, &setpoint,
        safety::MotionEvidenceDecision::SETPOINT_COORDINATE_MISMATCH,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    setpoint = PositionSetpoint(Reference(Candidate()));
    setpoint.coordinate = safety::EvidenceCoordinate::SENSOR_RAW;
    CheckCommandEvidenceDenial(
        &bank, &setpoint,
        safety::MotionEvidenceDecision::SETPOINT_COORDINATE_MISMATCH,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    setpoint = PositionSetpoint(Reference(Candidate()));
    setpoint.value = LowerFor(safety::FEEDBACK_POSITION) - 1;
    CheckCommandEvidenceDenial(
        &bank, &setpoint,
        safety::MotionEvidenceDecision::SETPOINT_BELOW_LIMIT,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);

    setpoint = PositionSetpoint(Reference(Candidate()));
    setpoint.value = UpperFor(safety::FEEDBACK_POSITION) + 1;
    CheckCommandEvidenceDenial(
        &bank, &setpoint,
        safety::MotionEvidenceDecision::SETPOINT_ABOVE_LIMIT,
        kBindings[0].joint_token, safety::FEEDBACK_POSITION);
}

void TestConfigSupervisorAndClockPropagation() {
    {
        Harness harness;
        safety::ConfigReference bad = harness.reference();
        bad.identity.digest.bytes[0] ^= 0x80U;
        const safety::MotionEvidenceBank bank =
            EvidenceBank(bad);
        const safety::MotionAdmissionResult denied =
            harness.admission.enable(
                kNow,
                safety::MessageStamp(kOwner, kSession, 2),
                bad, &bank);
        CheckDecision(
            denied, safety::MotionEvidenceDecision::CONFIG_DENIED);
        CHECK(denied.config_checked);
        CHECK(denied.config_decision ==
              safety::ConfigDecision::DIGEST_MISMATCH);
        CHECK(!denied.supervisor_checked);
        CHECK(harness.supervisor.state() == safety::State::ARMED);
        CHECK(harness.enableGood().allowed());
    }
    {
        Harness harness;
        CHECK(harness.enableGood().allowed());
        safety::ConfigReference bad = harness.reference();
        bad.identity.digest.bytes[0] ^= 0x40U;
        const safety::MotionEvidenceBank bank = EvidenceBank(bad);
        safety::MotionSetpoint setpoint = PositionSetpoint(bad);
        safety::CommandAdmissionProof proof = {};
        proof.config = bad;
        proof.command_generation = 1;
        const safety::MotionAdmissionResult denied =
            harness.admission.authorizeCommand(
                kNow,
                safety::MessageStamp(kOwner, kSession, 3),
                proof, &bank, &setpoint);
        CheckDecision(
            denied, safety::MotionEvidenceDecision::CONFIG_DENIED);
        CHECK(denied.config_decision ==
              safety::ConfigDecision::DIGEST_MISMATCH);
        CHECK(!denied.supervisor_checked);
        CHECK(harness.config_guard.snapshot().last_command_generation ==
              0U);

        const safety::MotionEvidenceBank good = harness.goodBank();
        setpoint = PositionSetpoint(harness.reference());
        CHECK(harness.admission.authorizeCommand(
                  kNow,
                  safety::MessageStamp(kOwner, kSession, 3),
                  harness.proof(1), &good, &setpoint).allowed());
    }
    {
        Harness harness;
        CHECK(harness.enableGood().allowed());
        const safety::MotionEvidenceBank bank = harness.goodBank();
        const safety::MotionSetpoint setpoint =
            PositionSetpoint(harness.reference());
        const safety::MotionAdmissionResult denied =
            harness.admission.authorizeCommand(
                kNow,
                safety::MessageStamp(2, kSession, 1),
                harness.proof(1), &bank, &setpoint);
        CheckDecision(
            denied, safety::MotionEvidenceDecision::SUPERVISOR_DENIED);
        CHECK(denied.config_checked);
        CHECK(denied.supervisor_checked);
        CHECK(denied.supervisor_result ==
              safety::Result::INVALID_OWNER);
        CHECK(harness.config_guard.snapshot().last_command_generation ==
              1U);
    }
    {
        Harness harness;
        safety::MotionEvidenceBank bank = harness.goodBank();
        bank.joints[0].quality_valid = false;
        CheckDecision(
            harness.admission.enable(
                kNow,
                safety::MessageStamp(kOwner, kSession, 2),
                harness.reference(), &bank),
            safety::MotionEvidenceDecision::SOURCE_QUALITY_INVALID);
        const safety::MotionAdmissionResult regression =
            harness.admission.enable(
                kNow - 1,
                safety::MessageStamp(kOwner, kSession, 2),
                harness.reference(), &bank);
        CheckDecision(
            regression,
            safety::MotionEvidenceDecision::CLOCK_REGRESSION);
        CHECK(!regression.config_checked);
        CHECK(harness.supervisor.state() == safety::State::ARMED);
    }
    {
        Harness harness;
        safety::ConfigReference bad = harness.reference();
        bad.identity.config_id.bytes[
            bad.identity.config_id.length] = 'x';
        const safety::MotionEvidenceBank bank = EvidenceBank(bad);
        CheckDecision(
            harness.admission.enable(
                kNow,
                safety::MessageStamp(kOwner, kSession, 2),
                bad, &bank),
            safety::MotionEvidenceDecision::CONFIG_REFERENCE_INVALID);
    }
}

void TestPolicyBindingAndTwelveJointCoverage() {
    const safety::MotionEvidencePolicy good_policy(
        kBindings, 2, kAllFields, 10, 5,
        safety::MotionEvidenceClass::SYNTHETIC_FIXTURE);
    safety::Configuration configuration(
        kSession, 1, 1000, 100, 1, 1);
    safety::SafetySupervisor supervisor(configuration);
    safety::SchemaCompatibilityPolicy schema = {1, 1};
    safety::ConfigIdentityGuard config_guard(schema);

    safety::MotionEvidenceGuard null_supervisor(
        NULL, &config_guard, good_policy);
    safety::MotionEvidenceGuard null_config(
        &supervisor, NULL, good_policy);
    CHECK(!null_supervisor.valid());
    CHECK(!null_config.valid());

    safety::MotionEvidenceBinding duplicate[] = {
        {1, 10},
        {1, 11},
    };
    const safety::MotionEvidencePolicy duplicate_policy(
        duplicate, 2, kAllFields, 10, 5,
        safety::MotionEvidenceClass::SYNTHETIC_FIXTURE);
    safety::MotionEvidenceGuard duplicate_guard(
        &supervisor, &config_guard, duplicate_policy);
    CHECK(!duplicate_guard.valid());

    const safety::MotionEvidencePolicy missing_common(
        kBindings, 2, kAllFields & ~safety::FEEDBACK_POSITION,
        10, 5, safety::MotionEvidenceClass::SYNTHETIC_FIXTURE);
    safety::MotionEvidenceGuard missing_common_guard(
        &supervisor, &config_guard, missing_common);
    CHECK(!missing_common_guard.valid());

    const safety::MotionEvidencePolicy missing_effort(
        kBindings, 2,
        kAllFields & ~safety::FEEDBACK_Q_AXIS_CURRENT &
            ~safety::FEEDBACK_OUTPUT_EFFORT,
        10, 5, safety::MotionEvidenceClass::SYNTHETIC_FIXTURE);
    safety::MotionEvidenceGuard missing_effort_guard(
        &supervisor, &config_guard, missing_effort);
    CHECK(!missing_effort_guard.valid());

    const safety::MotionEvidencePolicy bad_ages(
        kBindings, 2, kAllFields, 4, 5,
        safety::MotionEvidenceClass::SYNTHETIC_FIXTURE);
    safety::MotionEvidenceGuard bad_age_guard(
        &supervisor, &config_guard, bad_ages);
    CHECK(!bad_age_guard.valid());

    safety::MotionEvidenceBinding twelve[12] = {};
    for (uint8_t index = 0; index < 12U; ++index) {
        twelve[index].joint_token =
            static_cast<uint16_t>(index + 1U);
        twelve[index].actuator_token =
            static_cast<uint16_t>(index + 101U);
    }
    Harness twelve_harness(twelve, 12);
    const safety::MotionEvidenceBank twelve_bank =
        twelve_harness.goodBank();
    CHECK(twelve_bank.joint_count == 12U);
    CHECK(twelve_harness.admission.enable(
              kNow,
              safety::MessageStamp(kOwner, kSession, 2),
              twelve_harness.reference(), &twelve_bank).allowed());
}

void TestDecisionAndCoordinateContracts() {
    for (uint8_t value = 0; value <= 44U; ++value) {
        CHECK(strcmp(
                  safety::MotionEvidenceDecisionName(
                      static_cast<safety::MotionEvidenceDecision>(value)),
                  "UNKNOWN_MOTION_EVIDENCE_DECISION") != 0);
    }
    CHECK(safety::ExpectedCoordinateForFeedbackField(
              safety::FEEDBACK_POSITION) ==
          safety::EvidenceCoordinate::CANONICAL_JOINT);
    CHECK(safety::ExpectedCoordinateForFeedbackField(
              safety::FEEDBACK_VELOCITY) ==
          safety::EvidenceCoordinate::CANONICAL_JOINT);
    CHECK(safety::ExpectedCoordinateForFeedbackField(
              safety::FEEDBACK_Q_AXIS_CURRENT) ==
          safety::EvidenceCoordinate::Q_AXIS_ELECTRICAL);
    CHECK(safety::ExpectedCoordinateForFeedbackField(
              safety::FEEDBACK_OUTPUT_EFFORT) ==
          safety::EvidenceCoordinate::ACTUATOR_OUTPUT);
    CHECK(safety::ExpectedCoordinateForFeedbackField(
              safety::FEEDBACK_TEMPERATURE) ==
          safety::EvidenceCoordinate::DRIVE_CASE);
    CHECK(safety::ExpectedCoordinateForFeedbackField(
              safety::FEEDBACK_BUS_VOLTAGE) ==
          safety::EvidenceCoordinate::DC_BUS);
    CHECK(safety::ExpectedCoordinateForFeedbackField(
              safety::FEEDBACK_FOLLOWING_ERROR) ==
          safety::EvidenceCoordinate::CANONICAL_JOINT);
    CHECK(safety::ExpectedCoordinateForFeedbackField(0) ==
          safety::EvidenceCoordinate::UNKNOWN);
}

}  // namespace

int main() {
    TestGoodArmCommandAndInclusiveBoundaries();
    TestEveryFeedbackAndLimitBoundary();
    TestArmEvidenceDenials();
    TestCommandEvidenceAndSetpointDenials();
    TestConfigSupervisorAndClockPropagation();
    TestPolicyBindingAndTwelveJointCoverage();
    TestDecisionAndCoordinateContracts();

    if (failures != 0) {
        fprintf(stderr,
                "motion evidence guard: %d failures across %llu checks\n",
                failures,
                static_cast<unsigned long long>(checks));
        return 1;
    }
    printf("motion evidence guard: %llu checks passed\n",
           static_cast<unsigned long long>(checks));
    return 0;
}
