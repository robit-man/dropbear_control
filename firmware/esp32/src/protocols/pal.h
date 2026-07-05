/**
 * Protocol Abstraction Layer (PAL) - Header
 *
 * Provides a unified interface for CAN bus, RS485, and EtherCAT protocols.
 * Abstracts the underlying transport to provide consistent motor control.
 */

#ifndef PAL_H
#define PAL_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include "../include/types.h"
#include "../drivers/motor_driver.h"

// Command structure for protocol handlers
struct Command {
    uint8_t motorId;
    uint8_t frameType;
    float targetPosition;
    float targetVelocity;
    float targetTorque;
    uint32_t paramId;
    uint32_t paramValue;
};

// Status report structure
struct StatusReport {
    uint8_t motorId;
    uint8_t status;
    float position;
    float velocity;
    float current;
    float temperature;
    uint32_t errorCode;
};

// Protocol abstraction layer
class ProtocolAbstractionLayer {
public:
    ProtocolAbstractionLayer();
    ~ProtocolAbstractionLayer();

    bool initialize(uint8_t protocolType);
    void deinitialize();

    bool sendFrame(const uint8_t* data, uint8_t length);
    bool receiveFrame(uint8_t* data, uint8_t maxLength, uint8_t& receivedLength);

    void setMotorId(uint8_t motorId);
    uint8_t getMotorId() const;

    bool isConnected() const;

    // Command handlers
    void handlePositionCmd(const Command& cmd);
    void handleVelocityCmd(const Command& cmd);
    void handleTorqueCmd(const Command& cmd);
    void handleParamRead(const Command& cmd);
    void handleParamWrite(const Command& cmd);
    void handleHeartbeat(const Command& cmd);
    void handleFirmwareUpdate(const Command& cmd);

    // Utility
    uint8_t calculateChecksum(const uint8_t* data, uint8_t length);
    bool validateFrame(const uint8_t* data, uint8_t length);
    String getMotorSeriesName() const;
    String getProtocolName() const;

private:
    uint8_t _motorId;
    void initCAN();
    void initRS485();
    void initEtherCAT();
    void processCommands();
    uint8_t _protocolType;
    bool _initialized;
    StatusReport _status;
    MotorConfig _config;
};

#endif // PAL_H
