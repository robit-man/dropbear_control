# MyActuator ESP32 Motor Controller Firmware

## Overview

This firmware implements motor control for all MyActuator motor series using ESP32 microcontrollers. It provides a unified Protocol Abstraction Layer (PAL) that supports CAN bus, RS485 (Modbus RTU), and EtherCAT (CoE) communication protocols.

## Supported Motor Series

- **RMD-X**: Planetary motor (10W - 2kW)
- **RH**: Harmonic motor (50W - 1.5kW)
- **CEM**: Cycloid actuator (100W - 1.2kW)
- **RMD-H**: Direct drive hollow motor (200W - 2kW)
- **RMD-L**: Direct drive motor
- **FL**: Linear actuator

## Communication Protocols

- **CAN bus**: ISO 11898-1, 500kbps, 29-bit extended IDs
- **RS485**: Modbus RTU, 115200 baud, 8N1
- **EtherCAT**: CoE (CANopen over EtherCAT), 1ms cycle time, DC sync

## Project Structure

```
firmware/esp32/
├── platformio.ini          # PlatformIO configuration
├── src/
│   ├── main.cpp            # Main entry point
│   ├── protocols/
│   │   ├── pal.h           # Protocol Abstraction Layer header
│   │   └── pal.cpp         # Protocol Abstraction Layer implementation
│   ├── drivers/
│   │   ├── encoder.h       # Encoder driver header
│   │   ├── encoder.cpp     # Encoder driver implementation
│   │   ├── can_bus.h       # CAN bus driver header
│   │   ├── can_bus.cpp     # CAN bus driver implementation
│   │   ├── rs485.h         # RS485 driver header
│   │   ├── rs485.cpp       # RS485 driver implementation
│   │   ├── ethercat.h      # EtherCAT driver header
│   │   └── ethercat.cpp    # EtherCAT driver implementation
│   └── utils/
│       ├── config.h        # Configuration utilities header
│       ├── config.cpp      # Configuration utilities implementation
│       ├── logger.h        # Logger utilities header
│       └── logger.cpp      # Logger utilities implementation
└── lib/                    # External libraries
```

## Building

### Prerequisites

- PlatformIO CLI (`pip install platformio`)
- ESP32 development board (ESP32 DevKitC or ESP32-S3)

### Build Commands

```bash
# Build for ESP32
pio run -e esp32

# Build for ESP32-S3
pio run -e esp32s3

# Upload to ESP32
pio run -e esp32 -t upload

# Monitor serial output
pio device monitor -b 115200
```

## Configuration

### Motor Series Selection

Select motor series by defining preprocessor macros in `platformio.ini`:

```ini
build_flags =
    -DMOTOR_RMD_X    # RMD-X Planetary
    -DMOTOR_RH       # RH Harmonic
    -DMOTOR_CEM      # CEM Cycloid
    -DMOTOR_RMD_H    # RMD-H Direct Drive
    -DMOTOR_RMD_L    # RMD-L Direct Drive
    -DMOTOR_FL       # FL Linear
```

### Protocol Selection

Select communication protocol:

```ini
build_flags =
    -DPROTOCOL_CAN
    -DPROTOCOL_RS485
    -DPROTOCOL_ETHERCAT
```

### Encoder Resolution

Select encoder resolution:

```ini
build_flags =
    -DENCODER_14BIT   # 14-bit absolute (16384 counts/rev)
    -DENCODER_17BIT   # 17-bit absolute (131072 counts/rev)
    -DENCODER_18BIT   # 18-bit absolute (262144 counts/rev)
```

## API Usage

### Initialization

```cpp
#include "protocols/pal.h"

ProtocolAbstractionLayer pal;
MotorConfig config;

void setup() {
    // Configure motor
    config.motorSeries = MotorSeries::RMD_X;
    config.protocol = Protocol::CAN;
    config.encoderBits = 14;
    
    // Initialize PAL
    pal.init(config);
}
```

### Control Commands

```cpp
// Set position
pal.setPosition(1000);

// Set velocity
pal.setVelocity(500);

// Set torque
pal.setTorque(100);
```

### Status Reading

```cpp
StatusReport status = pal.getStatus();
Serial.print("Position: ");
Serial.println(status.position);
Serial.print("Velocity: ");
Serial.println(status.velocity);
```

## Protocol Details

### CAN Bus

- **Frame Format**: 29-bit extended IDs
- **Baud Rate**: 500kbps
- **Motor ID**: Configurable per motor
- **Frame Types**: STATUS_REPORT, POSITION_CMD, VELOCITY_CMD, TORQUE_CMD, PARAM_READ, PARAM_WRITE, DIAGNOSTIC, FIRMWARE_UPDATE, HEARTBEAT

### RS485 (Modbus RTU)

- **Baud Rate**: 115200
- **Data Format**: 8N1
- **Function Codes**: 0x03 (Read Holding Registers), 0x06 (Write Single Register), 0x08 (Diagnostics)

### EtherCAT (CoE)

- **Cycle Time**: 1ms (configurable)
- **DC Sync**: Enabled
- **SDO Access**: 
  - Read: `0x600 + (motor_id << 4) + 0x0A`
  - Write: `0x600 + (motor_id << 4) + 0x0B`
  - Response: `0x580 + (motor_id << 4)`

## Development

### Adding a New Motor Series

1. Add motor series enum to `pal.h`
2. Create motor-specific driver files in `src/drivers/`
3. Update `main.cpp` to initialize new motor
4. Add motor-specific configuration to `platformio.ini`

### Adding a New Protocol

1. Create protocol driver files in `src/drivers/`
2. Add protocol enum to `pal.h`
3. Implement protocol-specific methods in `pal.cpp`
4. Update `main.cpp` to support new protocol

## Testing

### Unit Tests

Run unit tests with:

```bash
pio test -e esp32
```

### Integration Tests

Connect motor and run integration tests:

```bash
pio run -e esp32 -t upload
pio device monitor -b 115200
```

## Documentation

- [PROTOCOLS_CONTRACT.md](../../contracts/PROTOCOLS_CONTRACT.md) - Protocol specifications
- [MOTOR_RMD_X_CONTRACT.md](../../contracts/MOTOR_RMD_X_CONTRACT.md) - RMD-X specifications
- [MOTOR_RH_CONTRACT.md](../../contracts/MOTOR_RH_CONTRACT.md) - RH specifications
- [MOTOR_CEM_CONTRACT.md](../../contracts/MOTOR_CEM_CONTRACT.md) - CEM specifications
- [MOTOR_RMD_H_CONTRACT.md](../../contracts/MOTOR_RMD_H_CONTRACT.md) - RMD-H specifications

## License

Proprietary - MyActuator

## Support

For technical support, contact: support@myactuator.com
