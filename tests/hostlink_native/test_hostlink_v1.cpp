#include "hostlink_v1.h"

#include <stdint.h>

#include <cmath>
#include <cstdio>
#include <cstring>
#include <iostream>

namespace hl = myactuator::hostlink_v1;

namespace {

int checks = 0;
int failures = 0;

#define CHECK(condition)                                                        \
    do {                                                                        \
        ++checks;                                                               \
        if (!(condition)) {                                                     \
            ++failures;                                                         \
            std::cerr << "FAIL " << __FILE__ << ':' << __LINE__ << ": "       \
                      << #condition << '\n';                                   \
        }                                                                       \
    } while (false)

const uint64_t kSession = 0x1020304050607080ULL;
const uint64_t kNow = 9000000000ULL;

struct Vector {
    char outcome[24];
    char type[24];
    size_t size;
    uint8_t data[hl::kMaxFrameSize + 1];
};

int HexDigit(char value) {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10;
    return -1;
}

bool CopyField(char* output, size_t capacity, const char* begin,
               const char* end) {
    const size_t size = static_cast<size_t>(end - begin);
    if (size >= capacity) return false;
    std::memcpy(output, begin, size);
    output[size] = '\0';
    return true;
}

bool ParseVectorLine(char* line, const char* wanted_name, Vector* output) {
    char* first = std::strchr(line, '\t');
    if (first == 0) return false;
    if (std::strlen(wanted_name) != static_cast<size_t>(first - line) ||
        std::memcmp(line, wanted_name, first - line) != 0)
        return false;
    char* second = std::strchr(first + 1, '\t');
    char* third = second == 0 ? 0 : std::strchr(second + 1, '\t');
    if (second == 0 || third == 0) return false;
    char* end = std::strchr(third + 1, '\n');
    if (end == 0) end = third + 1 + std::strlen(third + 1);
    if (!CopyField(output->outcome, sizeof(output->outcome), first + 1,
                   second) ||
        !CopyField(output->type, sizeof(output->type), second + 1, third))
        return false;
    const size_t hex_size = static_cast<size_t>(end - (third + 1));
    if ((hex_size & 1U) != 0 || hex_size / 2 > sizeof(output->data))
        return false;
    output->size = hex_size / 2;
    for (size_t index = 0; index < output->size; ++index) {
        const int high = HexDigit(third[1 + index * 2]);
        const int low = HexDigit(third[2 + index * 2]);
        if (high < 0 || low < 0) return false;
        output->data[index] = static_cast<uint8_t>((high << 4) | low);
    }
    return true;
}

bool LoadVector(const char* path, const char* name, Vector* output) {
    std::FILE* stream = std::fopen(path, "rb");
    if (stream == 0) return false;
    char line[10000];
    bool found = false;
    while (std::fgets(line, sizeof(line), stream) != 0) {
        if (ParseVectorLine(line, name, output)) {
            found = true;
            break;
        }
    }
    std::fclose(stream);
    return found;
}

void Set(hl::Text* output, const char* value, bool exact = true) {
    CHECK(hl::SetText(output, value, std::strlen(value), false, exact) ==
          hl::Status::OK);
}

void SetOptional(hl::Text* output, const char* value) {
    CHECK(hl::SetText(output, value, std::strlen(value), true,
                      value[0] != '\0') == hl::Status::OK);
}

void SetDetail(hl::DetailText* output, const char* value) {
    CHECK(hl::SetDetailText(output, value, std::strlen(value), true) ==
          hl::Status::OK);
}

hl::Sha256 Hash(uint8_t value) {
    hl::Sha256 result = {};
    std::memset(result.bytes, value, sizeof(result.bytes));
    return result;
}

hl::ConfigIdentity Config() {
    hl::ConfigIdentity config = {};
    Set(&config.identity, "dropbear-main");
    Set(&config.revision, "robot-rev-2026-07");
    config.sha256 = Hash(0x11);
    return config;
}

hl::Envelope Envelope(uint64_t sequence, bool zero_hash = false,
                      uint8_t flags = 0) {
    hl::Envelope result = {};
    result.flags = flags;
    result.session_id = kSession;
    result.sequence = sequence;
    result.monotonic_ns = kNow;
    result.config_sha256 = Hash(zero_hash ? 0 : 0x11);
    return result;
}

hl::Hello Hello() {
    hl::Hello body = {};
    Set(&body.endpoint_id, "dropbear-host");
    body.role = hl::EndpointRole::HOST;
    body.supported_major = 1;
    body.minimum_minor = 0;
    body.maximum_minor = 0;
    body.required_capabilities = hl::kMandatoryCapabilities;
    body.offered_capabilities = hl::kMandatoryCapabilities;
    body.minimum_rate_hz = 50;
    body.maximum_rate_hz = 1000;
    body.preferred_rate_hz = 500;
    body.maximum_payload_size = hl::kMaxPayloadSize;
    return body;
}

hl::Capabilities Capabilities() {
    hl::Capabilities body = {};
    body.accepted = true;
    body.selected_major = 1;
    body.selected_minor = 0;
    body.selected_capabilities = hl::kMandatoryCapabilities;
    body.selected_rate_hz = 500;
    body.selected_payload_size = hl::kMaxPayloadSize;
    body.rejection = hl::NegotiationRejection::NONE;
    return body;
}

hl::Command Command(hl::CommandMode mode = hl::CommandMode::IMPEDANCE) {
    hl::Command body = {};
    Set(&body.canonical_actuator_id, "left-knee-actuator");
    body.config = Config();
    Set(&body.source_identity, "controller-main");
    Set(&body.lease_id, "locomotion-lease-7");
    Set(&body.lease_owner, "controller-main");
    body.lease_sequence = 41;
    body.lease_expiry_monotonic_ns = kNow + 2000000000ULL;
    body.mode = mode;
    body.enable_requested = mode != hl::CommandMode::DISABLE;
    switch (mode) {
        case hl::CommandMode::DISABLE:
            break;
        case hl::CommandMode::POSITION:
            body.position_rad = {true, 0.2};
            break;
        case hl::CommandMode::VELOCITY:
            body.velocity_rad_s = {true, -0.1};
            break;
        case hl::CommandMode::EFFORT:
            body.effort_nm = {true, 0.15};
            break;
        case hl::CommandMode::CURRENT_Q:
            body.current_q_a = {true, -0.4};
            break;
        case hl::CommandMode::IMPEDANCE:
            body.position_rad = {true, 0.2};
            body.velocity_rad_s = {true, -0.1};
            body.effort_nm = {true, 0.15};
            body.stiffness_nm_per_rad = {true, 22.0};
            body.damping_nm_s_per_rad = {true, 0.8};
            break;
    }
    return body;
}

hl::State State() {
    hl::State body = {};
    Set(&body.canonical_actuator_id, "left-knee-actuator");
    body.config = Config();
    body.sample_monotonic_ns = kNow - 2000000;
    body.sample_age_ns = 2000000;
    body.validity = hl::SampleValidity::STALE;
    body.connectivity = hl::Connectivity::DEGRADED;
    body.drive_health = hl::DriveHealth::WARNING;
    body.bus_health = hl::BusHealth::RECOVERING;
    body.native_response = hl::NativeResponseState::DRIVE_FAULT;
    Set(&body.fault_code, "DRIVE_WARNING");
    body.safety_state = hl::SafetyState::SHUTDOWN;
    body.position_rad = {true, 0.4};
    body.velocity_rad_s = {true, -0.2};
    body.effort_nm = {true, 1.2};
    body.current_q_a = {true, 0.3};
    body.temperature_c = {true, 38.5};
    body.voltage_v = {true, 47.8};
    body.native_status_code = {true, 0x1234};
    body.native_fault_mask = {true, 0x1004};
    return body;
}

hl::Disposition Disposition() {
    hl::Disposition body = {};
    body.request_session_id = kSession;
    body.request_sequence = 3;
    Set(&body.canonical_actuator_id, "left-knee-actuator");
    body.phase = hl::DispositionPhase::REJECTED;
    body.phase_monotonic_ns = kNow;
    Set(&body.reason_code, "CONFIG_MISMATCH");
    return body;
}

hl::Fault Fault() {
    hl::Fault body = {};
    Set(&body.fault_code, "BUS_OFF");
    body.severity = hl::FaultSeverity::LATCHED;
    body.safety_state = hl::SafetyState::FAULT;
    body.occurred_monotonic_ns = kNow - 1;
    body.related_sequence = 3;
    SetOptional(&body.canonical_actuator_id, "left-knee-actuator");
    SetDetail(&body.description,
              "CAN controller entered bus-off; no physical-state claim");
    return body;
}

hl::Heartbeat Heartbeat() {
    hl::Heartbeat body = {};
    Set(&body.endpoint_id, "gateway-main");
    body.role = hl::EndpointRole::GATEWAY;
    body.link_health = hl::LinkHealth::DEGRADED;
    body.safety_state = hl::SafetyState::SHUTDOWN;
    body.uptime_ns = 99000;
    body.last_received_sequence = 42;
    return body;
}

hl::TypedMessage Message(hl::MessageType type) {
    hl::TypedMessage message = {};
    message.type = type;
    switch (type) {
        case hl::MessageType::HELLO: message.hello = Hello(); break;
        case hl::MessageType::CAPABILITIES:
            message.capabilities = Capabilities();
            break;
        case hl::MessageType::COMMAND: message.command = Command(); break;
        case hl::MessageType::STATE: message.state = State(); break;
        case hl::MessageType::DISPOSITION:
            message.disposition = Disposition();
            break;
        case hl::MessageType::FAULT: message.fault = Fault(); break;
        case hl::MessageType::HEARTBEAT: message.heartbeat = Heartbeat(); break;
    }
    return message;
}

void CheckEncoded(const char* corpus, const char* name,
                  const hl::TypedMessage& message, const hl::Envelope& envelope) {
    Vector expected = {};
    CHECK(LoadVector(corpus, name, &expected));
    uint8_t encoded[hl::kMaxFrameSize];
    size_t encoded_size = 0;
    CHECK(hl::EncodeMessage(message, envelope, encoded, sizeof(encoded),
                            &encoded_size) == hl::Status::OK);
    CHECK(encoded_size == expected.size);
    CHECK(encoded_size == expected.size &&
          std::memcmp(encoded, expected.data, expected.size) == 0);
}

void TestConstantsCrcAndGoldenEncode(const char* corpus) {
    CHECK(hl::kHeaderSize == 72);
    CHECK(hl::kMaxPayloadSize == 4096);
    CHECK(hl::kMaxFrameSize == 4172);
    CHECK(hl::kMaxBufferSize == 8344);
    CHECK(hl::Crc32c(reinterpret_cast<const uint8_t*>("123456789"), 9) ==
          0xE3069283UL);
    CHECK(hl::Crc32c(0, 0) == 0);

    CheckEncoded(corpus, "hello", Message(hl::MessageType::HELLO),
                 Envelope(1, true));
    CheckEncoded(corpus, "capabilities", Message(hl::MessageType::CAPABILITIES),
                 Envelope(2, true));
    CheckEncoded(corpus, "command", Message(hl::MessageType::COMMAND),
                 Envelope(3));
    CheckEncoded(corpus, "state_health", Message(hl::MessageType::STATE),
                 Envelope(4));
    CheckEncoded(corpus, "disposition", Message(hl::MessageType::DISPOSITION),
                 Envelope(5));
    CheckEncoded(corpus, "fault", Message(hl::MessageType::FAULT), Envelope(6));
    CheckEncoded(corpus, "heartbeat", Message(hl::MessageType::HEARTBEAT),
                 Envelope(7, false,
                          hl::FRAME_FLAG_RESPONSE |
                              hl::FRAME_FLAG_URGENT_SAFETY));

    hl::TypedMessage max_text = Message(hl::MessageType::HELLO);
    char endpoint[hl::kMaxTextBytes];
    std::memset(endpoint, 'e', sizeof(endpoint));
    CHECK(hl::SetText(&max_text.hello.endpoint_id, endpoint, sizeof(endpoint)) ==
          hl::Status::OK);
    CheckEncoded(corpus, "boundary_max_text", max_text, Envelope(8, true));

    hl::TypedMessage max_detail = Message(hl::MessageType::FAULT);
    char detail[hl::kMaxDetailBytes];
    std::memset(detail, 'd', sizeof(detail));
    CHECK(hl::SetDetailText(&max_detail.fault.description, detail,
                            sizeof(detail)) == hl::Status::OK);
    CheckEncoded(corpus, "boundary_max_detail", max_detail, Envelope(9));

    hl::TypedMessage disable = Message(hl::MessageType::COMMAND);
    disable.command = Command(hl::CommandMode::DISABLE);
    Set(&disable.command.lease_id, "disable-lease-8");
    disable.command.lease_sequence = 42;
    disable.command.lease_expiry_monotonic_ns = kNow + 1;
    CheckEncoded(corpus, "boundary_disable_command", disable, Envelope(10));
}

void TestWholeGoldenCorpus(const char* corpus) {
    std::FILE* stream = std::fopen(corpus, "rb");
    CHECK(stream != 0);
    if (stream == 0) return;
    char line[10000];
    CHECK(std::fgets(line, sizeof(line), stream) != 0);  // header
    size_t vectors = 0;
    size_t accepted = 0;
    size_t rejected_frame = 0;
    size_t rejected_body = 0;
    uint8_t observed_types = 0;
    while (std::fgets(line, sizeof(line), stream) != 0) {
        char* tab = std::strchr(line, '\t');
        if (tab == 0) continue;
        char name[128] = {};
        CHECK(CopyField(name, sizeof(name), line, tab));
        Vector vector = {};
        CHECK(ParseVectorLine(line, name, &vector));
        ++vectors;
        hl::Frame frame = {};
        const hl::Status frame_status =
            hl::DecodeFrame(vector.data, vector.size, &frame);
        if (std::strcmp(vector.outcome, "reject_frame") == 0) {
            ++rejected_frame;
            CHECK(frame_status != hl::Status::OK);
            continue;
        }
        CHECK(frame_status == hl::Status::OK);
        if (frame_status != hl::Status::OK) continue;
        hl::TypedMessage message = {};
        const hl::Status body_status = hl::DecodeMessage(frame, &message);
        if (std::strcmp(vector.outcome, "reject_body") == 0) {
            ++rejected_body;
            CHECK(body_status != hl::Status::OK);
            continue;
        }
        ++accepted;
        CHECK(body_status == hl::Status::OK);
        observed_types |= static_cast<uint8_t>(
            1U << (static_cast<uint8_t>(frame.message_type) - 1));
        uint8_t roundtrip[hl::kMaxFrameSize];
        size_t roundtrip_size = 0;
        CHECK(hl::EncodeFrame(frame, roundtrip, sizeof(roundtrip),
                              &roundtrip_size) == hl::Status::OK);
        CHECK(roundtrip_size == vector.size);
        CHECK(roundtrip_size == vector.size &&
              std::memcmp(roundtrip, vector.data, vector.size) == 0);
    }
    std::fclose(stream);
    CHECK(vectors == 32);
    CHECK(accepted == 10);
    CHECK(rejected_frame == 11);
    CHECK(rejected_body == 11);
    CHECK(observed_types == 0x7F);
}

void TestAllCommandModesAndPresenceRules() {
    for (uint8_t raw = 0; raw <= 5; ++raw) {
        hl::TypedMessage message = {};
        message.type = hl::MessageType::COMMAND;
        message.command = Command(static_cast<hl::CommandMode>(raw));
        uint8_t encoded[hl::kMaxFrameSize];
        size_t size = 0;
        CHECK(hl::EncodeMessage(message, Envelope(raw + 1), encoded,
                                sizeof(encoded), &size) == hl::Status::OK);
        hl::Frame frame = {};
        hl::TypedMessage decoded = {};
        CHECK(hl::DecodeFrame(encoded, size, &frame) == hl::Status::OK);
        CHECK(hl::DecodeMessage(frame, &decoded) == hl::Status::OK);
        CHECK(decoded.command.mode == static_cast<hl::CommandMode>(raw));
        CHECK(hl::TextEquals(decoded.command.source_identity,
                             "controller-main"));
    }

    hl::TypedMessage invalid = {};
    invalid.type = hl::MessageType::COMMAND;
    invalid.command = Command(hl::CommandMode::POSITION);
    invalid.command.position_rad.present = false;
    uint8_t encoded[hl::kMaxFrameSize];
    size_t size = 0;
    CHECK(hl::EncodeMessage(invalid, Envelope(1), encoded, sizeof(encoded),
                            &size) == hl::Status::MODE_PRESENCE_MISMATCH);
    invalid.command = Command(hl::CommandMode::DISABLE);
    invalid.command.effort_nm = {true, 0.0};
    CHECK(hl::EncodeMessage(invalid, Envelope(1), encoded, sizeof(encoded),
                            &size) == hl::Status::MODE_PRESENCE_MISMATCH);
    invalid.command = Command(hl::CommandMode::EFFORT);
    invalid.command.enable_requested = false;
    CHECK(hl::EncodeMessage(invalid, Envelope(1), encoded, sizeof(encoded),
                            &size) == hl::Status::ENABLE_MODE_MISMATCH);
    invalid.command = Command(hl::CommandMode::CURRENT_Q);
    invalid.command.current_q_a.value = std::nan("");
    CHECK(hl::EncodeMessage(invalid, Envelope(1), encoded, sizeof(encoded),
                            &size) == hl::Status::NONFINITE_VALUE);
    invalid.command.current_q_a.value = INFINITY;
    CHECK(hl::EncodeMessage(invalid, Envelope(1), encoded, sizeof(encoded),
                            &size) == hl::Status::NONFINITE_VALUE);

    hl::TypedMessage valid = Message(hl::MessageType::COMMAND);
    CHECK(hl::EncodeMessage(valid, Envelope(1), encoded, sizeof(encoded), &size) ==
          hl::Status::OK);
    hl::Frame frame = {};
    CHECK(hl::DecodeFrame(encoded, size, &frame) == hl::Status::OK);
    frame.payload[frame.payload_size - 42] = 0x80;
    hl::TypedMessage decoded = {};
    CHECK(hl::DecodeMessage(frame, &decoded) ==
          hl::Status::UNKNOWN_FIELD_MASK);
    frame.payload_size = hl::kMaxPayloadSize + 1;
    CHECK(hl::DecodeMessage(frame, &decoded) == hl::Status::PAYLOAD_LIMIT);
}

void TestTextEnvelopeAndCrossEnvelopeValidation() {
    hl::Text text = {};
    CHECK(hl::SetText(&text, "unknown", 7) == hl::Status::NONEXACT_TEXT);
    CHECK(hl::SetText(&text, "left-*-actuator", 15) ==
          hl::Status::NONEXACT_TEXT);
    CHECK(hl::SetText(&text, " endpoint", 9) == hl::Status::NONEXACT_TEXT);
    const char control[] = {'a', '\n'};
    CHECK(hl::SetText(&text, control, sizeof(control)) ==
          hl::Status::INVALID_TEXT);
    const char invalid_utf8[] = {static_cast<char>(0xC0),
                                 static_cast<char>(0x80)};
    CHECK(hl::SetText(&text, invalid_utf8, sizeof(invalid_utf8)) ==
          hl::Status::INVALID_TEXT);

    hl::TypedMessage command = Message(hl::MessageType::COMMAND);
    uint8_t encoded[hl::kMaxFrameSize];
    size_t size = 0;
    hl::Envelope wrong_hash = Envelope(1);
    wrong_hash.config_sha256 = Hash(0x22);
    CHECK(hl::EncodeMessage(command, wrong_hash, encoded, sizeof(encoded),
                            &size) == hl::Status::CONFIG_MISMATCH);
    hl::Envelope expired = Envelope(1);
    command.command.lease_expiry_monotonic_ns = kNow;
    CHECK(hl::EncodeMessage(command, expired, encoded, sizeof(encoded), &size) ==
          hl::Status::EXPIRED_COMMAND);

    hl::TypedMessage state = Message(hl::MessageType::STATE);
    state.state.sample_age_ns = 1;
    CHECK(hl::EncodeMessage(state, Envelope(1), encoded, sizeof(encoded), &size) ==
          hl::Status::CROSS_ENVELOPE_MISMATCH);
    state = Message(hl::MessageType::STATE);
    state.state.drive_health = static_cast<hl::DriveHealth>(255);
    CHECK(hl::EncodeMessage(state, Envelope(1), encoded, sizeof(encoded), &size) ==
          hl::Status::INVALID_ENUM);
    state = Message(hl::MessageType::STATE);
    state.state.bus_health = static_cast<hl::BusHealth>(255);
    CHECK(hl::EncodeMessage(state, Envelope(1), encoded, sizeof(encoded), &size) ==
          hl::Status::INVALID_ENUM);

    hl::TypedMessage disposition = Message(hl::MessageType::DISPOSITION);
    disposition.disposition.phase = hl::DispositionPhase::ADMITTED;
    CHECK(hl::EncodeMessage(disposition, Envelope(1), encoded, sizeof(encoded),
                            &size) == hl::Status::CROSS_ENVELOPE_MISMATCH);
}

void TestNegotiationAndPublishedCeilings() {
    hl::Hello local = Hello();
    hl::Hello peer = Hello();
    Set(&peer.endpoint_id, "gateway");
    peer.role = hl::EndpointRole::GATEWAY;
    local.minimum_rate_hz = 100;
    local.maximum_rate_hz = 800;
    local.preferred_rate_hz = 600;
    peer.minimum_rate_hz = 200;
    peer.maximum_rate_hz = 500;
    peer.preferred_rate_hz = 400;
    peer.maximum_payload_size = 2048;
    hl::Capabilities result = {};
    CHECK(hl::Negotiate(local, peer, &result) == hl::Status::OK);
    CHECK(result.accepted);
    CHECK(result.selected_rate_hz == 400);
    CHECK(result.selected_payload_size == 2048);

    peer.supported_major = 2;
    CHECK(hl::Negotiate(local, peer, &result) == hl::Status::OK);
    CHECK(!result.accepted);
    CHECK(result.rejection ==
          hl::NegotiationRejection::MAJOR_VERSION_MISMATCH);
    peer = Hello();
    peer.maximum_payload_size = 128;
    CHECK(hl::Negotiate(Hello(), peer, &result) == hl::Status::OK);
    CHECK(result.rejection ==
          hl::NegotiationRejection::PAYLOAD_LIMIT_MISMATCH);

    hl::Frame maximum = {};
    maximum.message_type = hl::MessageType::HEARTBEAT;
    maximum.session_id = 1;
    maximum.sequence = 1;
    maximum.payload_size = hl::kMaxPayloadSize;
    maximum.major = 1;
    maximum.minor = 0;
    uint8_t encoded[hl::kMaxFrameSize];
    size_t size = 0;
    CHECK(hl::EncodeFrame(maximum, encoded, sizeof(encoded), &size) ==
          hl::Status::OK);
    CHECK(size == hl::kMaxFrameSize);
    CHECK(hl::EncodeFrame(maximum, encoded, sizeof(encoded) - 1, &size) ==
          hl::Status::OUTPUT_TOO_SMALL);
}

struct Collector {
    uint64_t sequences[32];
    size_t count;
    hl::ParseErrorCode errors[32];
    size_t error_count;
};

void CollectFrame(void* context, const hl::Frame& frame) {
    Collector* collector = static_cast<Collector*>(context);
    if (collector->count < 32)
        collector->sequences[collector->count++] = frame.sequence;
}

void CollectError(void* context, const hl::ParseErrorEvent& event) {
    Collector* collector = static_cast<Collector*>(context);
    if (collector->error_count < 32)
        collector->errors[collector->error_count++] = event.code;
}

bool HasError(const Collector& collector, hl::ParseErrorCode code) {
    for (size_t index = 0; index < collector.error_count; ++index)
        if (collector.errors[index] == code) return true;
    return false;
}

void TestIncrementalStreamParser(const char* corpus) {
    Vector command = {};
    Vector state = {};
    Vector heartbeat = {};
    CHECK(LoadVector(corpus, "command", &command));
    CHECK(LoadVector(corpus, "state_health", &state));
    CHECK(LoadVector(corpus, "heartbeat", &heartbeat));

    for (size_t split = 0; split <= command.size; ++split) {
        hl::StreamParser parser;
        Collector collector = {};
        hl::ParseBatch batch = {};
        CHECK(parser.feed(command.data, split, CollectFrame, CollectError,
                          &collector, &batch) == hl::Status::OK);
        CHECK(parser.feed(command.data + split, command.size - split,
                          CollectFrame, CollectError, &collector, &batch) ==
              hl::Status::OK);
        CHECK(collector.count == 1);
        CHECK(collector.sequences[0] == 3);
        CHECK(parser.bufferedBytes() == 0);
    }

    uint8_t concatenated[hl::kMaxFrameSize * 3];
    size_t total = 0;
    std::memcpy(concatenated + total, command.data, command.size);
    total += command.size;
    std::memcpy(concatenated + total, state.data, state.size);
    total += state.size;
    std::memcpy(concatenated + total, heartbeat.data, heartbeat.size);
    total += heartbeat.size;
    hl::StreamParser parser;
    Collector collector = {};
    hl::ParseBatch batch = {};
    for (size_t index = 0; index < total; ++index)
        CHECK(parser.feed(concatenated + index, 1, CollectFrame, CollectError,
                          &collector, &batch) == hl::Status::OK);
    CHECK(collector.count == 3);
    CHECK(collector.sequences[0] == 3);
    CHECK(collector.sequences[1] == 4);
    CHECK(collector.sequences[2] == 7);
    CHECK(parser.bufferedBytes() == 0);

    uint8_t corrupted[hl::kMaxFrameSize];
    std::memcpy(corrupted, command.data, command.size);
    corrupted[hl::kHeaderSize + 3] ^= 0x80;
    uint8_t noisy[16 + hl::kMaxFrameSize * 2];
    const uint8_t noise[] = {'n', 'o', 'i', 's', 'e'};
    size_t noisy_size = 0;
    std::memcpy(noisy + noisy_size, noise, sizeof(noise));
    noisy_size += sizeof(noise);
    std::memcpy(noisy + noisy_size, corrupted, command.size);
    noisy_size += command.size;
    std::memcpy(noisy + noisy_size, heartbeat.data, heartbeat.size);
    noisy_size += heartbeat.size;
    parser.reset();
    collector = Collector();
    CHECK(parser.feed(noisy, noisy_size, CollectFrame, CollectError, &collector,
                      &batch) == hl::Status::OK);
    CHECK(collector.count == 1);
    CHECK(collector.sequences[0] == 7);
    CHECK(HasError(collector, hl::ParseErrorCode::NOISE_DISCARDED));
    CHECK(HasError(collector, hl::ParseErrorCode::CRC_MISMATCH));
    CHECK(parser.bufferedBytes() == 0);

    parser.reset();
    collector = Collector();
    const uint8_t prefix[] = {'x', 'D', 'B', 'H'};
    CHECK(parser.feed(prefix, sizeof(prefix), CollectFrame, CollectError,
                      &collector, &batch) == hl::Status::OK);
    CHECK(parser.bufferedBytes() == 3);
    CHECK(parser.feed(command.data + 3, command.size - 3, CollectFrame,
                      CollectError, &collector, &batch) == hl::Status::OK);
    CHECK(collector.count == 1);
    CHECK(parser.bufferedBytes() == 0);

    static uint8_t oversized[hl::kMaxFeedSize + 1];
    CHECK(parser.feed(oversized, sizeof(oversized), CollectFrame, CollectError,
                      &collector, &batch) == hl::Status::FEED_TOO_LARGE);
    CHECK(parser.bufferedBytes() == 0);

    uint8_t maximum_header[hl::kHeaderSize];
    std::memcpy(maximum_header, command.data, sizeof(maximum_header));
    maximum_header[8] = 0;
    maximum_header[9] = 0;
    maximum_header[10] = 0x10;
    maximum_header[11] = 0;
    parser.reset();
    collector = Collector();
    CHECK(parser.feed(maximum_header, sizeof(maximum_header), CollectFrame,
                      CollectError, &collector, &batch) == hl::Status::OK);
    static uint8_t maximum_feed[hl::kMaxFeedSize];
    CHECK(parser.feed(maximum_feed, sizeof(maximum_feed), CollectFrame,
                      CollectError, &collector, &batch) == hl::Status::OK);
    CHECK(HasError(collector, hl::ParseErrorCode::BUFFER_OVERFLOW));
    CHECK(parser.bufferedBytes() <= hl::kMaxBufferSize);
}

void TestSessionReceiver(const char* corpus) {
    Vector vector = {};
    CHECK(LoadVector(corpus, "command", &vector));
    hl::Frame frame = {};
    CHECK(hl::DecodeFrame(vector.data, vector.size, &frame) == hl::Status::OK);
    hl::SessionReceiver receiver;
    CHECK(receiver.initialize(kSession, Hash(0x11), Capabilities()) ==
          hl::Status::OK);
    hl::TypedMessage message = {};
    hl::ReceiveResult result = receiver.receive(frame, kNow, true, &message);
    CHECK(result.link_accepted);
    CHECK(!result.motion_authorized);
    CHECK(result.denial == hl::ReceiveDenial::NONE);
    CHECK(hl::TextEquals(message.command.source_identity, "controller-main"));
    CHECK(receiver.lastSequence() == 3);

    result = receiver.receive(frame, kNow, true, &message);
    CHECK(!result.link_accepted);
    CHECK(result.denial == hl::ReceiveDenial::DUPLICATE_SEQUENCE);
    hl::Frame reordered = frame;
    reordered.sequence = 2;
    CHECK(receiver.receive(reordered, kNow, true, &message).denial ==
          hl::ReceiveDenial::REORDERED_SEQUENCE);

    hl::SessionReceiver mismatch;
    CHECK(mismatch.initialize(kSession, Hash(0x11), Capabilities()) ==
          hl::Status::OK);
    hl::Frame wrong = frame;
    wrong.session_id -= 1;
    CHECK(mismatch.receive(wrong, kNow, true, &message).denial ==
          hl::ReceiveDenial::PREVIOUS_OR_UNKNOWN_SESSION);
    wrong = frame;
    wrong.config_sha256 = Hash(0x22);
    CHECK(mismatch.receive(wrong, kNow, true, &message).denial ==
          hl::ReceiveDenial::CONFIG_MISMATCH);
    wrong = frame;
    wrong.payload_size = 3;
    std::memcpy(wrong.payload, "bad", 3);
    CHECK(mismatch.receive(wrong, kNow, true, &message).denial ==
          hl::ReceiveDenial::MALFORMED_BODY);
    CHECK(mismatch.lastSequence() == 0);

    hl::SessionReceiver expired;
    CHECK(expired.initialize(kSession, Hash(0x11), Capabilities()) ==
          hl::Status::OK);
    const hl::ReceiveResult expired_result = expired.receive(
        frame, frame.monotonic_ns + 2000000000ULL, true, &message);
    CHECK(expired_result.denial == hl::ReceiveDenial::EXPIRED_COMMAND);
    CHECK(!expired_result.link_accepted);
    CHECK(expired.lastSequence() == 0);

    const hl::ReceiveResult invalid_time =
        mismatch.receive(frame, frame.monotonic_ns - 1, true, &message);
    CHECK(invalid_time.denial == hl::ReceiveDenial::INVALID_EVALUATION_TIME);
    CHECK(invalid_time.status == hl::Status::CROSS_ENVELOPE_MISMATCH);
    hl::Capabilities incomplete = Capabilities();
    incomplete.selected_capabilities &= ~(1ULL << 3);
    hl::SessionReceiver denied;
    CHECK(denied.initialize(kSession, Hash(0x11), incomplete) ==
          hl::Status::INVALID_NEGOTIATION);
    CHECK(denied.initialize(kSession, Hash(0), Capabilities()) ==
          hl::Status::INVALID_SHA256);
}

void TestNoRawEscapeSurfaceAndStatusCodes() {
    CHECK(sizeof(hl::Sha256) == 32);
    CHECK(sizeof(((hl::Text*)0)->bytes) == hl::kMaxTextBytes);
    CHECK(sizeof(((hl::DetailText*)0)->bytes) == hl::kMaxDetailBytes);
    CHECK(std::strcmp(hl::StatusCode(hl::Status::CONFIG_MISMATCH),
                      "CONFIG_MISMATCH") == 0);
    CHECK(static_cast<uint8_t>(hl::MessageType::HELLO) == 1);
    CHECK(static_cast<uint8_t>(hl::MessageType::HEARTBEAT) == 7);
    // TypedMessage exposes only named protocol bodies; vendor bytes cannot be
    // submitted without constructing a Frame, which SessionReceiver decodes
    // through the closed seven-type body switch before exposure.
    hl::TypedMessage value = {};
    CHECK(sizeof(value.command.source_identity.bytes) == hl::kMaxTextBytes);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: test_hostlink_v1 GOLDEN_TSV\n";
        return 2;
    }
    TestConstantsCrcAndGoldenEncode(argv[1]);
    TestWholeGoldenCorpus(argv[1]);
    TestAllCommandModesAndPresenceRules();
    TestTextEnvelopeAndCrossEnvelopeValidation();
    TestNegotiationAndPublishedCeilings();
    TestIncrementalStreamParser(argv[1]);
    TestSessionReceiver(argv[1]);
    TestNoRawEscapeSurfaceAndStatusCodes();

    if (failures != 0) {
        std::cerr << failures << " of " << checks << " checks failed\n";
        return 1;
    }
    std::cout << "HOSTLINK_NATIVE_OK " << checks << " checks"
              << " sizeof(Frame)=" << sizeof(hl::Frame)
              << " sizeof(TypedMessage)=" << sizeof(hl::TypedMessage)
              << " sizeof(StreamParser)=" << sizeof(hl::StreamParser) << '\n';
    return 0;
}
