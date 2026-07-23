# Iteration 12 plan — evidence-aware simulator runtime and ROS boundary

- Iteration status: `COMPLETE-OFFLINE-PHYSICAL-AUTHORIZATION-HOLD`
- Phase context: P2/P4/P5 elaboration, WP-110/WP-130/WP-140/WP-150/
  WP-160/WP-180
- Entry gate: Iteration 11 canonical machine run
  `b4a1516e60828aa042491fa6`, 57/57 stages PASS, 77 requirements,
  122 catalog tests and 23 critical artifact bindings
- Catalog baseline: 44 models, 53 exact STEP variants/configurations,
  0 accepted articulated assets, 0 sourced real plants
- Dropbear baseline: source/graph authority 0, 161 unresolved graph
  questions, 0 runtime ROS/simulator mappings
- Physical baseline: 0 selected CAN adapters, 0 installed inventories,
  0 authorized physical actions

## Iteration outcome

Create one deterministic, backend-neutral simulation session and one exact
runtime catalog that join catalog, CAD, plant and Dropbear lifecycle evidence.
Then expose the same lifecycle, identity, command/state and revocation
semantics through a dependency-free `ros2_control`-compatible core.

The runtime must distinguish useful synthetic execution from model fidelity.
The protocol emulator, synthetic plant and browser toy may execute only under
their explicit evidence classes. None may become an exact-model plant,
reviewed articulated CAD asset, canonical Dropbear graph or physical backend.

## Delivery Track A — current-state reassessment

| ID | Atomic work package | Exit condition |
|---|---|---|
| I12-A01 | Recalculate completeness | Assessment reflects current source/graph/CAD/plant/API/gate evidence, not the original prototype snapshot |
| I12-A02 | Separate dimensions | Catalog acquisition, codec support, physical applicability, CAD articulation, plant fidelity and whole-robot readiness are scored independently |
| I12-A03 | Exact remaining ledger | Every incomplete claim names its proving artifact/gate rather than a percentage alone |
| I12-A04 | Preserve prototype attribution | Existing user ESP32/web edits remain distinct and are not rewritten as production paths |

## Delivery Track B — unified simulator runtime catalog

| ID | Atomic work package | Exit condition |
|---|---|---|
| I12-B01 | Strict catalog schema | Closed Draft 2020-12 schema binds exact inputs, generation digest and false authority claims |
| I12-B02 | Exact 44-model join | Every catalog tuple appears once; no family/default/latest fallback |
| I12-B03 | Exact 53-configuration join | CAD configuration and source-variant coverage are lossless and ordered |
| I12-B04 | CAD state separation | Vendor STEP acquisition, candidate conversion, accepted articulation, local loadability and browser publication remain distinct |
| I12-B05 | Plant state separation | Synthetic executable engine, sourced plant and physically validated plant are distinct |
| I12-B06 | Protocol state separation | Codec/emulator tooling never implies exact model/firmware applicability |
| I12-B07 | Graph lifecycle binding | Source and graph registry generations plus simulator projection digest are bound |
| I12-B08 | Backend capability matrix | Each backend declares supported use cases, dynamics, geometry, command, determinism and physical-I/O properties |
| I12-B09 | Dropbear admission | Whole-robot fidelity requires active canonical graph, mappings, accepted CAD and admitted plant dependencies |
| I12-B10 | Browser-safe projection | No local paths, source archive URLs or evidence paths are exposed |
| I12-B11 | Transactional generation | Failure never replaces the last valid generated catalog |
| I12-B12 | Host exact queries | Model/config/backend lookup is exact and generation checked at use |

## Delivery Track C — deterministic simulation session

| ID | Atomic work package | Exit condition |
|---|---|---|
| I12-C01 | Typed selection | Exact catalog generation, model/config/backend/use-case and fidelity requirements |
| I12-C02 | Closed lifecycle | Unconfigured, inactive, active, faulted and finalized transitions are explicit |
| I12-C03 | Virtual time | Integer tick/time only; read and wall clock never advance simulation |
| I12-C04 | Command envelope | Sequence, issue/deadline tick, actuator, mode, SI target and bounds are exact |
| I12-C05 | Reset contract | Explicit seed, initial state digest and reset generation |
| I12-C06 | State envelope | Tick, sample/receive time, validity, source, units, fault and identity are retained |
| I12-C07 | Snapshot/restore | Snapshot binds engine/catalog/config/graph/reset generation and state digest |
| I12-C08 | Scheduled faults | Fault kind, target, injection tick, duration and disposition are deterministic |
| I12-C09 | Trace integrity | Dense event sequence, canonical encoding, rolling digest and replay equality |
| I12-C10 | Registry revocation | Catalog/source/graph generation change faults a live session before further use |
| I12-C11 | Synthetic plant adapter | Existing fixed-step plant executes through the common contract without model-fidelity claims |
| I12-C12 | Protocol emulator adapter | V4.4 protocol state executes through the common time/fault/trace contract without plant claims |
| I12-C13 | Replay adapter | Recorded state is readable but never command-capable |
| I12-C14 | Rigid-body/physical denial | Missing admitted graph/assets/plants and missing physical adapter always deny |
| I12-C15 | Cross-backend vectors | Lifecycle/time/reset/revoke/fault/trace behavior is reusable across all executable adapters |

## Delivery Track D — ROS control boundary

| ID | Atomic work package | Exit condition |
|---|---|---|
| I12-D01 | Dependency-free core | Contract imports and tests without a ROS installation |
| I12-D02 | Exact interface descriptor | Hardware name, joints, command/state interfaces and parameters bind graph/config generations |
| I12-D03 | Lifecycle parity | Configure/activate/deactivate/cleanup/error/shutdown map without implicit enable |
| I12-D04 | Command mode claims | Position/velocity/effort interfaces exist only when exact graph/backend capability admits them |
| I12-D05 | State validity | Missing/stale/faulted signals are not replaced with zero |
| I12-D06 | Read/write separation | Read cannot command; write requires active session, lease, finite data and current generations |
| I12-D07 | Return dispositions | Success, not-ready, invalid, stale, timeout and fault remain distinct |
| I12-D08 | Revocation | Source/graph/catalog generation change yields error and invalidates handles |
| I12-D09 | No direct native access | Interface exposes no CAN ID, opcode, raw bytes or bypass path |
| I12-D10 | Plugin handoff shape | A future C++ `hardware_interface::SystemInterface` adapter can consume the tested core without redefining semantics |

## Delivery Track E — integration and evidence

| ID | Atomic work package | Exit condition |
|---|---|---|
| I12-E01 | Browser catalog consumer | UI can show exact readiness/blockers but load no unaccepted asset |
| I12-E02 | Cross-layer parity | Host/browser/ROS/simulator agree on generation and zero real-fidelity counts |
| I12-E03 | Mutation coverage | Counts, IDs, hashes, paths, claims, lifecycle, time and backend substitution mutations deny |
| I12-E04 | Requirement/test registration | New cases are cataloged and traced to existing/new requirements |
| I12-E05 | Critical artifact binding | Offline report hashes simulator catalog and any ROS/session status artifacts |
| I12-E06 | Full regression | Focused suites, web, ESP32 compile and complete machine gate pass |

## Discovery Track — Iteration 13 fidelity convergence

| ID | Discovery item | Definition of Ready |
|---|---|---|
| I12-X01 | Rigid-body engine benchmark | Headless determinism, contact, ROS integration, closed-chain and developer workflow cases fixed |
| I12-X02 | Source reviewer session | Seven source roles and 29 divergence decisions assigned |
| I12-X03 | Graph reviewer cohorts | Ten cohorts, expertise, sequence and evidence windows assigned |
| I12-X04 | Installed-model CAD cohort | Exact physical model and candidate output-member review assigned |
| I12-X05 | Remaining CAD campaign | 44-model/53-configuration review order and shell/re-source lanes scheduled |
| I12-X06 | Plant parameter corpus | Vendor curves/manual clauses and uncertainty fields inventoried by exact tuple |
| I12-X07 | Correlation design | Datasheet, bench and holdout metrics separated |
| I12-X08 | ROS build environment | Target ROS distribution/compiler/plugin ABI pinned |
| I12-X09 | U0 authorization | Visual-only request completed by named humans without powered scope |
| I12-X10 | Adapter fixture | Exact isolated hardware and physical TX-disable measurement reviewed |

## Dependency order

1. A establishes honest current state.
2. B joins current authoritative registries and defines exact admission.
3. C consumes B and the existing hardware API/plant/emulator cores.
4. D consumes B/C and graph lifecycle without requiring ROS at test time.
5. E integrates consumers and closes the machine evidence.
6. X prepares later human/physical/engine work but grants no authority.

## Iteration gates

- G12.1: catalog covers exactly 44 models/53 configurations and reproduces
  from current source hashes.
- G12.2: all current exact-model, articulated-CAD, real-plant and Dropbear
  whole-robot fidelity admissions remain denied.
- G12.3: explicit synthetic sessions execute deterministically with no model
  or physical claim.
- G12.4: session trace/replay, lifecycle, deadline, fault and live generation
  revocation tests pass.
- G12.5: ROS core preserves missing/stale/faulted state and cannot command
  outside active admitted sessions.
- G12.6: browser and host projections are generation-equivalent and path-safe.
- G12.7: physical authorization remains a visible hold.
- G12.8: traceability, complete gate, web and ESP32 compile pass.

## Definition of Done

- [x] Current completeness assessment is evidence-correct.
- [x] Unified simulator runtime catalog is strict, generated and tested.
- [x] Backend-neutral deterministic session has plant/protocol/replay adapters.
- [x] Exact-model/whole-robot fidelity remains fail-closed until real evidence.
- [x] Dependency-free ROS control core passes lifecycle/state/command tests.
- [x] Browser and host consumers agree and expose no unsafe path.
- [x] Physical authorization status is unchanged and explicit.
- [x] Full machine gate and verification report pass.
