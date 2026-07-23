# Iteration 9 plan — authoritative joint observation, calibration and limit admission

- Iteration status: `COMPLETE-OFFLINE-WITH-EXTERNAL-CARRIES`
- Phase context: P2 elaboration, WP-030/WP-090/WP-120 integration preparation
- Entry gate: Iteration 8 unified offline gate green; 77 requirements, 109
  cataloged tests, 44-model/53-configuration CAD coverage, 12-actuator
  Dropbear reconciliation and motion false
- External carry: one X12 independent-review workbench remains ready; no
  submitted decision exists
- Physical baseline: exact installed motor tuples 0/12, runtime routes 0/12,
  physical calibrations 0/12, real plant parameter sets 0/44, accepted CAD
  configurations 0/53
- Safety boundary: no powered motor, physical calibration movement, HIL,
  physical stop, real CAN driver, robot enable or inferred ROS mapping

## Outcomes

Iteration 9 makes observation truth executable. It defines immutable,
provenance-bound calibration and limit records; atomically admits only records
matching the active robot/config/installed identity; converts timestamped raw
observations without hiding missing hip yaw; reconciles multiple sensors only
under an explicit policy; and applies the most restrictive valid limit. It
also gives host/robot consumers a generated per-actuator readiness view that
denies all current Dropbear joints.

No synthetic fixture or legacy offset may become a physical calibration, and
no state estimate may create physical motion authority.

## Track A — independent CAD evidence carry

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I9-A01 | Preserve exact X12 packet/workbench | Source, candidate, hypothesis, template and local evidence hashes reproduce |
| I9-A02 | Receive independent decision | Identified non-automation reviewer submits complete accept/amend/reject record |
| I9-A03 | Validate and apply transactionally | Decision schema, occurrence partition, frame, axis, answer and hash checks pass before ledger regeneration |
| I9-A04 | Retain non-promotion boundary | Acceptance, if any, changes exact CAD status only; motor/plant/Dropbear support remains separately denied |
| I9-A05 | Start the next selector cohort | Only after A03 validates the workflow; no automated semantic reviewer |

Track A remains asynchronous and cannot be converted into an inferred
acceptance or a blocker for offline state work.

## Track B1 — calibration evidence contract

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I9-B01 | Exact calibration subject | Require robot hardware revision, canonical joint/actuator, installed serial and exact model/hardware/firmware/protocol/transport/control tuple, bus and node |
| I9-B02 | Configuration binding | Require canonical config ID/revision/digest and calibration schema/revision; reject stale or cross-robot reuse |
| I9-B03 | Coordinate definition | Record external/raw zero, native/output zero, joint zero, motor-to-joint sign, output-per-motor ratio, wrap domain and SI units without implicit defaults |
| I9-B04 | Procedure provenance | Require method, fixture/reference, tool ID/version/calibration, operator, UTC time, environment and source artifact hashes |
| I9-B05 | Measurement evidence | Require repeated samples, uncertainty/bounds, residual and explicit pass criteria; raw legacy offsets remain candidate observations only |
| I9-B06 | Invalidation contract | Enumerate motor/sensor/controller replacement, node reassignment, mechanical disassembly, firmware/config/frame/procedure changes and expiry |
| I9-B07 | Integrity and lifecycle | Canonical digest, immutable accepted record, draft/rejected/accepted/revoked states and explicit reviewer authority |
| I9-B08 | Empty physical baseline | Generate no accepted physical records from current repository observations; readiness remains 0/12 |

## Track B2 — limit provenance and effective-bound selection

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I9-C01 | Four provenance classes | Separate vendor rating, software command limit, measured safe robot limit and runtime derate |
| I9-C02 | Coordinate and mode scope | Every bound declares motor/output/joint coordinate, sign convention, SI unit, control mode, direction and operating envelope |
| I9-C03 | Evidence validity | Source/hash/revision/reviewer/time/expiry and exact installed/config dependency are mandatory |
| I9-C04 | Restrictive selection | Lower/upper/magnitude bounds resolve by intersection/minimum only across applicable valid evidence |
| I9-C05 | Unknown/contradiction denial | Missing required class, empty intersection, unit/frame mismatch, NaN/Inf or stale dependency returns typed denial; never infinity, zero-by-default or family fallback |
| I9-C06 | Runtime derate snapshot | Derate includes generation, sample time, validity horizon and reason; stale/reordered generation denies |
| I9-C07 | Boundary suite | Inclusive endpoints, direction asymmetry, wrap coordinates, conflicting evidence, staleness and exact-tuple drift pass deterministic tests |

## Track B3 — allocation-free observation/calibration core

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I9-D01 | Typed raw samples | Fixed-size source/joint/config/calibration identity, source kind, monotonic sample/RX time, raw value/unit and fault/quality fields |
| I9-D02 | Calibration admission | Active immutable snapshot matches exact subject/config/integrity/generation and is valid at sample time |
| I9-D03 | External conversion | Convert raw observation to canonical joint radians only through admitted explicit affine/wrap/sign semantics; finite/overflow/range checks fail closed |
| I9-D04 | Native conversion | Keep motor/native/output coordinates distinct; apply ratio/sign/zero only where calibration proves them |
| I9-D05 | Age and ordering | Reject future, stale, duplicate, regressed and overflowing time/generation; expose sample and RX age separately |
| I9-D06 | Missing-source behavior | A required missing source yields unavailable state; hip yaw cannot borrow or alias another hip channel |
| I9-D07 | Reconciliation policy | Explicit reviewed policy selects native, external, require-both or comparison; no silent average/fallback |
| I9-D08 | Disagreement/fault | Required-source invalidity or bounded disagreement returns typed invalid/fault evidence with both samples retained |
| I9-D09 | Limit application | Observation and command checks consume one exact effective-limit snapshot and preserve reason/provenance IDs |
| I9-D10 | Embedded constraints | C++11, allocation-free service path, warnings-as-errors, no exceptions/RTTI, ASan/UBSan and allocation-symbol scan pass |

## Track B4 — host parity and deterministic fixtures

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I9-E01 | Reference implementation | Python reference uses the same closed enums, field-presence and denial semantics as native core |
| I9-E02 | Shared golden corpus | Accept/reject fixtures cover every source/policy/limit/time/integrity outcome with byte-stable canonical JSON |
| I9-E03 | Synthetic fixtures | Clearly synthetic linear sensors/native positions exercise conversion, wrap, latency, disagreement and dropout without physical claims |
| I9-E04 | Protocol/plant coupling | Synthetic plant observations may enter only through a synthetic source identity and never satisfy a physical calibration dependency |
| I9-E05 | Replay determinism | Identical ordered samples produce identical state/disposition trace and digest across repeated runs |

## Track B5 — Dropbear readiness projection

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I9-F01 | Per-actuator dependency graph | Join canonical actuator, installed identity, route, calibration, limits, feedback policy, CAD binding and graph mapping by exact stable IDs |
| I9-F02 | Generated denial reasons | Every incomplete joint emits ordered machine-readable blockers; generation never fills an absent value |
| I9-F03 | Hip-yaw distinction | Both hip-yaw rows explicitly expose missing external feedback and unresolved reviewed policy |
| I9-F04 | Consumer boundary | Host/firmware/ROS/simulator loaders may query readiness but cannot obtain a route, calibration or effective limit from incomplete rows |
| I9-F05 | Configuration parity | Reconciliation and readiness artifacts bind the unchanged canonical digest and source hashes |
| I9-F06 | Motion hold point | Global and per-actuator motion remain false until exact installed/config/calibration/limits/safety/HIL dependencies pass |

## Track B6 — Dropbear description evidence inventory

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I9-G01 | Canonical-source candidates | Hash source URDF/xacro/controller/CAD-description files separately from committed build/install derivatives |
| I9-G02 | Joint/link candidate graph | Extract named links/joints, types, parent/child, axes, origins, mimic/transmission/control membership and mesh references as observations |
| I9-G03 | Duplicate/drift report | Detect source/build/install and detailed/simplified divergence without selecting authority automatically |
| I9-G04 | Active/passive/closed-chain questions | Emit review questions for every ambiguous five-ROS/six-actuator or loop-closure edge |
| I9-G05 | No generated runtime graph | Until reviewed, graph candidates remain outside canonical runtime views and cannot populate ROS-actuator mappings |

## Track B7 — unified evidence output

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I9-H01 | Machine gate summary | Full gate writes canonical JSON with code/config/tool identity, stages, outcomes and evidence class |
| I9-H02 | Failure preservation | Failed stage/exit and prior completed stage evidence remain inspectable without being reported as a pass |
| I9-H03 | Claim invariants | Summary states physical work not performed, 0/44 support/real plants, 0/53 accepted CAD and Dropbear motion false |
| I9-H04 | Iteration report | Catalog/trace/gate totals and external carries reconcile exactly with generated evidence |

## Dependency and execution order

1. B01..B08 establishes calibration meaning before any conversion.
2. C01..C07 establishes limit meaning independently; D09 consumes it only
   after the selector is tested.
3. D01 -> D02 -> D03/D04 -> D05/D06 -> D07/D08 -> D09/D10.
4. E01/E02 may proceed with B/C schemas; E03..E05 require the native policy
   surface to stabilize.
5. F01 consumes current reconciliation plus B/C schemas; F02..F06 remain
   denial-only with the empty physical baselines.
6. G01/G02 inventories evidence; G03/G04 classify gaps; G05 prevents
   candidate promotion.
7. H01..H04 follows stable test lanes and closes the iteration.
8. A01..A05 remains independent and never grants motion or support.

## Hazard ledger

| Hazard | Unsafe shortcut prohibited | Required control |
|---|---|---|
| H9-01 stale calibration reuse | Match only joint name/model family | Exact robot/config/serial/tuple/bus/node/frame dependency and invalidation |
| H9-02 sign/ratio confusion | Combine direction, gear ratio and zero into an undocumented scalar | Explicit coordinate transforms with units, direction and golden boundary cases |
| H9-03 fabricated feedback | Copy/alias a neighboring channel or command state | Required-source policy and missing hip yaw as unavailable |
| H9-04 stale sample appears current | Use RX time as sample time or ignore wrap | Separate monotonic sample/RX age and bounded wrap-safe comparison |
| H9-05 false fusion confidence | Average disagreeing/invalid sources | Explicit policy, validity gates, disagreement threshold and retained evidence |
| H9-06 unsafe limit fallback | Vendor max, infinity, zero or symmetric default | Applicable evidence intersection; missing/contradictory bound denies |
| H9-07 synthetic-to-physical calibration | Reuse synthetic affine fixture | Exact evidence class/source kind dependency and physical readiness false |
| H9-08 CAD/URDF name promotion | Map by name/order/mesh label | Candidate graph plus human review questions; zero runtime mappings |
| H9-09 generator collision | Multiple producers own one output tree | Exclusive generated namespace and stale-file tests |

## Iteration gates

- G9.1: strict calibration schema/semantics and empty physical registry pass.
- G9.2: limit provenance/intersection selector passes all unknown, stale,
  contradictory and boundary cases.
- G9.3: native observation/calibration/fusion core passes normal, sanitizer and
  allocation constraints.
- G9.4: Python/native golden parity and deterministic replay pass using only
  synthetic fixtures.
- G9.5: Dropbear readiness projection gives 0/12 ready, preserves both hip-yaw
  gaps and motion false.
- G9.6: description inventory is source/hash reproducible and has zero promoted
  ROS-actuator mappings.
- G9.7: unified evidence JSON, traceability, generated drift, host/native/web
  tests, ESP32 compile and whitespace pass.

## Definition of Done

- [x] Calibration facts are exact, immutable, provenance-bound and cannot be
  manufactured from legacy offsets or synthetic fixtures.
- [x] Effective limits are selected only from applicable valid evidence and
  missing/contradictory inputs fail closed.
- [x] Timestamped observation conversion/fusion is allocation-free and never
  hides missing, stale, reordered or disagreeing inputs.
- [x] Host/native golden traces agree and synthetic evidence remains visibly
  nonphysical.
- [x] All 12 Dropbear actuators expose exact readiness blockers; zero routes,
  calibrations, ROS mappings and motion authority remain.
- [x] Candidate robot-description topology is inventoried without becoming
  canonical by automation.
- [x] Independent CAD review is applied exactly or carried explicitly.
- [x] Unified offline gate and Iteration 9 verification report are green.
