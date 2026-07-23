# Legacy 64-byte link compatibility inventory

Scope: read-only audit of the current user-owned browser, Python and ESP32
prototype paths. No source behavior was changed. These observations are
migration fixtures for WP-060-T01; they are not requirements for host-link V1.

## Implementations observed

| Layer | Path | Current role |
|---|---|---|
| ESP32 packed frame | `firmware/esp32/src/serial_frame.h` | Header-only 64-byte pack/unpack and CRC-16 |
| ESP32 dispatch | `firmware/esp32/src/serial_bridge.cpp` | USB serial byte ingest, direct controller calls, synthetic status output |
| Python host | `host/myactuator_lib/protocol/frame.py` | Matching 64-byte pack/unpack |
| Browser | `web/js/protocol.js` | Matching dashboard/toy-simulator frame implementation |

The three frame implementations currently agree on a 64-byte shape with
little-endian `0xAA55`, 8-bit frame/header/body sequence fields, 32-byte fixed
payload, CRC-16/CCITT-FALSE over bytes 0..42 and 19 unchecked padding bytes.
That cross-language agreement is useful as a regression fixture only.

## Gap and disposition matrix

| Legacy characteristic | Risk / ambiguity | V1 disposition |
|---|---|---|
| Two-byte sync and fixed 64-byte framing | No explicit version, header length or payload length | New magic plus explicit major/minor, header length, payload length and bounded total length |
| 8-bit sequence and independent `headerSeq` | Wraps quickly; no defined relationship, replay window or ordering rule | One 64-bit session-scoped sequence with strict receiver policy |
| No session identifier | Reconnect/restart traffic can be mistaken for current authority | Random/negotiated nonzero session identity; prior-session rejection |
| No monotonic time or expiry | Commands cannot express freshness or bounded lifetime | Envelope timestamp plus explicit lease/command expiry |
| No configuration identity | Host/firmware can act on different topology/limits | Exact configuration ID, revision and SHA-256 on every relevant message |
| CRC-16 only; reserved/padding unchecked | Corruption detection exists, but canonicality and extension behavior are undefined | CRC-32C plus strict flags/reserved/length validation |
| Fixed payload silently zero-padded | Actual field presence and command-specific requirements are ambiguous | Typed bodies with exact lengths and mode-specific required fields |
| `motorId` and broadcast zero | No canonical actuator identity or verified bus ownership | Canonical actuator ID in the host contract; native address remains gateway-private |
| Position/velocity/torque command frame types | ESP32 dispatch calls `MotorController` directly with no config, lease or safety admission | Legacy command frames never enter V1 admission; migration adapter must terminate before the sole arbiter |
| Torque payload decoded as N·m | No evidenced torque constant; status writes controller current into a torque field | V1 uses explicitly typed q-axis current unless an exact tuple later supplies a reviewed torque transform |
| Diagnostic and firmware-update public types | No role/authentication/capability or bounded diagnostic budget | No raw native-frame or update command in the V1 control surface; future management plane is separately authorized |
| Broadcast commands accepted | Can target an unintended actuator and bypass unique ownership | V1 commands require one canonical actuator and exact lease scope |
| Frame type/reserved/padding not fully canonicalized | Multiple byte representations and unknown types can pass CRC | Unknown message type/flag/reserved/body length rejects |
| Serial logs share the frame stream | Resync work and observability depend on arbitrary text noise | V1 parser is bounded and noise-tolerant; production transport should separate machine frames from logs |
| Direct periodic status | No sample age/validity/connectivity/native-response/disposition semantics | Typed state and disposition messages preserve each stage separately |

## Compatibility policy

1. Keep the legacy Python/JavaScript/C++ tests so user work is preserved and
   regressions remain visible.
2. Do not make V1 byte-compatible with the 64-byte frame. Silent dual
   interpretation would retain the unsafe omissions above.
3. If a migration adapter is later needed, it must be a named untrusted edge:
   decode legacy input, assign no authority, require canonical identity/config
   lookup and submit a fresh intent through the same lease/safety admission
   path as every other client.
4. Never forward the legacy `DIAGNOSTIC` payload as raw MYACTUATOR bytes.
5. The current `SerialBridge` remains disconnected from the production-path
   codec and safety cores until a separately reviewed adapter/scheduler slice.

## Required frozen migration fixtures

- Python/JavaScript CRC vector reported by existing tests (`0xef0e`).
- Fragmented/noisy 64-byte browser stream cases from `web/test/`.
- Position, velocity and current/"torque" payload examples, labeled with their
  current observed interpretation and the V1 rejection/migration decision.
- Sequence wrap and reconnect cases that demonstrate why no legacy command
  authority can be carried into a new V1 session.
