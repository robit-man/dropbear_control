# Legacy host API inventory and migration boundary

Scope: read-only audit of the Python host package before the Iteration 4
gateway-session delivery. This inventory preserves existing work while making
clear which surfaces are regression fixtures and which surface may eventually
become the supported host-to-gateway API. No legacy module was edited during
this audit.

## Executable import topology

Python resolves `myactuator_lib.transport` to the package directory
`transport/__init__.py`, not the adjacent `transport.py` module. Consequently,
the currently imported `Transport` contract is synchronous
`connect`/`disconnect`/`send`/`receive`. The async `open`/`close`/`send`/`recv`
ABC and its three stub backends in `transport.py` are shadowed at normal package
import time.

The legacy layers are split into three parallel object graphs:

| Concern | Imported/tested prototype | Parallel legacy surface | Consequence |
|---|---|---|---|
| Frame | `protocol/frame.py` | `framing.py` | Both implement the 64-byte prototype but use different constructor and sequence-field names |
| Transport | `transport/base.py` + `transport/loopback.py` | `transport.py` and `can_transport.py` | Sync, async and separate CAN-specific lifecycle contracts coexist |
| Device | `device/base.py` | `devices.py` | A sync request helper and an async abstract motor API coexist without one concrete production device |
| ROS | none in the gate | `ros.py` over `devices.MotorDevice` | Command routing reaches only abstract setters; `spin()` is unimplemented |

The offline gate exercises only `protocol/frame.py`, the synchronous loopback
transport and `device/base.py`. It does not execute the shadowed async transport,
the product-scaling layer, SocketCAN, serial bridge, abstract `MotorDevice`, or
ROS runtime path.

## Surface-by-surface findings

### `protocol/frame.py` and `framing.py`

Both encode a fixed 64-byte, little-endian `0xAA55` frame with CRC-16 and an
8-bit sequence. This shape is already classified as the legacy migration
fixture in the Iteration 3 compatibility inventory. It has no version,
negotiated length, link session, full replay counter, configuration identity,
source identity, lease or disposition semantics. Neither copy is a safe
remote-command envelope.

The copies are source-compatible only in concept: the canonical-package class
uses `sequence` and `header_seq`, while `framing.Frame` uses `seq` and carries a
different constructor order/default policy. Code importing one cannot be
silently redirected to the other without explicit migration tests.

### `transport.py`, `transport/` and `can_transport.py`

- `transport.py` defines an async API, but all CAN, serial and EtherCAT methods
  raise `NotImplementedError` and the module name is shadowed by the package.
- `transport/` defines the synchronous API used by the current offline test;
  its only concrete implementation is an in-memory FIFO that identifies itself
  as CAN for testing.
- `can_transport.py` is a third independent synchronous hierarchy over
  `framing.Frame`. It exposes direct SocketCAN and an ESP32 serial bridge, plus
  classic-CAN fragmentation of the 64-byte legacy frame.
- `can_transport.py` is not the V1 gateway link. Its frame/correlation model
  lacks link negotiation, configuration identity, source/lease fields and
  semantic dispositions. Direct CAN also bypasses the intended ESP32 sole
  arbiter.
- The classic-CAN fragmentation design needs separate adversarial review: its
  grouping key is only motor/type/8-bit sequence, buffer lifetime is not
  bounded by a documented deadline, and it is not part of the production
  migration target.

### `device/base.py`, `devices.py` and `protocols.py`

- `device/base.py` constructs legacy 64-byte position/status frames and returns
  whichever frame the loopback produces. It does not correlate a real drive
  response or enforce configuration, lease, limits, health or disposition.
- `devices.py` defines only an abstract async `MotorDevice`; it has no concrete
  family implementation and imports the synchronous transport package.
- `protocols.py` assumes one set of scaling constants across broad product
  families and explicitly leaves rated torque unknown. These family-level
  assumptions do not meet the six-field exact support key
  `(model, hardware revision, drive firmware, protocol, transport, mode)`.
- `protocols.py` builds a synthetic unified protocol, not official V4.4
  eight-byte native messages. Its torque conversion and generic stop/zero
  encodings cannot be used for hardware admission.

### `ros.py`

The bridge provides useful name/state-shape scaffolding and headless routing,
but it binds to the abstract legacy `MotorDevice`, discovers joints with a
regular expression, substitutes zero for missing feedback, and leaves the ROS
runtime unimplemented. It has no quality/age/connectivity fields, exact config
digest, session/lease lifecycle, disposition correlation or safety authority.
It must not be described as a `ros2_control` hardware interface.

## Frozen migration decision

1. `hostlink_v1.py` is the only current byte-contract reference for the future
   host-to-ESP32 link. Iteration 4's native mirror must agree with it through
   shared vectors before any I/O adapter is connected.
2. `gateway_session.py` will be the only new host lifecycle surface. It may
   construct typed V1 messages but cannot expose vendor-native bytes, issue a
   safety lease, or claim motion authorization.
3. Existing frame/transport/device/CAN/ROS modules remain regression and
   discovery fixtures until a later, separately reviewed deprecation or
   adapter work package. They are not deleted or silently aliased.
4. A future real serial/TCP adapter terminates at the bounded V1 parser. A
   future CAN adapter exists only below the ESP32 admission/scheduler boundary;
   direct host-to-drive CAN is outside the Dropbear production architecture.
5. ROS commands must eventually enter the same host session, configuration,
   lease and disposition path as every other client. ROS connection or joint
   naming can never imply command authority.
6. SI-to-native conversion belongs behind an exact, verified configuration
   tuple. Until that evidence exists, positive conversion paths remain
   synthetic tests and the tracked Dropbear configuration remains denied.

## Later cleanup criteria

No legacy module should be removed or renamed until all of the following are
true: import and downstream-use discovery is complete; replacement V1
transport/device/ROS contracts are accepted; migration fixtures cover old
bytes and public imports; deprecation is documented; and the full offline plus
hardware-appropriate gates pass. Cleanup itself is not part of Iteration 4.
