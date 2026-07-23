#pragma once

// Allocation-free projection of correlated gateway evidence into Host Link V1
// typed dispositions and state. This layer accepts no raw host command and
// cannot authorize motion. It deliberately exposes q-axis current separately
// from effort and emits only fields present in a correlated native response.

#include <stdint.h>

#include "../gateway/gateway_core.h"
#include "../hostlink/hostlink_v1.h"
#include "../safety/safety_supervisor.h"

namespace myactuator {
namespace runtime {

struct HostRequestCorrelation {
    uint64_t request_session_id;
    uint64_t request_sequence;
    uint64_t safety_sequence;
    uint64_t transaction_id;
    hostlink_v1::Text canonical_actuator_id;
    hostlink_v1::ConfigIdentity config;
    gateway::RouteToken route_token;
    uint8_t bus_id;
    uint8_t node_id;
    uint32_t owner_id;
};

enum class EgressCode : uint8_t {
    OK = 0,
    NULL_OUTPUT,
    CONTEXT_INVALID,
    CORRELATION_MISMATCH,
    PHASE_UNMAPPED,
    GATEWAY_CODE_UNMAPPED,
    TIME_OVERFLOW,
    OBSERVATION_REQUIRED,
    RESPONSE_KIND_MISMATCH,
    SAFETY_STATE_UNMAPPED,
    HOST_TEXT_REJECTED,
};

const char* EgressCodeName(EgressCode code);

// Builds a Host Link DISPOSITION body. Non-rejected phases always carry the
// literal NONE; rejected phases carry the stable GatewayCore CodeName.
EgressCode BuildHostDisposition(
    const HostRequestCorrelation& context,
    const gateway::Disposition& event,
    hostlink_v1::TypedMessage* output);

struct ObservedStatePolicy {
    // Zero is invalid. Samples older than this are emitted as STALE while
    // retaining their measured timestamp and values.
    uint64_t maximum_sample_age_ms;
};

// Requires an OBSERVED/NATIVE_STATE_SAMPLE gateway event and a decoded
// response matching its route, node, opcode and response kind. Bus health is
// UNKNOWN here because a correlated response alone is not a bus-health
// monitor. Drive health is known only for status-1 error evidence.
EgressCode BuildObservedHostState(
    const HostRequestCorrelation& context,
    const gateway::Disposition& observation,
    const rmd_v44::DecodedResponse& response,
    uint64_t native_sample_monotonic_ms,
    uint64_t now_monotonic_ms,
    safety::State safety_state,
    const ObservedStatePolicy& policy,
    hostlink_v1::TypedMessage* output);

// Centralizes egress envelope identity and monotonic checks before the common
// Host Link encoder applies its message-specific cross-envelope validation.
EgressCode BuildHostEgressEnvelope(
    uint64_t gateway_session_id,
    uint64_t gateway_sequence,
    uint64_t monotonic_ns,
    const hostlink_v1::Sha256& active_config_sha256,
    const hostlink_v1::TypedMessage& message,
    hostlink_v1::Envelope* output);

}  // namespace runtime
}  // namespace myactuator
