# Iteration 10 verification report

Result: `PASS-OFFLINE`

## Verified outcome

Iteration 10 established independent source and robot-graph authority
contracts, strict canonical-graph admission, four denial-only consumer views,
a graph/readiness-gated joint API and an Iteration 11 unpowered-discovery
package. None of these artifacts selects real Dropbear source files, answers a
real graph question, creates a ROS-actuator mapping, configures physical I/O
or grants support/motion.

## Delivered evidence

| Area | Verified result |
|---|---|
| source inventory | 198 paths, 96 objects, 29 divergent logical groups |
| source authority | 7 roles, 29 divergence decisions, 0 submitted/accepted/runtime-complete |
| graph review | 161 exact questions, 10 cohorts, 0 submitted/accepted/canonical |
| synthetic graph proof | rooted tree plus positive mimic, physical closed-chain and simulator-only closure; adversarial topology/identity/reviewer tests |
| graph projections | 4 parity-checked views, 0 transforms/URDF/transmissions/plants/mappings/handles/paths |
| hardware API | 12 exact actuators, typed command/state provenance, fail-only physical default |
| discovery | 12 empty installed slots, 7 runbooks, 0 submissions/controllers/authorized actions |
| CAD/plant physical baseline | 0/53 accepted CAD configurations, 0/44 sourced real plants |
| readiness | 0/12 motion-ready, 0 routes/calibrations/mappings |

The graph, projection, hardware API and discovery suites contain 59 focused
tests. The positive records are synthetic unit fixtures and are not written
to an evidence registry.

## Repository gate

Pre-closure machine run `04f60a60707aa6f3712e8c53` passed 52/52 ordered
stages from 2026-07-23T07:05:55.010Z through
2026-07-23T07:07:07.186Z. The closure rerun at
`generated/verification/offline_gate_report.json` is the canonical machine
record and hashes the closure sources.

The gate covers:

- 15 critical artifact hashes and 34 claim invariants;
- 77/77 requirements, 118 catalog tests and 48 checked links;
- all source/CAD/plant/config/protocol/safety/host/native/gateway/graph/API/
  discovery suites;
- browser protocol and toy-simulator regressions;
- ESP32 compile with 22,360 bytes RAM and 299,709 bytes flash; and
- tracked-diff whitespace.

The machine evidence classes are specification, offline static, offline unit,
offline build and synthetic SIL. Physical evidence is false.

## Fail-closed non-claims

- No hardware access, CAN capture, bench, HIL or robot motion was performed.
- No MYACTUATOR model/firmware tuple is supported for powered use.
- No real motor-plant parameter set or physical rigid-body graph exists.
- No source-authority, graph or CAD reviewer submission exists.
- The ten external sensor names remain unverified observations; hip yaw remains
  explicitly missing on both sides.
- Gazebo/open-loop candidates are not a physical hardware plugin.
- The preserved ESP32 runtime was not wired to the new API or adapters.

## External carries

1. independent source-authority reviewer and seven-role decision;
2. independent graph/mechanical reviewer answering all 161 questions;
3. independent X12/output-member CAD review and remaining model cohorts;
4. hardware-owner/safety approval for one bounded unpowered inventory;
5. actual controller/transceiver/pin/clock/TX-disable observations;
6. independent safe-power evidence;
7. exact installed motor/firmware/protocol/route records;
8. physical calibration, limit and feedback-reconciliation records;
9. sourced/correlated real plant parameters; and
10. staged adapter, one-actuator, leg and robot HIL.

Internal V2 carries also remain: positive registry revocation/supersession,
structured alias/chirality/symmetry metadata, structured coupling
domain/singularity equations, algebraic DOF accounting and positive
dependency closure. V1 represents these as explicit reviewed facts/equations
or unresolved questions and cannot infer them.
