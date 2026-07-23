# ADR-002: Exact-tuple, capability-specific support

- Status: Accepted
- Requirements: SYS-002, SYS-003, PRO-006, VER-001
- Work packages: WP-020, WP-040, WP-180

## Decision

Index support by manufacturer/model/hardware/drive-firmware/protocol-revision/
transport/control-mode. Advertise only the intersection of capabilities with
current evidence. Unknown fields fail closed; family class existence never
implies model support.

## Consequences

The initial 44-model catalog can be complete while hardware support remains
zero. More records and explicit limitations are required, but mixed firmware
and brake semantics cannot be accidentally promoted.

