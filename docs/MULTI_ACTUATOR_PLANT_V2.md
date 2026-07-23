# Deterministic multi-actuator plant V2

Status: implemented offline synthetic composition contract.

This document specifies the composition layer between the deterministic
single-actuator V2 equation core and future robot-level simulation. It exists
to exercise twelve-axis scheduling, ownership, command batching, fault
propagation, snapshot and replay behavior before a reviewed canonical
Dropbear graph or exact MYACTUATOR plant set is available.

It is deliberately not:

- a canonical Dropbear robot description;
- a rigid-body, contact, transmission-coupling or closed-chain model;
- a shared electrical power-bus model;
- an exact MYACTUATOR model;
- evidence that any installed unit, firmware or transport is applicable;
- physically validated; or
- capable of physical I/O or motion authority.

The module permanently exposes `support_granted=false`,
`exact_model_fidelity=false`, `dropbear_canonical=false`,
`models_rigid_body=false`, `models_shared_power_bus=false`,
`physical_validation=false`, `physical_io=false` and
`motion_authority=false`.

## Identity and configuration

A bank configuration contains:

1. one exact scene identifier;
2. a lexicographically ordered, duplicate-free tuple of actuator identifiers;
3. one typed `PlantV2Configuration` per actuator;
4. one positive aggregate absolute commanded q-axis-current budget;
5. the closed policies
   `all_declared_actuators_exactly_once`,
   `reject_entire_batch_before_mutation`,
   `rollback_entire_step_on_failure`,
   `latch_bank_fault_and_clear_all_commands`, and
   `sha256-scene-seed-actuator-v1`; and
6. the permanent non-authority fields above.

Every actuator must use the same exact-rational current-loop period. State
sample rates, command delay, feedback delay, jitter and sensor noise may
differ because they remain local V2 contract semantics. The scene digest
binds every actuator ID, each complete V2 configuration digest, the aggregate
budget, policy names and authority boundary. Input order is not normalized:
noncanonical ordering is rejected.

This contract intentionally does not guess a bus topology, joint graph,
motor family or mapping. A future canonical scene must be generated from
independently accepted Dropbear graph, CAD and plant registries and must use a
separate evidence-bearing admission path.

## Deterministic reset and seeds

Reset takes one unsigned 64-bit scene seed. Each actuator seed is derived as:

```text
SHA-256(
  "myactuator-multi-actuator-v2-seed\0"
  || scene-configuration-sha256
  || "\0"
  || decimal-scene-seed
  || "\0"
  || actuator-id
)[0:8] as unsigned big-endian integer
```

This makes each noise/jitter stream stable, independent and bound to the
scene identity. Reset clears batch sequence, bank fault state, pending
commands and all per-actuator hidden state.

## Atomic command batches

One `MultiActuatorCommandBatch` contains:

- the exact scene digest;
- reset generation;
- the next dense bank sequence;
- the current issued step;
- an exclusive future deadline step; and
- exactly one command for every declared actuator.

Rows must be in canonical actuator order. Each row is either disabled with
exactly zero current or enabled with a finite q-axis-current target. The
target must satisfy the actuator's own reviewed-direction and source-current
limits. The sum of absolute enabled targets must not exceed the separate
synthetic aggregate command budget.

The bank validates the full batch before submitting any local V2 command. It
also snapshots every actuator and restores all of them if an unexpected local
submission failure occurs. A rejected batch consumes no bank or local
sequence and changes no plant state.

The aggregate budget is an admission envelope only. It does not claim supply
voltage sag, regeneration, battery dynamics, wiring loss or controller power
sharing.

## Transactional synchronized stepping

One bank step requires an exact, canonically ordered load row for every
actuator. Each finite load must be within that actuator's V2 load-torque
bound. The bank snapshots all axes, advances each exactly once, and restores
all axes if any local step fails.

After a successful synchronized step:

- every local `step_index` equals the bank step;
- aggregate absolute q-axis current and maximum winding/case temperatures
  are recomputed from the actual states;
- per-axis samples and diagnostics remain distinct; and
- any local thermal shutdown clears commands on every axis and latches a
  bank-wide `thermal-shutdown:<actuator-id>` fault.

A latched bank refuses new batches and further advancement until explicit
reset. This is a synthetic fail-stop semantic, not proof that hardware power
was removed.

## Snapshot, restore and replay

The snapshot is canonical JSON data containing:

- schema and scene configuration identity;
- scene seed and reset generation;
- bank step and next dense batch sequence;
- latched bank fault state;
- the last aggregate/per-axis step projection; and
- the complete hash-bound V2 snapshot for every actuator.

The outer `snapshot_sha256` binds the entire payload. Restore validates field
closure, digest, exact actuator partition, bank/local step parity, local
configuration identities, derived seeds, sequence relations, authority
fields and aggregate state. It restores into fresh engines first and changes
the live bank only after every candidate engine validates, preventing partial
restore.

`deterministic_multi_actuator_trace_sha256` hashes every accepted command
batch and resulting bank step in canonical form. It is a regression identity
for the declared synthetic scene only.

## Evidence boundary and next integration

This layer can support controller, estimator, scheduling, lease-loss and
cross-axis fault tests with twelve synchronized actuator plants. It cannot
be selected as an exact-model or canonical whole-robot backend. Promotion
requires, independently:

1. accepted exact MYACTUATOR protocol applicability;
2. reviewed source facts and a complete V2 runtime contract per actuator;
3. accepted output-member/axis CAD;
4. one accepted canonical Dropbear source and graph;
5. reviewed rigid-body inertial/contact/sensor semantics; and
6. separately authorized physical correlation evidence.
