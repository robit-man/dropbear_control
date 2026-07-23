# ADR-010: Independent safe power and default-deny remote actuation

- Status: Accepted as safety boundary; physical design open
- Requirements: SAF-009, ROB-007, SEC-001..004
- Work packages: WP-100, WP-170

## Decision

Treat software motor-off as a supervised request, never the sole emergency
control. Require independently testable physical power removal for powered
work. Remote physical command endpoints are disabled by default and require
authenticated identity, least privilege, safety-state admission and audit.

## Consequences

The current unauthenticated Flask endpoint cannot be a production control path.
Hardware topology, stop categories and validation remain a P0 physical hold;
offline documents do not satisfy them.

