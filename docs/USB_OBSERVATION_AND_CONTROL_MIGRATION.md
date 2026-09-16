# USB observation and actuator-control migration

Status: passive observation is implemented; physical command transport is
locked and not installed.

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
external absolute sensors
  -> deployed leg ESP32 CSV
  -> O_RDONLY USB readers
  -> strict side-specific decoder
  -> freshness and provenance
  -> browser Dropbear USD state
```

There is no serial write call, command encoder, CAN adapter, or physical
hardware backend on this path.

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

Open <http://localhost:8000/?live=1>. The query parameter explicitly selects
the receive-only hardware state as soon as at least one fresh leg stream is
available. Without it, click **USE LIVE STATE**. A missing or stale side stays
visibly unobserved; it is never filled with simulated data while live state is
selected.

On remote AGX desktop sessions where Chrome cannot create a WebGL2 context,
the same URL automatically uses the Canvas 2D measured-state viewer. This
keeps telemetry, per-joint availability, and control-lock state visible without
claiming that the simplified stick view is the USD renderer.

The paths are USB-topology identities. All three installed CP2102 bridges
currently report the same serial number, `0001`, so `/dev/serial/by-id` cannot
distinguish them. Passive payload classification identifies `/dev/ttyUSB0`
(path `1.1`) and `/dev/ttyUSB1` (path `1.2`) as the left and right leg streams,
respectively. `/dev/ttyUSB2` (path `1.4`) is reserved for the neck controller.
The leg classification is based on the unsolicited five-angle CSV contract;
no command was sent to any controller.

## Observation contract

Each leg line must contain exactly five finite decimal values in `0..360`:

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

Left hip yaw `0x149` and right hip yaw `0x14C` have no value in the deployed
five-field stream. They remain unavailable in the UI.

The API publishes `mode: read_only`, `writeCapable: false`, and `txBytes: 0`.
The reader opens each character device with `O_RDONLY | O_NOCTTY | O_NONBLOCK`,
has no write method, performs no reconnect loop, and drops malformed, stale,
oversized, or partial records.

Opening a USB UART can still change modem-control lines inside a driver and can
reset some ESP32 boards. The opt-in environment flag exists for that reason.
The deployed source also enables its actuator loop on boot, so a passive host
reader alone cannot prove that the controller or powered robot is inert.

## First attached-hardware observation

Observed on the AGX Xavier on 2026-09-15, without sending serial bytes:

| Link | Result |
|---|---|
| Right leg, USB path `1.2` | Fresh five-field degree records; no decoder/read errors after admission |
| Left leg, USB path `1.1` | Fresh five-field degree records; example `166,92,20,193,147`; no decoder/read errors after admission |
| Neck candidate, USB path `1.4` | Silent during passive observation, consistent with the neck's request/response `HEALTH` protocol; left unopened by the corrected leg service |

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
copies an external sensor value into a motor field. A versioned `DB2` parser is
ready for five external angles plus six independently measured motor-native
angles; legacy five-field records remain supported.

## Browser software zero and angle recording

**ZERO MODEL FROM CURRENT POSE** accepts one fresh snapshot from both leg
controllers and the entered torso-forward angle, currently `7°`. This action
writes no serial or CAN bytes and does not invoke the ESP32 calibration
command. The browser stores the external readings as local datums and renders
subsequent motion from the shortest wrapped degree delta. The captured pose
continues to use the corrected USD default-stance joint coordinates, while the
displayed sensor delta is `0°` at capture. The datum and torso angle persist in
browser local storage.

The angle recorder exports one CSV row per side and joint for each admitted
sample. It keeps external raw angle, external zeroed delta, upstream model
joint angle, motor-native angle, and motor-native zeroed delta in separate
columns with CAN ID and availability. Hip yaw therefore has an empty external
column, and all motor columns remain empty with an explicit status on today's
deployed firmware. Recording stops at 120,000 rows to bound browser memory.

## ESP32 console and firmware toolchain

The ESP32 Devices view inventories stable `/dev/serial/by-path` identities,
shows the bounded raw receive tail, and permits only the diagnostic serial
queries `status`, `chirality`, `mac`, `saved`, and `help`. Compile and upload
are separate stages. Upload requires the exact build and source checksum from
the current server session, a selected stable device, three physical-safety
acknowledgements, and the typed phrase `FLASH <ROLE>`.

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
