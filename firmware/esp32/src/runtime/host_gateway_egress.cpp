#include "host_gateway_egress.h"

#include <cstring>
#include <limits>

namespace myactuator {
namespace runtime {
namespace {

static const uint64_t kNanosecondsPerMillisecond = 1000000ULL;
static const double kPi = 3.14159265358979323846264338327950288;

bool TextValid(const hostlink_v1::Text& text) {
    if (text.size == 0U || text.size > hostlink_v1::kMaxTextBytes) {
        return false;
    }
    hostlink_v1::Text checked = {};
    return hostlink_v1::SetText(
               &checked, reinterpret_cast<const char*>(text.bytes), text.size) ==
           hostlink_v1::Status::OK;
}

bool ShaNonzero(const hostlink_v1::Sha256& sha) {
    uint8_t combined = 0U;
    for (size_t index = 0; index < sizeof(sha.bytes); ++index) {
        combined = static_cast<uint8_t>(combined | sha.bytes[index]);
    }
    return combined != 0U;
}

bool ContextValid(const HostRequestCorrelation& context) {
    return context.request_session_id != 0U &&
           context.request_sequence != 0U &&
           context.safety_sequence != 0U && context.transaction_id != 0U &&
           TextValid(context.canonical_actuator_id) &&
           TextValid(context.config.identity) &&
           TextValid(context.config.revision) &&
           ShaNonzero(context.config.sha256) && context.route_token != 0U &&
           context.bus_id != 0U && rmd_v44::IsValidMotorId(context.node_id) &&
           context.owner_id > 0U && context.owner_id <= 32U;
}

bool EventCorrelates(const HostRequestCorrelation& context,
                     const gateway::Disposition& event) {
    return event.transaction_id == context.transaction_id &&
           event.route_token == context.route_token &&
           event.bus_id == context.bus_id && event.node_id == context.node_id &&
           event.owner_id == context.owner_id &&
           event.session_id == context.request_session_id &&
           event.sequence == context.safety_sequence &&
           event.command_generation == context.request_sequence;
}

EgressCode Phase(gateway::Phase phase,
                 hostlink_v1::DispositionPhase* output) {
    if (output == NULL) return EgressCode::NULL_OUTPUT;
    switch (phase) {
        case gateway::Phase::RECEIVED:
            *output = hostlink_v1::DispositionPhase::RECEIVED;
            return EgressCode::OK;
        case gateway::Phase::ADMITTED:
            *output = hostlink_v1::DispositionPhase::ADMITTED;
            return EgressCode::OK;
        case gateway::Phase::NATIVE_TX:
            *output = hostlink_v1::DispositionPhase::NATIVE_TX;
            return EgressCode::OK;
        case gateway::Phase::NATIVE_RESPONSE:
            *output = hostlink_v1::DispositionPhase::NATIVE_RESPONSE;
            return EgressCode::OK;
        case gateway::Phase::OBSERVED:
            *output = hostlink_v1::DispositionPhase::OBSERVED;
            return EgressCode::OK;
        case gateway::Phase::REJECTED:
            *output = hostlink_v1::DispositionPhase::REJECTED;
            return EgressCode::OK;
    }
    return EgressCode::PHASE_UNMAPPED;
}

bool GatewayCodeKnown(gateway::Code code) {
    switch (code) {
        case gateway::Code::OK:
        case gateway::Code::CORE_INVALID:
        case gateway::Code::ROUTE_NOT_FOUND:
        case gateway::Code::ROUTE_MISMATCH:
        case gateway::Code::OWNER_MISMATCH:
        case gateway::Code::INVALID_REQUEST_FRAME:
        case gateway::Code::OPCODE_NOT_ALLOWED:
        case gateway::Code::TRAFFIC_CLASS_MISMATCH:
        case gateway::Code::BRAKE_UNSUPPORTED:
        case gateway::Code::SAFETY_OPCODE_WRONG_LANE:
        case gateway::Code::DEADLINE_INVALID:
        case gateway::Code::DEADLINE_EXPIRED:
        case gateway::Code::CONTROL_QUEUE_FULL:
        case gateway::Code::DIAGNOSTIC_QUEUE_FULL:
        case gateway::Code::CONFIG_DENIED:
        case gateway::Code::SAFETY_DENIED:
        case gateway::Code::REPLAY_REJECTED:
        case gateway::Code::LEASE_EXPIRED:
        case gateway::Code::RESPONSE_SLOT_FULL:
        case gateway::Code::RESPONSE_OUTSTANDING:
        case gateway::Code::RESPONSE_PREEMPTED_BY_SAFETY:
        case gateway::Code::RESPONSE_TIMEOUT:
        case gateway::Code::RESPONSE_BEFORE_TRANSMIT:
        case gateway::Code::RESPONSE_MALFORMED:
        case gateway::Code::RESPONSE_UNEXPECTED_NODE:
        case gateway::Code::RESPONSE_UNEXPECTED_OPCODE:
        case gateway::Code::RESPONSE_UNEXPECTED:
        case gateway::Code::RESPONSE_DUPLICATE:
        case gateway::Code::OBSERVATION_BEFORE_RESPONSE:
        case gateway::Code::OBSERVATION_NOT_STATE:
        case gateway::Code::TRANSACTION_NOT_FOUND:
        case gateway::Code::DIAGNOSTIC_BUDGET_EXHAUSTED:
        case gateway::Code::CYCLE_REGRESSION:
        case gateway::Code::SAFETY_ACTION_UNCONFIGURED:
        case gateway::Code::SAFETY_ACTION_NOT_REQUIRED:
        case gateway::Code::TRANSACTION_ID_EXHAUSTED:
        case gateway::Code::TIME_OVERFLOW:
        case gateway::Code::TRANSPORT_TX_FAILED:
        case gateway::Code::TRANSPORT_BUS_OFF:
            return true;
    }
    return false;
}

EgressCode SetReason(hostlink_v1::Text* output,
                     gateway::Phase phase,
                     gateway::Code code) {
    if (output == NULL) return EgressCode::NULL_OUTPUT;
    if (!GatewayCodeKnown(code)) return EgressCode::GATEWAY_CODE_UNMAPPED;
    const char* reason = phase == gateway::Phase::REJECTED
                             ? gateway::CodeName(code)
                             : "NONE";
    return hostlink_v1::SetText(output, reason, std::strlen(reason), false,
                                phase == gateway::Phase::REJECTED) ==
                   hostlink_v1::Status::OK
               ? EgressCode::OK
               : EgressCode::HOST_TEXT_REJECTED;
}

EgressCode SafetyState(safety::State state,
                       hostlink_v1::SafetyState* output) {
    if (output == NULL) return EgressCode::NULL_OUTPUT;
    switch (state) {
        case safety::State::BOOT:
            *output = hostlink_v1::SafetyState::BOOT;
            return EgressCode::OK;
        case safety::State::DISCOVERY:
            *output = hostlink_v1::SafetyState::DISCOVERY;
            return EgressCode::OK;
        case safety::State::DISABLED:
            *output = hostlink_v1::SafetyState::DISABLED;
            return EgressCode::OK;
        case safety::State::ARMED:
            *output = hostlink_v1::SafetyState::ARMED;
            return EgressCode::OK;
        case safety::State::ENABLED:
            *output = hostlink_v1::SafetyState::ENABLED;
            return EgressCode::OK;
        case safety::State::SHUTDOWN:
            *output = hostlink_v1::SafetyState::SHUTDOWN;
            return EgressCode::OK;
        case safety::State::FAULT:
            *output = hostlink_v1::SafetyState::FAULT;
            return EgressCode::OK;
    }
    return EgressCode::SAFETY_STATE_UNMAPPED;
}

bool MillisecondsToNanoseconds(uint64_t value, uint64_t* output) {
    if (output == NULL ||
        value > std::numeric_limits<uint64_t>::max() /
                    kNanosecondsPerMillisecond) {
        return false;
    }
    *output = value * kNanosecondsPerMillisecond;
    return true;
}

double DegreesToRadians(double degrees) {
    return degrees * kPi / 180.0;
}

}  // namespace

const char* EgressCodeName(EgressCode code) {
    switch (code) {
        case EgressCode::OK: return "OK";
        case EgressCode::NULL_OUTPUT: return "NULL_OUTPUT";
        case EgressCode::CONTEXT_INVALID: return "CONTEXT_INVALID";
        case EgressCode::CORRELATION_MISMATCH:
            return "CORRELATION_MISMATCH";
        case EgressCode::PHASE_UNMAPPED: return "PHASE_UNMAPPED";
        case EgressCode::GATEWAY_CODE_UNMAPPED:
            return "GATEWAY_CODE_UNMAPPED";
        case EgressCode::TIME_OVERFLOW: return "TIME_OVERFLOW";
        case EgressCode::OBSERVATION_REQUIRED:
            return "OBSERVATION_REQUIRED";
        case EgressCode::RESPONSE_KIND_MISMATCH:
            return "RESPONSE_KIND_MISMATCH";
        case EgressCode::SAFETY_STATE_UNMAPPED:
            return "SAFETY_STATE_UNMAPPED";
        case EgressCode::HOST_TEXT_REJECTED:
            return "HOST_TEXT_REJECTED";
    }
    return "UNKNOWN_EGRESS_CODE";
}

EgressCode BuildHostDisposition(
    const HostRequestCorrelation& context,
    const gateway::Disposition& event,
    hostlink_v1::TypedMessage* output) {
    if (output == NULL) return EgressCode::NULL_OUTPUT;
    std::memset(output, 0, sizeof(*output));
    if (!ContextValid(context)) return EgressCode::CONTEXT_INVALID;
    if (!EventCorrelates(context, event)) {
        return EgressCode::CORRELATION_MISMATCH;
    }
    uint64_t phase_ns = 0U;
    if (!MillisecondsToNanoseconds(event.monotonic_ms, &phase_ns)) {
        return EgressCode::TIME_OVERFLOW;
    }
    output->type = hostlink_v1::MessageType::DISPOSITION;
    hostlink_v1::Disposition& disposition = output->disposition;
    disposition.request_session_id = context.request_session_id;
    disposition.request_sequence = context.request_sequence;
    disposition.canonical_actuator_id = context.canonical_actuator_id;
    disposition.phase_monotonic_ns = phase_ns;
    EgressCode code = Phase(event.phase, &disposition.phase);
    if (code != EgressCode::OK) return code;
    return SetReason(&disposition.reason_code, event.phase, event.code);
}

EgressCode BuildObservedHostState(
    const HostRequestCorrelation& context,
    const gateway::Disposition& observation,
    const rmd_v44::DecodedResponse& response,
    uint64_t native_sample_monotonic_ms,
    uint64_t now_monotonic_ms,
    safety::State safety_state,
    const ObservedStatePolicy& policy,
    hostlink_v1::TypedMessage* output) {
    if (output == NULL) return EgressCode::NULL_OUTPUT;
    std::memset(output, 0, sizeof(*output));
    if (!ContextValid(context) || policy.maximum_sample_age_ms == 0U) {
        return EgressCode::CONTEXT_INVALID;
    }
    if (!EventCorrelates(context, observation)) {
        return EgressCode::CORRELATION_MISMATCH;
    }
    if (observation.phase != gateway::Phase::OBSERVED ||
        observation.code != gateway::Code::OK ||
        observation.observation_class !=
            gateway::ObservationClass::NATIVE_STATE_SAMPLE) {
        return EgressCode::OBSERVATION_REQUIRED;
    }
    if (observation.response_kind == rmd_v44::ResponseKind::kNone ||
        observation.response_kind == rmd_v44::ResponseKind::kEcho ||
        observation.response_kind != response.kind ||
        observation.node_id != response.motor_id ||
        observation.opcode != static_cast<uint8_t>(response.command)) {
        return EgressCode::RESPONSE_KIND_MISMATCH;
    }
    if (native_sample_monotonic_ms > observation.monotonic_ms ||
        observation.monotonic_ms > now_monotonic_ms) {
        return EgressCode::CORRELATION_MISMATCH;
    }
    uint64_t sample_ns = 0U;
    uint64_t age_ns = 0U;
    if (!MillisecondsToNanoseconds(native_sample_monotonic_ms, &sample_ns) ||
        !MillisecondsToNanoseconds(now_monotonic_ms -
                                      native_sample_monotonic_ms,
                                  &age_ns)) {
        return EgressCode::TIME_OVERFLOW;
    }

    output->type = hostlink_v1::MessageType::STATE;
    hostlink_v1::State& state = output->state;
    state.canonical_actuator_id = context.canonical_actuator_id;
    state.config = context.config;
    state.sample_monotonic_ns = sample_ns;
    state.sample_age_ns = age_ns;
    state.validity = now_monotonic_ms - native_sample_monotonic_ms <=
                             policy.maximum_sample_age_ms
                         ? hostlink_v1::SampleValidity::VALID
                         : hostlink_v1::SampleValidity::STALE;
    state.connectivity = hostlink_v1::Connectivity::CONNECTED;
    state.drive_health = hostlink_v1::DriveHealth::UNKNOWN;
    state.bus_health = hostlink_v1::BusHealth::UNKNOWN;
    state.native_response = hostlink_v1::NativeResponseState::VALID;
    if (hostlink_v1::SetText(&state.fault_code, "NONE", 4U, false, false) !=
        hostlink_v1::Status::OK) {
        return EgressCode::HOST_TEXT_REJECTED;
    }
    EgressCode safety_code = SafetyState(safety_state, &state.safety_state);
    if (safety_code != EgressCode::OK) return safety_code;

    switch (response.kind) {
        case rmd_v44::ResponseKind::kAngle:
            state.position_rad = {
                true, DegreesToRadians(
                          static_cast<double>(response.angle_i32_raw) * 0.01)};
            break;
        case rmd_v44::ResponseKind::kStatus1:
            state.temperature_c = {
                true, static_cast<double>(response.motor_temperature_c)};
            state.voltage_v = {
                true, static_cast<double>(response.voltage_raw) * 0.1};
            state.native_fault_mask = {true, response.error_mask};
            state.drive_health = response.error_mask == 0U
                                     ? hostlink_v1::DriveHealth::OK
                                     : hostlink_v1::DriveHealth::FAULT;
            if (response.error_mask != 0U &&
                hostlink_v1::SetText(&state.fault_code,
                                     "RMD_V44_STATUS1_ERROR",
                                     std::strlen("RMD_V44_STATUS1_ERROR")) !=
                    hostlink_v1::Status::OK) {
                return EgressCode::HOST_TEXT_REJECTED;
            }
            break;
        case rmd_v44::ResponseKind::kMotionStatus:
            state.position_rad = {
                true, DegreesToRadians(
                          static_cast<double>(response.output_angle_raw))};
            state.velocity_rad_s = {
                true, DegreesToRadians(
                          static_cast<double>(response.output_speed_raw))};
            state.current_q_a = {
                true, static_cast<double>(response.iq_raw) * 0.01};
            state.temperature_c = {
                true, static_cast<double>(response.motor_temperature_c)};
            break;
        case rmd_v44::ResponseKind::kPhaseStatus:
            state.temperature_c = {
                true, static_cast<double>(response.motor_temperature_c)};
            break;
        case rmd_v44::ResponseKind::kOperatingMode:
            break;
        case rmd_v44::ResponseKind::kNone:
        case rmd_v44::ResponseKind::kEcho:
            return EgressCode::RESPONSE_KIND_MISMATCH;
    }
    // No V4.4 response field is torque at the output.
    state.effort_nm.present = false;
    return EgressCode::OK;
}

EgressCode BuildHostEgressEnvelope(
    uint64_t gateway_session_id,
    uint64_t gateway_sequence,
    uint64_t monotonic_ns,
    const hostlink_v1::Sha256& active_config_sha256,
    const hostlink_v1::TypedMessage& message,
    hostlink_v1::Envelope* output) {
    if (output == NULL) return EgressCode::NULL_OUTPUT;
    std::memset(output, 0, sizeof(*output));
    if (gateway_session_id == 0U || gateway_sequence == 0U ||
        !ShaNonzero(active_config_sha256)) {
        return EgressCode::CONTEXT_INVALID;
    }
    if (message.type == hostlink_v1::MessageType::STATE &&
        message.state.sample_monotonic_ns > monotonic_ns) {
        return EgressCode::CORRELATION_MISMATCH;
    }
    if (message.type == hostlink_v1::MessageType::DISPOSITION &&
        message.disposition.phase_monotonic_ns > monotonic_ns) {
        return EgressCode::CORRELATION_MISMATCH;
    }
    output->session_id = gateway_session_id;
    output->sequence = gateway_sequence;
    output->monotonic_ns = monotonic_ns;
    output->config_sha256 = active_config_sha256;
    return EgressCode::OK;
}

}  // namespace runtime
}  // namespace myactuator
