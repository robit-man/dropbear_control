# Dropbear graph-gated hardware API

`host/myactuator_lib/dropbear_hardware_api.py` defines the future common joint
boundary without wiring it into the preserved ESP32 or ROS runtime.

## Admission identity

A session requires exact:

- canonical configuration SHA-256;
- accepted graph decision ID and full digest;
- source-registry and graph-registry generation SHA-256 values;
- positive configuration generation;
- fresh session ID and owner; and
- one explicitly selected backend identity.

A joint handle additionally requires one of the twelve exact actuator IDs and
a currently valid lease ID/owner/sequence/time interval. Every command repeats
the configuration, graph, session, actuator and lease identity and has a
monotonic deadline no later than lease expiry. Handles cannot cross
configuration generations or reconnects.

A generation provider is checked before configuration and every handle
operation. Revocation, supersession, malformed generation state or an
unavailable provider cancels/faults the active session before reuse.

The tracked admission loader consumes the hash-checked graph projections and
the twelve-row readiness registry. It currently returns graph denied, no ready
actuators and physical motion false, so it cannot configure a command session
or create a handle.

## Typed command and state boundary

Commands are closed modes:

- `disable`;
- `joint_position` with output-coordinate radians and velocity/current
  bounds;
- `joint_velocity` in radians per second with current bound; and
- `output_torque` in output newton-metres with velocity/current bounds.

There is no vendor byte array, CAN/node ID, raw command, generic effort field,
implicit enable flag or native q-axis-current command on this robot-facing
surface.

State independently represents position, velocity, q-axis current and output
effort. Each signal records presence, numeric value, native/external/fused/
synthetic/replay/unavailable source, source age, valid/stale/missing/faulted
status and evidence references. Missing effort cannot be fabricated from
q-axis current.

## Backend and lifecycle separation

Replay, protocol emulator, synthetic plant, rigid-body candidate and physical
adapter are distinct enum identities. Replay is never command-capable.
Offline synthetic admission is marked test-only and cannot configure physical
I/O.

The lifecycle is:

`unconfigured -> inactive -> active -> inactive/faulted -> unconfigured`

Deactivate, fault and cleanup cancel pending work. Reconfiguration needs a new
session ID and generation; stale handles fail. Backend configuration,
activation, command and state failures latch the session fault before reuse.

`FailOnlyPhysicalBackend` is the only physical default. It has no concrete
adapter and every direct operation raises; session admission rejects it before
configuration. A later real implementation must pass graph/readiness,
safe-power, exact protocol/route, calibration/limit and HIL gates rather than
replacing this default by convention.

Run:

```bash
tests/dropbear_hardware_api/run_tests.sh
```

The suite covers normal fake/replay behavior plus identity, timing, lifecycle,
backend-kind, state-provenance, stale-handle, source/graph revocation,
physical-substitution and tracked denial mutations. Passing it is offline API
evidence only.
