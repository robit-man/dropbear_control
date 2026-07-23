# Iteration 2 verification report

- Executed: 2026-07-22T18:22:16-07:00
- Iteration result: `PASS-OFFLINE-FOUNDATION`
- Hardware commanded: no
- Physical applicability established: no
- Plant or rigid-body fidelity established: no

## Delivered slices

| Work package | Deliverable | Executable evidence | Result |
|---|---|---|---|
| WP-020 | Exact six-field support/evidence registry | 27 Python tests | PASS offline |
| WP-030 | Canonical Dropbear Draft 2020-12 schema, semantic validator, digest and incomplete observed migration input | 23 Python/schema tests | PASS offline foundation |
| WP-130 | Deterministic multi-node RMD CAN V4.4 protocol-state emulator | 22 Python tests plus shared 34-vector codec corpus | PASS SIL-protocol foundation |
| WP-180 | Unified repository gate includes all three suites | `tools/test_all.sh` | PASS |

## Unified gate evidence

`tools/test_all.sh` passed end-to-end and reported:

- 44 unique vendor model packages;
- 53 STEP assets: 26 assembly, 27 flattened;
- 9 document sets and 32 PDFs;
- legacy host `HOSTLIB_OK`;
- 14 Python protocol tests and 175 native C++ codec checks over 34 shared
  vectors;
- 27 support/evidence policy tests;
- 314 native safety-supervisor checks;
- 22 deterministic protocol-emulator tests;
- 23 structural/semantic Dropbear configuration tests;
- all existing web protocol/simulator/harness/end-to-end regressions;
- 77/77 requirement trace rows, 20 sources, 10 ADRs, 20 work packages,
  90 cataloged tests and 48 checked links;
- ESP32 PlatformIO compile success at 6.8% RAM and 22.8% flash;
- tracked-diff whitespace check.

## Acceptance findings

- The vendor catalog creates no support records and cannot authorize powered
  use. Every powered decision requires an exact model/hardware/firmware/
  protocol/transport/control-mode tuple, hardware-level evidence, live
  dependency evidence and the independent runtime safety boundary.
- The emulator uses the revision-exact codec, virtual monotonic time and
  deterministic scenarios. It never converts a command into synthetic
  feedback dynamics and explicitly declares physical-plant and
  model/firmware-applicability evidence false.
- The Dropbear example has 12 canonical joints, five external encoder
  observations per leg and explicit missing hip-yaw external sensing. Legacy
  `0x141` through `0x14C` values remain unverified full command-ID
  observations. Native node IDs, owners, exact motor tuples, limits,
  calibrations, CAD bindings and enable authority remain unknown, so motion is
  denied.

## Remaining holds

This result does not satisfy G0 physical readiness, G2 bench/HIL, exact
installed-motor applicability, real ESP32 CAN scheduling, physical stop or
independent power removal, 44-model output-shaft articulation, sourced
actuator plants, ROS integration, or a whole-robot rigid-body simulator.

The next delivery slice is WP-060-T01..06 with WP-030-T05/T06: one bounded,
versioned host link carrying config identity, leases, state validity and
dispositions; generated configuration views; corrupt/replay/fuzz coverage;
and hash-mismatch admission rejection.
