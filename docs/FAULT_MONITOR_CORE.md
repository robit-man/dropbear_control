# Deterministic multi-source fault monitor

Status: `EXISTS-OFFLINE`; no physical safe-state or motor-off claim.

[`fault_monitor.h`](../firmware/esp32/src/safety/fault_monitor.h) and
[`fault_monitor.cpp`](../firmware/esp32/src/safety/fault_monitor.cpp) provide
the allocation-free fault-arbitration core for `SAF-005` and `TST-SAF-005`.
The core binds one exact
[`SafetySupervisor`](../firmware/esp32/src/safety/safety_supervisor.h) to one
recovered
[`FaultEvidenceCore`](../firmware/esp32/src/safety/fault_evidence.h). It
performs no storage, clock, configuration, bus, sensor, actuator or power-cut
I/O.

## Typed inputs and policy

A trusted adapter supplies one monotonic observation containing:

- configuration consistency;
- bus-off state and cumulative bus counters;
- consecutive native-response timeouts;
- a critical drive-fault indication;
- a local-limit violation indication;
- explicit feedback validity, generation and sample/receive times; and
- the exact admitted command, feedback and bus context to preserve if a fault
  rises.

The policy requires a nonzero response-timeout budget, a nonempty known
feedback-field mask and a nonzero maximum feedback age. Unknown feedback bits,
a response streak larger than its cumulative counter, future or reversed
feedback timestamps, hidden values behind an absent feedback mask, clock
regression, policy error, missing evidence recovery or supervisor/evidence
misbinding all fault closed as evidence-integrity failures.

The monitor does not discover these facts and does not validate their physical
origin. Production adapters must bind them to the active configuration,
installed tuple, native transaction ledger, independently reviewed limits and
trusted feedback sources.

## Deterministic arbitration

Each observation evaluates six causes in one fixed order:

1. configuration mismatch;
2. bus off;
3. response-timeout budget exceeded;
4. critical drive fault;
5. local-limit violation; and
6. required feedback missing or stale.

Only a rising edge appends an event. Simultaneous causes retain the first as
the primary event and append the others as ordered secondary events. A
continuing level cannot flood the bounded evidence record; after a healthy
observation, a later rising edge is recorded again. Healthy observations
never clear the durable-latch state held by `FaultEvidenceCore`.

Every accepted event enters `FAULT`, clears output permission and preserves
the supplied command, feedback and bus context. The gateway's existing final
safety boundary then suppresses queued normal control and emits its
route-specific STOP/SHUTDOWN request. That native frame is only a software
safe-action request. It is not proof that the frame was transmitted, accepted,
executed, that the actuator stopped, or that independent power was removed.

## Native transport boundary

`GatewayTransportRuntime` now preserves two related distinctions:

- native receive or transmit bus-off raises `BUS_OFF`, while other transport
  failures remain `EXTERNAL`; and
- expired native-response slots accumulate a configurable consecutive streak.
  A streak equal to the budget is allowed, while the next miss raises
  `RESPONSE_BUDGET_EXCEEDED` before transmit polling. An accepted correlated
  response resets the streak.

The timeout fault and bus-off handling reach the same supervisor/gateway
preemption path in the focused runtime tests. The runtime does not yet provide
the trusted context adapter or persistence transaction needed to call the
fault monitor in production. That composition remains a required ESP32
integration task.

## Verification

Run:

```bash
tests/safety/run_tests.sh
tests/gateway_transport_runtime/run_tests.sh
```

The safety suite executes 596 focused monitor checks for each individual
source, all six simultaneous sources, fixed priority, duplicate suppression,
clear/re-rise behavior, exact response and feedback-age boundaries, complete
context retention, bounded overflow, malformed input, recovery omission,
clock regression and binding/policy failures. Every individual source is
injected after an IQ command is queued; the next final-boundary frame must be
STOP and never IQ.

The monitor lane passes GCC, GCC ASan/UBSan, Clang and an undefined-symbol
allocation audit. The transport lane executes 11 normal and sanitized cases,
including exact timeout-budget and bus-off fault classification.

Production completion still requires a vetted ESP32 observation adapter,
durable fault-snapshot transaction, UTC/audit binding, exact installed-unit
identity, reviewed drive/limit/feedback mappings, real controller recovery,
tuple-specific motor-off observation and independent power removal.
