# MYACTUATOR / Dropbear master program plan

This dependency-ordered plan spans offline protocol truth through robot
behavior. Status is evidence-based: `DONE-OFFLINE`, `ACTIVE`, `OPEN`, or
`PHYSICAL-HOLD`. Gate definitions are in
[phase-gates.md](../gates/phase-gates.md); requirement links resolve through
[traceability-matrix.md](../requirements/traceability-matrix.md).

## Dependency spine

```text
WP-000 -> 010 -> 020 -> 030 -> 040 -> 050 -> 060 -> 070
                                      |      |      |
                                      +------v------v
                                             080 -> 090 -> 100
030 -> 110 -> 120 -> 160 -> 190               |
010 -> 140 -> 150 -> 160                       |
040 -> 130 -> 150 -> 160                       |
all work packages -> 170 -> 180 -> phase release
```

## Work-package control table

| WP | Outcome | Depends on | Requirements | Exit evidence / gate | Status |
|---|---|---|---|---|---|
| WP-000 | Preserve prototype and establish safe baseline | — | SYS-005, VER-007 | Cleanly attributable snapshot; exact physical inventory; bench prohibition/plan; G0 | ACTIVE; physical inventory open |
| WP-010 | Controlled official sources and acquisition provenance | 000 | SYS-001, CAD-001, SEC-005 | 44-model/53-STEP/9-document manifests, hashes, change policy | DONE-OFFLINE; six-page live snapshot exactly matches all 53 tracked archive URLs and drift is transactional |
| WP-020 | Exact-tuple capability/evidence ledger | 010 | SYS-002..004, PRO-006, VER-001 | Schema validation; zero wildcard claims; unsupported fields explicit | ACTIVE; positive installed-unit applicability lifecycle, 145-subject evidence queue and zero-exception 12-rule claim-surface audit are green, while real accepted evidence remains zero |
| WP-030 | Canonical Dropbear registry and generators | 000,020 | CFG-001..006, ROB-001 | Reviewed canonical registry, generated-view parity, config hash | ACTIVE; schema/views/guard, positive source lifecycle and pinned 12-actuator/10-sensor reconciliation green; tracked authority 0 and physical refinement open |
| WP-040 | Protocol extraction and applicability analysis | 010,020 | PRO-001,004..006 | Clause ledger per revision/tuple; ambiguity log; reviewed units | ACTIVE; V4.4 offline core and synthetic independently reviewed exact-tuple admission green, physical tuple/capture decisions open |
| WP-050 | Pure native codecs and golden vectors | 040 | PRO-002..008, FW-006, VER-003 | Host+embedded-core vectors/boundaries/malformed pass; G1 | ACTIVE |
| WP-060 | Versioned host-link contract and parser | 020,030,070 | LNK-001..005 | Compatibility matrix; corrupt/replay/fuzz tests; dispositions | ACTIVE; Python/native V1 parity green, authenticated adapter/transport open |
| WP-070 | Deterministic command lease/admission/safety core | 020,030,040 | SAF-001..010, VER-004 | Fake-clock transition/property/fault tests; boot-disabled | ACTIVE; safety/config identity/fake-scheduler composition, bounded restart-persistent fault context, six-source deterministic fault arbitration and 4,789-sequence final-TX property exploration green; trusted observation/persistence adapters and real safe action open |
| WP-080 | Real ESP32 transports and deterministic bus scheduler | 050,070 | FW-001..002, SAF-008 | Adapter integration; timing/utilization/error tests | ACTIVE offline core; bounded gateway, controller-independent contract and exact no-I/O adapter intake green; installed selection/real driver/I/O/utilization/recovery open |
| WP-090 | Feedback, sensors, calibration and model limits | 030,040,080 | SAF-007, FW-003..004 | Validity/age/fusion/limit tests and exact provenance | ACTIVE offline core; exact calibration, restrictive four-class limits and allocation-free conversion/replay/explicit reconciliation/position checks green; host parity and physical records remain open/0 |
| WP-100 | Physical safety integration and one-motor/leg HIL | 080,090,170 | SAF-005..009, VER-006 | Independent cut, stop/fault/disconnect injection, 8-hour run; G2/G3 | PHYSICAL-HOLD |
| WP-110 | Coherent host API and `ros2_control` interface | 030,060,070 | HST-001..005, ROB-004 | Replay/emulator adapters, lifecycle/error tests, stable interface | ACTIVE; bounded host/session API plus exact Jazzy C++ plugin build/load and Python/C++ lifecycle/read/write/revocation parity green; accepted graph descriptor, authority/lease service, concrete gateway adapter and controller integration open |
| WP-120 | Canonical Dropbear description reconciliation | 030,110,140 | ROB-001..003 | Semantic two-leg joint parity; physical/sim mappings; provenance | ACTIVE observation foundation; structured graph V2 and lifecycle registry/projections green, but source/graph authority and reviewed mappings remain 0 |
| WP-130 | Revision-exact protocol emulator | 040,050,070 | SIM-001..002 | Conformance, timing/state/fault injection suite | ACTIVE; protocol-state emulator, synthetic native gateway and explicit synthetic plant coupling green, physical applicability open |
| WP-140 | Evidence-preserving 44-model CAD pipeline | 010,020,030 | CAD-001..006, VER-005 | 44/44 reviewed, 53/53 preserved, output articulation/axis; G4 asset | ACTIVE; 53/53 inspected/imported, review/toolchain gates green, output shaft 0/44 accepted |
| WP-150 | Sourced actuator plants and converted assets | 130,140 | SIM-003, CAD-003..005 | Parameter/uncertainty records; plant/thermal/mesh regressions | ACTIVE; 15 manuals/215 pages yield 531 page-bound candidates for 44/44 models, all 406 mapped candidates bind handoff tasks, and the fact lifecycle, all-38-fact/exact-tuple assembler plus reviewed V1 and full-semantic event-scheduled V2 runtime adapters are gate-integrated; assigned reviewers, accepted facts, profiles, contracts and sourced/physical exact-model plants remain 0/44 |
| WP-160 | Consolidated Dropbear digital twin | 110,120,130,150 | SIM-004..006, ROB-002..005 | Backend benchmark, schema parity, controller/replay tests; G5/G6 | ACTIVE synthetic foundation; generic rigid-body benchmark and transactional twelve-axis V2 plant bank are green, while canonical source/graph/CAD/plant admission remains 0 |
| WP-170 | Security, operations and safe bench controls | 000,060,070 | ROB-007, SEC-001..005, SAF-009 | Threat mitigations, identities/roles, signed config/update, runbooks | ACTIVE offline core; post-auth role/audit, exact installed security-profile intake and Python/native artifact transaction/reboot semantics green; tracked roots/keys/adapters remain zero and real authentication/crypto/persistence/endpoint/runbook work is open |
| WP-180 | Unified verification, traceability and release evidence | all releasable WPs | SYS-006, VER-001..007 | One test entry; coverage/evidence validation; no claim inflation | ACTIVE; the twelve-axis 80-stage/140-test source state passed twice with identical source/diff identities; current wiring closes planned `TST-CLM-003` and adds an 81st claim-surface stage plus 45th critical artifact, whose two-pass checkpoint and signed release remain open |
| WP-190 | Locomotion, behavior and operator release | 100,160,170,180 | ROB-005..007 | G7 controller/behavior validation on approved backends/hardware | OPEN |

## Granular execution ledger

### WP-000 — preservation and physical baseline

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-000-T01 | Record repository revision, dirty-file ownership and preservation rule | — | Status snapshot + diff attribution |
| WP-000-T02 | Pin Dropbear upstream revision and sparse-audit scope | T01 | SRC-014 |
| WP-000-T03 | Archive prototype interfaces/known defects as regression inputs | T01,T02 | Regression IDs TST-DBR-* |
| WP-000-T04 | Inventory each installed motor label, serial, hardware/firmware, brake, node and bus | T02 | SRC-016 exact-tuple sheet |
| WP-000-T05 | Record wiring, termination, controller ownership, power/current limits and physical cut | T04 | Reviewed topology + photos/drawings |
| WP-000-T06 | Quarantine powered tests until bench hazard review/runbook approval | T05 | Signed G0 physical checklist |

### WP-010 — source control

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-010-T01 | Validate 44 unique catalog names and package revisions | 000-T01 | Catalog validator result |
| WP-010-T02 | Validate all 53 STEP hashes, source URLs and variant-to-model mapping | T01 | Asset acquisition manifest |
| WP-010-T03 | Validate nine document-set archives and 32 extracted PDFs | T01 | Document acquisition manifest |
| WP-010-T04 | Record authoritative-use limits and PDF clause-review rule | T02,T03 | SRC-001..015 register |
| WP-010-T05 | Detect vendor revision drift without silently updating baseline | T02,T03 | Pinned resync/diff test |

### WP-020 — support/evidence ledger

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-020-T01 | Implement exact `SupportKey` schema and `UNKNOWN -> unsupported` rule | 010 | Schema tests |
| WP-020-T02 | Instantiate 44 catalog records and retain 53 CAD variant links | T01 | 44/44, 53/53 validation |
| WP-020-T03 | Add capability-granular sources, limits and evidence fields | T01 | Record schema review |
| WP-020-T04 | Implement state lattice, staleness propagation and revocation | T03 | Transition/invalidation tests |
| WP-020-T05 | Generate and audit UI/API/document support wording solely from evidence state | T04 | COMPLETE-OFFLINE: 20 roots, 674 text/JSON surfaces, 566 hash-bound binaries, 12 rules, zero findings/exceptions |

### WP-030 — canonical registry

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-030-T01 | Define schema for robot/node/bus/joint/actuator/sensor/CAD/calibration | 020,000-T04 | Schema + examples |
| WP-030-T02 | Import current 12 IDs, chirality, names and offsets as `unverified` | T01 | Migration report, no runtime default |
| WP-030-T03 | Resolve semantic six-joint legs vs five-joint sim and absent hip-yaw sensing | T02 | Reviewed mapping/exception |
| WP-030-T04 | Validate exact tuple, unique owner/ID/name, units, limits and source refs | T01,T03 | Negative/positive schema tests |
| WP-030-T05 | Generate firmware/host/ROS/UI/sim views and canonical hash | T04 | Reproducible generation test |
| WP-030-T06 | Reject startup/enable on view/hash mismatch | T05,070 | Admission integration test |

### WP-040 — protocol truth

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-040-T01 | Build clause ledger for X V4.4 identifiers, opcodes, fields and states | 010-T03 | Reviewed citations |
| WP-040-T02 | Record 1 Mbit/s, standard 8-byte, request/response ID domains | T01 | Protocol requirement review |
| WP-040-T03 | Resolve signedness/scales/ranges/rounding and motor/output coordinates | T01 | Unit table review |
| WP-040-T04 | Treat A1 as q-axis current; map torque only through evidenced constants | T03 | Unit/label regression |
| WP-040-T05 | Identify brake-open/state requirements and default-deny unknown tuples | T01 | Applicability decision |
| WP-040-T06 | Repeat clause/applicability analysis for V2, V3, RH, L, CEM, H, FL/FLO | 020, T01 | Per-revision ledgers; future gate |
| WP-040-T07 | Capture exact-tuple physical traces and reconcile discrepancies | 000-T04,050 | SRC-017; PHYSICAL-HOLD |

### WP-050 — codec steel thread

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-050-T01 | Define typed RMD CAN V4.4 request/response/result types | 040-T01..05 | API review |
| WP-050-T02 | Encode/decode ID domains and exact 8-byte frames without I/O | T01 | Unit tests |
| WP-050-T03 | Implement field conversion with overflow/rejection policy | T01 | Boundary/property tests |
| WP-050-T04 | Add independently transcribed official golden vectors with citations | T02,T03 | Vector review + hashes |
| WP-050-T05 | Add malformed ID/length/opcode/reserved/unexpected-response cases | T02 | Negative suite |
| WP-050-T06 | Execute same vector corpus against host and embedded-core builds | T04,T05 | Dual-run evidence |
| WP-050-T07 | Add captured vectors only after exact tuple and sanitized provenance | 040-T07 | Bench evidence; PHYSICAL-HOLD |

### WP-060 — host link

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-060-T01 | Inventory conflicting frame enums/APIs and freeze migration vectors | 000-T03 | Compatibility inventory |
| WP-060-T02 | Specify version/length/type/sequence/time/CRC and resync | 030,070 | Interface review |
| WP-060-T03 | Specify config identity, command lease, state validity and fault fields | T02 | Schema tests |
| WP-060-T04 | Specify receipt/admission/TX/response/observed-state dispositions | T02 | State/sequence tests |
| WP-060-T05 | Implement bounded parsers plus corruption/truncation/replay fuzzing | T03,T04 | Parser/fuzz evidence |
| WP-060-T06 | Negotiate versions/capabilities/rates; fail closed incompatibility | T05 | Compatibility matrix |

### WP-070 — offline safety core

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-070-T01 | Implement BOOT/DISCOVERY/DISABLED/ARMED/ENABLED/SHUTDOWN/FAULT pure state core | 020,040 | Transition table tests |
| WP-070-T02 | Implement exact lease owner/scope/expiry with fake monotonic clock | T01 | Lease boundary/wrap tests |
| WP-070-T03 | Implement ordered admission/rejection reasons and no clamping default | T02 | Admission table coverage |
| WP-070-T04 | Implement immutable intents and single-writer scheduler interface | T03 | Concurrency/property tests |
| WP-070-T05 | Latch fault context and guarded reset without auto re-enable | T01 | Fault persistence/reset tests |
| WP-070-T06 | Encode regressions for boot play mode, dual writers, all-ID ownership and bad stop IDs | T04,T05 | TST-DBR suite |
| WP-070-T07 | Prove queued command invalidation between admission and TX | T03,T04 | Race/fault-injection tests |
| WP-070-T08 | Compose typed config/bus/response/drive/limit/feedback faults into ordered bounded evidence and immediate final-TX preemption | T05,T07 | TST-SAF-005 |

### WP-080 — real transport and scheduler

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-080-T01 | Bind protocol cores to explicit real/fake transport adapters | 050,070 | Stub-success rejection tests |
| WP-080-T02 | Configure verified bit rate, standard IDs, filters and timestamps | T01 | Adapter config evidence |
| WP-080-T03 | Allocate control/read/diagnostic/safe-action slots per bus | T01,030 | Schedule analysis |
| WP-080-T04 | Correlate responses and enforce deadline/miss/retry budgets | T02,T03 | Deterministic emulator tests |
| WP-080-T05 | Measure utilization/jitter/queue depth and handle bus-off recovery | T03,T04 | SIL then HIL timing results |
| WP-080-T06 | Prove only declared owner transmits each node ID | 030, T03 | Multi-node contention test |

### WP-090 — state, sensors and limits

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-090-T01 | Decode native position/velocity/current/temp/voltage/error with validity | 050,080 | Golden + emulator tests |
| WP-090-T02 | Timestamp at RX/sample and propagate age/dropout | T01 | Fake-clock stale-data tests |
| WP-090-T03 | Version and atomically apply external encoder calibrations | 030,T02 | Calibration transaction tests |
| WP-090-T04 | Reconcile native/external sensors without hiding missing hip yaw | T01,T03 | Fusion/invalidity tests |
| WP-090-T05 | Enforce sourced limits in motor and output coordinates | 020,030,T01 | Boundary/transform tests |
| WP-090-T06 | Derive effort only for exact tuples with evidenced constants | T01,T05 | Unit/provenance tests |

### WP-100 — physical safety and staged HIL

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-100-T01 | Hazard review, current-limited unloaded fixture and independent cut | 000,170 | Approved runbook/inspection |
| WP-100-T02 | Verify discovery/disable/stop/brake/fault-clear on one exact tuple | T01,080,090 | Bench evidence bundle |
| WP-100-T03 | Inject host loss, corrupt link, bus-off, stale feedback, drive fault and limit events | T02 | Fault/latency evidence |
| WP-100-T04 | Complete thermal/timing 8-hour current-limited one-motor run | T02,T03 | Trend + acceptance result |
| WP-100-T05 | Scale schedule and ownership to one six-actuator leg | T04 | HIL timing/contention results |
| WP-100-T06 | Scale to both legs only after electrical/mechanical hazard re-review | T05 | G3 approval |

### WP-110 — host and ROS integration

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-110-T01 | Select one async transport/device lifecycle and deprecate duplicates | 060 | API/compatibility decision |
| WP-110-T02 | Implement serial, replay and emulator sessions with reconnect policy | T01 | Lifecycle/error tests |
| WP-110-T03 | Expose typed SI state/commands and structured diagnostics | T01,T02 | API conformance tests |
| WP-110-T04 | Implement ros2_control SystemInterface over the same device API | 030,T03 | Plugin lifecycle tests |
| WP-110-T05 | Reuse controller tests across replay/SIL/hardware backends | T04,130 | Cross-backend suite |

### WP-120 — Dropbear description

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-120-T01 | Inventory detailed/simplified URDF/xacro, CAD, Gazebo, Isaac and Altair authority | 000 | Provenance/duplicate report |
| WP-120-T02 | Select canonical source and generation boundary; exclude build/install artifacts | T01 | Architecture approval |
| WP-120-T03 | Map semantic six-joint legs and both-leg topology to registry | 030,T02 | Joint parity test |
| WP-120-T04 | Correct axes/origins/transmissions/limits, including min=max defects | T03,140 | Description validators |
| WP-120-T05 | Reconcile sourced inertials/collisions/sensors and detailed/simplified forms | T02,140 | Geometry/dynamics review |
| WP-120-T06 | Generate engine and ros2_control mappings with canonical hashes | T03..05 | Reproducibility/parity tests |

### WP-130 — protocol emulator

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-130-T01 | Model node identity, revision, modes and command/response state | 040,050 | Codec conformance suite |
| WP-130-T02 | Implement deterministic response delay, timeout and unexpected-frame injection | T01 | Fake-clock tests |
| WP-130-T03 | Implement drive status/error, bus and brake fault scenarios only where specified | T01 | Scenario/citation review |
| WP-130-T04 | Record/replay native traces without elevating simulator evidence | T02,T03 | Replay determinism test |
| WP-130-T05 | Run gateway scheduler/safety integration against multi-node emulator | 070,080,T01..04 | SIL protocol evidence |

### WP-140 — CAD conversion

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-140-T01 | Validate 44-model/53-variant source manifest and archive integrity | 010 | Inventory test |
| WP-140-T02 | Define conversion record, naming, units/frame and licensing schemas | 020,030 | Schema tests |
| WP-140-T03 | Preserve 26 assemblies and inventory/disposition all 27 flattened variants without semantic promotion | T01,T02 | 26 packet records + 27 inventories / 1,628 stable components |
| WP-140-T04 | Review housing/output members, origin/axis/direction/zero pose for each exact geometry configuration | T03 | signed exact-configuration reviews; currently open |
| WP-140-T05 | Produce reproducible GLB visual and collision meshes | T04 | Toolchain/hash evidence |
| WP-140-T06 | Run scale/orientation/rotation/housing-immobility/collision/render tests | T05 | 44/44 acceptance matrix |
| WP-140-T07 | Record mass/COM/inertia source or leave unsupported | T04 | Provenance review |

### WP-150 — actuator plant and model assets

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-150-T01 | Define electrical/mechanical/gear/friction/thermal/sensor/latency schema | 020,130 | Schema/unit tests |
| WP-150-T02 | Hash and digest every page of all 15 pinned product-manual occurrences with a locked extraction environment | 010,T01 | 215 page identities; one explicit no-text page |
| WP-150-T03 | Select exact product table/header/page for every model without family or latest fallback | T02 | 44 unique table bindings |
| WP-150-T04 | Preserve raw label/unit/value/bounding boxes and parse scalar/range/qualified/alternative forms | T03 | 531 deterministic candidates |
| WP-150-T05 | Suggest target/conversion only where semantics permit; retain line/phase, motor/module/output, rated/peak/no-load and range distinctions | T04 | 89 direct, 317 semantic-review, 125 unmapped candidates |
| WP-150-T06 | Bind mapped candidates to exact-model parameter/envelope handoff tasks without accepting values | T05,020 | 406 candidate-to-task references; current acceptance zero |
| WP-150-T07 | Independently review applicability, semantics, unit conversion, uncertainty and conflicts candidate by candidate | T06,040 | signed review decisions; human assignment required |
| WP-150-T08 | Materialize accepted official source facts separately from fitted and bench-measured records | T07 | immutable fact records and revocation lineage |
| WP-150-T09 | Assemble complete exact-model parameter sets only from explicitly selected compatible facts | T08 | 34 parameters + four envelopes/model; missing remains blocking |
| WP-150-T10 | Adapt a complete set into typed executable parameters only through an independently reviewed scenario/solver profile with complete source-semantic accounting | T01,T09 | V1 profile/contract schemas, deterministic registry, typed engine and adversarial tests; zero real contracts |
| WP-150-T11 | Validate against datasheet curves, then authorized bench/holdout data with declared metrics | T10 | offline comparison; physical hold |
| WP-150-T12 | Bind plant output geometry/axis to independently reviewed CAD record | T09,140 | rotation/state parity test |
| WP-150-T13 | Extend the equation/solver contract for nonzero noise, command delay/jitter, multi-rate state sampling, arbitrary feedback delay, peak-duration behavior and asymmetric bidirectional efficiency | T10 | COMPLETE-OFFLINE: versioned V2 adapter plus analytic/property/trace parity tests |

### WP-160 — whole-robot digital twin

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-160-T01 | Benchmark candidate engines with fixed robot/controller/contact scenarios | 120,150 | Reproducible benchmark/ADR |
| WP-160-T02 | Integrate canonical description, sensors and ros2_control backend | T01,110 | Schema/interface parity |
| WP-160-T03 | Remove authority from duplicated/generated descriptions and pin third parties | 120,T02 | Provenance/build test |
| WP-160-T04 | Validate kinematics, dynamics, contacts, state estimation and deterministic replay | T02 | SIL-robot evidence |
| WP-160-T05 | Run identical joint/controller tests across rigid-body, plant and gateway HIL | T02,100 | Cross-backend error report |
| WP-160-T06 | Connect browser to GLB catalog and recorded/live typed telemetry | 140,T02 | UI asset/telemetry tests |
| WP-160-T07 | Compose a synchronized twelve-axis V2 plant bank below the canonical robot boundary with atomic all-axis batches, rollback, fail-stop and replay | 150 | 14 focused tests and pinned synthetic trace; no graph/rigid-body/shared-bus fidelity |

### WP-170 — security and operations

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-170-T01 | Maintain threat model for physical command/config/update/evidence paths | 000,060 | Threat assessment reviews |
| WP-170-T02 | Define device/operator/service identities, roles and local recovery | T01 | Authorization matrix tests |
| WP-170-T03 | Disable remote actuation by default; enforce lease/safety admission after auth | T02,070 | Negative integration tests |
| WP-170-T04 | Add signed/integrity-checked config, calibration and firmware update/rollback | T01,030 | Tamper/rollback tests |
| WP-170-T05 | Bound/audit diagnostics without secrets or real-time starvation | T02,080 | Log review/load test |
| WP-170-T06 | Create bench, incident, fault-recovery and evidence-retention runbooks | T01..05 | Dry-run records |

### WP-180 — verification and release system

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-180-T01 | Implement one command for firmware compile, host/web/protocol/safety/catalog tests | releasable WPs | Machine-readable run summary |
| WP-180-T02 | Validate requirement/ADR/WP/test/evidence cross-links and orphan IDs | T01 | Trace linter result |
| WP-180-T03 | Emit immutable evidence manifests with environment/tool/code/config identity | T01 | Schema validation |
| WP-180-T04 | Enforce offline/SIL/bench/HIL classification and stale dependency invalidation | 020,T03 | Claim/evidence negative tests |
| WP-180-T05 | Gate whitespace, generated diffs, preserved user work, licenses and unsupported claims | T02..04 | Release checklist |
| WP-180-T06 | Publish requirement and model-capability coverage dashboards | T02..05 | Source-bound JSON/HTML dashboard; complete offline, release approval remains separate |
| WP-180-T07 | Prepare and publish the completed provenance-, license- and secret-reviewed release to the confirmed public GitHub repository | T01..06, all releasable WPs | Clean release candidate, public remote identity, pushed tag/commit and independently fetched verification |

### WP-190 — control and behavior release

| Task | Deliverable / objective | Depends | Evidence |
|---|---|---|---|
| WP-190-T01 | Establish estimator inputs/validity and controller timing/error budgets | 160,100 | Replay/SIL/HIL results |
| WP-190-T02 | Validate joint, impedance and whole-body controllers without native bus access | T01 | Cross-backend suite |
| WP-190-T03 | Validate gait/planner interfaces, constraints and safe transition requests | T02 | SIL scenarios |
| WP-190-T04 | Integrate authenticated operator/diagnostic workflows through host API | 170,T02 | Authorization/safety tests |
| WP-190-T05 | Stage current-limited robot trials under approved G7 procedure | 100,T01..04 | Physical robot evidence |
| WP-190-T06 | Release only exact evidenced configurations and retain rollback | 180,T05 | Signed release record |

## Immediate P0–P1 critical path

The offline foundations for WP-020, WP-030, WP-040/050, WP-060, WP-070 and
WP-130 now have executable evidence, and the bounded offline portion of WP-080
and lifecycle/replay portion of WP-110 are active. Partial status is
intentional: claim generation, authenticated real adapters, real bus outcomes,
broader property exploration and physical applicability remain open.

The Iteration 4 steel thread joins typed Python host intent -> native V1
session -> exact config/safety checks -> bounded fake scheduler -> V4.4
protocol emulator. It preserves separate receipt/admission/TX/response/
observation dispositions and proves queued config/lease/fault invalidation.
The next dependency-ready campaign is the joined WP-140/WP-150 human review:
resolve exact housing/output/axis semantics for all 53 STEP configurations and
independently convert the 531 page-bound product-spec candidates into selected
source facts. No model can advance from `UNSUPPORTED` until its actual output
member, transform, axis, units and complete compatible plant set are reviewed.
WP-090 may continue using unknown-valued fixtures, but it cannot invent
physical limits, calibration or product dynamics.

In parallel, the unpowered discovery path may collect—but never infer—
WP-000-T04..05/SRC-016 inputs under an approved procedure. No powered work,
HIL, output-shaft articulation, plant accuracy or physical firmware
applicability is credited at this gate.

## Iteration 16 evidence snapshot

| Slice | Offline evidence | Remaining boundary |
|---|---|---|
| WP-150 full-content acquisition | All 15 pinned PDF occurrences and 215 pages are hashed; extraction is local and locked to Poppler `pdftotext` 24.02.0 `-bbox-layout` | vendor revision change control and independent applicability review |
| WP-150 exact table selection | 44/44 catalog models have one exact page/table/header binding across nine product sheets; no family fallback | human verification of applicability to exact model/hardware/firmware |
| WP-150 candidate registry | 531 candidates preserve coordinates, raw labels/units/values and structured scalar/range/qualified/alternative forms | 89 direct mappings still need review; 317 semantic blockers need resolution; 125 values need disposition |
| WP-150 handoff integration | All 406 mapped candidates are referenced by exact parameter/envelope tasks across the 44 plant packets | all 17 roles unassigned; accepted candidates/facts/sets remain zero |
| WP-150 runtime adapters | V1 conservatively accounts for all 38 source semantics; V2 exactly adds rational multirate capture, arbitrary delay, counter noise/jitter, directional efficiency, one-shot peak, separate thermal limits, deadline/order and complete replay state; both require independent human profiles, emit hash-bound typed contracts and join registry V4/simulator/session/trace | tracked V1/V2 profiles/contracts/loadable models remain zero; real review and physical correlation remain open |
| WP-160 twelve-axis composition | One exact-clock V2 plant per observed actuator slot, deterministic per-axis seeds, all-axis command/load closure, aggregate current admission, forced transaction rollback, bank thermal fail-stop, complete snapshot and pinned trace | synthetic only; canonical graph, rigid body, shared power bus, exact model and physical correlation remain absent |
| WP-020/180 claim-surface audit | Exact 20-root scope hashes 674 text/JSON surfaces and 566 binaries; nine lexical plus three structured rules reject family/acquisition/build/simulation/physical promotion with zero exceptions | static misuse control only; semantic review, support evidence and all physical gates remain separate |
| WP-070 fault and event properties | 314 supervisor, 216 fault-context, 596 six-source monitor and 8,218,041 composed event checks cover bounded context, corrupt/missing restart denial, fixed-priority config/bus/response/drive/limit/feedback arbitration, reconnect/reload retention, explicit reset to BOOT, and final-TX denial across 4,789 deterministic state/lease/config/fault/transport/time sequences | trusted observation plus durable storage/audit adapters, UTC binding, exact-tuple safe-action observation and physical cut remain open |
| WP-180 non-promotion gate | The candidate, lifecycle, assembly, both runtime-adapter/plant layers, twelve-axis synthetic bank, claim-surface audit and safety properties are separately cataloged and staged | the 81-stage fault-evidence source state passed twice with identical 741-file manifest/diff identities; event-property expansion, release signature, public publication and all human/physical evidence remain open |

## Iteration 11 evidence snapshot

| Slice | Offline evidence | Remaining boundary |
|---|---|---|
| WP-030 source lifecycle V2 | Strict submission/event/registry schemas, deterministic accept/reject/revoke/atomic-supersede replay, independent human approver rules and 17 focused tests | tracked submissions/events/active source remain 0; independent decisions required |
| WP-120 structured graph V2 | Frames, expressed-in transforms/axes, aliases, chirality, symmetry, affine coupling domains, singularities, physical/simulator closure, DOF/ownership/dependency ledgers and lifecycle replay | 161 real questions unresolved; graph submissions/active graph/mappings remain 0 |
| WP-110 lifecycle consumers | Four hash-parity host/ROS/simulator/UI projections and typed API generation tokens; synthetic revoke/supersede invalidates mappings, sessions and handles | no real URDF/transmission/plant/joint handle is materialized |
| WP-080 adapter intake | Exact TWAI/MCP2515-neutral manifest, independent physical/controller TX-disable facts, timing/queue/timestamp/loss/error-state checks and permanently disabled physical factory | controller/transceiver/pins/clock/driver are not observed or selected; no I/O |
| WP-000/100 discovery | Visual-only U0 authorization request, role assignment and evidence-custody ledger prepared | all physical actions unauthorized; asset/location/window/people/zero-energy evidence absent |
| WP-180 unified gate | 57 ordered stages, 77 requirements, 122 catalog tests and 23 critical artifact bindings | physical evidence classes, release signing and coverage dashboard remain open |

## Iteration 2 evidence snapshot

| Slice | Offline evidence | Remaining boundary |
|---|---|---|
| WP-020 exact support | 27 support tests plus ten claim-surface tests; six-field exact keys, hardware evidence floor, dependency validity/staleness, 44 catalog-only denials and zero family/build/acquisition promotion across 674 text/JSON surfaces | physical exact tuples and human evidence |
| WP-030 canonical registry | Draft 2020-12 schema, canonical digest, explicit 12-joint/10-encoder incomplete observation, 23 tests | physical topology/tuples/limits/calibration/CAD; generated views and startup integration |
| WP-130 protocol emulator | 22 tests; shared V4.4 vectors, multi-node virtual time, drop/delay/unexpected/drive-fault injection, replay | ESP32 scheduler/safety adapter; bus-off and physical behavior; all plant dynamics |
| WP-180 unified gate | support/emulator/schema suites added to `tools/test_all.sh` | immutable environment manifest, coverage dashboard, release automation |

## Iteration 3 evidence snapshot

| Slice | Offline evidence | Remaining boundary |
|---|---|---|
| WP-030 generated views | Five lossless layer projections, firmware C++17 projection, manifest, atomic generator and 15 tests | physical facts; signed loader; actual runtime consumers; ESP32 toolchain impact |
| WP-060 host-link V1 | 44 tests; 72-byte bounded header, typed bodies, CRC-32C resync, negotiation, session/order/config/expiry denial, seeded fuzz | native C++ implementation, shared vectors, authenticated session, transport binding |
| WP-070/170 config identity | 139 native checks; external validation gates, atomic generation-bound stage/commit, rollback, revoke, exact arm/TX reference and safety composition | secure loader/token/counters/time; adapter and physical safe action |
| Cross-layer non-promotion | Generated incomplete digest reaches the link exactly, remains `motion_authorized=false`, and is rejected by the native motion guard (4 Python tests + 75 native checks) | complete reviewed config and all physical authorization gates |
| WP-180 unified gate | dependency pins and all Iteration 3 suites run from `tools/test_all.sh` | immutable environment/toolchain manifest and release dashboard |

## Iteration 4 evidence snapshot

| Slice | Offline evidence | Remaining boundary |
|---|---|---|
| WP-060 native host-link V1 | 32 reproducible Python/native accept/reject vectors; all seven typed bodies; 2,472 GCC ASan/UBSan and Clang checks; allocation/exception audit | authenticated transport/session establishment; target memory/WCET measurement; persistent replay defense |
| WP-070/080 gateway core | 658 native checks; fixed routes/queues/correlation/disposition ring; last-moment config+safety checks; diagnostic budget; safety-action priority | real transport send result/RX, retry, arbitration loss, bus-off recovery, utilization and HIL |
| WP-110 host gateway session | 28 deterministic async fake-adapter tests; bounded lifecycle, negotiation, command correlation, reconnect without lease restore, capture/replay | serial/USB/TCP adapter, OS discovery/backoff, authentication, legacy API migration and ROS integration |
| WP-130 native emulator steel thread | Six cases join Python V1, native session/config/safety/scheduler and V4.4 emulator for synthetic success, tracked-config denial, drop, delay, unexpected node and drive-fault injection | tracked exact tuple remains denied; no real bus, physical telemetry, plant or mechanical observation |
| WP-170 authorization/audit | Seven closed roles, ten actions, 37 Python/native vectors, exact generation/lease/safety checks, default physical/remote denial, independent activation review, replay consumption and isolated bounded safe-disable audit lane | credential/transport authentication, keys, signed update verification, persistent replay, durable audit, gateway call-site and operations/HIL evidence |
| WP-170 platform trust/artifacts | Exact PlatformIO 7.0.1, Arduino-ESP32 package, ESP-IDF 4.4.7, sdkconfig and partition hashes; positive-capable independent profile selection; seven separated key purposes; 48 shared Python/native stage/commit/abort/reboot vectors; 496-byte allocation-free engine | tracked Secure Boot/flash encryption/boot anti-rollback/NVS/roots/keys/adapters all unselected or disabled; actual verifier, encrypted durable state/audit, OTA/power-loss tests and provisioning evidence |
| ESP32 integration check | New host-link and gateway cores compile in the existing ESP32 environment; 22,360 B RAM and 299,213 B flash reported in this build | cores are not wired into the user runtime; target stack/WCET and environment-family matrix remain open |
| WP-180 unified gate | Iteration 4 native/session/gateway/steel-thread suites are registered in `tools/test_all.sh` | immutable environment/toolchain manifest, evidence schema/dashboard and release automation |

## Iteration 5 foundation snapshot

| Slice | Offline evidence | Remaining boundary |
|---|---|---|
| WP-140 exact source inspection | 53/53 source-bound lexical reports, 48 unique hashes, five duplicate groups, assembly relations/member-name candidates and explicit 52 mm / one m unit candidates | lexical evidence cannot select output, axis, transformed bounds or scale acceptance |
| WP-140 review/support ledger | V2 strict schema and 13 tests cover 53 exact variants/configurations and 44 models, unit/frame/axis/member/export/license gates and default 0/44 denial | signed human/visual housing-output reviews and canonical selections for every exact configuration |
| WP-140 conversion toolchain | CadQuery 2.8.0 / OCCT 7.9.3.1, 44 exact package+wheel pins, explicit mm-to-m GLB scaling and synthetic two-link STEP/GLB articulation proof | per-model semantic selections, deterministic real exports and redistribution decisions |
| WP-140 real-source import | 53/53 valid kernel imports; 48 variants contain closed solids; X6-8 pair, CEM-25, CEM-45 and FL-85-23 are shell-only | member-preserving assembly/partition workflow; healing evidence for shell-only sources; 0/44 accepted |
| WP-140 candidate review campaign | 26/26 source-bound assembly packets and 27/27 flattened inventories; 1,628 stable topology components; all local images hashed and all heuristic authority false | signed member/axis decisions; five shell heal/re-source reviews; accepted exports/articulation remain 0/44 |
| WP-140 real candidate export pilot | X12 hypothesis yields occurrence-preserving 12-leaf housing / six-leaf output STEP, metre GLB and -30/0/+30 output-only articulation; three tests prevent unresolved candidate promotion | resolve five member/origin/sign questions, obtain independent review, then rebuild as accepted-local or reject; support remains 0/44 |
| WP-140/160 consumer enforcement | Generated web registry covers 44 models/53 variants/53 exact configurations, agrees with empty Dropbear CAD bindings and exposes 0 assets; browser candidate and toy-plant promotion tests pass | accepted artifact publication path and real rigid-body consumer remain OPEN |
