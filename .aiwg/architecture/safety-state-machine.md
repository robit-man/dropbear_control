# Gateway safety state machine

This is the normative offline behavior for [SAF-001..010](../requirements/system-requirements.md).
It is designed for deterministic tests; it is not a functional-safety
certification or hardware stop proof.

## States and permitted output

| State | Entry meaning | Native command permission |
|---|---|---|
| `BOOT` | Reset/startup; identity and integrity not trusted | No native TX except transport-silent initialization |
| `DISCOVERY` | Config valid; observe/probe expected nodes without motion | Read/identity probes only from an allowlist |
| `DISABLED` | Expected nodes known; safe action continuously supervised | Tuple-evidenced motor-off/read traffic only |
| `ARMED` | Compatible lease held; all motion prerequisites pass; zero-motion setpoint established | Motor-off/read and explicitly evidenced zero-command preparation only |
| `ENABLED` | Explicit enable admitted for one owner/mode | One scheduler-owned, admitted command per actuator per slot |
| `SHUTDOWN` | Motion authority revoked; tuple-specific motor-off acknowledgement is pending | Motor-off/read traffic only; safe action has highest scheduler priority |
| `FAULT` | P0 failure latched with context | Tuple-evidenced motor-off/read/fault-clear traffic only; physical cut may be required |

Reset always enters `BOOT`, never `ARMED` or `ENABLED`.

## Transition table

Any transition not listed is rejected and logged without changing state.

| From | Event | Required guard | To | Required action |
|---|---|---|---|---|
| BOOT | `BOOT_OK` | executable/config integrity; transport initialized silent; clock valid | DISCOVERY | Start bounded discovery deadline |
| BOOT | `ANY_P0_FAILURE` | none | FAULT | Latch evidence; inhibit motion; request physical cut if native safe action unknown |
| DISCOVERY | `DISCOVERY_OK` | expected exact identities/capabilities match config; no extra conflicting owner | DISABLED | Begin safe-action verification and state publication |
| DISCOVERY | `DISCOVERY_TIMEOUT_OR_MISMATCH` | none | FAULT | Latch missing/unexpected identity evidence |
| DISABLED | `ARM_REQUEST` | authenticated compatible source; lease valid; safe action observed; limits/calibration/health current | ARMED | Bind owner/mode/config; initialize zero command |
| DISABLED | `DISABLE_REQUEST` | any source | DISABLED | Refresh safe-action request; no implicit clear |
| ARMED | `ENABLE_REQUEST` | owner; fresh command; zero discontinuity policy; physical prerequisites; no fault | ENABLED | Admit next scheduled command only |
| ARMED | `LEASE_LOSS_OR_DISABLE` | none | SHUTDOWN | Revoke owner; request safe action; start acknowledgement deadline |
| ENABLED | `VALID_COMMAND_TICK` | all admission guards pass | ENABLED | Encode/schedule exactly one command; record disposition |
| ENABLED | `DISABLE_REQUEST` | any trusted local or owning source | SHUTDOWN | Preempt normal traffic; request safe action; revoke lease; start acknowledgement deadline |
| ENABLED | `LEASE_LOSS` | none | SHUTDOWN | Preempt traffic; revoke lease; request safe action; record latency |
| SHUTDOWN | `MOTOR_OFF_ACKNOWLEDGED` | Correlated tuple-specific acknowledgement/state evidence is fresh | DISABLED | Record safe-action disposition; continue disabled supervision |
| SHUTDOWN | `SAFE_ACTION_TIMEOUT_OR_FAILURE` | none | FAULT | Latch shutdown context; retain safe-action priority; request physical cut per policy |
| ARMED/ENABLED/SHUTDOWN/DISABLED/DISCOVERY | `P0_FAILURE` | none | FAULT | Preempt traffic; latch first cause plus subsequent events; request safe action |
| FAULT | `RESET_REQUEST` | authorized local/service role; root cause absent; safe action observed; evidence committed | BOOT | Clear latch as an auditable new event; never re-enable automatically |

Lease loss never jumps directly to DISABLED: it passes through SHUTDOWN until
motor-off acknowledgement is observed. The acknowledgement definition and
deadline are exact-tuple evidence; absent or failed evidence enters FAULT.

## Per-tick event priority

Events are totally ordered; lower numbers preempt later processing:

1. independent e-stop/power-removal indication;
2. internal integrity/config/clock failure;
3. native drive critical fault, bus-off or safe-action failure;
4. local hard limit or invalid/aged sensor required for control;
5. lease loss/expiry or owner/config/mode mismatch;
6. disable request;
7. enable/arm request;
8. admitted motion command;
9. bounded diagnostics/read traffic.

If multiple P0 events occur, the first becomes the primary latch and all are
appended to the same transition evidence. No later event may suppress an
earlier safe action.

## Invariants

- `state != ENABLED` implies no motion native opcode may be queued.
- `SHUTDOWN` cannot report completion or transition to DISABLED before a fresh,
  correlated tuple-specific motor-off acknowledgement/state observation.
- At most one active lease and one writer exist for an actuator.
- A queued command is invalid if its lease, config hash, mode or deadline
  changes before TX; admission is rechecked at scheduling time.
- `FAULT` is sticky across link reconnect and configuration reload.
- Unknown identity, capability, limit, safe opcode or brake state prevents
  `ARMED`.
- All time comparisons use wrap-safe monotonic arithmetic; wall time is only
  evidence metadata.
- Reset cannot clear evidence; restart cannot clear a persisted safety latch
  unless the approved hazard policy explicitly permits it.
- The safe-action request is not recorded as “motor stopped” without observed
  tuple-specific evidence.

## Timers and counters

Names are normative; numeric budgets remain configuration values with
provenance and bounds:

`discovery_deadline`, `lease_deadline`, `command_deadline`,
`max_state_sample_age`, `response_deadline`, `max_consecutive_misses`,
`safe_action_deadline`, `bus_recovery_budget`, and `fault_log_commit_deadline`.
Any required missing/out-of-bounds value blocks `BOOT_OK`.

## Fault record

Record state/from/to, primary and secondary reason codes, monotonic and UTC
time, owner/sequence/config hash, exact actuator tuple, last admitted command,
latest samples with ages, transport/bus counters, safe-action request and
observed disposition. Format follows
[evidence-format.md](../testing/evidence-format.md).

The allocation-free
[`fault_evidence`](../../firmware/esp32/src/safety/fault_evidence.h) core now
implements the bounded native subset: primary plus secondary cause records,
boot/monotonic identity, command/config/route context, fixed-unit feedback,
bus counters, CRC32C-protected snapshots, fail-closed required recovery and an
explicit guarded reset that returns only to `BOOT`. It performs no persistence
or physical I/O. A vetted durable adapter, UTC source, audit binding,
tuple-specific motor-off observer and independent power-removal path remain
required.

The allocation-free
[`fault_monitor`](../../firmware/esp32/src/safety/fault_monitor.h) core now
composes configuration consistency, bus-off, consecutive-response budget,
critical drive fault, local-limit and required-feedback validity/age into the
same supervisor and evidence record. It records only deterministic rising
edges in fixed priority order, faults closed on malformed/misbound input and
preempts queued normal gateway traffic. A trusted adapter must still produce
these typed observations and durably commit the resulting snapshot before the
production runtime may rely on them.
