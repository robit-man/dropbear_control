#include "gateway_core.h"

#include <cstdlib>
#include <cstring>
#include <iostream>

namespace gw = myactuator::gateway;
namespace cfg = myactuator::safety;
namespace v44 = myactuator::rmd_v44;

namespace {

int g_checks = 0;

#define CHECK(expression)                                                        \
    do {                                                                         \
        ++g_checks;                                                              \
        if (!(expression)) {                                                     \
            std::cerr << __FILE__ << ":" << __LINE__                           \
                      << " CHECK failed: " #expression << "\n";                \
            std::exit(1);                                                        \
        }                                                                        \
    } while (0)

const uint32_t kSession = 0x13572468UL;
const uint32_t kOwner = 1;

cfg::SchemaCompatibilityPolicy SchemaPolicy() {
    cfg::SchemaCompatibilityPolicy policy = {1, 1};
    return policy;
}

cfg::Configuration SafetyConfiguration() {
    return cfg::Configuration(kSession, 1, 1000, 50, 0x00000003UL,
                              0x00000003UL);
}

cfg::Prerequisites ReadyPrerequisites() {
    cfg::Prerequisites prerequisites;
    prerequisites.configuration_valid = true;
    prerequisites.expected_nodes_present = true;
    prerequisites.transport_ready = true;
    prerequisites.safety_interlock_ready = true;
    prerequisites.external_faults_clear = true;
    prerequisites.motor_off_confirmed = true;
    return prerequisites;
}

cfg::ConfigIdentity Identity(const char* id,
                             uint64_t revision,
                             uint16_t schema_version,
                             uint8_t digest_seed = 0x40) {
    cfg::ConfigIdentity identity = {};
    const size_t length = std::strlen(id);
    CHECK(length <= cfg::kConfigIdCapacity);
    identity.config_id.length = static_cast<uint8_t>(length);
    std::memcpy(identity.config_id.bytes, id, length);
    for (size_t index = 0; index < cfg::kSha256DigestSize; ++index) {
        identity.digest.bytes[index] =
            static_cast<uint8_t>(digest_seed + index);
    }
    identity.revision = revision;
    identity.schema_version = schema_version;
    return identity;
}

cfg::ConfigCandidate Candidate(uint64_t generation = 1,
                               uint64_t validity_deadline = 10000) {
    cfg::ConfigCandidate candidate = {};
    candidate.identity = Identity("synthetic-dropbear", 1, 1);
    candidate.generation = generation;
    candidate.validity_deadline_ms = validity_deadline;
    candidate.structural_validated = true;
    candidate.semantic_validated = true;
    candidate.motion_allowed = true;
    candidate.authorization_class = cfg::AuthorizationClass::MOTION;
    return candidate;
}

cfg::ConfigExpectation Expectation(const cfg::ConfigCandidate& candidate) {
    cfg::ConfigExpectation expectation = {};
    expectation.identity = candidate.identity;
    expectation.generation = candidate.generation;
    return expectation;
}

cfg::GenerationCommitToken Token(uint64_t generation) {
    cfg::GenerationCommitToken token = {};
    token.generation = generation;
    for (size_t index = 0; index < cfg::kCommitTokenSize; ++index) {
        token.bytes[index] = static_cast<uint8_t>(0x80 + index);
    }
    return token;
}

cfg::ConfigReference Reference(const cfg::ConfigCandidate& candidate) {
    cfg::ConfigReference reference = {};
    reference.identity = candidate.identity;
    reference.generation = candidate.generation;
    reference.authorization_class = candidate.authorization_class;
    return reference;
}

void Activate(cfg::ConfigIdentityGuard* guard,
              const cfg::ConfigCandidate& candidate) {
    const cfg::GenerationCommitToken token = Token(candidate.generation);
    CHECK(guard->stageCandidate(0, candidate, Expectation(candidate), token) ==
          cfg::ConfigDecision::ALLOWED);
    CHECK(guard->commitStaged(0, token) == cfg::ConfigDecision::ALLOWED);
}

gw::Route MakeRoute(size_t index,
                    uint32_t owner = kOwner,
                    uint8_t safety_opcode = 0) {
    gw::Route route = {};
    route.token = static_cast<gw::RouteToken>(100 + index);
    route.bus_id = 1;
    route.node_id = static_cast<uint8_t>(index + 1);
    route.owner_id = owner;
    route.allowed_opcode_count = 3;
    route.allowed_opcodes[0] =
        static_cast<uint8_t>(v44::Command::kIqControl);
    route.allowed_opcodes[1] =
        static_cast<uint8_t>(v44::Command::kReadStatus1);
    route.allowed_opcodes[2] =
        static_cast<uint8_t>(v44::Command::kReadStatus2);
    route.safety_opcode =
        safety_opcode != 0
            ? safety_opcode
            : static_cast<uint8_t>(index % 2 == 0
                                       ? v44::Command::kStop
                                       : v44::Command::kShutdown);
    return route;
}

gw::Route* InitializeRoutes(gw::Route* routes, size_t route_count) {
    for (size_t index = 0; index < route_count; ++index) {
        routes[index] = MakeRoute(index);
    }
    return routes;
}

struct Harness {
    gw::Route routes[gw::kMaximumRoutes];
    size_t route_count;
    cfg::ConfigCandidate candidate;
    cfg::ConfigReference reference;
    cfg::ConfigIdentityGuard config_guard;
    cfg::SafetySupervisor supervisor;
    gw::GatewayCore core;

    Harness(size_t count = 2,
            uint32_t lease_duration = 1000,
            uint8_t diagnostic_budget = 1,
            uint8_t maximum_control_burst = 2)
        : routes(),
          route_count(count),
          candidate(Candidate()),
          reference(Reference(candidate)),
          config_guard(SchemaPolicy()),
          supervisor(SafetyConfiguration()),
          core(InitializeRoutes(routes, count), count,
               gw::Policy(20, diagnostic_budget, maximum_control_burst),
               &config_guard, &supervisor) {
        CHECK(core.valid());
        Activate(&config_guard, candidate);
        CHECK(supervisor.completeBoot(0, ReadyPrerequisites()) ==
              cfg::Result::OK);
        CHECK(supervisor.acquireLease(
                  0, cfg::MessageStamp(kOwner, kSession, 1),
                  lease_duration) == cfg::Result::OK);
        CHECK(supervisor.enable(
                  0, cfg::MessageStamp(kOwner, kSession, 2)) ==
              cfg::Result::OK);
        CHECK(core.beginCycle(1) == gw::Code::OK);
    }
};

v44::Frame RequestFrame(uint8_t node_id,
                        v44::Command command,
                        int16_t iq_raw = 25) {
    v44::Frame frame = {};
    v44::Error result = v44::Error::kInvalidCommand;
    if (command == v44::Command::kIqControl) {
        result = v44::EncodeIqControlRaw(node_id, iq_raw, &frame);
    } else {
        result = v44::EncodeZeroPayloadRequest(node_id, command, &frame);
    }
    CHECK(result == v44::Error::kOk);
    return frame;
}

gw::Submission Submission(Harness& harness,
                          size_t route_index,
                          gw::TrafficClass traffic_class,
                          v44::Command command,
                          uint64_t command_generation,
                          uint64_t safety_sequence,
                          uint64_t absolute_deadline = 500) {
    CHECK(route_index < harness.route_count);
    const gw::Route& route = harness.routes[route_index];
    gw::Submission submission = {};
    submission.route_token = route.token;
    submission.bus_id = route.bus_id;
    submission.node_id = route.node_id;
    submission.owner_id = route.owner_id;
    submission.traffic_class = traffic_class;
    submission.config_proof.config = harness.reference;
    submission.config_proof.command_generation = command_generation;
    submission.safety_session_id = kSession;
    submission.safety_sequence = safety_sequence;
    submission.absolute_deadline_ms = absolute_deadline;
    submission.frame = RequestFrame(route.node_id, command);
    return submission;
}

v44::Frame ResponseFor(const gw::TxEnvelope& transmitted,
                       uint8_t node_override = 0,
                       uint8_t opcode_override = 0) {
    v44::Frame response = transmitted.frame;
    const uint8_t node =
        node_override == 0 ? transmitted.node_id : node_override;
    response.arbitration_id = v44::ResponseArbitrationId(node);
    if (opcode_override != 0) {
        response.data[0] = opcode_override;
    }
    return response;
}

void CompleteStateResponse(Harness& harness,
                           const gw::TxEnvelope& transmitted,
                           uint64_t now_ms) {
    const v44::Frame response = ResponseFor(transmitted);
    CHECK(harness.core.acceptResponse(now_ms, transmitted.bus_id, response) ==
          gw::Code::OK);
    CHECK(harness.core.recordObservation(
              now_ms, transmitted.transaction_id,
              gw::ObservationClass::NATIVE_STATE_SAMPLE) == gw::Code::OK);
}

bool HasDisposition(const gw::GatewayCore& core,
                    gw::Phase phase,
                    gw::Code code) {
    for (size_t index = 0; index < core.dispositionCount(); ++index) {
        gw::Disposition event = {};
        CHECK(core.dispositionAt(index, &event));
        if (event.phase == phase && event.code == code) {
            return true;
        }
    }
    return false;
}

gw::Disposition LastDisposition(const gw::GatewayCore& core) {
    gw::Disposition event = {};
    CHECK(core.dispositionCount() != 0);
    CHECK(core.dispositionAt(core.dispositionCount() - 1, &event));
    return event;
}

void TestRouteValidationAndBrakeProhibition() {
    cfg::ConfigIdentityGuard guard(SchemaPolicy());
    cfg::SafetySupervisor supervisor(SafetyConfiguration());
    gw::Route routes[2] = {MakeRoute(0), MakeRoute(1)};
    gw::GatewayCore valid(routes, 2, gw::Policy(10, 1, 1), &guard,
                          &supervisor);
    CHECK(valid.valid());

    routes[1].token = routes[0].token;
    gw::GatewayCore duplicate_token(routes, 2, gw::Policy(10, 1, 1),
                                    &guard, &supervisor);
    CHECK(!duplicate_token.valid());

    routes[1] = MakeRoute(1);
    routes[1].node_id = routes[0].node_id;
    gw::GatewayCore duplicate_node(routes, 2, gw::Policy(10, 1, 1), &guard,
                                   &supervisor);
    CHECK(!duplicate_node.valid());

    routes[1] = MakeRoute(1);
    routes[1].safety_opcode =
        static_cast<uint8_t>(v44::Command::kBrakeRelease);
    gw::GatewayCore brake_safety(routes, 2, gw::Policy(10, 1, 1), &guard,
                                 &supervisor);
    CHECK(!brake_safety.valid());

    routes[1] = MakeRoute(1);
    routes[1].allowed_opcodes[0] =
        static_cast<uint8_t>(v44::Command::kBrakeLock);
    gw::GatewayCore brake_normal(routes, 2, gw::Policy(10, 1, 1), &guard,
                                 &supervisor);
    CHECK(!brake_normal.valid());

    routes[1] = MakeRoute(1);
    gw::GatewayCore bad_policy(routes, 2, gw::Policy(0, 1, 1), &guard,
                               &supervisor);
    CHECK(!bad_policy.valid());
    CHECK(std::strcmp(gw::CodeName(gw::Code::BRAKE_UNSUPPORTED),
                      "BRAKE_UNSUPPORTED") == 0);
}

void TestEnqueueValidationAndBoundedQueues() {
    Harness harness;
    gw::Submission request = Submission(
        harness, 0, gw::TrafficClass::CONTROL,
        v44::Command::kIqControl, 1, 3);

    gw::Submission wrong_route = request;
    wrong_route.node_id = 2;
    CHECK(harness.core.enqueue(1, wrong_route) == gw::Code::ROUTE_MISMATCH);

    gw::Submission wrong_owner = request;
    wrong_owner.owner_id = 2;
    CHECK(harness.core.enqueue(1, wrong_owner) == gw::Code::OWNER_MISMATCH);

    gw::Submission malformed = request;
    malformed.frame.dlc = 7;
    CHECK(harness.core.enqueue(1, malformed) ==
          gw::Code::INVALID_REQUEST_FRAME);

    gw::Submission wrong_class = request;
    wrong_class.traffic_class = gw::TrafficClass::DIAGNOSTIC;
    CHECK(harness.core.enqueue(1, wrong_class) ==
          gw::Code::TRAFFIC_CLASS_MISMATCH);

    gw::Submission brake = request;
    brake.frame = RequestFrame(1, v44::Command::kBrakeRelease);
    CHECK(harness.core.enqueue(1, brake) == gw::Code::BRAKE_UNSUPPORTED);

    gw::Submission stop = request;
    stop.frame = RequestFrame(1, v44::Command::kStop);
    CHECK(harness.core.enqueue(1, stop) ==
          gw::Code::SAFETY_OPCODE_WRONG_LANE);

    gw::Submission expired = request;
    expired.absolute_deadline_ms = 1;
    CHECK(harness.core.enqueue(1, expired) == gw::Code::DEADLINE_INVALID);

    for (size_t index = 0; index < gw::kControlQueueCapacity; ++index) {
        gw::Submission queued = request;
        queued.config_proof.command_generation = index + 1;
        queued.safety_sequence = index + 3;
        CHECK(harness.core.enqueue(1, queued) == gw::Code::OK);
    }
    CHECK(harness.core.controlQueueSize() == gw::kControlQueueCapacity);
    CHECK(harness.core.enqueue(1, request) ==
          gw::Code::CONTROL_QUEUE_FULL);

    Harness diagnostics;
    for (size_t index = 0; index < gw::kDiagnosticQueueCapacity; ++index) {
        gw::Submission queued = Submission(
            diagnostics, 0, gw::TrafficClass::DIAGNOSTIC,
            v44::Command::kReadStatus1, index + 1, index + 3);
        CHECK(diagnostics.core.enqueue(1, queued) == gw::Code::OK);
    }
    CHECK(diagnostics.core.diagnosticQueueSize() ==
          gw::kDiagnosticQueueCapacity);
    gw::Submission extra = Submission(
        diagnostics, 0, gw::TrafficClass::DIAGNOSTIC,
        v44::Command::kReadStatus1, 9, 12);
    CHECK(diagnostics.core.enqueue(1, extra) ==
          gw::Code::DIAGNOSTIC_QUEUE_FULL);
    CHECK(harness.core.dispositionCount() <= gw::kDispositionCapacity);
}

void TestNormalTransmitUsesFinalGuardsAndSharedCodec() {
    Harness harness;
    const gw::Submission command = Submission(
        harness, 0, gw::TrafficClass::CONTROL,
        v44::Command::kIqControl, 1, 3);
    CHECK(harness.core.enqueue(1, command) == gw::Code::OK);
    gw::TxEnvelope transmitted = {};
    CHECK(harness.core.pollTransmit(2, &transmitted) ==
          gw::PollResult::FRAME_READY);
    CHECK(!transmitted.safety_action);
    CHECK(transmitted.route_token == harness.routes[0].token);
    CHECK(transmitted.bus_id == harness.routes[0].bus_id);
    CHECK(transmitted.node_id == harness.routes[0].node_id);
    CHECK(transmitted.opcode ==
          static_cast<uint8_t>(v44::Command::kIqControl));
    v44::DecodedRequest decoded = {};
    CHECK(v44::DecodeRequest(transmitted.frame, &decoded, 1,
                             transmitted.opcode) == v44::Error::kOk);
    CHECK(decoded.iq_raw == 25);

    const gw::Disposition event = LastDisposition(harness.core);
    CHECK(event.phase == gw::Phase::NATIVE_TX);
    CHECK(event.config_checked);
    CHECK(event.config_decision == cfg::ConfigDecision::ALLOWED);
    CHECK(event.safety_checked);
    CHECK(event.safety_result == cfg::Result::OK);
    CHECK(event.command_generation == 1);
    CHECK(event.owner_id == kOwner);
    CHECK(event.session_id == kSession);
    CHECK(event.sequence == 3);
    CHECK(harness.core.outstandingResponseCount() == 1);
    CompleteStateResponse(harness, transmitted, 3);
    CHECK(harness.core.outstandingResponseCount() == 0);
}

void TestConfigRevokeDeadlineAndIdentityRaces() {
    {
        Harness harness;
        CHECK(harness.core.enqueue(
                  1, Submission(harness, 0, gw::TrafficClass::CONTROL,
                                v44::Command::kIqControl, 1, 3)) ==
              gw::Code::OK);
        // ADMITTED is bounded queue/shape admission only. It deliberately
        // precedes the mutable config and safety authorizations at TX time.
        CHECK(HasDisposition(harness.core, gw::Phase::ADMITTED,
                             gw::Code::OK));
        CHECK(harness.config_guard.revoke(2) == cfg::ConfigDecision::ALLOWED);
        gw::TxEnvelope transmitted = {};
        CHECK(harness.core.pollTransmit(2, &transmitted) ==
              gw::PollResult::NO_FRAME);
        CHECK(HasDisposition(harness.core, gw::Phase::REJECTED,
                             gw::Code::CONFIG_DENIED));
        CHECK(!HasDisposition(harness.core, gw::Phase::NATIVE_TX,
                              gw::Code::OK));
        CHECK(!transmitted.safety_action);
    }
    {
        Harness harness;
        gw::Submission command = Submission(
            harness, 0, gw::TrafficClass::CONTROL,
            v44::Command::kIqControl, 1, 3, 5);
        CHECK(harness.core.enqueue(1, command) == gw::Code::OK);
        gw::TxEnvelope transmitted = {};
        CHECK(harness.core.pollTransmit(5, &transmitted) ==
              gw::PollResult::NO_FRAME);
        CHECK(HasDisposition(harness.core, gw::Phase::REJECTED,
                             gw::Code::DEADLINE_EXPIRED));
    }
    {
        Harness harness;
        gw::Submission digest_mismatch = Submission(
            harness, 0, gw::TrafficClass::CONTROL,
            v44::Command::kIqControl, 1, 3);
        digest_mismatch.config_proof.config.identity.digest.bytes[0] ^= 0xFF;
        CHECK(harness.core.enqueue(1, digest_mismatch) == gw::Code::OK);
        gw::TxEnvelope transmitted = {};
        CHECK(harness.core.pollTransmit(2, &transmitted) ==
              gw::PollResult::NO_FRAME);
        const gw::Disposition event = LastDisposition(harness.core);
        CHECK(event.code == gw::Code::CONFIG_DENIED);
        CHECK(event.config_decision == cfg::ConfigDecision::DIGEST_MISMATCH);
    }
    {
        Harness harness;
        gw::Submission generation_mismatch = Submission(
            harness, 0, gw::TrafficClass::CONTROL,
            v44::Command::kIqControl, 1, 3);
        ++generation_mismatch.config_proof.config.generation;
        CHECK(harness.core.enqueue(1, generation_mismatch) == gw::Code::OK);
        gw::TxEnvelope transmitted = {};
        CHECK(harness.core.pollTransmit(2, &transmitted) ==
              gw::PollResult::NO_FRAME);
        const gw::Disposition event = LastDisposition(harness.core);
        CHECK(event.code == gw::Code::CONFIG_DENIED);
        CHECK(event.config_decision ==
              cfg::ConfigDecision::GENERATION_MISMATCH);
    }
}

void TestGenerationAndSafetyReplayEmitNoNormalTx() {
    {
        Harness harness;
        CHECK(harness.core.enqueue(
                  1, Submission(harness, 0, gw::TrafficClass::CONTROL,
                                v44::Command::kIqControl, 1, 3)) ==
              gw::Code::OK);
        CHECK(harness.core.enqueue(
                  1, Submission(harness, 1, gw::TrafficClass::CONTROL,
                                v44::Command::kIqControl, 1, 4)) ==
              gw::Code::OK);
        gw::TxEnvelope first = {};
        CHECK(harness.core.pollTransmit(2, &first) ==
              gw::PollResult::FRAME_READY);
        gw::TxEnvelope second = {};
        CHECK(harness.core.pollTransmit(2, &second) ==
              gw::PollResult::NO_FRAME);
        CHECK(HasDisposition(harness.core, gw::Phase::REJECTED,
                             gw::Code::REPLAY_REJECTED));
    }
    {
        Harness harness;
        CHECK(harness.core.enqueue(
                  1, Submission(harness, 0, gw::TrafficClass::CONTROL,
                                v44::Command::kIqControl, 1, 3)) ==
              gw::Code::OK);
        gw::TxEnvelope first = {};
        CHECK(harness.core.pollTransmit(2, &first) ==
              gw::PollResult::FRAME_READY);
        CompleteStateResponse(harness, first, 3);
        CHECK(harness.core.enqueue(
                  3, Submission(harness, 0, gw::TrafficClass::CONTROL,
                                v44::Command::kIqControl, 2, 3)) ==
              gw::Code::OK);
        gw::TxEnvelope replay = {};
        CHECK(harness.core.pollTransmit(4, &replay) ==
              gw::PollResult::NO_FRAME);
        const gw::Disposition event = LastDisposition(harness.core);
        CHECK(event.code == gw::Code::REPLAY_REJECTED);
        CHECK(event.safety_result ==
              cfg::Result::REPLAYED_OR_OUT_OF_ORDER);
    }
}

void TestLeaseExpiryAndFaultRacesUseOnlySafetyLane() {
    {
        Harness harness(2, 10);
        CHECK(harness.core.enqueue(
                  1, Submission(harness, 0, gw::TrafficClass::CONTROL,
                                v44::Command::kIqControl, 1, 3)) ==
              gw::Code::OK);
        gw::TxEnvelope output = {};
        CHECK(harness.core.pollTransmit(10, &output) ==
              gw::PollResult::FRAME_READY);
        CHECK(output.safety_action);
        CHECK(output.opcode ==
              static_cast<uint8_t>(v44::Command::kStop));
        CHECK(harness.supervisor.state() == cfg::State::SHUTDOWN);
        CHECK(HasDisposition(harness.core, gw::Phase::REJECTED,
                             gw::Code::LEASE_EXPIRED));
        CHECK(!HasDisposition(harness.core, gw::Phase::NATIVE_TX,
                              gw::Code::SAFETY_DENIED));
    }
    {
        Harness harness;
        CHECK(harness.core.enqueue(
                  1, Submission(harness, 0, gw::TrafficClass::CONTROL,
                                v44::Command::kIqControl, 1, 3)) ==
              gw::Code::OK);
        CHECK(harness.config_guard.revoke(2) == cfg::ConfigDecision::ALLOWED);
        CHECK(harness.supervisor.raiseFault(2, cfg::Fault::EXTERNAL) ==
              cfg::Result::OK);
        gw::TxEnvelope output = {};
        CHECK(harness.core.pollTransmit(2, &output) ==
              gw::PollResult::FRAME_READY);
        CHECK(output.safety_action);
        CHECK(output.opcode ==
              static_cast<uint8_t>(v44::Command::kStop));
        CHECK(harness.core.controlQueueSize() == 1);
    }
}

void TestMultiNodeOwnershipAndRouteIsolation() {
    Harness harness;
    CHECK(harness.routes[0].node_id != harness.routes[1].node_id);
    CHECK(harness.routes[0].token != harness.routes[1].token);
    CHECK(harness.routes[0].owner_id == harness.routes[1].owner_id);

    gw::Submission first = Submission(
        harness, 0, gw::TrafficClass::CONTROL,
        v44::Command::kIqControl, 1, 3);
    gw::Submission second = Submission(
        harness, 1, gw::TrafficClass::CONTROL,
        v44::Command::kIqControl, 2, 4);
    CHECK(harness.core.enqueue(1, first) == gw::Code::OK);
    CHECK(harness.core.enqueue(1, second) == gw::Code::OK);
    gw::TxEnvelope first_tx = {};
    gw::TxEnvelope second_tx = {};
    CHECK(harness.core.pollTransmit(2, &first_tx) ==
          gw::PollResult::FRAME_READY);
    CHECK(harness.core.pollTransmit(2, &second_tx) ==
          gw::PollResult::FRAME_READY);
    CHECK(first_tx.node_id == 1);
    CHECK(second_tx.node_id == 2);
    CHECK(first_tx.route_token != second_tx.route_token);

    Harness isolated;
    gw::Submission crossed = Submission(
        isolated, 0, gw::TrafficClass::CONTROL,
        v44::Command::kIqControl, 1, 3);
    crossed.frame = RequestFrame(isolated.routes[1].node_id,
                                 v44::Command::kIqControl);
    CHECK(isolated.core.enqueue(1, crossed) ==
          gw::Code::INVALID_REQUEST_FRAME);
}

void TestSafetyPriorityAndEchoNeverClaimsObservation() {
    Harness harness;
    CHECK(harness.core.enqueue(
              1, Submission(harness, 0, gw::TrafficClass::CONTROL,
                            v44::Command::kIqControl, 1, 3)) ==
          gw::Code::OK);
    CHECK(harness.supervisor.requestShutdown(
              2, cfg::MessageStamp(kOwner, kSession, 4)) == cfg::Result::OK);

    gw::TxEnvelope safety_tx = {};
    CHECK(harness.core.pollTransmit(2, &safety_tx) ==
          gw::PollResult::FRAME_READY);
    CHECK(safety_tx.safety_action);
    CHECK(safety_tx.node_id == 1);
    CHECK(safety_tx.opcode ==
          static_cast<uint8_t>(v44::Command::kStop));
    CHECK(harness.core.controlQueueSize() == 1);

    v44::DecodedRequest decoded = {};
    CHECK(v44::DecodeRequest(safety_tx.frame, &decoded, 1,
                             static_cast<uint8_t>(v44::Command::kStop)) ==
          v44::Error::kOk);
    CHECK(harness.core.acceptResponse(
              3, safety_tx.bus_id, ResponseFor(safety_tx)) == gw::Code::OK);
    CHECK(harness.core.recordObservation(
              3, safety_tx.transaction_id,
              gw::ObservationClass::NATIVE_STATE_SAMPLE) ==
          gw::Code::OBSERVATION_NOT_STATE);
    CHECK(harness.supervisor.state() == cfg::State::SHUTDOWN);
    CHECK(harness.supervisor.shutdownIntent());
    CHECK(harness.core.releaseCompletedResponse(safety_tx.transaction_id) ==
          gw::Code::OK);

    gw::TxEnvelope second_safety = {};
    CHECK(harness.core.pollTransmit(3, &second_safety) ==
          gw::PollResult::FRAME_READY);
    CHECK(second_safety.safety_action);
    CHECK(second_safety.node_id == 2);
    CHECK(second_safety.opcode ==
          static_cast<uint8_t>(v44::Command::kShutdown));
    // The core exposes one dispatch attempt per route for this shutdown
    // generation. It has no transport send-result or automatic retry input.
    gw::TxEnvelope no_retry = {};
    CHECK(harness.core.pollTransmit(3, &no_retry) ==
          gw::PollResult::NO_FRAME);
}

void TestUnconfiguredSafetyActionFailsClosed() {
    gw::Route route = MakeRoute(0);
    route.safety_opcode = 0;
    cfg::ConfigIdentityGuard guard(SchemaPolicy());
    cfg::SafetySupervisor supervisor(SafetyConfiguration());
    gw::GatewayCore core(&route, 1, gw::Policy(20, 1, 1), &guard,
                         &supervisor);
    CHECK(core.valid());
    CHECK(supervisor.completeBoot(0, ReadyPrerequisites()) == cfg::Result::OK);
    CHECK(supervisor.acquireLease(
              0, cfg::MessageStamp(kOwner, kSession, 1), 100) ==
          cfg::Result::OK);
    CHECK(supervisor.enable(0, cfg::MessageStamp(kOwner, kSession, 2)) ==
          cfg::Result::OK);
    CHECK(supervisor.raiseFault(1, cfg::Fault::EXTERNAL) == cfg::Result::OK);
    gw::TxEnvelope output = {};
    CHECK(core.pollTransmit(1, &output) == gw::PollResult::NO_FRAME);
    CHECK(HasDisposition(core, gw::Phase::REJECTED,
                         gw::Code::SAFETY_ACTION_UNCONFIGURED));
    CHECK(core.pollTransmit(1, &output) == gw::PollResult::NO_FRAME);
}

void TestDiagnosticBudgetAndAntiStarvation() {
    Harness harness(2, 1000, 1, 2);
    CHECK(harness.core.enqueue(
              1, Submission(harness, 0, gw::TrafficClass::CONTROL,
                            v44::Command::kIqControl, 1, 3)) ==
          gw::Code::OK);
    CHECK(harness.core.enqueue(
              1, Submission(harness, 1, gw::TrafficClass::CONTROL,
                            v44::Command::kIqControl, 2, 4)) ==
          gw::Code::OK);
    CHECK(harness.core.enqueue(
              1, Submission(harness, 0, gw::TrafficClass::CONTROL,
                            v44::Command::kIqControl, 4, 6)) ==
          gw::Code::OK);
    CHECK(harness.core.enqueue(
              1, Submission(harness, 0, gw::TrafficClass::DIAGNOSTIC,
                            v44::Command::kReadStatus1, 3, 5)) ==
          gw::Code::OK);
    CHECK(harness.core.enqueue(
              1, Submission(harness, 1, gw::TrafficClass::DIAGNOSTIC,
                            v44::Command::kReadStatus1, 5, 7)) ==
          gw::Code::OK);

    gw::TxEnvelope output = {};
    CHECK(harness.core.pollTransmit(2, &output) ==
          gw::PollResult::FRAME_READY);
    CHECK(output.opcode == static_cast<uint8_t>(v44::Command::kIqControl));
    CompleteStateResponse(harness, output, 2);
    CHECK(harness.core.pollTransmit(2, &output) ==
          gw::PollResult::FRAME_READY);
    CHECK(output.opcode == static_cast<uint8_t>(v44::Command::kIqControl));
    CompleteStateResponse(harness, output, 2);

    // The waiting diagnostic must run after a bounded two-control burst.
    CHECK(harness.core.pollTransmit(2, &output) ==
          gw::PollResult::FRAME_READY);
    CHECK(output.opcode ==
          static_cast<uint8_t>(v44::Command::kReadStatus1));
    CHECK(output.node_id == 1);
    CompleteStateResponse(harness, output, 2);

    CHECK(harness.core.pollTransmit(2, &output) ==
          gw::PollResult::FRAME_READY);
    CHECK(output.opcode == static_cast<uint8_t>(v44::Command::kIqControl));
    CompleteStateResponse(harness, output, 2);
    CHECK(harness.core.pollTransmit(2, &output) ==
          gw::PollResult::NO_FRAME);
    CHECK(harness.core.diagnosticQueueSize() == 1);

    CHECK(harness.core.beginCycle(2) == gw::Code::OK);
    CHECK(harness.core.pollTransmit(3, &output) ==
          gw::PollResult::FRAME_READY);
    CHECK(output.opcode ==
          static_cast<uint8_t>(v44::Command::kReadStatus1));
    CHECK(output.node_id == 2);
    CompleteStateResponse(harness, output, 3);
    CHECK(harness.core.diagnosticQueueSize() == 0);
    CHECK(harness.core.beginCycle(1) == gw::Code::CYCLE_REGRESSION);
}

void TestResponseCorrelationAndExplicitObservation() {
    Harness harness;
    CHECK(harness.core.enqueue(
              1, Submission(harness, 0, gw::TrafficClass::DIAGNOSTIC,
                            v44::Command::kReadStatus1, 1, 3)) ==
          gw::Code::OK);
    gw::TxEnvelope transmitted = {};
    CHECK(harness.core.pollTransmit(2, &transmitted) ==
          gw::PollResult::FRAME_READY);

    CHECK(harness.core.acceptResponse(
              3, transmitted.bus_id,
              ResponseFor(transmitted, 2, 0)) ==
          gw::Code::RESPONSE_UNEXPECTED_NODE);
    CHECK(harness.core.acceptResponse(
              3, transmitted.bus_id,
              ResponseFor(
                  transmitted, 0,
                  static_cast<uint8_t>(v44::Command::kReadStatus2))) ==
          gw::Code::RESPONSE_UNEXPECTED_OPCODE);

    v44::Frame malformed = ResponseFor(transmitted);
    malformed.data[3] = 2;
    CHECK(harness.core.acceptResponse(3, transmitted.bus_id, malformed) ==
          gw::Code::RESPONSE_MALFORMED);
    CHECK(harness.core.outstandingResponseCount() == 1);

    const v44::Frame valid = ResponseFor(transmitted);
    CHECK(harness.core.acceptResponse(3, transmitted.bus_id, valid) ==
          gw::Code::OK);
    CHECK(harness.core.acceptResponse(3, transmitted.bus_id, valid) ==
          gw::Code::RESPONSE_DUPLICATE);
    CHECK(HasDisposition(harness.core, gw::Phase::NATIVE_RESPONSE,
                         gw::Code::OK));
    CHECK(!HasDisposition(harness.core, gw::Phase::OBSERVED,
                          gw::Code::OK));
    CHECK(harness.core.recordObservation(
              4, transmitted.transaction_id,
              gw::ObservationClass::NATIVE_STATE_SAMPLE) == gw::Code::OK);
    CHECK(HasDisposition(harness.core, gw::Phase::OBSERVED,
                         gw::Code::OK));
    CHECK(harness.core.outstandingResponseCount() == 0);

    CHECK(HasDisposition(harness.core, gw::Phase::RECEIVED, gw::Code::OK));
    CHECK(HasDisposition(harness.core, gw::Phase::ADMITTED, gw::Code::OK));
    CHECK(HasDisposition(harness.core, gw::Phase::NATIVE_TX, gw::Code::OK));
}

void TestResponseDeadlineBoundary() {
    Harness harness;
    CHECK(harness.core.enqueue(
              1, Submission(harness, 0, gw::TrafficClass::DIAGNOSTIC,
                            v44::Command::kReadStatus1, 1, 3)) ==
          gw::Code::OK);
    gw::TxEnvelope transmitted = {};
    CHECK(harness.core.pollTransmit(5, &transmitted) ==
          gw::PollResult::FRAME_READY);
    CHECK(harness.core.expireResponses(24) == 0);
    CHECK(harness.core.expireResponses(25) == 1);
    CHECK(harness.core.outstandingResponseCount() == 0);
    CHECK(HasDisposition(harness.core, gw::Phase::REJECTED,
                         gw::Code::RESPONSE_TIMEOUT));
    CHECK(harness.core.acceptResponse(
              25, transmitted.bus_id, ResponseFor(transmitted)) ==
          gw::Code::RESPONSE_UNEXPECTED);
}

void TestResponseAndObservationChronology() {
    Harness harness;
    CHECK(harness.core.enqueue(
              1, Submission(harness, 0, gw::TrafficClass::DIAGNOSTIC,
                            v44::Command::kReadStatus1, 1, 3)) ==
          gw::Code::OK);
    gw::TxEnvelope transmitted = {};
    CHECK(harness.core.pollTransmit(10, &transmitted) ==
          gw::PollResult::FRAME_READY);

    const v44::Frame response = ResponseFor(transmitted);
    CHECK(harness.core.acceptResponse(9, transmitted.bus_id, response) ==
          gw::Code::RESPONSE_BEFORE_TRANSMIT);
    CHECK(HasDisposition(harness.core, gw::Phase::REJECTED,
                         gw::Code::RESPONSE_BEFORE_TRANSMIT));
    CHECK(harness.core.recordObservation(
              10, transmitted.transaction_id,
              gw::ObservationClass::NATIVE_STATE_SAMPLE) ==
          gw::Code::OBSERVATION_BEFORE_RESPONSE);

    CHECK(harness.core.acceptResponse(12, transmitted.bus_id, response) ==
          gw::Code::OK);
    CHECK(harness.core.recordObservation(
              11, transmitted.transaction_id,
              gw::ObservationClass::NATIVE_STATE_SAMPLE) ==
          gw::Code::OBSERVATION_BEFORE_RESPONSE);
    CHECK(HasDisposition(harness.core, gw::Phase::REJECTED,
                         gw::Code::OBSERVATION_BEFORE_RESPONSE));
    CHECK(harness.core.recordObservation(
              12, transmitted.transaction_id,
              gw::ObservationClass::NATIVE_STATE_SAMPLE) == gw::Code::OK);
}

void TestSafetyPreemptsFullNormalResponseSlots() {
    Harness harness(gw::kMaximumRoutes);
    for (size_t index = 0; index < gw::kMaximumRoutes; ++index) {
        CHECK(harness.core.enqueue(
                  1, Submission(harness, index, gw::TrafficClass::CONTROL,
                                v44::Command::kIqControl, index + 1,
                                index + 3)) == gw::Code::OK);
        gw::TxEnvelope output = {};
        CHECK(harness.core.pollTransmit(2, &output) ==
              gw::PollResult::FRAME_READY);
        CHECK(!output.safety_action);
    }
    CHECK(harness.core.outstandingResponseCount() ==
          gw::kResponseSlotCapacity);
    CHECK(harness.supervisor.requestShutdown(
              3, cfg::MessageStamp(kOwner, kSession, 11)) == cfg::Result::OK);
    gw::TxEnvelope safety_output = {};
    CHECK(harness.core.pollTransmit(3, &safety_output) ==
          gw::PollResult::FRAME_READY);
    CHECK(safety_output.safety_action);
    CHECK(harness.core.outstandingResponseCount() ==
          gw::kResponseSlotCapacity);
    CHECK(HasDisposition(harness.core, gw::Phase::REJECTED,
                         gw::Code::RESPONSE_PREEMPTED_BY_SAFETY));
}

void TestDispositionRingIsBoundedAndOrdered() {
    Harness harness;
    gw::Submission invalid = Submission(
        harness, 0, gw::TrafficClass::CONTROL,
        v44::Command::kIqControl, 1, 3);
    invalid.route_token = 999;
    for (size_t index = 0; index < gw::kDispositionCapacity + 20; ++index) {
        CHECK(harness.core.enqueue(1, invalid) ==
              gw::Code::ROUTE_NOT_FOUND);
    }
    CHECK(harness.core.dispositionCount() == gw::kDispositionCapacity);
    gw::Disposition first = {};
    gw::Disposition last = {};
    CHECK(harness.core.dispositionAt(0, &first));
    CHECK(harness.core.dispositionAt(
        harness.core.dispositionCount() - 1, &last));
    CHECK(first.event_id < last.event_id);
    CHECK(!harness.core.dispositionAt(
        harness.core.dispositionCount(), &last));
}

}  // namespace

int main() {
    TestRouteValidationAndBrakeProhibition();
    TestEnqueueValidationAndBoundedQueues();
    TestNormalTransmitUsesFinalGuardsAndSharedCodec();
    TestConfigRevokeDeadlineAndIdentityRaces();
    TestGenerationAndSafetyReplayEmitNoNormalTx();
    TestLeaseExpiryAndFaultRacesUseOnlySafetyLane();
    TestMultiNodeOwnershipAndRouteIsolation();
    TestSafetyPriorityAndEchoNeverClaimsObservation();
    TestUnconfiguredSafetyActionFailsClosed();
    TestDiagnosticBudgetAndAntiStarvation();
    TestResponseCorrelationAndExplicitObservation();
    TestResponseDeadlineBoundary();
    TestResponseAndObservationChronology();
    TestSafetyPreemptsFullNormalResponseSlots();
    TestDispositionRingIsBoundedAndOrdered();
    std::cout << "GATEWAY_CORE_OK checks=" << g_checks << "\n";
    return 0;
}
