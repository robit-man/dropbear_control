# Iteration 11 delivery implementation plan

Status: `COMPLETE-OFFLINE`

## Vertical slices

1. Source registry lifecycle: event schema, replay, active decision selection,
   revocation, atomic supersession, empty tracked baseline and host denial.
2. Structured graph V2: frames/aliases/chirality/symmetry, equations,
   singularities, DOF and dependency-state validation.
3. Lifecycle projections: generation/hash-aware host/ROS/simulator/UI outputs
   and session invalidation.
4. Controller adapter intake: exact manifest and fail-only selection without
   a concrete driver or runtime wiring.
5. Closure: focused mutations, catalog/traceability, full machine gate and
   explicit physical hold.

## Exclusive namespaces

- `assets/dropbear/source_authority_registry/` — human submissions/events;
- `generated/dropbear_source_registry_v2/` — registry projection only;
- `assets/dropbear/graph_v2/` — future human graph submissions;
- `generated/dropbear_graph_v2/` — candidate/status/projections only; and
- `assets/dropbear/can_adapter_manifests/` — future exact adapter evidence.

No generator may consume a build/install robot description as source or write
into the preserved ESP32 runtime.

## Closure

All five slices are complete for the offline evidence class. The tracked
source and graph registries remain empty, all lifecycle-aware projections
remain denial-only, and the physical adapter factory remains disabled. The
preserved ESP32 runtime was compiled but was not wired to these new paths.
