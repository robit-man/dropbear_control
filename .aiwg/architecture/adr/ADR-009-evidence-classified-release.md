# ADR-009: Evidence-classified claims and release gates

- Status: Accepted
- Requirements: SYS-003..004, VER-001..007
- Work packages: WP-010, WP-170, WP-180, WP-190

## Decision

Store test evidence with explicit offline/SIL/bench/HIL/robot class, exact
tuple, code/config/tool revisions and trace IDs. Release claims are generated
from current evidence records and gates; a lower class never satisfies a
higher-class requirement.

## Consequences

CI can honestly pass P1 while physical support remains zero. Evidence
invalidation and retention become product behaviors, not documentation chores.

