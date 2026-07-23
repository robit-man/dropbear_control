#pragma once

// Allocation-free Host Link V1 command ingress.
//
// This is the only production-shaped boundary that converts a negotiated,
// session-accepted host command into a GatewayCore submission. It performs no
// I/O and grants no MYACTUATOR model/firmware applicability. The initial
// closed translation surface supports only CURRENT_Q -> RMD V4.4 IQ control;
// effort is never interpreted as current.

#include <stddef.h>
#include <stdint.h>

#include "../gateway/gateway_core.h"
#include "../hostlink/hostlink_v1.h"

namespace myactuator {
namespace runtime {

static const size_t kMaximumHostCommandBindings = gateway::kMaximumRoutes;
static const uint32_t kRmdV44IqAmperesPerLsbNumerator = 1U;
static const uint32_t kRmdV44IqAmperesPerLsbDenominator = 100U;

enum class TranslationKind : uint8_t {
    RMD_V44_IQ_CURRENT_A = 1,
};

// Generated/reviewed configuration owns this record. Caller-controlled host
// fields select it but never supply route, node, owner, scale or safety proof.
struct HostCommandBinding {
    hostlink_v1::Text canonical_actuator_id;
    hostlink_v1::Text source_identity;
    hostlink_v1::Text lease_owner;
    hostlink_v1::ConfigIdentity host_config;
    safety::ConfigReference safety_config;
    gateway::RouteToken route_token;
    uint8_t bus_id;
    uint8_t node_id;
    uint32_t owner_id;
    TranslationKind translation;
    uint32_t iq_amperes_per_lsb_numerator;
    uint32_t iq_amperes_per_lsb_denominator;
    int16_t minimum_iq_raw;
    int16_t maximum_iq_raw;
};

enum class BindingCode : uint8_t {
    OK = 0,
    NULL_BINDINGS,
    COUNT_INVALID,
    TEXT_INVALID,
    CONFIG_ID_TOO_LONG,
    CONFIG_REVISION_INVALID,
    CONFIG_ID_MISMATCH,
    CONFIG_REVISION_MISMATCH,
    CONFIG_DIGEST_MISMATCH,
    CONFIG_SCHEMA_UNSUPPORTED,
    CONFIG_GENERATION_INVALID,
    CONFIG_AUTHORIZATION_DENIED,
    ROUTE_INVALID,
    OWNER_INVALID,
    TRANSLATION_UNSUPPORTED,
    SCALE_UNSUPPORTED,
    CURRENT_RANGE_INVALID,
    DUPLICATE_SELECTOR,
    DUPLICATE_ROUTE,
};

enum class IngressCode : uint8_t {
    OK = 0,
    INVALID_CORE,
    NULL_OUTPUT,
    HOST_DENIED,
    NOT_COMMAND,
    ACTUATOR_NOT_BOUND,
    SOURCE_NOT_BOUND,
    LEASE_OWNER_MISMATCH,
    CONFIG_MISMATCH,
    SESSION_ID_OUT_OF_RANGE,
    UNSUPPORTED_MODE,
    CURRENT_VALUE_INVALID,
    CURRENT_NOT_ON_GRID,
    CURRENT_OUT_OF_RANGE,
    DEADLINE_NOT_MILLISECOND_ALIGNED,
    NATIVE_ENCODE_FAILED,
};

struct IngressResult {
    IngressCode code;
    bool link_accepted;
    hostlink_v1::ReceiveDenial receive_denial;
    hostlink_v1::Status host_status;
    uint64_t evaluation_time_ms;
    gateway::RouteToken route_token;
};

BindingCode ValidateHostCommandBinding(const HostCommandBinding& binding);
const char* BindingCodeName(BindingCode code);
const char* IngressCodeName(IngressCode code);

class HostCommandIngress {
public:
    HostCommandIngress(const HostCommandBinding* bindings,
                       size_t binding_count,
                       uint64_t active_session_id,
                       const hostlink_v1::Sha256& active_config_sha256,
                       const hostlink_v1::Capabilities& negotiation,
                       uint64_t initial_sequence = 0,
                       uint64_t initial_monotonic_ns = 0);

    bool valid() const;
    BindingCode bindingStatus() const;
    hostlink_v1::Status sessionStatus() const;
    size_t bindingCount() const;

    // now_monotonic_ns is used both for SessionReceiver expiry evaluation and
    // the returned millisecond timestamp. A successful caller must enqueue at
    // result.evaluation_time_ms without substituting a different clock.
    IngressResult receive(const hostlink_v1::Frame& frame,
                          uint64_t now_monotonic_ns,
                          gateway::Submission* submission);

private:
    const HostCommandBinding* bindings_;
    size_t binding_count_;
    BindingCode binding_status_;
    hostlink_v1::Status session_status_;
    bool valid_;
    hostlink_v1::SessionReceiver receiver_;
    hostlink_v1::TypedMessage scratch_;

    BindingCode validateBindings() const;
    const HostCommandBinding* findBinding(
        const hostlink_v1::Command& command,
        IngressCode* denial) const;
};

}  // namespace runtime
}  // namespace myactuator
