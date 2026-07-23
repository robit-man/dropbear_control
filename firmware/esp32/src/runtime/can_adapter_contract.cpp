#include "can_adapter_contract.h"

#include <cstring>

namespace myactuator {
namespace runtime {

const char* AdapterInitCodeName(AdapterInitCode code) {
    switch (code) {
        case AdapterInitCode::OK: return "OK";
        case AdapterInitCode::NULL_DRIVER: return "NULL_DRIVER";
        case AdapterInitCode::BUS_INVALID: return "BUS_INVALID";
        case AdapterInitCode::BITRATE_UNSUPPORTED:
            return "BITRATE_UNSUPPORTED";
        case AdapterInitCode::DLC_UNSUPPORTED: return "DLC_UNSUPPORTED";
        case AdapterInitCode::FILTER_UNSUPPORTED:
            return "FILTER_UNSUPPORTED";
        case AdapterInitCode::FILTER_INVALID: return "FILTER_INVALID";
        case AdapterInitCode::MODE_PURPOSE_MISMATCH:
            return "MODE_PURPOSE_MISMATCH";
        case AdapterInitCode::LISTEN_ONLY_UNPROVEN:
            return "LISTEN_ONLY_UNPROVEN";
        case AdapterInitCode::TIMESTAMP_UNSUPPORTED:
            return "TIMESTAMP_UNSUPPORTED";
        case AdapterInitCode::BUS_STATE_UNSUPPORTED:
            return "BUS_STATE_UNSUPPORTED";
        case AdapterInitCode::LOSS_COUNTER_UNSUPPORTED:
            return "LOSS_COUNTER_UNSUPPORTED";
        case AdapterInitCode::TX_ACCEPTANCE_UNSUPPORTED:
            return "TX_ACCEPTANCE_UNSUPPORTED";
        case AdapterInitCode::DRIVER_REJECTED: return "DRIVER_REJECTED";
        case AdapterInitCode::DRIVER_IO_ERROR: return "DRIVER_IO_ERROR";
        case AdapterInitCode::INITIAL_STATE_INVALID:
            return "INITIAL_STATE_INVALID";
    }
    return "UNKNOWN_ADAPTER_INIT_CODE";
}

ConformingNativeCanAdapter::ConformingNativeCanAdapter(
    NativeCanDriver* driver,
    const CanAdapterConfiguration& configuration)
    : driver_(driver),
      configuration_(configuration),
      init_code_(AdapterInitCode::NULL_DRIVER),
      initialized_(false),
      timestamp_seen_(false),
      last_timestamp_ms_(0U),
      rx_dropped_total_(0U) {}

AdapterInitCode ConformingNativeCanAdapter::validateContract() const {
    if (driver_ == NULL) return AdapterInitCode::NULL_DRIVER;
    if (configuration_.bus_id == 0U) return AdapterInitCode::BUS_INVALID;
    const CanControllerCapabilities capabilities = driver_->capabilities();
    if (configuration_.bitrate != rmd_v44::kCanBitrate ||
        capabilities.maximum_bitrate < configuration_.bitrate) {
        return AdapterInitCode::BITRATE_UNSUPPORTED;
    }
    if (capabilities.maximum_dlc < rmd_v44::kFrameDlc) {
        return AdapterInitCode::DLC_UNSUPPORTED;
    }
    if (!capabilities.supports_standard_id_filter) {
        return AdapterInitCode::FILTER_UNSUPPORTED;
    }
    if (configuration_.filter_minimum_id >
            configuration_.filter_maximum_id ||
        configuration_.filter_maximum_id > 0x7ffU) {
        return AdapterInitCode::FILTER_INVALID;
    }
    if (!capabilities.supports_monotonic_rx_timestamp ||
        capabilities.timestamp_resolution_ns == 0U) {
        return AdapterInitCode::TIMESTAMP_UNSUPPORTED;
    }
    if (!capabilities.supports_bus_state_reporting) {
        return AdapterInitCode::BUS_STATE_UNSUPPORTED;
    }
    if (!capabilities.supports_rx_loss_counter) {
        return AdapterInitCode::LOSS_COUNTER_UNSUPPORTED;
    }
    if (configuration_.purpose == CanAdapterPurpose::LISTEN_ONLY_CAPTURE) {
        if (configuration_.mode != CanControllerMode::LISTEN_ONLY) {
            return AdapterInitCode::MODE_PURPOSE_MISMATCH;
        }
        if (!capabilities.supports_listen_only ||
            !capabilities.listen_only_tx_disable_confirmed) {
            return AdapterInitCode::LISTEN_ONLY_UNPROVEN;
        }
        if (configuration_.filter_minimum_id != 0U ||
            configuration_.filter_maximum_id != 0x7ffU) {
            return AdapterInitCode::FILTER_INVALID;
        }
    } else if (configuration_.purpose == CanAdapterPurpose::RUNTIME_GATEWAY) {
        if (configuration_.mode != CanControllerMode::NORMAL) {
            return AdapterInitCode::MODE_PURPOSE_MISMATCH;
        }
        if (!capabilities.supports_synchronous_tx_acceptance) {
            return AdapterInitCode::TX_ACCEPTANCE_UNSUPPORTED;
        }
        const uint16_t expected_min =
            rmd_v44::ResponseArbitrationId(rmd_v44::kMinMotorId);
        const uint16_t expected_max =
            rmd_v44::ResponseArbitrationId(rmd_v44::kMaxMotorId);
        if (configuration_.filter_minimum_id != expected_min ||
            configuration_.filter_maximum_id != expected_max) {
            return AdapterInitCode::FILTER_INVALID;
        }
    } else {
        return AdapterInitCode::MODE_PURPOSE_MISMATCH;
    }
    return AdapterInitCode::OK;
}

AdapterInitCode ConformingNativeCanAdapter::initialize() {
    initialized_ = false;
    timestamp_seen_ = false;
    last_timestamp_ms_ = 0U;
    rx_dropped_total_ = 0U;
    init_code_ = validateContract();
    if (init_code_ != AdapterInitCode::OK) return init_code_;
    const DriverConfigureResult configured = driver_->configure(configuration_);
    if (configured == DriverConfigureResult::REJECTED) {
        init_code_ = AdapterInitCode::DRIVER_REJECTED;
        return init_code_;
    }
    if (configured == DriverConfigureResult::IO_ERROR) {
        init_code_ = AdapterInitCode::DRIVER_IO_ERROR;
        return init_code_;
    }
    const CanControllerState state = driver_->state();
    if (state != CanControllerState::ACTIVE &&
        state != CanControllerState::ERROR_WARNING) {
        init_code_ = AdapterInitCode::INITIAL_STATE_INVALID;
        return init_code_;
    }
    initialized_ = true;
    init_code_ = AdapterInitCode::OK;
    return init_code_;
}

bool ConformingNativeCanAdapter::initialized() const { return initialized_; }

AdapterInitCode ConformingNativeCanAdapter::initCode() const {
    return init_code_;
}

CanControllerState ConformingNativeCanAdapter::controllerState() const {
    return driver_ == NULL ? CanControllerState::STOPPED : driver_->state();
}

uint64_t ConformingNativeCanAdapter::observedRxDroppedTotal() const {
    return rx_dropped_total_;
}

bool ConformingNativeCanAdapter::ready(uint8_t bus_id) const {
    return initialized_ &&
           configuration_.purpose == CanAdapterPurpose::RUNTIME_GATEWAY &&
           configuration_.mode == CanControllerMode::NORMAL &&
           bus_id == configuration_.bus_id &&
           driver_->state() == CanControllerState::ACTIVE;
}

bool ConformingNativeCanAdapter::frameStructurallyValid(
    const rmd_v44::Frame& frame) const {
    return !frame.is_extended && !frame.is_remote &&
           frame.arbitration_id <= 0x7ffU &&
           frame.dlc <= rmd_v44::kFrameDlc;
}

bool ConformingNativeCanAdapter::receiveIdAllowed(
    uint16_t arbitration_id) const {
    return arbitration_id >= configuration_.filter_minimum_id &&
           arbitration_id <= configuration_.filter_maximum_id;
}

SendResult ConformingNativeCanAdapter::tryTransmit(
    uint8_t bus_id, const rmd_v44::Frame& frame) {
    if (!initialized_) return SendResult::NOT_READY;
    if (configuration_.purpose == CanAdapterPurpose::LISTEN_ONLY_CAPTURE ||
        configuration_.mode == CanControllerMode::LISTEN_ONLY) {
        return SendResult::TX_DISABLED;
    }
    if (bus_id != configuration_.bus_id) return SendResult::NOT_READY;
    const CanControllerState state = driver_->state();
    if (state == CanControllerState::BUS_OFF) return SendResult::BUS_OFF;
    if (state == CanControllerState::ERROR_PASSIVE) {
        return SendResult::ERROR_PASSIVE;
    }
    if (state != CanControllerState::ACTIVE) return SendResult::NOT_READY;
    if (!frameStructurallyValid(frame) ||
        frame.dlc != rmd_v44::kFrameDlc) {
        return SendResult::INVALID_FRAME;
    }
    rmd_v44::DecodedRequest decoded = {};
    if (rmd_v44::DecodeRequest(frame, &decoded) != rmd_v44::Error::kOk) {
        return SendResult::INVALID_FRAME;
    }
    switch (driver_->transmit(frame)) {
        case DriverTransmitResult::ACCEPTED: return SendResult::SENT;
        case DriverTransmitResult::WOULD_BLOCK: return SendResult::WOULD_BLOCK;
        case DriverTransmitResult::ERROR_PASSIVE:
            return SendResult::ERROR_PASSIVE;
        case DriverTransmitResult::BUS_OFF: return SendResult::BUS_OFF;
        case DriverTransmitResult::IO_ERROR: return SendResult::IO_ERROR;
    }
    return SendResult::IO_ERROR;
}

ReceiveResult ConformingNativeCanAdapter::tryReceive(ReceivedFrame* frame) {
    if (frame == NULL || !initialized_) return ReceiveResult::IO_ERROR;
    std::memset(frame, 0, sizeof(*frame));
    const CanControllerState state = driver_->state();
    if (state == CanControllerState::BUS_OFF) return ReceiveResult::BUS_OFF;
    if (state == CanControllerState::ERROR_PASSIVE) {
        return ReceiveResult::ERROR_PASSIVE;
    }
    if (state == CanControllerState::STOPPED ||
        state == CanControllerState::RECOVERING) {
        return ReceiveResult::IO_ERROR;
    }

    DriverReceivedFrame received = {};
    const DriverReceiveResult result = driver_->receive(&received);
    if (result == DriverReceiveResult::NO_DATA) {
        return ReceiveResult::NO_DATA;
    }
    if (result == DriverReceiveResult::OVERFLOW) {
        return ReceiveResult::OVERFLOW;
    }
    if (result == DriverReceiveResult::IO_ERROR) {
        return ReceiveResult::IO_ERROR;
    }
    if (received.bus_id != configuration_.bus_id ||
        !frameStructurallyValid(received.frame) ||
        !receiveIdAllowed(received.frame.arbitration_id)) {
        return ReceiveResult::IO_ERROR;
    }
    if (configuration_.purpose == CanAdapterPurpose::RUNTIME_GATEWAY &&
        received.frame.dlc != rmd_v44::kFrameDlc) {
        return ReceiveResult::IO_ERROR;
    }
    if ((timestamp_seen_ && received.monotonic_ms < last_timestamp_ms_) ||
        received.rx_dropped_total < rx_dropped_total_) {
        return ReceiveResult::IO_ERROR;
    }
    timestamp_seen_ = true;
    last_timestamp_ms_ = received.monotonic_ms;
    if (received.rx_dropped_total > rx_dropped_total_) {
        rx_dropped_total_ = received.rx_dropped_total;
        return ReceiveResult::OVERFLOW;
    }
    frame->bus_id = received.bus_id;
    frame->monotonic_ms = received.monotonic_ms;
    frame->frame = received.frame;
    return ReceiveResult::FRAME;
}

}  // namespace runtime
}  // namespace myactuator
