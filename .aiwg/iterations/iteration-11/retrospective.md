# Iteration 11 retrospective

Status: `COMPLETE-OFFLINE`

## What changed

The main architectural gain is that authority is now a revocable lifecycle,
not a static “approved” flag. Source selection, graph selection, downstream
projections and joint handles all bind exact registry generations. A revoke,
supersede or unavailability event therefore removes capability instead of
leaving stale consumers alive.

Graph V2 also replaces prose-only ambiguity with structured frames, aliases,
chirality, symmetry, coupling domains, singularities, closure classes, DOF
accounting and ownership. This makes the remaining human work large but
finite: seven source roles, 29 source divergences and 161 graph questions.

The adapter intake established the same discipline at the hardware boundary:
a library name or ESP32 include cannot select TWAI or MCP2515. Exact installed
controller/transceiver/clock/pin/driver and TX-disable evidence is required,
and selection remains separate for listen-only versus runtime use.

## What remains deliberately incomplete

Offline structures cannot answer the physical questions. The project still
has zero supported model tuples, zero accepted output-shaft CAD
configurations, zero real plant parameter sets, zero source/graph authority,
zero runtime routes and zero authorized physical actions. The preserved
prototype runtime remains unwired by design.

## Process findings

- Empty tracked registries plus positive temporary fixtures are effective:
  lifecycle code can be proven without fabricating project evidence.
- Registry generation must be checked at every command/state use, not only at
  configuration time.
- Controller mode and independent physical TX disable are distinct facts.
- Closure reports must be written before the canonical final gate so the
  machine source manifest hashes the actual handoff.
- Review work should be scheduled by cohort and independence boundary, not as
  one undifferentiated “fix the URDF” task.

## Next iteration bias

Keep offline work moving on reviewer tooling, ROS/replay interfaces, protocol
applicability and CAD/plant pipelines while human assignments and U0
authorization are resolved. Do not let physical scheduling stall software
quality, and do not let software completion imply physical readiness.
