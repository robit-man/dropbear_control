# Canonical Dropbear host-link V1 reference

Status: **offline reference implemented and tested; not a hardware or motion
authorization claim**

Implementation: `host/myactuator_lib/hostlink_v1.py`
Tests: `tests/hostlink/run_tests.sh`

## Boundary and invariants

Host-link V1 carries canonical robot intent and observation between an
established host session and a gateway. It does not carry a native motor frame,
does not grant a lease, does not apply physical limits and does not authorize
the gateway scheduler to transmit. A link-accepted `COMMAND` remains a
candidate for authenticated authorization, exact-tuple support, lease, safety,
limit and scheduler admission.

All multi-byte values are network byte order. Monotonic times are unsigned
64-bit nanoseconds in the sender's clock domain. SI values are finite IEEE 754
binary64 numbers. Text is length-prefixed, strict UTF-8 and bounded.

## Binary envelope

The V1.0 header is exactly 72 bytes:

| Offset | Size | Field | Rule |
|---:|---:|---|---|
| 0 | 4 | magic | ASCII `DBHL` |
| 4 | 1 | major version | `1` |
| 5 | 1 | minor version | `0` |
| 6 | 2 | header length | `72` |
| 8 | 4 | payload length | `0..4096` |
| 12 | 1 | message type | typed values 1..7 only |
| 13 | 1 | flags | bit 0 response, bit 1 urgent-safety; all others rejected |
| 14 | 2 | reserved | zero |
| 16 | 8 | session ID | nonzero; assigned outside this codec |
| 24 | 8 | sequence | nonzero, strictly increasing within an established session |
| 32 | 8 | monotonic timestamp | nanoseconds |
| 40 | 32 | active configuration SHA-256 | raw digest; zero only before an active configuration/session |
| 72 | N | typed payload | exactly `payload length` bytes |
| 72+N | 4 | CRC-32C | Castagnoli CRC over header and payload, initial/final XOR `0xffffffff` |

The standard CRC check value for ASCII `123456789` is `0xe3069283`.

Hard limits are:

- payload: 4,096 bytes;
- complete frame: 4,172 bytes;
- incremental parser buffer: 8,344 bytes;
- one `feed()` input: 8,344 bytes;
- ordinary identifier text: 255 UTF-8 bytes;
- fault description: 512 UTF-8 bytes.

Header length, payload length, message type, flags and reserved fields are
validated before the parser waits for a declared payload. A candidate can
therefore never force an unbounded allocation or resynchronization scan.

## Typed bodies

Body primitives use `u8`, `u16`, `u32`, `u64`, binary64 and `u16 byte-length +
UTF-8`. Decoders reject truncation, trailing data, invalid UTF-8, unknown enum
or mask bits, non-finite numbers and inconsistent cross-envelope data.

| Type | Required semantic content |
|---|---|
| `HELLO` | endpoint/role; one major and a minor range; required/offered capability masks; minimum/maximum/preferred control rates; maximum payload |
| `CAPABILITIES` | accepted/rejected result; selected version, capabilities, rate and payload; or one rejection with all selected fields zero |
| `COMMAND` | canonical actuator ID; exact configuration identity/revision/hash; source identity; lease ID/owner/sequence/absolute monotonic expiry; desired enable; mode; typed finite SI values |
| `STATE` | canonical actuator ID and configuration; sample time and exact age; validity/connectivity/drive-health/bus-health/native-response states; fault and safety state; presence-preserving SI samples; typed native status/error integers |
| `DISPOSITION` | request session/sequence and actuator; one reached phase; phase time; explicit rejection reason |
| `FAULT` | fault code/severity/safety state/time/related sequence; optional canonical actuator and bounded description |
| `HEARTBEAT` | endpoint/role/link health/safety state/uptime/last received sequence |

There is no `RAW`, vendor frame or arbitrary command-byte message.

### Command mode field rules

| Mode | Enable requested | Required SI fields | Permitted optional SI fields |
|---|---|---|---|
| `DISABLE` | false | none | none |
| `POSITION` | true | `position_rad` | `velocity_rad_s`, `effort_nm` |
| `VELOCITY` | true | `velocity_rad_s` | `effort_nm` |
| `EFFORT` | true | `effort_nm` | none |
| `CURRENT_Q` | true | `current_q_a` | none |
| `IMPEDANCE` | true | `position_rad`, `velocity_rad_s`, `stiffness_nm_per_rad`, `damping_nm_s_per_rad` | `effort_nm` |

Missing required or extra mode-inapplicable values reject the complete body.
The exact body configuration hash must equal the envelope hash. Lease expiry
equal to the envelope or receiver evaluation time is expired.

### State and disposition semantics

State field presence is an explicit mask and is distinct from sample validity.
The encoded age must exactly equal envelope time minus sample time. Native
response state differentiates not-expected, pending, valid, timed-out,
malformed and drive-fault observations without forwarding vendor bytes.

Disposition phases are distinct:

1. `RECEIVED`
2. `ADMITTED`
3. `NATIVE_TX`
4. `NATIVE_RESPONSE`
5. `OBSERVED`
6. `REJECTED`

Only `REJECTED` carries a non-`NONE` reason. `NATIVE_TX` does not mean native
acceptance, `NATIVE_RESPONSE` does not prove mechanical execution, and neither
means `OBSERVED`.

## Negotiation

`negotiate(local, peer)` fails closed when:

- either peer is not major V1;
- supported minor ranges do not overlap V1.0;
- either peer's required capabilities are absent from the other's offer;
- control-rate ranges do not overlap; or
- the common payload limit is below 256 bytes.

Otherwise it selects the highest implemented common minor, capability
intersection, smaller payload bound and a deterministic rate within the common
range. The established receiver additionally requires all mandatory V1
capabilities: typed SI commands, config and lease binding, state validity,
semantic dispositions, CRC/resync and session anti-replay.

## Stream recovery and receiver ordering

`StreamParser` accepts fragmented or concatenated frames. It retains at most a
three-byte possible magic prefix from pure noise. Invalid headers and CRCs
discard one byte at the candidate magic and scan again, so a later valid frame
can be recovered even when it follows corruption in the same input. Every scan
and incomplete candidate is bounded by the 8,344-byte buffer and 4,172-byte
frame limits. Overflow is observable and drops oldest data; an over-limit
single feed resets and raises.

`SessionReceiver` is created only from an externally established nonzero
session, nonzero active configuration digest and accepted complete
negotiation. Before decoding or exposing a command it rejects:

1. unsupported envelope version;
2. previous or unknown session;
3. duplicate or reordered sequence;
4. backward monotonic timestamp;
5. inactive configuration hash;
6. malformed typed body; and
7. command expiry at receiver evaluation time.

Every denied result has `message=None`. Every accepted result still has
`motion_authorized=False`.

## Verification and requirement mapping

`tests/hostlink/run_tests.sh` runs 44 deterministic standard-library test
methods. Property-style coverage uses fixed seeds and includes:

- every split point and byte-at-a-time reconstruction;
- 100 random fragmentations of mixed typed frames;
- 250 single-bit protected-region corruptions, each followed by a recovery
  sentinel that must be the only emitted frame; and
- 500 random-noise chunks with buffer-bound and no-frame assertions.

| Requirement | Executable evidence |
|---|---|
| LNK-001 / TST-LNK-001..002 | fixed envelope/CRC/limits, malformed header cases, fragmentation, concatenation, corruption, noise and bounded recovery tests |
| LNK-002 / TST-LNK-003 | all command modes, exact config/lease identity, expiry, finite/missing/forbidden SI value tests and raw-byte absence check |
| LNK-003 / TST-LNK-004 | full/minimal state round trips, age binding, health/native response/fault/safety/config and optional-field tests |
| LNK-004 / TST-LNK-005 | all six disposition phases and invalid phase/reason combinations |
| LNK-005 / TST-LNK-006 | compatible negotiation plus major/minor/capability/rate/payload mismatch tests |
| SEC-002 / TST-LNK-007 | established-session duplicate/reorder/previous-session/config/time/expiry/malformed-body denial tests |

## Deliberate limitations and open evidence

- CRC-32C detects accidental corruption; it is not authentication, integrity
  against an attacker, encryption or source authorization. A production link
  still requires authenticated session establishment and transport/security
  policy.
- Session IDs and monotonic sequence persistence across restart are external
  responsibilities. This in-memory reference alone cannot prevent replay
  after power loss.
- Negotiation proves syntactic compatibility only. It does not prove motor,
  firmware, transport, mode, rate, timing or configuration applicability.
- No physical limits, discontinuity policy, exact-tuple support registry,
  active lease ownership, safety transition, scheduler budget or native codec
  is invoked here.
- `STATE` native status/error integers preserve typed observations but require
  the separately evidenced native codec to assign meaning.
- No serial/USB/TCP adapter, ESP32 implementation, ROS interface, SIL timing,
  HIL capture or powered hardware was exercised by this delivery.
