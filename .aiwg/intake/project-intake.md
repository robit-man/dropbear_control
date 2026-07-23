# Project intake: MYACTUATOR library and Dropbear control stack

Status: brownfield discovery baseline
Date: 2026-07-22
Confidence: high for repository findings; medium for physical topology and
motor-specific behavior until hardware/manufacturing records are supplied

## Objective

Turn the current MYACTUATOR/ESP32 scaffolding and Dropbear bench prototype into
a model-complete, testable, safety-bounded actuator library, digital twin, and
low-to-high robot control stack.

## In-scope systems

- this repository's ESP32 firmware, host Python library, protocol contracts,
  browser dashboard, simulator, tests, and CAD assets;
- official MYACTUATOR product packages and current protocol/manual sources;
- Dropbear's current low-level ESP32 and Flask control code;
- the interfaces needed to reach robot hardware abstraction, state estimation,
  joint/whole-body control, planning, simulation, HIL, and operator tooling.

## Current baseline

- Firmware compiles, but active transports and family drivers do not perform
  actuator I/O.
- Host self-test and browser toy-simulation tests pass; physical transports and
  concrete devices are incomplete.
- Existing protocol/product contracts are drafts and conflict with current
  vendor material and internal frame definitions.
- The browser is substantial uncommitted work, but uses synthetic dynamics and
  zero-byte STEP placeholders.
- The official catalog has 44 products and 53 STEP variants; all source STEP
  files are now available in a reproducible ignored cache.
- The Dropbear low-level control working copy is pinned to commit
  `13cf5ecaa39b8b89c794fe905dcea0490cfa7726`.
- The wider Dropbear tree already contains detailed/simplified URDF, Gazebo
  `ros2_control`, Isaac and Altair work. It also contains duplicate sources and
  committed generated outputs, and its five-joint open-loop simulated leg does
  not map to the six-actuator hardware leg.
- Dropbear directly emits torque commands to 12 hard-coded CAN IDs and samples
  external analog sensors, but has no actuator feedback path, command lease,
  verified stop behavior, stable high-level interface, or single-writer rule.

## Constraints and assumptions

- Existing uncommitted firmware and web changes are user work and were not
  rewritten during intake.
- Source STEP files are retained locally but not committed until redistribution
  rights and large-asset storage are decided.
- The exact motor models, drive firmware versions, electrical topology, robot
  revision, calibration values, and safety circuitry remain to be captured.
- Hardware claims require bench/HIL evidence; compilation and loopback are not
  accepted as actuator support.
- The motor's integrated drive should close vendor-supported inner loops unless
  measurement shows a compelling need for a different boundary.

## Highest-priority requirements

| ID | Requirement | Acceptance evidence |
|---|---|---|
| SAFE-001 | Boot and communication loss leave all actuators verifiably disabled | power-cycle and link-loss HIL traces |
| SAFE-002 | Exactly one arbiter writes commands to each actuator | architecture/test proof and contention fault test |
| CFG-001 | One versioned robot/joint registry supplies IDs, models, axes, signs, units, limits, assets, and calibration references | generated firmware/host/UI/URDF artifacts have identical schema hash |
| PROTO-001 | Native protocol codecs match official manual vectors and captured hardware frames | golden-vector suite and CAN captures |
| FW-001 | ESP32 schedules real CAN request/response traffic and reports actuator status/faults | one-motor then six-motor bench logs |
| LINK-001 | Host link is framed, versioned, checksummed, sequenced, timestamped, acknowledged, and lease-bound | fuzz/resync/timeout/integration tests |
| CAD-001 | Every official product retains provenance-pinned source CAD | 44/44 catalog and archive checksum records |
| CAD-002 | Every claimed simulation asset has separate fixed/output geometry and reviewed axis/origin/scale | conversion manifest and rotation regression |
| SIM-001 | Protocol emulator reproduces supported commands, status, timing, modes, and injected faults | driver conformance suite |
| SIM-002 | Whole-robot simulator and hardware use the same joint/hardware API | shared controller integration test |
| ROS-001 | A robot hardware interface exposes canonical joint commands, state, faults, and timestamps | interface tests in SIL and HIL |
| TEST-001 | Model support is evidence-based by exact model/firmware/protocol/mode tuple | published support matrix with current evidence |

## Open inputs needed before implementation decisions harden

- exact Dropbear actuator model at each joint and drive firmware version;
- whether left/right legs have physically isolated CAN buses and which ESP32
  owns each bus;
- transceiver/oscillator details and measured CAN bitrate/termination;
- actual output-side sensor type/wiring and calibration procedure;
- power distribution, contactor/e-stop topology, allowable bench voltage and
  current;
- current robot CAD/URDF/mass-property authority;
- intended high-level platform and real-time rate requirements;
- vendor permission for redistributing STEP/manual assets.

These inputs affect implementation details, but do not block protocol cleanup,
simulator asset provenance, a protocol emulator, or the safety architecture.

## Intake outputs

- [Library completeness assessment](../../docs/MYACTUATOR_LIBRARY_ASSESSMENT.md)
- [Dropbear low-level notes](../../docs/DROPBEAR_CONTROL_STACK_NOTES.md)
- [Target control/simulation architecture](../../docs/CONTROL_STACK_TARGET.md)
- [Solution profile](solution-profile.md)
- [Option matrix](option-matrix.md)
- [Official CAD catalog](../../assets/myactuator/catalog.tsv)
