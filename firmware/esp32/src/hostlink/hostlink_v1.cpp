#include "hostlink_v1.h"

#include <cmath>
#include <cstring>
#include <limits>

namespace myactuator {
namespace hostlink_v1 {

namespace {

static const uint8_t kMagic[4] = {'D', 'B', 'H', 'L'};
static const uint8_t kKnownFrameFlags =
    FRAME_FLAG_RESPONSE | FRAME_FLAG_URGENT_SAFETY;
static const uint16_t kCommandKnownMask = 0x003F;
static const uint16_t kStateKnownMask = 0x00FF;

uint16_t ReadU16(const uint8_t* data) {
    return static_cast<uint16_t>((static_cast<uint16_t>(data[0]) << 8) |
                                 static_cast<uint16_t>(data[1]));
}

uint32_t ReadU32(const uint8_t* data) {
    return (static_cast<uint32_t>(data[0]) << 24) |
           (static_cast<uint32_t>(data[1]) << 16) |
           (static_cast<uint32_t>(data[2]) << 8) |
           static_cast<uint32_t>(data[3]);
}

uint64_t ReadU64(const uint8_t* data) {
    uint64_t value = 0;
    for (size_t index = 0; index < 8; ++index) {
        value = (value << 8) | static_cast<uint64_t>(data[index]);
    }
    return value;
}

void WriteU16(uint8_t* data, uint16_t value) {
    data[0] = static_cast<uint8_t>(value >> 8);
    data[1] = static_cast<uint8_t>(value);
}

void WriteU32(uint8_t* data, uint32_t value) {
    data[0] = static_cast<uint8_t>(value >> 24);
    data[1] = static_cast<uint8_t>(value >> 16);
    data[2] = static_cast<uint8_t>(value >> 8);
    data[3] = static_cast<uint8_t>(value);
}

void WriteU64(uint8_t* data, uint64_t value) {
    for (size_t index = 0; index < 8; ++index) {
        data[7 - index] = static_cast<uint8_t>(value);
        value >>= 8;
    }
}

bool MessageTypeValid(uint8_t value) {
    return value >= static_cast<uint8_t>(MessageType::HELLO) &&
           value <= static_cast<uint8_t>(MessageType::HEARTBEAT);
}

bool EndpointRoleValid(EndpointRole value) {
    const uint8_t raw = static_cast<uint8_t>(value);
    return raw >= 1 && raw <= 4;
}

bool RejectionValid(NegotiationRejection value) {
    return static_cast<uint8_t>(value) <= 5;
}

bool CommandModeValid(CommandMode value) {
    return static_cast<uint8_t>(value) <= 5;
}

bool SampleValidityValid(SampleValidity value) {
    return static_cast<uint8_t>(value) <= 2;
}

bool ConnectivityValid(Connectivity value) {
    return static_cast<uint8_t>(value) <= 2;
}

bool DriveHealthValid(DriveHealth value) {
    return static_cast<uint8_t>(value) <= 3;
}

bool BusHealthValid(BusHealth value) {
    return static_cast<uint8_t>(value) <= 4;
}

bool NativeResponseValid(NativeResponseState value) {
    return static_cast<uint8_t>(value) <= 5;
}

bool SafetyStateValid(SafetyState value) {
    return static_cast<uint8_t>(value) <= 6;
}

bool DispositionPhaseValid(DispositionPhase value) {
    const uint8_t raw = static_cast<uint8_t>(value);
    return raw >= 1 && raw <= 6;
}

bool FaultSeverityValid(FaultSeverity value) {
    return static_cast<uint8_t>(value) <= 4;
}

bool LinkHealthValid(LinkHealth value) {
    return static_cast<uint8_t>(value) <= 4;
}

bool IsUnicodeWhitespace(uint32_t codepoint) {
    return (codepoint >= 0x0009 && codepoint <= 0x000D) ||
           (codepoint >= 0x001C && codepoint <= 0x0020) ||
           codepoint == 0x0085 || codepoint == 0x00A0 ||
           codepoint == 0x1680 ||
           (codepoint >= 0x2000 && codepoint <= 0x200A) ||
           codepoint == 0x2028 || codepoint == 0x2029 ||
           codepoint == 0x202F || codepoint == 0x205F ||
           codepoint == 0x3000;
}

bool DecodeCodepoint(const uint8_t* bytes, size_t size, size_t* offset,
                     uint32_t* codepoint) {
    if (*offset >= size) {
        return false;
    }
    const uint8_t first = bytes[(*offset)++];
    if (first < 0x80) {
        *codepoint = first;
        return true;
    }
    size_t continuation_count = 0;
    uint32_t value = 0;
    uint32_t minimum = 0;
    if ((first & 0xE0) == 0xC0) {
        continuation_count = 1;
        value = first & 0x1F;
        minimum = 0x80;
    } else if ((first & 0xF0) == 0xE0) {
        continuation_count = 2;
        value = first & 0x0F;
        minimum = 0x800;
    } else if ((first & 0xF8) == 0xF0) {
        continuation_count = 3;
        value = first & 0x07;
        minimum = 0x10000;
    } else {
        return false;
    }
    if (continuation_count > size - *offset) {
        return false;
    }
    for (size_t index = 0; index < continuation_count; ++index) {
        const uint8_t next = bytes[(*offset)++];
        if ((next & 0xC0) != 0x80) {
            return false;
        }
        value = (value << 6) | (next & 0x3F);
    }
    if (value < minimum || value > 0x10FFFF ||
        (value >= 0xD800 && value <= 0xDFFF)) {
        return false;
    }
    *codepoint = value;
    return true;
}

bool AsciiEqualInsensitive(const uint8_t* bytes, size_t size,
                           const char* expected) {
    size_t expected_size = 0;
    while (expected[expected_size] != '\0') {
        ++expected_size;
    }
    if (size != expected_size) {
        return false;
    }
    for (size_t index = 0; index < size; ++index) {
        uint8_t actual = bytes[index];
        if (actual >= 'A' && actual <= 'Z') {
            actual = static_cast<uint8_t>(actual + ('a' - 'A'));
        }
        if (actual != static_cast<uint8_t>(expected[index])) {
            return false;
        }
    }
    return true;
}

bool IsNonexactWord(const uint8_t* bytes, size_t size) {
    static const char* const words[] = {
        "all", "any", "default", "latest", "none", "tbd", "unknown"};
    for (size_t index = 0; index < sizeof(words) / sizeof(words[0]); ++index) {
        if (AsciiEqualInsensitive(bytes, size, words[index])) {
            return true;
        }
    }
    return false;
}

bool IsNonexactWhole(const uint8_t* bytes, size_t size) {
    if (IsNonexactWord(bytes, size)) {
        return true;
    }
    return AsciiEqualInsensitive(bytes, size, "*") ||
           AsciiEqualInsensitive(bytes, size, "n/a");
}

bool IsSegmentDelimiter(uint8_t value) {
    return value == '.' || value == '-' || value == '_' || value == '/';
}

Status ValidateTextBytes(const uint8_t* bytes, size_t size, size_t maximum,
                         bool allow_empty, bool require_exact) {
    if (size > maximum || (!allow_empty && size == 0)) {
        return Status::INVALID_TEXT;
    }
    if (size == 0) {
        return Status::OK;
    }
    size_t offset = 0;
    uint32_t first_codepoint = 0;
    uint32_t last_codepoint = 0;
    bool first = true;
    while (offset < size) {
        uint32_t codepoint = 0;
        if (!DecodeCodepoint(bytes, size, &offset, &codepoint)) {
            return Status::INVALID_TEXT;
        }
        if (codepoint < 0x20 || codepoint == 0x7F) {
            return Status::INVALID_TEXT;
        }
        if (first) {
            first_codepoint = codepoint;
            first = false;
        }
        last_codepoint = codepoint;
    }
    if (!require_exact) {
        return Status::OK;
    }
    if (IsUnicodeWhitespace(first_codepoint) ||
        IsUnicodeWhitespace(last_codepoint) || IsNonexactWhole(bytes, size)) {
        return Status::NONEXACT_TEXT;
    }
    for (size_t index = 0; index < size; ++index) {
        const uint8_t value = bytes[index];
        if (value == '*' || value == '?' || value == '[' || value == ']' ||
            value == '{' || value == '}') {
            return Status::NONEXACT_TEXT;
        }
    }
    size_t segment_start = 0;
    for (size_t index = 0; index <= size; ++index) {
        if (index == size || IsSegmentDelimiter(bytes[index])) {
            if (index > segment_start &&
                IsNonexactWord(bytes + segment_start, index - segment_start)) {
                return Status::NONEXACT_TEXT;
            }
            segment_start = index + 1;
        }
    }
    return Status::OK;
}

Status ValidateText(const Text& text, bool allow_empty, bool require_exact) {
    return ValidateTextBytes(text.bytes, text.size, kMaxTextBytes, allow_empty,
                             require_exact);
}

Status ValidateDetail(const DetailText& text, bool allow_empty) {
    return ValidateTextBytes(text.bytes, text.size, kMaxDetailBytes, allow_empty,
                             false);
}

Status ValidateSha(const Sha256& sha, bool allow_zero) {
    return (!allow_zero && Sha256IsZero(sha)) ? Status::INVALID_SHA256
                                              : Status::OK;
}

Status ValidateConfig(const ConfigIdentity& config) {
    Status status = ValidateText(config.identity, false, true);
    if (status != Status::OK) {
        return status;
    }
    status = ValidateText(config.revision, false, true);
    if (status != Status::OK) {
        return status;
    }
    return ValidateSha(config.sha256, false);
}

bool TextIsNone(const Text& text) {
    return text.size == 4 && text.bytes[0] == 'N' && text.bytes[1] == 'O' &&
           text.bytes[2] == 'N' && text.bytes[3] == 'E';
}

Status ValidateStatusText(const Text& text, bool allow_none) {
    if (allow_none && TextIsNone(text)) {
        return Status::OK;
    }
    return ValidateText(text, false, true);
}

class Writer {
public:
    Writer(uint8_t* data, size_t capacity)
        : data_(data), capacity_(capacity), offset_(0), status_(Status::OK) {}

    void u8(uint8_t value) {
        write(&value, 1);
    }

    void u16(uint16_t value) {
        uint8_t encoded[2];
        WriteU16(encoded, value);
        write(encoded, sizeof(encoded));
    }

    void u32(uint32_t value) {
        uint8_t encoded[4];
        WriteU32(encoded, value);
        write(encoded, sizeof(encoded));
    }

    void u64(uint64_t value) {
        uint8_t encoded[8];
        WriteU64(encoded, value);
        write(encoded, sizeof(encoded));
    }

    void boolean(bool value) {
        u8(value ? 1 : 0);
    }

    void f64(double value) {
        if (!std::isfinite(value)) {
            fail(Status::NONFINITE_VALUE);
            return;
        }
        static_assert(sizeof(double) == sizeof(uint64_t),
                      "Host-link V1 requires IEEE-754 binary64 storage");
        static_assert(std::numeric_limits<double>::is_iec559,
                      "Host-link V1 requires IEEE-754 binary64 semantics");
        uint64_t bits = 0;
        std::memcpy(&bits, &value, sizeof(bits));
        u64(bits);
    }

    void text(const Text& value, bool allow_empty = false,
              bool require_exact = true) {
        const Status checked = ValidateText(value, allow_empty, require_exact);
        if (checked != Status::OK) {
            fail(checked);
            return;
        }
        u16(value.size);
        write(value.bytes, value.size);
    }

    void detail(const DetailText& value, bool allow_empty = true) {
        const Status checked = ValidateDetail(value, allow_empty);
        if (checked != Status::OK) {
            fail(checked);
            return;
        }
        u16(value.size);
        write(value.bytes, value.size);
    }

    void fixed(const uint8_t* value, size_t size) {
        write(value, size);
    }

    Status status() const { return status_; }
    size_t size() const { return offset_; }

private:
    uint8_t* data_;
    size_t capacity_;
    size_t offset_;
    Status status_;

    void fail(Status status) {
        if (status_ == Status::OK) {
            status_ = status;
        }
    }

    void write(const uint8_t* value, size_t size) {
        if (status_ != Status::OK) {
            return;
        }
        if (size > capacity_ - offset_) {
            fail(Status::OUTPUT_TOO_SMALL);
            return;
        }
        if (size != 0) {
            std::memcpy(data_ + offset_, value, size);
        }
        offset_ += size;
    }
};

class Reader {
public:
    Reader(const uint8_t* data, size_t size)
        : data_(data), size_(size), offset_(0), status_(Status::OK) {}

    uint8_t u8() {
        const uint8_t* value = take(1);
        return value == 0 ? 0 : value[0];
    }

    uint16_t u16() {
        const uint8_t* value = take(2);
        return value == 0 ? 0 : ReadU16(value);
    }

    uint32_t u32() {
        const uint8_t* value = take(4);
        return value == 0 ? 0 : ReadU32(value);
    }

    uint64_t u64() {
        const uint8_t* value = take(8);
        return value == 0 ? 0 : ReadU64(value);
    }

    bool boolean() {
        const uint8_t value = u8();
        if (status_ == Status::OK && value > 1) {
            fail(Status::INVALID_BOOLEAN);
        }
        return value != 0;
    }

    double f64() {
        const uint64_t bits = u64();
        double value = 0.0;
        std::memcpy(&value, &bits, sizeof(value));
        if (status_ == Status::OK && !std::isfinite(value)) {
            fail(Status::NONFINITE_VALUE);
        }
        return value;
    }

    void text(Text* output, bool allow_empty = false,
              bool require_exact = true) {
        if (output == 0) {
            fail(Status::NULL_ARGUMENT);
            return;
        }
        std::memset(output, 0, sizeof(*output));
        const uint16_t length = u16();
        if (status_ != Status::OK) {
            return;
        }
        if (length > kMaxTextBytes) {
            fail(Status::INVALID_TEXT);
            return;
        }
        const uint8_t* value = take(length);
        if (status_ != Status::OK) {
            return;
        }
        const Status checked = ValidateTextBytes(value, length, kMaxTextBytes,
                                                 allow_empty, require_exact);
        if (checked != Status::OK) {
            fail(checked);
            return;
        }
        output->size = length;
        if (length != 0) {
            std::memcpy(output->bytes, value, length);
        }
    }

    void detail(DetailText* output, bool allow_empty = true) {
        if (output == 0) {
            fail(Status::NULL_ARGUMENT);
            return;
        }
        std::memset(output, 0, sizeof(*output));
        const uint16_t length = u16();
        if (status_ != Status::OK) {
            return;
        }
        if (length > kMaxDetailBytes) {
            fail(Status::INVALID_TEXT);
            return;
        }
        const uint8_t* value = take(length);
        if (status_ != Status::OK) {
            return;
        }
        const Status checked = ValidateTextBytes(value, length, kMaxDetailBytes,
                                                 allow_empty, false);
        if (checked != Status::OK) {
            fail(checked);
            return;
        }
        output->size = length;
        if (length != 0) {
            std::memcpy(output->bytes, value, length);
        }
    }

    void fixed(uint8_t* output, size_t size) {
        const uint8_t* value = take(size);
        if (value != 0) {
            std::memcpy(output, value, size);
        }
    }

    Status finish() const {
        if (status_ != Status::OK) {
            return status_;
        }
        return offset_ == size_ ? Status::OK : Status::BODY_TRAILING_BYTES;
    }

    Status status() const { return status_; }

private:
    const uint8_t* data_;
    size_t size_;
    size_t offset_;
    Status status_;

    void fail(Status status) {
        if (status_ == Status::OK) {
            status_ = status;
        }
    }

    const uint8_t* take(size_t count) {
        if (status_ != Status::OK || count > size_ - offset_) {
            fail(Status::BODY_TRUNCATED);
            return 0;
        }
        const uint8_t* result = data_ + offset_;
        offset_ += count;
        return result;
    }
};

Status WriteConfig(Writer* writer, const ConfigIdentity& config) {
    const Status status = ValidateConfig(config);
    if (status != Status::OK) {
        return status;
    }
    writer->text(config.identity);
    writer->text(config.revision);
    writer->fixed(config.sha256.bytes, 32);
    return writer->status();
}

Status ReadConfig(Reader* reader, ConfigIdentity* config) {
    reader->text(&config->identity);
    reader->text(&config->revision);
    reader->fixed(config->sha256.bytes, 32);
    if (reader->status() != Status::OK) {
        return reader->status();
    }
    return ValidateConfig(*config);
}

Status ValidateCommand(const Command& command) {
    Status status = ValidateText(command.canonical_actuator_id, false, true);
    if (status != Status::OK) return status;
    status = ValidateConfig(command.config);
    if (status != Status::OK) return status;
    status = ValidateText(command.source_identity, false, true);
    if (status != Status::OK) return status;
    status = ValidateText(command.lease_id, false, true);
    if (status != Status::OK) return status;
    status = ValidateText(command.lease_owner, false, true);
    if (status != Status::OK) return status;
    if (command.lease_sequence == 0 || command.lease_expiry_monotonic_ns == 0) {
        return Status::INVALID_SEQUENCE;
    }
    if (!CommandModeValid(command.mode)) return Status::INVALID_ENUM;
    const OptionalDouble* values[] = {
        &command.position_rad,          &command.velocity_rad_s,
        &command.effort_nm,             &command.current_q_a,
        &command.stiffness_nm_per_rad,  &command.damping_nm_s_per_rad,
    };
    uint16_t mask = 0;
    for (size_t index = 0; index < 6; ++index) {
        if (values[index]->present) {
            if (!std::isfinite(values[index]->value)) {
                return Status::NONFINITE_VALUE;
            }
            mask |= static_cast<uint16_t>(1U << index);
        }
    }
    uint16_t required = 0;
    uint16_t allowed = 0;
    switch (command.mode) {
        case CommandMode::DISABLE:
            required = 0;
            allowed = 0;
            break;
        case CommandMode::POSITION:
            required = 1U << 0;
            allowed = (1U << 0) | (1U << 1) | (1U << 2);
            break;
        case CommandMode::VELOCITY:
            required = 1U << 1;
            allowed = (1U << 1) | (1U << 2);
            break;
        case CommandMode::EFFORT:
            required = 1U << 2;
            allowed = 1U << 2;
            break;
        case CommandMode::CURRENT_Q:
            required = 1U << 3;
            allowed = 1U << 3;
            break;
        case CommandMode::IMPEDANCE:
            required = (1U << 0) | (1U << 1) | (1U << 4) | (1U << 5);
            allowed = required | (1U << 2);
            break;
    }
    if ((mask & required) != required || (mask & ~allowed) != 0) {
        return Status::MODE_PRESENCE_MISMATCH;
    }
    if ((command.mode == CommandMode::DISABLE && command.enable_requested) ||
        (command.mode != CommandMode::DISABLE && !command.enable_requested)) {
        return Status::ENABLE_MODE_MISMATCH;
    }
    return Status::OK;
}

Status ValidateState(const State& state) {
    Status status = ValidateText(state.canonical_actuator_id, false, true);
    if (status != Status::OK) return status;
    status = ValidateConfig(state.config);
    if (status != Status::OK) return status;
    if (!SampleValidityValid(state.validity) ||
        !ConnectivityValid(state.connectivity) ||
        !DriveHealthValid(state.drive_health) ||
        !BusHealthValid(state.bus_health) ||
        !NativeResponseValid(state.native_response) ||
        !SafetyStateValid(state.safety_state)) {
        return Status::INVALID_ENUM;
    }
    status = ValidateStatusText(state.fault_code, true);
    if (status != Status::OK) return status;
    const OptionalDouble* values[] = {
        &state.position_rad, &state.velocity_rad_s, &state.effort_nm,
        &state.current_q_a,  &state.temperature_c,  &state.voltage_v,
    };
    for (size_t index = 0; index < 6; ++index) {
        if (values[index]->present && !std::isfinite(values[index]->value)) {
            return Status::NONFINITE_VALUE;
        }
    }
    return Status::OK;
}

Status ValidateDisposition(const Disposition& disposition) {
    if (disposition.request_session_id == 0 ||
        disposition.request_sequence == 0) {
        return Status::INVALID_SEQUENCE;
    }
    Status status = ValidateText(disposition.canonical_actuator_id, false, true);
    if (status != Status::OK) return status;
    if (!DispositionPhaseValid(disposition.phase)) return Status::INVALID_ENUM;
    status = ValidateStatusText(disposition.reason_code, true);
    if (status != Status::OK) return status;
    const bool rejected = disposition.phase == DispositionPhase::REJECTED;
    if ((rejected && TextIsNone(disposition.reason_code)) ||
        (!rejected && !TextIsNone(disposition.reason_code))) {
        return Status::CROSS_ENVELOPE_MISMATCH;
    }
    return Status::OK;
}

Status ValidateFault(const Fault& fault) {
    Status status = ValidateText(fault.fault_code, false, true);
    if (status != Status::OK) return status;
    if (!FaultSeverityValid(fault.severity) ||
        !SafetyStateValid(fault.safety_state)) {
        return Status::INVALID_ENUM;
    }
    status = ValidateText(fault.canonical_actuator_id, true,
                          fault.canonical_actuator_id.size != 0);
    if (status != Status::OK) return status;
    return ValidateDetail(fault.description, true);
}

Status ValidateHeartbeat(const Heartbeat& heartbeat) {
    Status status = ValidateText(heartbeat.endpoint_id, false, true);
    if (status != Status::OK) return status;
    if (!EndpointRoleValid(heartbeat.role) ||
        !LinkHealthValid(heartbeat.link_health) ||
        !SafetyStateValid(heartbeat.safety_state)) {
        return Status::INVALID_ENUM;
    }
    return Status::OK;
}

Status EncodePayload(const TypedMessage& message, uint8_t* payload,
                     size_t capacity, size_t* payload_size) {
    if (payload == 0 || payload_size == 0) return Status::NULL_ARGUMENT;
    Writer writer(payload, capacity);
    Status status = Status::OK;
    switch (message.type) {
        case MessageType::HELLO: {
            const Hello& body = message.hello;
            status = ValidateHello(body);
            if (status != Status::OK) return status;
            writer.text(body.endpoint_id);
            writer.u8(static_cast<uint8_t>(body.role));
            writer.u8(body.supported_major);
            writer.u8(body.minimum_minor);
            writer.u8(body.maximum_minor);
            writer.u64(body.required_capabilities);
            writer.u64(body.offered_capabilities);
            writer.u16(body.minimum_rate_hz);
            writer.u16(body.maximum_rate_hz);
            writer.u16(body.preferred_rate_hz);
            writer.u32(body.maximum_payload_size);
            break;
        }
        case MessageType::CAPABILITIES: {
            const Capabilities& body = message.capabilities;
            status = ValidateCapabilities(body);
            if (status != Status::OK) return status;
            writer.boolean(body.accepted);
            writer.u8(body.selected_major);
            writer.u8(body.selected_minor);
            writer.u64(body.selected_capabilities);
            writer.u16(body.selected_rate_hz);
            writer.u32(body.selected_payload_size);
            writer.u8(static_cast<uint8_t>(body.rejection));
            break;
        }
        case MessageType::COMMAND: {
            const Command& body = message.command;
            status = ValidateCommand(body);
            if (status != Status::OK) return status;
            writer.text(body.canonical_actuator_id);
            status = WriteConfig(&writer, body.config);
            if (status != Status::OK) return status;
            writer.text(body.source_identity);
            writer.text(body.lease_id);
            writer.text(body.lease_owner);
            writer.u64(body.lease_sequence);
            writer.u64(body.lease_expiry_monotonic_ns);
            writer.u8(static_cast<uint8_t>(body.mode));
            writer.boolean(body.enable_requested);
            const OptionalDouble* values[] = {
                &body.position_rad,         &body.velocity_rad_s,
                &body.effort_nm,            &body.current_q_a,
                &body.stiffness_nm_per_rad, &body.damping_nm_s_per_rad,
            };
            uint16_t mask = 0;
            for (size_t index = 0; index < 6; ++index) {
                if (values[index]->present) mask |= 1U << index;
            }
            writer.u16(mask);
            for (size_t index = 0; index < 6; ++index) {
                if (values[index]->present) writer.f64(values[index]->value);
            }
            break;
        }
        case MessageType::STATE: {
            const State& body = message.state;
            status = ValidateState(body);
            if (status != Status::OK) return status;
            writer.text(body.canonical_actuator_id);
            status = WriteConfig(&writer, body.config);
            if (status != Status::OK) return status;
            writer.u64(body.sample_monotonic_ns);
            writer.u64(body.sample_age_ns);
            writer.u8(static_cast<uint8_t>(body.validity));
            writer.u8(static_cast<uint8_t>(body.connectivity));
            writer.u8(static_cast<uint8_t>(body.drive_health));
            writer.u8(static_cast<uint8_t>(body.bus_health));
            writer.u8(static_cast<uint8_t>(body.native_response));
            writer.text(body.fault_code, false, false);
            writer.u8(static_cast<uint8_t>(body.safety_state));
            const OptionalDouble* values[] = {
                &body.position_rad, &body.velocity_rad_s, &body.effort_nm,
                &body.current_q_a,  &body.temperature_c,  &body.voltage_v,
            };
            uint16_t mask = 0;
            for (size_t index = 0; index < 6; ++index) {
                if (values[index]->present) mask |= 1U << index;
            }
            if (body.native_status_code.present) mask |= 1U << 6;
            if (body.native_fault_mask.present) mask |= 1U << 7;
            writer.u16(mask);
            for (size_t index = 0; index < 6; ++index) {
                if (values[index]->present) writer.f64(values[index]->value);
            }
            if (body.native_status_code.present)
                writer.u32(body.native_status_code.value);
            if (body.native_fault_mask.present)
                writer.u32(body.native_fault_mask.value);
            break;
        }
        case MessageType::DISPOSITION: {
            const Disposition& body = message.disposition;
            status = ValidateDisposition(body);
            if (status != Status::OK) return status;
            writer.u64(body.request_session_id);
            writer.u64(body.request_sequence);
            writer.text(body.canonical_actuator_id);
            writer.u8(static_cast<uint8_t>(body.phase));
            writer.u64(body.phase_monotonic_ns);
            writer.text(body.reason_code, false, false);
            break;
        }
        case MessageType::FAULT: {
            const Fault& body = message.fault;
            status = ValidateFault(body);
            if (status != Status::OK) return status;
            writer.text(body.fault_code);
            writer.u8(static_cast<uint8_t>(body.severity));
            writer.u8(static_cast<uint8_t>(body.safety_state));
            writer.u64(body.occurred_monotonic_ns);
            writer.u64(body.related_sequence);
            writer.text(body.canonical_actuator_id, true,
                        body.canonical_actuator_id.size != 0);
            writer.detail(body.description);
            break;
        }
        case MessageType::HEARTBEAT: {
            const Heartbeat& body = message.heartbeat;
            status = ValidateHeartbeat(body);
            if (status != Status::OK) return status;
            writer.text(body.endpoint_id);
            writer.u8(static_cast<uint8_t>(body.role));
            writer.u8(static_cast<uint8_t>(body.link_health));
            writer.u8(static_cast<uint8_t>(body.safety_state));
            writer.u64(body.uptime_ns);
            writer.u64(body.last_received_sequence);
            break;
        }
    }
    if (writer.status() != Status::OK) return writer.status();
    *payload_size = writer.size();
    return Status::OK;
}

Status DecodePayload(const Frame& frame, TypedMessage* output) {
    if (output == 0) return Status::NULL_ARGUMENT;
    std::memset(output, 0, sizeof(*output));
    output->type = frame.message_type;
    Reader reader(frame.payload, frame.payload_size);
    Status status = Status::OK;
    switch (frame.message_type) {
        case MessageType::HELLO: {
            Hello& body = output->hello;
            reader.text(&body.endpoint_id);
            body.role = static_cast<EndpointRole>(reader.u8());
            body.supported_major = reader.u8();
            body.minimum_minor = reader.u8();
            body.maximum_minor = reader.u8();
            body.required_capabilities = reader.u64();
            body.offered_capabilities = reader.u64();
            body.minimum_rate_hz = reader.u16();
            body.maximum_rate_hz = reader.u16();
            body.preferred_rate_hz = reader.u16();
            body.maximum_payload_size = reader.u32();
            status = reader.finish();
            if (status == Status::OK) status = ValidateHello(body);
            return status;
        }
        case MessageType::CAPABILITIES: {
            Capabilities& body = output->capabilities;
            body.accepted = reader.boolean();
            body.selected_major = reader.u8();
            body.selected_minor = reader.u8();
            body.selected_capabilities = reader.u64();
            body.selected_rate_hz = reader.u16();
            body.selected_payload_size = reader.u32();
            body.rejection = static_cast<NegotiationRejection>(reader.u8());
            status = reader.finish();
            if (status == Status::OK) status = ValidateCapabilities(body);
            return status;
        }
        case MessageType::COMMAND: {
            Command& body = output->command;
            reader.text(&body.canonical_actuator_id);
            status = ReadConfig(&reader, &body.config);
            if (status != Status::OK) return status;
            reader.text(&body.source_identity);
            reader.text(&body.lease_id);
            reader.text(&body.lease_owner);
            body.lease_sequence = reader.u64();
            body.lease_expiry_monotonic_ns = reader.u64();
            body.mode = static_cast<CommandMode>(reader.u8());
            body.enable_requested = reader.boolean();
            const uint16_t mask = reader.u16();
            if ((mask & ~kCommandKnownMask) != 0) {
                return Status::UNKNOWN_FIELD_MASK;
            }
            OptionalDouble* values[] = {
                &body.position_rad,         &body.velocity_rad_s,
                &body.effort_nm,            &body.current_q_a,
                &body.stiffness_nm_per_rad, &body.damping_nm_s_per_rad,
            };
            for (size_t index = 0; index < 6; ++index) {
                values[index]->present = (mask & (1U << index)) != 0;
                if (values[index]->present) values[index]->value = reader.f64();
            }
            status = reader.finish();
            if (status == Status::OK) status = ValidateCommand(body);
            return status;
        }
        case MessageType::STATE: {
            State& body = output->state;
            reader.text(&body.canonical_actuator_id);
            status = ReadConfig(&reader, &body.config);
            if (status != Status::OK) return status;
            body.sample_monotonic_ns = reader.u64();
            body.sample_age_ns = reader.u64();
            body.validity = static_cast<SampleValidity>(reader.u8());
            body.connectivity = static_cast<Connectivity>(reader.u8());
            body.drive_health = static_cast<DriveHealth>(reader.u8());
            body.bus_health = static_cast<BusHealth>(reader.u8());
            body.native_response = static_cast<NativeResponseState>(reader.u8());
            reader.text(&body.fault_code, false, false);
            body.safety_state = static_cast<SafetyState>(reader.u8());
            const uint16_t mask = reader.u16();
            if ((mask & ~kStateKnownMask) != 0) {
                return Status::UNKNOWN_FIELD_MASK;
            }
            OptionalDouble* values[] = {
                &body.position_rad, &body.velocity_rad_s, &body.effort_nm,
                &body.current_q_a,  &body.temperature_c,  &body.voltage_v,
            };
            for (size_t index = 0; index < 6; ++index) {
                values[index]->present = (mask & (1U << index)) != 0;
                if (values[index]->present) values[index]->value = reader.f64();
            }
            body.native_status_code.present = (mask & (1U << 6)) != 0;
            if (body.native_status_code.present)
                body.native_status_code.value = reader.u32();
            body.native_fault_mask.present = (mask & (1U << 7)) != 0;
            if (body.native_fault_mask.present)
                body.native_fault_mask.value = reader.u32();
            status = reader.finish();
            if (status == Status::OK) status = ValidateState(body);
            return status;
        }
        case MessageType::DISPOSITION: {
            Disposition& body = output->disposition;
            body.request_session_id = reader.u64();
            body.request_sequence = reader.u64();
            reader.text(&body.canonical_actuator_id);
            body.phase = static_cast<DispositionPhase>(reader.u8());
            body.phase_monotonic_ns = reader.u64();
            reader.text(&body.reason_code, false, false);
            status = reader.finish();
            if (status == Status::OK) status = ValidateDisposition(body);
            return status;
        }
        case MessageType::FAULT: {
            Fault& body = output->fault;
            reader.text(&body.fault_code);
            body.severity = static_cast<FaultSeverity>(reader.u8());
            body.safety_state = static_cast<SafetyState>(reader.u8());
            body.occurred_monotonic_ns = reader.u64();
            body.related_sequence = reader.u64();
            reader.text(&body.canonical_actuator_id, true, false);
            reader.detail(&body.description);
            status = reader.finish();
            if (status == Status::OK) status = ValidateFault(body);
            return status;
        }
        case MessageType::HEARTBEAT: {
            Heartbeat& body = output->heartbeat;
            reader.text(&body.endpoint_id);
            body.role = static_cast<EndpointRole>(reader.u8());
            body.link_health = static_cast<LinkHealth>(reader.u8());
            body.safety_state = static_cast<SafetyState>(reader.u8());
            body.uptime_ns = reader.u64();
            body.last_received_sequence = reader.u64();
            status = reader.finish();
            if (status == Status::OK) status = ValidateHeartbeat(body);
            return status;
        }
    }
    return Status::UNKNOWN_MESSAGE_TYPE;
}

void AddParseError(ParseBatch* batch, ParseErrorHandler handler, void* context,
                   ParseErrorCode code, size_t discarded, Status detail) {
    ++batch->error_count;
    batch->discarded_bytes += discarded;
    if (handler != 0) {
        const ParseErrorEvent event = {code, discarded, detail};
        handler(context, event);
    }
}

}  // namespace

const char* StatusCode(Status status) {
    switch (status) {
        case Status::OK: return "OK";
        case Status::NULL_ARGUMENT: return "NULL_ARGUMENT";
        case Status::OUTPUT_TOO_SMALL: return "OUTPUT_TOO_SMALL";
        case Status::FEED_TOO_LARGE: return "FEED_TOO_LARGE";
        case Status::BAD_MAGIC: return "BAD_MAGIC";
        case Status::UNSUPPORTED_VERSION: return "UNSUPPORTED_VERSION";
        case Status::INVALID_HEADER_LENGTH: return "INVALID_HEADER_LENGTH";
        case Status::PAYLOAD_LIMIT: return "PAYLOAD_LIMIT";
        case Status::FRAME_LENGTH_MISMATCH: return "FRAME_LENGTH_MISMATCH";
        case Status::UNKNOWN_MESSAGE_TYPE: return "UNKNOWN_MESSAGE_TYPE";
        case Status::UNKNOWN_FLAGS: return "UNKNOWN_FLAGS";
        case Status::RESERVED_NONZERO: return "RESERVED_NONZERO";
        case Status::INVALID_SESSION: return "INVALID_SESSION";
        case Status::INVALID_SEQUENCE: return "INVALID_SEQUENCE";
        case Status::CRC_MISMATCH: return "CRC_MISMATCH";
        case Status::BODY_TRUNCATED: return "BODY_TRUNCATED";
        case Status::BODY_TRAILING_BYTES: return "BODY_TRAILING_BYTES";
        case Status::INVALID_TEXT: return "INVALID_TEXT";
        case Status::NONEXACT_TEXT: return "NONEXACT_TEXT";
        case Status::INVALID_SHA256: return "INVALID_SHA256";
        case Status::INVALID_ENUM: return "INVALID_ENUM";
        case Status::INVALID_BOOLEAN: return "INVALID_BOOLEAN";
        case Status::INVALID_CAPABILITIES: return "INVALID_CAPABILITIES";
        case Status::INVALID_RATE: return "INVALID_RATE";
        case Status::INVALID_NEGOTIATION: return "INVALID_NEGOTIATION";
        case Status::UNKNOWN_FIELD_MASK: return "UNKNOWN_FIELD_MASK";
        case Status::NONFINITE_VALUE: return "NONFINITE_VALUE";
        case Status::MODE_PRESENCE_MISMATCH: return "MODE_PRESENCE_MISMATCH";
        case Status::ENABLE_MODE_MISMATCH: return "ENABLE_MODE_MISMATCH";
        case Status::CONFIG_MISMATCH: return "CONFIG_MISMATCH";
        case Status::CROSS_ENVELOPE_MISMATCH: return "CROSS_ENVELOPE_MISMATCH";
        case Status::EXPIRED_COMMAND: return "EXPIRED_COMMAND";
    }
    return "UNKNOWN_STATUS";
}

Status SetText(Text* output, const char* value, size_t size, bool allow_empty,
               bool require_exact) {
    if (output == 0 || (value == 0 && size != 0)) return Status::NULL_ARGUMENT;
    const Status status = ValidateTextBytes(
        reinterpret_cast<const uint8_t*>(value), size, kMaxTextBytes,
        allow_empty, require_exact);
    if (status != Status::OK) return status;
    std::memset(output, 0, sizeof(*output));
    output->size = static_cast<uint16_t>(size);
    if (size != 0) std::memcpy(output->bytes, value, size);
    return Status::OK;
}

Status SetDetailText(DetailText* output, const char* value, size_t size,
                     bool allow_empty) {
    if (output == 0 || (value == 0 && size != 0)) return Status::NULL_ARGUMENT;
    const Status status = ValidateTextBytes(
        reinterpret_cast<const uint8_t*>(value), size, kMaxDetailBytes,
        allow_empty, false);
    if (status != Status::OK) return status;
    std::memset(output, 0, sizeof(*output));
    output->size = static_cast<uint16_t>(size);
    if (size != 0) std::memcpy(output->bytes, value, size);
    return Status::OK;
}

bool TextEquals(const Text& text, const char* value) {
    if (value == 0) return false;
    size_t size = 0;
    while (value[size] != '\0') ++size;
    return text.size == size &&
           (size == 0 || std::memcmp(text.bytes, value, size) == 0);
}

bool Sha256Equals(const Sha256& left, const Sha256& right) {
    uint8_t difference = 0;
    for (size_t index = 0; index < 32; ++index)
        difference |= left.bytes[index] ^ right.bytes[index];
    return difference == 0;
}

bool Sha256IsZero(const Sha256& value) {
    uint8_t aggregate = 0;
    for (size_t index = 0; index < 32; ++index) aggregate |= value.bytes[index];
    return aggregate == 0;
}

uint32_t Crc32c(const uint8_t* data, size_t size) {
    if (data == 0 && size != 0) return 0;
    uint32_t crc = 0xFFFFFFFFUL;
    for (size_t index = 0; index < size; ++index) {
        crc ^= data[index];
        for (uint8_t bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0x82F63B78UL &
                                static_cast<uint32_t>(
                                    -static_cast<int32_t>(crc & 1U)));
    }
    return crc ^ 0xFFFFFFFFUL;
}

Status ValidateHello(const Hello& hello) {
    Status status = ValidateText(hello.endpoint_id, false, true);
    if (status != Status::OK) return status;
    if (!EndpointRoleValid(hello.role)) return Status::INVALID_ENUM;
    if (hello.supported_major == 0 ||
        hello.minimum_minor > hello.maximum_minor) return Status::INVALID_NEGOTIATION;
    if ((hello.required_capabilities & ~kKnownCapabilities) != 0 ||
        (hello.offered_capabilities & ~kKnownCapabilities) != 0 ||
        (hello.required_capabilities & ~hello.offered_capabilities) != 0)
        return Status::INVALID_CAPABILITIES;
    if (hello.minimum_rate_hz == 0 || hello.maximum_rate_hz == 0 ||
        hello.preferred_rate_hz == 0 ||
        hello.minimum_rate_hz > kMaxControlRateHz ||
        hello.maximum_rate_hz > kMaxControlRateHz ||
        hello.preferred_rate_hz > kMaxControlRateHz ||
        hello.minimum_rate_hz > hello.maximum_rate_hz ||
        hello.preferred_rate_hz < hello.minimum_rate_hz ||
        hello.preferred_rate_hz > hello.maximum_rate_hz)
        return Status::INVALID_RATE;
    if (hello.maximum_payload_size == 0 ||
        hello.maximum_payload_size > kMaxPayloadSize)
        return Status::PAYLOAD_LIMIT;
    return Status::OK;
}

Status ValidateCapabilities(const Capabilities& capabilities) {
    if (!RejectionValid(capabilities.rejection)) return Status::INVALID_ENUM;
    if ((capabilities.selected_capabilities & ~kKnownCapabilities) != 0)
        return Status::INVALID_CAPABILITIES;
    if (capabilities.selected_rate_hz > kMaxControlRateHz ||
        capabilities.selected_payload_size > kMaxPayloadSize)
        return Status::INVALID_NEGOTIATION;
    if (capabilities.accepted) {
        if (capabilities.rejection != NegotiationRejection::NONE ||
            capabilities.selected_major != kVersionMajor ||
            capabilities.selected_minor > kVersionMinor ||
            capabilities.selected_capabilities == 0 ||
            capabilities.selected_rate_hz == 0 ||
            capabilities.selected_payload_size < kMinNegotiatedPayloadSize)
            return Status::INVALID_NEGOTIATION;
    } else if (capabilities.rejection == NegotiationRejection::NONE ||
               capabilities.selected_major != 0 ||
               capabilities.selected_minor != 0 ||
               capabilities.selected_capabilities != 0 ||
               capabilities.selected_rate_hz != 0 ||
               capabilities.selected_payload_size != 0) {
        return Status::INVALID_NEGOTIATION;
    }
    return Status::OK;
}

Status Negotiate(const Hello& local, const Hello& peer, Capabilities* result) {
    if (result == 0) return Status::NULL_ARGUMENT;
    Status status = ValidateHello(local);
    if (status != Status::OK) return status;
    status = ValidateHello(peer);
    if (status != Status::OK) return status;
    std::memset(result, 0, sizeof(*result));
    result->rejection = NegotiationRejection::NONE;
    if (local.supported_major != peer.supported_major ||
        local.supported_major != kVersionMajor) {
        result->rejection = NegotiationRejection::MAJOR_VERSION_MISMATCH;
        return Status::OK;
    }
    const uint8_t minor_low = local.minimum_minor > peer.minimum_minor
                                  ? local.minimum_minor
                                  : peer.minimum_minor;
    uint8_t minor_high = local.maximum_minor < peer.maximum_minor
                             ? local.maximum_minor
                             : peer.maximum_minor;
    if (minor_high > kVersionMinor) minor_high = kVersionMinor;
    if (minor_low > minor_high) {
        result->rejection = NegotiationRejection::MINOR_VERSION_MISMATCH;
        return Status::OK;
    }
    if ((local.required_capabilities & ~peer.offered_capabilities) != 0 ||
        (peer.required_capabilities & ~local.offered_capabilities) != 0) {
        result->rejection = NegotiationRejection::CAPABILITY_MISMATCH;
        return Status::OK;
    }
    const uint16_t rate_low = local.minimum_rate_hz > peer.minimum_rate_hz
                                  ? local.minimum_rate_hz
                                  : peer.minimum_rate_hz;
    const uint16_t rate_high = local.maximum_rate_hz < peer.maximum_rate_hz
                                   ? local.maximum_rate_hz
                                   : peer.maximum_rate_hz;
    if (rate_low > rate_high) {
        result->rejection = NegotiationRejection::RATE_MISMATCH;
        return Status::OK;
    }
    const uint32_t payload = local.maximum_payload_size < peer.maximum_payload_size
                                 ? local.maximum_payload_size
                                 : peer.maximum_payload_size;
    if (payload < kMinNegotiatedPayloadSize) {
        result->rejection = NegotiationRejection::PAYLOAD_LIMIT_MISMATCH;
        return Status::OK;
    }
    uint16_t preferred = local.preferred_rate_hz < peer.preferred_rate_hz
                             ? local.preferred_rate_hz
                             : peer.preferred_rate_hz;
    if (preferred > rate_high) preferred = rate_high;
    if (preferred < rate_low) preferred = rate_low;
    result->accepted = true;
    result->selected_major = kVersionMajor;
    result->selected_minor = minor_high;
    result->selected_capabilities =
        local.offered_capabilities & peer.offered_capabilities;
    result->selected_rate_hz = preferred;
    result->selected_payload_size = payload;
    return ValidateCapabilities(*result);
}

Status EncodeFrame(const Frame& frame, uint8_t* output, size_t capacity,
                   size_t* output_size) {
    if (output == 0 || output_size == 0) return Status::NULL_ARGUMENT;
    if (frame.major != kVersionMajor || frame.minor != kVersionMinor)
        return Status::UNSUPPORTED_VERSION;
    if (!MessageTypeValid(static_cast<uint8_t>(frame.message_type)))
        return Status::UNKNOWN_MESSAGE_TYPE;
    if ((frame.flags & ~kKnownFrameFlags) != 0) return Status::UNKNOWN_FLAGS;
    if (frame.session_id == 0) return Status::INVALID_SESSION;
    if (frame.sequence == 0) return Status::INVALID_SEQUENCE;
    if (frame.payload_size > kMaxPayloadSize) return Status::PAYLOAD_LIMIT;
    const size_t total = kHeaderSize + frame.payload_size + kCrcSize;
    if (capacity < total) return Status::OUTPUT_TOO_SMALL;
    std::memcpy(output, kMagic, sizeof(kMagic));
    output[4] = frame.major;
    output[5] = frame.minor;
    WriteU16(output + 6, static_cast<uint16_t>(kHeaderSize));
    WriteU32(output + 8, frame.payload_size);
    output[12] = static_cast<uint8_t>(frame.message_type);
    output[13] = frame.flags;
    WriteU16(output + 14, 0);
    WriteU64(output + 16, frame.session_id);
    WriteU64(output + 24, frame.sequence);
    WriteU64(output + 32, frame.monotonic_ns);
    std::memcpy(output + 40, frame.config_sha256.bytes, 32);
    if (frame.payload_size != 0)
        std::memcpy(output + kHeaderSize, frame.payload, frame.payload_size);
    WriteU32(output + kHeaderSize + frame.payload_size,
             Crc32c(output, kHeaderSize + frame.payload_size));
    *output_size = total;
    return Status::OK;
}

Status DecodeFrame(const uint8_t* data, size_t size, Frame* output) {
    if (data == 0 || output == 0) return Status::NULL_ARGUMENT;
    if (size < kHeaderSize + kCrcSize || size > kMaxFrameSize)
        return Status::FRAME_LENGTH_MISMATCH;
    if (std::memcmp(data, kMagic, sizeof(kMagic)) != 0) return Status::BAD_MAGIC;
    if (data[4] != kVersionMajor || data[5] != kVersionMinor)
        return Status::UNSUPPORTED_VERSION;
    if (ReadU16(data + 6) != kHeaderSize)
        return Status::INVALID_HEADER_LENGTH;
    const uint32_t payload_size = ReadU32(data + 8);
    if (payload_size > kMaxPayloadSize) return Status::PAYLOAD_LIMIT;
    if (size != kHeaderSize + payload_size + kCrcSize)
        return Status::FRAME_LENGTH_MISMATCH;
    if (!MessageTypeValid(data[12])) return Status::UNKNOWN_MESSAGE_TYPE;
    if ((data[13] & ~kKnownFrameFlags) != 0) return Status::UNKNOWN_FLAGS;
    if (ReadU16(data + 14) != 0) return Status::RESERVED_NONZERO;
    if (ReadU64(data + 16) == 0) return Status::INVALID_SESSION;
    if (ReadU64(data + 24) == 0) return Status::INVALID_SEQUENCE;
    if (Crc32c(data, size - kCrcSize) != ReadU32(data + size - kCrcSize))
        return Status::CRC_MISMATCH;
    std::memset(output, 0, sizeof(*output));
    output->message_type = static_cast<MessageType>(data[12]);
    output->flags = data[13];
    output->session_id = ReadU64(data + 16);
    output->sequence = ReadU64(data + 24);
    output->monotonic_ns = ReadU64(data + 32);
    std::memcpy(output->config_sha256.bytes, data + 40, 32);
    output->payload_size = payload_size;
    if (payload_size != 0)
        std::memcpy(output->payload, data + kHeaderSize, payload_size);
    output->major = data[4];
    output->minor = data[5];
    return Status::OK;
}

Status EncodeMessage(const TypedMessage& message, const Envelope& envelope,
                     uint8_t* output, size_t capacity, size_t* output_size) {
    if (output == 0 || output_size == 0) return Status::NULL_ARGUMENT;
    if (!MessageTypeValid(static_cast<uint8_t>(message.type)))
        return Status::UNKNOWN_MESSAGE_TYPE;
    if ((envelope.flags & ~kKnownFrameFlags) != 0)
        return Status::UNKNOWN_FLAGS;
    if (envelope.session_id == 0) return Status::INVALID_SESSION;
    if (envelope.sequence == 0) return Status::INVALID_SEQUENCE;
    if (capacity < kHeaderSize + kCrcSize) return Status::OUTPUT_TOO_SMALL;
    if (message.type == MessageType::COMMAND) {
        if (!Sha256Equals(message.command.config.sha256,
                          envelope.config_sha256))
            return Status::CONFIG_MISMATCH;
        if (message.command.lease_expiry_monotonic_ns <= envelope.monotonic_ns)
            return Status::EXPIRED_COMMAND;
    } else if (message.type == MessageType::STATE) {
        if (!Sha256Equals(message.state.config.sha256,
                          envelope.config_sha256))
            return Status::CONFIG_MISMATCH;
        if (message.state.sample_monotonic_ns > envelope.monotonic_ns ||
            envelope.monotonic_ns - message.state.sample_monotonic_ns !=
                message.state.sample_age_ns)
            return Status::CROSS_ENVELOPE_MISMATCH;
    } else if (message.type == MessageType::DISPOSITION &&
               message.disposition.phase_monotonic_ns > envelope.monotonic_ns) {
        return Status::CROSS_ENVELOPE_MISMATCH;
    } else if (message.type == MessageType::FAULT &&
               message.fault.occurred_monotonic_ns > envelope.monotonic_ns) {
        return Status::CROSS_ENVELOPE_MISMATCH;
    }

    size_t payload_capacity = capacity - kHeaderSize - kCrcSize;
    if (payload_capacity > kMaxPayloadSize) payload_capacity = kMaxPayloadSize;
    size_t payload_size = 0;
    Status status = EncodePayload(message, output + kHeaderSize,
                                  payload_capacity, &payload_size);
    if (status != Status::OK) return status;

    std::memcpy(output, kMagic, sizeof(kMagic));
    output[4] = kVersionMajor;
    output[5] = kVersionMinor;
    WriteU16(output + 6, static_cast<uint16_t>(kHeaderSize));
    WriteU32(output + 8, static_cast<uint32_t>(payload_size));
    output[12] = static_cast<uint8_t>(message.type);
    output[13] = envelope.flags;
    WriteU16(output + 14, 0);
    WriteU64(output + 16, envelope.session_id);
    WriteU64(output + 24, envelope.sequence);
    WriteU64(output + 32, envelope.monotonic_ns);
    std::memcpy(output + 40, envelope.config_sha256.bytes, 32);
    WriteU32(output + kHeaderSize + payload_size,
             Crc32c(output, kHeaderSize + payload_size));
    *output_size = kHeaderSize + payload_size + kCrcSize;
    return Status::OK;
}

Status DecodeMessage(const Frame& frame, TypedMessage* output) {
    if (frame.major != kVersionMajor || frame.minor != kVersionMinor)
        return Status::UNSUPPORTED_VERSION;
    if (!MessageTypeValid(static_cast<uint8_t>(frame.message_type)))
        return Status::UNKNOWN_MESSAGE_TYPE;
    if ((frame.flags & ~kKnownFrameFlags) != 0) return Status::UNKNOWN_FLAGS;
    if (frame.session_id == 0) return Status::INVALID_SESSION;
    if (frame.sequence == 0) return Status::INVALID_SEQUENCE;
    if (frame.payload_size > kMaxPayloadSize) return Status::PAYLOAD_LIMIT;
    Status status = DecodePayload(frame, output);
    if (status != Status::OK) return status;
    if (frame.message_type == MessageType::COMMAND) {
        if (!Sha256Equals(output->command.config.sha256, frame.config_sha256))
            return Status::CONFIG_MISMATCH;
        if (output->command.lease_expiry_monotonic_ns <= frame.monotonic_ns)
            return Status::EXPIRED_COMMAND;
    } else if (frame.message_type == MessageType::STATE) {
        if (!Sha256Equals(output->state.config.sha256, frame.config_sha256))
            return Status::CONFIG_MISMATCH;
        if (output->state.sample_monotonic_ns > frame.monotonic_ns ||
            frame.monotonic_ns - output->state.sample_monotonic_ns !=
                output->state.sample_age_ns)
            return Status::CROSS_ENVELOPE_MISMATCH;
    } else if (frame.message_type == MessageType::DISPOSITION &&
               output->disposition.phase_monotonic_ns > frame.monotonic_ns) {
        return Status::CROSS_ENVELOPE_MISMATCH;
    } else if (frame.message_type == MessageType::FAULT &&
               output->fault.occurred_monotonic_ns > frame.monotonic_ns) {
        return Status::CROSS_ENVELOPE_MISMATCH;
    }
    return Status::OK;
}

StreamParser::StreamParser() : buffer_(), buffered_(0), scratch_() {}

void StreamParser::reset() { buffered_ = 0; }

size_t StreamParser::bufferedBytes() const { return buffered_; }

void StreamParser::discardPrefix(size_t size) {
    if (size >= buffered_) {
        buffered_ = 0;
        return;
    }
    std::memmove(buffer_, buffer_ + size, buffered_ - size);
    buffered_ -= size;
}

Status StreamParser::feed(const uint8_t* data, size_t size,
                          FrameHandler frame_handler,
                          ParseErrorHandler error_handler, void* context,
                          ParseBatch* result) {
    if (result == 0 || (data == 0 && size != 0)) return Status::NULL_ARGUMENT;
    std::memset(result, 0, sizeof(*result));
    if (size > kMaxFeedSize) {
        reset();
        return Status::FEED_TOO_LARGE;
    }
    const size_t overflow = buffered_ + size > kMaxBufferSize
                                ? buffered_ + size - kMaxBufferSize
                                : 0;
    if (overflow != 0) {
        discardPrefix(overflow);
        AddParseError(result, error_handler, context,
                      ParseErrorCode::BUFFER_OVERFLOW, overflow,
                      Status::PAYLOAD_LIMIT);
    }
    if (size != 0) {
        std::memcpy(buffer_ + buffered_, data, size);
        buffered_ += size;
    }

    while (buffered_ != 0) {
        size_t magic_offset = buffered_;
        for (size_t index = 0; index + sizeof(kMagic) <= buffered_; ++index) {
            if (std::memcmp(buffer_ + index, kMagic, sizeof(kMagic)) == 0) {
                magic_offset = index;
                break;
            }
        }
        if (magic_offset == buffered_) {
            size_t keep = 0;
            const size_t maximum = buffered_ < sizeof(kMagic) - 1
                                       ? buffered_
                                       : sizeof(kMagic) - 1;
            for (size_t candidate = maximum; candidate > 0; --candidate) {
                if (std::memcmp(buffer_ + buffered_ - candidate, kMagic,
                                candidate) == 0) {
                    keep = candidate;
                    break;
                }
            }
            const size_t discarded = buffered_ - keep;
            if (discarded != 0) {
                discardPrefix(discarded);
                AddParseError(result, error_handler, context,
                              ParseErrorCode::NOISE_DISCARDED, discarded,
                              Status::BAD_MAGIC);
            }
            break;
        }
        if (magic_offset != 0) {
            discardPrefix(magic_offset);
            AddParseError(result, error_handler, context,
                          ParseErrorCode::NOISE_DISCARDED, magic_offset,
                          Status::BAD_MAGIC);
        }
        if (buffered_ < kHeaderSize) break;
        const uint32_t payload_size = ReadU32(buffer_ + 8);
        const bool structural =
            buffer_[4] == kVersionMajor && buffer_[5] == kVersionMinor &&
            ReadU16(buffer_ + 6) == kHeaderSize &&
            payload_size <= kMaxPayloadSize && MessageTypeValid(buffer_[12]) &&
            (buffer_[13] & ~kKnownFrameFlags) == 0 &&
            ReadU16(buffer_ + 14) == 0 && ReadU64(buffer_ + 16) != 0 &&
            ReadU64(buffer_ + 24) != 0;
        if (!structural) {
            discardPrefix(1);
            AddParseError(result, error_handler, context,
                          ParseErrorCode::INVALID_HEADER, 1,
                          Status::INVALID_HEADER_LENGTH);
            continue;
        }
        const size_t total = kHeaderSize + payload_size + kCrcSize;
        if (buffered_ < total) break;
        const Status decoded = DecodeFrame(buffer_, total, &scratch_);
        if (decoded != Status::OK) {
            discardPrefix(1);
            AddParseError(result, error_handler, context,
                          ParseErrorCode::CRC_MISMATCH, 1, decoded);
            continue;
        }
        ++result->frame_count;
        if (frame_handler != 0) frame_handler(context, scratch_);
        discardPrefix(total);
    }
    return Status::OK;
}

SessionReceiver::SessionReceiver()
    : initialized_(false),
      session_id_(0),
      config_sha256_(),
      last_sequence_(0),
      last_monotonic_ns_(0) {}

Status SessionReceiver::initialize(uint64_t active_session_id,
                                   const Sha256& active_config_sha256,
                                   const Capabilities& negotiation,
                                   uint64_t initial_sequence,
                                   uint64_t initial_monotonic_ns) {
    if (active_session_id == 0) return Status::INVALID_SESSION;
    if (Sha256IsZero(active_config_sha256)) return Status::INVALID_SHA256;
    Status status = ValidateCapabilities(negotiation);
    if (status != Status::OK) return status;
    if (!negotiation.accepted || negotiation.selected_major != kVersionMajor ||
        (negotiation.selected_capabilities & kMandatoryCapabilities) !=
            kMandatoryCapabilities)
        return Status::INVALID_NEGOTIATION;
    initialized_ = true;
    session_id_ = active_session_id;
    config_sha256_ = active_config_sha256;
    last_sequence_ = initial_sequence;
    last_monotonic_ns_ = initial_monotonic_ns;
    return Status::OK;
}

bool SessionReceiver::initialized() const { return initialized_; }

uint64_t SessionReceiver::lastSequence() const { return last_sequence_; }

ReceiveResult SessionReceiver::receive(const Frame& frame,
                                       uint64_t now_monotonic_ns, bool has_now,
                                       TypedMessage* message) {
    ReceiveResult result = {false, ReceiveDenial::NONE, false, Status::OK};
    if (!initialized_ || message == 0) {
        result.status = Status::INVALID_NEGOTIATION;
        return result;
    }
    if (frame.major != kVersionMajor || frame.minor != kVersionMinor) {
        result.denial = ReceiveDenial::UNSUPPORTED_ENVELOPE;
        return result;
    }
    if (frame.session_id != session_id_) {
        result.denial = ReceiveDenial::PREVIOUS_OR_UNKNOWN_SESSION;
        return result;
    }
    if (frame.sequence == last_sequence_) {
        result.denial = ReceiveDenial::DUPLICATE_SEQUENCE;
        return result;
    }
    if (frame.sequence < last_sequence_) {
        result.denial = ReceiveDenial::REORDERED_SEQUENCE;
        return result;
    }
    if (frame.monotonic_ns < last_monotonic_ns_) {
        result.denial = ReceiveDenial::NONMONOTONIC_TIMESTAMP;
        return result;
    }
    if (!Sha256Equals(frame.config_sha256, config_sha256_)) {
        result.denial = ReceiveDenial::CONFIG_MISMATCH;
        return result;
    }
    Status status = DecodeMessage(frame, message);
    if (status != Status::OK) {
        result.denial = ReceiveDenial::MALFORMED_BODY;
        result.status = status;
        return result;
    }
    uint64_t evaluation_time = frame.monotonic_ns;
    if (has_now) {
        if (now_monotonic_ns < frame.monotonic_ns) {
            result.denial = ReceiveDenial::INVALID_EVALUATION_TIME;
            result.status = Status::CROSS_ENVELOPE_MISMATCH;
            return result;
        }
        evaluation_time = now_monotonic_ns;
    }
    if (frame.message_type == MessageType::COMMAND &&
        message->command.lease_expiry_monotonic_ns <= evaluation_time) {
        result.denial = ReceiveDenial::EXPIRED_COMMAND;
        result.status = Status::EXPIRED_COMMAND;
        return result;
    }
    last_sequence_ = frame.sequence;
    last_monotonic_ns_ = frame.monotonic_ns;
    result.link_accepted = true;
    result.denial = ReceiveDenial::NONE;
    result.motion_authorized = false;
    return result;
}

}  // namespace hostlink_v1
}  // namespace myactuator
