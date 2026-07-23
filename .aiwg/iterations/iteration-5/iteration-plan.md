# Iteration 5 dual-track plan — STEP truth and output-member review foundation

- Iteration status: `COMPLETE-OFFLINE-FOUNDATION`
- Phase context: P1 / Elaboration, WP-140 foundation
- Delivery scope: byte-preserving 53-variant STEP inspection, strict 44-model
  semantic-review ledger, fail-closed articulation acceptance and reproducible
  conversion-toolchain contract
- Discovery horizon: CAD-kernel selection, assembly member graph, visual output
  identification, scale/axis/origin conventions and redistribution policy
- Safety boundary: geometry work only; no actuator support, plant fidelity,
  firmware applicability or powered-operation claim

## Starting evidence

- 44 catalog models and 53 actual vendor STEP files are present and hash-verified.
- 26 variants contain assembly-usage relationships; 27 are flattened models.
- Five pairs are byte-identical duplicate variants, leaving 48 unique geometries.
- Source files total about 285 MB; variants range from 362,233 to 75,219,363 bytes.
- Static unit tokens indicate millimetres in 52 variants and metres in FL-85-23;
  this is discovery evidence only until a semantic review confirms scale.
- No CAD kernel or mesh/GLB converter is currently installed in the workspace.
- No package names a separately delivered output-shaft STEP; current support is
  intentionally 0/44.

## Delivery acceptance

| ID | Outcome | Required evidence |
|---|---|---|
| I5-D01 | Immutable source join | Every review row joins exact series/model/path/SHA/bytes/structure from `step_manifest.tsv`; missing, changed or extra sources fail |
| I5-D02 | Bounded Part 21 inventory | Dependency-free inspector reports schema, entity counts, assembly relations, named products/representations, unit candidates and untransformed point extents without claiming geometric interpretation |
| I5-D03 | Review contract | Strict schema represents housing/output selection, units, source-to-canonical transform, axis/origin/direction, segmentation method, reviewer/time/evidence and redistribution disposition |
| I5-D04 | Default denial | All 53 variants and 44 models begin unreviewed/unsupported; incomplete or internally inconsistent review records cannot become exportable or simulator-supported |
| I5-D05 | Duplicate handling | Byte-identical variants share inspection evidence but retain separate provenance/review rows and cannot silently inherit acceptance |
| I5-D06 | Assembly graph evidence | Assembly variants expose stable entity/member references and decoded-name candidates for human review; flattened variants require explicit segmentation evidence |
| I5-D07 | Toolchain decision | Pin a reproducible local conversion stack or record a blocked decision with exact missing capability; no opaque/manual export enters released assets |
| I5-D08 | Artifact contract | Canonical output requires separate `housing` and `output` links, source hash, SI scale, transforms, axis metadata, mesh settings and SHA-256 for STEP/mesh/GLB outputs |
| I5-D09 | Acceptance tests | Negative tests cover hash drift, unit ambiguity, zero/non-unit axis, missing output, identical housing/output selection, flattened-without-segmentation and unsupported promotion |
| I5-D10 | Unified evidence | CAD inspection/review tests, drift checks, traceability and full repository gate pass |

## Semantic review state machine

```text
UNREVIEWED
  -> INSPECTED_STATIC
  -> MEMBER_CANDIDATES_RECORDED
  -> GEOMETRY_REVIEWED
  -> CONVERSION_VERIFIED
  -> ACCEPTED_LOCAL | ACCEPTED_REDISTRIBUTABLE

Any source hash, review evidence, transform, axis, export hash or toolchain
change returns the variant to a non-accepted state.
```

`INSPECTED_STATIC` never implies that the selected unit, housing, output or
axis is correct. Only `ACCEPTED_*` can satisfy the CAD-articulation gate, and a
model is supported only when its designated canonical variant is accepted.

## Execution slices

### Slice A — truth-preserving static inventory

- define review/report schemas and stable variant IDs;
- implement a streaming/bounded Part 21 lexical inspector;
- verify all cached source hashes before inspecting;
- capture AP schema, entity histograms, products, representations, assembly
  relationships, unit candidates and raw untransformed point extrema;
- generate deterministic inspection evidence and prove five duplicate groups.

### Slice B — fail-closed semantic ledger

- create one review row per source variant and one canonical-selection row per
  catalog model;
- keep every field unknown/unreviewed by default;
- validate state transitions and full acceptance prerequisites;
- report 0/44 accepted until real review evidence exists.

### Slice C — reproducible CAD toolchain

- evaluate a pinned OpenCascade-based headless stack for STEP import,
  assembly/body selection, tessellation and GLB export;
- isolate dependencies from firmware/host runtime dependencies;
- record importer/kernel/exporter versions and mesh parameters;
- add a synthetic two-body STEP fixture to prove housing/output articulation
  without promoting vendor models.

### Slice D — model review campaign

- prioritize the assembly variants, decode/source member names and render
  exploded/contact-sheet views;
- identify the real output flange/shaft and fixed housing with retained entity
  references and screenshots;
- handle flattened variants only with reviewed solid/face segmentation or an
  improved vendor assembly;
- verify scale/orientation/axis by dimensions and interface features;
- accept model variants individually, never by series inference.

## Definition of Done

- [x] I5-D01..I5-D10 have executable evidence.
- [x] All 53 STEP sources are inspected deterministically from exact hashes.
- [x] Review/selection ledgers cover 53/53 variants and 44/44 models.
- [x] No unreviewed record can produce released housing/output artifacts.
- [x] The one metre-token outlier is explicit and cannot inherit millimetre scale.
- [x] Assembly and flattened workflows have distinct acceptance guards.
- [x] A reproducible conversion stack and synthetic articulation proof exist.
- [x] Any future real vendor acceptance requires retained human/visual evidence.
- [x] Unified gate, traceability, generated drift and whitespace checks pass.
