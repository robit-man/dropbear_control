# Dropbear robot-description evidence inventory

[`generated/dropbear_description/inventory.json`](../generated/dropbear_description/inventory.json)
is a pinned, observation-only inventory of the Dropbear robot-description
trees. It is generated directly from Git objects at commit
`13cf5ecaa39b8b89c794fe905dcea0490cfa7726`; sparse-checkout contents are not
used as the source of truth.

## Scope and current result

The inventory selects URDF, xacro and controller YAML candidates beneath the
committed CAD full-body URDF, Gazebo and RViz trees. At the current pin it
contains:

- 198 file paths and 96 unique Git objects;
- 120 source xacro/controller candidates;
- 7 expanded `.urdf` candidates;
- 71 committed install derivatives and zero matching build-description files;
- 65 exact-content duplicate groups;
- 44 repeated logical-path groups, 29 of which diverge; and
- 161 unresolved graph-review questions.

Each file records its Git object ID, SHA-256, byte size, package family,
candidate/derivative class, logical key, exact-copy paths and drifted
candidates. Observations are stored once per unique object and include link and
joint names, type, parent/child, axis, origin, mimic relation, transmission and
ROS 2 control membership, controller joint names, mesh references, xacro
macros and plugin references.

The 161 questions cover all 12 exact actuator mapping gaps, the six-actuator
versus five-ROS-joint mismatch for both legs, 112 observed mimic/coupling edges
and 35 Gazebo loop-closure candidates. These counts describe the pinned
candidate corpus; they are not a canonical kinematic graph.

## Authority boundary

No file is automatically selected as the authoritative robot description.
Direct source trees are candidate observations, expanded URDFs are generated
candidates, and committed `install/` copies are derivatives with no source
authority. Exact duplicates are not evidence of correctness, and a shared
logical filename does not make divergent detailed/simplified/Gazebo/RViz
content interchangeable.

Every review question is unresolved and has a null runtime mapping ID. The
artifact contains zero ROS-to-actuator mappings, selects no authoritative
description and keeps motion false. Only reviewed graph decisions may later
populate a separate canonical graph; this inventory cannot be used as a
runtime generator.

## Reproduction

```bash
python3 tools/generate_dropbear_description_inventory.py
tests/dropbear_description_inventory/run_tests.sh
```

The generator verifies the exact repository HEAD, binds the current
reconciliation hash/configuration digest, reads only selected blobs in one
bounded Git batch, validates the strict schema and emits canonical JSON.
`--check` detects byte drift. The tests independently re-read all 198 pinned
Git objects, validate hashes/sizes/classification, exercise duplicate/drift
and graph observations, require complete review-question coverage, and reject
authority, mapping or motion promotion.
