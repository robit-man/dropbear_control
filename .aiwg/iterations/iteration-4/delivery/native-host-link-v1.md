# Iteration 4 delivery — allocation-free native host-link V1

- Scope: offline C++11 parity implementation of
  `host/myactuator_lib/hostlink_v1.py`
- Hardware I/O: none
- Motion authorization: never; link acceptance remains only a candidate for
  configuration admission and `SafetySupervisor`
- Vendor-native/raw command escape: none
- Physical or motor applicability established: no

## Delivered artifacts

| Artifact | Purpose |
|---|---|
| `firmware/esp32/src/hostlink/hostlink_v1.h` | Fixed-size public types, typed message surface, envelope, negotiation, stream parser and established-session receiver |
| `firmware/esp32/src/hostlink/hostlink_v1.cpp` | Network-order codec, CRC-32C, validation, resynchronization and replay/config gate |
| `tests/hostlink_native/generate_golden.py` | Authoritative deterministic corpus generator using the Python V1 implementation |
| `tests/hostlink_native/golden_hostlink_v1.tsv` | 32 shared frames: 10 accepted, 11 rejected at envelope decode and 11 rejected at typed-body decode |
| `tests/hostlink_native/verify_golden.py` | Reproducibility and Python decode/round-trip verifier |
| `tests/hostlink_native/test_hostlink_v1.cpp` | Native parity, validation, stream and session checks |
| `tests/hostlink_native/run_tests.sh` | Python/native, sanitizer, allocation-symbol and Clang portability gate |

## Wire contract

The native envelope is byte-for-byte V1, not a platform reinterpretation:

| Offset | Width | Field |
|---:|---:|---|
| 0 | 4 | `DBHL` magic |
| 4 | 1 | major `1` |
| 5 | 1 | minor `0` |
| 6 | 2 | header length `72` |
| 8 | 4 | payload length |
| 12 | 1 | one of seven message types |
| 13 | 1 | known response/urgent-safety flags only |
| 14 | 2 | zero reserved field |
| 16 | 8 | non-zero session ID |
| 24 | 8 | non-zero sequence |
| 32 | 8 | monotonic nanoseconds |
| 40 | 32 | active configuration SHA-256 or the permitted zero sentinel |
| 72 | bounded | typed payload |
| final | 4 | big-endian CRC-32C over header and payload |

All integer and IEEE-754 binary64 fields use network order. The CRC uses the
Castagnoli polynomial with all-one initial/final XOR and produces the standard
`123456789 -> 0xe3069283` check value.

The native implementation adopts the full published ceiling rather than a
smaller dialect: 4096 payload bytes, 4172 frame bytes, 8344 parser-buffer/feed
bytes and a negotiated payload no greater than 4096. Accepted negotiation must
still select at least 256 bytes. Both peers' version, capabilities, rate ranges
and payload limits participate in the same deterministic selection as Python.

## Closed typed surface

The native `TypedMessage` has fixed-storage members only for `HELLO`,
`CAPABILITIES`, `COMMAND`, `STATE`, `DISPOSITION`, `FAULT` and `HEARTBEAT`.
There is no raw payload or vendor-command member. In particular:

- `COMMAND` includes the explicit `source_identity`, exact actuator/config,
  lease identity/owner/sequence/deadline, enable request and six named SI
  fields;
- all six command modes enforce the Python required/allowed presence masks and
  enable/mode relationship;
- `STATE` carries separate `DriveHealth`, `BusHealth`, native-response state,
  fault/safety state, validity/connectivity and optional native status/fault
  values;
- every optional numeric field preserves presence independently and every
  present binary64 value must be finite;
- configuration IDs/revisions, actuator IDs, source/lease identities and
  status codes use bounded UTF-8 and the same exact-identifier exclusions;
- command lease, state sample age, disposition time and fault occurrence are
  cross-checked against the envelope;
- command/state body digest must exactly equal the envelope digest.

`SessionReceiver` applies established-session version, exact session,
strictly increasing sequence, non-regressing timestamp, exact active digest,
typed-body and live-command checks before exposing a message. It always
reports `motion_authorized=false`.

The Python API raises `ValidationError` when a caller supplies an evaluation
time earlier than the frame timestamp. The exception-free native mapping is
explicit and fail-closed: `ReceiveDenial::INVALID_EVALUATION_TIME` with
`Status::CROSS_ENVELOPE_MISMATCH`. It therefore never returns an ambiguous
denial of `NONE` for that invalid caller input.

## Bounded incremental parsing

`StreamParser` owns a fixed buffer and scratch frame. `feed()` supports every
fragment boundary, single-byte feeds and concatenated frames. It retains at
most the three-byte prefix of a partial magic value, reports noise/header/CRC/
overflow events, discards one byte after a corrupt candidate and continues to
the next valid `DBHL` envelope. A feed above 8344 bytes resets and returns
`FEED_TOO_LARGE`; accumulated data never exceeds the fixed bound. Delivered
frames are callback values valid for the duration of that callback, so callers
must copy only the bounded fields they need or decode immediately.

## Memory and toolchain evidence

Measured with GCC on the current x86-64 verification host:

| Type | `sizeof` |
|---|---:|
| `Frame` | 4168 bytes |
| `TypedMessage` | 5136 bytes |
| `StreamParser` | 12520 bytes |

ABI padding can differ on ESP32, so the target build must measure these again.
The full-ceiling parser should be a long-lived static/global or explicitly
owned subsystem object, not a control-task stack local. Its callbacks should
decode using reused static/owner storage rather than placing `StreamParser`,
`Frame` and `TypedMessage` together on a small ESP32 task stack. Multiple links
must budget one parser buffer/scratch record per concurrent parser.
The current GCC `-fstack-usage` report shows a 240-byte largest individual
library function frame; encoding writes directly into caller-owned output and
does not hide a full `Frame` on its own stack. Nested call depth and ESP32 ABI
still require target measurement.

The native translation unit compiles as C++11 with warnings-as-errors,
`-fno-exceptions` and `-fno-rtti`, includes no Arduino dependency, and its
object-file audit finds no allocation or exception-runtime symbol. GCC
ASan/UBSan and a separate Clang build both pass.

## Executable result

Run:

```sh
tests/hostlink_native/run_tests.sh
```

Current result:

- Python reference: 44 tests passed;
- shared corpus: 32/32 generator-reproducible Python vectors, comprising 10
  accepts, 11 envelope rejects and 11 typed-body rejects;
- native GCC ASan/UBSan: 2472 checks passed;
- native Clang portability: the same 2472 checks passed;
- allocation/exception symbol audit: passed.

The native checks include byte-exact native encoding of all seven reference
messages and three boundary frames, full shared-corpus decode behavior, all
command modes, optional-field masks, non-finite and cross-envelope negatives,
negotiation, full bounds, every split point, one-byte concatenation, noise,
partial magic, CRC corruption, overflow/feed closure and established-session
replay/config/expiry behavior.

## Limitations and next integration evidence

This codec is not a transport, authenticated channel, secure session
negotiator, configuration loader, clock authority, command lease issuer,
gateway admission decision or motor safety mechanism. Production work still
must bind it to the configuration identity guard and safety supervisor, define
static ownership/task scheduling, authenticate peers/session establishment,
set timeout/backpressure policy, fuzz on the target compiler, prove persistent
anti-replay boundaries across reboot, and verify denial-to-physical-safe-state
behavior in SIL/HIL. No current result authorizes powered motor operation.
