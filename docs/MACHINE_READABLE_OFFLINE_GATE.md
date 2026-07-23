# Machine-readable offline gate evidence

`tools/test_all.sh` now writes
[`generated/verification/offline_gate_report.json`](../generated/verification/offline_gate_report.json)
atomically throughout a run. The report is canonical JSON validated by
[`offline-gate-report.schema.json`](../schemas/offline-gate-report.schema.json).

At initialization it records:

- the Git HEAD, dirty-state flag and tracked-diff digest;
- a path-and-content manifest digest over governance, contracts, docs,
  firmware, host, schemas, tests, tools and web source;
- canonical Dropbear configuration identity and digest;
- platform and Python, Node, npm, G++, PlatformIO and Git versions;
- hashes of the CAD support, plant, V1/V2 runtime-adapter, readiness,
  description, calibration, limit and canonical configuration evidence
  inputs; and
- fixed claim invariants for physical work, 44-model support, 53 CAD
  configurations, real plants, 12-actuator readiness, calibration, limits,
mappings and motion. The V2 claim block additionally pins its solver,
noise and jitter algorithm identities while requiring zero profiles,
contracts, loadable models and physically validated contracts.

Every stage is appended before execution and finalized atomically with its
exact result and exit code. A failing stage remains in the report together
with all earlier passes; finalization cannot turn a failed stage into a gate
pass. A successful final report is possible only when every executed stage is
`PASS`. Startup failure is identified separately if no stage could begin.

The evidence class is limited to specification, offline static/unit/build and
synthetic SIL. Physical evidence is structurally false. The report asserts
that no hardware capture, bench/HIL, robot motion or physical work occurred;
all real model support, accepted CAD, real plant, physical calibration,
measured-limit, runtime route, ROS-actuator mapping and motion counts remain
zero.

The report is a record of one workspace run, so timestamps and environment
identity are expected to change. Canonical means deterministic JSON encoding
and schema semantics, not byte identity across different executions.
