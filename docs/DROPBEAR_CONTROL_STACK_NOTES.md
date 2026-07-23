# Dropbear low-level control audit and reconciliation notes

Audited source: `Hyperspawn/Dropbear` commit
`13cf5ecaa39b8b89c794fe905dcea0490cfa7726` (2025-08-07), sparse working copy
at `references/Dropbear/Control System/Low Level Control`.

The deterministic follow-on reconciliation, exact cross-layer gaps, machine
schema and execution roadmap are in
[`DROPBEAR_LAYER_RECONCILIATION.md`](DROPBEAR_LAYER_RECONCILIATION.md) and
[`generated/dropbear_reconciliation/reconciliation.json`](../generated/dropbear_reconciliation/reconciliation.json).

## What exists

The low-level directory contains a 1,340-line ESP32 Arduino sketch, a
1,384-line Flask/HTML/JavaScript control application, and two example files.
The sketch hard-codes 12 CAN actuator IDs (`0x141` through `0x14C`), creates
FreeRTOS tasks for sensing/serial/torque/impedance behavior, and emits RMD
torque (`0xA1`) and stop (`0x81`) commands through an MCP2515. Five external
analog joint sensors are sampled per leg. The Flask application discovers two
serial devices, assigns them by reported chirality, and exposes direct torque,
configuration, constraints, impedance, and playback controls.

This is a valuable bench prototype: it proves the rough wiring topology, motor
ID convention, command byte used for torque, sensor offsets, and the intended
two-leg operator workflow. It is not yet a safe low-level controller or a
stable interface for high-level control.

## Broader Dropbear repository: substantial work, fragmented authority

The upstream tree is much farther along mechanically and visually than the
low-level folder suggests. Its Git tree contains approximately 13,328 files
under `Sim`, 1,105 under `CAD_Files`, ROS 2/Gazebo packages, detailed and
simplified URDF/xacro models, `ros2_control` descriptions, trajectory publisher
nodes, Isaac Sim USD projects, Altair models, and large native CAD assemblies.
This assessment used the sparse low-level checkout plus read-only inspection of
those source files; the multi-gigabyte LFS payload was not smudged.

The existing work should be consolidated, not discarded:

- Gazebo packages already define left/right leg, hand, waist, and joint-state
  controllers and demonstrate closed-chain work.
- detailed leg xacro already separates some RMD-X10 stator and rotor meshes and
  includes CAD-derived mass/inertia values. This is a useful candidate for
  validating the new official CAD segmentation—not yet trusted provenance.
- detailed and simplified robot descriptions provide a strong starting point
  for canonical Dropbear kinematics and visual assets;
- Isaac/Altair projects provide additional visual and dynamics comparisons;
- trajectory publisher scripts capture intended operator manipulation of
  simulated joint groups.

The reconciliation problem is visible in these assets:

- the same URDF/xacro content appears in `CAD_Files`, multiple `Sim/Gazebo`
  projects, and committed `build/`/`install/` outputs, so there is no canonical
  source or generation path;
- the Gazebo controller manager runs at 10 Hz and the joint trajectory
  controllers are explicitly open-loop position controllers;
- simulated legs command five CAD-derived joints with names such as
  `RL_Revolute67`, while low-level hardware commands six semantic actuators per
  leg including hip yaw;
- the leg `ros2_control` xacro supplies position only and sets both the minimum
  and maximum of several joints to `-PI`;
- only `gazebo_ros2_control/GazeboSystem` is defined; there is no Dropbear
  physical hardware plugin or shared firmware transport;
- the ROS package is version `0.0.0` with placeholder description/license and
  no useful automated test suite;
- trajectory publishers prompt on stdin and republish fixed positions at 1 Hz;
  they are demonstrations, not a planner or feedback controller;
- autonomous and teleoperation sections are largely images/resources, while
  the checked-in RT-X/VLA experiment is a separate upstream-style ML project
  with no Dropbear observation/action adapter;
- generated ROS build/install outputs, third-party binary plugins, very large
  simulation assets, and duplicates are committed, making provenance and
  review difficult.

This is why the project can be “far along” in CAD and simulation appearance but
still lack the connective control spine needed to move safely from high-level
intent to measured actuator state.

## Immediate critical defects

| Severity | Finding | Consequence |
|---|---|---|
| Critical | `setup()` sets `playMode = true` immediately after CAN initialization | Actuation tasks start without a host lease or explicit enable handshake |
| Critical | Each non-center ESP32 transmits all 12 left and right motor IDs | Two leg controllers can contend for the same actuators; chirality does not scope bus ownership |
| Critical | `torqueControlTask` and `impedanceControlTask` both write torque every 10 ms | Two unsynchronized command owners race; the zero-filled torque array can overwrite impedance output |
| Critical | Stop loop calls `sendStopCommand(i)` for indexes 0–11 instead of CAN IDs `0x141`–`0x14C` | Software stop does not address the actuators |
| Critical | No CAN response/status path, command watchdog, fault state, or physical e-stop integration | The controller cannot prove that a command arrived, detect a drive fault, or fail safely on host loss |
| High | Raw newline-delimited serial commands have no version, framing, checksum, sequence, timestamp, acknowledgement, or privilege boundary | Commands and state cannot be reconciled reliably across layers |
| High | Flask exposes arbitrary physical commands on `0.0.0.0:5000` with a placeholder secret and no authentication | Any reachable client can potentially command the robot |
| High | Startup and configuration include blocking serial workflows | Control timing and safety behavior can stall |

## Correctness defects to preserve as regression tests

- The `impedance` parser locates only three separators for five arguments.
  Desired velocity begins inside the desired-position substring, so the command
  cannot be decoded correctly.
- Flask has a `/set_pid` route, while the firmware has no matching `pid`
  command handler.
- Flask sends constraints using generic names such as `knee`; firmware expects
  names such as `knee_left`. Unmatched names can still be presented as success.
- The config writer prefixes constraint records with a joint name, but the
  loader only accepts records beginning with `Constraints:`. Saved constraints
  are not restored by that loader.
- Direction-multiplier persistence uses a separate file-write path that can
  overwrite rather than transactionally update configuration.
- Five analog positions are available for six motors on a leg; hip yaw is not
  represented in the sampled sensor set.
- The IMU task is not created. `readIMU()` probes addresses `0x68` through
  `0x6C` without a mux and reads the 14-byte register block as six consecutive
  axes, so temperature bytes are interpreted as gyro data.
- No receive-side motor telemetry is implemented, so native encoder, current,
  temperature, voltage, error, and multi-turn state are unavailable.
- Torque values are treated as raw integers/amps without a per-model torque
  constant, output gear ratio, sign convention, or saturation proof. In the
  current official CAN V4.4 protocol, `0xA1` is specifically q-axis current in
  0.01 A/LSB—not N·m—and brake-equipped motors require a separate brake-open
  command before `0xA1`.
- The Flask joint list omits hip yaw even though the firmware sends commands to
  both hip-yaw IDs.

## Why the low and high layers do not reconcile

The current low-level interface mixes operator UI concerns, persistent
configuration, sensor calibration, joint control, motor-bus scheduling, and
safety in two monolithic files. There is no machine-readable robot/joint
registry shared by firmware, host, UI, URDF, and simulator. Consequently each
layer independently invents joint names, units, signs, IDs, limits, timing, and
command semantics.

The missing contract is not merely a serial packet. It is a stateful ownership
boundary:

- who is allowed to command each joint;
- which layer closes position/velocity/torque loops;
- how a command becomes active and expires;
- how motor state is timestamped and correlated;
- how limits and faults propagate upward;
- which configuration revision produced the state;
- how simulation and hardware expose the same observable behavior.

## Required first extraction from Dropbear

Before adding more features, turn the hard-coded knowledge into reviewed data:

```text
robot.yaml
  robot revision
  controller nodes and bus ownership
  joint canonical name / aliases
  motor model / serial / firmware / protocol version
  CAN ID / bus / chirality
  motor-to-joint sign and gear/output convention
  hard, soft, velocity, torque, current and thermal limits
  encoder source / offset / wrap behavior
  CAD asset / joint origin / axis
  calibration revision and checksum
```

Generate firmware tables, host types, UI labels, URDF/xacro fragments, and
simulator mappings from this source. Do not maintain five copies manually.

## Rewrite boundary

The existing sketch should be retained as an archived prototype and test-vector
source. The production firmware should be decomposed into:

- native MYACTUATOR protocol codec and golden vectors;
- CAN transport plus deterministic request/response scheduler;
- model parameter/limit registry;
- joint-state acquisition and sensor fusion;
- exactly one command arbiter/writer per actuator;
- safety supervisor and verified motor-off path;
- versioned host link with CRC, sequencing, timestamps, acknowledgements, and
  a command lease;
- atomic/versioned calibration store;
- structured telemetry and bounded diagnostics;
- platform-independent core tests plus ESP32 hardware adapters.

The Flask application should become a diagnostic client of the same host API
used by ROS and tests. It must not bypass arbitration or safety, and remote
physical actuation must be authenticated and disabled by default.

## Preserve these useful artifacts

- current motor IDs and physical joint labels as migration inputs, not final
  truth;
- chirality discovery concept, moved into signed node identity/configuration;
- analog joint offsets and direction multipliers as unverified calibration
  candidates;
- MCP2515 pin/clock/rate assumptions for a wiring validation checklist;
- captured operator workflows for calibration, constraints, telemetry, and
  playback;
- existing torque and stop command bytes as hypotheses to verify against the
  exact motor firmware manual and CAN captures.

No existing calibration, sign, limit, or motor-ID value should enter the new
runtime without hardware review and provenance.
