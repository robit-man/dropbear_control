# MyActuator Unified Protocol Contract

**Version:** 1.0.0  
**Status:** Draft  
**Target Platform:** ESP32 (ESP32 DevKitC, ESP32-S3)  
**Build System:** PlatformIO  

> **Non-authoritative legacy draft.** The IDs, bit rates, Modbus/CoE mappings,
> auto-detection behavior and torque semantics below are unverified prototype
> proposals and conflict with current vendor sources. They must not drive
> powered hardware. Use the source register and versioned codecs under
> `host/myactuator_lib/` and `firmware/esp32/src/protocols/`.

---

## 1. Overview

This contract defines the unified communication protocol layer that abstracts CAN bus, RS485, and EtherCAT for all MyActuator motor series. The Protocol Abstraction Layer (PAL) provides a consistent interface regardless of the underlying transport.

### 1.1 Supported Protocols

| Protocol | Profile | Default Configuration |
|----------|---------|----------------------|
| CAN bus | ISO 11898-1 | 500kbps, 29-bit extended IDs |
| RS485 | Modbus RTU | 115200 baud, 8N1 |
| EtherCAT | CoE (CANopen over EtherCAT) | 1ms cycle time, DC sync |

### 1.2 Protocol Auto-Detection

The system supports automatic protocol detection and fallback:

1. **Boot Sequence:** Try CAN → RS485 → EtherCAT
2. **Heartbeat Monitoring:** Each protocol has a heartbeat mechanism
3. **Fallback Trigger:** If heartbeat fails for 3 consecutive cycles, switch to next protocol
4. **Manual Override:** Build flag `-DPROTOCOL_CAN` (or RS485/ETHERCAT) forces specific protocol

---

## 2. Protocol Abstraction Layer (PAL)

### 2.1 Unified Interface

```cpp
class IProtocol {
public:
    virtual ~IProtocol() = default;
    
    // Connection management
    virtual bool connect() = 0;
    virtual void disconnect() = 0;
    virtual bool isConnected() const = 0;
    
    // Data transfer
    virtual bool send(const Frame& frame) = 0;
    virtual bool receive(Frame& frame, uint32_t timeout_ms = 100) = 0;
    
    // Status
    virtual ProtocolType getType() const = 0;
    virtual uint32_t getLastError() const = 0;
    virtual uint32_t getRetryCount() const = 0;
};
```

### 2.2 Protocol Implementations

- `CanProtocol` - CAN bus implementation
- `ModbusProtocol` - RS485/Modbus RTU implementation
- `EthercatProtocol` - EtherCAT implementation

---

## 3. Message Frame Format

### 3.1 Unified Frame Structure (64 bytes)

```
┌─────────────────────────────────────────────────────────────────┐
│ Header (8 bytes)                                                │
├─────────────────────────────────────────────────────────────────┤
│ Motor ID (1 byte)                                               │
├─────────────────────────────────────────────────────────────────┤
│ Command Type (1 byte)                                           │
├─────────────────────────────────────────────────────────────────┤
│ Sequence Number (1 byte)                                        │
├─────────────────────────────────────────────────────────────────┤
│ Payload (32 bytes)                                              │
├─────────────────────────────────────────────────────────────────┤
│ CRC-16/CCITT Checksum (2 bytes)                                 │
├─────────────────────────────────────────────────────────────────┤
│ Padding (19 bytes)                                              │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Header Structure

| Field | Size | Description |
|-------|------|-------------|
| Sync Word | 2 bytes | `0xAA55` (little-endian) |
| Frame Type | 1 byte | See Frame Type Enum |
| Sequence Number | 1 byte | 0-255, wraps around |
| Reserved | 4 bytes | Zero-filled |

### 3.3 Frame Type Enum

```cpp
enum class FrameType : uint8_t {
    STATUS_REPORT      = 0x01,  // Motor status feedback
    POSITION_CMD       = 0x02,  // Position control command
    VELOCITY_CMD       = 0x03,  // Velocity control command
    TORQUE_CMD         = 0x04,  // Torque control command
    PARAM_READ         = 0x05,  // Parameter read request
    PARAM_WRITE        = 0x06,  // Parameter write request
    DIAGNOSTIC         = 0x07,  // Diagnostic request
    FIRMWARE_UPDATE    = 0x08,  // Firmware update command
    HEARTBEAT          = 0x09,  // Heartbeat signal
    RESERVED           = 0x0A-0xFF
};
```

### 3.4 Payload Structure (Command-Specific)

#### 3.4.1 STATUS_REPORT Payload

```
┌─────────────────────────────────────────────────────────────────┐
│ Position (4 bytes, int32_t)                                     │
├─────────────────────────────────────────────────────────────────┤
│ Velocity (4 bytes, int32_t)                                     │
├─────────────────────────────────────────────────────────────────┤
│ Torque (2 bytes, int16_t)                                       │
├─────────────────────────────────────────────────────────────────┤
│ Temperature (1 byte, uint8_t, °C)                               │
├─────────────────────────────────────────────────────────────────┤
│ Status Word (2 bytes, uint16_t)                                 │
├─────────────────────────────────────────────────────────────────┤
│ Fault Code (1 byte, uint8_t)                                    │
├─────────────────────────────────────────────────────────────────┤
│ Reserved (18 bytes)                                             │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.4.2 POSITION_CMD Payload

```
┌─────────────────────────────────────────────────────────────────┐
│ Target Position (4 bytes, int32_t)                              │
├─────────────────────────────────────────────────────────────────┤
│ Velocity Limit (4 bytes, int32_t)                               │
├─────────────────────────────────────────────────────────────────┤
│ Acceleration (4 bytes, int32_t)                                 │
├─────────────────────────────────────────────────────────────────┤
│ Profile Type (1 byte, uint8_t: 0=trapezoidal, 1=s-curve)       │
├─────────────────────────────────────────────────────────────────┤
│ Reserved (17 bytes)                                             │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.4.3 PARAM_READ/WRITE Payload

```
┌─────────────────────────────────────────────────────────────────┐
│ Parameter Address (2 bytes, uint16_t)                           │
├─────────────────────────────────────────────────────────────────┤
│ Parameter Value (4 bytes, uint32_t)                             │
├─────────────────────────────────────────────────────────────────┤
│ Reserved (26 bytes)                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. CAN Bus Protocol Specification

### 4.1 CAN ID Assignment

| Direction | CAN ID Formula | Example (Motor ID=5) |
|-----------|----------------|---------------------|
| Master → Motor (Commands) | `0x600 + (motor_id << 4)` | `0x650` |
| Motor → Master (Status) | `0x180 + (motor_id << 4)` | `0x1D0` |
| Broadcast | `0x7FF` | `0x7FF` |

### 4.2 PDO Mapping (Process Data Objects)

**TPDO1 (Transmit PDO - Motor → Master):**
- Bit 0-31: Position (32-bit)
- Bit 32-63: Velocity (32-bit)
- Bit 64-79: Torque (16-bit)
- Bit 80-87: Temperature (8-bit)
- Bit 88-103: Status Word (16-bit)
- Bit 104-111: Fault Code (8-bit)

**RPDO1 (Receive PDO - Master → Motor):**
- Bit 0-31: Target Position (32-bit)
- Bit 32-63: Velocity Limit (32-bit)
- Bit 64-95: Acceleration (32-bit)
- Bit 96-103: Profile Type (8-bit)

### 4.3 SDO (Service Data Objects)

- **Read SDO:** `0x600 + (motor_id << 4) + 0x0A`
- **Write SDO:** `0x600 + (motor_id << 4) + 0x0B`
- **Response SDO:** `0x580 + (motor_id << 4)`

### 4.4 NMT (Network Management)

| NMT Command | CAN ID | Data |
|-------------|--------|------|
| Start Remote Node | `0x000` | `0x01, motor_id` |
| Stop Remote Node | `0x000` | `0x02, motor_id` |
| Enter Pre-Operational | `0x000` | `0x80` |
| Reset Node | `0x000` | `0x81, motor_id` |
| Reset Communication | `0x000` | `0x82` |

### 4.5 Heartbeat Consumer

- **Period:** 100ms (configurable)
- **CAN ID:** `0x700 + (motor_id << 4)`
- **Data:** `0x00` (heartbeat indicator)
- **Timeout:** 300ms (3 missed heartbeats = fault)

### 4.6 Error Handling

- **Bus-Off Recovery:** Automatic reset after 128 occurrences
- **Retry Strategy:** Exponential backoff (10ms, 20ms, 40ms, ..., max 1000ms)
- **Max Retries:** 10 before reporting error

---

## 5. RS485 Protocol Specification

### 5.1 Modbus RTU Configuration

- **Baud Rate:** 115200
- **Data Bits:** 8
- **Parity:** None
- **Stop Bits:** 1
- **Timeout:** 100ms

### 5.2 Register Map

| Register Address | Description | Access | Size |
|-----------------|-------------|--------|------|
| 0x0000 | Status Word | Read | 16-bit |
| 0x0001 | Fault Code | Read | 16-bit |
| 0x0002 | Position Actual | Read | 32-bit |
| 0x0003 | Velocity Actual | Read | 32-bit |
| 0x0004 | Torque Actual | Read | 16-bit |
| 0x0005 | Temperature | Read | 16-bit |
| 0x0100 | Position Command | Read/Write | 32-bit |
| 0x0101 | Velocity Command | Read/Write | 32-bit |
| 0x0102 | Torque Command | Read/Write | 16-bit |
| 0x0200 | PID P-Gain | Read/Write | 32-bit |
| 0x0201 | PID I-Gain | Read/Write | 32-bit |
| 0x0202 | PID D-Gain | Read/Write | 32-bit |
| 0x0300 | Velocity Limit | Read/Write | 32-bit |
| 0x0301 | Acceleration Limit | Read/Write | 32-bit |
| 0x0302 | Deceleration Limit | Read/Write | 32-bit |

### 5.3 Function Codes

| Function Code | Description |
|--------------|-------------|
| 0x03 | Read Holding Registers |
| 0x06 | Write Single Register |
| 0x10 | Write Multiple Registers |
| 0x0B | Read Exception Status |

### 5.4 Broadcast Mode

- **Address:** 0x00
- **Use Case:** Firmware updates, mass parameter configuration
- **Response:** None (fire-and-forget)

---

## 6. EtherCAT Protocol Specification

### 6.1 CoE (CANopen over EtherCAT)

- **Object Dictionary:** Standard CANopen object dictionary
- **SDO Communication:** Block SDO for large transfers
- **PDO Mapping:** Dynamic PDO assignment

### 6.2 PDO Assignment

**TPDO1 Mapping:**
- 0x6041: Position Actual Value
- 0x6064: Velocity Actual Value
- 0x6077: Torque Actual Value
- 0x603F: Temperature
- 0x6042: Status Word

**RPDO1 Mapping:**
- 0x607A: Target Position
- 0x60FF: Target Velocity
- 0x6078: Target Torque
- 0x60C1: Profile Type

### 6.3 DC (Distributed Clocks)

- **Sync Mode:** SYNC0
- **Cycle Time:** 1ms (configurable, 0.5ms-10ms)
- **Shift Time:** 0μs (aligned to SYNC0)
- **Clock Drift Compensation:** Enabled

### 6.4 State Machine

```
INIT → PREOP → SAFEOP → OP
  ↓       ↓       ↓
 INIT    INIT    INIT
```

- **INIT:** Hardware initialization
- **PREOP:** Parameter configuration
- **SAFEOP:** Safe operation (limited output)
- **OP:** Full operation

---

## 7. Motor ID Management

### 7.1 Auto-Discovery

1. **CAN Bus Scan:** Send heartbeat request to all addresses (0x00-0xFF)
2. **Response Collection:** Collect motor IDs that respond
3. **Registration:** Add discovered motors to motor registry

### 7.2 Static Configuration

- **Storage:** ESP32 NVS (Non-Volatile Storage)
- **Format:** JSON
- **Fields:** Motor ID, Protocol, Baud Rate, CAN ID

### 7.3 Dynamic Assignment

- **Master Controller:** Assigns motor IDs via configuration command
- **Conflict Resolution:** Last-writer-wins with arbitration

---

## 8. Error Handling & Diagnostics

### 8.1 Fault Code Definitions

| Fault Code | Name | Description | Recovery |
|------------|------|-------------|----------|
| 0x00 | None | No fault | - |
| 0x01 | Overtemperature | Motor temperature > 120°C | Cool down, reset |
| 0x02 | Overcurrent | Current > 2x rated | Reduce load, reset |
| 0x03 | Overvoltage | DC bus > 80V | Check power supply |
| 0x04 | Undervoltage | DC bus < 18V | Check power supply |
| 0x05 | Encoder Fault | Encoder communication error | Check wiring, reset |
| 0x06 | Communication Timeout | No response from motor | Check connection, reset |
| 0x07 | Position Error | Position error > limit | Check mechanics, reset |
| 0x08 | Internal Error | Firmware/internal error | Reset, update firmware |

### 8.2 Error Recovery Procedures

1. **Automatic Recovery:**
   - Communication timeout: Retry 3 times, then alert
   - Overcurrent: Reduce current limit by 50%, retry
   - Overtemperature: Reduce load by 50%, monitor

2. **Manual Recovery:**
   - Clear fault register via command
   - Reset motor controller
   - Power cycle (last resort)

### 8.3 Diagnostic Logging

- **Buffer Size:** 256 entries (ring buffer)
- **Entry Format:** Timestamp, Fault Code, Motor ID, Context Data
- **Storage:** Flash (persistent across reboots)
- **Access:** Via diagnostic command or serial debug

---

## 9. PlatformIO Integration

### 9.1 platformio.ini

```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
build_flags = 
    -DPROTOCOL_CAN
    -DMOTOR_RMD_X
    -DBOARD_REV=1
lib_deps = 
    can@^1.0.0
    ModbusMaster@^0.5.0
    ECAT@^1.0.0
build_unflags = -Os
build_flags = -O2
monitor_speed = 115200

[env:esp32s3dev]
platform = espressif32
board = esp32s3dev
framework = arduino
build_flags = 
    -DPROTOCOL_CAN
    -DMOTOR_RMD_X
    -DBOARD_REV=2
lib_deps = 
    can@^1.0.0
    ModbusMaster@^0.5.0
    ECAT@^1.0.0
build_unflags = -Os
build_flags = -O2
monitor_speed = 115200
```

### 9.2 Build Flags

| Flag | Description | Values |
|------|-------------|--------|
| `-DPROTOCOL_CAN` | Enable CAN bus protocol | CAN, RS485, ETHERCAT |
| `-DMOTOR_RMD_X` | Enable RMD-X motor support | RMD_X, RH, CEM, RMD_H, RMD_L, FL_FLO |
| `-DBOARD_REV` | Board revision | 1 (DevKitC), 2 (ESP32-S3) |
| `-DDEBUG_LEVEL` | Debug verbosity | 0 (none), 1 (error), 2 (warn), 3 (info), 4 (debug) |

### 9.3 Memory Optimization Targets

- **Flash Usage:** < 512KB
- **RAM Usage:** < 50KB static, < 20KB stack per task
- **NVS Usage:** < 64KB

---

## 10. References

- **Motor Series Contracts:** See individual motor contracts (MOTOR_RMD_X_CONTRACT.md, etc.)
- **ESP32 Firmware Contract:** See ESP32_FIRMWARE_CONTRACT.md
- **Simulation Contract:** See SIMULATION_CONTRACT.md

---

## 11. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-07-03 | Omnius | Initial draft |
