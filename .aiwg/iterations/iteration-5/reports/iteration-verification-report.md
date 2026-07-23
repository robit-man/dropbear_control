# Iteration 5 verification report

- Assessment date: 2026-07-22
- Result: `PASS-OFFLINE-FOUNDATION`
- Vendor model articulation accepted: 0/44
- Vendor housing/output exports released: 0/44
- Plant, physical or HIL evidence produced: no

## Acceptance evidence

| Acceptance | Result | Principal evidence |
|---|---|---|
| I5-D01 exact source join | PASS | 53 paths join exact model/path/SHA/bytes/structure; source cache re-hashes |
| I5-D02 Part 21 inventory | PASS | 11 tests; 53 canonical static reports; schema/entities/products/assembly/unit/raw-point evidence |
| I5-D03 review contract | PASS | strict Draft 2020-12 schema and semantic validator for units/members/frame/joint/artifacts/license |
| I5-D04 default denial | PASS | 53 variant rows unreviewed and 44 model rows unsupported |
| I5-D05 duplicate handling | PASS | five duplicate hash groups retain ten separate provenance rows and distinct variant IDs |
| I5-D06 assembly graph | PASS | 26 assembly variants retain occurrence/product references and reversible decoded-name candidates |
| I5-D07 toolchain decision | PASS | CadQuery 2.8.0 / OCCT 7.9.3.1 isolated and exact-pinned |
| I5-D08 artifact contract | PASS | separate housing/output STEP+GLB, collision, source/toolchain hashes and visual evidence are mandatory |
| I5-D09 adversarial tests | PASS | 11 review tests cover drift, unit, axis, transform, selection, partition, artifact and promotion failures |
| I5-D10 unified evidence | PASS | 92-test trace baseline and complete `tools/test_all.sh` gate pass |

## Measured source/import results

| Measure | Result |
|---|---:|
| Catalog models | 44 |
| STEP provenance variants | 53 |
| Unique geometry SHA-256 values | 48 |
| Assembly variants / assembly-backed models | 26 / 22 |
| Flattened variants / flattened-only models | 27 / 22 |
| Static unit candidates | 52 millimetre, 1 metre |
| OpenCascade imports | 53/53 succeeded and valid |
| Variants with closed solids | 48 |
| Shell-only variants | 5 |
| Visual tessellation candidates | 53 |
| Semantically reviewed housing/output/axis | 0 |

The shell-only rows are both X6-8 provenance paths, CEM-25, CEM-45 and
FL-85-23. They cannot be collision candidates without reviewed healing or
solidification evidence.

## Toolchain evidence

- 44 exact transitive package versions and 44 platform-wheel filenames,
  SHA-256s and byte sizes are pinned for Linux x86-64 / CPython 3.12.
- The synthetic asymmetric-output proof keeps housing fixed, moves only the
  output under a +Z revolute transform, preserves output volume, round-trips
  separate STEP B-Reps and validates GLB 2.0 structure.
- The proof detected that GLB exporter unit parameters did not scale accessor
  coordinates. The locked workflow now scales OCCT millimetres explicitly by
  0.001 and checks metre-range accessors.
- The long process-isolated import reprobe passed for all 48 unique geometries;
  the main gate validates its exact inspection/toolchain-bound record.

## Evidence boundaries

- Static product-name scores and assembly relationships are candidate-review
  aids, not output-member selection.
- OpenCascade import validity does not establish correct units, transforms,
  housing/output membership, axis, zero pose, collision quality or simulator
  support.
- CadQuery flattens the simple import used for topology probing, so it does not
  preserve semantic assembly member authority.
- No redistribution approval exists; vendor geometry and review renders remain
  local/ignored.
- Model-level canonical selection must be refined before acceptance because
  some packages contain meaningful brake/non-brake geometry variants.

## Gate disposition

Iteration 5 completes the fail-closed CAD foundation and advances no G4 asset
acceptance. Iteration 6 may perform exact configuration-aware visual/member
review, real separate-link export and articulation verification. Status remains
unsupported 0/44 until those reviews pass individually.

