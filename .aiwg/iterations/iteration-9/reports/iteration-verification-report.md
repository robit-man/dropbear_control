# Iteration 9 verification report — authoritative observation, evidence admission and Dropbear graph denial

- Iteration disposition: `COMPLETE-OFFLINE-WITH-EXTERNAL-CARRIES`
- Verification date: 2026-07-22 America/Los_Angeles
- Unified gate: `PASS`, run `e9fd46830d230147971da6a1`
- Machine report SHA-256:
  `c41b143492a3f3b54ca4460adf1a30350cfdd39d638d5bbf361eb5eee5753ef8`
- Evidence boundary: specification, offline static/unit/build checks,
  deterministic host/native tests, synthetic SIL and ESP32 compile only
- Hardware capture, physical calibration, bench, HIL and robot motion: not
  performed

## Delivered and verified

### Exact-subject calibration evidence

- A strict immutable registry binds robot hardware revision, canonical
  joint/actuator, installed serial and exact model/hardware/firmware/protocol/
  transport/control tuple, bus/node, sensor and canonical configuration.
- Coordinate and wrap semantics, procedure, fixture, calibrated tools,
  operator, independent reviewer, timestamps, environment, measurements,
  uncertainty, residual, pass criteria, validity and invalidation are
  mandatory.
- Nested record/root digests, lifecycle and linear supersession are verified.
  Selection is by exact record ID; there is no latest, family, neighboring
  joint or synthetic-to-physical fallback.
- Eleven tests pass. The tracked physical registry contains zero records,
  accepted physical calibration remains 0/12 and motion remains false.

### Provenance-bound limit selection

- Vendor rating, software command, measured robot and generation-bounded
  runtime derate evidence remain separate provenance classes.
- Every bound carries exact subject/configuration, coordinate, direction,
  mode, unit, envelope, source/reviewer/validity and generation dependencies.
- Explicit record sets require every requested class/direction. Lower bounds
  select the maximum, upper bounds the minimum and magnitudes the minimum.
  Missing class/direction, stale generation, wrong identity/envelope/unit/
  frame/mode or an empty intersection returns a typed denial.
- Eleven tests pass. The tracked physical limit registry is empty, measured
  records remain zero and motion remains false.

### Allocation-free joint observation and host/native parity

- A portable C++11 core converts raw external, native-motor, native-output and
  explicitly synthetic observations only through an exact admitted
  calibration snapshot.
- Sample and receive freshness are separate. Identity, source kind, unit,
  evidence class, validity, sequence, sample/RX time and calibration
  generation must agree and progress monotonically.
- External-only, native-only and require-both preference are explicit. There
  is no averaging or fallback; missing input, aliasing and disagreement deny.
- Exact provenance-bound inclusive position snapshots reject missing,
  contradictory, stale or wrong-identity limits.
- Python and native C++ consume the same canonical 39-case JSONL corpus and
  assert numeric enum parity. Repeated replay is deterministic and denied
  samples do not advance stream state.
- Normal, ASan/UBSan, allocation-symbol and ESP32 compile lanes pass. The core
  remains intentionally unwired from the preserved user `main.cpp`.

### Per-actuator Dropbear readiness boundary

- A deterministic denial-only V1 joins the canonical configuration,
  reconciliation, calibration registry and limit registry by exact digest and
  source hash.
- Each of 12 exact actuators exposes 13 dependencies: configuration,
  installed identity, protocol applicability, exclusive route, calibration,
  complete limits, external feedback, native telemetry, feedback policy, CAD,
  ROS mapping, independent safe power and HIL.
- Both hip-yaw rows preserve missing external feedback. Ten other external
  sensor roles remain unverified observations.
- Installed tuples, routes, calibration IDs, limit IDs, feedback policies,
  CAD bindings and ROS mappings are structurally absent. All rows and the
  global gate remain motion false.
- Eight generator/consumer/adversarial tests pass. Unknown and family-like
  actuator queries never fall back.

### Pinned robot-description evidence inventory

- The inventory reads Git objects, not sparse working-tree content, from
  Dropbear commit `13cf5ecaa39b8b89c794fe905dcea0490cfa7726`.
- It covers 198 relevant URDF/xacro/controller paths and 96 unique objects:
  120 source candidates, seven expanded URDF candidates, 71 install
  derivatives and zero matching build-description files.
- Sixty-five exact-content groups and 44 repeated logical groups are
  explicit; 29 logical groups diverge across detailed, simplified, Gazebo,
  RViz or generated surfaces.
- Unique-object observations retain link/joint/type/parent/child/axis/origin,
  mimic, transmission/ROS-control, controller, mesh, macro and plugin tokens.
- The generator emits 161 unresolved review questions: 12 actuator mappings,
  two six-actuator/five-ROS-joint cardinality questions, 112 mimic/coupling
  edges and 35 Gazebo loop-closure candidates.
- Eight tests independently re-read all pinned objects and reject authority,
  mapping or motion promotion. No description is selected as canonical and
  runtime ROS-actuator mappings remain zero.

### Atomic machine gate evidence

- The gate now writes canonical schema-validated JSON before, during and
  after execution.
- It binds Git/diff/source-manifest identity, canonical configuration,
  toolchain versions, seven key artifact hashes, evidence class and fixed
  physical/support/CAD/plant/Dropbear claim invariants.
- Each stage is written before execution and finalized with its result and
  exit code. Seven focused tests prove a failed stage retains prior passes and
  cannot finalize as PASS.
- The completed report contains 47 contiguous PASS stages, zero failure
  metadata and exit code zero. UTC runtime was
  `2026-07-23T06:19:00.795Z` through `2026-07-23T06:20:25.213Z`.

## Gate matrix

| Iteration gate | Result | Evidence boundary |
|---|---|---|
| G9.1 calibration contract | PASS OFFLINE | Strict schema/semantic admission, adversarial lifecycle/digest tests, empty physical baseline |
| G9.2 limit selection | PASS OFFLINE | Four-class exact selection, boundary/staleness/contradiction denials, empty measured baseline |
| G9.3 native observation core | PASS OFFLINE | C++11 normal, sanitizer, allocation-symbol and ESP32 compile lanes |
| G9.4 host/native parity | PASS SYNTHETIC | One byte-stable 39-case corpus; no physical calibration or sensor evidence |
| G9.5 Dropbear readiness | PASS DENIAL FOUNDATION | 12 exact rows, 13 dependencies each, zero materialization and motion false |
| G9.6 description inventory | PASS OBSERVATION FOUNDATION | 198 pinned paths, duplicate/drift report, 161 unresolved questions, zero mappings |
| G9.7 unified evidence | PASS | 47-stage atomic report, all repository suites, traceability, web, ESP32 and whitespace |

## Verification totals

- requirements / trace rows: 77 / 77
- controlled sources / ADRs / work packages: 20 / 10 / 20
- test-catalog IDs: 113
- validated relative links: 48
- calibration / limit registry tests: 11 / 11
- shared observation cases: 39
- readiness / description-inventory tests: 8 / 8
- machine-report focused tests: 7
- machine gate stages: 47/47 PASS
- web regression suites: 6, all pass
- ESP32 target: `esp32`, compile only
- RAM: 22,360 / 327,680 bytes (6.8%)
- flash: 299,709 / 1,310,720 bytes (22.9%)
- exact CAD configurations accepted: 0/53
- catalog models supported: 0/44
- sourced / physically validated real plant parameter sets: 0 / 0
- Dropbear motion-ready / routes / ROS mappings / calibrations: 0 / 0 / 0 /
  0 of 12

## External carries and non-claims

- The independent X12 CAD workbench remains ready, but no identified
  non-automation reviewer has submitted a decision. CAD acceptance stays
  0/53.
- The 161 graph questions are mechanical/control review inputs, not mappings.
  Detailed/simplified name similarity, exact duplicate files and mesh labels
  grant no authority.
- No installed actuator serial/tuple, protocol applicability, physical bus
  route, controller owner, brake behavior, independent power removal,
  measured limit or physical calibration exists.
- No real ESP32 CAN driver/capture, measured scheduler timing, bench
  endurance, HIL, load-bearing test or robot release was performed.
- The synthetic plant and observation fixtures cannot populate physical
  evidence registries or establish one of the 44 real model parameter sets.
- Existing user ESP32 runtime files remain preserved. New cores compile but
  have not been wired into legacy command writers or hardware output.

## Close decision

Iteration 9 closes because every authorized offline outcome is reproducible
and machine-recorded, while every absent physical or human-reviewed fact
remains an explicit denial. Track A carries forward unchanged. The next safe
slice is a reviewed-decision contract for the candidate actuation/closed-chain
graph plus a source-authority selection record, followed by denial-only
canonical graph and ROS/simulator projections. It must not infer any of the
161 answers or enable physical output.
