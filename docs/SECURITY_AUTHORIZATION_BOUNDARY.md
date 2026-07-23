# Security authorization and audit boundary

Status: `OFFLINE-REFERENCE`; no production authentication, secure transport,
credential store, signed update path, physical action or motion authority.

This specification is the WP-170 least-privilege boundary shared by the Python
reference and allocation-free C++11 core. It converts a previously verified
identity assertion into either a stable denial or permission to evaluate the
later command-admission gates. A pass is deliberately named
`PASS_TO_NEXT_GATE`; it is never motor permission.

## Trust boundary and non-authority

```text
vetted credential + secure-transport adapter                 OPEN
  -> authenticated, bounded-lifetime identity assertion
  -> security authorization core                             IMPLEMENTED OFFLINE
  -> exact configuration/source/graph admission
  -> lease ownership and expiry
  -> local safety state/prerequisites
  -> limits/discontinuity/scheduler/protocol encoding
  -> independently controlled physical transport             OPEN
```

The authorization core does not parse credentials, store passwords or private
keys, select cryptographic primitives, validate certificates, verify
signatures, establish TLS/serial protection, persist replay state across boot,
or attest a device. Its `authenticated` and artifact-integrity inputs are
trusted assertions that a future reviewed adapter must construct; accepting
them from a client would violate this boundary.

Authentication, authorization, audit, safety admission and independent power
removal are separate controls. No one substitutes for another. Loss of an
authentication or audit prerequisite is a fail-closed security event and must
also cause the safety supervisor to move toward shutdown. Independently
testable physical power removal remains outside software.

## Closed role/action matrix

There is no wildcard or administrator role. Unknown enum values deny.

| Role | Read state | Diagnostics | Motion request | Disable request | Fault reset | Stage / activate config | Stage / activate firmware | Submit evidence |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Observer | yes | no | no | no | no | no | no | no |
| Diagnostic operator | yes | yes | no | no | no | no | no | no |
| Operator | yes | yes | yes | yes | no | no | no | no |
| Safety operator | yes | yes | no | yes | yes | no | no | no |
| Configuration manager | yes | yes | no | no | no | yes | no | no |
| Firmware manager | yes | yes | no | no | no | no | yes | no |
| Evidence reviewer | yes | yes | no | no | no | no | no | yes |

A physical fault reset or activation additionally requires verified local
presence. Config and firmware activation require a current rollback guard and
a separately authenticated, non-revoked evidence reviewer whose actor differs
from the initiating manager and whose approval binds the exact artifact
digest. These assertions do not prove a signature implementation exists.

## Deterministic denial order

Each request is evaluated in this order:

1. closed enums, nonzero fixed-size digests, session interval and request
   structure;
2. authentication assertion, revocation and bounded validity;
3. exact session binding and strictly increasing sequence;
4. closed role/action matrix;
5. global physical enable, remote physical enable, remote administration and
   local-presence policy;
6. exact active configuration, source-registry generation and graph-registry
   generation digests;
7. command lease and downstream safety-admission readiness for motion;
8. artifact-integrity assertion for config/firmware staging;
9. rollback guard and independent scoped review for activation; and
10. audit-path health and bounded capacity.

A fresh authenticated sequence is consumed even if a later check denies it.
Changing policy or state therefore cannot make an already attempted request
replayable. Current authorization replay state is session-local and volatile.
The separate artifact transaction core now defines reboot-persistent state and
receipt semantics, but the encrypted persistent adapter and power-loss
evidence remain open.

Default policy sets physical actuation, remote physical actuation and remote
administration to false. A physical-remote motion request passes this core only
when both physical flags are explicitly enabled, all exact generation
bindings match, the lease is valid, and downstream safety admission reports
ready. The resulting pass still grants no motion and must traverse every
remaining gateway gate again at transmit time.

## Bounded audit contract

Audit events contain only fixed-size digests and closed numeric context:

- actor, session, authentication-context and correlation digests;
- role, action, target, decision and safety state;
- monotonic time and authenticated-session sequence;
- config, source-generation, graph-generation and artifact digests; and
- lease-valid and safety-admission-ready observations.

The API has no credential, password, bearer token, private key, command
payload, setpoint or free-form detail field, so those values cannot be copied
into this log. Production persistence still needs access control, retention,
integrity, time/boot identity, export and privacy review.

The normal audit lane never overwrites. When full, a request that would pass
is denied with `AUDIT_CAPACITY_EXHAUSTED`. A separate bounded safe-disable lane
prevents diagnostic traffic from consuming the safe-action reserve; it retains
the newest events and exposes an overwrite counter. If either required lane is
unavailable, the request is denied with `AUDIT_UNAVAILABLE`, and the caller
must independently fail safe. A durable external audit sink remains open.

## Degraded-mode matrix

| Lost or invalid input | Result | Forbidden fallback |
|---|---|---|
| Authentication assertion / secure session | deny | trust CRC, client IP, UI login or serial possession |
| Identity revocation/expiry status | deny | extend on activity or accept a previous session |
| Config/source/graph generation identity | deny control-sensitive action | “latest,” family match or client-selected identity |
| Lease or safety readiness | deny motion request | direct native frame, PAL or WebSerial path |
| Physical enable policy | deny physical motion | enable because simulation/offline tests pass |
| Remote physical enable | deny remote motion | reuse local authorization |
| Local presence for physical recovery/update | deny | remote “continue anyway” |
| Artifact integrity assertion | deny stage/activation | CRC-only authenticity or unsigned promotion |
| Rollback guard / independent approval | deny activation | self-review or stale approval |
| Normal audit health/capacity | deny ordinary action | unlogged sensitive action |
| Safe audit health | deny software disable and independently enter shutdown | treat denial as continued motion permission |
| Authorization core itself | no physical endpoint binding | preserve a legacy bypass |

## Executable evidence and remaining work

`tests/security_authorization/run_tests.sh` runs seven Python tests, a 37-case
canonical Python/native corpus, the full 7-by-10 role matrix, replay and
safe-audit-lane adversaries, GCC ASan/UBSan, and an undefined-symbol allocation
audit. The native engine is compile-time capped at 16 normal plus four
safe-action records, occupies 6,216 bytes in the host ABI check and has an
8,192-byte static ceiling. Target ABI/stack placement still requires ESP32
measurement. The ESP32 build compiles the C++11 core, but the core remains
disconnected from the preserved runtime.

This closes only the stated offline tests for least-privilege decisions,
diagnostic non-escalation/audit-lane isolation, default-deny remote actuation
and secret-free audit structure. It does not complete SEC-001..004. Before a
production endpoint exists, WP-170 still requires:

- selected device/operator/service credential bootstrap and recovery;
- authenticated host-link transport binding and peer authorization source;
- secure key ownership/storage/rotation/revocation design;
- persistent boot/session anti-replay and trusted time/boot identity;
- signed config, calibration and firmware verification using vetted platform
  capabilities, plus monotonic rollback protection;
- durable integrity-protected audit export and retention;
- explicit call-site composition with the gateway and safety supervisor;
- multi-client/load, penetration and target timing evidence;
- incident/fault recovery and bench operations runbooks; and
- independent power cut and physical verification under separate authority.
