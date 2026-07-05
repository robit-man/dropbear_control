# CEM Cycloid Actuator Series Implementation Contract

**Version:** 1.0.0  
**Status:** Draft  
**Motor Series:** CEM (Integrated Cycloid Module)  
**Power Range:** 100W - 1.2kW  
**Reference:** PROTOCOLS_CONTRACT.md, ESP32_FIRMWARE_CONTRACT.md  

---

## 1. Overview

The CEM series is MyActuator's integrated cycloid actuator module, combining a brushless DC motor with a cycloidal drive for high-torque, compact linear and rotary actuation. This contract defines the implementation details for controlling CEM actuators via ESP32 firmware.

---

## 2. Model Number Decoding

### 2.1 Model Number Format

```
EPS-CEM-{PowerClass}-{StrokeOrRatio}-{Brake}-{DriveType}-{Communication}-{EncoderBits}
```

### 2.2 Field Definitions

| Field | Description | Values |
|-------|------|--------|
| EPS | Efficiency Precision Smart | Fixed prefix |
| CEM | Cycloid Electro-Mechanical | Series identifier |
| PowerClass | Power rating class | 1=100-200W, 2=200-300W, 3=300-400W, ... 10=1.0-1.2kW |
| StrokeOrRatio | Stroke (mm) or reduction ratio | 10, 20, 30, 50, 80, 100, 150, 200 |
| Brake | Brake configuration | 1=With brake, 0=No brake |
| DriveType | Drive electronics | M=MC, S=S3, D=DRC, W=Wifi |
| Communication | Communication interface | C=CAN, R=RS485, E=EtherCAT |
| EncoderBits | Encoder resolution | 14, 17, 18 |

### 2.3 Example Model Numbers

| Model | Power | Stroke/Ratio | Brake | Drive | Comm | Encoder |
|-------|-------|--------------|-------|-------|------|---------|
| EPS-CEM-1-20-0-M-C-14 | 100-200W | 20mm stroke | No | MC | CAN | 14-bit |
| EPS-CEM-5-50-1-S-R-17 | 400-500W | 50mm stroke | Yes | S3 | RS485 | 17-bit |
| EPS-CEM-8-100-0-D-E-18 | 700-800W | 100mm stroke | No | DRC | EtherCAT | 18-bit |

### 2.4 Power Class Mapping

| Class | Power Range | Rated Force (Linear) | Peak Force (Linear) |
|-------|------|-|-|
| 1 | 100-200W | 500N | 1500N |
| 2 | 200-300W | 800N | 2400N |
| 3 | 300-400W | 1100N | 3300N |
| 4 | 400-500W | 1400N | 4200N |
| 5 | 400-500W | 1600N | 4800N |
| 6 | 500-600W | 1800N | 5400N |
| 7 | 600-700W | 2000N | 6000N |
| 8 | 700-800W | 2200N | 6600N |
| 9 | 800W-1kW | 2500N | 7500N |
| 10 | 1.0-1.2kW | 2800N | 8400N |

---

## 3. Electrical Specifications

### 3.1 Voltage Ratings

| Model Size | Rated Voltage | Voltage Range |
|------|----|------|
| 1-5 (100-500W) | 24V DC | 18V - 36V |
| 6-10 (500W-1.2kW) | 48V DC | 36V - 60V |

### 3.2 Current Ratings (Example: CEM-5, 400-500W)

| Parameter | Value |
|------|------|
| Rated Voltage | 48V |
| Rated Current | 9.5A |
| Peak Current (30s) | 28.5A |
| Phase Resistance | 0.12Ω |
| Phase Inductance | 0.28mH |
| Back-EMF Constant | 10 V/kRPM |

### 3.3 Encoder Specifications

| Encoder Type | Resolution | Accuracy | Interface |
|------|----|------|------|
| 14-bit Absolute | 16384 counts/rev | ±0.5° | SPI |
| 17-bit Absolute | 131072 counts/rev | ±0.06° | SPI |
| 18-bit Absolute | 262144 counts/rev | ±0.03° | SPI |

---

## 4. Mechanical Specifications

### 4.1 Actuator Types

| Type | Description | Stroke Range |
|------|------|----|
| Linear | Linear actuation via ball screw | 10-200mm |
| Rotary | Rotary actuation via cycloidal drive | 0-360° (multi-turn) |

### 4.2 Dimensions (Example: CEM-5, 50mm Stroke, Linear)

| Parameter | Value |
|------|------|
| Total Length (extended) | 180mm |
| Total Length (retracted) | 130mm |
| Width | 65mm |
| Height | 65mm |
| Weight (no brake) | 3.2kg |
| Weight (with brake) | 3.7kg |

### 4.3 Mounting Configuration

- **Standard:** Flange mount with through-bolts
- **Options:** Foot mount, side mount, custom brackets
- **Mounting Holes:** 4x M5, 50mm spacing

### 4.4 IP Rating

- **Standard:** IP65 (actuator), IP67 (connector)
- **Optional:** IP67 (actuator), IP69K (connector)

---

## 5. Performance Characteristics

### 5.1 Force-Speed Curve (Example: CEM-5, 50mm Stroke)

| Speed (mm/s) | Continuous Force (N) | Peak Force (N) |
|------|----|----|
| 0 | 1600 | 4800 |
| 10 | 1550 | 4650 |
| 20 | 1450 | 4350 |
| 50 | 1200 | 3600 |
| 100 | 800 | 2400 |
| 200 | 400 | 1200 |
| 500 | 160 | 480 |

### 5.2 Efficiency

| Stroke Length | Efficiency at Rated Load |
|------|----|
| 10mm | 85% |
| 20mm | 82% |
| 50mm | 78% |
| 100mm | 73% |
| 200mm | 68% |

### 5.3 Positioning Accuracy

| Parameter | Value |
|------|------|
| Repeatability | ±0.01mm |
| Accuracy | ±0.02mm |
| Backlash | <0.005mm |

### 5.4 Duty Cycle

| Stroke Length | Max Duty Cycle | Cooling Time |
|------|----|----|
| 10mm | 100% | None |
| 20mm | 80% | 30s |
| 50mm | 60% | 60s |
| 100mm | 40% | 120s |
| 200mm | 20% | 180s |

---

## 6. Command Set

### 6.1 Motor-Specific Commands

| Command | Byte | Description |
|------|------|------|
| GET_MOTOR_INFO | 0x10 | Get motor model and firmware version |
| SET_STROKE_LENGTH | 0x11 | Set actuator stroke length |
| CALIBRATE_ENCODER | 0x12 | Calibrate encoder offset |
| SET_FORCE_LIMIT | 0x13 | Set force limit |
| GET_FORCE_CURVE | 0x14 | Get force-speed curve data |
| SET_THERMAL_MODEL | 0x15 | Set thermal model parameters |
| SET_DUTY_CYCLE | 0x16 | Set duty cycle parameters |

### 6.2 Parameter Addresses

| Parameter | Address | Size | Default | Description |
|------|------|------|---------|------|
| Stroke Length | 0x0010 | 16-bit | 50 | Actuator stroke (mm) |
| Force Limit | 0x0011 | 16-bit | 1600 | Max force limit (N) |
| Encoder Offset | 0x0012 | 32-bit | 0 | Encoder zero offset |
| Thermal Time Constant | 0x0013 | 16-bit | 320 | Thermal time constant (seconds) |
| Thermal Resistance | 0x0014 | 16-bit | 55 | Thermal resistance (°C/W) |
| Max Continuous Force | 0x0015 | 16-bit | 1600 | Max continuous force (N) |
| Max Peak Force | 0x0016 | 16-bit | 4800 | Max peak force (N) |
| Duty Cycle | 0x0017 | 8-bit | 80 | Max duty cycle (%) |

### 6.3 Status Word Bit Definitions

| Bit | Name | Description |
|--|------|------|
| 0 | Ready | Actuator is ready to receive commands |
| 1 | Enabled | Actuator drive is enabled |
| 2 | Fault | Fault condition active |
| 3 | Overtemperature | Motor temperature > 100°C |
| 4 | Overcurrent | Current > 1.5x rated |
| 5 | Position Error | Position error > limit |
| 6 | Homing Complete | Homing sequence finished |
| 7 | Brake Engaged | Brake is engaged |
| 8 | End of Stroke | Actuator at stroke limit |
| 9-15 | Reserved | - |

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
| 0x07 | End of Stroke | Actuator at stroke limit | Retract, reset |
| 0x08 | Internal Error | Firmware/internal error | Reset, update firmware |

---

## 7. Firmware Version History

### 7.1 Known Firmware Versions

| Version | Date | Changes |
|------|------|-----|
| 1.0.0 | 2024-03-01 | Initial release |
| 1.1.0 | 2024-05-10 | Added force limiting |
| 1.2.0 | 2024-08-15 | Improved thermal model |
| 1.3.0 | 2024-11-20 | Added duty cycle management |
| 2.0.0 | 2025-03-01 | Major rewrite, new protocol support |

### 7.2 Compatibility Matrix

| Firmware | Motor Hardware | Protocol Support |
|------|----|----|
| 1.0.0-1.2.0 | CEM Gen1 | CAN, RS485 |
| 1.3.0+ | CEM Gen1, Gen2 | CAN, RS485, EtherCAT |
| 2.0.0+ | CEM Gen2 | CAN, RS485, EtherCAT |

### 7.3 Upgrade Procedure

1. **Download Firmware:** Get `.bin` file from MyActuator website
2. **Prepare Update:** Connect actuator to master controller
3. **Enter Bootloader:** Send `0xAA55` command to actuator
4. **Transfer Firmware:** Stream `.bin` file via CAN/RS485
5. **Verify CRC:** Actuator verifies CRC-32 of received data
6. **Commit Update:** Actuator writes to OTA partition
7. **Reboot:** Actuator reboots with new firmware
8. **Verify:** Check firmware version via `GET_MOTOR_INFO`

---

## 8. Configuration Profiles

### 8.1 Default PID Gains (CEM-5, 50mm Stroke)

| Parameter | Value | Unit |
|------|------|------|
| P-Gain (Position) | 8.0 | - |
| I-Gain (Position) | 0.2 | - |
| D-Gain (Position) | 0.0 | - |
| P-Gain (Velocity) | 3.0 | - |
| I-Gain (Velocity) | 0.8 | - |
| D-Gain (Velocity) | 0.02 | - |
| P-Gain (Force) | 2.0 | - |
| I-Gain (Force) | 15.0 | - |
| D-Gain (Force) | 0.0 | - |

### 8.2 Limit Settings

| Parameter | Default | Unit | Description |
|------|------|------|------|
| Force Limit | 1600 | N | Max continuous force |
| Velocity Limit | 200 | mm/s | Max actuation speed |
| Position Error Limit | 500 | counts | Max position error |
| Temperature Limit | 80 | °C | Max operating temperature |
| Duty Cycle Limit | 80 | % | Max duty cycle |

### 8.3 Encoder Calibration Procedure

1. **Manual Positioning:** Move actuator to known reference position
2. **Send Calibration Command:** `CALIBRATE_ENCODER`
3. **Actuator Records Offset:** Stores current encoder value as zero
4. **Verify:** Check encoder reads 0 at reference position

### 8.4 Force Limiting Procedure

1. **Set Force Limit:** Send `SET_FORCE_LIMIT` with desired limit
2. **Monitor Force:** Actuator monitors actual force via current sensing
3. **Limit Enforcement:** If force exceeds limit, reduce command
4. **Fault Trigger:** If force exceeds 1.5x limit, trigger fault

---

## 9. STEP File References

### 9.1 File Naming Convention

```
CEM-{PowerClass}-{Stroke}-{Brake}.step
```

### 9.2 Example STEP Files

| Model | STEP File |
|------|------|
| CEM-1-20-0 | `CEM-1-20-0.step` |
| CEM-5-50-1 | `CEM-5-50-1.step` |
| CEM-8-100-0 | `CEM-8-100-0.step` |

### 9.3 Coordinate System

- **Origin:** Center of actuator body
- **X-Axis:** Along stroke direction, pointing outward
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

- **Hole Spacing:** 50mm (center-to-center)
- **Hole Diameter:** 5.5mm (for M5 bolts)
- **Pattern:** Square, 50mm x 50mm

### 9.5 Actuator Interface Dimensions

| Parameter | Value |
|------|------|
| Rod Diameter | 12mm (CEM-5 example) |
| Rod Thread | M10 |
| Mounting Flange | 65mm x 65mm |
| Stroke Range | 10-200mm |

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

// 3. Read actuator parameters
actuator.readParameters();

// 4. Calibrate encoder (if needed)
if (needs_calibration) {
    actuator.calibrateEncoder();
}

// 5. Set operating profile
actuator.setProfile(DEFAULT_PROFILE);

// 6. Enable actuator
actuator.enable();
```

### 10.3 Runtime Control Loop

```cpp
void controlLoop() {
    // 1. Read encoder
    int32_t position = encoder.readPosition();
    
    // 2. Read status
    ActuatorStatus status = actuator.getStatus();
    
    // 3. Calculate error
    int32_t error = target_position - position;
    
    // 4. PID control
    float output = pidController.compute(error, dt);
    
    // 5. Apply force limits
    output = constrain(output, -max_force, max_force);
    
    // 6. Send command
    actuator.setForce(output);
    
    // 7. Check safety
    if (status.fault || status.overtemp || status.endOfStroke) {
        actuator.disable();
        actuator.clearFault();
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
