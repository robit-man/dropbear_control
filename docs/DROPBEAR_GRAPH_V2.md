# Structured Dropbear graph V2

Graph V2 is the canonical data contract planned between reviewed robot
description sources and host, ROS, simulator and UI consumers. It replaces
free-form mechanical relationships with explicit, cross-referenceable
records. It does not accept the current Dropbear graph.

The tracked candidate is a deterministic migration from the V1
`graphdecision-*` template. It preserves all 161 V1 review questions as
unresolved, binds source-registry V2 generation, and contains no frames,
coordinates, actuator mappings or ROS mappings.

## Structured semantics

The decision schema and semantic validator cover:

- stable frames with one root, explicit parent, SI translation, unit
  quaternion and exact expressed-in frame;
- links, joints and actuator bindings with explicit
  `left`/`right`/`center`/`none` chirality;
- namespaced aliases whose target kind and ID must exist;
- reviewed symmetry pairs, including exact mirror, transformed and
  intentional-difference dispositions;
- joint origin and unit axis with explicit expressed-in frames;
- structured coupling input/output coordinates, coefficient terms, offset,
  SI units, valid domain, owner and dependent-coordinate closure;
- singularity detection variable/operator/threshold, handling policy and
  owner;
- physical closed-chain versus simulator-only closures with different
  counterpart and solver requirements;
- a DOF ledger separating independent, dependent, passive, fixed and
  simulator-only coordinates;
- exactly one writer/state policy for every independent coordinate;
- explicit missing, present or admitted CAD/calibration/limit/route
  dependencies; and
- exact actuator and ROS command-coordinate mappings.

Semantic admission rejects frame and physical-joint cycles, multiple parents,
disconnected links, alias collision, non-unit/non-finite transforms and axes,
unpaired chirality, coupling/domain/singularity disagreement, DOF lies,
unowned command coordinates, incomplete dependencies, and physical/simulator
closure leakage.

## Files

- `schemas/dropbear-graph-v2-decision.schema.json` — strict V2 decision;
- `schemas/dropbear-graph-v2-status.schema.json` — denial-baseline status;
- `tools/manage_dropbear_graph_v2.py` — migration, semantic validation and
  deterministic generation;
- `generated/dropbear_graph_v2/candidates/` — generated incomplete migration;
- `generated/dropbear_graph_v2/status.json` — current authority status; and
- `tests/dropbear_graph_v2/` — positive synthetic structures and adversarial
  mutations.

## Commands

```sh
python3 tools/manage_dropbear_graph_v2.py --generate
python3 tools/manage_dropbear_graph_v2.py --check
tests/dropbear_graph_v2/run_tests.sh
```

Synthetic graph fixtures prove representational and validation semantics only.
They do not represent the robot, do not enter generated project evidence, and
cannot satisfy the exact twelve-actuator canonical Dropbear admission check.

## Current blockers

- source registry V2 has no active accepted submission;
- all 161 V1 graph questions remain unresolved;
- structured graph review is missing;
- no canonical graph V2 exists; and
- downstream runtime mapping generation remains blocked.

Support and physical motion authority remain false independently of any future
source or graph acceptance.
