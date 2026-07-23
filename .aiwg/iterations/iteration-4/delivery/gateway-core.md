# Iteration 4 delivery: bounded fake-transport gateway core

## Outcome

Iteration 4 adds a platform-independent, allocation-free C++11 scheduler core
that composes the existing `ConfigIdentityGuard`, `SafetySupervisor`, and RMD
V4.4 codec. It provides deterministic synthetic-test evidence for request
admission, final transmit authorization, safety-lane priority, bounded response
correlation, and explicit audit dispositions.

This is a fake-transport core. It performs no ESP32, Arduino, TWAI/CAN, serial,
or host-link I/O. The routes in the tests are synthetic and do not establish the
identity or applicability of any installed Dropbear actuator.

Delivered files:

- `firmware/esp32/src/gateway/gateway_core.h`
- `firmware/esp32/src/gateway/gateway_core.cpp`
- `tests/gateway_core/test_gateway_core.cpp`
- `tests/gateway_core/run_tests.sh`

## Composition and boundary

The scheduler uses the existing protocol and safety components directly:

- `rmd_v44_codec` validates request arbitration ID, node, DLC, opcode, and
  payload shape at enqueue, creates safety requests, and decodes responses.
- `ConfigIdentityGuard::authorizeTransmit` is called at the final normal-TX
  boundary using the exact configuration reference and command generation
  captured in the queued submission.
- `SafetySupervisor::authorizeCommand` immediately follows the configuration
  decision at that same boundary using the captured owner, session, and
  sequence.
- `SafetySupervisor::shutdownIntent`, shutdown generation, and fault mask drive
  a separate safety-action lane. Normal authorization is intentionally not used
  in SHUTDOWN/FAULT because that authorization is unavailable in those states.

No code in this delivery depends on the concurrently developed native host-link
layer.

## Fixed capacities

| Resource | Capacity | Overflow behavior |
|---|---:|---|
| Routes | 8 | Invalid core configuration |
| Allowed opcodes per route | 8 | Invalid core configuration |
| Control queue | 8 | `CONTROL_QUEUE_FULL`; request not queued |
| Diagnostic queue | 4 | `DIAGNOSTIC_QUEUE_FULL`; request not queued |
| Response/correlation slots | 8 | `RESPONSE_SLOT_FULL`; no normal TX |
| Disposition ring | 64 | Oldest event overwritten deterministically |

The implementation uses fixed arrays and value copies. It does not use dynamic
allocation, exceptions, RTTI, the Arduino runtime, STL containers, or unbounded
queues.

## Route and admission contract

Each configured route has one canonical nonzero route token and an exact tuple:

`route token + bus ID + RMD node ID + owner ID`

Tokens and bus/node pairs must be unique. Each route has a bounded allowlist of
evidenced V4.4 opcodes. Normal route allowlists may contain only classified
control or diagnostic operations. STOP (`0x81`) and SHUTDOWN (`0x80`) belong
only to the safety-action lane. Brake release (`0x77`) and brake lock (`0x78`)
are unsupported in all lanes.

A submission repeats the entire route tuple deliberately. Enqueue rejects a
missing or crossed route, wrong owner, wrong node/arbitration ID, malformed
request, unknown or disallowed opcode, traffic-class mismatch, safety opcode in
the normal lane, brake opcode, invalid deadline, or bounded-queue overflow.

`ADMITTED` has a deliberately narrow meaning: the request passed route, request
shape, class, opcode, deadline, and bounded-queue checks and was copied into a
queue. It is **not** final configuration authorization, safety authorization, or
permission to transmit. Tests prove that an `ADMITTED` request can later be
rejected after config revocation without a `NATIVE_TX` event.

The queued value includes:

- exact configuration reference (schema identity/digest/generation and
  authorization class);
- command generation;
- safety owner, session, and sequence;
- absolute command deadline;
- canonical route token, bus, node, and owner;
- traffic class and complete request frame.

## Final normal-TX boundary

Immediately before returning a normal `TxEnvelope`, the scheduler:

1. revalidates the stored route, frame, opcode, class, and deadline;
2. verifies that the route has no pending native response;
3. reserves a bounded response slot;
4. calls `ConfigIdentityGuard::authorizeTransmit` with the captured proof;
5. calls `SafetySupervisor::authorizeCommand` with the captured message stamp;
6. creates the transaction and records `NATIVE_TX` only if both decisions allow.

Configuration revocation, identity/digest/generation mismatch, command-
generation replay, safety sequence replay, owner/session mismatch, lease expiry,
safety fault/shutdown, deadline expiry, route mismatch, slot exhaustion, and
time/transaction overflow produce no normal `TxEnvelope`.

The configuration authorization precedes safety authorization. Consequently, a
configuration command generation may be consumed when the subsequent safety
decision fails. This is a conservative fail-closed behavior; callers must issue
a new command generation rather than replay the denied one.

## Deterministic scheduling

Safety actions preempt all normal traffic. During normal operation:

- control is selected first;
- after the configured maximum consecutive control burst, one waiting
  diagnostic is selected if the current cycle still has diagnostic budget;
- `beginCycle` replenishes a fixed diagnostic budget;
- repeating a cycle ID is idempotent and cycle regression is rejected;
- exhaustion leaves diagnostic work queued; it does not create an unbounded
  bypass path.

The tests use a diagnostic budget of one and a maximum control burst of two to
prove the deterministic `control, control, diagnostic, control` order, retained
diagnostic work after budget exhaustion, and replenishment on the next cycle.

## Safety-action lane

The safety lane is bounded, generated from the shared V4.4 codec, and may emit
only configured STOP or SHUTDOWN frames. An unconfigured action is reported as
`SAFETY_ACTION_UNCONFIGURED` and fails closed. Brake commands are never a
fallback.

For each route, the current implementation exposes exactly one dispatch attempt
per `SafetySupervisor` shutdown generation or distinct fault mask. That attempt
is marked when the `TxEnvelope` is returned to the caller. The core has no input
for transport-send success/failure, arbitration loss, bus-off, recovery, or
retry timing. It therefore has no automatic retry or confirmed-delivery
contract. This delivery does **not** complete TST-FW-002 retry/bus-off evidence.

If all response slots are occupied, a safety action may preempt a pending normal
response correlation, choosing diagnostic before control and emitting
`RESPONSE_PREEMPTED_BY_SAFETY`. It never preempts another safety response.

A native STOP/SHUTDOWN echo is only a correlated protocol response. It does not
acknowledge shutdown completion, prove motor-off, prove shaft state, or clear
`SafetySupervisor` shutdown intent.

## Response and observation chronology

Each response slot records exact transmit time, absolute response deadline, and
the time of a valid correlated response. Correlation requires exact bus, node,
and opcode. The result vocabulary distinguishes:

- malformed native frame;
- unexpected node;
- unexpected opcode;
- otherwise unexpected response;
- duplicate response;
- response at or after its exact deadline;
- response timestamp before its native transmit
  (`RESPONSE_BEFORE_TRANSMIT`);
- safety preemption of a pending normal correlation.

Malformed and out-of-order responses do not satisfy or clear a pending slot.

`NATIVE_RESPONSE` records a valid decoded protocol response only. `OBSERVED`
requires a separate explicit `recordObservation` call for a correlated non-echo
state response. Observation before any correlated response, or with a timestamp
before the correlated response, is rejected as
`OBSERVATION_BEFORE_RESPONSE`. Echo and no-state response kinds are rejected as
`OBSERVATION_NOT_STATE`.

Even a valid `OBSERVED` disposition records only the explicit state-sample
handoff named by the caller. It is not evidence of mechanical position, torque,
velocity, motor-off, or safe physical state.

## Audit phases

| Phase | Exact meaning |
|---|---|
| `RECEIVED` | Enqueue API received a submission value |
| `ADMITTED` | Shape/route/class/deadline checks passed and a bounded queue accepted the copy |
| `NATIVE_TX` | A frame was returned to the transport adapter; for normal traffic both final guards allowed |
| `NATIVE_RESPONSE` | A native frame decoded and matched one pending bus/node/opcode transaction in time and chronology |
| `OBSERVED` | Caller explicitly handed off a correlated non-echo state sample in chronological order |
| `REJECTED` | A named admission, authorization, scheduling, chronology, correlation, or capacity rule denied progress |

Each disposition carries an event ID, transaction ID when available, monotonic
timestamp, route, bus, node, opcode, traffic class, safety-lane flag, owner,
session, sequence, command generation, final configuration decision, final
safety result, response kind, and observation class. A `NATIVE_TX` event means
the envelope became visible to the transport adapter, not that hardware accepted
or acted on it.

## Verification

`tests/gateway_core/run_tests.sh` performs two complete runs and an object audit:

- strict host build: C++11, `-Wall -Wextra -Werror -pedantic`, exceptions off,
  RTTI off;
- normal suite: `GATEWAY_CORE_OK checks=658`;
- ASan/UBSan suite: `GATEWAY_CORE_OK checks=658` and
  `GATEWAY_CORE_SANITIZERS_OK`;
- production object undefined-symbol audit rejects dynamic allocation symbols.

The suite covers route uniqueness, multi-node ownership/isolation, malformed and
crossed requests, opcode/class policy, brake prohibition, both queue overflows,
config revoke and identity races, deadline boundaries, config and safety replay,
lease expiry, fault/shutdown races, safety priority, one-attempt safety behavior,
unconfigured safety fail-closed behavior, response-slot safety preemption,
diagnostic budget/anti-starvation, shared-codec safety frames, exact response
correlation dispositions, response timeout, TX/response/observation chronology,
explicit observation, echo limitations, and bounded disposition ordering.

## Remaining limitations and follow-up

- Replace synthetic routes only after installed actuator identity, model,
  interface, owner, firmware, and evidenced opcode tuples are reconciled.
- Add an ESP32/TWAI adapter with explicit send-result, RX, bus-off, recovery, and
  bounded retry inputs. The present core cannot prove native transport delivery.
- Add host-link composition only after its schema and trust boundary stabilize;
  this core intentionally has no dependency on it.
- Add native emulator/live-CAN evidence and hardware-in-the-loop tests. Host
  sanitizer evidence is not ESP32 timing or hardware evidence.
- Define and test shutdown retry policy, rate limits, escalation, and confirmed
  physical safe-state observation. TST-FW-002 remains open.
- Connect correlated telemetry to the higher-level robot state estimator without
  relabeling protocol receipt as a mechanical observation.
- Measure WCET, queue pressure, response latency, and memory use on the selected
  ESP32 target and under the final FreeRTOS/TWAI integration.

