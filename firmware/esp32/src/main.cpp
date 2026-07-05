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

// Global protocol abstraction layer instance
ProtocolAbstractionLayer pal;

// Motor configuration
MotorConfig motorConfig;

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Logger::init(Serial);
    Logger::info("MyActuator ESP32 Motor Controller v1.0.0");
    Logger::info("Motor Series: RMD_X");
    Logger::info("Protocol: " + String((uint8_t)PROTOCOL));
    
    // Initialize motor configuration
    motorConfig.motorSeries = static_cast<MotorSeries>(MOTOR_SERIES);
    motorConfig.protocol = static_cast<Protocol>(PROTOCOL);
    motorConfig.encoderBits = ENCODER_BITS;
    motorConfig.powerClass = POWER_CLASS;
    motorConfig.gearboxType = static_cast<GearboxType>(GEARBOX_TYPE);
    motorConfig.hasBrake = HAS_BRAKE;
    motorConfig.driveType = static_cast<DriveType>(DRIVE_TYPE);
    motorConfig.communication = static_cast<Communication>(COMMUNICATION);
    
    // Initialize Protocol Abstraction Layer
    pal.init(motorConfig);
    
    // Initialize encoder
    Encoder::init();
    
    // Initialize communication protocol
    switch (motorConfig.protocol) {
        case Protocol::CAN:
            CANBus::init();
            break;
        case Protocol::RS485:
            RS485::init();
            break;
        case Protocol::ETHERCAT:
            EtherCAT::init();
            break;
        default:
            Logger::error("Unknown protocol");
            while (1) { delay(1000); }
    }
    
    Logger::info("System initialized successfully");
}

void loop() {
    // Process incoming commands
    pal.processCommands();
    
    // Read encoder and update motor state
    Encoder::update();
    
    // Send status reports
    pal.sendStatusReport();
    
    // Heartbeat
    pal.sendHeartbeat();
    
    // Motor status logging (every 1000ms)
    static uint32_t lastStatusLog = 0;
    if (millis() - lastStatusLog >= 1000) {
        lastStatusLog = millis();
        Logger::info("Motor Status: State=%d, Pos=%.2f, Vel=%.2f, Torque=%.2f",
                    motorController.getState(),
                    motorController.getPosition(),
                    motorController.getVelocity(),
                    motorController.getTorque());
    }
    
    // Small delay to prevent watchdog reset
    delay(1);
}
