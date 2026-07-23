# Iteration 4 verification report

- Assessment date: 2026-07-22
- Result: `PASS-OFFLINE`
- Hardware energized: no
- Exact installed actuator tuple established: no
- Physical, HIL, plant or mechanical evidence produced: no

## Acceptance result

| Acceptance | Result | Principal evidence |
|---|---|---|
| I4-D01 native V1 parity | PASS | 32 shared Python/native vectors; seven message bodies; exact network layout |
| I4-D02 stream recovery | PASS | every split point, one-byte/concatenated input, noise, CRC, overflow and bounded resync |
| I4-D03 typed safety surface | PASS | canonical command/state types; no vendor raw escape; `motion_authorized=false` |
| I4-D04 host lifecycle | PASS | 28 deterministic async connect/negotiate/reconnect/timeout/cancel/replay tests |
| I4-D05 bounded gateway | PASS | fixed routes/queues/response slots/disposition ring and capacity denials |
| I4-D06 last-moment admission | PASS | config revoke, lease expiry, safety fault and replay invalidate queued work before TX |
| I4-D07 response correlation | PASS | exact node/opcode/deadline/chronology; malformed/unexpected/duplicate cases |
| I4-D08 semantic dispositions | PASS | receipt/admission/TX/response/observation/rejection remain separate |
| I4-D09 emulator composition | PASS | six native-link/gateway/emulator scenarios with deterministic fault injection |
| I4-D10 unified evidence | PASS | full `tools/test_all.sh`, trace linter, generated-view check, whitespace and ESP32 build |

## Measured results

| Suite | Result |
|---|---:|
| Python host-link reference | 44 tests passed |
| Shared host-link corpus | 32/32 reproducible vectors: 10 accept, 11 frame reject, 11 body reject |
| Native host-link | 2,472 checks passed under GCC ASan/UBSan and Clang |
| Gateway core | 658 checks passed normal and ASan/UBSan; allocation-symbol audit passed |
| Host gateway session | 28 deterministic async tests passed |
| Native V1/gateway/emulator steel thread | 6 tests passed |
| Existing safety supervisor | 314 checks passed |
| Existing config identity guard | 139 checks passed |
| Existing RMD CAN V4.4 core | 34 vectors; 14 Python tests and 175 native checks passed |
| Traceability | 77 requirements, 77 rows, 20 sources, 10 ADRs, 20 WPs, 90 tests, 48 links |
| ESP32 compile | PASS; 22,360 B RAM (6.8%), 299,213 B flash (22.8%) |
| Unified offline gate | `OFFLINE_GATE_OK` and machine-readable PASS result |

## Evidence boundaries

- The positive motor/configuration tuple is synthetic and exists only in the
  test bridge. All 44 catalog models and the tracked Dropbear configuration
  remain unauthorized for powered actuation.
- The native cores compile in the ESP32 environment but are not wired into the
  user runtime. Host results are not target WCET, task-stack or jitter evidence.
- The fake scheduler has no transport send-result, retry, arbitration-loss,
  bus-off/recovery or real utilization input. TST-FW-002 remains planned.
- A returned TX envelope is not bus delivery. A correlated response is not
  mechanical execution. An explicit observation handoff is not physical shaft
  state or verified safe state.
- No CAD output member has been reviewed; CAD articulation and actuator plant
  support remain 0/44.

## Gate disposition

Iteration 4 is complete at offline/SIL-protocol evidence class. It advances no
physical phase gate. The next offline iteration may begin WP-140 semantic CAD
review/conversion while real adapter and physical discovery work remain under
their existing hold conditions.

