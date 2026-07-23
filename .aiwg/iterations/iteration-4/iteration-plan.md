# Iteration 4 dual-track plan — native V1 and fake-gateway steel thread

- Iteration status: `COMPLETE-OFFLINE`
- Phase context: P1 / Elaboration
- Delivery scope: native portion of WP-060, offline WP-080 scheduler steel
  thread, and host lifecycle/replay foundation for WP-110
- Discovery horizon: real ESP32 byte-stream/CAN adapters and exact physical
  configuration inputs
- Safety boundary: fake transports only; no user serial-path replacement, raw
  native public commands, hardware initialization, powered output or physical
  support claim

## Intent

Prove that the Python host contract and allocation-free native gateway agree
on bytes and semantics, then run an admitted request through a bounded native
scheduler against the deterministic V4.4 emulator. Preserve distinct
receipt/admission/native-TX/native-response/observation outcomes and invalidate
queued work if its config, lease or safety state changes before TX.

## Delivery acceptance

| ID | Outcome | Required evidence |
|---|---|---|
| I4-D01 | Native V1 parity | C++11/no allocation/exceptions/RTTI; exact shared golden frames for all seven types; strict bounds/CRC/version/type/flags/reserved checks |
| I4-D02 | Native stream recovery | fragment/concatenate/noise/corrupt/overflow tests; bounded buffer and deterministic resync |
| I4-D03 | Typed native safety surface | command exposes canonical source/actuator/config/lease/mode/SI only; state includes validity/connectivity/drive+bus health/fault/safety; no vendor raw escape |
| I4-D04 | Host session lifecycle | connect/negotiate/active/reconnect/shutdown states, no auto lease restore, cancellation/timeout/config mismatch and deterministic replay tests |
| I4-D05 | Bounded gateway queue | fixed capacity, unique route/owner, request shape validation, priority/budget/deadline rules and observable denials |
| I4-D06 | Last-moment dual admission | config guard and safety lease are checked at TX, not merely enqueue; config revoke, lease expiry, safety fault and replay invalidate queued work |
| I4-D07 | Native response correlation | response ID/opcode/node/deadline/malformed/unexpected handling via the canonical V4.4 codec |
| I4-D08 | Semantic dispositions | received/admitted/TX/response/observed/rejected phases cannot be collapsed or skipped in evidence reporting |
| I4-D09 | Emulator composition | fake native TX reaches only the protocol-state emulator; drop/delay/unexpected/drive-fault cases are deterministic and remain non-plant evidence |
| I4-D10 | Unified evidence | Python/native sanitizers, shared-vector parity, ESP32 compile, traceability and full offline gate pass |

## Design constraints

- Published V1 limits are ceilings. A native implementation may choose smaller
  static limits but must negotiate them and reject larger input.
- Native host-link CRC/frame parsing owns no lease or configuration trust.
- The scheduler accepts only typed, internally constructed native requests;
  public host bodies never contain vendor bytes.
- A queue slot carries exact config generation, safety owner/session/sequence,
  native node/opcode and absolute deadline.
- A request is authorized exactly at release-to-transport. Enqueue-time checks
  are advisory and cannot substitute for the final config/safety checks.
- A missing response does not prove a command was ignored.
- Response receipt and decoded drive state are not mechanical observation.
- The tracked Dropbear config remains incomplete/non-enableable. Synthetic
  verified identities used to exercise positive paths are test fixtures only.

## Definition of Done

- [x] I4-D01..I4-D10 have executable evidence.
- [x] Shared Python/native vectors are generated/reviewed deterministically and
  cover every message type plus representative rejection cases.
- [x] Native cores compile under host sanitizers and the ESP32 environment.
- [x] Queue invalidation races are exercised with a fake monotonic clock.
- [x] Host reconnect creates no safety lease or motion authority.
- [x] The emulator remains protocol-only and receives no command when any
  config/safety/scheduler guard denies.
- [x] Existing user-owned firmware/web/serial changes remain preserved and
  were not overwritten by this iteration.
- [x] Unified gate, traceability, generated drift and whitespace checks pass.
