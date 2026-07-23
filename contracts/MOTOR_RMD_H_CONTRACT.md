# RMD-H Direct Drive Motor Series Implementation Contract

**Version:** 1.0.0  
**Status:** Draft  
**Motor Series:** RMD-H (Integrated Direct Drive Module - Hollow)  
**Power Range:** 200W - 2kW  
**Reference:** PROTOCOLS_CONTRACT.md, ESP32_FIRMWARE_CONTRACT.md  

> **Non-authoritative legacy draft.** Example ratings, opcodes, limits and
> torque mappings below are not exact-model/firmware evidence and must not be
> used for powered control.

---

## 1. Overview

The RMD-H series is MyActuator's integrated direct drive motor with hollow center, designed for applications requiring through-bore access and high torque density. This contract defines the implementation details for controlling RMD-H motors via ESP32 firmware.

---

## 2. Model Number Decoding

### 2.1 Model Number Format

```
EPS-RMD-H-{PowerClass}-{BoreDiameter}-{Brake}-{DriveType}-{Communication}-{EncoderBits}
```

### 2.2 Field Definitions

| Field | Description | Values |
|-------|------|--------|
| EPS | Efficiency Precision Smart | Fixed prefix |
| RMD-H | Reducer Motor Drive - Direct Drive (Hollow) | Series identifier |
| PowerClass | Power rating class | 1=200-300W, 2=300-400W, 3=400-500W, ... 15=1.8-2.0kW |
| BoreDiameter | Through-bore diameter | 20, 25, 30, 40, 50, 60, 80 |
| Brake | Brake configuration | 1=With brake, 0=No brake |
| DriveType | Drive electronics | M=MC, S=S3, D=DRC, W=Wifi |
| Communication | Communication interface | C=CAN, R=RS485, E=EtherCAT |
| EncoderBits | Encoder resolution | 17, 18, 23 (multi-turn) |

### 2.3 Example Model Numbers

| Model | Power | Bore | Brake | Drive | Comm | Encoder |
|-------|-------|------|-------|-------|------|---------|
| EPS-RMD-H-1-20-0-M-C-17 | 200-300W | 20mm | No | MC | CAN | 17-bit |
| EPS-RMD-H-5-40-1-S-R-18 | 400-500W | 40mm | Yes | S3 | RS485 | 18-bit |
| EPS-RMD-H-10-60-0-D-E-23 | 800W-1kW | 60mm | No | DRC | EtherCAT | 23-bit multi-turn |

### 2.4 Power Class Mapping

| Class | Power Range | Rated Torque | Peak Torque |
|-------|------|-|-|
| 1 | 200-300W | 1.2 Nm | 3.6 Nm |
| 2 | 300-400W | 1.8 Nm | 5.4 Nm |
| 3 | 400-500W | 2.4 Nm | 7.2 Nm |
| 4 | 500-600W | 3.0 Nm | 9.0 Nm |
| 5 | 500-600W | 3.6 Nm | 10.8 Nm |
| 6 | 600-700W | 4.2 Nm | 12.6 Nm |
| 7 | 700-800W | 4.8 Nm | 14.4 Nm |
| 8 | 800W-1kW | 5.4 Nm | 16.2 Nm |
| 9 | 1.0-1.1kW | 6.0 Nm | 18.0 Nm |
| 10 | 1.1-1.2kW | 6.6 Nm | 19.8 Nm |
| 11 | 1.2-1.3kW | 7.2 Nm | 21.6 Nm |
| 12 | 1.3-1.4kW | 7.8 Nm | 23.4 Nm |
| 13 | 1.4-1.5kW | 8.4 Nm | 25.2 Nm |
| 14 | 1.5-1.6kW | 9.0 Nm | 27.0 Nm |
| 15 | 1.8-2.0kW | 10.8 Nm | 32.4 Nm |

---

## 3. Electrical Specifications

### 3.1 Voltage Ratings

| Model Size | Rated Voltage | Voltage Range |
|------|----|------|
| 1-5 (200-600W) | 48V DC | 36V - 60V |
| 6-10 (600W-1.2kW) | 72V DC | 54V - 84V |
| 11-15 (1.2-2.0kW) | 72V DC | 54V - 84V |

### 3.2 Current Ratings (Example: RMD-H-5, 500-600W)

| Parameter | Value |
|------|------|
| Rated Voltage | 48V |
| Rated Current | 12.5A |
| Peak Current (30s) | 37.5A |
| Phase Resistance | 0.08Ω |
| Phase Inductance | 0.15mH |
| Back-EMF Constant | 8 V/kRPM |

### 3.3 Encoder Specifications

| Encoder Type | Resolution | Accuracy | Interface |
|------|----|------|------|
| 17-bit Absolute | 131072 counts/rev | ±0.06° | SPI |
| 18-bit Absolute | 262144 counts/rev | ±0.03° | SPI |
| 23-bit Multi-turn | 8388608 counts/rev, 16384 turns | ±0.003° | SPI |

---

## 4. Mechanical Specifications

### 4.1 Flange Sizes

| Model Size | Flange Diameter | Mounting Holes | Bore Diameter |
|------|----|----|----|
| 1-2 | 80mm | 4x M6 | 20mm |
| 3-4 | 100mm | 4x M8 | 25-30mm |
| 5-7 | 120mm | 4x M10 | 40-50mm |
| 8-10 | 150mm | 4x M12 | 60mm |
| 11-15 | 180mm | 4x M16 | 80mm |

### 4.2 Dimensions (Example: RMD-H-5, 40mm Bore)

| Parameter | Value |
|------|------|
| Motor Length | 95mm |
| Flange Thickness | 15mm |
| Weight (no brake) | 4.5kg |
| Weight (with brake) | 5.2kg |

### 4.3 Shaft Configuration

- **Standard:** Hollow shaft (through-bore)
- **Bore Sizes:** 20mm, 25mm, 30mm, 40mm, 50mm, 60mm, 80mm
- **Shaft End:** Threaded (M12, M16, M20 depending on size)

### 4.4 IP Rating

- **Standard:** IP65 (motor), IP67 (connector)
- **Optional:** IP67 (motor), IP69K (connector)

---

## 5. Performance Characteristics

### 5.1 Torque-Speed Curve (Example: RMD-H-5, 500-600W)

| Speed (RPM) | Continuous Torque (Nm) | Peak Torque (Nm) |
|------|----|----|
| 0 | 3.6 | 10.8 |
| 100 | 3.5 | 10.5 |
| 200 | 3.3 | 9.9 |
| 500 | 2.8 | 8.4 |
| 1000 | 2.0 | 6.0 |
| 2000 | 1.0 | 3.0 |
| 3000 | 0.6 | 1.8 |

### 5.2 Efficiency

| Speed (RPM) | Efficiency |
|------|----|
| 0 | N/A (stall) |
| 500 | 92% |
| 1000 | 95% |
| 2000 | 94% |
| 3000 | 91% |

### 5.3 Inertia

| Component | Inertia (kg·cm²) |
|------|----|
| Rotor | 1.2 |
| Shaft | 0.1 |
| **Total** | **1.3** |

### 5.4 Thermal Characteristics

| Parameter | Value |
|------|------|
| Thermal Time Constant | 350 seconds |
| Thermal Resistance | 40 °C/W |
| Max Winding Temperature | 155°C (Class F insulation) |
| Max Case Temperature | 100°C |

---

## 6. Command Set

### 6.1 Motor-Specific Commands

| Command | Byte | Description |
|------|------|------|
| GET_MOTOR_INFO | 0x10 | Get motor model and firmware version |
| SET_BORE_SIZE | 0x11 | Set through-bore diameter |
| CALIBRATE_ENCODER | 0x12 | Calibrate encoder offset |
| SET_TORQUE_CONSTANT | 0x13 | Set torque constant for current control |
| GET_TORQUE_CURVE | 0x14 | Get torque-speed curve data |
| SET_THERMAL_MODEL | 0x15 | Set thermal model parameters |
| SET_MULTI_TURN_CONFIG | 0x16 | Configure multi-turn encoder |

### 6.2 Parameter Addresses

| Parameter | Address | Size | Default | Description |
|------|------|------|---------|------|
| Bore Diameter | 0x0010 | 16-bit | 40 | Through-bore diameter (mm) |
| Encoder Offset | 0x0012 | 32-bit | 0 | Encoder zero offset |
| Torque Constant | 0x0013 | 16-bit | 80 | Torque constant (mNm/A) |
| Thermal Time Constant | 0x0014 | 16-bit | 350 | Thermal time constant (seconds) |
| Thermal Resistance | 0x0015 | 16-bit | 40 | Thermal resistance (°C/W) |
| Max Continuous Current | 0x0016 | 16-bit | 12500 | Max continuous current (mA) |
| Max Peak Current | 0x0017 | 16-bit | 37500 | Max peak current (mA) |
| Multi-turn Count | 0x0018 | 32-bit | 16384 | Multi-turn encoder count |

### 6.3 Status Word Bit Definitions

| Bit | Name | Description |
|--|------|------|
| 0 | Ready | Motor is ready to receive commands |
| 1 | Enabled | Motor drive is enabled |
| 2 | Fault | Fault condition active |
| 3 | Overtemperature | Motor temperature > 100°C |
| 4 | Overcurrent | Current > 1.5x rated |
| 5 | Position Error | Position error > limit |
| 6 | Homing Complete | Homing sequence finished |
| 7 | Brake Engaged | Brake is engaged |
| 8 | Hollow Shaft | Through-bore shaft active |
| 9 | Multi-turn | Multi-turn encoder active |
| 10-15 | Reserved | - |

### 6.4 Fault Code Definitions

| Fault Code | Name | Description | Recovery |
|------|------|----|----|
| 0x00 | None | No fault | - |
| 0x01 | Overtemperature | Motor temp > 120°C | Cool down, reset |
| 0x02 | Overcurrent | Current > 2x rated | Reduce load, reset |
| 0x03 | Encoder Fault | Encoder communication error | Check wiring, reset |
| 0x04 | Comm Timeout | Communication timeout | Check connection, reset |
| 0x05 | Position Error | Position error > limit | Check mechanics, reset |
| 0x06 | Brake Fault | Brake not responding | Check wiring, reset |
| 0x07 | Internal Error | Firmware/internal error | Reset, update firmware |

---

## 7. Firmware Version History

### 7.1 Known Firmware Versions

| Version | Date | Changes |
|------|------|-----|
| 1.0.0 | 2024-01-20 | Initial release |
| 1.1.0 | 2024-04-10 | Added thermal model |
| 1.2.0 | 2024-07-15 | Improved current control |
| 1.3.0 | 2024-10-20 | Added multi-turn encoder support |
| 2.0.0 | 2025-02-15 | Major rewrite, new protocol support |

### 7.2 Compatibility Matrix

| Firmware | Motor Hardware | Protocol Support |
|------|----|----|
| 1.0.0-1.2.0 | RMD-H Gen1 | CAN, RS485 |
| 1.3.0+ | RMD-H Gen1, Gen2 | CAN, RS485, EtherCAT |
| 2.0.0+ | RMD-H Gen2 | CAN, RS485, EtherCAT |

### 7.3 Upgrade Procedure

1. **Download Firmware:** Get `.bin` file from MyActuator website
2. **Prepare Update:** Connect motor to master controller
3. **Enter Bootloader:** Send `0xAA55` command to motor
4. **Transfer Firmware:** Stream `.bin` file via CAN/RS485
5. **Verify CRC:** Motor verifies CRC-32 of received data
6. **Commit Update:** Motor writes to OTA partition
7. **Reboot:** Motor reboots with new firmware
8. **Verify:** Check firmware version via `GET_MOTOR_INFO`

---

## 8. Configuration Profiles

### 8.1 Default PID Gains (RMD-H-5, 500-600W)

| Parameter | Value | Unit |
|------|------|------|
| P-Gain (Position) | 4.0 | - |
| I-Gain (Position) | 0.05 | - |
| D-Gain (Position) | 0.0 | - |
| P-Gain (Velocity) | 1.5 | - |
| I-Gain (Velocity) | 0.3 | - |
| D-Gain (Velocity) | 0.005 | - |
| P-Gain (Current) | 0.8 | - |
| I-Gain (Current) | 8.0 | - |
| D-Gain (Current) | 0.0 | - |

### 8.2 Limit Settings

| Parameter | Default | Unit | Description |
|------|------|------|------|
| Current Limit | 12500 | mA | Max continuous current |
| Velocity Limit | 3000 | RPM | Max speed |
| Position Error Limit | 1000 | counts | Max position error |
| Temperature Limit | 80 | °C | Max operating temperature |
| Torque Limit | 3.6 | Nm | Max continuous torque |

### 8.3 Encoder Calibration Procedure

1. **Manual Positioning:** Rotate motor to known reference position
2. **Send Calibration Command:** `CALIBRATE_ENCODER`
3. **Motor Records Offset:** Motor stores current encoder value as zero
4. **Verify:** Check encoder reads 0 at reference position

### 8.4 Thermal Management

1. **Monitor Temperature:** Read winding temperature via resistance measurement
2. **Derate Torque:** Reduce torque command based on temperature
3. **Fault Trigger:** If temperature > 120°C, trigger fault and disable motor

---

## 9. STEP File References

### 9.1 File Naming Convention

```
RMD-H-{PowerClass}-{BoreDiameter}-{Brake}.step
```

### 9.2 Example STEP Files

| Model | STEP File |
|------|------|
| RMD-H-1-20-0 | `RMD-H-1-20-0.step` |
| RMD-H-5-40-1 | `RMD-H-5-40-1.step` |
| RMD-H-10-60-0 | `RMD-H-10-60-0.step` |

### 9.3 Coordinate System

- **Origin:** Center of motor, on mounting face
- **X-Axis:** Along shaft, pointing outward
- **Y-Axis:** Upward (perpendicular to mounting face)
- **Z-Axis:** Right-hand rule (forward from mounting face)

### 9.4 Mounting Hole Pattern

```
        Y
        ↑
        │
   ●────┼────●
   │    │    │
   ●────┼────●  → X
   │         │
   ●         ●
        │
        ↓
       Z (out of page)
```

- **Hole Spacing:** 80mm (center-to-center, RMD-H-5 example)
- **Hole Diameter:** 7mm (for M6 bolts)
- **Pattern:** Square, 80mm x 80mm

### 9.5 Shaft Interface Dimensions

| Parameter | Value |
|------|------|
| Bore Diameter | 40mm (RMD-H-5 example) |
| Shaft End Thread | M16 |
| Keyway | Optional, 10mm width |

---

## 10. ESP32 Integration

### 10.1 Pin Mapping (ESP32 DevKitC)

| Signal | Pin | Notes |
|------|------|------|
| CAN_TX | GPIO5 | CAN bus transmit |
| CAN_RX | GPIO4 | CAN bus receive |
| Encoder_SCK | GPIO19 | Encoder clock |
| Encoder_MISO | GPIO21 | Encoder data out |
| Encoder_MOSI | GPIO22 | Encoder data in |
| Encoder_SS | GPIO23 | Encoder chip select |
| Brake | GPIO15 | Brake control (active high) |
| Status LED | GPIO2 | Status indicator |

### 10.2 Initialization Sequence

```cpp
// 1. Initialize communication protocol
protocol.init();

// 2. Initialize encoder
encoder.init();

// 3. Read motor parameters
motor.readParameters();

// 4. Calibrate encoder (if needed)
if (needs_calibration) {
    motor.calibrateEncoder();
}

// 5. Set operating profile
motor.setProfile(DEFAULT_PROFILE);

// 6. Enable motor
motor.enable();
```

### 10.3 Runtime Control Loop

```cpp
void controlLoop() {
    // 1. Read encoder
    int32_t position = encoder.readPosition();
    
    // 2. Read status
    MotorStatus status = motor.getStatus();
    
    // 3. Calculate error
    int32_t error = target_position - position;
    
    // 4. PID control
    float output = pidController.compute(error, dt);
    
    // 5. Apply limits
    output = constrain(output, -max_torque, max_torque);
    
    // 6. Send command
    motor.setTorque(output);
    
    // 7. Check safety
    if (status.fault || status.overtemp) {
        motor.disable();
        motor.clearFault();
    }
}
```

---

## 11. References

- **Protocols Contract:** See PROTOCOLS_CONTRACT.md
- **ESP32 Firmware Contract:** See ESP32_FIRMWARE_CONTRACT.md
- **Simulation Contract:** See SIMULATION_CONTRACT.md

---

## 12. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-07-03 | Omnius | Initial draft |
