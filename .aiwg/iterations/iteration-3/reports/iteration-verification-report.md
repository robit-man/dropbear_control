# Iteration 3 verification report

- Executed: 2026-07-22T18:45:40-07:00
- Iteration result: `PASS-OFFLINE`
- Hardware commanded: no
- Physical applicability established: no
- Runtime gateway/transport established: no

## Delivery results

| Outcome | Evidence | Result |
|---|---|---|
| Legacy compatibility boundary | Read-only Python/browser/ESP32 64-byte frame audit; direct-dispatch and missing-context risks recorded | PASS discovery |
| Host-link V1 reference | 44 tests, every split point, 100 seeded fragmentation trials, 250 protected-bit corruption/recovery trials, 500 noise chunks | PASS offline reference |
| Generated config views | 15 tests; firmware C++17, host JSON, ROS YAML, UI JSON, simulator JSON, manifest | PASS offline projection |
| Config identity guard | 139 native ASan/UBSan checks plus clang portability | PASS offline native core |
| Cross-layer non-promotion | 4 Python tests and 75 native checks using the tracked generated digest/header | PASS offline composition |
| Unified repository gate | `tools/test_all.sh` including all prior suites and ESP32 compile | PASS |

## Corrective review findings

Initial host-link delivery covered generic connectivity but not both health
domains required by LNK-003, and used lease owner as an implicit producer
identity. Before acceptance, the command body gained an explicit independent
`source_identity`; state gained distinct `DriveHealth` and `BusHealth` enums.
All 44 host-link tests passed again after the correction, and cross-layer tests
prove source and lease-owner identities remain distinct.

## Unified gate snapshot

- Pinned Python verification dependencies: PyYAML 6.0.1 and jsonschema 4.10.3.
- Vendor evidence: 44 models, 53 STEP files (26 assembly/27 flattened), nine
  document sets and 32 PDFs.
- Protocol: 14 Python V4.4 tests and 175 native checks over 34 shared vectors.
- Support: 27 exact-tuple/evidence tests; all 44 catalog identities remain
  unsupported for powered motion.
- Safety/config: 314 safety-supervisor checks, 139 config-guard checks and 75
  generated-config composition checks.
- Simulation: 22 deterministic protocol-state emulator tests; no plant claim.
- Configuration: 23 schema/semantic tests and 15 generated-view tests.
- Link: 44 bounded typed framing/session/fuzz tests plus four generated-digest
  composition tests.
- Governance: 77/77 requirement rows, 20 sources, 10 ADRs, 20 work packages,
  90 test catalog rows and 48 relative links.
- ESP32: compile success, 6.8% RAM and 22.8% flash. The config guard compiles as
  part of the project but is not yet wired to the user’s runtime path.

## What this proves

- One canonical, validated incomplete Dropbear configuration can produce
  byte-reproducible layer projections with a common digest without filling any
  unknown physical facts.
- A V1 link can carry bounded typed source/config/lease/command/state/
  disposition context and reject corrupt, incompatible, stale-session,
  duplicate, reordered, expired or config-mismatched traffic before exposure.
- Link receipt is structurally incapable of setting motion authorization.
- A native guard starts without trust, admits only an externally validated,
  exact, fresh, motion-authorized configuration transaction, rolls back failed
  updates and separately gates arm/TX.
- The actual tracked incomplete generated configuration can traverse the link
  as a candidate but cannot become an active motion configuration or satisfy
  the safety prerequisite.

## What remains open

- Native C++ V1 framing/parser and shared Python/native vectors.
- Real USB/UART/TCP adapter, authenticated session establishment and
  restart-persistent anti-replay state.
- Protected configuration loader, signatures, commit-token authority,
  persistent rollback counter and secure clock policy.
- Gateway arbiter/scheduler composition with queue invalidation and semantic
  dispositions.
- Exact installed motor/topology/limit/calibration evidence and all physical
  gates.
- CAD output articulation, sourced actuator plants, ROS/whole-robot simulation
  and HIL.

The next proposed slice is the native V1/shared-vector and fake-gateway steel
thread. It must consume generated identity, enforce both config and safety
admission, schedule only admitted V4.4 requests against the emulator, and
retain separate receipt/admission/TX/response/observation outcomes.
