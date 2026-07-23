#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "can_adapter_contract.h"
#include "rmd_v44_codec.h"

namespace rt = myactuator::runtime;
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

rt::CanControllerCapabilities Capabilities() {
    rt::CanControllerCapabilities value = {};
    value.maximum_bitrate = 1000000U;
    value.maximum_dlc = 8U;
    value.timestamp_resolution_ns = 1000U;
    value.supports_standard_id_filter = true;
    value.supports_listen_only = true;
    value.listen_only_tx_disable_confirmed = true;
    value.supports_monotonic_rx_timestamp = true;
    value.supports_bus_state_reporting = true;
    value.supports_rx_loss_counter = true;
    value.supports_synchronous_tx_acceptance = true;
    return value;
}

rt::CanAdapterConfiguration CaptureConfiguration() {
    rt::CanAdapterConfiguration value = {};
    value.bus_id = 1U;
    value.bitrate = v44::kCanBitrate;
    value.mode = rt::CanControllerMode::LISTEN_ONLY;
    value.purpose = rt::CanAdapterPurpose::LISTEN_ONLY_CAPTURE;
    value.filter_minimum_id = 0U;
    value.filter_maximum_id = 0x7ffU;
    return value;
}

rt::CanAdapterConfiguration RuntimeConfiguration() {
    rt::CanAdapterConfiguration value = CaptureConfiguration();
    value.mode = rt::CanControllerMode::NORMAL;
    value.purpose = rt::CanAdapterPurpose::RUNTIME_GATEWAY;
    value.filter_minimum_id =
        v44::ResponseArbitrationId(v44::kMinMotorId);
    value.filter_maximum_id =
        v44::ResponseArbitrationId(v44::kMaxMotorId);
    return value;
}

class FakeDriver : public rt::NativeCanDriver {
public:
    FakeDriver()
        : caps(Capabilities()),
          configure_result(rt::DriverConfigureResult::CONFIGURED),
          current_state(rt::CanControllerState::ACTIVE),
          transmit_result(rt::DriverTransmitResult::ACCEPTED),
          receive_result(rt::DriverReceiveResult::NO_DATA),
          configured(false),
          transmit_count(0U),
          last_configuration(),
          last_transmit(),
          received() {}

    rt::CanControllerCapabilities capabilities() const { return caps; }
    rt::DriverConfigureResult configure(
        const rt::CanAdapterConfiguration& configuration) {
        configured = true;
        last_configuration = configuration;
        return configure_result;
    }
    rt::CanControllerState state() const { return current_state; }
    rt::DriverTransmitResult transmit(const v44::Frame& frame) {
        ++transmit_count;
        last_transmit = frame;
        return transmit_result;
    }
    rt::DriverReceiveResult receive(rt::DriverReceivedFrame* frame) {
        if (receive_result == rt::DriverReceiveResult::FRAME) {
            *frame = received;
            receive_result = rt::DriverReceiveResult::NO_DATA;
            return rt::DriverReceiveResult::FRAME;
        }
        const rt::DriverReceiveResult result = receive_result;
        receive_result = rt::DriverReceiveResult::NO_DATA;
        return result;
    }

    void push(uint64_t timestamp_ms, uint16_t arbitration_id, uint8_t dlc = 8U,
              uint64_t dropped = 0U) {
        received = {};
        received.bus_id = 1U;
        received.monotonic_ms = timestamp_ms;
        received.rx_dropped_total = dropped;
        received.frame.arbitration_id = arbitration_id;
        received.frame.dlc = dlc;
        receive_result = rt::DriverReceiveResult::FRAME;
    }

    rt::CanControllerCapabilities caps;
    rt::DriverConfigureResult configure_result;
    rt::CanControllerState current_state;
    rt::DriverTransmitResult transmit_result;
    rt::DriverReceiveResult receive_result;
    bool configured;
    uint32_t transmit_count;
    rt::CanAdapterConfiguration last_configuration;
    v44::Frame last_transmit;
    rt::DriverReceivedFrame received;
};

void TestListenOnlyCannotTransmit() {
    FakeDriver driver;
    rt::ConformingNativeCanAdapter adapter(&driver, CaptureConfiguration());
    CHECK(adapter.initialize() == rt::AdapterInitCode::OK);
    CHECK(adapter.initialized());
    CHECK(driver.configured);
    CHECK(driver.last_configuration.mode ==
          rt::CanControllerMode::LISTEN_ONLY);
    CHECK(!adapter.ready(1U));
    v44::Frame request = {};
    CHECK(v44::EncodeIqControlRaw(1U, 25, &request) == v44::Error::kOk);
    CHECK(adapter.tryTransmit(1U, request) == rt::SendResult::TX_DISABLED);
    CHECK(driver.transmit_count == 0U);

    driver.push(10U, 0x123U, 3U);
    rt::ReceivedFrame capture = {};
    CHECK(adapter.tryReceive(&capture) == rt::ReceiveResult::FRAME);
    CHECK(capture.bus_id == 1U);
    CHECK(capture.monotonic_ms == 10U);
    CHECK(capture.frame.arbitration_id == 0x123U);
    CHECK(capture.frame.dlc == 3U);
}

void TestContractDenials() {
    FakeDriver driver;
    rt::CanAdapterConfiguration config = CaptureConfiguration();
    rt::ConformingNativeCanAdapter null_adapter(NULL, config);
    CHECK(null_adapter.initialize() == rt::AdapterInitCode::NULL_DRIVER);

    config.bus_id = 0U;
    rt::ConformingNativeCanAdapter bad_bus(&driver, config);
    CHECK(bad_bus.initialize() == rt::AdapterInitCode::BUS_INVALID);
    config = CaptureConfiguration();
    config.bitrate = 500000U;
    rt::ConformingNativeCanAdapter bad_bitrate(&driver, config);
    CHECK(bad_bitrate.initialize() ==
          rt::AdapterInitCode::BITRATE_UNSUPPORTED);
    config = CaptureConfiguration();
    driver.caps.maximum_dlc = 7U;
    rt::ConformingNativeCanAdapter bad_dlc(&driver, config);
    CHECK(bad_dlc.initialize() == rt::AdapterInitCode::DLC_UNSUPPORTED);
    driver = FakeDriver();
    driver.caps.supports_standard_id_filter = false;
    rt::ConformingNativeCanAdapter no_filter(&driver, config);
    CHECK(no_filter.initialize() == rt::AdapterInitCode::FILTER_UNSUPPORTED);
    driver = FakeDriver();
    config.filter_maximum_id = 0x7feU;
    rt::ConformingNativeCanAdapter bad_filter(&driver, config);
    CHECK(bad_filter.initialize() == rt::AdapterInitCode::FILTER_INVALID);
    config = CaptureConfiguration();
    config.mode = rt::CanControllerMode::NORMAL;
    rt::ConformingNativeCanAdapter bad_mode(&driver, config);
    CHECK(bad_mode.initialize() ==
          rt::AdapterInitCode::MODE_PURPOSE_MISMATCH);
    config = CaptureConfiguration();
    driver.caps.listen_only_tx_disable_confirmed = false;
    rt::ConformingNativeCanAdapter no_tx_proof(&driver, config);
    CHECK(no_tx_proof.initialize() ==
          rt::AdapterInitCode::LISTEN_ONLY_UNPROVEN);
    driver = FakeDriver();
    driver.caps.supports_monotonic_rx_timestamp = false;
    rt::ConformingNativeCanAdapter no_time(&driver, config);
    CHECK(no_time.initialize() ==
          rt::AdapterInitCode::TIMESTAMP_UNSUPPORTED);
    driver = FakeDriver();
    driver.caps.supports_bus_state_reporting = false;
    rt::ConformingNativeCanAdapter no_state(&driver, config);
    CHECK(no_state.initialize() ==
          rt::AdapterInitCode::BUS_STATE_UNSUPPORTED);
    driver = FakeDriver();
    driver.caps.supports_rx_loss_counter = false;
    rt::ConformingNativeCanAdapter no_loss(&driver, config);
    CHECK(no_loss.initialize() ==
          rt::AdapterInitCode::LOSS_COUNTER_UNSUPPORTED);
    driver = FakeDriver();
    config = RuntimeConfiguration();
    driver.caps.supports_synchronous_tx_acceptance = false;
    rt::ConformingNativeCanAdapter no_tx_acceptance(&driver, config);
    CHECK(no_tx_acceptance.initialize() ==
          rt::AdapterInitCode::TX_ACCEPTANCE_UNSUPPORTED);
    driver = FakeDriver();
    driver.configure_result = rt::DriverConfigureResult::REJECTED;
    rt::ConformingNativeCanAdapter rejected(&driver, config);
    CHECK(rejected.initialize() == rt::AdapterInitCode::DRIVER_REJECTED);
    driver = FakeDriver();
    driver.configure_result = rt::DriverConfigureResult::IO_ERROR;
    rt::ConformingNativeCanAdapter io_error(&driver, config);
    CHECK(io_error.initialize() == rt::AdapterInitCode::DRIVER_IO_ERROR);
    driver = FakeDriver();
    driver.current_state = rt::CanControllerState::STOPPED;
    rt::ConformingNativeCanAdapter stopped(&driver, config);
    CHECK(stopped.initialize() ==
          rt::AdapterInitCode::INITIAL_STATE_INVALID);
    CHECK(strcmp(rt::AdapterInitCodeName(rt::AdapterInitCode::OK), "OK") == 0);
    CHECK(strcmp(rt::AdapterInitCodeName(
                     static_cast<rt::AdapterInitCode>(255U)),
                 "UNKNOWN_ADAPTER_INIT_CODE") == 0);
}

void TestRuntimeTransmitMappingAndValidation() {
    FakeDriver driver;
    rt::ConformingNativeCanAdapter adapter(&driver, RuntimeConfiguration());
    CHECK(adapter.initialize() == rt::AdapterInitCode::OK);
    CHECK(adapter.ready(1U));
    CHECK(!adapter.ready(2U));
    v44::Frame request = {};
    CHECK(v44::EncodeIqControlRaw(1U, -25, &request) == v44::Error::kOk);
    CHECK(adapter.tryTransmit(1U, request) == rt::SendResult::SENT);
    CHECK(driver.transmit_count == 1U);
    CHECK(memcmp(driver.last_transmit.data, request.data,
                 sizeof(request.data)) == 0);

    driver.transmit_result = rt::DriverTransmitResult::WOULD_BLOCK;
    CHECK(adapter.tryTransmit(1U, request) == rt::SendResult::WOULD_BLOCK);
    driver.transmit_result = rt::DriverTransmitResult::ERROR_PASSIVE;
    CHECK(adapter.tryTransmit(1U, request) == rt::SendResult::ERROR_PASSIVE);
    driver.transmit_result = rt::DriverTransmitResult::BUS_OFF;
    CHECK(adapter.tryTransmit(1U, request) == rt::SendResult::BUS_OFF);
    driver.transmit_result = rt::DriverTransmitResult::IO_ERROR;
    CHECK(adapter.tryTransmit(1U, request) == rt::SendResult::IO_ERROR);

    v44::Frame invalid = request;
    invalid.is_extended = true;
    CHECK(adapter.tryTransmit(1U, invalid) == rt::SendResult::INVALID_FRAME);
    invalid = request;
    invalid.is_remote = true;
    CHECK(adapter.tryTransmit(1U, invalid) == rt::SendResult::INVALID_FRAME);
    invalid = request;
    invalid.dlc = 7U;
    CHECK(adapter.tryTransmit(1U, invalid) == rt::SendResult::INVALID_FRAME);
    invalid = request;
    invalid.data[1] = 1U;
    CHECK(adapter.tryTransmit(1U, invalid) == rt::SendResult::INVALID_FRAME);
    CHECK(adapter.tryTransmit(2U, request) == rt::SendResult::NOT_READY);

    driver.current_state = rt::CanControllerState::ERROR_PASSIVE;
    CHECK(adapter.tryTransmit(1U, request) == rt::SendResult::ERROR_PASSIVE);
    driver.current_state = rt::CanControllerState::BUS_OFF;
    CHECK(adapter.tryTransmit(1U, request) == rt::SendResult::BUS_OFF);
    driver.current_state = rt::CanControllerState::RECOVERING;
    CHECK(adapter.tryTransmit(1U, request) == rt::SendResult::NOT_READY);
}

void TestRuntimeReceiveEvidence() {
    FakeDriver driver;
    rt::ConformingNativeCanAdapter adapter(&driver, RuntimeConfiguration());
    CHECK(adapter.initialize() == rt::AdapterInitCode::OK);
    rt::ReceivedFrame output = {};
    driver.push(10U, v44::ResponseArbitrationId(1U));
    CHECK(adapter.tryReceive(&output) == rt::ReceiveResult::FRAME);
    CHECK(output.monotonic_ms == 10U);
    driver.push(10U, v44::ResponseArbitrationId(2U));
    CHECK(adapter.tryReceive(&output) == rt::ReceiveResult::FRAME);
    driver.push(9U, v44::ResponseArbitrationId(1U));
    CHECK(adapter.tryReceive(&output) == rt::ReceiveResult::IO_ERROR);

    FakeDriver loss_driver;
    rt::ConformingNativeCanAdapter loss(&loss_driver, RuntimeConfiguration());
    CHECK(loss.initialize() == rt::AdapterInitCode::OK);
    loss_driver.push(10U, v44::ResponseArbitrationId(1U), 8U, 2U);
    CHECK(loss.tryReceive(&output) == rt::ReceiveResult::OVERFLOW);
    CHECK(loss.observedRxDroppedTotal() == 2U);
    loss_driver.push(11U, v44::ResponseArbitrationId(1U), 8U, 1U);
    CHECK(loss.tryReceive(&output) == rt::ReceiveResult::IO_ERROR);

    FakeDriver invalid_driver;
    rt::ConformingNativeCanAdapter invalid(&invalid_driver,
                                            RuntimeConfiguration());
    CHECK(invalid.initialize() == rt::AdapterInitCode::OK);
    invalid_driver.push(10U, 0x123U);
    CHECK(invalid.tryReceive(&output) == rt::ReceiveResult::IO_ERROR);
    invalid_driver.push(10U, v44::ResponseArbitrationId(1U), 7U);
    CHECK(invalid.tryReceive(&output) == rt::ReceiveResult::IO_ERROR);
    invalid_driver.push(10U, v44::ResponseArbitrationId(1U));
    invalid_driver.received.frame.is_extended = true;
    CHECK(invalid.tryReceive(&output) == rt::ReceiveResult::IO_ERROR);

    FakeDriver states;
    rt::ConformingNativeCanAdapter state_adapter(&states,
                                                  RuntimeConfiguration());
    CHECK(state_adapter.initialize() == rt::AdapterInitCode::OK);
    states.current_state = rt::CanControllerState::ERROR_PASSIVE;
    CHECK(state_adapter.tryReceive(&output) ==
          rt::ReceiveResult::ERROR_PASSIVE);
    states.current_state = rt::CanControllerState::BUS_OFF;
    CHECK(state_adapter.tryReceive(&output) == rt::ReceiveResult::BUS_OFF);
    states.current_state = rt::CanControllerState::ACTIVE;
    states.receive_result = rt::DriverReceiveResult::OVERFLOW;
    CHECK(state_adapter.tryReceive(&output) == rt::ReceiveResult::OVERFLOW);
    states.receive_result = rt::DriverReceiveResult::IO_ERROR;
    CHECK(state_adapter.tryReceive(&output) == rt::ReceiveResult::IO_ERROR);
    CHECK(state_adapter.tryReceive(NULL) == rt::ReceiveResult::IO_ERROR);
}

}  // namespace

int main() {
    TestListenOnlyCannotTransmit();
    TestContractDenials();
    TestRuntimeTransmitMappingAndValidation();
    TestRuntimeReceiveEvidence();
    if (failures != 0) {
        fprintf(stderr, "CAN adapter contract failures=%d\n", failures);
        return 1;
    }
    printf("CAN_ADAPTER_CONTRACT_OK\n");
    return 0;
}
