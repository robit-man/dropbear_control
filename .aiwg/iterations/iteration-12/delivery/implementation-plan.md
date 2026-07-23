# Iteration 12 delivery implementation plan

Status: `COMPLETE-OFFLINE`

## Vertical slices

1. Reassess the current library against executable evidence and replace stale
   prototype-era completeness percentages with per-capability proof states.
2. Generate one source-bound runtime catalog joining the 44-model product
   registry, 53 CAD configurations, plant backends and Dropbear lifecycle.
3. Implement a deterministic simulation session with a small engine protocol,
   fixed virtual time, explicit reset/fault/trace semantics and live
   generation checks.
4. Adapt the existing V4.4 emulator, synthetic electromechanical plant and
   replay source without changing their evidence classes.
5. Implement the dependency-free semantic core for a future
   `ros2_control::SystemInterface`.
6. Project only redacted readiness into the browser and close traceability,
   machine evidence, web and ESP32 regression.

## Exclusive namespaces

- `generated/myactuator/simulator/` — generated runtime catalog/status only;
- `web/assets/simulator_runtime*.generated.json` — redacted generated view;
- `host/myactuator_lib/simulation_runtime.py` — catalog admission;
- `host/myactuator_lib/simulation_session.py` — deterministic session core;
- `host/myactuator_lib/ros2_control_core.py` — ROS-independent semantics; and
- `tests/simulator_runtime/`, `tests/simulation_session/`,
  `tests/ros2_control_core/` — focused suites.

No generator writes vendor STEP, human review submissions, Dropbear source
files, the preserved ESP32 runtime or ROS build/install outputs.

## Design constraints

- Use existing registries as inputs; do not create a parallel source of truth.
- Accept exact IDs and kinds only.
- Use integer virtual time and canonical JSON for trace hashing.
- Keep catalog/demo, protocol, synthetic plant, sourced plant, rigid body and
  physical adapter evidence classes distinct.
- Require live source/graph/catalog generation parity for every session use.
- Never fabricate ROS joint mappings from names or symmetry.
- Keep browser projections path-free.
