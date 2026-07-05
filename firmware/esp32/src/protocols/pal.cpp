/**
 * Protocol Abstraction Layer (PAL) - Implementation
 * 
 * Provides unified interface for CAN, RS485, and EtherCAT protocols
 */

#include "pal.h"
#include "../drivers/can_bus.h"
#include "../drivers/rs485.h"
#include "../drivers/ethercat.h"
#include "../utils/logger.h"

ProtocolAbstractionLayer::ProtocolAbstractionLayer() 
    : _initialized(false) {
    memset(&_status, 0, sizeof(StatusReport));
}

ProtocolAbstractionLayer::~ProtocolAbstractionLayer() {
}

void ProtocolAbstractionLayer::init(const MotorConfig& config) {
    _config = config;
    _initialized = true;
    
    Logger::info("PAL initialized with motor series: " + String((uint8_t)config.motorSeries));
    Logger::info("Protocol: " + String((uint8_t)config.protocol));
    
    // Initialize protocol-specific implementation
    switch (config.protocol) {
        case Protocol::CAN:
            initCAN();
            break;
        case Protocol::RS485:
            initRS485();
            break;
        case Protocol::ETHERCAT:
            initEtherCAT();
            break;
    }
}

void ProtocolAbstractionLayer::initCAN() {
    CANBus::init();
    Logger::info("CAN bus initialized");
}

void ProtocolAbstractionLayer::initRS485() {
    RS485::init();
    Logger::info("RS485 initialized");
}

void ProtocolAbstractionLayer::initEtherCAT() {
    EtherCAT::init();
    Logger::info("EtherCAT initialized");
}

void ProtocolAbstractionLayer::processCommands() {
    // Process incoming commands based on protocol
    switch (_config.protocol) {
        case Protocol::CAN: {
            uint32_t id;
            uint8_t data[64];
            uint8_t length;
            
            if (CANBus::receiveFrame(id, data, length)) {
                // Parse and handle command
                if (length >= 2) {
                    FrameType frameType = (FrameType)data[0];
                    uint8_t motorId = data[1];
                    
                    Command cmd;
                    cmd.frameType = frameType;
                    cmd.motorId = motorId;
                    memcpy(cmd.payload, data + 2, length - 2);
                    cmd.payloadLength = length - 2;
                    
                    switch (frameType) {
                        case FrameType::POSITION_CMD:
                            handlePositionCmd(cmd);
                            break;
                        case FrameType::VELOCITY_CMD:
                            handleVelocityCmd(cmd);
                            break;
                        case FrameType::TORQUE_CMD:
                            handleTorqueCmd(cmd);
                            break;
                        case FrameType::PARAM_READ:
                            handleParamRead(cmd);
                            break;
                        case FrameType::PARAM_WRITE:
                            handleParamWrite(cmd);
                            break;
                        case FrameType::DIAGNOSTIC:
                            handleDiagnostic(cmd);
                            break;
                        case FrameType::FIRMWARE_UPDATE:
                            handleFirmwareUpdate(cmd);
                            break;
                        case FrameType::HEARTBEAT:
                            handleHeartbeat(cmd);
                            break;
                        default:
                            Logger::warn("Unknown frame type: " + String((uint8_t)frameType));
                            break;
                    }
                }
            }
            break;
        }
        case Protocol::RS485: {
            uint8_t address;
            uint8_t data[64];
            uint8_t length;
            
            if (RS485::receiveFrame(address, data, length)) {
                // Parse Modbus RTU command
                if (length >= 3) {
                    uint8_t functionCode = data[1];
                    
                    Command cmd;
                    cmd.motorId = address;
                    memcpy(cmd.payload, data + 2, length - 2);
                    cmd.payloadLength = length - 2;
                    
                    switch (functionCode) {
                        case 0x03: // Read Holding Registers
                            handleParamRead(cmd);
                            break;
                        case 0x06: // Write Single Register
                            handleParamWrite(cmd);
                            break;
                        case 0x08: // Diagnostics
                            handleDiagnostic(cmd);
                            break;
                        default:
                            Logger::warn("Unknown Modbus function code: " + String(functionCode));
                            break;
                    }
                }
            }
            break;
        }
        case Protocol::ETHERCAT: {
            uint8_t motorId;
            uint8_t data[64];
            uint8_t length;
            
            if (EtherCAT::receiveFrame(motorId, data, length)) {
                // Parse EtherCAT CoE command
                Command cmd;
                cmd.motorId = motorId;
                memcpy(cmd.payload, data, length);
                cmd.payloadLength = length;
                
                // Handle CoE commands
                handleParamRead(cmd);
            }
            break;
        }
    }
}

void ProtocolAbstractionLayer::sendStatusReport() {
    // Build and send status report based on protocol
    StatusReport status = getStatus();
    
    uint8_t frame[64];
    uint8_t length = 0;
    
    frame[length++] = (uint8_t)FrameType::STATUS_REPORT;
    frame[length++] = static_cast<uint8_t>(_config.motorSeries);
    
    // Pack status data
    memcpy(frame + length, &status.position, 4); length += 4;
    memcpy(frame + length, &status.velocity, 4); length += 4;
    memcpy(frame + length, &status.torque, 2); length += 2;
    memcpy(frame + length, &status.temperature, 2); length += 2;
    memcpy(frame + length, &status.voltage, 2); length += 2;
    memcpy(frame + length, &status.current, 2); length += 2;
    frame[length++] = status.statusFlags;
    frame[length++] = status.errorFlags;
    
    // Send based on protocol
    switch (_config.protocol) {
        case Protocol::CAN:
            CANBus::sendFrame(0x00, frame, length);
            break;
        case Protocol::RS485:
            RS485::sendFrame(static_cast<uint8_t>(_config.motorSeries), frame, length);
            break;
        case Protocol::ETHERCAT:
            EtherCAT::sendFrame(static_cast<uint8_t>(_config.motorSeries), frame, length);
            break;
    }
}

void ProtocolAbstractionLayer::sendHeartbeat() {
    uint8_t frame[2];
    frame[0] = (uint8_t)FrameType::HEARTBEAT;
    frame[1] = static_cast<uint8_t>(_config.motorSeries);
    
    switch (_config.protocol) {
        case Protocol::CAN:
            CANBus::sendFrame(0x00, frame, 2);
            break;
        case Protocol::RS485:
            RS485::sendFrame(static_cast<uint8_t>(_config.motorSeries), frame, 2);
            break;
        case Protocol::ETHERCAT:
            EtherCAT::sendFrame(static_cast<uint8_t>(_config.motorSeries), frame, 2);
            break;
    }
}

StatusReport ProtocolAbstractionLayer::getStatus() const {
    return _status;
}

void ProtocolAbstractionLayer::setPosition(int32_t position) {
    _status.position = position;
}

void ProtocolAbstractionLayer::setVelocity(int32_t velocity) {
    _status.velocity = velocity;
}

void ProtocolAbstractionLayer::setTorque(int16_t torque) {
    _status.torque = torque;
}

bool ProtocolAbstractionLayer::readParameter(uint8_t paramId, uint8_t* data, uint8_t length) {
    // Implement parameter read based on protocol
    return true;
}

bool ProtocolAbstractionLayer::writeParameter(uint8_t paramId, const uint8_t* data, uint8_t length) {
    // Implement parameter write based on protocol
    return true;
}

String ProtocolAbstractionLayer::getProtocolName() const {
    switch (_config.protocol) {
        case Protocol::CAN: return "CAN";
        case Protocol::RS485: return "RS485";
        case Protocol::ETHERCAT: return "EtherCAT";
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

void ProtocolAbstractionLayer::handlePositionCmd(const Command& cmd) {
    if (cmd.payloadLength >= 4) {
        int32_t position;
        memcpy(&position, cmd.payload, 4);
        setPosition(position);
        Logger::info("Position command: " + String(position));
    }
}

void ProtocolAbstractionLayer::handleVelocityCmd(const Command& cmd) {
    if (cmd.payloadLength >= 4) {
        int32_t velocity;
        memcpy(&velocity, cmd.payload, 4);
        setVelocity(velocity);
        Logger::info("Velocity command: " + String(velocity));
    }
}

void ProtocolAbstractionLayer::handleTorqueCmd(const Command& cmd) {
    if (cmd.payloadLength >= 2) {
        int16_t torque;
        memcpy(&torque, cmd.payload, 2);
        setTorque(torque);
        Logger::info("Torque command: " + String(torque));
    }
}

void ProtocolAbstractionLayer::handleParamRead(const Command& cmd) {
    Logger::info("Parameter read request from motor " + String(cmd.motorId));
}

void ProtocolAbstractionLayer::handleParamWrite(const Command& cmd) {
    Logger::info("Parameter write request from motor " + String(cmd.motorId));
}

void ProtocolAbstractionLayer::handleDiagnostic(const Command& cmd) {
    Logger::info("Diagnostic request from motor " + String(cmd.motorId));
}

void ProtocolAbstractionLayer::handleFirmwareUpdate(const Command& cmd) {
    Logger::info("Firmware update request from motor " + String(cmd.motorId));
}

void ProtocolAbstractionLayer::handleHeartbeat(const Command& cmd) {
    // Heartbeat received, update status
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
    
    uint8_t expectedChecksum = data[length - 1];
    uint8_t calculatedChecksum = calculateChecksum(data, length - 1);
    
    return expectedChecksum == calculatedChecksum;
}
