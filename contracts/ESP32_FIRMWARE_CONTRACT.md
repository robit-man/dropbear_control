# ESP32 Firmware Implementation Contract

**Version:** 1.0.0
**Status:** Draft
**Target Platform:** ESP32 (ESP32 DevKitC, ESP32-S3)
**Build System:** PlatformIO
**Reference:** PROTOCOLS_CONTRACT.md, MOTOR_RMD_X_CONTRACT.md, MOTOR_RH_CONTRACT.md, MOTOR_CEM_CONTRACT.md, MOTOR_RMD_H_CONTRACT.md

---

## 1. Overview

This contract defines the ESP32 firmware architecture for controlling all MyActuator motor series. The firmware implements a unified control loop with motor-specific drivers and a Protocol Abstraction Layer (PAL) for communication.

### 1.1 Architecture Layers

| Layer | Responsibility |
|-------|---------------|
| Application | State machine, command dispatch, safety monitoring |
| Motor Drivers | Per-motor-series control (RMD-X, RH, CEM, RMD-H, RMD-L, FL) |
| Control Loop | PID, current control, encoder processing |
| Protocol Abstraction | Unified interface for CAN, RS485, EtherCAT |
| Hardware Abstraction | GPIO, SPI, I2C, ADC, PWM, UART |

### 1.2 Directory Structure

```
firmware/esp32/
├── platformio.ini
├── README.md
├── include/
│   ├── config.h          # Build configuration, pin mappings
│   ├── types.h           # Common type definitions
│   └── constants.h       # Physical constants, scaling factors
├── src/
│   ├── main.cpp          # Entry point, initialization
│   ├── drivers/
│   │   ├── motor_driver.h    # Abstract motor driver interface
│   │   ├── rmd_x_driver.h    # RMD-X planetary motor driver
│   │   ├── rh_driver.h       # RH harmonic motor driver
│   │   ├── cem_driver.h      # CEM cycloid actuator driver
│   │   ├── rmd_h_driver.h    # RMD-H direct drive motor driver
│   │   ├── rmd_l_driver.h    # RMD-L direct drive motor driver
│   │   └── fl_driver.h       # FL linear actuator driver
│   ├── protocols/
│   │   ├── pal.h           # Protocol Abstraction Layer interface
│   │   ├── can_protocol.h  # CAN bus implementation
│   │   ├── rs485_protocol.h # RS485/Modbus RTU implementation
│   │   └── ethercat_protocol.h # EtherCAT/CoE implementation
│   └── utils/
│       ├── pid.h           # PID controller
│       ├── encoder.h       # Encoder processing
│       ├── safety.h        # Safety monitoring
│       └── logger.h        # Diagnostic logging
└── lib/
    └── (third-party libraries)
```

### 1.3 Build Configuration

The `platformio.ini` defines two environments:

- **esp32**: ESP32 DevKitC with PSRAM
- **esp32s3**: ESP32-S3 DevKitC with PSRAM

Build flags enable all motor series and protocols via conditional compilation.

---

## 2. Motor Driver Interface

All motor drivers implement the `IMotorDriver` interface:

```cpp
class IMotorDriver {
public:
    virtual ~IMotorDriver() = default;
    
    // Initialization
    virtual bool init() = 0;
    virtual void deinit() = 0;
    
    // State queries
    virtual MotorStatus getStatus() = 0;
    virtual float getTemperature() = 0;
    virtual int32_t getPosition() = 0;
    virtual float getVelocity() = 0;
    virtual float getCurrent() = 0;
    
    // Control commands
    virtual void setPosition(float target) = 0;
    virtual void setVelocity(float target) = 0;
    virtual void setTorque(float target) = 0;
    virtual void enable() = 0;
    virtual void disable() = 0;
    virtual void faultReset() = 0;
    
    // Configuration
    virtual void setLimits(float maxVelocity, float maxTorque) = 0;
    virtual void setGains(float kp, float ki, float kd) = 0;
};
```

### 2.1 Motor-Specific Extensions

Each motor series adds series-specific commands:

- **RMD-X**: Gearbox ratio configuration, backlash compensation
- **RH**: Harmonic drive ratio, zero calibration
- **CEM**: Stroke length, cycloid phase offset
- **RMD-H**: Hollow bore access, direct drive inertia compensation
- **RMD-L**: Direct drive tuning, cogging compensation
- **FL**: Linear scale calibration, force feedback

---

## 3. Protocol Abstraction Layer (PAL)

The PAL provides a unified interface for all communication protocols:

```cpp
class IProtocol {
public:
    virtual ~IProtocol() = default;
    
    virtual bool init() = 0;
    virtual void deinit() = 0;
    
    virtual bool send(const Frame& frame) = 0;
    virtual bool receive(Frame& frame, uint32_t timeout_ms = 100) = 0;
    
    virtual ProtocolType getType() const = 0;
    virtual uint8_t getNodeId() const = 0;
    virtual void setNodeId(uint8_t id) = 0;
};
```

### 3.1 Frame Structure

All protocols use a unified 64-byte frame format (see PROTOCOLS_CONTRACT.md Section 3).

### 3.2 Protocol Selection

The active protocol is selected at build time via `#define PROTOCOL_CAN`, `PROTOCOL_RS485`, or `PROTOCOL_ETHERCAT`.

---

## 4. Control Loop

### 4.1 Control Loop Timing

- **Current loop**: 10 kHz (hardware timer interrupt)
- **Velocity loop**: 1 kHz (software timer)
- **Position loop**: 100 Hz (software timer)
- **Communication**: Protocol-dependent (CAN: 100 Hz, RS485: 50 Hz, EtherCAT: 1 kHz)

### 4.2 PID Implementation

```cpp
class PIDController {
public:
    void setGains(float kp, float ki, float kd);
    void setLimits(float outputMin, float outputMax);
    float compute(float setpoint, float measurement, float dt);
    void reset();
};
```

### 4.3 Encoder Processing

- **14-bit encoder**: 16384 counts/rev
- **17-bit encoder**: 131072 counts/rev
- **18-bit encoder**: 262144 counts/rev

Quadrature decoding with hardware timer capture.

---

## 5. Safety System

### 5.1 Fault Monitoring

- Over-temperature (>85°C): Disable motor, log fault
- Over-current (>150% rated): Disable motor, log fault
- Position limit violation: Soft stop, log warning
- Communication timeout (>500ms): Disable motor, log fault
- Voltage undervoltage (<10V): Disable motor, log fault

### 5.2 Safe State Machine

```
IDLE → ENABLE → RUNNING → FAULT → IDLE
                ↓
              DISABLE
```

---

## 6. Configuration

### 6.1 Pin Mapping (ESP32 DevKitC)

| Function | Pin |
|----------|-----|
| Motor PWM A | GPIO 18 |
| Motor PWM B | GPIO 19 |
| Encoder A | GPIO 4 |
| Encoder B | GPIO 5 |
| Encoder Z | GPIO 16 |
| Current sense ADC | GPIO 34 |
| Temperature ADC | GPIO 35 |
| CAN TX | GPIO 22 |
| CAN RX | GPIO 23 |
| RS485 TX | GPIO 17 |
| RS485 RX | GPIO 16 |
| RS485 DE/RE | GPIO 21 |
| EtherCAT TX | GPIO 22 |
| EtherCAT RX | GPIO 23 |
| Status LED | GPIO 2 |
| Fault LED | GPIO 25 |
| Enable button | GPIO 32 |
| Fault reset button | GPIO 33 |

### 6.2 Motor Configuration

Each motor series has a configuration structure:

```cpp
struct MotorConfig {
    uint8_t motorId;
    float ratedVoltage;
    float ratedCurrent;
    float ratedTorque;
    float maxVelocity;
    float maxTorque;
    float gearboxRatio;
    uint16_t encoderResolution;
    float kp, ki, kd;
    float maxVelocityLimit;
    float maxTorqueLimit;
};
```

---

## 7. Diagnostic Logging

### 7.1 Log Levels

- **ERROR**: Fault conditions, critical failures
- **WARN**: Degraded operation, limit violations
- **INFO**: State transitions, configuration changes
- **DEBUG**: Control loop data, protocol frames

### 7.2 Log Format

```
[timestamp] [level] [module] message
```

Example:
```
[1234567] [ERROR] [MOTOR] Over-temperature fault: 92.3°C
[1234568] [INFO] [PAL] CAN frame received: ID=0x100, type=STATUS_REPORT
```

---

## 8. Firmware Update

### 8.1 Update Procedure

1. Receive firmware image via selected protocol
2. Verify CRC32 checksum
3. Erase target flash sector
4. Write firmware image
5. Verify written data
6. Reset to application

### 8.2 Bootloader

A minimal bootloader (not in this contract) handles:
- USB DFU mode entry
- Firmware verification
- Application jump

---

## 9. Memory Optimization

### 9.1 Flash Usage Targets

- Bootloader: <16 KB
- Application: <256 KB
- NVS (configuration): <32 KB
- Firmware update buffer: <64 KB

### 9.2 RAM Usage Targets

- Control loop stack: 2 KB
- Protocol buffers: 4 KB
- Motor driver state: 2 KB
- Logging buffer: 1 KB

---

## 10. References

- PROTOCOLS_CONTRACT.md
- MOTOR_RMD_X_CONTRACT.md
- MOTOR_RH_CONTRACT.md
- MOTOR_CEM_CONTRACT.md
- MOTOR_RMD_H_CONTRACT.md
- ESP32 Arduino Core Documentation
- ESP-IDF Reference Manual

---

## 11. Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-07-03 | Omnius | Initial draft |
