# Iteration 8 verification report — authoritative command spine and deterministic evidence backends

- Iteration disposition: `COMPLETE-OFFLINE-WITH-EXTERNAL-CARRIES`
- Verification date: 2026-07-22
- Unified gate: `OFFLINE_GATE_OK`
- Evidence boundary: specification, deterministic host/native tests, generated
  artifact drift checks, synthetic SIL and ESP32 compile only
- Powered hardware, physical capture, bench, HIL and robot evidence: not
  performed

## Delivered and verified

### Session-owned host command ingress

- An allocation-free C++11 production core owns Host Link session receipt and
  refuses caller-supplied decoded-command bypasses.
- Static bindings require exact actuator, source, lease owner, config
  ID/revision/hash, safety reference/generation, route, bus, node, owner,
  translation kind, scale and raw range.
- Only `CURRENT_Q` reaches the typed V4.4 IQ codec. Effort, position, velocity,
  impedance and disable cannot be relabeled as current.
- Values must be finite, within route range and already lie on the 0.01 A grid;
  there is no rounding, clamp or saturation.
- Lease deadlines must be exactly millisecond-aligned and fit the native
  session/time domain; the mapping cannot extend a lease.
- Integrated fake transport asserts exact request bytes and preserves config,
  session, sequence, deadline, owner and route proof through gateway
  submission.
- Normal, ASan/UBSan and undefined-allocation-symbol lanes pass. Duplicate
  test-only conversion policy was removed from the stack bridge.

### Correlated typed egress

- Every gateway phase and result code has a stable Host Link disposition map;
  unknown enumeration values fail closed.
- Transaction, route, bus, node, owner, session, sequence, safety sequence and
  command generation must correlate before state is exposed.
- State is emitted only from an `OBSERVED` native sample. Current remains
  current, effort remains absent, and receipt/TX/response never becomes a
  mechanical-observation claim.
- Stale samples, time overflow and response-kind-specific field presence are
  tested in normal and sanitizer lanes.

### CAN adapter and listen-only evidence contract

- Controller-independent capability checks require evidenced 1-Mbit/s mode,
  standard-ID filtering, timestamps, controller state/loss reporting and
  explicit synchronous TX result.
- Runtime filtering is exact for the V4.4 response domain `0x241..0x260`;
  extended, RTR and structurally invalid frames fail.
- Would-block, TX failure, not-ready, TX-disabled, error-passive, bus-off and
  RX overflow remain distinct through transport-service results.
- Listen-only mode uses the full standard-ID observation range, structurally
  disables transmit, and tests that the driver transmit method is never
  called.
- The JSONL capture schema and host validator require monotonic timestamps,
  controller/build/config provenance, flags/DLC/data, loss counters and RX-only
  scope. A valid capture still cannot assert protocol applicability, motor
  support or motion authority.
- No ESP32-specific physical driver was selected and no CAN capture was
  collected.

### Deterministic synthetic actuator plant

- A distinct `synthetic_actuator_plant` backend implements fixed-step
  semi-implicit integration of R-L/back-EMF electrical state, rotor/output
  inertia, elastic gear, backlash, damping, friction, voltage/current/speed/
  position/torque bounds, two-node thermal state, derating/shutdown and
  quantized delayed sensors.
- Analytic and boundary cases cover equilibrium, first electrical step,
  backlash/friction, saturation, thermal rise/cooldown, sensor latency and
  protocol-emulator coupling.
- The pinned 2,000-step trace hash is
  `2cfca5c638918c938802e91bc189f40e42413b1c230cb5b3d6adb0868e296a3b`.
- The canonical plant registry now exposes three explicitly distinct backend
  kinds, while real sourced/loadable parameter sets remain zero and all 44
  catalog models remain unsupported.

### Dropbear topology and layer reconciliation

- Seven upstream files are read from pinned Git objects at commit
  `13cf5ecaa39b8b89c794fe905dcea0490cfa7726`; paths and SHA-256 hashes are
  embedded in a deterministic reconciliation artifact.
- The artifact preserves 12 semantic actuator/address observations, ten
  external sensor observations and ten ROS leg command joints with zero
  evidence-backed mappings.
- Arithmetic candidate node IDs `1..12` remain explicitly non-route
  observations; installed identity, route, owner, protocol applicability,
  limits, calibration and CAD bindings remain unresolved for all 12.
- ROS observations remain explicit: five joints per leg, open-loop position,
  10 Hz controller manager, `-PI..-PI` active limits and Gazebo-only hardware.
- Ten layers from high-level intent to estimator record owner, rate,
  units/frame, failure propagation and blockers; every layer has physical
  motion authority false.
- Ten tests re-hash Git objects, verify cardinalities/layer order and mutate
  identity, route, calibration, ROS mapping and motion fields to prove unsafe
  promotion is rejected.
- The canonical configuration digest is unchanged at
  `dd8909bceece765e80d83d7d3f93196d6967b4f3ae72e20fdee6f29d21a81cba`;
  motion remains false.

## Gate matrix

| Iteration gate | Result | Evidence boundary |
|---|---|---|
| G8.1 production ingress | PASS | Native offline core, exact binding/quantization/time denial and sanitizer checks |
| G8.2 host-to-native fake path | PASS | Session-owned ingress through config/safety/gateway to exact fake bytes; no duplicate translator |
| G8.3 typed egress | PASS | Total disposition map and correlated observed-state projection |
| G8.4 adapter/capture conformance | PASS OFFLINE | Fake-driver and capture validation only; physical driver/capture held |
| G8.5 synthetic plant | PASS SIL-SYNTHETIC | Analytic/deterministic synthetic fixture; real support remains 0/44 |
| G8.6 Dropbear topology | PASS DENIAL FOUNDATION | Pinned graph/gap artifact; mappings/routes 0 and motion false |
| G8.7 unified gate | PASS | All repository suites, traceability, web, ESP32 compile and whitespace |

## Verification totals

- requirements: 77
- traceability rows: 77
- controlled sources: 20
- ADRs: 10
- work packages: 20
- test-catalog IDs: 106
- validated relative links: 48
- Dropbear reconciliation tests: 10
- synthetic plant tests: 15
- listen-only capture tests: 7
- web regression suites: 6, all pass
- ESP32 target: `esp32`, compile only
- RAM: 22,360 / 327,680 bytes (6.8%)
- flash: 299,709 / 1,310,720 bytes (22.9%)
- exact CAD configurations accepted: 0/53
- catalog models supported: 0/44
- real plant parameter sets/loadable plants: 0/0
- Dropbear installed routes/calibrations/CAD bindings: 0/0/0 of 12

## External carries and non-claims

- Independent CAD judgment remains external. The X12 candidate has no
  submitted decision and cannot be self-signed by automation.
- The new CAN contract is not a real MCP2515/TWAI adapter, measured bus timing,
  or proof of wiring, termination, transceiver behavior or bus-off recovery.
- The synthetic plant is not identified against a MYACTUATOR model and cannot
  provide torque constants, friction, thermal or latency claims for one.
- The Dropbear repository observations are not an installed physical
  inventory. ROS names, CAD mesh labels and CAN address shapes cannot fill
  exact identity, route, calibration or kinematic edges.
- New runtime cores compile into the ESP32 project but remain intentionally
  unwired from the preserved user `main.cpp` and legacy writers.
- No exact installed tuple, physical stop/brake, independent power removal,
  sign/limit/calibration, HIL, endurance or robot release is proven.

## Close decision

Iteration 8 closes because every offline outcome is reproducible, the unified
gate is green, and unavailable external facts remain explicit holds rather
than fabricated completion. Track A carries forward until an independent
reviewer submits a valid decision. Physical adapter and robot work remain
unauthorized. The next safe slice is an offline canonical Dropbear actuation
graph and sensor/calibration contract, followed by generated-denial adapters;
it must not wire physical output or infer five-to-six joint mappings.
