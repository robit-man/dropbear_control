# MyActuator ESP32 Motor Controller Firmware

## Overview

This directory contains prototype ESP32 scaffolding plus two production-path,
hardware-free cores: an official-source RMD classic-CAN V4.4 codec and a
deterministic command-lease safety supervisor. The current PAL, transports and
family drivers do not yet provide verified physical motor control. A successful
compile is not evidence that any actuator is supported.

## Cataloged Motor Series

- **RMD-X**: Planetary motor (10W - 2kW)
- **RH**: Harmonic motor (50W - 1.5kW)
- **CEM**: Cycloid actuator (100W - 1.2kW)
- **RMD-H**: Direct drive hollow motor (200W - 2kW)
- **RMD-L**: Direct drive motor
- **FL/FLO**

These labels describe repository/catalog coverage, not implemented or
hardware-verified support. Support must be recorded for an exact `(model,
hardware revision, drive firmware, protocol version, transport, control
mode)` tuple.

## Communication Scaffolding

- **Official RMD native CAN V4.4 offline core**: classic CAN, 1 Mbit/s,
  standard 11-bit IDs, DLC 8, request `0x140 + motor ID`, response
  `0x240 + motor ID`, logical IDs 1–32. Applicability to installed hardware is
  unverified.
- **Legacy MCP2515, RS485 and EtherCAT adapters**: incomplete prototype code;
  their current constants and mappings are not authoritative.

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

The `esp32` environment currently compiles (RAM ~6.8%, Flash ~22.8%); this is a
compile-only result.

## Configuration

### Motor Series Selection

The current environments define several family macros simultaneously and then
select RMD-X through `MOTOR_SERIES`; this is a known prototype defect, not a
family compile matrix. Future environments must select exactly one evidenced
model/transport tuple. The legacy flags are:

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

### WebSerial Two-Way Control

In addition to the PAL transports (CAN/RS485/EtherCAT), `main.cpp` binds a
`SerialBridge` to the USB CDC `Serial` port. The bridge parses the 64-byte
unified protocol frames (contracts/PROTOCOLS_CONTRACT.md section 3) arriving
over WebSerial and dispatches them to the `MotorController`:

- `src/serial_frame.h` — pure-C++ frame pack/unpack + CRC-16/CCITT-FALSE
  (matches `web/js/protocol.js` and `host/myactuator_lib/protocol/frame.py`).
- `src/serial_bridge.h/.cpp` — 64-byte frame parser, command dispatch
  (position/velocity/torque), and periodic `STATUS_REPORT` emission.

The web dashboard (`web/`) can exercise this synthetic frame path and render
toy `STATUS_REPORT` telemetry. That path is not integrated with the official
V4.4 codec/safety boundary and must not be used to command powered hardware.

> Note: `Logger` also writes text to the same `Serial` stream. The dashboard
> resyncs on 64-byte boundaries and ignores non-frame bytes, so interleaved log
> lines are tolerated. For a clean machine-only link, route frames to a
> separate UART (`Serial1`/`Serial2`) and point the dashboard there.

## Protocol Details

### CAN Bus

- **Canonical offline V4.4 core**: standard 11-bit classic-CAN data frames,
  DLC 8, 1 Mbit/s, logical IDs 1–32.
- **Legacy MCP2515 adapter**: still uses conflicting 500 kbit/s/base-ID
  assumptions and is not connected to the canonical core.

### RS485

- The existing Modbus-like mapping is a draft without sufficient vendor
  evidence and is not supported.

### EtherCAT

- The current CoE object/ID mapping is unverified scaffolding and is not
  supported.

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

### Complete offline gate

```bash
tools/test_all.sh
```

### Protocol and safety cores only

```bash
tests/protocol/run_tests.sh
tests/safety/run_tests.sh
```

Hardware upload/monitor steps are intentionally excluded from the offline
gate. Bench and HIL procedures require an exact hardware inventory, independent
power-removal path, current limits, verified stop semantics and supervision.

## Documentation

- [PROTOCOLS_CONTRACT.md](../../contracts/PROTOCOLS_CONTRACT.md) - legacy draft
- [MOTOR_RMD_X_CONTRACT.md](../../contracts/MOTOR_RMD_X_CONTRACT.md) - legacy draft
- [MOTOR_RH_CONTRACT.md](../../contracts/MOTOR_RH_CONTRACT.md) - legacy draft
- [MOTOR_CEM_CONTRACT.md](../../contracts/MOTOR_CEM_CONTRACT.md) - legacy draft
- [MOTOR_RMD_H_CONTRACT.md](../../contracts/MOTOR_RMD_H_CONTRACT.md) - legacy draft

## License

Proprietary - MyActuator

## Support

For technical support, contact: support@myactuator.com
