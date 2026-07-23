#pragma once

// Controller-independent, allocation-free CAN adapter conformance boundary.
// No concrete ESP32/TWAI/MCP2515 implementation is supplied here. A driver is
// admitted only when it can prove the required mode, filter, timestamp,
// loss-counter, bus-state and transmit-result capabilities.

#include <stdint.h>

#include "gateway_transport_runtime.h"

namespace myactuator {
namespace runtime {

enum class CanControllerMode : uint8_t {
    STOPPED = 0,
    LISTEN_ONLY,
    NORMAL,
};

enum class CanAdapterPurpose : uint8_t {
    LISTEN_ONLY_CAPTURE = 0,
    RUNTIME_GATEWAY,
};

enum class CanControllerState : uint8_t {
    STOPPED = 0,
    ACTIVE,
    ERROR_WARNING,
    ERROR_PASSIVE,
    BUS_OFF,
    RECOVERING,
};

struct CanControllerCapabilities {
    uint32_t maximum_bitrate;
    uint8_t maximum_dlc;
    uint32_t timestamp_resolution_ns;
    bool supports_standard_id_filter;
    bool supports_listen_only;
    bool listen_only_tx_disable_confirmed;
    bool supports_monotonic_rx_timestamp;
    bool supports_bus_state_reporting;
    bool supports_rx_loss_counter;
    bool supports_synchronous_tx_acceptance;
};

struct CanAdapterConfiguration {
    uint8_t bus_id;
    uint32_t bitrate;
    CanControllerMode mode;
    CanAdapterPurpose purpose;
    uint16_t filter_minimum_id;
    uint16_t filter_maximum_id;
};

enum class DriverConfigureResult : uint8_t {
    CONFIGURED = 0,
    REJECTED,
    IO_ERROR,
};

enum class DriverTransmitResult : uint8_t {
    ACCEPTED = 0,
    WOULD_BLOCK,
    ERROR_PASSIVE,
    BUS_OFF,
    IO_ERROR,
};

enum class DriverReceiveResult : uint8_t {
    FRAME = 0,
    NO_DATA,
    OVERFLOW,
    IO_ERROR,
};

struct DriverReceivedFrame {
    uint8_t bus_id;
    uint64_t monotonic_ms;
    uint64_t rx_dropped_total;
    rmd_v44::Frame frame;
};

class NativeCanDriver {
public:
    virtual CanControllerCapabilities capabilities() const = 0;
    virtual DriverConfigureResult configure(
        const CanAdapterConfiguration& configuration) = 0;
    virtual CanControllerState state() const = 0;
    virtual DriverTransmitResult transmit(const rmd_v44::Frame& frame) = 0;
    virtual DriverReceiveResult receive(DriverReceivedFrame* frame) = 0;

protected:
    ~NativeCanDriver() {}
};

enum class AdapterInitCode : uint8_t {
    OK = 0,
    NULL_DRIVER,
    BUS_INVALID,
    BITRATE_UNSUPPORTED,
    DLC_UNSUPPORTED,
    FILTER_UNSUPPORTED,
    FILTER_INVALID,
    MODE_PURPOSE_MISMATCH,
    LISTEN_ONLY_UNPROVEN,
    TIMESTAMP_UNSUPPORTED,
    BUS_STATE_UNSUPPORTED,
    LOSS_COUNTER_UNSUPPORTED,
    TX_ACCEPTANCE_UNSUPPORTED,
    DRIVER_REJECTED,
    DRIVER_IO_ERROR,
    INITIAL_STATE_INVALID,
};

const char* AdapterInitCodeName(AdapterInitCode code);

class ConformingNativeCanAdapter : public NativeCanTransport {
public:
    ConformingNativeCanAdapter(
        NativeCanDriver* driver,
        const CanAdapterConfiguration& configuration);

    AdapterInitCode initialize();
    bool initialized() const;
    AdapterInitCode initCode() const;
    CanControllerState controllerState() const;
    uint64_t observedRxDroppedTotal() const;

    bool ready(uint8_t bus_id) const;
    SendResult tryTransmit(uint8_t bus_id, const rmd_v44::Frame& frame);
    ReceiveResult tryReceive(ReceivedFrame* frame);

private:
    NativeCanDriver* driver_;
    CanAdapterConfiguration configuration_;
    AdapterInitCode init_code_;
    bool initialized_;
    bool timestamp_seen_;
    uint64_t last_timestamp_ms_;
    uint64_t rx_dropped_total_;

    AdapterInitCode validateContract() const;
    bool frameStructurallyValid(const rmd_v44::Frame& frame) const;
    bool receiveIdAllowed(uint16_t arbitration_id) const;
};

}  // namespace runtime
}  // namespace myactuator
