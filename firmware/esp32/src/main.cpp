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
 *
 * Two-way control over USB CDC Serial (WebSerial):
 *   The SerialBridge parses the 64-byte unified protocol frames
 *   (contracts/PROTOCOLS_CONTRACT.md section 3) arriving on Serial and
 *   dispatches them to the MotorController. It also emits STATUS_REPORT
 *   frames so the web dashboard can visualize live state.
 */

#include <Arduino.h>
#include "protocols/pal.h"
#include "drivers/encoder.h"
#include "drivers/can_bus.h"
#include "drivers/rs485.h"
#include "drivers/ethercat.h"
#include "drivers/mcp2515_can.h"
#include "drivers/motor_driver.h"
#include "motor_controller.h"
#include "serial_bridge.h"
#include "utils/config.h"
#include "utils/logger.h"
#include "constants.h"

// Quadrature encoder pins (override via build_flags: -DPIN_ENCODER_A=...).
#ifndef PIN_ENCODER_A
#define PIN_ENCODER_A 34
#endif
#ifndef PIN_ENCODER_B
#define PIN_ENCODER_B 35
#endif
#ifndef PIN_ENCODER_Z
#define PIN_ENCODER_Z 32
#endif

// Global protocol abstraction layer instance
ProtocolAbstractionLayer pal;

// Motor configuration
MotorConfig motorConfig;

// Active motor controller + serial bridge (two-way WebSerial control)
MotorController* controller = nullptr;
SerialBridge* bridge = nullptr;
IMotorDriver* driver = nullptr;

// Build the per-series driver selected at compile time via build flags.
static IMotorDriver* createDriver(uint8_t motorId, const MotorConfig& config) {
#if defined(MOTOR_RMD_X)
    return new RMDXDriver(motorId, config);
#elif defined(MOTOR_RH)
    return new RHDriver(motorId, config);
#elif defined(MOTOR_CEM)
    return new CEMDriver(motorId, config);
#elif defined(MOTOR_RMD_H)
    return new RMDHDriver(motorId, config);
#elif defined(MOTOR_RMD_L)
    return new RMDLDriver(motorId, config);
#elif defined(MOTOR_FL)
    return new FLDriver(motorId, config);
#else
    (void)motorId;
    (void)config;
    return nullptr;
#endif
}

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

    // Build the per-series motor driver + controller, then bind the serial
    // bridge for two-way WebSerial control.
    driver = createDriver(motorConfig.motorId, motorConfig);
    if (driver) {
        controller = new MotorController(motorConfig.motorId, motorConfig);
        controller->setMotorDriver(driver);
        // Bind the quadrature encoder so position/velocity telemetry is real
        // (otherwise the SerialBridge status report is always zero).
        Encoder* encoder = new Encoder(PIN_ENCODER_A, PIN_ENCODER_B, PIN_ENCODER_Z);
        #if defined(ENCODER_BITS)
        encoder->setResolution(ENCODER_BITS >= 18 ? ENCODER_18BIT
                            : ENCODER_BITS >= 17 ? ENCODER_17BIT
                            : ENCODER_14BIT);
        #endif
        controller->setEncoder(encoder);
        if (controller->initialize()) {
            Logger::info("MAIN", "Motor controller initialized");
        } else {
            Logger::error("MAIN", "Motor controller init failed");
        }
        bridge = new SerialBridge(Serial, *controller, motorConfig.motorId);
        bridge->begin();
    } else {
        Logger::error("MAIN", "No motor driver for selected series");
    }

    Logger::info("MAIN", "System initialized successfully");
}

void loop() {
    // Process incoming commands (PAL transport: CAN/RS485/EtherCAT)
    pal.processCommands();

    // Send status reports (PAL transport)
    pal.sendStatusReport();

    // Heartbeat (PAL transport)
    pal.sendHeartbeat();

    // Two-way WebSerial bridge: parse 64-byte frames, run the control loop,
    // and emit STATUS_REPORT frames back to the dashboard.
    if (bridge) {
        bridge->update();
    }

    // Small delay to prevent watchdog reset
    delay(1);
}
