# RMD-X Planetary Motor Series Implementation Contract

**Version:** 1.0.0  
**Status:** Draft  
**Motor Series:** RMD-X (Integrated Planetary Module)  
**Power Range:** 10W - 2kW  
**Reference:** PROTOCOLS_CONTRACT.md, ESP32_FIRMWARE_CONTRACT.md  

> **Non-authoritative legacy draft.** Example ratings, opcodes, limits and
> torque mappings below are not exact-model/firmware evidence and must not be
> used for powered control.

---

## 1. Overview

The RMD-X series is MyActuator's integrated planetary motor module, combining a brushless DC motor with a planetary gearbox in a single compact package. This contract defines the implementation details for controlling RMD-X motors via ESP32 firmware.

---

## 2. Model Number Decoding

### 2.1 Model Number Format

```
EPS-RMD-X-{PowerClass}-{ReductionRatio}-{Brake}-{DriveType}-{Communication}-{EncoderBits}
```

### 2.2 Field Definitions

| Field | Description | Values |
|-------|------|--------|
| EPS | Efficiency Precision Smart | Fixed prefix |
| RMD-X | Reducer Motor Drive - Planetary | Series identifier |
| PowerClass | Power rating class | 1=10-100W, 2=100-200W, 3=200-300W, ... 20=1.5-2.0kW |
| ReductionRatio | Gearbox reduction ratio | 5, 10, 20, 25, 50, 100, 125, 200, 250, 500 |
| Brake | Brake configuration | 1=With brake, 0=No brake |
| DriveType | Drive electronics | M=MC, S=S3, D=DRC, W=Wifi |
| Communication | Communication interface | C=CAN, R=RS485, E=EtherCAT |
| EncoderBits | Encoder resolution | 14, 17, 18 |

### 2.3 Example Model Numbers

| Model | Power | Reduction | Brake | Drive | Comm | Encoder |
|-------|-------|-----------|-------|-------|------|---------|
| EPS-RMD-X-1-10-0-M-C-14 | 10-100W | 10:1 | No | MC | CAN | 14-bit |
| EPS-RMD-X-5-50-1-S-R-17 | 400-500W | 50:1 | Yes | S3 | RS485 | 17-bit |
| EPS-RMD-X-10-100-0-D-E-18 | 800W-1kW | 100:1 | No | DRC | EtherCAT | 18-bit |

### 2.4 Power Class Mapping

| Class | Power Range | Rated Torque (No-Reducer) | Peak Torque (No-Reducer) |
|-------|------|------|------|
| 1 | 10-100W | 0.32 Nm | 0.96 Nm |
| 2 | 100-200W | 0.64 Nm | 1.92 Nm |
| 3 | 200-300W | 0.96 Nm | 2.88 Nm |
| 4 | 300-400W | 1.28 Nm | 3.84 Nm |
| 5 | 400-500W | 1.60 Nm | 4.80 Nm |
| 6 | 500-600W | 1.92 Nm | 5.76 Nm |
| 7 | 600-700W | 2.24 Nm | 6.72 Nm |
| 8 | 700-800W | 2.56 Nm | 7.68 Nm |
| 9 | 800W-1kW | 2.88 Nm | 8.64 Nm |
| 10 | 1.0-1.1kW | 3.20 Nm | 9.60 Nm |
| 11 | 1.1-1.2kW | 3.52 Nm | 10.56 Nm |
| 12 | 1.2-1.3kW | 3.84 Nm | 11.52 Nm |
| 13 | 1.3-1.4kW | 4.16 Nm | 12.48 Nm |
| 14 | 1.4-1.5kW | 4.48 Nm | 13.44 Nm |
| 15 | 1.5-1.6kW | 4.80 Nm | 14.40 Nm |
| 16 | 1.6-1.7kW | 5.12 Nm | 15.36 Nm |
| 17 | 1.7-1.8kW | 5.44 Nm | 16.32 Nm |
| 18 | 1.8-1.9kW | 5.76 Nm | 17.28 Nm |
| 19 | 1.9-2.0kW | 6.08 Nm | 18.24 Nm |
| 20 | 1.5-2.0kW | 6.40 Nm | 19.20 Nm |

---

## 3. Electrical Specifications

### 3.1 Voltage Ratings

| Model Size | Rated Voltage | Voltage Range |
|------|----|------|
| 1-5 (10-500W) | 24V DC | 18V - 36V |
| 6-10 (500W-1kW) | 48V DC | 36V - 60V |
| 11-20 (1.1-2.0kW) | 72V DC | 54V - 84V |

### 3.2 Current Ratings (Example: RMD-X-5, 400-500W)

| Parameter | Value |
|------|------|
| Rated Voltage | 48V |
| Rated Current | 8.5A |
| Peak Current (30s) | 25.5A |
| Phase Resistance | 0.15Ω |
| Phase Inductance | 0.3mH |
| Back-EMF Constant | 12 V/kRPM |

### 3.3 Encoder Specifications

| Encoder Type | Resolution | Accuracy | Interface |
|------|----|------|------|
| 14-bit Absolute | 16384 counts/rev | ±0.5° | SPI |
| 17-bit Absolute | 131072 counts/rev | ±0.06° | SPI |
| 18-bit Absolute | 262144 counts/rev | ±0.03° | SPI |

---

## 4. Mechanical Specifications

### 4.1 Flange Sizes

| Model Size | Flange Diameter | Mounting Holes | Shaft Diameter |
|------|----|----|----|
| 1-2 | 40mm | 4x M3 | 8mm |
| 3-4 | 58mm | 4x M4 | 11mm |
| 5-7 | 70mm | 4x M5 | 14mm |
| 8-10 | 90mm | 4x M6 | 19mm |
| 11-15 | 110mm | 4x M8 | 24mm |
| 16-20 | 130mm | 4x M10 | 28mm |

### 4.2 Dimensions (Example: RMD-X-5, 50:1 Reduction)

| Parameter | Value |
|------|------|
| Total Length (with reducer) | 145mm |
| Motor Length | 85mm |
| Reducer Length | 60mm |
| Weight (no brake) | 2.8kg |
| Weight (with brake) | 3.2kg |

### 4.3 Shaft Configuration

- **Standard:** Round shaft with keyway
- **Options:** Hollow shaft, spline shaft, lead screw
- **Shaft End:** Threaded (M6, M8, M10 depending on size)

### 4.4 IP Rating

- **Standard:** IP65 (motor), IP67 (connector)
- **Optional:** IP67 (motor), IP69K (connector)

---

## 5. Performance Characteristics

### 5.1 Torque-Speed Curve (Example: RMD-X-5, 50:1)

| Speed (RPM) | Continuous Torque (Nm) | Peak Torque (Nm) |
|------|----|----|
| 0 | 250 | 750 |
| 100 | 240 | 720 |
| 200 | 220 | 660 |
| 500 | 180 | 540 |
| 1000 | 120 | 360 |
| 2000 | 60 | 180 |
| 3000 | 30 | 90 |

### 5.2 Efficiency

| Reduction Ratio | Efficiency at Rated Load |
|------|----|
| 5:1 | 95% |
| 10:1 | 92% |
| 20:1 | 88% |
| 50:1 | 82% |
| 100:1 | 75% |
| 200:1 | 68% |
| 500:1 | 58% |

### 5.3 Backlash

| Reduction Ratio | Backlash (arc-min) |
|------|----|
| 5:1 | 5 |
| 10:1 | 8 |
| 20:1 | 12 |
| 50:1 | 20 |
| 100:1 | 35 |
| 200:1 | 60 |
| 500:1 | 120 |

### 5.4 Inertia

| Component | Inertia (kg·cm²) |
|------|----|
| Motor Rotor | 0.5 |
| Reducer (reflected) | 2.0 (50:1 example) |
| Output Shaft | 0.3 |
| **Total** | **2.8** |

---

## 6. Command Set

### 6.1 Motor-Specific Commands

| Command | Byte | Description |
|------|------|------|
| GET_MOTOR_INFO | 0x10 | Get motor model and firmware version |
| SET_REDUCTION_RATIO | 0x11 | Set gearbox reduction ratio |
| CALIBRATE_ENCODER | 0x12 | Calibrate encoder offset |
| SET_BACKLASH_COMP | 0x13 | Set backlash compensation value |
| GET_TORQUE_CURVE | 0x14 | Get torque-speed curve data |
| SET_THERMAL_MODEL | 0x15 | Set thermal model parameters |

### 6.2 Parameter Addresses

| Parameter | Address | Size | Default | Description |
|------|------|------|---------|------|
| Reduction Ratio | 0x0010 | 16-bit | 50 | Gearbox ratio |
| Backlash | 0x0011 | 16-bit | 20 | Backlash compensation (arc-sec) |
| Encoder Offset | 0x0012 | 32-bit | 0 | Encoder zero offset |
| Thermal Time Constant | 0x0013 | 16-bit | 300 | Thermal time constant (seconds) |
| Thermal Resistance | 0x0014 | 16-bit | 50 | Thermal resistance (°C/W) |
| Max Continuous Current | 0x0015 | 16-bit | 8500 | Max continuous current (mA) |
| Max Peak Current | 0x0016 | 16-bit | 25500 | Max peak current (mA) |

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
| 8-15 | Reserved | - |

### 6.4 Fault Code Definitions

| Fault Code | Name | Description | Recovery |
|------|------|----|----|
| 0x00 | None | No fault | - |
| 0x01 | Overtemperature | Motor temp > 120°C | Cool down, reset |
| 0x02 | Overcurrent | Current > 2x rated | Reduce load, reset |
| 0x03 | Encoder Fault | Encoder communication error | Check wiring, reset |
| 0x04 | Comm Timeout | Communication timeout | Check connection, reset |
| 0x05 | Position Error | Position error > 1000 counts | Check mechanics, reset |
| 0x06 | Brake Fault | Brake not responding | Check wiring, reset |
| 0x07 | Internal Error | Firmware/internal error | Reset, update firmware |

---

## 7. Firmware Version History

### 7.1 Known Firmware Versions

| Version | Date | Changes |
|------|------|-----|
| 1.0.0 | 2024-01-15 | Initial release |
| 1.1.0 | 2024-03-20 | Added backlash compensation |
| 1.2.0 | 2024-06-10 | Improved thermal model |
| 1.3.0 | 2024-09-05 | Added auto-tuning |
| 2.0.0 | 2025-01-15 | Major rewrite, new protocol support |

### 7.2 Compatibility Matrix

| Firmware | Motor Hardware | Protocol Support |
|------|----|----|
| 1.0.0-1.2.0 | RMD-X Gen1 | CAN, RS485 |
| 1.3.0+ | RMD-X Gen1, Gen2 | CAN, RS485, EtherCAT |
| 2.0.0+ | RMD-X Gen2 | CAN, RS485, EtherCAT |

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

### 8.1 Default PID Gains (RMD-X-5, 50:1)

| Parameter | Value | Unit |
|------|------|------|
| P-Gain (Position) | 5.0 | - |
| I-Gain (Position) | 0.1 | - |
| D-Gain (Position) | 0.0 | - |
| P-Gain (Velocity) | 2.0 | - |
| I-Gain (Velocity) | 0.5 | - |
| D-Gain (Velocity) | 0.01 | - |
| P-Gain (Current) | 1.0 | - |
| I-Gain (Current) | 10.0 | - |
| D-Gain (Current) | 0.0 | - |

### 8.2 Limit Settings

| Parameter | Default | Unit | Description |
|------|------|------|------|
| Current Limit | 8500 | mA | Max continuous current |
| Velocity Limit | 3000 | RPM | Max output speed |
| Position Error Limit | 1000 | counts | Max position error |
| Temperature Limit | 80 | °C | Max operating temperature |

### 8.3 Encoder Calibration Procedure

1. **Manual Positioning:** Rotate motor to known reference position
2. **Send Calibration Command:** `CALIBRATE_ENCODER`
3. **Motor Records Offset:** Motor stores current encoder value as zero
4. **Verify:** Check encoder reads 0 at reference position

### 8.4 Backlash Compensation

1. **Measure Backlash:** Rotate motor +1000 counts, then -2000 counts, then +1000 counts
2. **Calculate Compensation:** Compensation = (Position2 - Position1) / 2
3. **Set Compensation:** Send `SET_BACKLASH_COMP` with calculated value
4. **Verify:** Repeat measurement, error should be < 10 arc-sec

---

## 9. STEP File References

### 9.1 File Naming Convention

```
RMD-X-{PowerClass}-{ReductionRatio}-{Brake}.step
```

### 9.2 Example STEP Files

| Model | STEP File |
|------|------|
| RMD-X-1-10-0 | `RMD-X-1-10-0.step` |
| RMD-X-5-50-1 | `RMD-X-5-50-1.step` |
| RMD-X-10-100-0 | `RMD-X-10-100-0.step` |

### 9.3 Coordinate System

- **Origin:** Center of output shaft
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

- **Hole Spacing:** 60mm (center-to-center)
- **Hole Diameter:** 4.5mm (for M4 bolts)
- **Pattern:** Square, 60mm x 60mm

### 9.5 Shaft Interface Dimensions

| Parameter | Value |
|------|------|
| Shaft Diameter | 14mm (RMD-X-5 example) |
| Keyway Width | 5mm |
| Keyway Depth | 2.5mm |
| Thread Size | M10 (shaft end) |

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
