# Iteration 4 steel-thread scenario matrix

This matrix freezes the cross-layer evidence expected after the three delivery
tracks land. It is an offline composition contract, not an adapter design or a
physical-support claim.

## Required stages

Every scenario records the following stages independently:

1. V1 bytes parsed and typed body exposed (`RECEIVED`).
2. Session/config/lease/shape policy accepted (`ADMITTED`) or a named denial.
3. Config guard and safety supervisor rechecked at queue release.
4. A typed V4.4 request encoded and offered to the fake transport
   (`NATIVE_TX`).
5. A response correlated by node, opcode and deadline (`NATIVE_RESPONSE`) or a
   named missing/malformed/unexpected result.
6. An independent timestamped feedback sample (`OBSERVED`), if one actually
   exists. A drive response alone never creates this stage.

Stages may terminate early but may not be skipped, inferred, or relabeled.

## Deterministic cases

| Case | Change introduced before native TX | Required result | Emulator traffic |
|---|---|---|---|
| ST-01 synthetic accepted current request | none | one request with evidenced A1 scaling; received/admitted/TX/response distinct; no observed claim | exactly one request and one correlated response |
| ST-02 tracked Dropbear config | tracked config is incomplete and motion-disabled | config denial; no native TX | none |
| ST-03 config revoked after enqueue | revoke exact queued generation | queued request invalidated with config reason | none |
| ST-04 config expired after enqueue | advance fake clock to validity deadline | queued request invalidated | none |
| ST-05 lease expired after enqueue | advance fake clock to lease deadline | shutdown intent plus safe-action handling; motion request not sent | safe action only if explicitly scheduled |
| ST-06 safety fault after enqueue | latch external fault | queued motion invalidated; safe-action lane remains serviceable | safe action only |
| ST-07 replayed command generation | reuse consumed config command generation | replay denial; no native TX | none |
| ST-08 replayed safety sequence | reuse consumed owner/session sequence | replay denial; no native TX | none |
| ST-09 wrong response node | inject valid response for another node | unexpected/correlation failure; never observed | one request plus injected wrong response |
| ST-10 wrong response opcode | inject valid response with another opcode | unexpected/correlation failure; never observed | one request plus injected wrong response |
| ST-11 response delay | deliver after request deadline | timeout/deadline disposition; TX remains recorded | one request and late response |
| ST-12 dropped response | consume request, return no response | response timeout; absence does not claim drive ignored request | one request, no response |
| ST-13 drive fault | inject nonzero drive fault status | response and drive fault recorded separately; fault path engaged | one request and fault response |
| ST-14 diagnostic saturation | fill diagnostic budget/queue | control budget and safe action are not starved | bounded diagnostic requests only |
| ST-15 reconnect | replace host link session | pending requests cancelled; prior-session bytes rejected; no lease restored or command resent | none until a new explicit command |
| ST-16 parser corruption | corrupt/noise/fragment native V1 stream | bounded resync; no typed command from corrupt frame | none |

## Positive fixture boundary

The single positive motion case uses an explicitly named synthetic exact tuple
and a test-only configuration whose structural/semantic/motion flags are true.
It may exercise the documented V4.4 q-axis-current scale because that is part of
the reviewed protocol source. It does not assert that a catalog motor or the
Dropbear robot implements V4.4, nor that a real current command is safe.

The tracked Dropbear configuration is a mandatory negative case. Tests must not
modify, copy and relabel it as verified. Any positive fixture is kept under the
test tree and includes `synthetic`, `offline_only`, and `physical_support=false`
markers in its documentation or generated trace.

## Interface constraints

- The native V1 command body contains no native opcode, arbitration ID or byte
  payload.
- SI-to-native conversion occurs inside the gateway boundary and is selected
  only by an exact configuration tuple. A test helper may provide that mapping
  only for the named synthetic fixture.
- The scheduler exposes typed V4.4 frames only to the fake transport boundary;
  it does not add a public host raw-frame API.
- Safe action is limited to the reviewed STOP/SHUTDOWN path. Brake commands
  remain unsupported because applicability and physical semantics are unknown.
- Response correlation and decoding use the canonical V4.4 codec. The emulator
  is not permitted to accept a different, test-only wire shape.

## Evidence labels

Passing this matrix permits only `EXISTS-OFFLINE` or `SIL-PROTOCOL` evidence for
the covered cases. It does not advance any tuple to supported, provide HIL
evidence, validate a physical stop, establish output-shaft CAD completeness, or
provide a motor/rigid-body plant model.
