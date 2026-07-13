/**
 * MyActuator ESP32 Motor Controller - Main Entry Point
 *
 * Supports all MyActuator motor series:
 * - RMD-X (Planetary)
 * - RH (Harmonic)
 * - CEM (Cycloid)
 * - RMD-H (Direct Drive Hollow)
 * - RMD-L (Direct Drive)
 * - FL (Linear)
 *
 * Protocols: CAN bus, RS485 (Modbus RTU), EtherCAT (CoE)
 */

#include <Arduino.h>
#include "protocols/pal.h"
#include "drivers/encoder.h"
#include "drivers/can_bus.h"
#include "drivers/rs485.h"
#include "drivers/ethercat.h"
#include "drivers/mcp2515_can.h"
#include "utils/config.h"
#include "utils/logger.h"
#include "constants.h"

// Global protocol abstraction layer instance
ProtocolAbstractionLayer pal;

// Motor configuration
MotorConfig motorConfig;

void setup() {
    Serial.begin(115200);
    delay(1000);

    Logger::init(Serial);
    Logger::info("MAIN", "MyActuator ESP32 Motor Controller v1.0.0");
    Logger::info("MAIN", "Motor Series: RMD_X");
    Logger::info("MAIN", "Protocol: %u", (uint8_t)PROTO_CAN);

    // Initialize motor configuration
    motorConfig.motorSeries = MOTOR_SERIES_RMD_X;
    motorConfig.protocol = PROTO_CAN;
    motorConfig.motorId = 1;
    motorConfig.baudRate = DEFAULT_BAUDRATE;
    motorConfig.maxTorque = DEFAULT_MAX_TORQUE;
    motorConfig.maxVelocity = DEFAULT_MAX_VELOCITY;
    motorConfig.kp = DEFAULT_KP;
    motorConfig.ki = DEFAULT_KI;
    motorConfig.kd = DEFAULT_KD;

    // Initialize Protocol Abstraction Layer
    pal.init(motorConfig);

    // Initialize communication protocol
    switch (motorConfig.protocol) {
        case PROTO_CAN:
            CANBus::init();
            break;
        case PROTO_RS485:
            RS485::init();
            break;
        case PROTO_ETHERCAT:
            EtherCAT::init();
            break;
        default:
            Logger::error("MAIN", "Unknown protocol");
            while (1) { delay(1000); }
    }

    Logger::info("MAIN", "System initialized successfully");
}

void loop() {
    // Process incoming commands
    pal.processCommands();

    // Send status reports
    pal.sendStatusReport();

    // Heartbeat
    pal.sendHeartbeat();

    // Small delay to prevent watchdog reset
    delay(1);
}
