#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <cmath>
#include <limits>

#include "config_identity_guard.h"
#include "gateway_core.h"
#include "gateway_transport_runtime.h"
#include "host_command_ingress.h"
#include "hostlink_v1.h"
#include "rmd_v44_codec.h"
#include "safety_supervisor.h"

namespace gw = myactuator::gateway;
namespace host = myactuator::hostlink_v1;
namespace rt = myactuator::runtime;
namespace safety = myactuator::safety;
namespace v44 = myactuator::rmd_v44;

namespace {

int failures = 0;

#define CHECK(condition)                                                       \
    do {                                                                       \
        if (!(condition)) {                                                    \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__,          \
                    #condition);                                               \
            ++failures;                                                        \
        }                                                                      \
    } while (0)

static const uint64_t kSession = 0x12345678ULL;
static const uint64_t kFrameTimeNs = 2000000ULL;
static const uint64_t kEvaluationTimeNs = 3000000ULL;
static const uint64_t kDeadlineNs = 100000000ULL;

void Set(host::Text* output, const char* value) {
    CHECK(host::SetText(output, value, strlen(value)) == host::Status::OK);
}

host::Sha256 Digest() {
    host::Sha256 value = {};
    for (size_t index = 0; index < sizeof(value.bytes); ++index) {
        value.bytes[index] = static_cast<uint8_t>(index + 1U);
    }
    return value;
}

host::Capabilities Capabilities() {
    host::Capabilities value = {};
    value.accepted = true;
    value.selected_major = host::kVersionMajor;
    value.selected_minor = host::kVersionMinor;
    value.selected_capabilities = host::kMandatoryCapabilities;
    value.selected_rate_hz = 500U;
    value.selected_payload_size = host::kMaxPayloadSize;
    value.rejection = host::NegotiationRejection::NONE;
    return value;
}

rt::HostCommandBinding Binding(const char* actuator = "joint.left.hip",
                               const char* source = "controller.primary",
                               uint16_t route_token = 7U,
                               uint8_t node_id = 1U) {
    rt::HostCommandBinding value = {};
    Set(&value.canonical_actuator_id, actuator);
    Set(&value.source_identity, source);
    Set(&value.lease_owner, source);
    Set(&value.host_config.identity, "synthetic-v44-node1");
    Set(&value.host_config.revision, "1");
    value.host_config.sha256 = Digest();
    value.safety_config.identity.config_id.length =
        static_cast<uint8_t>(value.host_config.identity.size);
    memcpy(value.safety_config.identity.config_id.bytes,
           value.host_config.identity.bytes, value.host_config.identity.size);
    memcpy(value.safety_config.identity.digest.bytes,
           value.host_config.sha256.bytes, sizeof(value.host_config.sha256.bytes));
    value.safety_config.identity.revision = 1U;
    value.safety_config.identity.schema_version = 1U;
    value.safety_config.generation = 1U;
    value.safety_config.authorization_class =
        safety::AuthorizationClass::MOTION;
    value.route_token = route_token;
    value.bus_id = 1U;
    value.node_id = node_id;
    value.owner_id = 1U;
    value.translation = rt::TranslationKind::RMD_V44_IQ_CURRENT_A;
    value.iq_amperes_per_lsb_numerator =
        rt::kRmdV44IqAmperesPerLsbNumerator;
    value.iq_amperes_per_lsb_denominator =
        rt::kRmdV44IqAmperesPerLsbDenominator;
    value.minimum_iq_raw = -1000;
    value.maximum_iq_raw = 1000;
    return value;
}

host::Command Command(host::CommandMode mode = host::CommandMode::CURRENT_Q,
                      double value = 1.25,
                      uint64_t deadline_ns = kDeadlineNs) {
    host::Command command = {};
    Set(&command.canonical_actuator_id, "joint.left.hip");
    Set(&command.config.identity, "synthetic-v44-node1");
    Set(&command.config.revision, "1");
    command.config.sha256 = Digest();
    Set(&command.source_identity, "controller.primary");
    Set(&command.lease_id, "lease.boot-1");
    Set(&command.lease_owner, "controller.primary");
    command.lease_sequence = 3U;
    command.lease_expiry_monotonic_ns = deadline_ns;
    command.mode = mode;
    command.enable_requested = mode != host::CommandMode::DISABLE;
    switch (mode) {
        case host::CommandMode::DISABLE:
            break;
        case host::CommandMode::POSITION:
            command.position_rad = {true, value};
            break;
        case host::CommandMode::VELOCITY:
            command.velocity_rad_s = {true, value};
            break;
        case host::CommandMode::EFFORT:
            command.effort_nm = {true, value};
            break;
        case host::CommandMode::CURRENT_Q:
            command.current_q_a = {true, value};
            break;
        case host::CommandMode::IMPEDANCE:
            command.position_rad = {true, value};
            command.velocity_rad_s = {true, 0.0};
            command.stiffness_nm_per_rad = {true, 1.0};
            command.damping_nm_s_per_rad = {true, 0.1};
            break;
    }
    return command;
}

bool FrameFor(const host::Command& command,
              host::Frame* frame,
              uint64_t sequence = 3U,
              uint64_t session = kSession,
              uint64_t frame_time_ns = kFrameTimeNs,
              const host::Sha256* envelope_digest = NULL) {
    static uint8_t encoded[host::kMaxFrameSize];
    host::TypedMessage message = {};
    message.type = host::MessageType::COMMAND;
    message.command = command;
    host::Envelope envelope = {};
    envelope.session_id = session;
    envelope.sequence = sequence;
    envelope.monotonic_ns = frame_time_ns;
    envelope.config_sha256 = envelope_digest == NULL
                                 ? command.config.sha256
                                 : *envelope_digest;
    size_t size = 0U;
    if (host::EncodeMessage(message, envelope, encoded, sizeof(encoded),
                            &size) != host::Status::OK) {
        return false;
    }
    return host::DecodeFrame(encoded, size, frame) == host::Status::OK;
}

struct IngressHarness {
    rt::HostCommandBinding binding;
    host::Frame frame;
    gw::Submission submission;

    IngressHarness() : binding(Binding()), frame(), submission() {}

    rt::IngressResult run(const host::Command& command,
                          uint64_t now_ns = kEvaluationTimeNs,
                          uint64_t session = kSession,
                          uint64_t sequence = 3U) {
        CHECK(FrameFor(command, &frame, sequence, session));
        rt::HostCommandIngress ingress(&binding, 1U, session, Digest(),
                                       Capabilities(), 2U, 0U);
        CHECK(ingress.valid());
        return ingress.receive(frame, now_ns, &submission);
    }
};

void TestBindingValidation() {
    rt::HostCommandBinding value = Binding();
    CHECK(rt::ValidateHostCommandBinding(value) == rt::BindingCode::OK);
    CHECK(strcmp(rt::BindingCodeName(rt::BindingCode::OK), "OK") == 0);
    CHECK(strcmp(rt::BindingCodeName(static_cast<rt::BindingCode>(255)),
                 "UNKNOWN_BINDING_CODE") == 0);

    value = Binding();
    value.canonical_actuator_id.size = 0U;
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::TEXT_INVALID);
    value = Binding();
    value.host_config.identity.size = safety::kConfigIdCapacity + 1U;
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::CONFIG_ID_TOO_LONG);
    value = Binding();
    Set(&value.host_config.revision, "01");
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::CONFIG_REVISION_INVALID);
    value = Binding();
    value.safety_config.identity.config_id.bytes[0] = 'X';
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::CONFIG_ID_MISMATCH);
    value = Binding();
    value.safety_config.identity.revision = 2U;
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::CONFIG_REVISION_MISMATCH);
    value = Binding();
    value.safety_config.identity.digest.bytes[0] ^= 1U;
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::CONFIG_DIGEST_MISMATCH);
    value = Binding();
    value.safety_config.identity.schema_version = 2U;
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::CONFIG_SCHEMA_UNSUPPORTED);
    value = Binding();
    value.safety_config.generation = 0U;
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::CONFIG_GENERATION_INVALID);
    value = Binding();
    value.safety_config.authorization_class =
        safety::AuthorizationClass::OBSERVE_ONLY;
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::CONFIG_AUTHORIZATION_DENIED);
    value = Binding();
    value.node_id = 0U;
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::ROUTE_INVALID);
    value = Binding();
    value.owner_id = 33U;
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::OWNER_INVALID);
    value = Binding();
    value.translation = static_cast<rt::TranslationKind>(9U);
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::TRANSLATION_UNSUPPORTED);
    value = Binding();
    value.iq_amperes_per_lsb_denominator = 10U;
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::SCALE_UNSUPPORTED);
    value = Binding();
    value.minimum_iq_raw = 2;
    value.maximum_iq_raw = 1;
    CHECK(rt::ValidateHostCommandBinding(value) ==
          rt::BindingCode::CURRENT_RANGE_INVALID);

    rt::HostCommandBinding duplicates[2] = {Binding(), Binding()};
    rt::HostCommandIngress duplicate_selector(
        duplicates, 2U, kSession, Digest(), Capabilities());
    CHECK(!duplicate_selector.valid());
    CHECK(duplicate_selector.bindingStatus() ==
          rt::BindingCode::DUPLICATE_SELECTOR);
    duplicates[1] = Binding("joint.right.hip", "controller.secondary", 7U,
                            2U);
    rt::HostCommandIngress duplicate_route(
        duplicates, 2U, kSession, Digest(), Capabilities());
    CHECK(!duplicate_route.valid());
    CHECK(duplicate_route.bindingStatus() == rt::BindingCode::DUPLICATE_ROUTE);

    rt::HostCommandIngress null_ingress(
        NULL, 1U, kSession, Digest(), Capabilities());
    CHECK(!null_ingress.valid());
    CHECK(null_ingress.bindingStatus() == rt::BindingCode::NULL_BINDINGS);
    rt::HostCommandBinding bindings[rt::kMaximumHostCommandBindings + 1U] = {};
    rt::HostCommandIngress too_many(
        bindings, rt::kMaximumHostCommandBindings + 1U, kSession, Digest(),
        Capabilities());
    CHECK(!too_many.valid());
    CHECK(too_many.bindingStatus() == rt::BindingCode::COUNT_INVALID);
}

void TestExactPositiveTranslation() {
    IngressHarness harness;
    const rt::IngressResult result = harness.run(Command());
    CHECK(result.code == rt::IngressCode::OK);
    CHECK(result.link_accepted);
    CHECK(result.evaluation_time_ms == 3U);
    CHECK(result.route_token == harness.binding.route_token);
    CHECK(harness.submission.route_token == harness.binding.route_token);
    CHECK(harness.submission.bus_id == harness.binding.bus_id);
    CHECK(harness.submission.node_id == harness.binding.node_id);
    CHECK(harness.submission.owner_id == harness.binding.owner_id);
    CHECK(harness.submission.traffic_class == gw::TrafficClass::CONTROL);
    CHECK(harness.submission.config_proof.config.generation == 1U);
    CHECK(harness.submission.config_proof.command_generation == 3U);
    CHECK(harness.submission.safety_session_id == kSession);
    CHECK(harness.submission.safety_sequence == 3U);
    CHECK(harness.submission.absolute_deadline_ms == 100U);
    v44::DecodedRequest decoded = {};
    CHECK(v44::DecodeRequest(harness.submission.frame, &decoded, 1U,
                             static_cast<uint8_t>(v44::Command::kIqControl)) ==
          v44::Error::kOk);
    CHECK(decoded.iq_raw == 125);
    CHECK(strcmp(rt::IngressCodeName(result.code), "OK") == 0);
    CHECK(strcmp(rt::IngressCodeName(static_cast<rt::IngressCode>(255)),
                 "UNKNOWN_INGRESS_CODE") == 0);
}

void TestExactSelectionDenials() {
    IngressHarness harness;
    host::Command command = Command();
    Set(&command.canonical_actuator_id, "joint.right.hip");
    CHECK(harness.run(command).code == rt::IngressCode::ACTUATOR_NOT_BOUND);

    command = Command();
    Set(&command.source_identity, "controller.secondary");
    CHECK(harness.run(command).code == rt::IngressCode::SOURCE_NOT_BOUND);

    command = Command();
    Set(&command.lease_owner, "controller.secondary");
    CHECK(harness.run(command).code == rt::IngressCode::LEASE_OWNER_MISMATCH);

    command = Command();
    Set(&command.config.identity, "synthetic-v44-node2");
    CHECK(harness.run(command).code == rt::IngressCode::CONFIG_MISMATCH);
    command = Command();
    Set(&command.config.revision, "2");
    CHECK(harness.run(command).code == rt::IngressCode::CONFIG_MISMATCH);
}

void TestClosedModeSurface() {
    const host::CommandMode unsupported[] = {
        host::CommandMode::DISABLE,
        host::CommandMode::POSITION,
        host::CommandMode::VELOCITY,
        host::CommandMode::EFFORT,
        host::CommandMode::IMPEDANCE,
    };
    for (size_t index = 0; index < sizeof(unsupported) / sizeof(unsupported[0]);
         ++index) {
        IngressHarness harness;
        CHECK(harness.run(Command(unsupported[index])).code ==
              rt::IngressCode::UNSUPPORTED_MODE);
    }
}

void TestCurrentAndDeadlineBoundaries() {
    IngressHarness harness;
    CHECK(harness.run(Command(host::CommandMode::CURRENT_Q, 0.0)).code ==
          rt::IngressCode::OK);
    harness = IngressHarness();
    CHECK(harness.run(Command(host::CommandMode::CURRENT_Q, -10.0)).code ==
          rt::IngressCode::OK);
    harness = IngressHarness();
    CHECK(harness.run(Command(host::CommandMode::CURRENT_Q, 10.0)).code ==
          rt::IngressCode::OK);
    harness = IngressHarness();
    CHECK(harness.run(Command(host::CommandMode::CURRENT_Q, 1.251)).code ==
          rt::IngressCode::CURRENT_NOT_ON_GRID);
    harness = IngressHarness();
    CHECK(harness.run(Command(host::CommandMode::CURRENT_Q, 10.01)).code ==
          rt::IngressCode::CURRENT_OUT_OF_RANGE);
    harness = IngressHarness();
    CHECK(harness.run(Command(host::CommandMode::CURRENT_Q, -10.01)).code ==
          rt::IngressCode::CURRENT_OUT_OF_RANGE);
    harness = IngressHarness();
    CHECK(harness.run(Command(host::CommandMode::CURRENT_Q, 1.25,
                              kDeadlineNs + 1U)).code ==
          rt::IngressCode::DEADLINE_NOT_MILLISECOND_ALIGNED);

    // Non-finite and missing current values are rejected by Host Link before
    // the translator can observe them.
    host::Command invalid = Command();
    invalid.current_q_a.value = std::numeric_limits<double>::infinity();
    host::Frame frame = {};
    CHECK(!FrameFor(invalid, &frame));
    invalid = Command();
    invalid.current_q_a.present = false;
    CHECK(!FrameFor(invalid, &frame));
}

void TestSessionAndEnvelopeDenials() {
    rt::HostCommandBinding binding = Binding();
    host::Frame frame = {};
    CHECK(FrameFor(Command(), &frame));
    rt::HostCommandIngress ingress(&binding, 1U, kSession, Digest(),
                                   Capabilities(), 2U, 0U);
    CHECK(ingress.valid());
    CHECK(ingress.receive(frame, kEvaluationTimeNs, NULL).code ==
          rt::IngressCode::NULL_OUTPUT);
    gw::Submission submission = {};
    CHECK(ingress.receive(frame, kEvaluationTimeNs, &submission).code ==
          rt::IngressCode::OK);
    CHECK(ingress.receive(frame, kEvaluationTimeNs, &submission).code ==
          rt::IngressCode::HOST_DENIED);

    const uint64_t large_session =
        static_cast<uint64_t>(std::numeric_limits<uint32_t>::max()) + 1U;
    CHECK(FrameFor(Command(), &frame, 3U, large_session));
    rt::HostCommandIngress large(&binding, 1U, large_session, Digest(),
                                 Capabilities(), 2U, 0U);
    CHECK(large.receive(frame, kEvaluationTimeNs, &submission).code ==
          rt::IngressCode::SESSION_ID_OUT_OF_RANGE);

    CHECK(FrameFor(Command(), &frame));
    rt::HostCommandIngress expired(&binding, 1U, kSession, Digest(),
                                   Capabilities(), 2U, 0U);
    CHECK(expired.receive(frame, kDeadlineNs, &submission).code ==
          rt::IngressCode::HOST_DENIED);
    CHECK(expired.receive(frame, kDeadlineNs, &submission).receive_denial ==
          host::ReceiveDenial::EXPIRED_COMMAND);

    host::TypedMessage heartbeat = {};
    heartbeat.type = host::MessageType::HEARTBEAT;
    Set(&heartbeat.heartbeat.endpoint_id, "host.primary");
    heartbeat.heartbeat.role = host::EndpointRole::HOST;
    heartbeat.heartbeat.link_health = host::LinkHealth::ACTIVE;
    heartbeat.heartbeat.safety_state = host::SafetyState::DISABLED;
    heartbeat.heartbeat.uptime_ns = kFrameTimeNs;
    heartbeat.heartbeat.last_received_sequence = 2U;
    host::Envelope envelope = {};
    envelope.session_id = kSession;
    envelope.sequence = 3U;
    envelope.monotonic_ns = kFrameTimeNs;
    envelope.config_sha256 = Digest();
    static uint8_t bytes[host::kMaxFrameSize];
    size_t size = 0U;
    CHECK(host::EncodeMessage(heartbeat, envelope, bytes, sizeof(bytes),
                              &size) == host::Status::OK);
    CHECK(host::DecodeFrame(bytes, size, &frame) == host::Status::OK);
    rt::HostCommandIngress not_command(&binding, 1U, kSession, Digest(),
                                       Capabilities(), 2U, 0U);
    CHECK(not_command.receive(frame, kEvaluationTimeNs, &submission).code ==
          rt::IngressCode::NOT_COMMAND);
}

safety::ConfigCandidate Candidate(const rt::HostCommandBinding& binding) {
    safety::ConfigCandidate value = {};
    value.identity = binding.safety_config.identity;
    value.generation = binding.safety_config.generation;
    value.validity_deadline_ms = 1000U;
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
    value.generation = 1U;
    value.bytes[0] = 0x5aU;
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

class CaptureTransport : public rt::NativeCanTransport {
public:
    CaptureTransport() : count(0U), bus(0U), frame() {}

    bool ready(uint8_t bus_id) const { return bus_id == 1U; }
    rt::SendResult tryTransmit(uint8_t bus_id, const v44::Frame& value) {
        ++count;
        bus = bus_id;
        frame = value;
        return rt::SendResult::SENT;
    }
    rt::ReceiveResult tryReceive(rt::ReceivedFrame* output) {
        (void)output;
        return rt::ReceiveResult::NO_DATA;
    }

    uint32_t count;
    uint8_t bus;
    v44::Frame frame;
};

void TestIntegratedBytePath() {
    rt::HostCommandBinding binding = Binding();
    host::Frame host_frame = {};
    CHECK(FrameFor(Command(), &host_frame));
    rt::HostCommandIngress ingress(&binding, 1U, kSession, Digest(),
                                   Capabilities(), 2U, 0U);
    gw::Submission submission = {};
    const rt::IngressResult accepted =
        ingress.receive(host_frame, kEvaluationTimeNs, &submission);
    CHECK(accepted.code == rt::IngressCode::OK);

    const safety::ConfigCandidate candidate = Candidate(binding);
    safety::ConfigIdentityGuard guard({1U, 1U});
    CHECK(guard.stageCandidate(0U, candidate, Expectation(candidate), Token()) ==
          safety::ConfigDecision::ALLOWED);
    CHECK(guard.commitStaged(0U, Token()) == safety::ConfigDecision::ALLOWED);
    safety::SafetySupervisor supervisor(safety::Configuration(
        static_cast<uint32_t>(kSession), 1U, 1000U, 20U, 1U, 1U));
    CHECK(supervisor.completeBoot(0U, Ready()) == safety::Result::OK);
    CHECK(supervisor.acquireLease(
              0U, safety::MessageStamp(1U, static_cast<uint32_t>(kSession), 1U),
              100U) == safety::Result::OK);
    CHECK(supervisor.enable(
              0U, safety::MessageStamp(1U, static_cast<uint32_t>(kSession), 2U))
          == safety::Result::OK);

    gw::Route route = {};
    route.token = binding.route_token;
    route.bus_id = binding.bus_id;
    route.node_id = binding.node_id;
    route.owner_id = binding.owner_id;
    route.allowed_opcode_count = 1U;
    route.allowed_opcodes[0] =
        static_cast<uint8_t>(v44::Command::kIqControl);
    route.safety_opcode = static_cast<uint8_t>(v44::Command::kShutdown);
    gw::GatewayCore core(&route, 1U, gw::Policy(20U, 1U, 2U), &guard,
                         &supervisor);
    CHECK(core.valid());
    CHECK(core.enqueue(accepted.evaluation_time_ms, submission) ==
          gw::Code::OK);
    CaptureTransport transport;
    rt::GatewayTransportRuntime runtime(
        &core, &supervisor, &transport, rt::ServicePolicy(2U, 2U));
    const rt::ServiceReport report =
        runtime.service(accepted.evaluation_time_ms, 1U);
    CHECK(report.code == rt::ServiceCode::OK);
    CHECK(report.tx_sent == 1U);
    CHECK(transport.count == 1U);
    CHECK(transport.bus == binding.bus_id);
    v44::DecodedRequest decoded = {};
    CHECK(v44::DecodeRequest(transport.frame, &decoded, binding.node_id,
                             static_cast<uint8_t>(v44::Command::kIqControl)) ==
          v44::Error::kOk);
    CHECK(decoded.iq_raw == 125);
    CHECK(core.outstandingResponseCount() == 1U);
}

}  // namespace

int main() {
    TestBindingValidation();
    TestExactPositiveTranslation();
    TestExactSelectionDenials();
    TestClosedModeSurface();
    TestCurrentAndDeadlineBoundaries();
    TestSessionAndEnvelopeDenials();
    TestIntegratedBytePath();
    if (failures != 0) {
        fprintf(stderr, "host command ingress failures=%d\n", failures);
        return 1;
    }
    printf("HOST_COMMAND_INGRESS_OK\n");
    return 0;
}
