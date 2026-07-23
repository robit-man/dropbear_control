# Iteration 10 delivery implementation plan

Status: `V1-STEEL-THREAD-COMPLETE-OFFLINE`; every denial-first vertical slice
below is implemented and tested. Positive registries, structured graph V2
semantics and real source/graph/CAD/hardware evidence remain explicit carries.

## Committed vertical slices

1. **Source decision steel thread**
   - strict schema and semantic validator;
   - generated unanswered template bound to the pinned inventory;
   - adversarial reviewer/hash/derivative/divergence tests;
   - empty accepted registry and typed host denial.
2. **Graph decision steel thread**
   - strict decision schema for all inventory questions and actuator edges;
   - deterministic cohort packet and local no-network workbench;
   - transaction validator and zero accepted baseline.
3. **Canonical graph core**
   - immutable graph types and admission;
   - synthetic tree/mimic/closed-chain fixtures;
   - topology, DOF, ownership, identity and dependency invariants;
   - empty Dropbear registry.
4. **Consumer-denial steel thread**
   - generated host/ROS/simulator/UI status;
   - exact source/config/inventory/decision hashes;
   - zero transforms, transmissions, actuator mappings and motion.
5. **Hardware API contract**
   - typed fake/replay/synthetic lifecycle;
   - graph/readiness-gated handle factory;
   - fail-only physical backend;
   - no user runtime integration.

## Integration boundaries

- The description inventory is immutable input and remains observation-only.
- Source and graph decision outputs use separate exclusive namespaces.
- The canonical graph registry can consume accepted decisions only through
  their record IDs and full hashes.
- Readiness V1 remains denial-only; new graph status is a peer dependency
  rather than an in-place weakening.
- Host, ROS, simulator and UI consume generated status projections only.
- Firmware receives no graph-derived physical mapping in this iteration.

## Completion order

`source schema -> template -> validator -> graph schema -> packet/workbench ->
graph core -> synthetic tests -> empty registry -> denial projections ->
hardware API -> unified gate`.

Every slice updates catalog/traceability before the next slice can claim
completion.

Closure result: all five V1 steel threads completed. The graph core
additionally proves positive synthetic mimic, physical closed-chain and
simulator-only closure semantics. Positive lifecycle/revocation, structured
symmetry/coupling/DOF metadata and dependency closure remain V2 work. No
preserved user ESP32 runtime file or ROS package was wired to the new
contracts.
