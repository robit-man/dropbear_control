# Iteration 10 plan — reviewed robot graph authority and denial-only consumers

- Iteration status: `COMPLETE-OFFLINE-GRAPH-AUTHORITY-DISCOVERY-READY`
- Phase context: P2 elaboration, WP-030/WP-110/WP-120/WP-140/WP-160/WP-180
- Delivery track: Iteration 10 graph decision/admission work
- Discovery track: Iteration 11 unpowered installed-discovery and physical
  adapter readiness
- Entry gate: Iteration 9 machine run `e9fd46830d230147971da6a1`, 47/47 stages
  PASS, 77 requirements, 113 catalog tests and 48 validated links
- Candidate graph baseline: 198 paths, 96 objects, 161 unresolved questions,
  zero canonical source selections and zero ROS-actuator mappings
- Physical baseline: installed tuples/routes/calibrations 0/12, real plants
  0/44, accepted CAD 0/53, supported models 0/44
- Safety boundary: no automatic graph answer, physical adapter selection,
  powered movement, CAN TX, calibration movement, HIL or robot enable

## Iteration outcome

Iteration 10 separates observed robot-description content from human-reviewed
authority. It defines hash-bound source-selection and graph-decision records,
validates complete decisions transactionally, and admits a canonical graph
only when all required identities, edges, couplings, loop closures and
actuator/observation roles are explicit and internally consistent.

The current repository has no submitted graph reviewer decision. Therefore
all production ROS, host and simulator projections remain denial-only with
zero mappings. Synthetic graphs may exercise positive algorithms but cannot
answer Dropbear questions or populate physical readiness.

In parallel, Discovery prepares Iteration 11's unpowered installed-inventory,
CAN-controller selection and listen-only campaign artifacts without executing
physical work.

## Delivery Track A — independent CAD evidence carry

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I10-A01 | Re-hash X12 workbench carry | Candidate/template/workbench/source hashes reproduce |
| I10-A02 | Poll only for submitted decision | Absence remains explicit; no automated reviewer substitution |
| I10-A03 | Validate any submission transactionally | Reviewer independence, occurrence partition, frame/axis and hashes all pass before ledger mutation |
| I10-A04 | Preserve separation | A CAD acceptance changes one exact configuration only and grants no graph/motor/plant/motion support |
| I10-A05 | Prepare next cohort only after valid human result | No bulk semantic inference or self-signing |

## Delivery Track B — source-authority decision contract

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I10-B01 | Exact decision subject | Bind repository URL, commit, tree ID, inventory path/hash/schema and canonical configuration digest |
| I10-B02 | Closed source roles | Declare kinematic, visual, collision, inertial, ros2-control, Gazebo constraint and controller roles separately |
| I10-B03 | Exact file selections | Each role lists exact path, Git object ID, SHA-256 and logical key; no glob/family/default |
| I10-B04 | Candidate/derivative rule | Install/build derivatives cannot be primary source; expanded URDF needs its source transform and generator provenance |
| I10-B05 | Divergence disposition | Every selected divergent logical group is explicitly choose/amend/reject with rationale |
| I10-B06 | Completeness | Every required role is selected or explicitly declared unavailable; silent omission denies |
| I10-B07 | Reviewer authority | Identified human reviewer, organizational independence, review time, rationale and signature/reference are mandatory |
| I10-B08 | Automation boundary | Automation may prepare/validate but cannot be author, reviewer or approver |
| I10-B09 | Lifecycle | Draft/submitted/accepted/rejected/revoked states, supersession and invalidation are explicit |
| I10-B10 | Integrity | Canonical record digest covers every field and all selected object hashes |
| I10-B11 | Empty baseline | Generate a complete unanswered template but zero accepted source-authority records |

## Delivery Track C — graph decision and review packet

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I10-C01 | Bind question universe | Decision references exactly one inventory hash and all 161 stable question IDs |
| I10-C02 | Define canonical nodes | Stable link/joint IDs, aliases, chirality, semantic role and source observation references |
| I10-C03 | Joint semantics | Type, parent, child, origin, normalized axis, positive direction, coordinate frame and zero convention are explicit |
| I10-C04 | Activity classification | Every joint is active, passive, mimic, coupled, fixed or simulator-only with rationale |
| I10-C05 | Actuator edges | Each of 12 canonical actuator IDs maps to an exact graph edge or explicit multi-edge coupling; no order/name guess |
| I10-C06 | Observation edges | External/native/synthetic observation roles map explicitly; both missing hip-yaw external roles remain representable |
| I10-C07 | Coupling equation | Ratio/sign/offset/domain/independent coordinates and singularity conditions are explicit but not physical calibration |
| I10-C08 | Mimic constraints | Driver/driven direction, multiplier, offset and source evidence are explicit |
| I10-C09 | Closed-chain constraints | Loop endpoint, closure type, independent coordinate, solver responsibility and physical counterpart are explicit |
| I10-C10 | Simulator-only edges | Gazebo closures cannot leak into physical kinematic authority |
| I10-C11 | Active/passive ownership | Exactly one command owner and one state source policy per active coordinate |
| I10-C12 | Cardinality reconciliation | Six actuators/five ROS commands per leg is explained with no orphan or duplicate ownership |
| I10-C13 | Symmetry policy | Left/right equality or intentional difference is explicit; mirror inference is prohibited |
| I10-C14 | Limit/calibration references | Graph contains stable dependency slots only; it cannot invent bound or calibration records |
| I10-C15 | CAD binding references | Housing/output/origin/axis binding IDs are dependencies, never mesh-name guesses |
| I10-C16 | Reviewer answers | Every inventory question has answer, rationale, evidence IDs and disposition |
| I10-C17 | Review packet | Local packet groups source, cardinality, actuator, mimic and loop questions into bounded cohorts |
| I10-C18 | No-network workbench | Embedded evidence and exact template export; no external calls or hidden autofill |
| I10-C19 | Independent approval | Human graph/mechanical reviewer identity and independent approval required |
| I10-C20 | Empty baseline | No submitted decision exists; all 161 questions remain unresolved |

## Delivery Track D — canonical graph admission and invariants

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I10-D01 | Transactional loader | Validate schema, record digest, source objects, inventory/config hashes and reviewer authority before exposure |
| I10-D02 | Exact ID uniqueness | Link, joint, coordinate, actuator, sensor, alias and constraint IDs are unique in their domains |
| I10-D03 | Endpoint closure | Every parent/child/mimic/coupling/loop reference resolves exactly |
| I10-D04 | Tree versus loop partition | Base tree has one root and no cycle; every additional loop edge is declared exactly once |
| I10-D05 | Axis/origin validity | Finite rigid transforms and normalized nonzero axes; fixed joints have no active axis |
| I10-D06 | DOF accounting | Independent, dependent, passive and simulator-only coordinates reconcile algebraically |
| I10-D07 | Actuator coverage | Exactly 12 canonical actuators covered once under explicit coupling rules |
| I10-D08 | ROS command coverage | Every ROS joint maps or is explicitly passive/uncommanded; no unresolved five/six edge |
| I10-D09 | Observation coverage | Required feedback policy declares missing/optional/required sources without alias |
| I10-D10 | Ownership | One writer per command coordinate and no planner/simulator/diagnostic bus bypass |
| I10-D11 | Dependency closure | CAD/calibration/limit/route dependencies exist and match exact graph subjects before positive readiness |
| I10-D12 | Synthetic positive fixture | A small clearly synthetic tree plus mimic/closed-loop variants proves algorithms only |
| I10-D13 | Mutation suite | Cycles, disconnected nodes, duplicate ownership, orphan edges, axis/transform errors and hash drift deny |
| I10-D14 | Empty physical registry | With no accepted decision, canonical Dropbear graph count and runtime mapping count remain zero |

## Delivery Track E — denial-only host, ROS and simulator projections

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I10-E01 | Generated graph status | Exact per-actuator/joint blockers join source and graph decision state |
| I10-E02 | Host query boundary | Exact IDs only; incomplete graph returns typed denial and no transform/mapping object |
| I10-E03 | ROS projection | Emit status/blockers only; no URDF, transmission or ros2_control hardware mapping from candidates |
| I10-E04 | Simulator projection | Candidate topology is inspectable but cannot become rigid-body authority |
| I10-E05 | Readiness integration | Add source-authority/graph dependencies without changing 0/12 readiness or V1 semantics |
| I10-E06 | Browser redaction | Expose counts/questions/status without local paths or physical claims |
| I10-E07 | Generator ownership | Each projection owns an exclusive namespace and fails on stale/unexpected files |
| I10-E08 | Cross-view parity | Host/ROS/sim/UI status views agree on digest, counts, blockers and zero mappings |

## Delivery Track F — Dropbear hardware API contract

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I10-F01 | API identity | Canonical config/graph generation/session/lease and exact actuator IDs required |
| I10-F02 | Command surface | Time-bounded typed joint intents only; no vendor bytes, native IDs or raw effort ambiguity |
| I10-F03 | State surface | Position/velocity/current/effort presence, source, ages, validity, fault and provenance remain distinct |
| I10-F04 | Graph dependency | No command handle exists until accepted graph plus readiness dependencies resolve |
| I10-F05 | Backend identity | Replay, protocol emulator, synthetic plant, rigid-body candidate and physical adapter remain distinct |
| I10-F06 | Fail-only physical default | Missing concrete adapter cannot claim connect/send/read success |
| I10-F07 | Fake lifecycle tests | Configure/activate/deactivate/cleanup/fault/reconnect and cancellation preserve safety state |
| I10-F08 | No runtime wiring | Contract and fake consumers only; preserved user ESP32 main and ROS package remain untouched |

## Delivery Track G — unified verification and handoff

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I10-G01 | Catalog and trace | Every new suite has requirement/WP/gate mapping and exact count |
| I10-G02 | Machine evidence | Gate hashes new source/graph/projection artifacts and retains zero physical claims |
| I10-G03 | Normal/adversarial tests | Strict schema, semantic, digest, source drift and promotion mutations pass |
| I10-G04 | Full repository gate | All stages, web, host/native, ESP32 compile and whitespace pass |
| I10-G05 | Verification report | Counts, hashes, external carries and non-claims reconcile exactly |
| I10-G06 | Discovery handoff | Iteration 11 artifacts meet Definition of Ready without authorizing physical execution |

## Discovery Track — Iteration 11 unpowered physical-readiness package

| ID | Discovery item | Definition of Ready |
|---|---|---|
| I10-X01 | Installed-inventory schema | Exact robot/controller/transceiver/motor serial tuple, bus/node/connector and evidence fields reviewed |
| I10-X02 | Discovery capture tool design | Read-only import/validation path, no command capability, append-only evidence and operator confirmation |
| I10-X03 | Controller decision matrix | ESP32 TWAI versus external MCP2515 facts, pin/timing/filter/state/loss/TX-disable capabilities and unknowns explicit |
| I10-X04 | Listen-only runbook | Power state, isolation, termination, ground, TX hardware disable, rollback and abort criteria reviewed |
| I10-X05 | Capture acceptance | Timestamp/loss/load windows and exact source/applicability comparison procedure defined |
| I10-X06 | Independent power survey | E-stop/power-removal owner, state feedback, measured latency plan and failure modes documented |
| I10-X07 | Calibration campaign template | Per-joint fixture/reference/current/travel/operator/reviewer/invalidation steps defined but not executed |
| I10-X08 | Limit campaign template | Vendor/software/measured/derate evidence collection and conservative staged movement plan defined |
| I10-X09 | CAD output-shaft cohorts | Prioritize assembly variants and flattened re-source/heal candidates for independent review |
| I10-X10 | Real plant intake | Exact parameter-source/uncertainty/envelope/correlation acceptance checklist defined |
| I10-X11 | HIL matrix | One actuator to six-actuator leg progression, injected faults, deadlines and stop criteria defined |
| I10-X12 | Required authorization list | Identify which tasks require hardware owner, safety reviewer, operator and physical workspace approval |

## Dependency order

1. B01..B11 establishes source authority meaning.
2. C01 consumes the immutable inventory; C02..C16 defines decision semantics;
   C17/C18 packages review; C19 is external; C20 keeps baseline empty.
3. D01 consumes accepted B/C decisions; D02..D11 validate; D12/D13 prove with
   synthetic data; D14 preserves zero canonical Dropbear graphs.
4. E01 consumes D status; E02..E08 are denial-only until D admits a graph.
5. F01..F08 consumes E status and existing host/gateway contracts without
   wiring physical output.
6. G01..G06 closes delivery only after stable generators and tests.
7. Discovery X01..X12 proceeds one iteration ahead and cannot execute hardware.
8. A01..A05 remains asynchronous and grants no graph or motor authority.

## Hazard ledger

| Hazard | Unsafe shortcut prohibited | Required control |
|---|---|---|
| H10-01 derivative authority | Select committed install file because it is runnable | Exact primary-source decision with reviewer and generator provenance |
| H10-02 duplicate consensus | Treat repeated identical blobs as corroboration | Duplicate relation is provenance only |
| H10-03 detailed/simplified merge | Merge same logical filenames field-by-field | Explicit choose/amend/reject per divergent group |
| H10-04 five/six ordering guess | Zip ROS and actuator arrays | Reviewed edge/coupling decision per actuator |
| H10-05 mimic means actuator | Assume mimic joint is driven or passive | Explicit activity, driver, equation and ownership |
| H10-06 Gazebo loop leakage | Promote simulator closure to physical graph | Separate simulator-only classification and physical counterpart evidence |
| H10-07 mirror inference | Copy left answers to right | Explicit symmetry decision and per-side evidence |
| H10-08 graph as calibration | Treat origin/axis/coupling observation as physical zero/ratio | Calibration remains exact separate dependency |
| H10-09 synthetic promotion | Use positive fixture to answer Dropbear questions | Synthetic subject/evidence class and zero runtime mapping |
| H10-10 API bypass | Expose handles before graph/readiness admission | Fail-only factory and exact dependency checks |
| H10-11 physical discovery creep | Execute listen-only or power survey from offline plan | Separate authorization hold and no physical calls |
| H10-12 generator collision | Share output roots | Exclusive producer namespace and unexpected-file tests |

## Iteration gates

- G10.1: source-authority schema/template/validator is strict; accepted count 0.
- G10.2: graph-decision schema covers all 161 questions and all 12 actuators;
  submitted/accepted count 0.
- G10.3: canonical graph admission passes synthetic properties and denies the
  incomplete Dropbear baseline with zero mappings.
- G10.4: host/ROS/simulator/UI projections agree and materialize no runtime
  graph facts.
- G10.5: hardware API fake/fail-only lifecycle passes and cannot bypass graph
  or readiness.
- G10.6: Iteration 11 discovery package meets Definition of Ready while every
  physical action remains unauthorized.
- G10.7: machine report, traceability, generated drift, full tests, ESP32
  compile and whitespace pass.

## Definition of Done

- [x] Source candidates and derivatives have an independently reviewable
  authority decision contract with no accepted baseline record.
- [x] All 161 graph questions and 12 actuator edges have strict review
  semantics and no automated answers.
- [x] Canonical graph admission is transactionally tested with synthetic
  fixtures and exposes zero Dropbear runtime mappings.
- [x] Host/ROS/simulator/UI consumers remain exact and denial-only.
- [x] Dropbear hardware API contract cannot exist without graph/readiness
  admission and has no physical success default.
- [x] Independent CAD work is applied exactly or carried explicitly.
- [x] Iteration 11 discovery artifacts are ready but no physical work occurs.
- [x] Unified gate and Iteration 10 verification report are green.

## Closure evidence

- Source authority: seven roles and 29 divergent groups represented; zero
  submissions or accepted selections.
- Graph authority: 161 questions in ten review cohorts; synthetic tree,
  mimic, physical closed-chain and simulator-only closure admission proven;
  zero real submissions, canonical graphs or mappings.
- Consumer parity: four hash-bound denial views; zero transforms, URDF,
  transmissions, authoritative plants, command handles or UI paths.
- Hardware API: exact graph/config/session/generation/actuator/lease/deadline
  boundary; offline lifecycle/fault/reconnect tests pass; physical adapter has
  no success path.
- Iteration 11 discovery: twelve empty installed slots and seven reviewable
  runbooks; zero submitted inventories, selected controllers or authorized
  actions; execution remains false.
- Verification: 77 requirements, 118 catalog entries, 48 checked links and
  52/52 full offline gate stages passed in the pre-closure run; the canonical
  rerun is recorded in `generated/verification/offline_gate_report.json`.

## Explicit V1 carries

Completion means the denial-first V1 steel thread is closed; it does not imply
that every positive production feature listed in the atomic backlog exists.
The next graph-authority revision still needs:

- positive accepted/rejected/revoked registry lifecycle and supersession
  processing after real submissions exist;
- structured aliases, chirality/symmetry policy and coordinate-frame metadata
  beyond the current exact canonical IDs and parent-frame convention;
- structured coupling domains, singularity conditions and algebraic DOF
  accounting beyond the current equation/evidence plus ownership checks;
- positive CAD/calibration/limit/route dependency closure; and
- ROS, rigid-body and physical runtime integration after real graph admission.

These carries cannot weaken the V1 denial status or be filled by inference.
