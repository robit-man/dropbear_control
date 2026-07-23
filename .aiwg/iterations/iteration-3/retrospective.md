# Iteration 3 retrospective

## Outcome

The project now has a concrete offline contract from canonical Dropbear data
through host messaging to native configuration/safety admission. It is still
deliberately disconnected from real transport and powered hardware.

## What worked

- Treating the legacy 64-byte frame as migration evidence, not a compatibility
  constraint, allowed V1 to carry the identity, time, lease and disposition
  context the old frame cannot represent.
- Lossless views were safer than layer-specific partial projections at this
  stage: every consumer sees the same unknowns and blockers, so omissions
  cannot silently become defaults.
- The generated digest became an executable cross-layer join rather than a
  documentation convention.
- Config activation and safety state remain separate. A successful link parse
  or config commit does not arm or enable anything.
- Seeded parser tests give repeatable fuzz-like coverage while retaining a
  short, deterministic offline gate.

## Corrections made during review

- `source_identity` was split from `lease_owner`; connection, producer and
  lease identities are different security concepts.
- Drive and bus health became distinct state fields rather than being inferred
  from connectivity/native-response state.
- ADR-001 was corrected from a premature `robot.yaml` implementation detail to
  the actual schema-validated canonical data model.
- The schema/config-view dependencies were pinned and checked before the
  unified suite.

## Carry-forward rules

- The Python V1 reference is the semantic oracle for the native implementation;
  create shared golden vectors rather than manually translating behavior.
- Native parser limits must be smaller or equal to the published V1 limits and
  use no unbounded allocation.
- A link session never creates or restores a safety lease. Reconnect and reboot
  return through negotiation/config/safety prerequisites.
- Queue entries must carry the exact config generation and lease stamp and be
  revalidated immediately before TX.
- Preserve all six dispositions. A native response is not observed state, and
  neither is mechanical execution proof.
- Keep the tracked incomplete config non-enableable until physical evidence is
  reviewed; do not build an artificial “complete” default for integration.

## Next iteration hypothesis

A fake byte stream plus deterministic native scheduler/emulator can exercise
the real low-to-high boundary without hardware. If Python/native V1 vectors,
config/safety admission and V4.4 response correlation agree in one steel
thread, the project will be ready to replace the legacy serial dispatch with a
reviewed adapter while keeping powered TX disabled.
