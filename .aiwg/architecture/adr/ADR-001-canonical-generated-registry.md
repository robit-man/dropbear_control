# ADR-001: Canonical generated robot registry

- Status: Accepted; offline schema/projection foundation implemented
- Requirements: CFG-001..006, ROB-001..003
- Work packages: WP-030, WP-120

## Decision

Use one schema-versioned canonical registry document as the reviewed source for
node/bus ownership, canonical joints, exact actuator tuples,
signs/ratios/limits, sensor mappings, CAD frames and calibration references.
Generate typed firmware, host, ROS, UI and simulator views; reject
hand-maintained runtime copies when hashes differ.

## Consequences

This removes current name/ID/unit drift and enables configuration admission.
The compiler and generated diffs become release-critical. Existing Dropbear
values enter only as unverified migration candidates until SRC-016/SRC-020 are
reviewed.

The current canonical input is the deliberately incomplete JSON observation
under `schemas/examples/`; JSON Schema plus semantic validation and canonical
digest checks precede deterministic view generation. The format may later be
authored as YAML only if it validates to the identical canonical data model
and digest. Generated views remain projections and the current firmware view
is compile-tested but not yet consumed by the ESP32 runtime.
