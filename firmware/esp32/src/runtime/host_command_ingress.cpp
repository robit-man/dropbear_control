#include "host_command_ingress.h"

#include <cmath>
#include <cstring>
#include <limits>

namespace myactuator {
namespace runtime {
namespace {

static const uint64_t kNanosecondsPerMillisecond = 1000000ULL;
// Measured in raw IQ units. This absorbs ordinary binary64 multiplication
// noise but is far below any physically meaningful fraction of a 0.01 A LSB.
static const double kRawGridTolerance = 1.0e-9;

bool TextEqual(const hostlink_v1::Text& left,
               const hostlink_v1::Text& right) {
    return left.size == right.size &&
           (left.size == 0U ||
            std::memcmp(left.bytes, right.bytes, left.size) == 0);
}

bool TextLooksExact(const hostlink_v1::Text& text) {
    if (text.size == 0U || text.size > hostlink_v1::kMaxTextBytes) {
        return false;
    }
    for (size_t index = 0; index < text.size; ++index) {
        const uint8_t value = text.bytes[index];
        if (value < 0x21U || value > 0x7eU || value == '*' || value == '?' ||
            value == '[' || value == ']' || value == '{' || value == '}') {
            return false;
        }
    }
    return true;
}

bool ShaEqual(const hostlink_v1::Sha256& host,
              const safety::Sha256Digest& guarded) {
    return std::memcmp(host.bytes, guarded.bytes,
                       safety::kSha256DigestSize) == 0;
}

bool ShaNonzero(const hostlink_v1::Sha256& value) {
    uint8_t combined = 0U;
    for (size_t index = 0; index < sizeof(value.bytes); ++index) {
        combined = static_cast<uint8_t>(combined | value.bytes[index]);
    }
    return combined != 0U;
}

bool ParseCanonicalRevision(const hostlink_v1::Text& text,
                            uint64_t* output) {
    if (output == NULL || text.size == 0U ||
        (text.size > 1U && text.bytes[0] == '0')) {
        return false;
    }
    uint64_t value = 0U;
    for (size_t index = 0; index < text.size; ++index) {
        const uint8_t byte = text.bytes[index];
        if (byte < '0' || byte > '9') return false;
        const uint64_t digit = static_cast<uint64_t>(byte - '0');
        if (value > (std::numeric_limits<uint64_t>::max() - digit) / 10U) {
            return false;
        }
        value = value * 10U + digit;
    }
    if (value == 0U) return false;
    *output = value;
    return true;
}

bool HostConfigEqual(const hostlink_v1::ConfigIdentity& left,
                     const hostlink_v1::ConfigIdentity& right) {
    return TextEqual(left.identity, right.identity) &&
           TextEqual(left.revision, right.revision) &&
           hostlink_v1::Sha256Equals(left.sha256, right.sha256);
}

double NearestInteger(double value) {
    return value >= 0.0 ? std::floor(value + 0.5)
                        : std::ceil(value - 0.5);
}

IngressResult Result(IngressCode code) {
    IngressResult result = {};
    result.code = code;
    result.receive_denial = hostlink_v1::ReceiveDenial::NONE;
    result.host_status = hostlink_v1::Status::OK;
    return result;
}

}  // namespace

BindingCode ValidateHostCommandBinding(const HostCommandBinding& binding) {
    if (binding.host_config.identity.size > safety::kConfigIdCapacity ||
        binding.safety_config.identity.config_id.length == 0U ||
        binding.safety_config.identity.config_id.length >
            safety::kConfigIdCapacity) {
        return BindingCode::CONFIG_ID_TOO_LONG;
    }
    if (!TextLooksExact(binding.canonical_actuator_id) ||
        !TextLooksExact(binding.source_identity) ||
        !TextLooksExact(binding.lease_owner) ||
        !TextLooksExact(binding.host_config.identity) ||
        !TextLooksExact(binding.host_config.revision) ||
        !ShaNonzero(binding.host_config.sha256)) {
        return BindingCode::TEXT_INVALID;
    }
    uint64_t revision = 0U;
    if (!ParseCanonicalRevision(binding.host_config.revision, &revision)) {
        return BindingCode::CONFIG_REVISION_INVALID;
    }
    const safety::BoundedConfigId& guarded_id =
        binding.safety_config.identity.config_id;
    if (binding.host_config.identity.size != guarded_id.length ||
        std::memcmp(binding.host_config.identity.bytes, guarded_id.bytes,
                    guarded_id.length) != 0) {
        return BindingCode::CONFIG_ID_MISMATCH;
    }
    if (revision != binding.safety_config.identity.revision) {
        return BindingCode::CONFIG_REVISION_MISMATCH;
    }
    if (!ShaEqual(binding.host_config.sha256,
                  binding.safety_config.identity.digest)) {
        return BindingCode::CONFIG_DIGEST_MISMATCH;
    }
    if (binding.safety_config.identity.schema_version != 1U) {
        return BindingCode::CONFIG_SCHEMA_UNSUPPORTED;
    }
    if (binding.safety_config.generation == 0U) {
        return BindingCode::CONFIG_GENERATION_INVALID;
    }
    if (binding.safety_config.authorization_class !=
        safety::AuthorizationClass::MOTION) {
        return BindingCode::CONFIG_AUTHORIZATION_DENIED;
    }
    if (binding.route_token == 0U || binding.bus_id == 0U ||
        !rmd_v44::IsValidMotorId(binding.node_id)) {
        return BindingCode::ROUTE_INVALID;
    }
    if (binding.owner_id == 0U || binding.owner_id > 32U) {
        return BindingCode::OWNER_INVALID;
    }
    if (binding.translation != TranslationKind::RMD_V44_IQ_CURRENT_A) {
        return BindingCode::TRANSLATION_UNSUPPORTED;
    }
    if (binding.iq_amperes_per_lsb_numerator !=
            kRmdV44IqAmperesPerLsbNumerator ||
        binding.iq_amperes_per_lsb_denominator !=
            kRmdV44IqAmperesPerLsbDenominator) {
        return BindingCode::SCALE_UNSUPPORTED;
    }
    if (binding.minimum_iq_raw > binding.maximum_iq_raw) {
        return BindingCode::CURRENT_RANGE_INVALID;
    }
    return BindingCode::OK;
}

const char* BindingCodeName(BindingCode code) {
    switch (code) {
        case BindingCode::OK: return "OK";
        case BindingCode::NULL_BINDINGS: return "NULL_BINDINGS";
        case BindingCode::COUNT_INVALID: return "COUNT_INVALID";
        case BindingCode::TEXT_INVALID: return "TEXT_INVALID";
        case BindingCode::CONFIG_ID_TOO_LONG: return "CONFIG_ID_TOO_LONG";
        case BindingCode::CONFIG_REVISION_INVALID:
            return "CONFIG_REVISION_INVALID";
        case BindingCode::CONFIG_ID_MISMATCH: return "CONFIG_ID_MISMATCH";
        case BindingCode::CONFIG_REVISION_MISMATCH:
            return "CONFIG_REVISION_MISMATCH";
        case BindingCode::CONFIG_DIGEST_MISMATCH:
            return "CONFIG_DIGEST_MISMATCH";
        case BindingCode::CONFIG_SCHEMA_UNSUPPORTED:
            return "CONFIG_SCHEMA_UNSUPPORTED";
        case BindingCode::CONFIG_GENERATION_INVALID:
            return "CONFIG_GENERATION_INVALID";
        case BindingCode::CONFIG_AUTHORIZATION_DENIED:
            return "CONFIG_AUTHORIZATION_DENIED";
        case BindingCode::ROUTE_INVALID: return "ROUTE_INVALID";
        case BindingCode::OWNER_INVALID: return "OWNER_INVALID";
        case BindingCode::TRANSLATION_UNSUPPORTED:
            return "TRANSLATION_UNSUPPORTED";
        case BindingCode::SCALE_UNSUPPORTED: return "SCALE_UNSUPPORTED";
        case BindingCode::CURRENT_RANGE_INVALID:
            return "CURRENT_RANGE_INVALID";
        case BindingCode::DUPLICATE_SELECTOR: return "DUPLICATE_SELECTOR";
        case BindingCode::DUPLICATE_ROUTE: return "DUPLICATE_ROUTE";
    }
    return "UNKNOWN_BINDING_CODE";
}

const char* IngressCodeName(IngressCode code) {
    switch (code) {
        case IngressCode::OK: return "OK";
        case IngressCode::INVALID_CORE: return "INVALID_CORE";
        case IngressCode::NULL_OUTPUT: return "NULL_OUTPUT";
        case IngressCode::HOST_DENIED: return "HOST_DENIED";
        case IngressCode::NOT_COMMAND: return "NOT_COMMAND";
        case IngressCode::ACTUATOR_NOT_BOUND: return "ACTUATOR_NOT_BOUND";
        case IngressCode::SOURCE_NOT_BOUND: return "SOURCE_NOT_BOUND";
        case IngressCode::LEASE_OWNER_MISMATCH:
            return "LEASE_OWNER_MISMATCH";
        case IngressCode::CONFIG_MISMATCH: return "CONFIG_MISMATCH";
        case IngressCode::SESSION_ID_OUT_OF_RANGE:
            return "SESSION_ID_OUT_OF_RANGE";
        case IngressCode::UNSUPPORTED_MODE: return "UNSUPPORTED_MODE";
        case IngressCode::CURRENT_VALUE_INVALID:
            return "CURRENT_VALUE_INVALID";
        case IngressCode::CURRENT_NOT_ON_GRID:
            return "CURRENT_NOT_ON_GRID";
        case IngressCode::CURRENT_OUT_OF_RANGE:
            return "CURRENT_OUT_OF_RANGE";
        case IngressCode::DEADLINE_NOT_MILLISECOND_ALIGNED:
            return "DEADLINE_NOT_MILLISECOND_ALIGNED";
        case IngressCode::NATIVE_ENCODE_FAILED:
            return "NATIVE_ENCODE_FAILED";
    }
    return "UNKNOWN_INGRESS_CODE";
}

HostCommandIngress::HostCommandIngress(
    const HostCommandBinding* bindings,
    size_t binding_count,
    uint64_t active_session_id,
    const hostlink_v1::Sha256& active_config_sha256,
    const hostlink_v1::Capabilities& negotiation,
    uint64_t initial_sequence,
    uint64_t initial_monotonic_ns)
    : bindings_(bindings),
      binding_count_(binding_count),
      binding_status_(BindingCode::OK),
      session_status_(hostlink_v1::Status::OK),
      valid_(false),
      receiver_(),
      scratch_() {
    binding_status_ = validateBindings();
    if (binding_status_ != BindingCode::OK) return;
    session_status_ = receiver_.initialize(
        active_session_id, active_config_sha256, negotiation,
        initial_sequence, initial_monotonic_ns);
    valid_ = session_status_ == hostlink_v1::Status::OK;
}

bool HostCommandIngress::valid() const { return valid_; }

BindingCode HostCommandIngress::bindingStatus() const {
    return binding_status_;
}

hostlink_v1::Status HostCommandIngress::sessionStatus() const {
    return session_status_;
}

size_t HostCommandIngress::bindingCount() const { return binding_count_; }

BindingCode HostCommandIngress::validateBindings() const {
    if (bindings_ == NULL) return BindingCode::NULL_BINDINGS;
    if (binding_count_ == 0U ||
        binding_count_ > kMaximumHostCommandBindings) {
        return BindingCode::COUNT_INVALID;
    }
    for (size_t index = 0; index < binding_count_; ++index) {
        const BindingCode checked =
            ValidateHostCommandBinding(bindings_[index]);
        if (checked != BindingCode::OK) return checked;
        for (size_t previous = 0; previous < index; ++previous) {
            if (TextEqual(bindings_[index].canonical_actuator_id,
                          bindings_[previous].canonical_actuator_id) &&
                TextEqual(bindings_[index].source_identity,
                          bindings_[previous].source_identity)) {
                return BindingCode::DUPLICATE_SELECTOR;
            }
            if (bindings_[index].route_token ==
                    bindings_[previous].route_token ||
                (bindings_[index].bus_id == bindings_[previous].bus_id &&
                 bindings_[index].node_id == bindings_[previous].node_id)) {
                return BindingCode::DUPLICATE_ROUTE;
            }
        }
    }
    return BindingCode::OK;
}

const HostCommandBinding* HostCommandIngress::findBinding(
    const hostlink_v1::Command& command,
    IngressCode* denial) const {
    bool actuator_seen = false;
    for (size_t index = 0; index < binding_count_; ++index) {
        const HostCommandBinding& binding = bindings_[index];
        if (!TextEqual(command.canonical_actuator_id,
                       binding.canonical_actuator_id)) {
            continue;
        }
        actuator_seen = true;
        if (TextEqual(command.source_identity, binding.source_identity)) {
            return &binding;
        }
    }
    if (denial != NULL) {
        *denial = actuator_seen ? IngressCode::SOURCE_NOT_BOUND
                                : IngressCode::ACTUATOR_NOT_BOUND;
    }
    return NULL;
}

IngressResult HostCommandIngress::receive(
    const hostlink_v1::Frame& frame,
    uint64_t now_monotonic_ns,
    gateway::Submission* submission) {
    IngressResult result = Result(IngressCode::OK);
    result.evaluation_time_ms = now_monotonic_ns /
                                kNanosecondsPerMillisecond;
    if (!valid_) {
        result.code = IngressCode::INVALID_CORE;
        result.host_status = session_status_;
        return result;
    }
    if (submission == NULL) {
        result.code = IngressCode::NULL_OUTPUT;
        return result;
    }
    std::memset(submission, 0, sizeof(*submission));
    const hostlink_v1::ReceiveResult link = receiver_.receive(
        frame, now_monotonic_ns, true, &scratch_);
    result.link_accepted = link.link_accepted;
    result.receive_denial = link.denial;
    result.host_status = link.status;
    if (!link.link_accepted) {
        result.code = IngressCode::HOST_DENIED;
        return result;
    }
    if (scratch_.type != hostlink_v1::MessageType::COMMAND) {
        result.code = IngressCode::NOT_COMMAND;
        return result;
    }

    const hostlink_v1::Command& command = scratch_.command;
    IngressCode selection_denial = IngressCode::ACTUATOR_NOT_BOUND;
    const HostCommandBinding* binding =
        findBinding(command, &selection_denial);
    if (binding == NULL) {
        result.code = selection_denial;
        return result;
    }
    result.route_token = binding->route_token;
    if (!TextEqual(command.lease_owner, binding->lease_owner)) {
        result.code = IngressCode::LEASE_OWNER_MISMATCH;
        return result;
    }
    if (!HostConfigEqual(command.config, binding->host_config)) {
        result.code = IngressCode::CONFIG_MISMATCH;
        return result;
    }
    if (frame.session_id > std::numeric_limits<uint32_t>::max()) {
        result.code = IngressCode::SESSION_ID_OUT_OF_RANGE;
        return result;
    }
    if (command.mode != hostlink_v1::CommandMode::CURRENT_Q) {
        result.code = IngressCode::UNSUPPORTED_MODE;
        return result;
    }
    if (!command.current_q_a.present ||
        !std::isfinite(command.current_q_a.value)) {
        result.code = IngressCode::CURRENT_VALUE_INVALID;
        return result;
    }
    const double raw_value =
        command.current_q_a.value *
        static_cast<double>(binding->iq_amperes_per_lsb_denominator) /
        static_cast<double>(binding->iq_amperes_per_lsb_numerator);
    if (!std::isfinite(raw_value)) {
        result.code = IngressCode::CURRENT_VALUE_INVALID;
        return result;
    }
    const double nearest = NearestInteger(raw_value);
    if (std::fabs(raw_value - nearest) > kRawGridTolerance) {
        result.code = IngressCode::CURRENT_NOT_ON_GRID;
        return result;
    }
    if (nearest < static_cast<double>(binding->minimum_iq_raw) ||
        nearest > static_cast<double>(binding->maximum_iq_raw)) {
        result.code = IngressCode::CURRENT_OUT_OF_RANGE;
        return result;
    }
    if (command.lease_expiry_monotonic_ns %
            kNanosecondsPerMillisecond != 0U) {
        result.code = IngressCode::DEADLINE_NOT_MILLISECOND_ALIGNED;
        return result;
    }

    rmd_v44::Frame native = {};
    const rmd_v44::Error encoded = rmd_v44::EncodeIqControlRaw(
        binding->node_id, static_cast<int16_t>(nearest), &native);
    if (encoded != rmd_v44::Error::kOk) {
        result.code = IngressCode::NATIVE_ENCODE_FAILED;
        return result;
    }

    submission->route_token = binding->route_token;
    submission->bus_id = binding->bus_id;
    submission->node_id = binding->node_id;
    submission->owner_id = binding->owner_id;
    submission->traffic_class = gateway::TrafficClass::CONTROL;
    submission->config_proof.config = binding->safety_config;
    submission->config_proof.command_generation = frame.sequence;
    submission->safety_session_id = static_cast<uint32_t>(frame.session_id);
    submission->safety_sequence = command.lease_sequence;
    submission->absolute_deadline_ms =
        command.lease_expiry_monotonic_ns / kNanosecondsPerMillisecond;
    submission->frame = native;
    result.code = IngressCode::OK;
    return result;
}

}  // namespace runtime
}  // namespace myactuator
