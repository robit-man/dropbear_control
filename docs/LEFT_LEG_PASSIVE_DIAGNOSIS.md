# Left leg passive serial diagnosis

Observed on the AGX host on 2026-09-14. No serial or CAN bytes were
transmitted during these checks.

## Result

The left USB/UART device enumerates and the host reader opens it successfully,
but the ESP32 produces no serial bytes. The failure is upstream of the browser
CSV parser and default-stance calibration.

| Check | Left | Right reference |
|---|---|---|
| Stable USB path | hub port `1.4` | hub port `1.2` |
| Linux tty | `/dev/ttyUSB2` | `/dev/ttyUSB1` |
| USB bridge | Silicon Labs CP2102, `10c4:ea60`, `cp210x`, 12 Mbps | same |
| Passive file descriptor | open read-only | open read-only |
| Reader state | `observing` | `observing` |
| Read errors / overflows | `0 / 0` | `0 / 0` |
| Decoded frames after restart | `0` | continuously increasing |

Both CP2102 boards report the same factory serial `0001`, so `/dev/serial/by-id`
is ambiguous. The service uses the stable physical `by-path` names and is not
depending on that duplicate ID.

## Firmware gates that explain a silent open UART

The deployed source begins serial at 115200, loads SPIFFS configuration, starts
the MCP2515, enables `playMode`, and only then creates the sensor task. That
task publishes its five degree values only while `playMode && !isCenter`.

The source has three paths consistent with the passive evidence:

1. No saved config: `promptLegSide()` waits for serial input before the CAN
   setup and tasks are reached.
2. Saved `center` chirality: tasks run, but the sensor CSV branch is suppressed.
3. MCP2515 initialization failure: setup prints one failure line and enters a
   permanent loop before tasks are created. A reader attached after boot would
   see the same ongoing silence.

The current byte-silent constraint prevents a `chirality` query from separating
these cases. A future supported bench check should capture power-on serial from
the first byte and compare it with MCP2515 electrical status before any command
transport is enabled.
