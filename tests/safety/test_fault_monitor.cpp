#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "config_identity_guard.h"
#include "fault_monitor.h"
#include "gateway_core.h"
#include "rmd_v44_codec.h"

namespace gw = myactuator::gateway;
namespace safety = myactuator::safety;
namespace v44 = myactuator::rmd_v44;

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
const uint32_t kSession = 0x51AFC005UL;
const uint32_t kBootId = 0xA005U;
const uint32_t kRequiredFeedback =
    safety::FEEDBACK_POSITION | safety::FEEDBACK_VELOCITY |
    safety::FEEDBACK_Q_AXIS_CURRENT | safety::FEEDBACK_TEMPERATURE |
    safety::FEEDBACK_BUS_VOLTAGE;

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
    const char* id = "fault-monitor-test";
    value.identity.config_id.length =
        static_cast<uint8_t>(strlen(id));
    memcpy(value.identity.config_id.bytes, id, strlen(id));
    for (size_t index = 0; index < safety::kSha256DigestSize; ++index) {
        value.identity.digest.bytes[index] =
            static_cast<uint8_t>(index + 1U);
    }
    value.identity.revision = 1;
    value.identity.schema_version = 1;
    value.generation = 7;
    value.validity_deadline_ms = 10000;
    value.structural_validated = true;
    value.semantic_validated = true;
    value.motion_allowed = true;
    value.authorization_class = safety::AuthorizationClass::MOTION;
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
    value.generation = 7;
    for (size_t index = 0; index < safety::kCommitTokenSize; ++index) {
        value.bytes[index] = static_cast<uint8_t>(0xC0U + index);
    }
    return value;
}

gw::Route Route() {
    gw::Route value = {};
    value.token = 17;
    value.bus_id = 1;
    value.node_id = 2;
    value.owner_id = kOwner;
    value.allowed_opcode_count = 1;
    value.allowed_opcodes[0] =
        static_cast<uint8_t>(v44::Command::kIqControl);
    value.safety_opcode = static_cast<uint8_t>(v44::Command::kStop);
    return value;
}

struct Harness {
    safety::Configuration configuration;
    safety::SafetySupervisor supervisor;
    safety::FaultEvidenceCore evidence;
    safety::FaultMonitorPolicy monitor_policy;
    safety::FaultMonitor monitor;
    safety::ConfigCandidate candidate;
    safety::SchemaCompatibilityPolicy schema_policy;
    safety::ConfigIdentityGuard guard;
    gw::Route route;
    gw::GatewayCore gateway;
    uint64_t command_generation;

    Harness()
        : configuration(kSession, 1, 1000, 100,
                        1UL << (kOwner - 1), 1UL << (kOwner - 1)),
          supervisor(configuration),
          evidence(&supervisor, kBootId),
          monitor_policy(2, kRequiredFeedback, 5),
          monitor(&supervisor, &evidence, monitor_policy),
          candidate(Candidate()),
          schema_policy{1, 1},
          guard(schema_policy),
          route(Route()),
          gateway(&route, 1, gw::Policy(20, 1, 2),
                  &guard, &supervisor),
          command_generation(0) {
        safety::PersistentFaultSnapshot initial = {};
        CHECK(safety::FaultEvidenceCore::createInitialCleanSnapshot(
                  &initial) == safety::FaultEvidenceResult::OK);
        CHECK(evidence.recoverRequired(0, &initial) ==
              safety::FaultEvidenceResult::OK);
        const safety::GenerationCommitToken token = CommitToken();
        CHECK(guard.stageCandidate(
                  0, candidate, Expectation(candidate), token) ==
              safety::ConfigDecision::ALLOWED);
        CHECK(guard.commitStaged(0, token) ==
              safety::ConfigDecision::ALLOWED);
        CHECK(supervisor.completeBoot(0, Ready()) ==
              safety::Result::OK);
        CHECK(supervisor.acquireLease(
                  0, safety::MessageStamp(kOwner, kSession, 1), 1000) ==
              safety::Result::OK);
        CHECK(supervisor.enable(
                  0, safety::MessageStamp(kOwner, kSession, 2)) ==
              safety::Result::OK);
        CHECK(monitor.valid());
        CHECK(gateway.valid());
    }

    void enqueueIq(uint64_t sequence) {
        v44::Frame frame = {};
        CHECK(v44::EncodeIqControlRaw(route.node_id, 123, &frame) ==
              v44::Error::kOk);
        gw::Submission submission = {};
        submission.route_token = route.token;
        submission.bus_id = route.bus_id;
        submission.node_id = route.node_id;
        submission.owner_id = route.owner_id;
        submission.traffic_class = gw::TrafficClass::CONTROL;
        submission.config_proof.config.identity = candidate.identity;
        submission.config_proof.config.generation = candidate.generation;
        submission.config_proof.config.authorization_class =
            safety::AuthorizationClass::MOTION;
        submission.config_proof.command_generation =
            ++command_generation;
        submission.safety_session_id = kSession;
        submission.safety_sequence = sequence;
        submission.absolute_deadline_ms = 1000;
        submission.frame = frame;
        CHECK(gateway.enqueue(1, submission) == gw::Code::OK);
    }
};

safety::FaultMonitorSample HealthySample(uint64_t now_ms) {
    safety::FaultMonitorSample sample = {};
    sample.monotonic_ms = now_ms;
    sample.configuration_consistent = true;

    sample.command.present = true;
    sample.command.owner_id = kOwner;
    sample.command.session_id = kSession;
    sample.command.sequence = 3;
    sample.command.deadline_ms = 1000;
    sample.command.config_generation = 7;
    for (size_t index = 0; index < safety::kFaultConfigDigestSize; ++index) {
        sample.command.config_digest[index] =
            static_cast<uint8_t>(index + 1U);
    }
    sample.command.route_token = 17;
    sample.command.bus_id = 1;
    sample.command.node_id = 2;
    sample.command.opcode =
        static_cast<uint8_t>(v44::Command::kIqControl);
    sample.command.requested_value_native = 123;
    sample.command.admitted_value_native = 100;

    sample.feedback.valid_mask = safety::kKnownFeedbackMask;
    sample.feedback.sample_generation = 19;
    sample.feedback.sampled_at_ms = now_ms >= 2 ? now_ms - 2 : 0;
    sample.feedback.received_at_ms = now_ms >= 1 ? now_ms - 1 : 0;
    sample.feedback.position_urad = 123456;
    sample.feedback.velocity_urad_s = -6543;
    sample.feedback.q_axis_current_ma = 2000;
    sample.feedback.output_effort_unm = 112233;
    sample.feedback.temperature_mk = 315150;
    sample.feedback.bus_voltage_mv = 48000;
    sample.feedback.following_error_urad = 345;

    sample.bus.transmitted_frames = 100;
    sample.bus.received_frames = 98;
    sample.bus.transmit_errors = 2;
    sample.bus.receive_errors = 3;
    sample.bus.response_timeouts = 4;
    sample.bus.recovery_attempts = 1;
    sample.bus.last_receive_ms = sample.feedback.received_at_ms;
    return sample;
}

bool HasFault(const safety::SafetySupervisor& supervisor,
              safety::Fault fault) {
    return (supervisor.faultMask() &
            static_cast<uint32_t>(fault)) != 0;
}

void ApplyFailure(uint32_t bit, safety::FaultMonitorSample* sample) {
    switch (bit) {
        case safety::MONITOR_CONFIGURATION_MISMATCH:
            sample->configuration_consistent = false;
            return;
        case safety::MONITOR_BUS_OFF:
            sample->bus.bus_off = true;
            return;
        case safety::MONITOR_RESPONSE_BUDGET_EXCEEDED:
            sample->consecutive_response_timeouts = 3;
            return;
        case safety::MONITOR_DRIVE_CRITICAL:
            sample->drive_critical = true;
            return;
        case safety::MONITOR_LOCAL_LIMIT:
            sample->local_limit_violated = true;
            return;
        case safety::MONITOR_REQUIRED_FEEDBACK_INVALID:
            sample->feedback.valid_mask &= ~safety::FEEDBACK_BUS_VOLTAGE;
            return;
    }
}

safety::FailureReason ReasonForBit(uint32_t bit) {
    switch (bit) {
        case safety::MONITOR_CONFIGURATION_MISMATCH:
            return safety::FailureReason::CONFIGURATION_MISMATCH;
        case safety::MONITOR_BUS_OFF:
            return safety::FailureReason::BUS_OFF;
        case safety::MONITOR_RESPONSE_BUDGET_EXCEEDED:
            return safety::FailureReason::RESPONSE_BUDGET_EXCEEDED;
        case safety::MONITOR_DRIVE_CRITICAL:
            return safety::FailureReason::DRIVE_CRITICAL;
        case safety::MONITOR_LOCAL_LIMIT:
            return safety::FailureReason::LOCAL_LIMIT;
        case safety::MONITOR_REQUIRED_FEEDBACK_INVALID:
            return safety::FailureReason::REQUIRED_FEEDBACK_INVALID;
    }
    return safety::FailureReason::FAULT_EVIDENCE_INVALID;
}

safety::Fault SupervisorFaultForBit(uint32_t bit) {
    switch (bit) {
        case safety::MONITOR_CONFIGURATION_MISMATCH:
            return safety::Fault::CONFIGURATION_MISMATCH;
        case safety::MONITOR_BUS_OFF:
            return safety::Fault::BUS_OFF;
        case safety::MONITOR_RESPONSE_BUDGET_EXCEEDED:
            return safety::Fault::RESPONSE_BUDGET_EXCEEDED;
        case safety::MONITOR_DRIVE_CRITICAL:
            return safety::Fault::DRIVE_CRITICAL;
        case safety::MONITOR_LOCAL_LIMIT:
            return safety::Fault::LOCAL_LIMIT;
        case safety::MONITOR_REQUIRED_FEEDBACK_INVALID:
            return safety::Fault::REQUIRED_FEEDBACK_INVALID;
    }
    return safety::Fault::FAULT_EVIDENCE_INVALID;
}

void CheckExactContext(const safety::FaultEvent& event,
                       const safety::FaultMonitorSample& sample) {
    CHECK(event.boot_id == kBootId);
    CHECK(event.monotonic_ms == sample.monotonic_ms);
    CHECK(event.command.present);
    CHECK(event.command.owner_id == sample.command.owner_id);
    CHECK(event.command.session_id == sample.command.session_id);
    CHECK(event.command.sequence == sample.command.sequence);
    CHECK(event.command.deadline_ms == sample.command.deadline_ms);
    CHECK(event.command.config_generation ==
          sample.command.config_generation);
    CHECK(memcmp(event.command.config_digest,
                 sample.command.config_digest,
                 safety::kFaultConfigDigestSize) == 0);
    CHECK(event.command.route_token == sample.command.route_token);
    CHECK(event.command.bus_id == sample.command.bus_id);
    CHECK(event.command.node_id == sample.command.node_id);
    CHECK(event.command.opcode == sample.command.opcode);
    CHECK(event.command.requested_value_native ==
          sample.command.requested_value_native);
    CHECK(event.command.admitted_value_native ==
          sample.command.admitted_value_native);
    CHECK(event.feedback.valid_mask == sample.feedback.valid_mask);
    CHECK(event.feedback.sample_generation ==
          sample.feedback.sample_generation);
    CHECK(event.feedback.sampled_at_ms ==
          sample.feedback.sampled_at_ms);
    CHECK(event.feedback.received_at_ms ==
          sample.feedback.received_at_ms);
    CHECK(event.feedback.position_urad ==
          sample.feedback.position_urad);
    CHECK(event.feedback.velocity_urad_s ==
          sample.feedback.velocity_urad_s);
    CHECK(event.feedback.q_axis_current_ma ==
          sample.feedback.q_axis_current_ma);
    CHECK(event.feedback.output_effort_unm ==
          sample.feedback.output_effort_unm);
    CHECK(event.feedback.temperature_mk ==
          sample.feedback.temperature_mk);
    CHECK(event.feedback.bus_voltage_mv ==
          sample.feedback.bus_voltage_mv);
    CHECK(event.feedback.following_error_urad ==
          sample.feedback.following_error_urad);
    CHECK(event.bus.bus_off == sample.bus.bus_off);
    CHECK(event.bus.transmitted_frames ==
          sample.bus.transmitted_frames);
    CHECK(event.bus.received_frames == sample.bus.received_frames);
    CHECK(event.bus.transmit_errors == sample.bus.transmit_errors);
    CHECK(event.bus.receive_errors == sample.bus.receive_errors);
    CHECK(event.bus.response_timeouts ==
          sample.bus.response_timeouts);
    CHECK(event.bus.recovery_attempts ==
          sample.bus.recovery_attempts);
    CHECK(event.bus.last_receive_ms == sample.bus.last_receive_ms);
}

void TestEachSourcePreemptsQueuedTorqueWithExactEvidence() {
    const uint32_t bits[] = {
        safety::MONITOR_CONFIGURATION_MISMATCH,
        safety::MONITOR_BUS_OFF,
        safety::MONITOR_RESPONSE_BUDGET_EXCEEDED,
        safety::MONITOR_DRIVE_CRITICAL,
        safety::MONITOR_LOCAL_LIMIT,
        safety::MONITOR_REQUIRED_FEEDBACK_INVALID,
    };
    for (size_t index = 0; index < sizeof(bits) / sizeof(bits[0]); ++index) {
        Harness harness;
        harness.enqueueIq(3);
        safety::FaultMonitorSample sample = HealthySample(10);
        ApplyFailure(bits[index], &sample);
        const safety::FaultMonitorReport report =
            harness.monitor.observe(sample);
        CHECK(report.result == safety::FaultMonitorResult::FAULT_LATCHED);
        CHECK(report.newly_latched_mask == bits[index]);
        CHECK(report.active_failure_mask == bits[index]);
        CHECK(report.events_attempted == 1);
        CHECK(report.events_recorded == 1);
        CHECK(harness.supervisor.state() == safety::State::FAULT);
        CHECK(!harness.supervisor.outputsPermitted());
        CHECK(harness.supervisor.shutdownIntent());
        CHECK(HasFault(harness.supervisor,
                       SupervisorFaultForBit(bits[index])));
        CHECK(harness.evidence.record().stored_event_count == 1);
        const safety::FaultEvent& event =
            harness.evidence.record().events[0];
        CHECK(event.reason == ReasonForBit(bits[index]));
        CHECK(event.state_before == safety::State::ENABLED);
        CheckExactContext(event, sample);

        CHECK(harness.gateway.beginCycle(index + 1) == gw::Code::OK);
        gw::TxEnvelope envelope = {};
        CHECK(harness.gateway.pollTransmit(10, &envelope) ==
              gw::PollResult::FRAME_READY);
        CHECK(envelope.safety_action);
        CHECK(envelope.frame.data[0] ==
              static_cast<uint8_t>(v44::Command::kStop));
        CHECK(envelope.frame.data[0] !=
              static_cast<uint8_t>(v44::Command::kIqControl));
    }
}

void TestSimultaneousPriorityDuplicateAndRisingEdge() {
    Harness harness;
    safety::FaultMonitorSample sample = HealthySample(10);
    for (uint8_t bit = 0; bit < 6; ++bit) {
        ApplyFailure(1UL << bit, &sample);
    }
    const safety::FaultMonitorReport first =
        harness.monitor.observe(sample);
    CHECK(first.result == safety::FaultMonitorResult::FAULT_LATCHED);
    CHECK(first.newly_latched_mask == safety::kKnownMonitorFailureMask);
    CHECK(first.events_attempted == 6);
    CHECK(first.events_recorded == 6);
    CHECK(harness.evidence.record().stored_event_count == 6);
    CHECK(harness.evidence.record().total_event_count == 6);
    CHECK(harness.evidence.record().events[0].state_before ==
          safety::State::ENABLED);
    for (uint8_t index = 0; index < 6; ++index) {
        CHECK(harness.evidence.record().events[index].reason ==
              ReasonForBit(1UL << index));
        if (index > 0) {
            CHECK(harness.evidence.record().events[index].state_before ==
                  safety::State::FAULT);
        }
    }

    const safety::FaultMonitorReport duplicate =
        harness.monitor.observe(sample);
    CHECK(duplicate.result == safety::FaultMonitorResult::FAULT_ACTIVE);
    CHECK(duplicate.newly_latched_mask == 0);
    CHECK(duplicate.events_attempted == 0);
    CHECK(harness.evidence.record().total_event_count == 6);

    safety::FaultMonitorSample healthy = HealthySample(11);
    CHECK(harness.monitor.observe(healthy).result ==
          safety::FaultMonitorResult::OK);
    CHECK(harness.monitor.activeFailureMask() == 0);
    CHECK(harness.evidence.latched());
    CHECK(harness.supervisor.state() == safety::State::FAULT);

    safety::FaultMonitorSample reraised = HealthySample(12);
    reraised.bus.bus_off = true;
    const safety::FaultMonitorReport edge =
        harness.monitor.observe(reraised);
    CHECK(edge.result == safety::FaultMonitorResult::FAULT_LATCHED);
    CHECK(edge.newly_latched_mask == safety::MONITOR_BUS_OFF);
    CHECK(edge.events_recorded == 1);
    CHECK(harness.evidence.record().total_event_count == 7);
    CHECK(harness.evidence.record().events[6].reason ==
          safety::FailureReason::BUS_OFF);
    CHECK(harness.evidence.record().events[6].state_before ==
          safety::State::FAULT);
}

void TestResponseAndFeedbackBoundariesAreExact() {
    {
        Harness harness;
        safety::FaultMonitorSample at_budget = HealthySample(10);
        at_budget.consecutive_response_timeouts = 2;
        CHECK(harness.monitor.observe(at_budget).result ==
              safety::FaultMonitorResult::OK);
        safety::FaultMonitorSample beyond = HealthySample(11);
        beyond.consecutive_response_timeouts = 3;
        CHECK(harness.monitor.observe(beyond).result ==
              safety::FaultMonitorResult::FAULT_LATCHED);
        CHECK(harness.evidence.record().events[0].reason ==
              safety::FailureReason::RESPONSE_BUDGET_EXCEEDED);
    }
    {
        Harness harness;
        safety::FaultMonitorSample at_age = HealthySample(10);
        at_age.feedback.sampled_at_ms = 4;
        at_age.feedback.received_at_ms = 5;
        CHECK(harness.monitor.observe(at_age).result ==
              safety::FaultMonitorResult::OK);
        safety::FaultMonitorSample stale = at_age;
        stale.monotonic_ms = 11;
        CHECK(harness.monitor.observe(stale).result ==
              safety::FaultMonitorResult::FAULT_LATCHED);
        CHECK(harness.evidence.record().events[0].reason ==
              safety::FailureReason::REQUIRED_FEEDBACK_INVALID);
    }
}

void TestMalformedSamplesAndCommandContextFailClosed() {
    {
        Harness harness;
        safety::FaultMonitorSample sample = HealthySample(10);
        sample.feedback.valid_mask |= 1UL << 31;
        CHECK(harness.monitor.observe(sample).result ==
              safety::FaultMonitorResult::INVALID_SAMPLE);
        CHECK(harness.evidence.record().events[0].reason ==
              safety::FailureReason::FAULT_EVIDENCE_INVALID);
        CHECK(HasFault(harness.supervisor,
                       safety::Fault::FAULT_EVIDENCE_INVALID));
    }
    {
        Harness harness;
        safety::FaultMonitorSample sample = HealthySample(10);
        sample.consecutive_response_timeouts = 5;
        sample.bus.response_timeouts = 4;
        CHECK(harness.monitor.observe(sample).result ==
              safety::FaultMonitorResult::INVALID_SAMPLE);
        CHECK(harness.evidence.record().events[0].reason ==
              safety::FailureReason::FAULT_EVIDENCE_INVALID);
    }
    {
        Harness harness;
        safety::FaultMonitorSample sample = {};
        sample.monotonic_ms = 10;
        sample.configuration_consistent = true;
        sample.feedback.position_urad = 1;
        CHECK(harness.monitor.observe(sample).result ==
              safety::FaultMonitorResult::INVALID_SAMPLE);
    }
    {
        Harness harness;
        safety::FaultMonitorSample sample = HealthySample(10);
        sample.feedback.received_at_ms = 11;
        CHECK(harness.monitor.observe(sample).result ==
              safety::FaultMonitorResult::INVALID_SAMPLE);
    }
    {
        Harness harness;
        safety::FaultMonitorSample sample = HealthySample(10);
        sample.configuration_consistent = false;
        sample.command.config_generation = 0;
        CHECK(harness.monitor.observe(sample).result ==
              safety::FaultMonitorResult::INVALID_SAMPLE);
        CHECK(harness.evidence.record().events[0].reason ==
              safety::FailureReason::FAULT_EVIDENCE_INVALID);
    }
}

void TestRecoveryPolicyClockAndBindingFailuresFailClosed() {
    {
        safety::SafetySupervisor supervisor(
            safety::Configuration(kSession, 1, 1000, 100, 1, 1));
        safety::FaultEvidenceCore evidence(&supervisor, 1);
        safety::FaultMonitor monitor(
            &supervisor, &evidence,
            safety::FaultMonitorPolicy(2, kRequiredFeedback, 5));
        CHECK(monitor.valid());
        CHECK(monitor.observe(HealthySample(10)).result ==
              safety::FaultMonitorResult::RECOVERY_REQUIRED);
        CHECK(evidence.latched());
        CHECK(evidence.record().events[0].reason ==
              safety::FailureReason::FAULT_EVIDENCE_INVALID);
        CHECK(supervisor.state() == safety::State::FAULT);
    }
    {
        Harness harness;
        safety::FaultMonitor invalid(
            &harness.supervisor, &harness.evidence,
            safety::FaultMonitorPolicy(0, kRequiredFeedback, 5));
        CHECK(!invalid.valid());
        CHECK(invalid.observe(HealthySample(10)).result ==
              safety::FaultMonitorResult::INVALID_POLICY);
        CHECK(HasFault(harness.supervisor,
                       safety::Fault::FAULT_EVIDENCE_INVALID));
    }
    {
        Harness harness;
        CHECK(harness.monitor.observe(HealthySample(10)).result ==
              safety::FaultMonitorResult::OK);
        CHECK(harness.monitor.observe(HealthySample(9)).result ==
              safety::FaultMonitorResult::CLOCK_REGRESSION);
        CHECK(harness.evidence.record().events[0].monotonic_ms == 10);
        CHECK(harness.evidence.record().events[0].reason ==
              safety::FailureReason::FAULT_EVIDENCE_INVALID);
    }
    {
        Harness harness;
        safety::SafetySupervisor other(
            safety::Configuration(kSession, 1, 1000, 100, 1, 1));
        safety::FaultMonitor wrong(
            &other, &harness.evidence,
            safety::FaultMonitorPolicy(2, kRequiredFeedback, 5));
        CHECK(!wrong.valid());
        CHECK(wrong.observe(HealthySample(10)).result ==
              safety::FaultMonitorResult::INVALID_MONITOR);
        CHECK(HasFault(other, safety::Fault::FAULT_EVIDENCE_INVALID));
        CHECK(harness.evidence.record().total_event_count == 0);
        CHECK(harness.evidence.boundTo(&harness.supervisor));
        CHECK(!harness.evidence.boundTo(&other));
        CHECK(!harness.evidence.boundTo(NULL));
    }
    {
        safety::FaultMonitor null_monitor(
            NULL, NULL,
            safety::FaultMonitorPolicy(2, kRequiredFeedback, 5));
        CHECK(!null_monitor.valid());
        CHECK(null_monitor.observe(HealthySample(10)).result ==
              safety::FaultMonitorResult::INVALID_MONITOR);
    }
}

void TestBoundedSecondaryOverflowIsDeterministic() {
    Harness harness;
    uint64_t now_ms = 10;
    for (uint8_t index = 0; index < 11; ++index) {
        safety::FaultMonitorSample failure = HealthySample(now_ms++);
        failure.drive_critical = true;
        const safety::FaultMonitorReport report =
            harness.monitor.observe(failure);
        CHECK(report.result == safety::FaultMonitorResult::FAULT_LATCHED);
        CHECK(report.events_recorded == 1);
        safety::FaultMonitorSample healthy = HealthySample(now_ms++);
        CHECK(harness.monitor.observe(healthy).result ==
              safety::FaultMonitorResult::OK);
    }
    CHECK(harness.evidence.record().stored_event_count ==
          safety::kMaximumFaultEvents);
    CHECK(harness.evidence.record().total_event_count == 11);
    CHECK(harness.evidence.record().overflow_event_count == 3);
    CHECK(harness.evidence.record().events[0].state_before ==
          safety::State::ENABLED);
    CHECK(harness.evidence.record().events[7].state_before ==
          safety::State::FAULT);
}

void TestResultNamesAreStable() {
    CHECK(strcmp(safety::FaultMonitorResultName(
                     safety::FaultMonitorResult::OK), "OK") == 0);
    CHECK(strcmp(safety::FaultMonitorResultName(
                     safety::FaultMonitorResult::FAULT_LATCHED),
                 "FAULT_LATCHED") == 0);
    CHECK(strcmp(safety::FaultMonitorResultName(
                     safety::FaultMonitorResult::FAULT_ACTIVE),
                 "FAULT_ACTIVE") == 0);
    CHECK(strcmp(safety::FaultMonitorResultName(
                     safety::FaultMonitorResult::INVALID_MONITOR),
                 "INVALID_MONITOR") == 0);
    CHECK(strcmp(safety::FaultMonitorResultName(
                     safety::FaultMonitorResult::RECOVERY_REQUIRED),
                 "RECOVERY_REQUIRED") == 0);
    CHECK(strcmp(safety::FaultMonitorResultName(
                     safety::FaultMonitorResult::INVALID_POLICY),
                 "INVALID_POLICY") == 0);
    CHECK(strcmp(safety::FaultMonitorResultName(
                     safety::FaultMonitorResult::CLOCK_REGRESSION),
                 "CLOCK_REGRESSION") == 0);
    CHECK(strcmp(safety::FaultMonitorResultName(
                     safety::FaultMonitorResult::INVALID_SAMPLE),
                 "INVALID_SAMPLE") == 0);
    CHECK(strcmp(safety::FaultMonitorResultName(
                     safety::FaultMonitorResult::EVIDENCE_DENIED),
                 "EVIDENCE_DENIED") == 0);
    CHECK(strcmp(safety::FaultMonitorResultName(
                     static_cast<safety::FaultMonitorResult>(255)),
                 "UNKNOWN_FAULT_MONITOR_RESULT") == 0);
}

}  // namespace

int main() {
    TestEachSourcePreemptsQueuedTorqueWithExactEvidence();
    TestSimultaneousPriorityDuplicateAndRisingEdge();
    TestResponseAndFeedbackBoundariesAreExact();
    TestMalformedSamplesAndCommandContextFailClosed();
    TestRecoveryPolicyClockAndBindingFailuresFailClosed();
    TestBoundedSecondaryOverflowIsDeterministic();
    TestResultNamesAreStable();
    if (failures != 0) {
        fprintf(stderr,
                "fault monitor failures=%d checks=%llu\n",
                failures,
                static_cast<unsigned long long>(checks));
        return 1;
    }
    printf("FAULT_MONITOR_OK checks=%llu sources=6 overflow_events=3\n",
           static_cast<unsigned long long>(checks));
    return 0;
}
