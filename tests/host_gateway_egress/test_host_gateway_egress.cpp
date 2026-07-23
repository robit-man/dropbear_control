#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <cmath>
#include <limits>

#include "host_gateway_egress.h"
#include "hostlink_v1.h"

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

void Set(host::Text* output, const char* value) {
    CHECK(host::SetText(output, value, strlen(value)) == host::Status::OK);
}

host::Sha256 Digest() {
    host::Sha256 value = {};
    for (size_t index = 0; index < sizeof(value.bytes); ++index) {
        value.bytes[index] = static_cast<uint8_t>(0x40U + index);
    }
    return value;
}

rt::HostRequestCorrelation Context() {
    rt::HostRequestCorrelation value = {};
    value.request_session_id = 0x12345678U;
    value.request_sequence = 30U;
    value.safety_sequence = 40U;
    value.transaction_id = 50U;
    Set(&value.canonical_actuator_id, "joint.left.hip");
    Set(&value.config.identity, "synthetic-v44-node1");
    Set(&value.config.revision, "1");
    value.config.sha256 = Digest();
    value.route_token = 7U;
    value.bus_id = 1U;
    value.node_id = 1U;
    value.owner_id = 1U;
    return value;
}

gw::Disposition Event(gw::Phase phase = gw::Phase::OBSERVED,
                      gw::Code code = gw::Code::OK) {
    const rt::HostRequestCorrelation context = Context();
    gw::Disposition value = {};
    value.event_id = 60U;
    value.transaction_id = context.transaction_id;
    value.monotonic_ms = 11U;
    value.phase = phase;
    value.code = code;
    value.route_token = context.route_token;
    value.bus_id = context.bus_id;
    value.node_id = context.node_id;
    value.opcode = static_cast<uint8_t>(v44::Command::kIqControl);
    value.traffic_class = gw::TrafficClass::CONTROL;
    value.owner_id = context.owner_id;
    value.session_id = static_cast<uint32_t>(context.request_session_id);
    value.sequence = context.safety_sequence;
    value.command_generation = context.request_sequence;
    value.response_kind = v44::ResponseKind::kMotionStatus;
    value.observation_class = gw::ObservationClass::NATIVE_STATE_SAMPLE;
    return value;
}

v44::DecodedResponse Response(v44::ResponseKind kind =
                                  v44::ResponseKind::kMotionStatus) {
    v44::DecodedResponse value = {};
    value.kind = kind;
    value.motor_id = 1U;
    value.command = v44::Command::kIqControl;
    value.motor_temperature_c = 42;
    value.iq_raw = -125;
    value.output_speed_raw = 90;
    value.output_angle_raw = -45;
    return value;
}

bool Nearly(double left, double right) {
    return std::fabs(left - right) < 1.0e-12;
}

void TestDispositionPhaseAndReasonMapping() {
    const gw::Phase gateway_phases[] = {
        gw::Phase::RECEIVED,        gw::Phase::ADMITTED,
        gw::Phase::NATIVE_TX,       gw::Phase::NATIVE_RESPONSE,
        gw::Phase::OBSERVED,        gw::Phase::REJECTED,
    };
    const host::DispositionPhase host_phases[] = {
        host::DispositionPhase::RECEIVED,
        host::DispositionPhase::ADMITTED,
        host::DispositionPhase::NATIVE_TX,
        host::DispositionPhase::NATIVE_RESPONSE,
        host::DispositionPhase::OBSERVED,
        host::DispositionPhase::REJECTED,
    };
    for (size_t index = 0; index < 6U; ++index) {
        host::TypedMessage message = {};
        const gw::Code code = gateway_phases[index] == gw::Phase::REJECTED
                                  ? gw::Code::RESPONSE_TIMEOUT
                                  : gw::Code::OK;
        CHECK(rt::BuildHostDisposition(Context(),
                                       Event(gateway_phases[index], code),
                                       &message) == rt::EgressCode::OK);
        CHECK(message.type == host::MessageType::DISPOSITION);
        CHECK(message.disposition.phase == host_phases[index]);
        CHECK(message.disposition.phase_monotonic_ns == 11000000U);
        CHECK(host::TextEquals(
            message.disposition.reason_code,
            gateway_phases[index] == gw::Phase::REJECTED
                ? "RESPONSE_TIMEOUT"
                : "NONE"));
    }

    // Every currently declared gateway code has a stable rejection reason.
    for (uint8_t raw = 0U;
         raw <= static_cast<uint8_t>(gw::Code::TRANSPORT_BUS_OFF); ++raw) {
        host::TypedMessage message = {};
        CHECK(rt::BuildHostDisposition(
                  Context(), Event(gw::Phase::REJECTED,
                                   static_cast<gw::Code>(raw)),
                  &message) == rt::EgressCode::OK);
        CHECK(!host::TextEquals(message.disposition.reason_code, "NONE"));
    }
    host::TypedMessage output = {};
    CHECK(rt::BuildHostDisposition(
              Context(), Event(gw::Phase::REJECTED,
                               static_cast<gw::Code>(255U)),
              &output) == rt::EgressCode::GATEWAY_CODE_UNMAPPED);
    gw::Disposition invalid_phase = Event();
    invalid_phase.phase = static_cast<gw::Phase>(255U);
    CHECK(rt::BuildHostDisposition(Context(), invalid_phase, &output) ==
          rt::EgressCode::PHASE_UNMAPPED);
}

void TestDispositionCorrelationAndTime() {
    host::TypedMessage output = {};
    rt::HostRequestCorrelation context = Context();
    gw::Disposition event = Event();
    CHECK(rt::BuildHostDisposition(context, event, NULL) ==
          rt::EgressCode::NULL_OUTPUT);
    context.request_sequence = 0U;
    CHECK(rt::BuildHostDisposition(context, event, &output) ==
          rt::EgressCode::CONTEXT_INVALID);

    context = Context();
    event.transaction_id += 1U;
    CHECK(rt::BuildHostDisposition(context, event, &output) ==
          rt::EgressCode::CORRELATION_MISMATCH);
    event = Event();
    event.route_token += 1U;
    CHECK(rt::BuildHostDisposition(context, event, &output) ==
          rt::EgressCode::CORRELATION_MISMATCH);
    event = Event();
    event.bus_id += 1U;
    CHECK(rt::BuildHostDisposition(context, event, &output) ==
          rt::EgressCode::CORRELATION_MISMATCH);
    event = Event();
    event.node_id += 1U;
    CHECK(rt::BuildHostDisposition(context, event, &output) ==
          rt::EgressCode::CORRELATION_MISMATCH);
    event = Event();
    event.owner_id += 1U;
    CHECK(rt::BuildHostDisposition(context, event, &output) ==
          rt::EgressCode::CORRELATION_MISMATCH);
    event = Event();
    event.session_id += 1U;
    CHECK(rt::BuildHostDisposition(context, event, &output) ==
          rt::EgressCode::CORRELATION_MISMATCH);
    event = Event();
    event.sequence += 1U;
    CHECK(rt::BuildHostDisposition(context, event, &output) ==
          rt::EgressCode::CORRELATION_MISMATCH);
    event = Event();
    event.command_generation += 1U;
    CHECK(rt::BuildHostDisposition(context, event, &output) ==
          rt::EgressCode::CORRELATION_MISMATCH);
    event = Event();
    event.monotonic_ms = std::numeric_limits<uint64_t>::max();
    CHECK(rt::BuildHostDisposition(context, event, &output) ==
          rt::EgressCode::TIME_OVERFLOW);
}

void TestMotionStateIsTypedNotTorque() {
    host::TypedMessage message = {};
    CHECK(rt::BuildObservedHostState(
              Context(), Event(), Response(), 10U, 12U,
              safety::State::ENABLED, {5U}, &message) == rt::EgressCode::OK);
    CHECK(message.type == host::MessageType::STATE);
    const host::State& state = message.state;
    CHECK(state.sample_monotonic_ns == 10000000U);
    CHECK(state.sample_age_ns == 2000000U);
    CHECK(state.validity == host::SampleValidity::VALID);
    CHECK(state.connectivity == host::Connectivity::CONNECTED);
    CHECK(state.drive_health == host::DriveHealth::UNKNOWN);
    CHECK(state.bus_health == host::BusHealth::UNKNOWN);
    CHECK(state.native_response == host::NativeResponseState::VALID);
    CHECK(state.safety_state == host::SafetyState::ENABLED);
    CHECK(state.position_rad.present &&
          Nearly(state.position_rad.value, -3.14159265358979323846 / 4.0));
    CHECK(state.velocity_rad_s.present &&
          Nearly(state.velocity_rad_s.value, 3.14159265358979323846 / 2.0));
    CHECK(state.current_q_a.present &&
          Nearly(state.current_q_a.value, -1.25));
    CHECK(state.temperature_c.present &&
          Nearly(state.temperature_c.value, 42.0));
    CHECK(!state.effort_nm.present);
    CHECK(!state.voltage_v.present);
    CHECK(!state.native_fault_mask.present);

    host::Envelope envelope = {};
    CHECK(rt::BuildHostEgressEnvelope(9U, 1U, 12000000U, Digest(), message,
                                      &envelope) == rt::EgressCode::OK);
    static uint8_t bytes[host::kMaxFrameSize];
    size_t size = 0U;
    CHECK(host::EncodeMessage(message, envelope, bytes, sizeof(bytes), &size) ==
          host::Status::OK);
    host::Frame frame = {};
    host::TypedMessage decoded = {};
    CHECK(host::DecodeFrame(bytes, size, &frame) == host::Status::OK);
    CHECK(host::DecodeMessage(frame, &decoded) == host::Status::OK);
    CHECK(decoded.state.current_q_a.present);
    CHECK(!decoded.state.effort_nm.present);
}

void TestResponseKindFieldClosure() {
    host::TypedMessage message = {};
    gw::Disposition event = Event();
    v44::DecodedResponse response = Response(v44::ResponseKind::kAngle);
    event.response_kind = response.kind;
    event.opcode = static_cast<uint8_t>(v44::Command::kReadMultiTurnAngle);
    response.command = v44::Command::kReadMultiTurnAngle;
    response.angle_i32_raw = 9000;
    CHECK(rt::BuildObservedHostState(Context(), event, response, 10U, 12U,
                                     safety::State::DISABLED, {5U}, &message) ==
          rt::EgressCode::OK);
    CHECK(message.state.position_rad.present &&
          Nearly(message.state.position_rad.value,
                 3.14159265358979323846 / 2.0));
    CHECK(!message.state.current_q_a.present);

    event = Event();
    response = Response(v44::ResponseKind::kStatus1);
    event.response_kind = response.kind;
    event.opcode = static_cast<uint8_t>(v44::Command::kReadStatus1);
    response.command = v44::Command::kReadStatus1;
    response.voltage_raw = 482U;
    response.error_mask = 0U;
    CHECK(rt::BuildObservedHostState(Context(), event, response, 10U, 12U,
                                     safety::State::ARMED, {5U}, &message) ==
          rt::EgressCode::OK);
    CHECK(message.state.drive_health == host::DriveHealth::OK);
    CHECK(message.state.voltage_v.present &&
          Nearly(message.state.voltage_v.value, 48.2));
    CHECK(message.state.native_fault_mask.present &&
          message.state.native_fault_mask.value == 0U);
    CHECK(host::TextEquals(message.state.fault_code, "NONE"));

    response.error_mask = 0x0002U;
    CHECK(rt::BuildObservedHostState(Context(), event, response, 10U, 12U,
                                     safety::State::FAULT, {5U}, &message) ==
          rt::EgressCode::OK);
    CHECK(message.state.drive_health == host::DriveHealth::FAULT);
    CHECK(host::TextEquals(message.state.fault_code,
                           "RMD_V44_STATUS1_ERROR"));

    event = Event();
    response = Response(v44::ResponseKind::kPhaseStatus);
    event.response_kind = response.kind;
    event.opcode = static_cast<uint8_t>(v44::Command::kReadStatus3);
    response.command = v44::Command::kReadStatus3;
    CHECK(rt::BuildObservedHostState(Context(), event, response, 10U, 20U,
                                     safety::State::SHUTDOWN, {5U}, &message) ==
          rt::EgressCode::OK);
    CHECK(message.state.validity == host::SampleValidity::STALE);
    CHECK(message.state.temperature_c.present);
    CHECK(!message.state.current_q_a.present);

    event = Event();
    response = Response(v44::ResponseKind::kOperatingMode);
    event.response_kind = response.kind;
    event.opcode = static_cast<uint8_t>(v44::Command::kOperatingMode);
    response.command = v44::Command::kOperatingMode;
    CHECK(rt::BuildObservedHostState(Context(), event, response, 10U, 12U,
                                     safety::State::BOOT, {5U}, &message) ==
          rt::EgressCode::OK);
    CHECK(!message.state.position_rad.present);
    CHECK(!message.state.current_q_a.present);
    CHECK(!message.state.effort_nm.present);
}

void TestObservationDenialsAndSafetyMap() {
    host::TypedMessage message = {};
    gw::Disposition event = Event();
    v44::DecodedResponse response = Response();
    CHECK(rt::BuildObservedHostState(Context(), event, response, 10U, 12U,
                                     safety::State::ENABLED, {5U}, NULL) ==
          rt::EgressCode::NULL_OUTPUT);
    event.phase = gw::Phase::NATIVE_RESPONSE;
    CHECK(rt::BuildObservedHostState(Context(), event, response, 10U, 12U,
                                     safety::State::ENABLED, {5U}, &message) ==
          rt::EgressCode::OBSERVATION_REQUIRED);
    event = Event();
    event.response_kind = v44::ResponseKind::kEcho;
    response.kind = v44::ResponseKind::kEcho;
    CHECK(rt::BuildObservedHostState(Context(), event, response, 10U, 12U,
                                     safety::State::ENABLED, {5U}, &message) ==
          rt::EgressCode::RESPONSE_KIND_MISMATCH);
    event = Event();
    response = Response();
    response.motor_id = 2U;
    CHECK(rt::BuildObservedHostState(Context(), event, response, 10U, 12U,
                                     safety::State::ENABLED, {5U}, &message) ==
          rt::EgressCode::RESPONSE_KIND_MISMATCH);
    response = Response();
    CHECK(rt::BuildObservedHostState(Context(), event, response, 12U, 11U,
                                     safety::State::ENABLED, {5U}, &message) ==
          rt::EgressCode::CORRELATION_MISMATCH);
    CHECK(rt::BuildObservedHostState(Context(), event, response, 10U, 12U,
                                     safety::State::ENABLED, {0U}, &message) ==
          rt::EgressCode::CONTEXT_INVALID);

    const safety::State safety_states[] = {
        safety::State::BOOT,     safety::State::DISCOVERY,
        safety::State::DISABLED, safety::State::ARMED,
        safety::State::ENABLED,  safety::State::SHUTDOWN,
        safety::State::FAULT,
    };
    for (size_t index = 0U; index < 7U; ++index) {
        CHECK(rt::BuildObservedHostState(Context(), Event(), Response(), 10U,
                                         12U, safety_states[index], {5U},
                                         &message) == rt::EgressCode::OK);
    }
    CHECK(rt::BuildObservedHostState(
              Context(), Event(), Response(), 10U, 12U,
              static_cast<safety::State>(255U), {5U}, &message) ==
          rt::EgressCode::SAFETY_STATE_UNMAPPED);
}

void TestEnvelopeAndDispositionRoundTrip() {
    host::TypedMessage message = {};
    CHECK(rt::BuildHostDisposition(
              Context(), Event(gw::Phase::REJECTED,
                               gw::Code::TRANSPORT_BUS_OFF),
              &message) == rt::EgressCode::OK);
    host::Envelope envelope = {};
    CHECK(rt::BuildHostEgressEnvelope(9U, 2U, 11000000U, Digest(), message,
                                      &envelope) == rt::EgressCode::OK);
    static uint8_t bytes[host::kMaxFrameSize];
    size_t size = 0U;
    CHECK(host::EncodeMessage(message, envelope, bytes, sizeof(bytes), &size) ==
          host::Status::OK);
    host::Frame frame = {};
    host::TypedMessage decoded = {};
    CHECK(host::DecodeFrame(bytes, size, &frame) == host::Status::OK);
    CHECK(host::DecodeMessage(frame, &decoded) == host::Status::OK);
    CHECK(decoded.disposition.phase == host::DispositionPhase::REJECTED);
    CHECK(host::TextEquals(decoded.disposition.reason_code,
                           "TRANSPORT_BUS_OFF"));

    CHECK(rt::BuildHostEgressEnvelope(0U, 1U, 1U, Digest(), message,
                                      &envelope) ==
          rt::EgressCode::CONTEXT_INVALID);
    CHECK(rt::BuildHostEgressEnvelope(1U, 0U, 1U, Digest(), message,
                                      &envelope) ==
          rt::EgressCode::CONTEXT_INVALID);
    CHECK(rt::BuildHostEgressEnvelope(1U, 1U, 10000000U, Digest(), message,
                                      &envelope) ==
          rt::EgressCode::CORRELATION_MISMATCH);
    CHECK(strcmp(rt::EgressCodeName(rt::EgressCode::OK), "OK") == 0);
    CHECK(strcmp(rt::EgressCodeName(static_cast<rt::EgressCode>(255U)),
                 "UNKNOWN_EGRESS_CODE") == 0);
}

}  // namespace

int main() {
    TestDispositionPhaseAndReasonMapping();
    TestDispositionCorrelationAndTime();
    TestMotionStateIsTypedNotTorque();
    TestResponseKindFieldClosure();
    TestObservationDenialsAndSafetyMap();
    TestEnvelopeAndDispositionRoundTrip();
    if (failures != 0) {
        fprintf(stderr, "host gateway egress failures=%d\n", failures);
        return 1;
    }
    printf("HOST_GATEWAY_EGRESS_OK\n");
    return 0;
}
