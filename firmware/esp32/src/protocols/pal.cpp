/**
 * Protocol Abstraction Layer (PAL) - Implementation
 *
 * Provides unified interface for CAN, RS485, and EtherCAT protocols
 */

#include "pal.h"
#include <string.h>
#include "../drivers/can_bus.h"
#include "../drivers/rs485.h"
#include "../drivers/ethercat.h"
#include "../utils/logger.h"

ProtocolAbstractionLayer::ProtocolAbstractionLayer()
    : _motorId(0), _protocolType(0), _initialized(false), _motorDriver(nullptr) {
    memset(&_status, 0, sizeof(PalStatusReport));
}

ProtocolAbstractionLayer::~ProtocolAbstractionLayer() {
}

void ProtocolAbstractionLayer::init(const MotorConfig& config) {
    _config = config;
    _protocolType = (uint8_t)config.protocol;
    _motorId = config.motorId;
    _initialized = true;

    Logger::info("PAL", "Initialized motor series %u", (uint8_t)config.motorSeries);
    Logger::info("PAL", "Protocol %u", (uint8_t)config.protocol);

    switch (config.protocol) {
        case PROTO_CAN:
            initCAN();
            break;
        case PROTO_RS485:
            initRS485();
            break;
        case PROTO_ETHERCAT:
            initEtherCAT();
            break;
        default:
            Logger::error("PAL", "Unknown protocol");
            break;
    }
}

void ProtocolAbstractionLayer::deinitialize() {
    _initialized = false;
}

void ProtocolAbstractionLayer::initCAN() {
    CANBus::init();
    Logger::info("PAL", "CAN bus initialized");
}

void ProtocolAbstractionLayer::initRS485() {
    RS485::init();
    Logger::info("PAL", "RS485 initialized");
}

void ProtocolAbstractionLayer::initEtherCAT() {
    EtherCAT::init();
    Logger::info("PAL", "EtherCAT initialized");
}

void ProtocolAbstractionLayer::setMotorDriver(IMotorDriver* driver) {
    _motorDriver = driver;
}

void ProtocolAbstractionLayer::setMotorId(uint8_t motorId) {
    _motorId = motorId;
}

uint8_t ProtocolAbstractionLayer::getMotorId() const {
    return _motorId;
}

bool ProtocolAbstractionLayer::isConnected() const {
    return _initialized;
}

bool ProtocolAbstractionLayer::sendFrame(const uint8_t* data, uint8_t length) {
    switch (_config.protocol) {
        case PROTO_CAN:
            return CANBus::sendFrame(0x100 + _motorId, data, length);
        case PROTO_RS485:
            return RS485::sendFrame(_motorId, data, length);
        case PROTO_ETHERCAT:
            return EtherCAT::sendFrame(_motorId, data, length);
        default:
            return false;
    }
}

bool ProtocolAbstractionLayer::receiveFrame(uint8_t* data, uint8_t maxLength, uint8_t& receivedLength) {
    receivedLength = 0;
    (void)maxLength;
    switch (_config.protocol) {
        case PROTO_CAN: {
            uint32_t id = 0;
            return CANBus::receiveFrame(id, data, receivedLength);
        }
        case PROTO_RS485: {
            uint8_t addr = 0;
            return RS485::receiveFrame(addr, data, receivedLength);
        }
        case PROTO_ETHERCAT: {
            uint8_t mid = 0;
            return EtherCAT::receiveFrame(mid, data, receivedLength);
        }
        default:
            return false;
    }
}

void ProtocolAbstractionLayer::processCommands() {
    uint8_t data[64];
    uint8_t length = 0;

    if (!receiveFrame(data, (uint8_t)sizeof(data), length)) {
        return;
    }
    if (length < 2) {
        return;
    }

    FrameType frameType = (FrameType)data[0];
    uint8_t motorId = data[1];

    PalCommand cmd;
    cmd.frameType = frameType;
    cmd.motorId = motorId;
    cmd.targetPosition = 0.0f;
    cmd.targetVelocity = 0.0f;
    cmd.targetTorque = 0.0f;
    cmd.paramId = 0;
    cmd.paramValue = 0;

    switch (frameType) {
        case FRAME_TYPE_POSITION_CMD:
            handlePositionCmd(cmd);
            break;
        case FRAME_TYPE_VELOCITY_CMD:
            handleVelocityCmd(cmd);
            break;
        case FRAME_TYPE_TORQUE_CMD:
            handleTorqueCmd(cmd);
            break;
        case FRAME_TYPE_PARAM_READ:
            handleParamRead(cmd);
            break;
        case FRAME_TYPE_PARAM_WRITE:
            handleParamWrite(cmd);
            break;
        case FRAME_TYPE_HEARTBEAT:
            handleHeartbeat(cmd);
            break;
        case FRAME_TYPE_FIRMWARE_UPDATE:
            handleFirmwareUpdate(cmd);
            break;
        default:
            Logger::warn("PAL", "Unknown frame type %u", (uint8_t)frameType);
            break;
    }
}

void ProtocolAbstractionLayer::sendStatusReport() {
    sendStatusReport(_motorId, _status);
}

void ProtocolAbstractionLayer::sendStatusReport(uint8_t motorId, const PalStatusReport& status) {
    uint8_t frame[32];
    uint8_t len = 0;

    frame[len++] = (uint8_t)FRAME_TYPE_STATUS_REPORT;
    frame[len++] = motorId;
    memcpy(frame + len, &status.position, 4); len += 4;
    memcpy(frame + len, &status.velocity, 4); len += 4;
    memcpy(frame + len, &status.current, 4); len += 4;
    memcpy(frame + len, &status.temperature, 4); len += 4;
    frame[len++] = status.status;
    memcpy(frame + len, &status.errorCode, 4); len += 4;

    sendFrame(frame, len);
}

void ProtocolAbstractionLayer::sendHeartbeat() {
    uint8_t frame[2];
    frame[0] = (uint8_t)FRAME_TYPE_HEARTBEAT;
    frame[1] = _motorId;
    sendFrame(frame, 2);
}

PalStatusReport ProtocolAbstractionLayer::getStatus() const {
    return _status;
}

void ProtocolAbstractionLayer::handlePositionCmd(const PalCommand& cmd) {
    if (_motorDriver) {
        _motorDriver->setPosition(cmd.targetPosition);
    }
    Logger::info("PAL", "Position cmd motor %u", cmd.motorId);
}

void ProtocolAbstractionLayer::handleVelocityCmd(const PalCommand& cmd) {
    if (_motorDriver) {
        _motorDriver->setVelocity(cmd.targetVelocity);
    }
    Logger::info("PAL", "Velocity cmd motor %u", cmd.motorId);
}

void ProtocolAbstractionLayer::handleTorqueCmd(const PalCommand& cmd) {
    if (_motorDriver) {
        _motorDriver->setTorque(cmd.targetTorque);
    }
    Logger::info("PAL", "Torque cmd motor %u", cmd.motorId);
}

void ProtocolAbstractionLayer::handleParamRead(const PalCommand& cmd) {
    Logger::info("PAL", "Param read motor %u id %u", cmd.motorId, cmd.paramId);
}

void ProtocolAbstractionLayer::handleParamWrite(const PalCommand& cmd) {
    Logger::info("PAL", "Param write motor %u id %u", cmd.motorId, cmd.paramId);
}

void ProtocolAbstractionLayer::handleHeartbeat(const PalCommand& cmd) {
    (void)cmd;
}

void ProtocolAbstractionLayer::handleFirmwareUpdate(const PalCommand& cmd) {
    Logger::info("PAL", "Firmware update motor %u", cmd.motorId);
}

uint8_t ProtocolAbstractionLayer::calculateChecksum(const uint8_t* data, uint8_t length) {
    uint8_t checksum = 0;
    for (uint8_t i = 0; i < length; i++) {
        checksum ^= data[i];
    }
    return checksum;
}

bool ProtocolAbstractionLayer::validateFrame(const uint8_t* data, uint8_t length) {
    if (length < 2) return false;
    uint8_t expected = data[length - 1];
    uint8_t calculated = calculateChecksum(data, length - 1);
    return expected == calculated;
}

String ProtocolAbstractionLayer::getProtocolName() const {
    switch (_config.protocol) {
        case PROTO_CAN: return "CAN";
        case PROTO_RS485: return "RS485";
        case PROTO_ETHERCAT: return "EtherCAT";
        default: return "Unknown";
    }
}

String ProtocolAbstractionLayer::getMotorSeriesName() const {
    switch (_config.motorSeries) {
        case MOTOR_SERIES_RMD_X: return "RMD-X";
        case MOTOR_SERIES_RH: return "RH";
        case MOTOR_SERIES_CEM: return "CEM";
        case MOTOR_SERIES_RMD_H: return "RMD-H";
        case MOTOR_SERIES_RMD_L: return "RMD-L";
        case MOTOR_SERIES_FL: return "FL";
        default: return "Unknown";
    }
}
