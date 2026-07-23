# ADR-004: Gateway-local single writer, lease and safety supervisor

- Status: Accepted
- Requirements: SAF-001..010, FW-002, HST-004
- Work packages: WP-070, WP-080, WP-090, WP-100

## Decision

Only the deterministic bus scheduler may transmit native commands. Immutable
intents pass through authenticated ownership, bounded leases and the local
safety state machine. The gateway rechecks admission immediately before TX and
preempts normal traffic for safe action.

## Consequences

Host or UI loss cannot leave an indefinite command, and Dropbear’s dual torque
writers/all-ID contention become impossible by construction. Concurrency and
timing behavior require explicit bounded queues and fault-injection tests.

