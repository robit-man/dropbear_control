# Host-link session, command lease and authorization boundary

This decision refines ADR-004/005 for the Iteration 3 reference. It does not
define remote authentication or grant hardware authority.

## Distinct identities

| Identity | Meaning | Created/validated by | Must never imply |
|---|---|---|---|
| Transport connection | A byte stream is currently open | transport adapter | session continuity, identity or command authority |
| Link session ID | Namespace for negotiated version/capabilities and sequence replay checks | host-link peers | authenticated operator, lease ownership or enable |
| Source identity | Named command producer principal | future local/auth service | ownership merely because the string is present |
| Safety lease owner/generation | Sole time-bounded command scope selected by the arbiter/safety supervisor | gateway admission core | persistence across reconnect or process restart |
| Configuration identity | Exact schema/config revision and digest used to interpret topology/limits | generated config + identity guard | physical validity or support by itself |
| Native request sequence | Gateway scheduler correlation to one drive response | native scheduler | host execution merely because a frame was received |

## Required ordering

```text
byte stream
  -> bounded frame/CRC validation
  -> major/minor/capability/rate negotiation
  -> current-session + monotonic sequence validation
  -> authenticated source lookup (future; unavailable in Iteration 3)
  -> exact configuration identity check
  -> lease owner/scope/generation/expiry check
  -> command field/mode/finite/SI validation
  -> safety state/health/limit admission
  -> deterministic native scheduler
  -> correlated drive response
  -> independently timestamped observed state
```

Each arrow is a separate disposition. Receiving or decoding a message is not
admission; admission is not native TX; TX is not a native acknowledgement; an
acknowledgement is not independently observed mechanical state.

## Reconnect and replay rules

- Opening a transport produces no lease and no command permission.
- A new link session starts a fresh sequence namespace only after successful
  compatibility negotiation. It does not recreate, extend or transfer a
  safety lease.
- A command from a prior session is rejected even if its CRC, configuration
  digest and lease fields are otherwise valid.
- A duplicate or non-increasing sequence is rejected before typed command
  exposure. Sequence wrap requires a new negotiated session, not acceptance of
  a smaller number.
- Gateway restart returns the safety supervisor and config guard to their boot
  states. Neither a host replay nor a remembered link session may restore
  ARMED/ENABLED.
- Clock fields are monotonic-domain durations/timestamps, not UTC. Peers must
  not compare unrelated monotonic epochs as wall time; the gateway enforces
  its locally issued lease deadline.

## Iteration 3 limitation

The offline V1 reference can validate shape, negotiation, sessions,
sequences, configuration identity and explicit lease fields. It cannot
authenticate a source, issue a real gateway lease, authorize remote actuation,
or prove native scheduling. Any reference test that constructs an accepted
message does so only at the link-policy layer; the independent config/safety
guards remain authoritative and the generated Dropbear configuration remains
motion-disabled.
