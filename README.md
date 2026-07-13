# MyActuator — ESP32 Motor Controller + Host Tooling

Unified control stack for MyActuator servo drives (RMD-X, RH, CEM, RMD-H,
RMD-L, FL) built around an ESP32 firmware and a host-side Python library.
Wire-protocol details are pinned in `contracts/` and are the source of truth
for command/response framing.

## Repository layout

| Path | What it is |
|------|------------|
| `firmware/esp32/` | ESP32 Arduino/PlatformIO firmware: Protocol Abstraction Layer (PAL), per-motor drivers, and CAN / RS485 / EtherCAT transports |
| `host/myactuator_lib/` | Python library (transport / device / protocol / ROS bridge) with a self-test harness |
| `contracts/` | Source-of-truth protocol specs and per-motor command/response contracts |
| `web/` | **Planned** — WebSerial + Three.js motor configurator / test frontend (next milestone, not yet implemented) |

## Current status

- **Firmware** — builds clean for the `esp32` target (RAM 6.6%, Flash 22.0%).
  Additional environments `esp32s3`, `esp32c3`, `esp32s3dev` are configured in
  `platformio.ini`.
- **Host library** — self-test passes (`HOSTLIB_OK` from
  `host/myactuator_lib/_verify.py`).
- **Web frontend** — not yet implemented; scoped as the next feature set
  (WebSerial connection to the ESP32, motor configuration/test UI, and Three.js
  visualization of motors using STEP models from the MyActuator site).

## Quick start

### Firmware (PlatformIO)

```bash
cd firmware/esp32
pio run -e esp32            # build
pio run -e esp32 -t upload  # flash
pio device monitor -b 115200
```

Select motor series / protocol / encoder resolution via the `build_flags` in
`platformio.ini` (see `firmware/esp32/README.md` for details).

### Host library

```bash
cd host
PYTHONPATH=. python3 myactuator_lib/_verify.py   # expect: HOSTLIB_OK
```

The library exposes layered `transport`, `device`, `protocol`, and `ros`
packages; see `host/myactuator_lib/__init__.py` for the public surface.

## Documentation

- `firmware/esp32/README.md` — firmware build, configuration, and PAL API
- `contracts/PROTOCOLS_CONTRACT.md` — wire-protocol specification
- `contracts/MOTOR_*.md` — per-motor series contracts

## License

Proprietary — MyActuator.
