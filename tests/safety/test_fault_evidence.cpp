#include "fault_evidence.h"

#include <stdint.h>

#include <iostream>

namespace safety = myactuator::safety;

namespace {

int failures = 0;
int checks = 0;

#define CHECK(condition)                                                        \
    do {                                                                        \
        ++checks;                                                               \
        if (!(condition)) {                                                     \
            ++failures;                                                         \
            std::cerr << __FILE__ << ':' << __LINE__                            \
                      << ": check failed: " #condition << '\n';                \
        }                                                                       \
    } while (false)

const uint32_t kSession = 0xA55A1234UL;
const uint32_t kOwnerOne = 1;
const uint32_t kOwnerTwo = 2;

safety::Configuration Configuration() {
    return safety::Configuration(kSession, 10, 1000, 20, 0x3, 0x1);
}

safety::Prerequisites Ready() {
    safety::Prerequisites prerequisites;
    prerequisites.configuration_valid = true;
    prerequisites.expected_nodes_present = true;
    prerequisites.transport_ready = true;
    prerequisites.safety_interlock_ready = true;
    prerequisites.external_faults_clear = true;
    prerequisites.motor_off_confirmed = true;
    return prerequisites;
}

safety::PersistentFaultSnapshot InitialSnapshot() {
    safety::PersistentFaultSnapshot snapshot = {};
    CHECK(safety::FaultEvidenceCore::createInitialCleanSnapshot(&snapshot) ==
          safety::FaultEvidenceResult::OK);
    return snapshot;
}

void Enable(safety::SafetySupervisor* supervisor, uint64_t now_ms = 0) {
    CHECK(supervisor->completeBoot(now_ms, Ready()) == safety::Result::OK);
    CHECK(supervisor->acquireLease(
              now_ms, safety::MessageStamp(kOwnerOne, kSession, 1), 1000) ==
          safety::Result::OK);
    CHECK(supervisor->enable(
              now_ms, safety::MessageStamp(kOwnerOne, kSession, 2)) ==
          safety::Result::OK);
    CHECK(supervisor->outputsPermitted());
}

safety::FaultEvent FullBusOffEvent(uint64_t now_ms,
                                   safety::State state_before) {
    safety::FaultEvent event = {};
    event.boot_id = 0xFFFFFFFFUL;  // The core replaces caller input.
    event.reason = safety::FailureReason::BUS_OFF;
    event.monotonic_ms = now_ms;
    event.state_before = state_before;

    event.command.present = true;
    event.command.owner_id = kOwnerOne;
    event.command.session_id = kSession;
    event.command.sequence = 3;
    event.command.deadline_ms = now_ms + 100;
    event.command.config_generation = 7;
    for (size_t index = 0; index < safety::kFaultConfigDigestSize; ++index) {
        event.command.config_digest[index] =
            static_cast<uint8_t>(index + 1U);
    }
    event.command.route_token = 17;
    event.command.bus_id = 1;
    event.command.node_id = 2;
    event.command.opcode = 0xA1;
    event.command.requested_value_native = 250;
    event.command.admitted_value_native = 200;

    event.feedback.valid_mask =
        safety::FEEDBACK_POSITION | safety::FEEDBACK_VELOCITY |
        safety::FEEDBACK_Q_AXIS_CURRENT | safety::FEEDBACK_OUTPUT_EFFORT |
        safety::FEEDBACK_TEMPERATURE | safety::FEEDBACK_BUS_VOLTAGE |
        safety::FEEDBACK_FOLLOWING_ERROR;
    event.feedback.sample_generation = 19;
    event.feedback.sampled_at_ms = now_ms - 2;
    event.feedback.received_at_ms = now_ms - 1;
    event.feedback.position_urad = 123456;
    event.feedback.velocity_urad_s = -6543;
    event.feedback.q_axis_current_ma = 2000;
    event.feedback.output_effort_unm = 112233;
    event.feedback.temperature_mk = 315150;
    event.feedback.bus_voltage_mv = 48000;
    event.feedback.following_error_urad = 345;

    event.bus.bus_off = true;
    event.bus.transmitted_frames = 100;
    event.bus.received_frames = 98;
    event.bus.transmit_errors = 2;
    event.bus.receive_errors = 3;
    event.bus.response_timeouts = 4;
    event.bus.recovery_attempts = 1;
    event.bus.last_receive_ms = now_ms - 1;
    return event;
}

safety::FaultResetEvidence ResetEvidence(uint64_t generation) {
    safety::FaultResetEvidence evidence = {};
    evidence.fault_generation = generation;
    evidence.fault_record_durable = true;
    evidence.root_cause_absent = true;
    evidence.motor_off_observed = true;
    evidence.reset_event_durable = true;
    return evidence;
}

bool HasFault(const safety::SafetySupervisor& supervisor,
              safety::Fault fault) {
    return (supervisor.faultMask() & static_cast<uint32_t>(fault)) != 0;
}

void TestCleanProvisioningAndRecoveryStayBootDisabled() {
    safety::SafetySupervisor supervisor(Configuration());
    safety::FaultEvidenceCore evidence(&supervisor, 10);
    const safety::PersistentFaultSnapshot initial = InitialSnapshot();

    CHECK(!evidence.recoveryComplete());
    CHECK(evidence.recoverRequired(0, &initial) ==
          safety::FaultEvidenceResult::OK);
    CHECK(evidence.recoveryComplete());
    CHECK(!evidence.latched());
    CHECK(evidence.generation() == 0);
    CHECK(supervisor.state() == safety::State::BOOT);
    CHECK(!supervisor.outputsPermitted());
    CHECK(evidence.recoverRequired(0, &initial) ==
          safety::FaultEvidenceResult::RECOVERY_ALREADY_COMPLETED);

    safety::PersistentFaultSnapshot round_trip = {};
    CHECK(evidence.snapshot(&round_trip) == safety::FaultEvidenceResult::OK);
    CHECK(round_trip.magic == safety::kFaultSnapshotMagic);
    CHECK(round_trip.last_generation == 0);
    CHECK(!round_trip.record.latched);
    CHECK(round_trip.checksum_crc32c == initial.checksum_crc32c);
}

void TestMissingAndCorruptRecoveryFailClosed() {
    {
        safety::SafetySupervisor supervisor(Configuration());
        safety::FaultEvidenceCore evidence(&supervisor, 11);
        CHECK(evidence.recoverRequired(5, NULL) ==
              safety::FaultEvidenceResult::SNAPSHOT_MISSING);
        CHECK(evidence.recoveryComplete());
        CHECK(evidence.latched());
        CHECK(supervisor.state() == safety::State::FAULT);
        CHECK(supervisor.shutdownIntent());
        CHECK(!supervisor.outputsPermitted());
        CHECK(HasFault(supervisor, safety::Fault::FAULT_EVIDENCE_INVALID));
        CHECK(evidence.record().events[0].reason ==
              safety::FailureReason::FAULT_EVIDENCE_INVALID);
    }

    {
        safety::PersistentFaultSnapshot corrupt = InitialSnapshot();
        corrupt.magic ^= 1U;
        safety::SafetySupervisor supervisor(Configuration());
        safety::FaultEvidenceCore evidence(&supervisor, 12);
        CHECK(evidence.recoverRequired(6, &corrupt) ==
              safety::FaultEvidenceResult::SNAPSHOT_CORRUPT);
        CHECK(evidence.latched());
        CHECK(supervisor.state() == safety::State::FAULT);
    }

    {
        safety::PersistentFaultSnapshot corrupt = InitialSnapshot();
        corrupt.checksum_crc32c ^= 1U;
        safety::SafetySupervisor supervisor(Configuration());
        safety::FaultEvidenceCore evidence(&supervisor, 13);
        CHECK(evidence.recoverRequired(7, &corrupt) ==
              safety::FaultEvidenceResult::SNAPSHOT_CORRUPT);
        CHECK(evidence.latched());
        CHECK(supervisor.state() == safety::State::FAULT);
    }
}

void TestFullContextLatchesAndPreemptsOutputs() {
    safety::SafetySupervisor supervisor(Configuration());
    safety::FaultEvidenceCore evidence(&supervisor, 21);
    safety::PersistentFaultSnapshot initial = InitialSnapshot();
    CHECK(evidence.recoverRequired(0, &initial) ==
          safety::FaultEvidenceResult::OK);
    Enable(&supervisor);

    const safety::FaultEvent event =
        FullBusOffEvent(10, safety::State::ENABLED);
    CHECK(evidence.latch(event) == safety::FaultEvidenceResult::OK);
    CHECK(evidence.latched());
    CHECK(evidence.generation() == 1);
    CHECK(supervisor.state() == safety::State::FAULT);
    CHECK(supervisor.shutdownIntent());
    CHECK(!supervisor.outputsPermitted());
    CHECK(!supervisor.lease().active);
    CHECK(HasFault(supervisor, safety::Fault::BUS_OFF));

    const safety::FaultRecord& record = evidence.record();
    CHECK(record.stored_event_count == 1);
    CHECK(record.total_event_count == 1);
    CHECK(record.overflow_event_count == 0);
    CHECK(record.events[0].boot_id == 21);
    CHECK(record.events[0].reason == safety::FailureReason::BUS_OFF);
    CHECK(record.events[0].monotonic_ms == 10);
    CHECK(record.events[0].state_before == safety::State::ENABLED);
    CHECK(record.events[0].command.present);
    CHECK(record.events[0].command.sequence == 3);
    CHECK(record.events[0].command.config_generation == 7);
    CHECK(record.events[0].command.config_digest[31] == 32);
    CHECK(record.events[0].command.route_token == 17);
    CHECK(record.events[0].command.requested_value_native == 250);
    CHECK(record.events[0].feedback.valid_mask ==
          safety::kKnownFeedbackMask);
    CHECK(record.events[0].feedback.position_urad == 123456);
    CHECK(record.events[0].feedback.output_effort_unm == 112233);
    CHECK(record.events[0].bus.bus_off);
    CHECK(record.events[0].bus.response_timeouts == 4);

    safety::PersistentFaultSnapshot persisted = {};
    CHECK(evidence.snapshot(&persisted) == safety::FaultEvidenceResult::OK);
    CHECK(persisted.record.events[0].command.sequence == 3);
    CHECK(persisted.record.events[0].feedback.temperature_mk == 315150);
    CHECK(persisted.record.events[0].bus.transmit_errors == 2);
}

void TestSecondaryEventsPreservePrimaryAndBoundOverflow() {
    safety::SafetySupervisor supervisor(Configuration());
    safety::FaultEvidenceCore evidence(&supervisor, 22);
    safety::PersistentFaultSnapshot initial = InitialSnapshot();
    CHECK(evidence.recoverRequired(0, &initial) ==
          safety::FaultEvidenceResult::OK);
    Enable(&supervisor);
    CHECK(evidence.latch(
              FullBusOffEvent(10, safety::State::ENABLED)) ==
          safety::FaultEvidenceResult::OK);

    for (size_t index = 1; index < safety::kMaximumFaultEvents + 2; ++index) {
        safety::FaultEvent event = {};
        event.reason =
            index % 2 == 0
                ? safety::FailureReason::DRIVE_CRITICAL
                : safety::FailureReason::RESPONSE_BUDGET_EXCEEDED;
        event.monotonic_ms = 10 + index;
        event.state_before = safety::State::FAULT;
        const safety::FaultEvidenceResult result = evidence.latch(event);
        if (index < safety::kMaximumFaultEvents) {
            CHECK(result == safety::FaultEvidenceResult::OK);
        } else {
            CHECK(result ==
                  safety::FaultEvidenceResult::EVENT_RECORDED_WITH_OVERFLOW);
        }
    }

    const safety::FaultRecord& record = evidence.record();
    CHECK(record.events[0].reason == safety::FailureReason::BUS_OFF);
    CHECK(record.stored_event_count == safety::kMaximumFaultEvents);
    CHECK(record.total_event_count == safety::kMaximumFaultEvents + 2);
    CHECK(record.overflow_event_count == 2);
    CHECK(record.last_event_monotonic_ms ==
          10 + safety::kMaximumFaultEvents + 1);
    CHECK(HasFault(supervisor, safety::Fault::BUS_OFF));
    CHECK(HasFault(supervisor, safety::Fault::DRIVE_CRITICAL));
    CHECK(HasFault(supervisor,
                   safety::Fault::RESPONSE_BUDGET_EXCEEDED));

    safety::PersistentFaultSnapshot persisted = {};
    CHECK(evidence.snapshot(&persisted) == safety::FaultEvidenceResult::OK);
    safety::SafetySupervisor restarted(Configuration());
    safety::FaultEvidenceCore recovered(&restarted, 23);
    CHECK(recovered.recoverRequired(0, &persisted) ==
          safety::FaultEvidenceResult::OK);
    CHECK(recovered.record().total_event_count ==
          safety::kMaximumFaultEvents + 2);
    CHECK(restarted.state() == safety::State::FAULT);
}

void TestReconnectReloadAndRestartCannotClearOrEnable() {
    safety::SafetySupervisor supervisor(Configuration());
    safety::FaultEvidenceCore evidence(&supervisor, 31);
    safety::PersistentFaultSnapshot initial = InitialSnapshot();
    CHECK(evidence.recoverRequired(0, &initial) ==
          safety::FaultEvidenceResult::OK);
    Enable(&supervisor);
    CHECK(evidence.latch(
              FullBusOffEvent(10, safety::State::ENABLED)) ==
          safety::FaultEvidenceResult::OK);

    safety::PersistentFaultSnapshot before = {};
    safety::PersistentFaultSnapshot after = {};
    CHECK(evidence.snapshot(&before) == safety::FaultEvidenceResult::OK);
    safety::Prerequisites disconnected = Ready();
    disconnected.transport_ready = false;
    CHECK(supervisor.updatePrerequisites(11, disconnected) ==
          safety::Result::OK);
    CHECK(supervisor.updatePrerequisites(12, Ready()) == safety::Result::OK);
    CHECK(supervisor.completeBoot(13, Ready()) == safety::Result::INVALID_STATE);
    CHECK(supervisor.acquireLease(
              13, safety::MessageStamp(kOwnerOne, kSession, 4), 100) ==
          safety::Result::INVALID_STATE);
    CHECK(supervisor.enable(
              13, safety::MessageStamp(kOwnerOne, kSession, 5)) ==
          safety::Result::INVALID_STATE);
    CHECK(evidence.snapshot(&after) == safety::FaultEvidenceResult::OK);
    CHECK(before.checksum_crc32c == after.checksum_crc32c);
    CHECK(evidence.latched());
    CHECK(supervisor.state() == safety::State::FAULT);

    safety::SafetySupervisor restarted(Configuration());
    safety::FaultEvidenceCore recovered(&restarted, 32);
    CHECK(recovered.recoverRequired(0, &after) ==
          safety::FaultEvidenceResult::OK);
    CHECK(recovered.latched());
    CHECK(recovered.generation() == evidence.generation());
    CHECK(recovered.record().events[0].boot_id == 31);
    CHECK(recovered.record().events[0].command.sequence == 3);
    CHECK(restarted.state() == safety::State::FAULT);
    CHECK(restarted.shutdownIntent());
    CHECK(!restarted.outputsPermitted());
    CHECK(restarted.completeBoot(1, Ready()) == safety::Result::INVALID_STATE);
}

void TestSnapshotSemanticMutationIsRejected() {
    safety::SafetySupervisor supervisor(Configuration());
    safety::FaultEvidenceCore evidence(&supervisor, 41);
    safety::PersistentFaultSnapshot initial = InitialSnapshot();
    CHECK(evidence.recoverRequired(0, &initial) ==
          safety::FaultEvidenceResult::OK);
    Enable(&supervisor);
    CHECK(evidence.latch(
              FullBusOffEvent(10, safety::State::ENABLED)) ==
          safety::FaultEvidenceResult::OK);
    safety::PersistentFaultSnapshot persisted = {};
    CHECK(evidence.snapshot(&persisted) == safety::FaultEvidenceResult::OK);

    safety::PersistentFaultSnapshot mutations[5] = {
        persisted, persisted, persisted, persisted, persisted,
    };
    mutations[0].schema_major = 2;
    mutations[1].record.events[0].command.sequence = 99;
    mutations[2].record.reason_mask = 0;
    mutations[3].record.total_event_count = 0;
    mutations[4].last_generation = 2;
    for (size_t index = 0; index < 5; ++index) {
        safety::SafetySupervisor fresh(Configuration());
        safety::FaultEvidenceCore recovered(
            &fresh, static_cast<uint32_t>(42 + index));
        CHECK(recovered.recoverRequired(0, &mutations[index]) ==
              safety::FaultEvidenceResult::SNAPSHOT_CORRUPT);
        CHECK(recovered.latched());
        CHECK(fresh.state() == safety::State::FAULT);
        CHECK(HasFault(fresh, safety::Fault::FAULT_EVIDENCE_INVALID));
    }
}

void TestMalformedLiveEventFailsClosedWithExplicitCause() {
    safety::SafetySupervisor supervisor(Configuration());
    safety::FaultEvidenceCore evidence(&supervisor, 51);
    safety::PersistentFaultSnapshot initial = InitialSnapshot();
    CHECK(evidence.recoverRequired(0, &initial) ==
          safety::FaultEvidenceResult::OK);
    Enable(&supervisor);

    safety::FaultEvent malformed = FullBusOffEvent(
        10, safety::State::ENABLED);
    malformed.command.config_generation = 0;
    CHECK(evidence.latch(malformed) ==
          safety::FaultEvidenceResult::INVALID_EVENT);
    CHECK(evidence.latched());
    CHECK(evidence.record().events[0].reason ==
          safety::FailureReason::FAULT_EVIDENCE_INVALID);
    CHECK(supervisor.state() == safety::State::FAULT);
    CHECK(HasFault(supervisor, safety::Fault::FAULT_EVIDENCE_INVALID));
}

void TestResetRequiresEveryGuardAndNeverReenables() {
    safety::SafetySupervisor supervisor(Configuration());
    safety::FaultEvidenceCore evidence(&supervisor, 61);
    safety::PersistentFaultSnapshot initial = InitialSnapshot();
    CHECK(evidence.recoverRequired(0, &initial) ==
          safety::FaultEvidenceResult::OK);
    Enable(&supervisor);
    CHECK(evidence.latch(
              FullBusOffEvent(10, safety::State::ENABLED)) ==
          safety::FaultEvidenceResult::OK);
    const uint64_t generation = evidence.generation();

    safety::FaultResetEvidence reset_evidence = ResetEvidence(generation);
    reset_evidence.fault_record_durable = false;
    CHECK(evidence.reset(
              11, safety::MessageStamp(kOwnerOne, kSession, 3), Ready(),
              reset_evidence) ==
          safety::FaultEvidenceResult::RESET_EVIDENCE_REQUIRED);
    CHECK(evidence.latched());
    CHECK(supervisor.state() == safety::State::FAULT);

    reset_evidence = ResetEvidence(generation + 1);
    CHECK(evidence.reset(
              12, safety::MessageStamp(kOwnerOne, kSession, 4), Ready(),
              reset_evidence) ==
          safety::FaultEvidenceResult::RESET_GENERATION_MISMATCH);
    CHECK(evidence.latched());

    reset_evidence = ResetEvidence(generation);
    CHECK(evidence.reset(
              13, safety::MessageStamp(kOwnerTwo, kSession, 1), Ready(),
              reset_evidence) ==
          safety::FaultEvidenceResult::SUPERVISOR_DENIED);
    CHECK(evidence.latched());
    CHECK(supervisor.state() == safety::State::FAULT);

    safety::Prerequisites unresolved = Ready();
    unresolved.external_faults_clear = false;
    CHECK(evidence.reset(
              14, safety::MessageStamp(kOwnerOne, kSession, 4), unresolved,
              reset_evidence) ==
          safety::FaultEvidenceResult::SUPERVISOR_DENIED);
    CHECK(evidence.latched());

    CHECK(evidence.reset(
              15, safety::MessageStamp(kOwnerOne, kSession, 5), Ready(),
              reset_evidence) == safety::FaultEvidenceResult::OK);
    CHECK(!evidence.latched());
    CHECK(supervisor.state() == safety::State::BOOT);
    CHECK(!supervisor.outputsPermitted());
    CHECK(!supervisor.lease().active);

    safety::PersistentFaultSnapshot clean = {};
    CHECK(evidence.snapshot(&clean) == safety::FaultEvidenceResult::OK);
    CHECK(!clean.record.latched);
    CHECK(clean.last_generation == generation);

    safety::SafetySupervisor restarted(Configuration());
    safety::FaultEvidenceCore recovered(&restarted, 62);
    CHECK(recovered.recoverRequired(0, &clean) ==
          safety::FaultEvidenceResult::OK);
    CHECK(restarted.state() == safety::State::BOOT);
    CHECK(!restarted.outputsPermitted());
    CHECK(restarted.completeBoot(1, Ready()) == safety::Result::OK);
    CHECK(restarted.state() == safety::State::DISABLED);
    CHECK(!restarted.outputsPermitted());
}

void TestNewFaultGenerationAdvancesAfterExplicitReset() {
    safety::SafetySupervisor supervisor(Configuration());
    safety::FaultEvidenceCore evidence(&supervisor, 71);
    safety::PersistentFaultSnapshot initial = InitialSnapshot();
    CHECK(evidence.recoverRequired(0, &initial) ==
          safety::FaultEvidenceResult::OK);
    Enable(&supervisor);
    CHECK(evidence.latch(
              FullBusOffEvent(10, safety::State::ENABLED)) ==
          safety::FaultEvidenceResult::OK);
    CHECK(evidence.generation() == 1);
    CHECK(evidence.reset(
              11, safety::MessageStamp(kOwnerOne, kSession, 3), Ready(),
              ResetEvidence(1)) == safety::FaultEvidenceResult::OK);
    CHECK(supervisor.completeBoot(12, Ready()) == safety::Result::OK);

    safety::FaultEvent second = {};
    second.reason = safety::FailureReason::LOCAL_LIMIT;
    second.monotonic_ms = 13;
    second.state_before = safety::State::DISABLED;
    CHECK(evidence.latch(second) == safety::FaultEvidenceResult::OK);
    CHECK(evidence.generation() == 2);
    CHECK(evidence.record().events[0].reason ==
          safety::FailureReason::LOCAL_LIMIT);
    CHECK(supervisor.state() == safety::State::FAULT);
    CHECK(HasFault(supervisor, safety::Fault::LOCAL_LIMIT));
}

void TestRecoveryMustPrecedeLiveUse() {
    safety::SafetySupervisor supervisor(Configuration());
    safety::FaultEvidenceCore evidence(&supervisor, 81);
    safety::FaultEvent event = {};
    event.reason = safety::FailureReason::EXTERNAL;
    event.monotonic_ms = 1;
    event.state_before = safety::State::BOOT;
    CHECK(evidence.latch(event) ==
          safety::FaultEvidenceResult::RECOVERY_REQUIRED);
    CHECK(evidence.recoveryComplete());
    CHECK(evidence.latched());
    CHECK(supervisor.state() == safety::State::FAULT);
    CHECK(evidence.record().events[0].reason ==
          safety::FailureReason::FAULT_EVIDENCE_INVALID);
}

void TestNullSupervisorAndBootIdentityRejectWithoutDereference() {
    safety::PersistentFaultSnapshot initial = InitialSnapshot();
    safety::FaultEvent event = {};
    event.reason = safety::FailureReason::EXTERNAL;
    event.monotonic_ms = 1;
    event.state_before = safety::State::BOOT;

    safety::FaultEvidenceCore no_supervisor(NULL, 91);
    CHECK(no_supervisor.recoverRequired(0, &initial) ==
          safety::FaultEvidenceResult::INVALID_ARGUMENT);
    CHECK(no_supervisor.latch(event) ==
          safety::FaultEvidenceResult::INVALID_ARGUMENT);

    safety::SafetySupervisor supervisor(Configuration());
    safety::FaultEvidenceCore no_boot_identity(&supervisor, 0);
    CHECK(no_boot_identity.recoverRequired(0, &initial) ==
          safety::FaultEvidenceResult::INVALID_ARGUMENT);
    CHECK(no_boot_identity.latch(event) ==
          safety::FaultEvidenceResult::INVALID_ARGUMENT);
    CHECK(safety::FaultEvidenceCore::createInitialCleanSnapshot(NULL) ==
          safety::FaultEvidenceResult::INVALID_ARGUMENT);
}

}  // namespace

int main() {
    TestCleanProvisioningAndRecoveryStayBootDisabled();
    TestMissingAndCorruptRecoveryFailClosed();
    TestFullContextLatchesAndPreemptsOutputs();
    TestSecondaryEventsPreservePrimaryAndBoundOverflow();
    TestReconnectReloadAndRestartCannotClearOrEnable();
    TestSnapshotSemanticMutationIsRejected();
    TestMalformedLiveEventFailsClosedWithExplicitCause();
    TestResetRequiresEveryGuardAndNeverReenables();
    TestNewFaultGenerationAdvancesAfterExplicitReset();
    TestRecoveryMustPrecedeLiveUse();
    TestNullSupervisorAndBootIdentityRejectWithoutDereference();

    if (failures != 0) {
        std::cerr << failures << " of " << checks << " checks failed\n";
        return 1;
    }
    std::cout << "FAULT_EVIDENCE_OK " << checks << " checks\n";
    return 0;
}
