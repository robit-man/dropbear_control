# Dropbear host gateway-session contract

Status: **hardware-free async reference delivered; adapter, authentication and
motion admission remain open**

Implementation: `host/myactuator_lib/gateway_session.py`

Verification: `tests/gateway_session/run_tests.sh`

## Purpose and authority boundary

`GatewaySession` gives the host one lifecycle for connecting, negotiating,
exchanging typed host-link V1 messages, correlating command dispositions and
capturing/replaying link input. It is layered on the canonical
`hostlink_v1.py` parser and receiver.

The following identities remain deliberately distinct:

| Item | Owned by this layer | Authority it does **not** provide |
|---|---|---|
| Transport connection | open/read/write/close lifecycle | authenticated peer or session continuity |
| Link session ID | fresh sequence namespace per connect | operator identity, lease or enable |
| Active `ConfigIdentity` | exact identity/revision/SHA-256 binding | configuration truth, hardware applicability or physical validity |
| External `LeaseContext` | shape/match/expiry checks at send | issuance, acquisition, renewal or gateway safety acceptance |
| Link disposition | exact request correlation and reached phase | mechanical execution or motion authorization |
| Capture/replay | deterministic byte/parser/receiver regression | restored session, lease, evidence level or hardware behavior |

Every `CommandResult` and `ReplayResult` has immutable
`motion_authorized=False`.

Published lifetime bounds are 64 pending command requests, 128 queued typed
events, 512 capture records, 512 records in each lifecycle/parse/rejection/late
diagnostic history and 1,024 never-reused session IDs per `GatewaySession`.
The pending ceiling rejects before write. Histories use deterministic oldest-
first eviction, capture eviction is counted, and session-ID history exhaustion
fails closed and requires a new object.

## Injected interfaces

The implementation uses only the Python standard library and depends on:

```text
AsyncByteTransport:
  async connect()
  async read(maximum_bytes) -> bytes
  async write(bytes)
  async close()

MonotonicClock:
  now_ns() -> uint64

transport_factory() -> a new transport per connection
session_id_factory() -> a fresh nonzero uint64 per connection
```

The production default clock is `time.monotonic_ns`; tests inject a fake
clock, fake transports and deterministic session IDs. Every read requests at
most 4,096 bytes and rejects an adapter that returns more. Input is fed to the
host-link parser, whose hard buffer is 8,344 bytes.

## Lifecycle

The explicit states are:

```text
DISCONNECTED -> CONNECTING -> NEGOTIATING -> ACTIVE
ACTIVE/FAULT/CLOSED -> CLOSING -> CLOSED
CLOSED -> CONNECTING               (reconnect)
CONNECTING/NEGOTIATING/ACTIVE -> FAULT on transport/contract failure
```

Transitions are immutable `LifecycleRecord` values with an injected monotonic
timestamp and reason. `CLOSED` is idempotent. A close failure becomes `FAULT`.
Unexpected EOF, read failure, bounded event-queue overflow, unexpected active
message type or command write failure becomes `FAULT` and invalidates every
pending request.

## Negotiation and sequence ownership

For each new transport:

1. obtain a fresh session ID that has never been used by this object;
2. reset outbound sequence and the bounded parser;
3. host sends typed `HELLO` as outbound sequence 1;
4. gateway must return typed gateway `HELLO` as peer sequence 1, with the exact
   active configuration hash;
5. compute the deterministic V1 version/capability/rate/payload selection;
6. host sends typed `CAPABILITIES` as outbound sequence 2;
7. gateway must return the identical accepted `CAPABILITIES` as peer sequence
   2; and
8. install a new `SessionReceiver` seeded at peer sequence 2, then enter
   `ACTIVE`.

Major, minor, capability, rate, payload, role, configuration, sequence or
selection mismatch fails closed. Concurrent outbound writes share one async
lock and receive exactly one increasing uint64 sequence. A backward injected
monotonic clock is rejected before write. Sequence exhaustion requires a new
session; it cannot wrap.

## Command contract

The public command surface is `CommandIntent`, containing only a canonical
actuator ID, typed host-link mode, desired enable state and finite SI fields.
There is no raw payload, vendor command or native-frame field.

`send_command(intent, lease, ...)` requires an externally supplied immutable
`LeaseContext` containing:

- current link session ID;
- exact active `ConfigIdentity`;
- exact canonical actuator and source identities;
- lease identity, owner, generation and absolute monotonic expiry; and
- exactly one allowed command mode.

Session, config, actuator, mode and unexpired-time equality are checked before
building the canonical host-link `COMMAND`. This object stores no current
lease and has no acquire, restore or renew operation. Passing a lease context
is evidence only that the caller supplied the required facts; the gateway
still performs authoritative authentication, exact support, ownership,
safety, limits and last-moment scheduler admission.

## Pending requests and dispositions

A pending command is keyed by `(request session ID, outbound request
sequence)` before its bytes are written. Its canonical actuator and requested
completion phase are also fixed. Timeouts, caller cancellation, close,
reconnect and fault remove pending work without retransmission.

Disposition values remain separate:

```text
RECEIVED -> ADMITTED -> NATIVE_TX -> NATIVE_RESPONSE -> OBSERVED
           \--------------------------------------------> REJECTED
```

The result retains the exact tuple of received phases and provides separate
accessors for each phase. No later phase is relabeled as an earlier phase.
`REJECTED` completes with its reason. Duplicate, regressed, wrong-actuator,
previous-session and already-completed dispositions are retained as
`LateDispositionRecord` diagnostics and cannot complete another request.

## Reconnect behavior

`reconnect()` performs a close followed by a new connect:

- all pending futures fail with `SessionClosedError`;
- the reader, parser and receiver are discarded;
- a fresh transport and previously unused session ID are required;
- outbound sequence restarts only inside that new session namespace;
- only the two negotiation frames are sent; and
- no command, intent or lease is stored, restored, acquired, renewed or
  automatically resent.

A prior-session frame is rejected by the new receiver even when its CRC,
configuration and command contents are otherwise valid. A prior-session lease
context also fails before command serialization.

Queued state/fault/heartbeat events are cleared on close and before a new
connect. Every returned immutable `GatewayEvent` also carries the exact link
session ID, peer frame sequence and local receive time, so consumers never
receive an untagged body across a reconnect boundary.

## Immutable capture and deterministic replay

Every successful host-link write and every bounded read chunk is copied into a
frozen `CaptureRecord` containing a lifetime-monotonic index, direction,
session, lifecycle state, monotonic capture time and bytes. A 512-record deque
retains the newest records and increments `capture_dropped_records` for each
oldest-first eviction. Within that explicit retention window, inbound capture
retains original fragmentation, noise and corruption rather than only decoded
messages.

`replay_capture()`:

1. requires ordered unique immutable records, one exact target session,
   `ConfigIdentity` and accepted capabilities;
2. feeds inbound chunks to a new `StreamParser`;
3. validates retained gateway `HELLO`/`CAPABILITIES`, when present, only to
   seed the replay window;
4. sends every later complete frame through a new `SessionReceiver`; and
5. returns immutable typed messages, parse errors and receiver rejections.

Replay never runs request completion, creates no live session and reports
`motion_authorized=False`. Repeated replay of the same capture and parameters
is byte/order deterministic.

## Executable evidence

`tests/gateway_session/run_tests.sh` runs **28 deterministic async test
methods** with a fake monotonic clock and fake async byte transports.

| Acceptance | Tests cover |
|---|---|
| lifecycle | disconnected/connect/negotiate/active/closing/closed/fault, idempotent close, connect/EOF/read/write/close behavior |
| bounded parser | fragmented negotiation and state, adapter read bounds, corruption recovery diagnostics |
| negotiation | exact typed hello/capability exchange plus major, capability, config and selected-result mismatch |
| sequence | host hello/capability/command sequence, concurrent command serialization, clock regression and fresh reconnect namespace |
| lifetime bounds | 64-request pre-write rejection, 512-record capture eviction/counting and bounded diagnostic retention |
| command boundary | required external lease; exact session/config/actuator/mode/expiry; typed source/lease body; no raw/vendor API |
| correlation | each disposition phase separately, rejection reason, timeout, cancellation, close and fault invalidation |
| reconnect | new session/receiver, pending cancellation, stale-event clearing/session-tagged new events, previous lease denial, no automatic command resend |
| adversarial input | corruption, previous-session frame, config mismatch and late disposition cannot complete a current request |
| capture/replay | frozen records, fragmented/noisy corrupt capture, deterministic repeated parser/receiver replay and replay rejection preservation |
| authority | command/replay results remain `motion_authorized=False`; no acquire/restore lease API |

## Limitations and next evidence

- The async transport is an injected interface. No serial, USB, TCP or ESP32
  adapter, reconnect backoff or OS device discovery is implemented here.
- Session IDs are fresh within one object but are neither authenticated nor
  restart-persistent. Secure entropy alone does not authenticate a gateway.
- CRC-32C is not malicious integrity protection. Authentication, encryption,
  authorization roles and persistent replay defense remain external.
- `asyncio.wait_for` request/handshake timeouts use event-loop elapsed time;
  the injected monotonic clock supplies protocol timestamps and lease checks.
- Capture records may contain sensitive canonical host-link state and require
  an external retention/redaction/access policy. The in-memory ring is a
  bounded diagnostic window, not durable evidence storage; eviction can remove
  negotiation context or split a fragmented frame.
- Replay validates link behavior only. It does not reproduce gateway safety,
  native scheduling, actuator plant timing, estimator behavior or wall-clock
  scheduling jitter.
- A received disposition is a peer statement. This layer cannot prove native
  transmission, response authenticity, observed mechanics or safe stop.
- No exact motor tuple, powered hardware, CAN adapter, ESP32 task, ROS 2
  lifecycle, HIL timing or robot release evidence is claimed.
