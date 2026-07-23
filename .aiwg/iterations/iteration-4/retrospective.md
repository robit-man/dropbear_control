# Iteration 4 retrospective

## Outcome

The iteration closed the largest software-only discontinuity in the prior
architecture. A typed host command can now be encoded by Python, decoded by an
allocation-free native V1 receiver, re-authorized against exact config and
safety state at the final scheduler boundary, encoded by the canonical V4.4
core, exercised against the deterministic protocol emulator and correlated
without collapsing evidence phases.

## What changed the design

- `ADMITTED` was narrowed to bounded queue/shape admission. Final config and
  safety authority occurs only at release to the transport adapter.
- Response chronology now rejects response-before-TX and observation-before-
  response rather than treating matching bytes as sufficient.
- Reconnect creates a fresh link session, cancels pending work, clears stale
  telemetry and never restores or resends a lease/command.
- The safe-action lane has deterministic priority but intentionally claims
  only one dispatch attempt per shutdown generation/fault mask until real
  send-result/retry/bus-off inputs exist.
- Large native V1 storage is explicitly statically owned/budgeted; successful
  ESP32 compilation is not treated as runtime stack sufficiency.

## Verification lessons

- One synthetic exact tuple is useful for positive composition without
  weakening the production exact-tuple rule.
- Cross-language vectors caught contract risk more directly than two isolated
  unit suites.
- Phase-specific assertions prevent the simulator from accidentally promoting
  protocol receipt into plant or physical evidence.
- Keeping fake transport and protocol-state simulation explicit made the next
  real-I/O work legible: send outcomes, retry, arbitration loss, bus-off,
  recovery, utilization, task ownership and target timing are still missing.

## Debt carried forward

- Real authenticated host adapter and ESP32 runtime integration.
- TST-FW-001/002 real transport, retry, bus-off and utilization evidence.
- Legacy host API deprecation and `ros2_control` integration.
- State validity/calibration/limits service and all physical source inputs.
- Output-member semantic review, articulation metadata and conversion for all
  44 models / 53 STEP variants.
- Model-specific actuator plants and the reconciled Dropbear rigid-body twin.

## Next iteration

Iteration 5 begins WP-140 with a reproducible CAD inventory/inspection schema,
toolchain discovery, per-variant semantic-review ledger and fail-closed output-
member acceptance. It must preserve every source STEP byte-for-byte, distinguish
assembly and flattened variants, and produce no articulation or simulator-
support claim until a reviewer identifies the actual housing, output member,
axis, transform and units.

