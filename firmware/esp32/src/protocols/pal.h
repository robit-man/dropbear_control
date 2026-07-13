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

// PAL-local command/status structures. Note: types.h also defines wire-level
// `Command` and `StatusReport` structs; these are separate PAL abstractions.
struct PalCommand {
    uint8_t motorId;
    uint8_t frameType;
    float targetPosition;
    float targetVelocity;
    float targetTorque;
    uint32_t paramId;
    uint32_t paramValue;
};

struct PalStatusReport {
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

    void init(const MotorConfig& config);
    void deinitialize();

    // Command loop (driven from main loop)
    void processCommands();
    void sendStatusReport();
    void sendStatusReport(uint8_t motorId, const PalStatusReport& status);
    void sendHeartbeat();

    bool sendFrame(const uint8_t* data, uint8_t length);
    bool receiveFrame(uint8_t* data, uint8_t maxLength, uint8_t& receivedLength);

    void setMotorId(uint8_t motorId);
    uint8_t getMotorId() const;

    bool isConnected() const;

    // Command handlers
    void handlePositionCmd(const PalCommand& cmd);
    void handleVelocityCmd(const PalCommand& cmd);
    void handleTorqueCmd(const PalCommand& cmd);
    void handleParamRead(const PalCommand& cmd);
    void handleParamWrite(const PalCommand& cmd);
    void handleHeartbeat(const PalCommand& cmd);
    void handleFirmwareUpdate(const PalCommand& cmd);

    // Motor driver binding
    void setMotorDriver(IMotorDriver* driver);

    // Utility
    uint8_t calculateChecksum(const uint8_t* data, uint8_t length);
    bool validateFrame(const uint8_t* data, uint8_t length);
    PalStatusReport getStatus() const;
    String getMotorSeriesName() const;
    String getProtocolName() const;

private:
    uint8_t _motorId;
    void initCAN();
    void initRS485();
    void initEtherCAT();
    uint8_t _protocolType;
    bool _initialized;
    PalStatusReport _status;
    MotorConfig _config;
    IMotorDriver* _motorDriver;
};

#endif // PAL_H
