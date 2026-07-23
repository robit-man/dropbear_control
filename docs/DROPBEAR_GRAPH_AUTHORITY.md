# Dropbear canonical graph authority

The repository now has a review and admission mechanism for a canonical robot
graph; it does not yet have an accepted Dropbear graph.

## Inputs and decision boundary

The graph decision binds:

- the pinned Dropbear repository commit/tree;
- the exact 198-path description inventory and its hash;
- the source-authority denial status and hash;
- the canonical configuration digest;
- the exact reconciliation artifact and hash; and
- all 161 review questions in stable order with per-question hashes.

The decision schema is
[`dropbear-graph-decision.schema.json`](../schemas/dropbear-graph-decision.schema.json).
The generated draft, cohort packet, status and offline workbench are under
[`generated/dropbear_graph_review/`](../generated/dropbear_graph_review/).

Drafts contain no selected source authority, graph facts, reviewer or answers.
A submitted acceptance requires a separate accepted/runtime-complete source
decision, identified independent human mechanical reviewer, UTC review
evidence, all questions resolved and a canonical record digest. Automation can
prepare and validate records but cannot sign either source or graph authority.

## Graph invariants

An accepted graph must explicitly define:

- one rooted, connected, acyclic base tree;
- unique link, joint, constraint and ownership IDs with resolved endpoints;
- finite origins/rotations and normalized moving axes;
- fixed, active, passive, mimic, coupled and simulator-only semantics;
- mimic/coupling/closed-chain equations and solver/physical ownership;
- exactly twelve canonical actuator bindings;
- one command owner/state policy per active coordinate with no diagnostic
  bypass;
- all twelve observation roles while preserving both missing hip-yaw external
  sensors and the ten other sensors as unverified observations;
- exactly ten reviewed ROS mappings among twelve canonical actuators, with the
  two remaining roles explicitly uncommanded/passive; and
- stable dependency references for later CAD, calibration, limits and routes.

The validator rejects self-edges, multiple parents, disconnected nodes,
cycles, non-unit/non-finite axes, invalid fixed/mimic semantics, ambiguous
shared coordinates, actuator or ROS coverage drift, sensor aliasing, unknown
question facts, hash drift and reviewer/source promotion.

The positive graph used in tests is explicitly synthetic. It proves the
algorithm and never populates project evidence.

## Review workbench

The workbench embeds the exact draft and ten bounded cohorts:

- 2 cardinality/coupling questions;
- 12 actuator-mapping questions;
- 112 mimic/coupling candidates in six cohorts; and
- 35 Gazebo loop candidates in two cohorts.

It contains no network requests and exports only an answered draft. It does
not select source authority, construct graph facts, sign a review or grant
support/motion.

Run:

```bash
python3 tools/manage_dropbear_graph_review.py --check
tests/dropbear_graph_review/run_tests.sh
```

## Denial-only consumer projections

`tools/generate_dropbear_graph_projections.py` produces four separate views:

- host: zero transforms, mappings and command handles;
- ROS: zero URDF fragments, transmissions and hardware mappings;
- simulator: zero authoritative graphs, physical plants and mappings; and
- UI: zero paths, downloadable descriptions and mappings.

Every view carries the same status, inventory, configuration and decision
identity hashes, 161 unanswered questions and blockers. The host
`DropbearGraphProjectionSet` rechecks the graph status, inventory and template
bytes before returning typed status. It has exact view names only and no method
that exposes a candidate transform or mapping.

```bash
python3 tools/generate_dropbear_graph_projections.py --check
tests/dropbear_graph_projection/run_tests.sh
```

Current authoritative result: source selections 0, submitted graph decisions
0, canonical graphs 0, ROS-actuator mappings 0, support false and physical
motion authority false.
