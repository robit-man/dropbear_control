# Iteration 2 dual-track plan — canonical Dropbear configuration handoff

- Iteration status: `COMPLETE-OFFLINE`
- Phase context: P1 / early Elaboration
- Delivery scope: WP-030-T01 through the offline portion of WP-030-T04
- Discovery horizon: prepare WP-020, WP-030-T02..06, WP-060 and WP-120 for
  iteration 3
- Safety boundary: no powered hardware commands, physical applicability
  claims, calibration adoption or enable authority

## Iteration intent

Establish the first machine-readable Dropbear configuration contract while
keeping legacy source observations distinct from reviewed physical facts. The
Delivery track produces the schema, fail-closed example and executable
semantic invariants. The Discovery track defines the evidence needed to turn
that incomplete observation into a reviewed registry in a later iteration.

## Delivery track goals

| ID | Goal | Dependencies | Exit evidence | Result |
|---|---|---|---|---|
| I2-D01 | Define robot, controller-node, bus, joint, actuator, sensor, CAD, calibration, provenance and integrity records | WP-020 schema; ADR-001/002 | `schemas/dropbear-config.schema.json` | Done |
| I2-D02 | Establish exactly six semantic joints per leg and boundary-only legacy aliases | ROB-001, CFG-005 | schema plus positive/negative tests | Done |
| I2-D03 | Import the 12 legacy full CAN command identifiers and five encoder channels per leg role only as unverified observations | SRC-014; legacy sketch | incomplete example and observation ledger | Done |
| I2-D04 | Keep native node IDs, bus ownership, motor tuples, limits, calibration and CAD mappings unknown | SRC-016/018 missing | explicit `null`/`UNKNOWN`/`unsupported` values | Done |
| I2-D05 | Prove that an incomplete configuration cannot authorize motion | SAF-001, CFG-003, CFG-005 | deterministic semantic negative tests | Done |
| I2-D06 | Define and verify a reproducible configuration digest | CFG-006 | canonical SHA-256 algorithm and tamper test | Done |

## Discovery track goals for iteration 3

| ID | Goal | Discovery result required | Depends on |
|---|---|---|---|
| I2-X01 | Resolve physical controller and CAN topology without energizing actuators | labeled topology, node identities, wiring/termination review and named owner candidate per bus | WP-000-T04/T05 |
| I2-X02 | Resolve each installed actuator exact tuple | label/serial/model/hardware/drive-firmware/brake evidence with reviewer | SRC-016; WP-020 |
| I2-X03 | Reconcile the 12 legacy full CAN identifiers with native node IDs | explicit derivation or read-only capture evidence; discrepancies retained | I2-X01/I2-X02; SRC-017 if authorized |
| I2-X04 | Refine joint coordinates and sensing | reviewed sign, ratio, feedback source and explicit hip-yaw sensing decision per joint | I2-X01/I2-X02 |
| I2-X05 | Select the canonical Dropbear description authority | duplicate/provenance inventory and accepted detailed/simplified source boundary | WP-120-T01/T02 |
| I2-X06 | Define generator contracts | firmware, host, ROS, UI and simulator views plus hash-mismatch rejection cases | I2-D01..06; WP-030-T05/T06 |

## Definition of Done — Delivery

- [x] Schema is valid JSON and declares Draft 2020-12.
- [x] Schema rejects undeclared root and record properties structurally.
- [x] The example has 12 unique canonical joints and a one-to-one actuator
  mapping.
- [x] Legacy identifiers remain `legacy_full_command_can_id`; no arithmetic
  conversion is promoted to `native_node_id`.
- [x] Five external encoder observations exist per chirality role; both
  hip-yaw joints explicitly mark external sensing `missing`.
- [x] All motor model, hardware revision, drive firmware, protocol revision,
  control mode, ownership, limit, coordinate, calibration and CAD facts that
  lack evidence remain unknown/unsupported.
- [x] The example carries no enable authority and
  `motion_enable_allowed=false`.
- [x] The standard-library semantic validator checks cross-record references,
  unique IDs, ownership, boundary aliases, exact tuples, provenance, digest
  and fail-closed enable admission.
- [x] Positive and negative semantic tests pass deterministically.
- [x] No existing baseline, firmware, web or Dropbear source is changed.

## Definition of Ready — iteration 3 candidate work

An item is ready only when all applicable statements are true:

- the artifact to change, requirement IDs, acceptance checks and evidence
  class are named;
- inputs are pinned and the distinction between observation, official
  specification and physical verification is explicit;
- all dependencies and unresolved physical decisions are visible;
- acceptance criteria are executable offline or identify an approved physical
  runbook and operator;
- motion-affecting values name source, units, coordinate, revision and
  reviewer;
- no wildcard tuple, inferred native node ID or family-wide capability claim
  is permitted;
- generated-view changes include reproducibility and config-hash mismatch
  tests;
- any incomplete configuration remains non-enableable.

The item-by-item assessment is in
`discovery/definition-of-ready-backlog.md`.

## Synchronization and gate result

Discovery observations were frozen before example creation. Delivery encoded
only those observations, and negative tests were executed before handoff. The
iteration passes its offline scope. It does not pass a physical inventory,
bench, HIL, CAD-articulation or robot-release gate.

