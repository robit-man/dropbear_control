# Iteration 3 delivery — configuration identity admission guard

- Scope: offline, platform-independent configuration identity and admission
  state
- Related work: WP-030 generated-view admission and WP-060 bounded host-link
  identity handoff
- Hardware I/O: none
- Automatic actuator enable: none
- Cryptographic verification: external responsibility; this guard only
  compares an already calculated 32-byte SHA-256 digest
- Physical or model/firmware applicability established: no

## Delivered boundary

`ConfigIdentityGuard` is separate from `SafetySupervisor` and composes with it
at two explicit adapter boundaries:

1. `authorizeArm()` supplies the `configuration_valid` prerequisite used for
   discovery, arming and continued operation.
2. `authorizeTransmit()` must allow the exact active configuration and a fresh
   command generation before the adapter asks `SafetySupervisor` to authorize
   that command's owner/session/sequence.

Neither class calls the other, accesses hardware, enables outputs, verifies a
signature, computes a digest, loads a file or claims motor-off. Revocation must
be propagated by the adapter into the supervisor prerequisite and physical
shutdown paths.

## Identity and transaction contract

| Field | Bound/invariant |
|---|---|
| Configuration ID | Explicit length plus 32-byte fixed storage; 1–32 non-NUL bytes and canonical zero padding |
| Digest | Exactly 32 bytes; compared byte-for-byte; all-zero identity rejected |
| Schema | Unsigned 16-bit version inside a configured inclusive compatibility range |
| Revision | Non-zero and strictly greater than every successfully staged revision |
| Update generation | Non-zero and strictly greater than every successfully staged generation |
| Validity | Absolute monotonic millisecond deadline; invalid at the exact deadline |
| Authorization | Candidate must explicitly carry `motion_allowed=true` and class `MOTION` |
| Commit token | Fixed 16-byte non-zero token plus the exact staged generation |
| Command generation | Non-zero, strictly increasing within the active generation |

The external loader presents both a candidate and a trusted expectation. The
guard requires exact configuration ID, digest, revision, schema and update
generation agreement, plus external structural and semantic validation flags.
Supplying a candidate as its own expectation does not establish authenticity;
the expectation and validation evidence must cross a separately trusted
boundary.

Staging does not mutate the active record. Commit replaces the active record
only after an exact generation-correlated token match. A malformed, stale,
expired or mismatched candidate, and a failed commit, leave the prior active
configuration byte-for-byte unchanged. Starting another staging attempt
invalidates an abandoned staged transaction. Successfully staged revision and
generation numbers cannot be reused even if that transaction is later revoked.

Boot contains no active trusted record. Commit resets command-generation replay
state but does not arm or enable anything. Revoke is immediate and makes both
arm and transmit admission return `REVOKED`; it retains the last active record
only for audit/snapshot visibility. Monotonic-clock regression also revokes and
clears staging.

## Stable decisions

`ConfigDecision` uses explicit numeric values and `DecisionCode()` exposes
stable strings for adapter telemetry. Denials distinguish missing/revoked/
expired state, malformed identity, each identity component mismatch, schema,
external validation, motion permission, authorization class, validity,
revision/generation monotonicity, staged transaction/token correlation and
command-generation replay.

## Executable evidence

Run:

```sh
tests/config_admission/run_tests.sh
```

The runner uses C++11, warnings-as-errors, `-fno-exceptions`, `-fno-rtti`, and
ASan/UBSan by default. Set `SANITIZE=0` only for toolchains without sanitizer
support. The suite currently executes 139 checks covering:

- fixed-size identities/tokens and stable decision codes;
- empty boot trust and absence of automatic enable;
- schema, structural, semantic, motion and authorization gates;
- exact expected ID/digest/revision/schema/generation comparisons;
- invalid identity, deadline and commit-token rejection;
- atomic update success, token mismatch and rollback;
- stale revision/generation rejection without active-state mutation;
- exact arm and transmit identity admission;
- fresh command generations and stale/replay denial;
- deadline, explicit revoke and clock-regression closure;
- composition with `SafetySupervisor`, including missing/tampered/stale config,
  successful dual authorization and propagated revocation faulting closed.

## Limitations and remaining evidence

This is an identity/admission state machine, not a secure loader or root of
trust. Production integration still needs canonical configuration generation,
trusted digest/signature verification, authenticated transport, protected
commit-token issuance, monotonic persistent counters across reboot, secure
clock/deadline policy, non-volatile rollback protection, adapter wiring into
the ESP32 task/transport boundary, and hardware evidence that denied software
transmission corresponds to the required physical safe state.
