# Iteration 11 verification report

Result: `PASS-OFFLINE-PHYSICAL-HOLD`

## Verified outcome

Iteration 11 delivered positive-capable source and structured-graph authority
lifecycles, deterministic lifecycle-aware host/ROS/simulator/UI projections,
registry-generation revocation in the typed hardware API, and an exact
controller-neutral CAN-adapter intake. The real tracked state remains
deliberately empty: no source, graph, mapping, adapter, CAD, plant, support or
motion authority was accepted.

## Delivered evidence

| Area | Verified result |
|---|---|
| source lifecycle V2 | accept/reject/revoke/atomic-supersede replay; exact drift/digest/order/independence checks; 0 tracked submissions/events/active |
| structured graph V2 | frames, transforms, expressed-in axes, aliases, chirality, symmetry, structured couplings/domains/singularities, closure, DOF, ownership and dependencies |
| graph lifecycle V2 | positive synthetic replay and immediate revocation/supersession; 0 tracked submissions/events/active |
| consumer projections | four generation/hash-parity views; 0 frames, mappings, URDF fragments, physical plants or local paths |
| typed hardware API | source/graph registry generations bind admission, sessions and handles; live generation change faults the session and cancels use |
| CAN adapter intake | exact TWAI/MCP2515-neutral manifest semantics; 0 reviewed/selected; physical factory disabled |
| discovery handoff | visual-only U0 request, assignment register and 15-gate readiness ledger; execution remains false |

The new source, graph, lifecycle-projection, hardware-API and adapter suites
include positive temporary fixtures, adversarial mutations and tracked
denial-baseline tests. Synthetic acceptance is never written into project
authority registries.

## Repository gate

Pre-closure machine run `26a26b5affbaad6ae66abb3b` passed 57/57 ordered
stages from 2026-07-23T08:02:58.222Z through
2026-07-23T08:04:35.058Z. The closure rerun at
`generated/verification/offline_gate_report.json` is the canonical machine
record and hashes these closure sources.

The gate covers:

- 23 critical artifact hashes and fail-closed claim invariants;
- 77/77 requirements, 122 catalog tests and checked documentation links;
- source/graph lifecycle generation, replay, revocation and mutations;
- host/API, native gateway, protocol, safety, emulator, CAD and plant suites;
- browser protocol/toy-simulator regressions;
- ESP32 compile-only regression; and
- tracked-diff whitespace.

Evidence classes are specification, offline static, offline unit, offline
build and synthetic SIL. Physical evidence is false.

## Fail-closed non-claims

- No hardware access, CAN capture, bench, HIL or robot motion was performed.
- No MYACTUATOR model/firmware/protocol tuple is supported for powered use.
- No source or graph submission/event is accepted or active.
- No canonical physical graph, ROS mapping, command handle or real simulator
  backend exists.
- No TWAI or MCP2515 controller, transceiver, pinout, clock or driver is
  selected.
- No real motor-plant parameter set or accepted output-shaft CAD
  configuration exists.
- The preserved ESP32 runtime was not wired to a physical adapter or the new
  gateway/API path.

## External carries

1. assign an independent source reviewer and source lifecycle approver;
2. decide seven source roles and all 29 divergent groups;
3. assign mechanical/control reviewers and answer all 161 graph questions;
4. migrate the reviewed graph to V2 and obtain independent approval;
5. complete and approve the exact visual-only U0 request;
6. capture/review installed motor/controller/transceiver/connector facts;
7. select and conform one exact listen-only adapter on an isolated fixture;
8. separately authorize bounded L1 and safe-power phases;
9. review installed-model housing/output/axis CAD and source real plant
   parameters; and
10. progress through one-actuator, leg and robot HIL under separate gates.
