# Iteration 11 plan — positive authority lifecycle and structured graph V2

- Iteration status: `COMPLETE-OFFLINE-PHYSICAL-AUTHORIZATION-HOLD`
- Phase context: P2 elaboration, WP-030/WP-100/WP-110/WP-120/WP-160/WP-180
- Entry gate: Iteration 10 machine run `5d20ea02d4e806edf8c74a0a`,
  52/52 stages PASS, 77 requirements, 118 catalog tests, 48 checked links
- Real authority baseline: source decisions 0, graph decisions 0, canonical
  graphs 0, runtime mappings 0, installed inventories 0
- Physical baseline: ready actuators/routes/calibrations 0/12, accepted CAD
  0/53, real plants 0/44, authorized physical actions 0
- Hard hold: no robot access, electrical connection, power, CAN capture/TX,
  brake release, calibration motion, HIL or robot motion

## Iteration outcome

Iteration 11 turns the V1 review formats into durable positive-capable
registries without accepting any synthetic or missing real decision. It also
defines graph V2 data structures for frames, aliases, chirality, symmetry,
coupling domains, singularities and explicit DOF accounting.

The unpowered installed-inventory campaign remains ready for human review but
cannot execute without the user's bounded authorization plus named
hardware-owner and safety-reviewer roles. Offline delivery proceeds
independently.

## Delivery Track A — source authority registry V2

| ID | Atomic work package | Exit condition |
|---|---|---|
| I11-A01 | Preserve V1 decision validation | Every source selection still binds exact current tree/inventory/config and seven roles/29 divergences |
| I11-A02 | Separate submissions namespace | Only exact JSON files in one owned directory; no glob/family/default selection |
| I11-A03 | Closed lifecycle events | Accept, reject, revoke and atomic supersede transitions only |
| I11-A04 | Independent approver | Registry approver is identified, UTC, human, independent of automation and source reviewer |
| I11-A05 | Event integrity | Event digest binds decision hashes, transition, actor, evidence and replacement |
| I11-A06 | Global event order | Contiguous sequence and monotonic UTC; replay is deterministic |
| I11-A07 | Single active authority | At most one final accepted runtime-complete source decision |
| I11-A08 | Atomic supersession | Old accepted becomes superseded as the exact new submitted decision becomes accepted |
| I11-A09 | Revocation | Revoked source immediately removes active authority and downstream eligibility |
| I11-A10 | Drift invalidation | Any current inventory/tree/config/object drift rejects registry rebuild before write |
| I11-A11 | Empty positive-capable baseline | Tracked registry contains zero decisions/events/active authority |
| I11-A12 | Synthetic lifecycle proof | Accept/reject/revoke/supersede paths pass in memory/temp only and never enter tracked evidence |

## Delivery Track B — structured graph V2

| ID | Atomic work package | Exit condition |
|---|---|---|
| I11-B01 | V1 subject carry | V2 binds accepted source registry generation/hash plus inventory/config |
| I11-B02 | Frame registry | Stable frame IDs, parent relation, SI rigid transform and source evidence |
| I11-B03 | Alias registry | Alias namespace/source/target are explicit and collision-free |
| I11-B04 | Chirality | Link/joint/actuator side is left/right/center/none, never inferred from name |
| I11-B05 | Symmetry policy | Each mirrored pair is reviewed equal, transformed or intentionally different |
| I11-B06 | Joint frames | Origin and axis declare exact expressed-in frame |
| I11-B07 | Structured coupling | Equation kind, terms, ratio/sign/offset, input/output coordinate and domain |
| I11-B08 | Singularity model | Condition, detection variable, exclusion/handling policy and owner |
| I11-B09 | Structured closure | Physical versus simulator-only loop endpoints and solver responsibility |
| I11-B10 | DOF ledger | Independent/dependent/passive/fixed/simulator coordinates reconcile to graph counts |
| I11-B11 | Ownership closure | One writer/state policy per independent command coordinate |
| I11-B12 | Dependency closure state | CAD/calibration/limit/route references carry missing/present/admitted separately |
| I11-B13 | V1 migration | V1 graph can be deterministically represented as an incomplete V2 candidate, never auto-admitted |
| I11-B14 | Synthetic positive fixtures | Tree, mimic, coupling, closed chain, simulator loop and intentional asymmetry validate |
| I11-B15 | Mutation suite | Frame cycles, aliases, symmetry, equations, singularities and DOF lies deny |
| I11-B16 | Real baseline | No V2 Dropbear graph accepted; all downstream mappings remain zero |

## Delivery Track C — lifecycle-aware projections and API

| ID | Atomic work package | Exit condition |
|---|---|---|
| I11-C01 | Registry status projection | Source/graph active, revoked, superseded and blocker states are hash-bound |
| I11-C02 | Transactional downstream refresh | Registry failure preserves last generated denial artifact |
| I11-C03 | Host exact query | Exact decision/graph generation only; no stale handle across revocation |
| I11-C04 | ROS denial/positive shape | Positive schema can describe mappings but tracked output remains empty |
| I11-C05 | Simulator denial/positive shape | Positive schema can bind graph backend but no real backend is selected |
| I11-C06 | UI lifecycle view | Counts/state/revocation reason only; no local/evidence paths |
| I11-C07 | API revocation token | Source/graph registry generation participates in session/handle identity |
| I11-C08 | Synthetic revocation tests | Accepted fake session becomes unusable after registry generation/revocation change |

## Delivery Track D — controller adapter intake, no I/O

| ID | Atomic work package | Exit condition |
|---|---|---|
| I11-D01 | Exact adapter manifest | Board/controller/transceiver/pins/clock/driver/binary/config tuple |
| I11-D02 | Purpose distinction | Listen-only and runtime-gateway decisions cannot substitute |
| I11-D03 | Timing evidence format | 1-Mbit/s timing inputs/result/sample point/error are explicit |
| I11-D04 | TX-disable evidence | Controller mode and independent physical disable are separate |
| I11-D05 | Queue/timestamp/loss | Bounds, clock, wrap, overflow and loss-counter evidence required |
| I11-D06 | Error-state policy | Warning/passive/bus-off/recovery evidence and bounded transitions |
| I11-D07 | TWAI/MCP2515 neutrality | Neither selected without installed evidence |
| I11-D08 | No-I/O fake validation | Synthetic driver manifest proves semantics only |
| I11-D09 | Physical factory denial | Missing admitted manifest cannot instantiate an adapter |
| I11-D10 | Runtime preservation | No user ESP32 runtime file is wired or rewritten |

## Discovery Track — Iteration 12 physical evidence convergence

| ID | Discovery item | Definition of Ready |
|---|---|---|
| I11-X01 | Human source-review packet | Exact seven-role/divergence workload and approver separation reviewed |
| I11-X02 | Human graph-review sequence | Cohort ordering, mechanical expertise and evidence sources assigned |
| I11-X03 | Bounded U0 authorization | Exact asset/location/time/actions/roles and zero-energy preconditions |
| I11-X04 | Inventory evidence custody | Approved storage, tools, hashes and reviewer path |
| I11-X05 | Controller selection meeting | Installed observations sufficient for TWAI/MCP2515 decision |
| I11-X06 | Isolated adapter fixture | Separate from robot, physical TX-disable measurement possible |
| I11-X07 | L1 authorization draft | Exact powered listen-only setup; no command authority |
| I11-X08 | Independent safe-power team | Named owner/reviewer/instrumentation and survey scope |
| I11-X09 | CAD reviewer cohort | Exact installed model/output-member candidate assigned |
| I11-X10 | Plant experiment design | Parameters, excitation, uncertainty and holdout criteria reviewed |
| I11-X11 | One-actuator HIL prerequisites | Exact tuple, restraint, bounds, stop path and fault matrix |
| I11-X12 | Stop/rollback decision | Explicit conditions for ending physical work and invalidating evidence |

## Dependency order

1. A01..A12 establishes durable source lifecycle.
2. B01 consumes only an active A registry; B02..B12 defines structured V2;
   B13..B15 proves it; B16 preserves the real denial.
3. C01..C08 consumes A/B lifecycle without weakening V1 projections.
4. D01..D10 remains no-I/O and cannot select hardware before U0 observations.
5. Discovery X01..X12 prepares external work but grants no action.

## Iteration gates

- G11.1: source registry lifecycle replay and transactional mutation tests pass;
  tracked active authority remains zero.
- G11.2: graph V2 structured schema and semantic mutations pass; tracked graph
  remains zero.
- G11.3: projection/API revocation behavior passes with synthetic fixtures and
  no real mapping/handle.
- G11.4: adapter manifest/factory remain neutral and no-I/O.
- G11.5: U0 physical campaign is either explicitly authorized and separately
  executed later, or remains a visible hold.
- G11.6: catalog, traceability, generated drift, full gate, web and ESP32
  compile pass.

## Definition of Done

- [x] Positive-capable source registry has complete tested lifecycle with zero
  tracked authority.
- [x] Structured graph V2 represents and validates all planned semantics.
- [x] Registry revocation invalidates synthetic projections/handles.
- [x] Adapter intake cannot select or instantiate physical I/O.
- [x] Physical authorization status is explicit and no scope leaks.
- [x] Full machine gate and verification report pass.
