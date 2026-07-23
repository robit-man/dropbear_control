#pragma once

#include <stddef.h>
#include <stdint.h>

namespace myactuator {
namespace hostlink_v1 {

static const uint8_t kVersionMajor = 1;
static const uint8_t kVersionMinor = 0;
static const size_t kHeaderSize = 72;
static const size_t kCrcSize = 4;
static const size_t kMaxPayloadSize = 4096;
static const size_t kMaxFrameSize = kHeaderSize + kMaxPayloadSize + kCrcSize;
static const size_t kMaxBufferSize = kMaxFrameSize * 2;
static const size_t kMaxFeedSize = kMaxBufferSize;
static const size_t kMaxTextBytes = 255;
static const size_t kMaxDetailBytes = 512;
static const uint32_t kMinNegotiatedPayloadSize = 256;
static const uint16_t kMaxControlRateHz = 5000;
static const uint64_t kMandatoryCapabilities = 0x7FULL;
static const uint64_t kKnownCapabilities = kMandatoryCapabilities;

enum class Status : uint8_t {
    OK = 0,
    NULL_ARGUMENT,
    OUTPUT_TOO_SMALL,
    FEED_TOO_LARGE,
    BAD_MAGIC,
    UNSUPPORTED_VERSION,
    INVALID_HEADER_LENGTH,
    PAYLOAD_LIMIT,
    FRAME_LENGTH_MISMATCH,
    UNKNOWN_MESSAGE_TYPE,
    UNKNOWN_FLAGS,
    RESERVED_NONZERO,
    INVALID_SESSION,
    INVALID_SEQUENCE,
    CRC_MISMATCH,
    BODY_TRUNCATED,
    BODY_TRAILING_BYTES,
    INVALID_TEXT,
    NONEXACT_TEXT,
    INVALID_SHA256,
    INVALID_ENUM,
    INVALID_BOOLEAN,
    INVALID_CAPABILITIES,
    INVALID_RATE,
    INVALID_NEGOTIATION,
    UNKNOWN_FIELD_MASK,
    NONFINITE_VALUE,
    MODE_PRESENCE_MISMATCH,
    ENABLE_MODE_MISMATCH,
    CONFIG_MISMATCH,
    CROSS_ENVELOPE_MISMATCH,
    EXPIRED_COMMAND,
};

const char* StatusCode(Status status);

enum class MessageType : uint8_t {
    HELLO = 1,
    CAPABILITIES = 2,
    COMMAND = 3,
    STATE = 4,
    DISPOSITION = 5,
    FAULT = 6,
    HEARTBEAT = 7,
};

enum FrameFlag : uint8_t {
    FRAME_FLAG_NONE = 0,
    FRAME_FLAG_RESPONSE = 1U << 0,
    FRAME_FLAG_URGENT_SAFETY = 1U << 1,
};

enum class EndpointRole : uint8_t {
    HOST = 1,
    GATEWAY = 2,
    SIMULATOR = 3,
    REPLAY = 4,
};

enum class NegotiationRejection : uint8_t {
    NONE = 0,
    MAJOR_VERSION_MISMATCH = 1,
    MINOR_VERSION_MISMATCH = 2,
    CAPABILITY_MISMATCH = 3,
    RATE_MISMATCH = 4,
    PAYLOAD_LIMIT_MISMATCH = 5,
};

enum class CommandMode : uint8_t {
    DISABLE = 0,
    POSITION = 1,
    VELOCITY = 2,
    EFFORT = 3,
    CURRENT_Q = 4,
    IMPEDANCE = 5,
};

enum class SampleValidity : uint8_t {
    INVALID = 0,
    VALID = 1,
    STALE = 2,
};

enum class Connectivity : uint8_t {
    DISCONNECTED = 0,
    DEGRADED = 1,
    CONNECTED = 2,
};

enum class DriveHealth : uint8_t {
    UNKNOWN = 0,
    OK = 1,
    WARNING = 2,
    FAULT = 3,
};

enum class BusHealth : uint8_t {
    UNKNOWN = 0,
    OK = 1,
    DEGRADED = 2,
    BUS_OFF = 3,
    RECOVERING = 4,
};

enum class NativeResponseState : uint8_t {
    NOT_EXPECTED = 0,
    PENDING = 1,
    VALID = 2,
    TIMED_OUT = 3,
    MALFORMED = 4,
    DRIVE_FAULT = 5,
};

enum class SafetyState : uint8_t {
    BOOT = 0,
    DISCOVERY = 1,
    DISABLED = 2,
    ARMED = 3,
    ENABLED = 4,
    SHUTDOWN = 5,
    FAULT = 6,
};

enum class DispositionPhase : uint8_t {
    RECEIVED = 1,
    ADMITTED = 2,
    NATIVE_TX = 3,
    NATIVE_RESPONSE = 4,
    OBSERVED = 5,
    REJECTED = 6,
};

enum class FaultSeverity : uint8_t {
    INFO = 0,
    WARNING = 1,
    RECOVERABLE = 2,
    LATCHED = 3,
    EMERGENCY = 4,
};

enum class LinkHealth : uint8_t {
    STARTING = 0,
    NEGOTIATING = 1,
    ACTIVE = 2,
    DEGRADED = 3,
    FAULTED = 4,
};

struct Text {
    uint16_t size;
    uint8_t bytes[kMaxTextBytes];
};

struct DetailText {
    uint16_t size;
    uint8_t bytes[kMaxDetailBytes];
};

struct Sha256 {
    uint8_t bytes[32];
};

struct ConfigIdentity {
    Text identity;
    Text revision;
    Sha256 sha256;
};

struct OptionalDouble {
    bool present;
    double value;
};

struct OptionalU32 {
    bool present;
    uint32_t value;
};

struct Hello {
    Text endpoint_id;
    EndpointRole role;
    uint8_t supported_major;
    uint8_t minimum_minor;
    uint8_t maximum_minor;
    uint64_t required_capabilities;
    uint64_t offered_capabilities;
    uint16_t minimum_rate_hz;
    uint16_t maximum_rate_hz;
    uint16_t preferred_rate_hz;
    uint32_t maximum_payload_size;
};

struct Capabilities {
    bool accepted;
    uint8_t selected_major;
    uint8_t selected_minor;
    uint64_t selected_capabilities;
    uint16_t selected_rate_hz;
    uint32_t selected_payload_size;
    NegotiationRejection rejection;
};

struct Command {
    Text canonical_actuator_id;
    ConfigIdentity config;
    Text source_identity;
    Text lease_id;
    Text lease_owner;
    uint64_t lease_sequence;
    uint64_t lease_expiry_monotonic_ns;
    CommandMode mode;
    bool enable_requested;
    OptionalDouble position_rad;
    OptionalDouble velocity_rad_s;
    OptionalDouble effort_nm;
    OptionalDouble current_q_a;
    OptionalDouble stiffness_nm_per_rad;
    OptionalDouble damping_nm_s_per_rad;
};

struct State {
    Text canonical_actuator_id;
    ConfigIdentity config;
    uint64_t sample_monotonic_ns;
    uint64_t sample_age_ns;
    SampleValidity validity;
    Connectivity connectivity;
    DriveHealth drive_health;
    BusHealth bus_health;
    NativeResponseState native_response;
    Text fault_code;
    SafetyState safety_state;
    OptionalDouble position_rad;
    OptionalDouble velocity_rad_s;
    OptionalDouble effort_nm;
    OptionalDouble current_q_a;
    OptionalDouble temperature_c;
    OptionalDouble voltage_v;
    OptionalU32 native_status_code;
    OptionalU32 native_fault_mask;
};

struct Disposition {
    uint64_t request_session_id;
    uint64_t request_sequence;
    Text canonical_actuator_id;
    DispositionPhase phase;
    uint64_t phase_monotonic_ns;
    Text reason_code;
};

struct Fault {
    Text fault_code;
    FaultSeverity severity;
    SafetyState safety_state;
    uint64_t occurred_monotonic_ns;
    uint64_t related_sequence;
    Text canonical_actuator_id;
    DetailText description;
};

struct Heartbeat {
    Text endpoint_id;
    EndpointRole role;
    LinkHealth link_health;
    SafetyState safety_state;
    uint64_t uptime_ns;
    uint64_t last_received_sequence;
};

// Closed typed surface. There is deliberately no raw/vendor payload member.
struct TypedMessage {
    MessageType type;
    Hello hello;
    Capabilities capabilities;
    Command command;
    State state;
    Disposition disposition;
    Fault fault;
    Heartbeat heartbeat;
};

struct Envelope {
    uint8_t flags;
    uint64_t session_id;
    uint64_t sequence;
    uint64_t monotonic_ns;
    Sha256 config_sha256;
};

struct Frame {
    MessageType message_type;
    uint8_t flags;
    uint64_t session_id;
    uint64_t sequence;
    uint64_t monotonic_ns;
    Sha256 config_sha256;
    uint32_t payload_size;
    uint8_t payload[kMaxPayloadSize];
    uint8_t major;
    uint8_t minor;
};

Status SetText(Text* output, const char* value, size_t size,
               bool allow_empty = false, bool require_exact = true);
Status SetDetailText(DetailText* output, const char* value, size_t size,
                     bool allow_empty = true);
bool TextEquals(const Text& text, const char* value);
bool Sha256Equals(const Sha256& left, const Sha256& right);
bool Sha256IsZero(const Sha256& value);

uint32_t Crc32c(const uint8_t* data, size_t size);
Status ValidateHello(const Hello& hello);
Status ValidateCapabilities(const Capabilities& capabilities);
Status Negotiate(const Hello& local, const Hello& peer,
                 Capabilities* result);
Status EncodeFrame(const Frame& frame, uint8_t* output, size_t capacity,
                   size_t* output_size);
Status DecodeFrame(const uint8_t* data, size_t size, Frame* output);
Status EncodeMessage(const TypedMessage& message, const Envelope& envelope,
                     uint8_t* output, size_t capacity, size_t* output_size);
Status DecodeMessage(const Frame& frame, TypedMessage* output);

enum class ParseErrorCode : uint8_t {
    NOISE_DISCARDED = 0,
    INVALID_HEADER = 1,
    CRC_MISMATCH = 2,
    BUFFER_OVERFLOW = 3,
};

struct ParseErrorEvent {
    ParseErrorCode code;
    size_t discarded_bytes;
    Status detail;
};

struct ParseBatch {
    size_t frame_count;
    size_t error_count;
    size_t discarded_bytes;
};

typedef void (*FrameHandler)(void* context, const Frame& frame);
typedef void (*ParseErrorHandler)(void* context,
                                  const ParseErrorEvent& event);

class StreamParser {
public:
    StreamParser();
    void reset();
    size_t bufferedBytes() const;
    Status feed(const uint8_t* data, size_t size, FrameHandler frame_handler,
                ParseErrorHandler error_handler, void* context,
                ParseBatch* result);

private:
    uint8_t buffer_[kMaxBufferSize];
    size_t buffered_;
    Frame scratch_;

    void discardPrefix(size_t size);
};

enum class ReceiveDenial : uint8_t {
    NONE = 0,
    UNSUPPORTED_ENVELOPE,
    PREVIOUS_OR_UNKNOWN_SESSION,
    DUPLICATE_SEQUENCE,
    REORDERED_SEQUENCE,
    NONMONOTONIC_TIMESTAMP,
    CONFIG_MISMATCH,
    MALFORMED_BODY,
    INVALID_EVALUATION_TIME,
    EXPIRED_COMMAND,
};

struct ReceiveResult {
    bool link_accepted;
    ReceiveDenial denial;
    bool motion_authorized;
    Status status;
};

class SessionReceiver {
public:
    SessionReceiver();
    Status initialize(uint64_t active_session_id,
                      const Sha256& active_config_sha256,
                      const Capabilities& negotiation,
                      uint64_t initial_sequence = 0,
                      uint64_t initial_monotonic_ns = 0);
    bool initialized() const;
    uint64_t lastSequence() const;
    ReceiveResult receive(const Frame& frame, uint64_t now_monotonic_ns,
                          bool has_now, TypedMessage* message);

private:
    bool initialized_;
    uint64_t session_id_;
    Sha256 config_sha256_;
    uint64_t last_sequence_;
    uint64_t last_monotonic_ns_;
};

}  // namespace hostlink_v1
}  // namespace myactuator
