#include "gateway_transport_runtime.h"

#include <string.h>

namespace myactuator {
namespace runtime {

bool NoIoCanTransport::ready(uint8_t bus_id) const {
    (void)bus_id;
    return false;
}

SendResult NoIoCanTransport::tryTransmit(
    uint8_t bus_id, const rmd_v44::Frame& frame) {
    (void)bus_id;
    (void)frame;
    return SendResult::IO_ERROR;
}

ReceiveResult NoIoCanTransport::tryReceive(ReceivedFrame* frame) {
    (void)frame;
    return ReceiveResult::NO_DATA;
}

const char* ServiceCodeName(ServiceCode code) {
    switch (code) {
        case ServiceCode::OK: return "OK";
        case ServiceCode::INVALID_RUNTIME: return "INVALID_RUNTIME";
        case ServiceCode::CYCLE_REJECTED: return "CYCLE_REJECTED";
        case ServiceCode::SAFETY_TICK_REJECTED:
            return "SAFETY_TICK_REJECTED";
        case ServiceCode::RX_TIMESTAMP_INVALID:
            return "RX_TIMESTAMP_INVALID";
        case ServiceCode::RX_REJECTED: return "RX_REJECTED";
        case ServiceCode::RX_IO_ERROR: return "RX_IO_ERROR";
        case ServiceCode::RX_OVERFLOW: return "RX_OVERFLOW";
        case ServiceCode::ERROR_PASSIVE: return "ERROR_PASSIVE";
        case ServiceCode::BUS_OFF: return "BUS_OFF";
        case ServiceCode::TX_FAILED: return "TX_FAILED";
        case ServiceCode::TX_DISABLED: return "TX_DISABLED";
        case ServiceCode::TRANSPORT_NOT_READY:
            return "TRANSPORT_NOT_READY";
        case ServiceCode::RESPONSE_BUDGET_EXCEEDED:
            return "RESPONSE_BUDGET_EXCEEDED";
    }
    return "UNKNOWN_SERVICE_CODE";
}

GatewayTransportRuntime::GatewayTransportRuntime(
    gateway::GatewayCore* gateway_core,
    safety::SafetySupervisor* safety_supervisor,
    NativeCanTransport* transport,
    const ServicePolicy& policy)
    : gateway_core_(gateway_core),
      safety_supervisor_(safety_supervisor),
      transport_(transport),
      policy_(policy),
      valid_(gateway_core != NULL && safety_supervisor != NULL &&
             transport != NULL && gateway_core->valid() &&
             policy.maximum_rx_per_service > 0 &&
             policy.maximum_rx_per_service <= kMaximumRxPerService &&
             policy.maximum_tx_per_service > 0 &&
             policy.maximum_tx_per_service <= kMaximumTxPerService &&
             policy.maximum_consecutive_response_timeouts > 0),
      consecutive_response_timeouts_(0) {}

bool GatewayTransportRuntime::valid() const {
    return valid_;
}

void GatewayTransportRuntime::latchTransportFault(
    uint64_t now_ms, safety::Fault fault) {
    safety_supervisor_->raiseFault(now_ms, fault);
}

ServiceReport GatewayTransportRuntime::service(uint64_t now_ms,
                                               uint64_t cycle_id) {
    ServiceReport report = {};
    report.code = ServiceCode::OK;
    report.gateway_code = gateway::Code::OK;
    report.safety_result = safety::Result::OK;
    if (!valid_) {
        report.code = ServiceCode::INVALID_RUNTIME;
        report.gateway_code = gateway::Code::CORE_INVALID;
        return report;
    }

    report.safety_result = safety_supervisor_->tick(now_ms);
    if (report.safety_result != safety::Result::OK &&
        report.safety_result != safety::Result::LEASE_EXPIRED) {
        report.code = ServiceCode::SAFETY_TICK_REJECTED;
        return report;
    }
    report.gateway_code = gateway_core_->beginCycle(cycle_id);
    if (report.gateway_code != gateway::Code::OK) {
        report.code = ServiceCode::CYCLE_REJECTED;
        return report;
    }
    report.expired_responses = gateway_core_->expireResponses(now_ms);
    if (report.expired_responses != 0) {
        const size_t remaining =
            static_cast<size_t>(UINT32_MAX -
                                consecutive_response_timeouts_);
        if (report.expired_responses > remaining) {
            consecutive_response_timeouts_ = UINT32_MAX;
        } else {
            consecutive_response_timeouts_ +=
                static_cast<uint32_t>(report.expired_responses);
        }
    }
    report.consecutive_response_timeouts =
        consecutive_response_timeouts_;
    if (consecutive_response_timeouts_ >
        policy_.maximum_consecutive_response_timeouts) {
        report.code = ServiceCode::RESPONSE_BUDGET_EXCEEDED;
        report.safety_result = safety_supervisor_->raiseFault(
            now_ms, safety::Fault::RESPONSE_BUDGET_EXCEEDED);
    }

    for (uint8_t index = 0;
         index < policy_.maximum_rx_per_service;
         ++index) {
        ReceivedFrame received = {};
        const ReceiveResult result = transport_->tryReceive(&received);
        if (result == ReceiveResult::NO_DATA) {
            break;
        }
        if (result == ReceiveResult::BUS_OFF) {
            report.code = ServiceCode::BUS_OFF;
            report.bus_off_observed = true;
            latchTransportFault(now_ms, safety::Fault::BUS_OFF);
            break;
        }
        if (result == ReceiveResult::ERROR_PASSIVE) {
            report.code = ServiceCode::ERROR_PASSIVE;
            latchTransportFault(now_ms, safety::Fault::EXTERNAL);
            break;
        }
        if (result == ReceiveResult::OVERFLOW) {
            report.code = ServiceCode::RX_OVERFLOW;
            latchTransportFault(now_ms, safety::Fault::EXTERNAL);
            break;
        }
        if (result == ReceiveResult::IO_ERROR) {
            report.code = ServiceCode::RX_IO_ERROR;
            latchTransportFault(now_ms, safety::Fault::EXTERNAL);
            break;
        }
        ++report.rx_frames;
        if (received.monotonic_ms > now_ms) {
            ++report.rx_rejected;
            report.code = ServiceCode::RX_TIMESTAMP_INVALID;
            continue;
        }
        report.gateway_code = gateway_core_->acceptResponse(
            received.monotonic_ms, received.bus_id, received.frame);
        if (report.gateway_code == gateway::Code::OK) {
            ++report.rx_accepted;
            consecutive_response_timeouts_ = 0;
            report.consecutive_response_timeouts = 0;
        } else {
            ++report.rx_rejected;
            report.code = ServiceCode::RX_REJECTED;
        }
    }

    for (uint8_t index = 0;
         index < policy_.maximum_tx_per_service;
         ++index) {
        gateway::TxEnvelope envelope = {};
        const gateway::PollResult poll =
            gateway_core_->pollTransmit(now_ms, &envelope);
        if (poll == gateway::PollResult::NO_FRAME) {
            break;
        }
        if (poll == gateway::PollResult::INVALID_CORE) {
            report.code = ServiceCode::INVALID_RUNTIME;
            report.gateway_code = gateway::Code::CORE_INVALID;
            break;
        }
        ++report.tx_attempted;
        SendResult result = SendResult::NOT_READY;
        if (transport_->ready(envelope.bus_id)) {
            result = transport_->tryTransmit(envelope.bus_id,
                                             envelope.frame);
        }
        if (result == SendResult::SENT) {
            ++report.tx_sent;
            continue;
        }
        ++report.tx_failed;
        const gateway::TransportFailure failure =
            result == SendResult::BUS_OFF
                ? gateway::TransportFailure::BUS_OFF
                : gateway::TransportFailure::TX_FAILED;
        report.gateway_code = gateway_core_->reportTransportFailure(
            now_ms, envelope.transaction_id, failure);
        if (failure == gateway::TransportFailure::BUS_OFF) {
            report.code = ServiceCode::BUS_OFF;
            report.bus_off_observed = true;
        } else if (result == SendResult::ERROR_PASSIVE) {
            report.code = ServiceCode::ERROR_PASSIVE;
        } else if (result == SendResult::TX_DISABLED) {
            report.code = ServiceCode::TX_DISABLED;
        } else if (result == SendResult::NOT_READY) {
            report.code = ServiceCode::TRANSPORT_NOT_READY;
        } else {
            report.code = ServiceCode::TX_FAILED;
        }
        // A failed transmission latches a safety fault. Stop normal service;
        // the next cycle can retry the safety action through the same bounded
        // path if the transport is ready again.
        break;
    }
    return report;
}

}  // namespace runtime
}  // namespace myactuator
