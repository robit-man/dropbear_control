#include "config_identity_guard.h"
#include "dropbear_config.generated.hpp"
#include "gateway_core.h"
#include "host_command_ingress.h"
#include "hostlink_v1.h"
#include "rmd_v44_codec.h"
#include "safety_supervisor.h"

#include <stdint.h>

#include <cmath>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

namespace generated = myactuator::generated::dropbear;
namespace gateway = myactuator::gateway;
namespace hostlink = myactuator::hostlink_v1;
namespace runtime = myactuator::runtime;
namespace safety = myactuator::safety;
namespace v44 = myactuator::rmd_v44;

namespace {

struct ParseCapture {
    size_t frames;
    size_t errors;
    hostlink::Frame frame;
};

void CaptureFrame(void* context, const hostlink::Frame& frame) {
    ParseCapture* capture = static_cast<ParseCapture*>(context);
    ++capture->frames;
    capture->frame = frame;
}

void CaptureError(void* context, const hostlink::ParseErrorEvent&) {
    ParseCapture* capture = static_cast<ParseCapture*>(context);
    ++capture->errors;
}

int HexNibble(char value) {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10;
    return -1;
}

bool ParseHex(const std::string& value, std::vector<uint8_t>* output) {
    if (output == NULL || value.size() % 2U != 0U) return false;
    output->clear();
    output->reserve(value.size() / 2U);
    for (size_t index = 0; index < value.size(); index += 2U) {
        const int high = HexNibble(value[index]);
        const int low = HexNibble(value[index + 1U]);
        if (high < 0 || low < 0) return false;
        output->push_back(static_cast<uint8_t>((high << 4) | low));
    }
    return true;
}

std::string Hex(const uint8_t* data, size_t size) {
    static const char digits[] = "0123456789abcdef";
    std::string result;
    result.reserve(size * 2U);
    for (size_t index = 0; index < size; ++index) {
        result.push_back(digits[(data[index] >> 4U) & 0x0fU]);
        result.push_back(digits[data[index] & 0x0fU]);
    }
    return result;
}

bool ParseRevision(const hostlink::Text& text, uint64_t* output) {
    if (output == NULL || text.size == 0U) return false;
    uint64_t value = 0U;
    for (size_t index = 0; index < text.size; ++index) {
        const uint8_t digit = text.bytes[index];
        if (digit < '0' || digit > '9') return false;
        if (value > (UINT64_MAX - static_cast<uint64_t>(digit - '0')) / 10U) {
            return false;
        }
        value = value * 10U + static_cast<uint64_t>(digit - '0');
    }
    if (value == 0U) return false;
    *output = value;
    return true;
}

bool ToGuardIdentity(const hostlink::ConfigIdentity& source,
                     safety::ConfigIdentity* output) {
    if (output == NULL || source.identity.size == 0U ||
        source.identity.size > safety::kConfigIdCapacity) {
        return false;
    }
    std::memset(output, 0, sizeof(*output));
    output->config_id.length = static_cast<uint8_t>(source.identity.size);
    std::memcpy(output->config_id.bytes, source.identity.bytes,
                source.identity.size);
    std::memcpy(output->digest.bytes, source.sha256.bytes,
                safety::kSha256DigestSize);
    if (!ParseRevision(source.revision, &output->revision)) return false;
    output->schema_version = 1U;
    return true;
}

hostlink::Capabilities AcceptedCapabilities() {
    hostlink::Capabilities result = {};
    result.accepted = true;
    result.selected_major = hostlink::kVersionMajor;
    result.selected_minor = hostlink::kVersionMinor;
    result.selected_capabilities = hostlink::kMandatoryCapabilities;
    result.selected_rate_hz = 500U;
    result.selected_payload_size = hostlink::kMaxPayloadSize;
    result.rejection = hostlink::NegotiationRejection::NONE;
    return result;
}

bool DecodeLinkCommand(const std::string& frame_hex,
                       hostlink::Frame* frame,
                       hostlink::TypedMessage* message) {
    std::vector<uint8_t> bytes;
    if (!ParseHex(frame_hex, &bytes)) return false;

    // Static ownership mirrors the embedded placement guidance. The parser,
    // frame and typed message are deliberately not co-located on a task stack.
    static hostlink::StreamParser parser;
    static ParseCapture capture;
    parser.reset();
    std::memset(&capture, 0, sizeof(capture));
    size_t offset = 0U;
    while (offset < bytes.size()) {
        size_t chunk = 1U + (offset % 17U);
        if (chunk > bytes.size() - offset) chunk = bytes.size() - offset;
        hostlink::ParseBatch batch = {};
        if (parser.feed(bytes.data() + offset, chunk, CaptureFrame,
                        CaptureError, &capture, &batch) !=
            hostlink::Status::OK) {
            return false;
        }
        offset += chunk;
    }
    if (capture.frames != 1U || capture.errors != 0U ||
        capture.frame.message_type != hostlink::MessageType::COMMAND) {
        return false;
    }

    hostlink::SessionReceiver receiver;
    if (receiver.initialize(capture.frame.session_id,
                            capture.frame.config_sha256,
                            AcceptedCapabilities(), 2U, 0U) !=
        hostlink::Status::OK) {
        return false;
    }
    const hostlink::ReceiveResult received = receiver.receive(
        capture.frame, capture.frame.monotonic_ns, true, message);
    if (!received.link_accepted || received.motion_authorized ||
        received.denial != hostlink::ReceiveDenial::NONE) {
        return false;
    }
    *frame = capture.frame;
    return true;
}

safety::ConfigExpectation Expectation(
    const safety::ConfigCandidate& candidate) {
    safety::ConfigExpectation result = {};
    result.identity = candidate.identity;
    result.generation = candidate.generation;
    return result;
}

safety::GenerationCommitToken Token(uint64_t generation) {
    safety::GenerationCommitToken result = {};
    result.generation = generation;
    result.bytes[0] = 0x5aU;
    return result;
}

safety::Prerequisites ReadyPrerequisites() {
    safety::Prerequisites result;
    result.configuration_valid = true;
    result.expected_nodes_present = true;
    result.transport_ready = true;
    result.safety_interlock_ready = true;
    result.external_faults_clear = true;
    result.motor_off_confirmed = true;
    return result;
}

gateway::Route SyntheticRoute() {
    gateway::Route result = {};
    result.token = 1U;
    result.bus_id = 1U;
    result.node_id = 1U;
    result.owner_id = 1U;
    result.allowed_opcode_count = 1U;
    result.allowed_opcodes[0] =
        static_cast<uint8_t>(v44::Command::kIqControl);
    result.safety_opcode = static_cast<uint8_t>(v44::Command::kShutdown);
    return result;
}

runtime::HostCommandBinding SyntheticBinding(
    const hostlink::Sha256& config_sha256) {
    runtime::HostCommandBinding result = {};
    const char* actuator = "synthetic-actuator-node1";
    const char* source = "synthetic-controller";
    const char* config_id = "synthetic-v44-node1";
    hostlink::SetText(&result.canonical_actuator_id, actuator,
                      std::strlen(actuator));
    hostlink::SetText(&result.source_identity, source, std::strlen(source));
    hostlink::SetText(&result.lease_owner, source, std::strlen(source));
    hostlink::SetText(&result.host_config.identity, config_id,
                      std::strlen(config_id));
    hostlink::SetText(&result.host_config.revision, "1", 1U);
    result.host_config.sha256 = config_sha256;
    result.safety_config.identity.config_id.length =
        static_cast<uint8_t>(std::strlen(config_id));
    std::memcpy(result.safety_config.identity.config_id.bytes, config_id,
                std::strlen(config_id));
    std::memcpy(result.safety_config.identity.digest.bytes,
                config_sha256.bytes, safety::kSha256DigestSize);
    result.safety_config.identity.revision = 1U;
    result.safety_config.identity.schema_version = 1U;
    result.safety_config.generation = 1U;
    result.safety_config.authorization_class =
        safety::AuthorizationClass::MOTION;
    const gateway::Route route = SyntheticRoute();
    result.route_token = route.token;
    result.bus_id = route.bus_id;
    result.node_id = route.node_id;
    result.owner_id = route.owner_id;
    result.translation = runtime::TranslationKind::RMD_V44_IQ_CURRENT_A;
    result.iq_amperes_per_lsb_numerator =
        runtime::kRmdV44IqAmperesPerLsbNumerator;
    result.iq_amperes_per_lsb_denominator =
        runtime::kRmdV44IqAmperesPerLsbDenominator;
    result.minimum_iq_raw = INT16_MIN;
    result.maximum_iq_raw = INT16_MAX;
    return result;
}

void PrintPhaseCounts(const gateway::GatewayCore& core) {
    size_t counts[6] = {};
    for (size_t index = 0; index < core.dispositionCount(); ++index) {
        gateway::Disposition event = {};
        if (core.dispositionAt(index, &event)) {
            ++counts[static_cast<size_t>(event.phase)];
        }
    }
    std::cout << " received=" << counts[0]
              << " admitted=" << counts[1]
              << " native_tx=" << counts[2]
              << " native_response=" << counts[3]
              << " observed=" << counts[4]
              << " rejected=" << counts[5]
              << " outstanding=" << core.outstandingResponseCount();
}

int RunTracked(const std::string& frame_hex) {
    static hostlink::Frame frame;
    static hostlink::TypedMessage message;
    if (!DecodeLinkCommand(frame_hex, &frame, &message)) return 10;

    safety::ConfigIdentity identity = {};
    if (!ToGuardIdentity(message.command.config, &identity)) return 11;
    if (!hostlink::TextEquals(message.command.config.identity,
                              generated::kConfigurationId.data())) {
        return 12;
    }
    safety::ConfigCandidate candidate = {};
    candidate.identity = identity;
    candidate.generation = 1U;
    candidate.validity_deadline_ms = 1000U;
    candidate.structural_validated = true;
    candidate.semantic_validated = true;
    candidate.motion_allowed = generated::kMotionEnableAllowed;
    candidate.authorization_class = safety::AuthorizationClass::OBSERVE_ONLY;

    safety::ConfigIdentityGuard guard({1U, 1U});
    const safety::ConfigDecision decision = guard.stageCandidate(
        0U, candidate, Expectation(candidate), Token(candidate.generation));
    bool any_native_node = false;
    for (const generated::ActuatorObservation& actuator :
         generated::kActuators) {
        any_native_node = any_native_node || actuator.native_node_id.has_value;
    }
    std::cout << "TRACKED link=1 motion_allowed="
              << (generated::kMotionEnableAllowed ? 1 : 0)
              << " config=" << safety::DecisionCode(decision)
              << " native_node_bound=" << (any_native_node ? 1 : 0)
              << " native_tx=0" << std::endl;
    return decision == safety::ConfigDecision::MOTION_NOT_ALLOWED &&
                   !guard.snapshot().active_present && !any_native_node
               ? 0
               : 13;
}

int RunPositive(const std::string& frame_hex) {
    static hostlink::Frame link_frame;
    static hostlink::TypedMessage parsed_message;
    if (!DecodeLinkCommand(frame_hex, &link_frame, &parsed_message)) return 20;
    // The production ingress repeats session acceptance here and owns all
    // host-command-to-native conversion policy. This synthetic binding is not
    // a Dropbear or catalog applicability tuple.
    const runtime::HostCommandBinding binding =
        SyntheticBinding(link_frame.config_sha256);
    runtime::HostCommandIngress ingress(
        &binding, 1U, link_frame.session_id, link_frame.config_sha256,
        AcceptedCapabilities(), 2U, 0U);
    if (!ingress.valid()) return 21;
    gateway::Submission submission = {};
    const runtime::IngressResult ingress_result = ingress.receive(
        link_frame, link_frame.monotonic_ns, &submission);
    if (ingress_result.code != runtime::IngressCode::OK) return 22;

    safety::ConfigCandidate candidate = {};
    candidate.identity = binding.safety_config.identity;
    candidate.generation = binding.safety_config.generation;
    candidate.validity_deadline_ms = 1000U;
    candidate.structural_validated = true;
    candidate.semantic_validated = true;
    candidate.motion_allowed = true;
    candidate.authorization_class = safety::AuthorizationClass::MOTION;
    safety::ConfigIdentityGuard guard({1U, 1U});
    const safety::GenerationCommitToken token = Token(candidate.generation);
    if (guard.stageCandidate(0U, candidate, Expectation(candidate), token) !=
            safety::ConfigDecision::ALLOWED ||
        guard.commitStaged(0U, token) != safety::ConfigDecision::ALLOWED) {
        return 23;
    }

    const uint32_t session_id = submission.safety_session_id;
    safety::SafetySupervisor supervisor(
        safety::Configuration(session_id, 1U, 200U, 20U, 1U, 1U));
    if (supervisor.completeBoot(0U, ReadyPrerequisites()) !=
            safety::Result::OK ||
        supervisor.acquireLease(
            0U, safety::MessageStamp(1U, session_id, 1U), 100U) !=
            safety::Result::OK ||
        supervisor.enable(0U,
                          safety::MessageStamp(1U, session_id, 2U)) !=
            safety::Result::OK) {
        return 25;
    }

    const gateway::Route route = SyntheticRoute();
    gateway::GatewayCore core(&route, 1U, gateway::Policy(20U, 1U, 2U),
                              &guard, &supervisor);
    if (!core.valid() || core.beginCycle(1U) != gateway::Code::OK) return 28;

    if (core.enqueue(ingress_result.evaluation_time_ms, submission) !=
        gateway::Code::OK) return 29;

    gateway::TxEnvelope transmitted = {};
    if (core.pollTransmit(ingress_result.evaluation_time_ms, &transmitted) !=
        gateway::PollResult::FRAME_READY) {
        return 30;
    }
    std::cout << "TX transaction=" << transmitted.transaction_id
              << " bus=" << static_cast<unsigned>(transmitted.bus_id)
              << " arbitration=" << transmitted.frame.arbitration_id
              << " data=" << Hex(transmitted.frame.data, 8U)
              << std::endl;

    std::string action;
    if (!(std::cin >> action)) return 31;
    if (action == "RX") {
        uint64_t at_ms = 0U;
        unsigned bus_id = 0U;
        unsigned arbitration_id = 0U;
        std::string data_hex;
        if (!(std::cin >> at_ms >> bus_id >> arbitration_id >> data_hex)) {
            return 32;
        }
        std::vector<uint8_t> response_bytes;
        if (!ParseHex(data_hex, &response_bytes) ||
            response_bytes.size() != 8U || bus_id > UINT8_MAX ||
            arbitration_id > UINT16_MAX) {
            return 33;
        }
        v44::Frame response = {};
        response.arbitration_id = static_cast<uint16_t>(arbitration_id);
        response.dlc = 8U;
        std::memcpy(response.data, response_bytes.data(), 8U);
        const gateway::Code response_code = core.acceptResponse(
            at_ms, static_cast<uint8_t>(bus_id), response);
        gateway::Code observation_code = gateway::Code::TRANSACTION_NOT_FOUND;
        if (response_code == gateway::Code::OK) {
            observation_code = core.recordObservation(
                at_ms + 1U, transmitted.transaction_id,
                gateway::ObservationClass::NATIVE_STATE_SAMPLE);
        }
        std::cout << "RESULT response=" << gateway::CodeName(response_code)
                  << " observation="
                  << gateway::CodeName(observation_code);
        PrintPhaseCounts(core);
        std::cout << std::endl;
        return 0;
    }
    if (action == "EXPIRE") {
        uint64_t at_ms = 0U;
        if (!(std::cin >> at_ms)) return 34;
        const size_t expired = core.expireResponses(at_ms);
        std::cout << "RESULT expire=" << expired;
        PrintPhaseCounts(core);
        std::cout << std::endl;
        return 0;
    }
    return 35;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    std::string label;
    std::string frame_hex;
    if (!(std::cin >> label >> frame_hex) || label != "FRAME") return 3;
    const std::string mode(argv[1]);
    if (mode == "tracked") return RunTracked(frame_hex);
    if (mode == "positive") return RunPositive(frame_hex);
    return 4;
}
