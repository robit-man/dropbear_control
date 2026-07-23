#pragma once

// Allocation-free orchestration between GatewayCore and one native CAN
// transport adapter. This portable layer has no Arduino or MCP2515 dependency.
// It does not parse host commands, load configuration, infer routes, or claim
// hardware applicability.

#include <stddef.h>
#include <stdint.h>

#include "../gateway/gateway_core.h"
#include "../safety/safety_supervisor.h"

namespace myactuator {
namespace runtime {

static const uint8_t kMaximumRxPerService = 16;
static const uint8_t kMaximumTxPerService = 16;

enum class SendResult : uint8_t {
    SENT = 0,
    WOULD_BLOCK,
    BUS_OFF,
    ERROR_PASSIVE,
    IO_ERROR,
    INVALID_FRAME,
    TX_DISABLED,
    NOT_READY,
};

enum class ReceiveResult : uint8_t {
    FRAME = 0,
    NO_DATA,
    BUS_OFF,
    ERROR_PASSIVE,
    OVERFLOW,
    IO_ERROR,
};

struct ReceivedFrame {
    uint8_t bus_id;
    uint64_t monotonic_ms;
    rmd_v44::Frame frame;
};

// The adapter must return SENT only after the controller accepted the exact
// standard, non-RTR, DLC-8 frame for transmission. Queueing below this boundary
// is allowed only if it is bounded and a later bus-off/TX failure is surfaced
// through a stronger adapter contract; the initial ESP32 adapter should use a
// synchronous controller acceptance result.
class NativeCanTransport {
public:
    virtual bool ready(uint8_t bus_id) const = 0;
    virtual SendResult tryTransmit(uint8_t bus_id,
                                   const rmd_v44::Frame& frame) = 0;
    virtual ReceiveResult tryReceive(ReceivedFrame* frame) = 0;

protected:
    // Runtime owns no adapter and never deletes through this interface. A
    // protected non-virtual destructor avoids hidden operator-delete support
    // in the allocation-free embedded core.
    ~NativeCanTransport() {}
};

// Explicit stub for builds with no evidenced hardware adapter. It can never
// claim successful I/O.
class NoIoCanTransport : public NativeCanTransport {
public:
    bool ready(uint8_t bus_id) const;
    SendResult tryTransmit(uint8_t bus_id,
                           const rmd_v44::Frame& frame);
    ReceiveResult tryReceive(ReceivedFrame* frame);
};

struct ServicePolicy {
    uint8_t maximum_rx_per_service;
    uint8_t maximum_tx_per_service;
    uint32_t maximum_consecutive_response_timeouts;

    ServicePolicy(uint8_t maximum_rx,
                  uint8_t maximum_tx,
                  uint32_t maximum_response_timeouts = 3)
        : maximum_rx_per_service(maximum_rx),
          maximum_tx_per_service(maximum_tx),
          maximum_consecutive_response_timeouts(
              maximum_response_timeouts) {}
};

enum class ServiceCode : uint8_t {
    OK = 0,
    INVALID_RUNTIME,
    CYCLE_REJECTED,
    SAFETY_TICK_REJECTED,
    RX_TIMESTAMP_INVALID,
    RX_REJECTED,
    RX_IO_ERROR,
    RX_OVERFLOW,
    ERROR_PASSIVE,
    BUS_OFF,
    TX_FAILED,
    TX_DISABLED,
    TRANSPORT_NOT_READY,
    RESPONSE_BUDGET_EXCEEDED,
};

struct ServiceReport {
    ServiceCode code;
    gateway::Code gateway_code;
    safety::Result safety_result;
    size_t expired_responses;
    uint32_t consecutive_response_timeouts;
    uint8_t rx_frames;
    uint8_t rx_accepted;
    uint8_t rx_rejected;
    uint8_t tx_attempted;
    uint8_t tx_sent;
    uint8_t tx_failed;
    bool bus_off_observed;
};

class GatewayTransportRuntime {
public:
    GatewayTransportRuntime(gateway::GatewayCore* gateway_core,
                            safety::SafetySupervisor* safety_supervisor,
                            NativeCanTransport* transport,
                            const ServicePolicy& policy);

    bool valid() const;
    ServiceReport service(uint64_t now_ms, uint64_t cycle_id);

private:
    gateway::GatewayCore* gateway_core_;
    safety::SafetySupervisor* safety_supervisor_;
    NativeCanTransport* transport_;
    ServicePolicy policy_;
    bool valid_;
    uint32_t consecutive_response_timeouts_;

    void latchTransportFault(uint64_t now_ms, safety::Fault fault);
};

const char* ServiceCodeName(ServiceCode code);

}  // namespace runtime
}  // namespace myactuator
