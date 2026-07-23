# Software architecture description

Baseline: P1 target, not an as-built claim. Requirements are in
[system-requirements.md](../requirements/system-requirements.md); decisions are
under [`adr/`](adr/); verification is in
[master-test-plan.md](../testing/master-test-plan.md).

## Architectural invariant

Every active command has one owner, one typed unit/coordinate convention, one
monotonic expiration, one admitted configuration, and observable disposition.
Unknown model/firmware/protocol applicability prevents enable.

## Context and trust boundaries

```text
operator / autonomy (untrusted intent)
  -> behavior and planning
  -> estimator + whole-body/joint controller
  -> ros2_control SystemInterface
  -> authenticated host gateway client
  == versioned CRC-framed host link ==
  -> ESP32 admission + safety supervisor + deterministic scheduler
  == native CAN/RS485/EtherCAT boundary ==
  -> integrated MYACTUATOR drive -> mechanics

registry + evidence store -> generated validated views at every layer
replay / protocol emulator / plant / rigid-body backend replace only below
the stable hardware interface, never the safety contract.
```

The ESP32 is the last software authority before a drive and therefore owns
local lease expiry, bus scheduling, model-aware limits and motor-off requests.
The independent physical power-removal path is outside this software assurance
boundary.

## Component model

| Component | Owns | Inputs / outputs | Forbidden coupling |
|---|---|---|---|
| `registry-compiler` | Validate `robot.yaml`; generate typed joint/node/config tables and hash | Controlled source -> firmware/host/ROS/UI/sim views | No runtime defaults for missing safety fields |
| `protocol-core/<revision>` | Pure encode/decode and field validation | Typed native request/response <-> 8-byte frames | No I/O, clocks, model constants or safety state |
| `model-registry` | Exact-tuple capabilities, constants, limits and evidence states | Support records -> admitted capability | No family-wide promotion |
| `transport-adapter` | Actual bus initialization, TX/RX, error state and timestamps | Frames <-> hardware | No success from stubs; no command semantics |
| `can-scheduler` | Per-bus ownership, deterministic slots, response deadlines and utilization budget | Admitted requests -> correlated outcomes | No second writer; diagnostics cannot starve safety |
| `command-arbiter` | Source identity, priority, mode and lease selection | Candidate joint commands -> one candidate per joint | No direct native TX |
| `safety-supervisor` | State, guards, local limits, lease expiration, fault latch and safe request | Candidate + config + health -> admitted command or rejection | No remote bypass or implicit reset |
| `sensor-service` | Native/external samples, calibration identity, time and validity | Raw feedback -> typed joint/drive observations | No fabricated torque from current |
| `host-link` | Framing, CRC, version/capability negotiation, sequence and disposition | Typed command/state/control messages | Receipt is not actuator execution |
| `host-device-api` | Async session, reconnect policy, typed devices/replay/emulator | Application intent <-> gateway messages | No vendor bytes above device boundary |
| `dropbear-hardware-interface` | Stable joint command/state contract and diagnostics | ros2_control <-> host API/backend | No direct serial strings/native CAN |
| `protocol-emulator` | Revision-specific drive state, responses, latency and fault injection | Native frames <-> deterministic virtual drive | Not a plant-accuracy claim |
| `actuator-plant` | Model dynamics, sensors and declared uncertainty | Admitted effort/motion -> physical state | No unsourced “representative family” values |
| `robot-description` | Canonical topology, geometry, transmissions, inertials and sensors | Registry/assets -> URDF/xacro/backend forms | Generated duplicates are non-authoritative |
| `evidence-runner` | Test orchestration, manifests, result classification and trace links | Revision + test environment -> immutable result bundle | No HIL/bench promotion from offline runs |

## Canonical data contracts

All external numeric commands/state use SI units and explicit coordinate
frames. Native wire scales exist only in the protocol core.

- `ConfigIdentity`: schema version, robot revision, configuration hash,
  generator version.
- `ActuatorIdentity`: manufacturer, model, hardware revision, serial, drive
  firmware, protocol/revision, transport, node and bus.
- `JointIdentity`: canonical name, aliases, parent/child, axis/origin, motor to
  output mapping and sign.
- `CommandEnvelope`: source, sequence, creation and expiry monotonic times,
  config hash, requested state/mode and per-joint SI values.
- `CommandDisposition`: sequence, joint, admission result/reason, admission
  time, scheduler result and any observed acknowledgement. These are distinct
  phases.
- `DriveSample` / `JointSample`: device and sample timestamps, validity,
  position, velocity, q-axis current, derived effort only when evidenced,
  voltage, temperature, status/error, connectivity and calibration identity.
- `SafetySnapshot`: state, latched fault, last transition/event, lease owner,
  time remaining, prerequisite bitmap and safe-action disposition.

Host-link V1 now has byte-equivalent bounded Python and platform-independent
C++11 implementations, a shared cross-language vector corpus, strict session
receiver and a bounded async host-session reference under WP-060/WP-110. The
native link composes offline with the config guard, safety supervisor, bounded
fake scheduler and V4.4 emulator. A real authenticated transport adapter,
ESP32 runtime ownership and target timing/memory evidence remain open; the
current 64-byte prototype is migration input, not the V1 contract.

## Runtime control sequence

1. BOOT validates executable/config integrity and initializes transports with
   command output inhibited.
2. DISCOVERY observes exact actuator identity/capabilities and refuses wildcard
   support. It does not command motion.
3. DISABLED repeatedly verifies the evidenced tuple-specific safe action while
   publishing bounded state/diagnostics.
4. A compatible authenticated host requests a lease. The arbiter selects one
   source; the safety supervisor evaluates [command admission](command-admission.md).
5. ARMED establishes a valid lease and zero-motion preconditions. ENABLED is a
   separate explicit transition.
6. Each control tick evaluates safety events first, then lease/config/health,
   limits, arbitration, encoding and a budgeted scheduler slot.
7. Disable or lease-loss paths enter SHUTDOWN while the required motor-off
   acknowledgement is pending; acknowledgement reaches DISABLED and timeout or
   failure reaches FAULT. Any P0 failure preempts normal traffic, records
   context, requests safe action and enters latched FAULT as specified in
   [safety-state-machine.md](safety-state-machine.md).

## Simulation substitution

| Backend | Replaces | Preserves | Evidence class |
|---|---|---|---|
| Recorded replay | Host session input | Typed state/timing contract | offline |
| Protocol emulator | Native actuator(s) below scheduler | Native frames, revision state, timing/fault semantics | SIL-protocol |
| Actuator plant | Drive/mechanics below gateway or interface | Typed commands/state and parameter uncertainty | SIL-plant |
| Rigid-body engine | Full mechanics/sensors below SystemInterface | Canonical joints, limits and command/state API | SIL-robot |
| HIL rig | Physical actuators and/or load with real ESP32 | Link, scheduler and real-time behavior | HIL only when SRC-016..019 exist |

## Deployment units

- ESP32 image: generated config, protocol core, real transport, scheduler,
  arbiter, safety, sensors and host link.
- Host package: codec reference tests, device API, evidence/replay tooling and
  ROS 2 hardware plugin.
- Simulator packages: deterministic protocol emulator; parameterized actuator
  plant; engine adapters fed from canonical robot description.
- Browser: catalog, GLB inspection, telemetry and authenticated diagnostics;
  no independent command path.
- Evidence store: append-only result bundles indexed by tuple, requirement,
  code/config revision and evidence class.

## Quality budgets to establish before physical enable

Exact values are open requirements derived by WP-080/WP-100 and cannot be
invented at P1: control period/jitter, bus utilization ceiling, response and
lease deadlines, sensor age, stop latency, host reconnect policy, numeric
error, thermal uncertainty and simulation tolerances. Absence of a required
budget is an enable blocker, not a default.

## Open architectural evidence

- Physical Dropbear exact tuples, bus topology and firmware applicability.
- Independently verified motor-off behavior and physical power removal.
- Authenticated host transport binding, persistent replay defense and runtime
  integration of the accepted V1 framing/version negotiation.
- Real ESP32 bus send/RX outcomes, retry/arbitration-loss/bus-off policy,
  utilization and target WCET/stack evidence.
- Model parameter and thermal evidence for actuator plants.
- Housing/output segmentation and axis for all 44 CAD models.
- Canonical Dropbear description selection and physics-engine benchmark.
