# MyActuator ESP32 Motor Controller Firmware

## Overview

This firmware implements motor control for all MyActuator motor series using
ESP32 microcontrollers. It provides a unified Protocol Abstraction Layer (PAL)
that supports CAN bus, RS485 (Modbus RTU), and EtherCAT (CoE) communication
protocols, and dispatches decoded commands to per-motor drivers through a
common `IMotorDriver` interface.

## Supported Motor Series

- **RMD-X**: Planetary motor (10W - 2kW)
- **RH**: Harmonic motor (50W - 1.5kW)
- **CEM**: Cycloid actuator (100W - 1.2kW)
- **RMD-H**: Direct drive hollow motor (200W - 2kW)
- **RMD-L**: Direct drive motor
- **FL**: Linear actuator

## Communication Protocols

- **CAN bus**: ISO 11898-1, 500kbps, 29-bit extended IDs (MCP2515 via SPI)
- **RS485**: Modbus RTU, 115200 baud, 8N1
- **EtherCAT**: CoE (CANopen over EtherCAT), 1ms cycle time, DC sync

## Project Structure

```
firmware/esp32/
├── platformio.ini            # PlatformIO environments (esp32/esp32s3/esp32c3/esp32s3dev)
├── include/
│   ├── config.h              # Compile-time configuration macros
│   ├── constants.h           # Default limits / baud / PID constants
│   └── types.h               # Shared types (MotorConfig, FaultCode, etc.)
├── src/
│   ├── main.cpp              # Entry point: init PAL + selected transport
│   ├── motor_controller.h/.cpp
│   ├── protocols/
│   │   ├── pal.h / pal.cpp   # Protocol Abstraction Layer
│   │   └── rs485_protocol.h  # RS485/Modbus framing helpers
│   ├── drivers/
│   │   ├── encoder.h/.cpp
│   │   ├── can_bus.h/.cpp
│   │   ├── mcp2515_can.h/.cpp
│   │   ├── rs485.h/.cpp
│   │   ├── ethercat.h/.cpp
│   │   ├── motor_driver.h    # IMotorDriver interface
│   │   ├── rmd_x_driver.h/.cpp
│   │   ├── rh_driver.h/.cpp
│   │   ├── cem_driver.h/.cpp
│   │   ├── rmd_h_driver.h/.cpp
│   │   ├── rmd_l_driver.h/.cpp
│   │   └── fl_driver.h/.cpp
│   └── utils/
│       ├── config.h/.cpp
│       ├── logger.h/.cpp
│       └── pid_controller.h/.cpp
└── README.md
```

## Building

### Prerequisites

- PlatformIO CLI (`pip install platformio`)
- ESP32 development board (ESP32 DevKitC, ESP32-S3, or ESP32-C3)

### Build Commands

```bash
# Build for ESP32
pio run -e esp32

# Build for ESP32-S3
pio run -e esp32s3

# Upload to board
pio run -e esp32 -t upload

# Monitor serial output
pio device monitor -b 115200
```

The `esp32` environment currently builds clean (RAM ~6.6%, Flash ~22.0%).

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

```ini
build_flags =
    -DPROTOCOL_CAN_BUS
    -DPROTOCOL_RS485
    -DPROTOCOL_ETHERCAT
```

### Encoder Resolution

```ini
build_flags =
    -DENCODER_BITS=14   # 14-bit absolute (16384 counts/rev)
    -DENCODER_BITS=17   # 17-bit absolute (131072 counts/rev)
    -DENCODER_BITS=18   # 18-bit absolute (262144 counts/rev)
```

## API Usage

### Initialization

```cpp
#include "protocols/pal.h"
#include "drivers/motor_driver.h"

ProtocolAbstractionLayer pal;
MotorConfig motorConfig;

void setup() {
    Serial.begin(115200);
    Logger::init(Serial);

    // Configure motor
    motorConfig.motorSeries = MOTOR_SERIES_RMD_X;
    motorConfig.protocol    = PROTO_CAN;
    motorConfig.motorId     = 1;
    motorConfig.baudRate    = DEFAULT_BAUDRATE;
    motorConfig.maxTorque   = DEFAULT_MAX_TORQUE;
    motorConfig.maxVelocity = DEFAULT_MAX_VELOCITY;
    motorConfig.kp = DEFAULT_KP;
    motorConfig.ki = DEFAULT_KI;
    motorConfig.kd = DEFAULT_KD;

    // Initialize PAL and bind the selected transport
    pal.init(motorConfig);
    pal.initCAN();
}
```

### Runtime Loop

```cpp
void loop() {
    pal.processCommands();    // decode + dispatch incoming frames to the driver
    pal.sendStatusReport();   // periodic telemetry
    pal.sendHeartbeat();      // liveness
    delay(1);
}
```

The PAL exposes `init()`, `setMotorDriver()`, `setMotorId()`, `processCommands()`,
`sendStatusReport()`, `sendHeartbeat()`, `initCAN()`, and `initEtherCAT()`.
Decoded commands are forwarded to the active `IMotorDriver` implementation
(`rmd_x_driver`, `rh_driver`, `cem_driver`, `rmd_h_driver`, `rmd_l_driver`,
`fl_driver`).

## Protocol Details

### CAN Bus

- **Frame Format**: 29-bit extended IDs
- **Baud Rate**: 500kbps
- **Motor ID**: Configurable per motor
- **Frame Types**: STATUS_REPORT, POSITION_CMD, VELOCITY_CMD, TORQUE_CMD,
  PARAM_READ, PARAM_WRITE, DIAGNOSTIC, FIRMWARE_UPDATE, HEARTBEAT

### RS485 (Modbus RTU)

- **Baud Rate**: 115200
- **Data Format**: 8N1
- **Function Codes**: 0x03 (Read Holding Registers), 0x06 (Write Single
  Register), 0x08 (Diagnostics)

### EtherCAT (CoE)

- **Cycle Time**: 1ms (configurable)
- **DC Sync**: Enabled
- **SDO Access**:
  - Read:  `0x600 + (motor_id << 4) + 0x0A`
  - Write: `0x600 + (motor_id << 4) + 0x0B`
  - Response: `0x580 + (motor_id << 4)`

## Development

### Adding a New Motor Series

1. Add a motor series enum/constant in `include/types.h` and `pal.h`.
2. Create motor-specific driver files in `src/drivers/` implementing
   `IMotorDriver` (see `motor_driver.h`).
3. Register the driver in `main.cpp` / PAL dispatch.
4. Add motor-specific configuration macros to `platformio.ini`.

### Adding a New Protocol

1. Create a protocol driver in `src/drivers/` (e.g. `can_bus`, `rs485`,
   `ethercat`).
2. Add a protocol enum/constant to `pal.h`.
3. Implement protocol-specific init/dispatch in `pal.cpp` (e.g. `initCAN()`,
   `initEtherCAT()`).
4. Wire it into `main.cpp`.

## Testing

### Unit Tests

```bash
pio test -e esp32
```

### Integration Tests

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
