# USB observation and actuator-control migration

Status: live observation and bounded diagnostic queries are implemented;
physical command transport is locked and not installed.

This document joins four source trees into one migration path:

- `Hyperspawn/Dropbear/Control System/Low Level Control` supplies the deployed
  two-ESP32 leg behavior;
- `robit-man/dropbear_control` owns the robot model, canonical joint names,
  observation boundary, admission gates, and eventual robot-level controller;
- `robit-man/Dropbear-Neck-Assembly/teleoperation` is a future source of remote
  operator intent; and
- `robit-man/dropbear-foot` is a future source of four load-cell measurements
  per foot.

The current milestone moves measurements in one direction only:

```text
external absolute sensors + RMD motor encoders
  -> non-motion CAN 0x92 queries
  -> deployed leg ESP32 DB3
  -> O_RDONLY USB readers
  -> strict side-specific decoder
  -> freshness and provenance
  -> browser Dropbear USD state
```

An isolated side channel can transmit only `version`, `health`, passive status,
and `observe on|off`. Behemoth requests receive the exact saved-role DB1
header. The allowlist cannot encode motion, and no physical command backend is
installed.

## Run the live observation dashboard

Install the pinned browser dependencies once:

```bash
cd web
npm ci
cd ..
```

On the current AGX Xavier USB topology, run:

The side assignment below follows a physical single-leg movement check made
on 2026-09-15. The deployed legacy builds do not emit a firmware identity and
did not answer the passive `chirality` diagnostic while streaming.

```bash
DROPBEAR_OBSERVATION_ENABLE=1 \
DROPBEAR_OBSERVATION_LEFT=/dev/serial/by-path/platform-141a0000.pcie-pci-0005:01:00.0-usb-0:1.2:1.0-port0 \
DROPBEAR_OBSERVATION_RIGHT=/dev/serial/by-path/platform-141a0000.pcie-pci-0005:01:00.0-usb-0:1.1:1.0-port0 \
DROPBEAR_OBSERVATION_MAX_AGE_MS=500 \
python3 web/serve.py 8000
```

Open <http://localhost:8000/?live=1&renderer=swiftshader&asset=lite>. The live
query requests observation
from both controllers, waits for fresh telemetry, and selects the measured
hardware state. Without it, click **USE LIVE STATE**. A missing or stale side stays
visibly unobserved; it is never filled with simulated data while live state is
selected.

The explicit SwiftShader renderer keeps the articulated 3D USD visible on the
current remote AGX desktop, where the sandboxed browser cannot bind the Xavier
GPU context. The light cache retains the 93-body kinematic graph and 27 loop
closures while reducing the rendered mesh to 64,216 triangles. The dashboard
keeps full viewport resolution; its software-renderer optimization avoids
re-solving unchanged articulated poses instead of pixelating the output.

The paths are USB-topology identities. All three installed CP2102 bridges
currently report the same serial number, `0001`, so `/dev/serial/by-id` cannot
distinguish them. The flashed DBV1 role records identify USB path `1.2` as
`LEFTLEG` and path `1.1` as `RIGHTLEG`. USB path `1.4` is reserved for the neck
controller and is not admitted as a leg.

## Observation contract

Legacy lines contain exactly five finite decimal values in `0..360`:

```text
outer_calf,inner_calf,hip_pitch,knee,hip_roll
```

| Side | Observation | CAN ID | USD joint | ESP32 input |
|---|---|---:|---|---:|
| Left | outer calf | `0x141` | `LL_Revolute81` | GPIO 14 |
| Left | inner calf | `0x142` | `LL_Revolute67` | GPIO 27 |
| Left | hip pitch | `0x146` | `LL_hip_joint` | GPIO 26 |
| Left | knee | `0x145` | `LL_knee_actuator_joint` | GPIO 25 |
| Left | hip roll | `0x14A` | `PG_left_leg_pitch` | GPIO 33 |
| Right | outer calf | `0x144` | `RL_Revolute81` | GPIO 14 |
| Right | inner calf | `0x143` | `RL_Revolute67` | GPIO 27 |
| Right | hip pitch | `0x147` | `RL_hip_joint` | GPIO 26 |
| Right | knee | `0x148` | `RL_knee_actuator_joint` | GPIO 25 |
| Right | hip roll | `0x14B` | `PG_right_leg_pitch` | GPIO 33 |

Each AS5600 is a single-turn `0..360°` sensor attached 1:1 to its actuator
output shaft. In particular, the knee field drives the upstream
`*_knee_actuator_joint` without a multiplier. The corrected closed-loop USD
linkage produces the larger downstream knee bend as a kinematic consequence.

`DB2` adds controller milliseconds and six raw RMD multi-turn angles. `DB3`
adds six restart-aligned RMD control angles plus six-bit raw-fresh,
control-ready, and alignment-fault masks. Five aligned fields use AS5600 at
restart and then run continuously from CAN. Hip yaw has no AS5600 and uses the
first verified RMD response as its boot-relative zero.

The installed calf drives use the older V1.7 `0x92` response: a signed 56-bit
little-endian angle occupies bytes 1–7. The X10 drives use the newer signed
32-bit response in bytes 4–7. Treating every response as the newer layout made
valid X8 replies increment the malformed-response counter. Firmware version
`2026.09.18` decodes the layout by the known actuator ID.

The API publishes `mode: read_only_with_diagnostic_queries`,
`writeCapable: false`, and `motionWriteCapable: false`.
The reader opens each character device with `O_RDONLY | O_NOCTTY | O_NONBLOCK`,
reconnects after USB changes, and drops malformed, stale, oversized, or partial
records. Diagnostic writes use a new short-lived descriptor, are byte-counted,
and accept no motion tokens.

Opening a USB UART can still change modem-control lines inside a driver and can
reset some ESP32 boards. The opt-in environment flag exists for that reason.
The deployed source also enables its actuator loop on boot, so a passive host
reader alone cannot prove that the controller or powered robot is inert.

## Attached-hardware observations

The first passive capture on 2026-09-15 established the five-field stream. On
2026-09-17, Behemoth
`behemoth-observation-protocol-2026.09.17` was compiled once and uploaded to
both leg ESP32s with `EraseFlash=none`; the installed SPIFFS region was checked
at `0x290000 + 0x160000` before each upload and both on-device application
hashes were verified afterward.

| Link | Result |
|---|---|
| Left leg, USB path `1.2` | DB3 fresh; CAN `0x146` and `0x14A` reply to RMD `0x92`; DBH1 AS5600 mask `10010` |
| Right leg, USB path `1.1` | DB3 fresh; CAN `0x147`, `0x148`, `0x14B`, and `0x14C` reply; DBH1 AS5600 mask `00010` |
| Neck candidate, USB path `1.4` | Silent during passive observation, consistent with the neck's request/response `HEALTH` protocol; left unopened by the corrected leg service |

A 200-frame sample after the operator repaired the broken right-foot CAN line
found left reply masks
`0b100100` and right reply masks covering `0b111100`. Both ESP32/MCP2515 paths
are therefore alive. All four legacy RMD-X8 Pro calf IDs (`0x141`–`0x144`)
were rejected by the then-installed newer-format-only decoder. Left `0x145`
and `0x149` were also absent, so the left leg still has an additional per-motor
or partial-chain fault independent of the X8 decode issue.
The right DBH1 counters retain the earlier transmit failures, but its current
consecutive-failure counter returned to zero after replies resumed.

The dashboard admits both leg streams. Physical default-stance captures map
their measured degrees into the corrected USD coordinates. Joint signs remain
provisional until controlled read-only motion correlation. Left inner calf and
right knee are explicitly marked unstable because their stationary readings
were multimodal; both remain raw-only in the model. These records do not
validate motor-native feedback.

The deployed values are normalized readings from five external analog absolute
sensors. They are not native RMD motor position responses. Firmware maps a
12-bit ADC range to degrees, averages ten readings, applies a stored side
offset, and emits integer-valued positions without a controller timestamp.
Validate every sensor against a physical reference before treating it as a
calibrated joint state.

Every API side also exposes six `motorJoints` entries with CAN IDs. With the
deployed five-field firmware, their positions are `null`, availability is
false, and status is `not_emitted_by_deployed_firmware`. The service never
copies an external sensor value into a motor field. A versioned `DB2` parser
accepts five external angles plus six independently measured motor-native
angles. `DB3` additionally drives the USD from six firmware-aligned CAN
positions; legacy five-field records remain supported.

## Browser software zero and angle recording

**ZERO MODEL FROM CURRENT POSE** accepts one fresh, motion-locked snapshot from
both leg controllers. Degraded individual channels no longer block the entire
capture: available CAN and AS5600 datums are recorded independently, while
unavailable joints remain visibly held. The entered torso-forward angle
defaults to `7°`. This action
writes no serial or CAN bytes and does not invoke the ESP32 calibration
command. The browser stores the external readings as local datums and renders
subsequent motion from the shortest wrapped degree delta. The captured pose
continues to use the corrected USD default-stance joint coordinates, while the
displayed sensor delta is `0°` at capture. The datum and torso angle persist in
browser local storage.

**LIVE ANGLE SOURCE** selects `Auto · CAN then AS5600`, `Motor CAN only`, or
`AS5600 only`. This affects only browser projection. It does not change ESP32
calibration or actuator commands, and a missing/stale channel remains held.

The angle recorder exports one CSV row per side and joint for each admitted
sample. It keeps external raw angle, external zeroed delta, upstream model
joint angle, raw motor angle, raw motor zeroed delta, aligned motor angle,
aligned model angle, and alignment fault in separate
columns with CAN ID and availability. Cached AS5600 numbers are recorded as
`firmware_marked_stale` but are excluded from zeroed/model columns. Hip yaw has
an empty external column. Recording stops at 120,000 rows to bound browser
memory.

The browser also rejects a fresh-but-implausible source transition above
`720°/s` from model application. This catches disconnected/noisy PWM channels
whose numeric values continue to change even while a packet stream is fresh;
the raw value remains visible and recordable for diagnosis.

## ESP32 console and firmware toolchain

The ESP32 Devices view inventories stable `/dev/serial/by-path` identities,
shows the bounded raw receive tail, and permits only version, capability,
health, observation, and passive status diagnostics. The host learns DB1 versus
legacy framing from `DBV1` and supplies exact limb headers. Compile and upload
are separate stages. Upload requires the exact build and source checksum from
the current server session, a selected stable device, three physical-safety
acknowledgements, and the typed phrase `FLASH <ROLE>`.

Upload does not run a second Arduino compile. After the target partition table
proves the expected SPIFFS location, the service hashes the session's compiled
binary again and writes only the factory application region at `0x10000`.
This shortens the interval between releasing the serial reader and opening the
bootloader while leaving the SPIFFS settings bytes untouched.

The local Arduino 1.8.19 toolchain targets the generic 4 MB ESP32 with the
`huge_app` partition (`esp32:esp32:esp32:PartitionScheme=huge_app`). Behemoth
uses about 1.75 MB and does not fit the default 1.31 MB application slot; this
layout trades OTA slots for a 3 MB application slot. The toolchain pins the
ESP32 Arduino core to 2.0.13 and the ignored sketchbook libraries to
MCP_CAN_lib 1.5.1 and FastAccelStepper 0.30.15. This is the last known pairing
verified against the exact Behemoth sketch on this AGX. Newer
FastAccelStepper releases require ESP-IDF 5.3, while FastAccelStepper 0.30.15
uses register APIs removed from ESP32 Arduino 3.x. The device API reports the
installed core and library versions and blocks compilation unless the exact
verified set is active.

## Frontend control lock

The frontend contains a deliberately inert command channel so the complete
interaction can be reviewed before a transport exists. It requires three
ordered server-verified actions:

1. begin the local safety review;
2. acknowledge support, clear workspace, independent emergency power removal,
   completed read-only validation, and reviewed signs/zeroes/limits; and
3. confirm a 60-second frontend lease.

Challenges expire after 120 seconds. Missing acknowledgements, mismatched
challenges, expiry, and out-of-order actions reset the sequence. The lease is
kept only in browser memory. Even with a valid lease, `/api/hardware/command`
returns HTTP 423 and `PHYSICAL_TRANSPORT_LOCKED`; `hardwareOutputEnabled`
remains false. This three-click interaction is an operator-admission layer,
not a physical safety function.

## Recommended control ownership

Keep each ESP32 responsible for one six-actuator leg bus and hard real-time
local duties. Make `dropbear_control` the only robot-level command owner.

```text
teleoperation / autonomy / ROS 2
  -> canonical desired robot state
  -> estimator and whole-body limits
  -> expiring safety lease and mode arbitration
  -> one typed gateway
  -> left-leg scheduler + right-leg scheduler
  -> exact CAN routes
```

The neck teleoperation services should publish typed operator intent or a
bounded target pose. They should never receive a serial device, CAN frame, raw
current value, or motor-driver object. Local, remote, scripted, ROS, and learned
controllers must all pass through the same arbitration and final safety gate.

### Phase 1: make deployed behavior observable and fail-safe

- boot with actuation disabled while continuing to publish sensor telemetry;
- replace index-based stop frames with the twelve actual actuator CAN IDs;
- clear every torque and impedance setpoint on stop, reset, parser failure, and
  lease loss;
- add controller identity, chirality, boot ID, sequence, monotonic timestamp,
  units, calibration generation, validity flags, and CRC to telemetry;
- separate machine telemetry from human-readable logs;
- expose native motor feedback beside external sensor feedback; and
- require a bounded command heartbeat plus an independent hardware power cut.

### Phase 2: validate observation

- capture both ESP32 streams at rest and through hand-supported motion;
- compare every external sensor with motor-native position and a physical angle
  reference at multiple points;
- establish wrap behavior, direction, zero, hysteresis, noise, dropout rate,
  latency, and maximum age;
- validate leg linkage transforms into USD coordinates; and
- retain calibration and test evidence by robot/controller/sensor identity.

### Phase 3: isolated command HIL

- connect the typed gateway to a CAN analyzer or emulator with no motor present;
- verify ID, opcode, units, saturation, sequence, deadline, bus-off behavior,
  watchdog behavior, and stop latency;
- allow one unloaded and current-limited actuator only after HIL evidence passes;
  and
- expand to one supported leg, then two supported legs, under explicit release
  criteria.

### Phase 4: robot control

- use timestamped measured state in the estimator;
- run position/velocity/effort loops at defined rates with one owner per axis;
- enforce mechanical limits, current limits, slew limits, thermal limits,
  plausibility checks, stale-state holds, and latched faults below the UI; and
- require independent power removal for release and emergency stop.

## Foot-force integration

`dropbear-foot` defines four HX711 channels per ESP32 with a shared GPIO 4
clock and data on GPIO 32, 12, 13, and 15. Its present firmware emits four CSV
values nominally at 80 Hz. It is not wired into the observation API yet.

Before admission, define and verify:

- which physical pad maps to each channel on each foot;
- output units and sign (the existing README/UI alternate between weight and
  pressure terminology);
- calibration mass, calibration generation, tare policy, drift, saturation,
  temperature sensitivity, and sensor capacity;
- per-sample controller identity, side, sequence, timestamp, validity, and CRC;
- contact thresholds with hysteresis and stale-data behavior; and
- force distribution outputs: total normal force, heel/toe and medial/lateral
  split, and center of pressure in the foot frame.

After that evidence exists, add the force samples as a separate typed source.
Do not splice them into the five-angle CSV or infer missing leg angles from
pressure.
