# Command ownership and admission specification

This specification makes [SAF-003..010](../requirements/system-requirements.md)
and [LNK-002..004](../requirements/system-requirements.md) executable without
hardware.

## Candidate command

```text
source_id, role, session_id, lease_id, sequence
created_monotonic, expires_monotonic
config_hash, joint_id, requested_state, mode
value_SI, optional feedforward_SI, limit_profile_id
```

The gateway does not accept a client-supplied priority. A static reviewed
policy maps authenticated role/source to allowed joints, modes and actions.

## Lease rules

1. A lease names source/session, config hash, joint set, mode set, issue time
   and absolute monotonic expiry bounded by configured maximum.
2. A joint has zero or one lease owner. Acquisition is atomic across a
   requested joint set; partial acquisition is rejected unless explicitly
   requested as such.
3. Renewal is an authenticated new decision, not activity-based extension.
4. Disconnect, expiry, config change, clock invalidity, safety transition or
   privilege revocation invalidates the lease immediately.
5. A new source cannot preempt an owner while ENABLED. Emergency disable is a
   separate action open only to authorized local/safety sources.

## Deterministic admission order

For every candidate and again immediately before native TX, evaluate in this
order and stop at the first failure:

| Step | Check | Stable rejection code |
|---:|---|---|
| 1 | Frame integrity, protocol version, message length and replay window | `BAD_ENVELOPE` |
| 2 | Authenticated source/session and action authorization | `UNAUTHORIZED` |
| 3 | Known canonical joint and exact configured actuator tuple | `UNKNOWN_TARGET` |
| 4 | Candidate config hash equals active validated config | `CONFIG_MISMATCH` |
| 5 | Sequence is new for the session and source | `REPLAY_OR_REORDER` |
| 6 | Creation/expiry arithmetic valid; command not early, stale or over maximum horizon | `BAD_DEADLINE` |
| 7 | Active lease matches source/session/joint/config and is unexpired | `NO_LEASE` |
| 8 | Requested state transition is permitted for current safety state | `BAD_STATE` |
| 9 | Mode is leased, exact-tuple evidenced and unchanged while ENABLED | `BAD_MODE` |
| 10 | Brake, transport, feedback, calibration and physical prerequisites valid | `PREREQUISITE_FAILED` |
| 11 | Values finite, correct dimensional type and representable before conversion | `BAD_VALUE` |
| 12 | Position/velocity/current/effort/thermal/following hard and soft limits pass in output and motor coordinates | `LIMIT_REJECTED` |
| 13 | Rate/discontinuity policy passes against last admitted command and fresh state | `DISCONTINUITY` |
| 14 | Scheduler slot/deadline/bus budget available | `SCHEDULE_REJECTED` |
| 15 | Protocol encoding succeeds without overflow/reserved violation | `ENCODE_REJECTED` |

Rejection never refreshes a lease. No value is silently clamped unless an
exact requirement explicitly declares clamping, evidence proves it safe and
the disposition returns both requested and applied values. Default is reject.

## Single-writer implementation rule

Only the scheduler task owns native transport TX. Other tasks submit immutable
typed intents to bounded mailboxes. The scheduler consumes the one
safety-supervisor-approved command snapshot for its cycle. Mailbox overflow is
observable and cannot overwrite a pending safe action.

## Disposition phases

`RECEIVED` -> `ADMITTED` or `REJECTED` -> `QUEUED` -> `TRANSMITTED` ->
`RESPONSE_MATCHED`/`TIMED_OUT` -> optionally `STATE_OBSERVED`.

Only the reached phase is reported. In particular, `TRANSMITTED` is not
“executed”, and a native command response is not proof of mechanical stop.

## Offline proof obligations

- Property: no generated event sequence emits a motion command outside
  ENABLED with a valid exact owner/lease/config/mode.
- Boundary: expiry equal to current time is expired; maximum horizon and timer
  wrap are tested explicitly.
- Concurrency: torque/impedance/diagnostic candidates cannot create two native
  writers or starve safe action.
- Replay: duplicate, reordered and previous-session sequences are rejected.
- Fault: every failure injected between admission and TX invalidates the
  queued command before encode/TX.
- Regression: Dropbear boot play mode, all-12-ID ownership, dual writers and
  invalid stop IDs are represented in [test-catalog.md](../testing/test-catalog.md).

