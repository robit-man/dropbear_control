# ADR-007: Separate protocol, actuator-plant and whole-robot simulation

- Status: Accepted
- Requirements: SIM-001..006
- Work packages: WP-130, WP-140, WP-150, WP-160

## Decision

Maintain three composable levels: revision-exact protocol emulator, sourced
single-actuator plant with uncertainty, and engine-backed Dropbear rigid-body
simulation. The browser is an asset/telemetry/diagnostic client, not the
authoritative physics implementation.

## Consequences

Protocol fidelity no longer masquerades as plant accuracy. Engine selection
and parameter provenance require explicit evidence, but failures can be
localized and injected deterministically.

