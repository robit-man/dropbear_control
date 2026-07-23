# Iteration 2 retrospective

## Outcome

The iteration established three missing interfaces between raw protocol work
and later robot integration: exact evidence-backed applicability, a canonical
robot configuration boundary, and a deterministic protocol-state substitute.
The unified offline gate is green.

## What worked

- Discovery and delivery remained synchronized around the same fail-closed
  boundary: observations were retained, but no physical fact was inferred.
- Shared V4.4 codec vectors prevented the emulator from creating a second wire
  protocol interpretation.
- The exact support key stopped catalog acquisition, a passing build and SIL
  execution from being promoted into hardware support.
- The incomplete Dropbear example made structural gaps executable: missing
  hip-yaw sensing, unknown native IDs, absent ownership, unresolved limits and
  missing CAD/calibration data are machine-visible blockers.
- Independent component suites were integrated into one repository command
  before the iteration was accepted.

## Friction and corrections

- Structural JSON Schema validation and cross-record semantic validation are
  different evidence. The final suite now runs both and labels the standalone
  semantic CLI result honestly.
- The existing Dropbear identifiers looked like motor IDs but are full command
  CAN identifiers. Naming them explicitly avoided an unsafe arithmetic
  migration assumption.
- A protocol emulator can easily be mistaken for a motor plant. Explicit
  false scope markers, no command-to-feedback dynamics and wording audits keep
  that boundary visible.
- Work-package completion is broader than a green component. WP-020, WP-030
  and WP-130 remain `ACTIVE` because claim generation, generated views and
  gateway integration are still open.

## Carry-forward rules

- Do not create a complete/enableable Dropbear configuration from the observed
  example. Physical tuple, topology, coordinate, limit, calibration and CAD
  evidence must be collected and reviewed first.
- Reuse the canonical schema digest and exact support decision at every future
  firmware/host/ROS/UI/simulator boundary.
- Keep one admission path and one native writer; tests and diagnostic clients
  receive no bypass.
- Treat response absence as unknown actuation outcome, not proof that the
  drive ignored a transmitted command.
- Keep physical/HIL work on hold until the inventory, independent cut and
  reviewed runbook exist.

## Next iteration hypothesis

A versioned host link plus generated configuration views is the shortest path
to reconcile low-level ESP32 behavior with host/ROS layers without coupling
them to legacy browser frames or raw vendor bytes. Its exit should prove that
identity/config/lease/validity context survives end to end and that corruption,
replay, staleness or schema mismatch prevents admission and native TX.
