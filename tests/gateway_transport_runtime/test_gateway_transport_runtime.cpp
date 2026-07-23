#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "gateway_transport_runtime.h"

namespace gw = myactuator::gateway;
namespace rt = myactuator::runtime;
namespace safety = myactuator::safety;
namespace v44 = myactuator::rmd_v44;

static int failures = 0;

#define CHECK(condition)                                                       \
    do {                                                                       \
        if (!(condition)) {                                                    \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__,          \
                    #condition);                                               \
            ++failures;                                                        \
        }                                                                      \
    } while (0)

const uint32_t kOwner = 1;
const uint32_t kSession = 0x12345678U;

safety::ConfigCandidate Candidate() {
    safety::ConfigCandidate value = {};
    const char* id = "dropbear-test";
    value.identity.config_id.length =
        static_cast<uint8_t>(strlen(id));
    memcpy(value.identity.config_id.bytes, id, strlen(id));
    for (size_t index = 0; index < safety::kSha256DigestSize; ++index) {
        value.identity.digest.bytes[index] =
            static_cast<uint8_t>(index + 1);
    }
    value.identity.revision = 1;
    value.identity.schema_version = 1;
    value.generation = 1;
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

safety::GenerationCommitToken Token() {
    safety::GenerationCommitToken value = {};
    value.generation = 1;
    for (size_t index = 0; index < safety::kCommitTokenSize; ++index) {
        value.bytes[index] = static_cast<uint8_t>(0xA0 + index);
    }
    return value;
}

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

gw::Route Route(uint16_t token, uint8_t node_id) {
    gw::Route value = {};
    value.token = token;
    value.bus_id = 1;
    value.node_id = node_id;
    value.owner_id = kOwner;
    value.allowed_opcode_count = 2;
    value.allowed_opcodes[0] =
        static_cast<uint8_t>(v44::Command::kIqControl);
    value.allowed_opcodes[1] =
        static_cast<uint8_t>(v44::Command::kReadStatus1);
    value.safety_opcode = static_cast<uint8_t>(v44::Command::kStop);
    return value;
}

class FakeTransport : public rt::NativeCanTransport {
public:
    FakeTransport()
        : is_ready(true), send_result(rt::SendResult::SENT),
          receive_error(rt::ReceiveResult::NO_DATA), rx_head(0), rx_count(0),
          tx_count(0), last_bus(0), last_frame() {}

    bool ready(uint8_t bus_id) const {
        return is_ready && bus_id == 1;
    }

    rt::SendResult tryTransmit(uint8_t bus_id,
                               const v44::Frame& frame) {
        ++tx_count;
        last_bus = bus_id;
        last_frame = frame;
        return send_result;
    }

    rt::ReceiveResult tryReceive(rt::ReceivedFrame* frame) {
        if (receive_error != rt::ReceiveResult::NO_DATA) {
            const rt::ReceiveResult result = receive_error;
            receive_error = rt::ReceiveResult::NO_DATA;
            return result;
        }
        if (rx_head >= rx_count) {
            return rt::ReceiveResult::NO_DATA;
        }
        *frame = rx[rx_head++];
        return rt::ReceiveResult::FRAME;
    }

    void push(const rt::ReceivedFrame& frame) {
        CHECK(rx_count < 8);
        if (rx_count < 8) {
            rx[rx_count++] = frame;
        }
    }

    size_t remainingRx() const {
        return rx_count - rx_head;
    }

    bool is_ready;
    rt::SendResult send_result;
    rt::ReceiveResult receive_error;
    rt::ReceivedFrame rx[8];
    size_t rx_head;
    size_t rx_count;
    uint32_t tx_count;
    uint8_t last_bus;
    v44::Frame last_frame;
};

struct Harness {
    gw::Route routes[2];
    size_t route_count;
    safety::ConfigCandidate candidate;
    safety::SchemaCompatibilityPolicy schema_policy;
    safety::ConfigIdentityGuard guard;
    safety::Configuration safety_configuration;
    safety::SafetySupervisor supervisor;
    gw::GatewayCore core;
    FakeTransport transport;
    rt::GatewayTransportRuntime runtime;

    explicit Harness(uint8_t maximum_rx = 4,
                     uint8_t maximum_tx = 4,
                     size_t routes_used = 1,
                     uint32_t maximum_response_timeouts = 3)
        : routes(),
          route_count(routes_used),
          candidate(Candidate()),
          schema_policy{1, 1},
          guard(schema_policy),
          safety_configuration(kSession, 1, 1000, 100,
                               1UL << (kOwner - 1),
                               1UL << (kOwner - 1)),
          supervisor(safety_configuration),
          core(initializeRoutes(), route_count, gw::Policy(20, 1, 2),
               &guard, &supervisor),
          transport(),
          runtime(&core, &supervisor, &transport,
                  rt::ServicePolicy(maximum_rx, maximum_tx,
                                    maximum_response_timeouts)) {
        CHECK(core.valid());
        const safety::GenerationCommitToken token = Token();
        CHECK(guard.stageCandidate(0, candidate, Expectation(candidate), token)
              == safety::ConfigDecision::ALLOWED);
        CHECK(guard.commitStaged(0, token) ==
              safety::ConfigDecision::ALLOWED);
        CHECK(supervisor.completeBoot(0, Ready()) == safety::Result::OK);
        CHECK(supervisor.acquireLease(
                  0, safety::MessageStamp(kOwner, kSession, 1), 1000) ==
              safety::Result::OK);
        CHECK(supervisor.enable(
                  0, safety::MessageStamp(kOwner, kSession, 2)) ==
              safety::Result::OK);
        CHECK(runtime.valid());
    }

    gw::Route* initializeRoutes() {
        routes[0] = Route(100, 1);
        routes[1] = Route(101, 2);
        return routes;
    }

    void enqueue(size_t route_index,
                 uint64_t command_generation,
                 uint64_t sequence) {
        v44::Frame frame = {};
        CHECK(v44::EncodeIqControlRaw(routes[route_index].node_id, 25,
                                     &frame) == v44::Error::kOk);
        gw::Submission submission = {};
        submission.route_token = routes[route_index].token;
        submission.bus_id = routes[route_index].bus_id;
        submission.node_id = routes[route_index].node_id;
        submission.owner_id = routes[route_index].owner_id;
        submission.traffic_class = gw::TrafficClass::CONTROL;
        submission.config_proof.config.identity = candidate.identity;
        submission.config_proof.config.generation = candidate.generation;
        submission.config_proof.config.authorization_class =
            safety::AuthorizationClass::MOTION;
        submission.config_proof.command_generation = command_generation;
        submission.safety_session_id = kSession;
        submission.safety_sequence = sequence;
        submission.absolute_deadline_ms = 500;
        submission.frame = frame;
        CHECK(core.enqueue(0, submission) == gw::Code::OK);
    }
};

rt::ReceivedFrame Response(uint64_t now_ms,
                           uint8_t node_id,
                           const v44::Frame& request) {
    rt::ReceivedFrame received = {};
    received.bus_id = 1;
    received.monotonic_ms = now_ms;
    received.frame = request;
    received.frame.arbitration_id = v44::ResponseArbitrationId(node_id);
    return received;
}

bool HasCode(const gw::GatewayCore& core, gw::Code code) {
    for (size_t index = 0; index < core.dispositionCount(); ++index) {
        gw::Disposition value = {};
        CHECK(core.dispositionAt(index, &value));
        if (value.code == code) {
            return true;
        }
    }
    return false;
}

bool HasFault(const safety::SafetySupervisor& supervisor,
              safety::Fault fault) {
    return (supervisor.faultMask() &
            static_cast<uint32_t>(fault)) != 0;
}

void TestSuccessfulTransmitAndCorrelatedReceive() {
    Harness harness;
    harness.enqueue(0, 1, 3);
    rt::ServiceReport sent = harness.runtime.service(1, 1);
    CHECK(sent.code == rt::ServiceCode::OK);
    CHECK(sent.tx_attempted == 1);
    CHECK(sent.tx_sent == 1);
    CHECK(sent.tx_failed == 0);
    CHECK(harness.transport.last_bus == 1);
    CHECK(harness.core.outstandingResponseCount() == 1);

    harness.transport.push(Response(2, 1, harness.transport.last_frame));
    rt::ServiceReport received = harness.runtime.service(2, 2);
    CHECK(received.rx_frames == 1);
    CHECK(received.rx_accepted == 1);
    CHECK(received.rx_rejected == 0);
    CHECK(HasCode(harness.core, gw::Code::OK));
}

void TestTransmitFailureClearsSlotAndLatchesFault() {
    Harness harness;
    harness.transport.send_result = rt::SendResult::IO_ERROR;
    harness.enqueue(0, 1, 3);
    const rt::ServiceReport report = harness.runtime.service(1, 1);
    CHECK(report.code == rt::ServiceCode::TX_FAILED);
    CHECK(report.tx_failed == 1);
    CHECK(report.gateway_code == gw::Code::TRANSPORT_TX_FAILED);
    CHECK(harness.core.outstandingResponseCount() == 0);
    CHECK(harness.supervisor.state() == safety::State::FAULT);
    CHECK(HasFault(harness.supervisor, safety::Fault::EXTERNAL));
    CHECK(!HasFault(harness.supervisor, safety::Fault::BUS_OFF));
    CHECK(HasCode(harness.core, gw::Code::TRANSPORT_TX_FAILED));
}

void TestBusOffIsDistinct() {
    Harness harness;
    harness.transport.send_result = rt::SendResult::BUS_OFF;
    harness.enqueue(0, 1, 3);
    const rt::ServiceReport report = harness.runtime.service(1, 1);
    CHECK(report.code == rt::ServiceCode::BUS_OFF);
    CHECK(report.bus_off_observed);
    CHECK(report.gateway_code == gw::Code::TRANSPORT_BUS_OFF);
    CHECK(harness.supervisor.state() == safety::State::FAULT);
    CHECK(HasFault(harness.supervisor, safety::Fault::BUS_OFF));
    CHECK(!HasFault(harness.supervisor, safety::Fault::EXTERNAL));

    Harness receive;
    receive.transport.receive_error = rt::ReceiveResult::BUS_OFF;
    const rt::ServiceReport received = receive.runtime.service(1, 1);
    CHECK(received.code == rt::ServiceCode::BUS_OFF);
    CHECK(received.bus_off_observed);
    CHECK(HasFault(receive.supervisor, safety::Fault::BUS_OFF));
    CHECK(!HasFault(receive.supervisor, safety::Fault::EXTERNAL));
}

void TestExtendedTransportStatesRemainDistinct() {
    Harness rx_passive;
    rx_passive.transport.receive_error = rt::ReceiveResult::ERROR_PASSIVE;
    CHECK(rx_passive.runtime.service(1, 1).code ==
          rt::ServiceCode::ERROR_PASSIVE);
    CHECK(rx_passive.supervisor.state() == safety::State::FAULT);

    Harness rx_overflow;
    rx_overflow.transport.receive_error = rt::ReceiveResult::OVERFLOW;
    CHECK(rx_overflow.runtime.service(1, 1).code ==
          rt::ServiceCode::RX_OVERFLOW);
    CHECK(rx_overflow.supervisor.state() == safety::State::FAULT);

    Harness tx_passive;
    tx_passive.transport.send_result = rt::SendResult::ERROR_PASSIVE;
    tx_passive.enqueue(0, 1, 3);
    CHECK(tx_passive.runtime.service(1, 1).code ==
          rt::ServiceCode::ERROR_PASSIVE);
    CHECK(tx_passive.core.outstandingResponseCount() == 0);

    Harness tx_disabled;
    tx_disabled.transport.send_result = rt::SendResult::TX_DISABLED;
    tx_disabled.enqueue(0, 1, 3);
    CHECK(tx_disabled.runtime.service(1, 1).code ==
          rt::ServiceCode::TX_DISABLED);

    Harness not_ready;
    not_ready.transport.is_ready = false;
    not_ready.enqueue(0, 1, 3);
    CHECK(not_ready.runtime.service(1, 1).code ==
          rt::ServiceCode::TRANSPORT_NOT_READY);
}

void TestNoIoAdapterCanNeverSucceed() {
    rt::NoIoCanTransport adapter;
    v44::Frame frame = {};
    CHECK(!adapter.ready(1));
    CHECK(adapter.tryTransmit(1, frame) == rt::SendResult::IO_ERROR);
    rt::ReceivedFrame received = {};
    CHECK(adapter.tryReceive(&received) == rt::ReceiveResult::NO_DATA);
}

void TestFailedSafetyActionRetriesAfterTransportRecovery() {
    Harness harness;
    harness.transport.send_result = rt::SendResult::IO_ERROR;
    harness.enqueue(0, 1, 3);
    CHECK(harness.runtime.service(1, 1).code == rt::ServiceCode::TX_FAILED);
    CHECK(harness.runtime.service(2, 2).code == rt::ServiceCode::TX_FAILED);
    harness.transport.send_result = rt::SendResult::SENT;
    const rt::ServiceReport recovered = harness.runtime.service(3, 3);
    CHECK(recovered.tx_sent == 1);
    CHECK(harness.transport.last_frame.data[0] ==
          static_cast<uint8_t>(v44::Command::kStop));
    CHECK(harness.core.outstandingResponseCount() == 1);
}

void TestReceiveTimestampAndBudgetAreBounded() {
    Harness harness(2, 1);
    v44::Frame malformed = {};
    malformed.dlc = 7;
    for (uint8_t index = 0; index < 3; ++index) {
        rt::ReceivedFrame value = {};
        value.bus_id = 1;
        value.monotonic_ms = index == 0 ? 50 : 1;
        value.frame = malformed;
        harness.transport.push(value);
    }
    const rt::ServiceReport report = harness.runtime.service(2, 1);
    CHECK(report.rx_frames == 2);
    CHECK(report.rx_rejected == 2);
    CHECK(report.code == rt::ServiceCode::RX_REJECTED);
    CHECK(harness.transport.remainingRx() == 1);
}

void TestTransmitBudgetLeavesWorkQueued() {
    Harness harness(1, 1, 2);
    harness.enqueue(0, 1, 3);
    harness.enqueue(1, 2, 4);
    const rt::ServiceReport report = harness.runtime.service(1, 1);
    CHECK(report.tx_sent == 1);
    CHECK(harness.core.controlQueueSize() == 1);
}

void TestResponseTimeoutBudgetFaultsAtExactBoundaryAndStops() {
    Harness harness(4, 4, 1, 2);
    harness.enqueue(0, 1, 3);
    CHECK(harness.runtime.service(1, 1).tx_sent == 1);

    const rt::ServiceReport first_timeout =
        harness.runtime.service(21, 2);
    CHECK(first_timeout.expired_responses == 1);
    CHECK(first_timeout.consecutive_response_timeouts == 1);
    CHECK(first_timeout.code == rt::ServiceCode::OK);
    CHECK(harness.supervisor.state() == safety::State::ENABLED);

    harness.enqueue(0, 2, 4);
    CHECK(harness.runtime.service(22, 3).tx_sent == 1);
    const rt::ServiceReport at_budget =
        harness.runtime.service(42, 4);
    CHECK(at_budget.expired_responses == 1);
    CHECK(at_budget.consecutive_response_timeouts == 2);
    CHECK(at_budget.code == rt::ServiceCode::OK);
    CHECK(harness.supervisor.state() == safety::State::ENABLED);

    harness.enqueue(0, 3, 5);
    CHECK(harness.runtime.service(43, 5).tx_sent == 1);
    const rt::ServiceReport exceeded =
        harness.runtime.service(63, 6);
    CHECK(exceeded.expired_responses == 1);
    CHECK(exceeded.consecutive_response_timeouts == 3);
    CHECK(exceeded.code ==
          rt::ServiceCode::RESPONSE_BUDGET_EXCEEDED);
    CHECK(exceeded.tx_sent == 1);
    CHECK(harness.transport.last_frame.data[0] ==
          static_cast<uint8_t>(v44::Command::kStop));
    CHECK(harness.supervisor.state() == safety::State::FAULT);
    CHECK(HasFault(harness.supervisor,
                   safety::Fault::RESPONSE_BUDGET_EXCEEDED));
    CHECK(!HasFault(harness.supervisor, safety::Fault::EXTERNAL));
}

void TestAcceptedResponseResetsTimeoutStreak() {
    Harness harness(4, 4, 1, 2);
    harness.enqueue(0, 1, 3);
    CHECK(harness.runtime.service(1, 1).tx_sent == 1);
    CHECK(harness.runtime.service(21, 2)
              .consecutive_response_timeouts == 1);

    harness.enqueue(0, 2, 4);
    CHECK(harness.runtime.service(22, 3).tx_sent == 1);
    harness.transport.push(
        Response(23, 1, harness.transport.last_frame));
    const rt::ServiceReport accepted =
        harness.runtime.service(23, 4);
    CHECK(accepted.rx_accepted == 1);
    CHECK(accepted.consecutive_response_timeouts == 0);

    harness.enqueue(0, 3, 5);
    CHECK(harness.runtime.service(24, 5).tx_sent == 1);
    const rt::ServiceReport next_timeout =
        harness.runtime.service(44, 6);
    CHECK(next_timeout.expired_responses == 1);
    CHECK(next_timeout.consecutive_response_timeouts == 1);
    CHECK(next_timeout.code == rt::ServiceCode::OK);
    CHECK(harness.supervisor.state() == safety::State::ENABLED);
}

void TestCycleRegressionAndInvalidPolicyFailClosed() {
    Harness harness;
    CHECK(harness.runtime.service(1, 2).code == rt::ServiceCode::OK);
    CHECK(harness.runtime.service(1, 1).code ==
          rt::ServiceCode::CYCLE_REJECTED);
    rt::GatewayTransportRuntime invalid(
        &harness.core, &harness.supervisor, &harness.transport,
        rt::ServicePolicy(0, 1));
    CHECK(!invalid.valid());
    CHECK(invalid.service(2, 3).code == rt::ServiceCode::INVALID_RUNTIME);

    rt::GatewayTransportRuntime invalid_response_budget(
        &harness.core, &harness.supervisor, &harness.transport,
        rt::ServicePolicy(1, 1, 0));
    CHECK(!invalid_response_budget.valid());
    CHECK(invalid_response_budget.service(2, 3).code ==
          rt::ServiceCode::INVALID_RUNTIME);
    CHECK(strcmp(rt::ServiceCodeName(
                     rt::ServiceCode::RESPONSE_BUDGET_EXCEEDED),
                 "RESPONSE_BUDGET_EXCEEDED") == 0);
}

int main() {
    TestSuccessfulTransmitAndCorrelatedReceive();
    TestTransmitFailureClearsSlotAndLatchesFault();
    TestBusOffIsDistinct();
    TestExtendedTransportStatesRemainDistinct();
    TestNoIoAdapterCanNeverSucceed();
    TestFailedSafetyActionRetriesAfterTransportRecovery();
    TestReceiveTimestampAndBudgetAreBounded();
    TestTransmitBudgetLeavesWorkQueued();
    TestResponseTimeoutBudgetFaultsAtExactBoundaryAndStops();
    TestAcceptedResponseResetsTimeoutStreak();
    TestCycleRegressionAndInvalidPolicyFailClosed();
    if (failures != 0) {
        fprintf(stderr, "gateway transport runtime failures=%d\n", failures);
        return 1;
    }
    printf("GATEWAY_TRANSPORT_RUNTIME_OK cases=11\n");
    return 0;
}
