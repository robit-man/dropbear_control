# Iteration 6 dual-track plan — exact CAD configuration review campaign

- Iteration status: `COMPLETE-OFFLINE-CANDIDATE-FOUNDATION`
- Phase context: P1/P2 asset elaboration, WP-140 review/export campaign
- Delivery scope: exact geometry-configuration selectors, local visual evidence,
  reviewed housing/output groups, real separate-link exports and per-variant
  articulation acceptance
- Starting support: 0/44 models, 0/53 variants
- Safety boundary: simulator geometry only; no physical motor, protocol, plant,
  mass/inertia or powered-operation claim

## Campaign cohorts

| Cohort | Models | Variants | Primary path |
|---|---:|---:|---|
| Assembly-backed | 22 | 26 | preserve occurrences/products/placements; select disjoint fixed/output groups |
| Flattened-only | 22 | 27 | reviewed solid/face partition or acquire better assembly source |
| Shell-only subset | 4 model names | 5 | visual only until healing/solidification or replacement source is reviewed |

The shell-only set is X6-8 (two paths), CEM-25, CEM-45 and FL-85-23.

## Delivery acceptance

| ID | Outcome | Required evidence |
|---|---|---|
| I6-D01 | Exact geometry selector | Replace one-file-per-model assumptions with reviewed configuration selectors covering brake/non-brake and any other meaningful package variants |
| I6-D02 | Assembly review packet | Every assembly variant has local overview/member/contact evidence joined to exact occurrence/product IDs and source hash |
| I6-D03 | Flattened partition packet | Every flattened variant has solid/shell inventory and repeatable labeled partition evidence or an explicit re-source block |
| I6-D04 | Output group selection | Housing/output selections are disjoint, complete for externally relevant geometry and independently reviewable; heuristics never auto-accept |
| I6-D05 | Joint definition | Unit, canonical transform, axis, origin, positive direction and zero pose are evidenced for each accepted configuration |
| I6-D06 | Separate B-Rep export | Housing/output STEP artifacts preserve exact source/toolchain identity and round-trip valid topology |
| I6-D07 | Visual/collision export | Metre-scaled housing/output GLB and conservative collision GLB use locked settings and retained hashes |
| I6-D08 | Articulation regression | Zero/positive/negative poses prove housing immobility, output-only rigid rotation, stable topology and no unintended overlap/scale change |
| I6-D09 | Model/config coverage | Dashboard distinguishes unsupported, blocked, candidate, accepted-local and redistributable states without collapsing variant provenance |
| I6-D10 | Unified release evidence | Per-acceptance artifacts/review signatures, schema/trace tests and full gate pass; 44/44 only when every required configuration is dispositioned |

## Execution order

1. Evolve the ledger to exact configuration selectors before accepting any
   variant; migrate the current 0/44 baseline losslessly.
2. Generate assembly review packets in model order, starting with RMD-X12-320
   as the workflow fixture. Candidate scoring remains non-authoritative.
3. Record candidate groups and unresolved questions; require independent review
   before `geometry_reviewed`.
4. Export and articulate only reviewed assembly configurations.
5. Build the flattened solid/shell partition UI/report using stable topology
   fingerprints, then process closed-solid variants.
6. Route shell-only variants to healing/re-source decisions; do not fabricate
   closed collision bodies.
7. Reconcile accepted exact geometry selectors into Dropbear registry and web/
   rigid-body asset consumers only after parity tests exist.

## RMD-X12-320 workflow fixture observations

The first local packet joins 18 occurrences. Static name/visual candidates are
NAUO3 (`输出法兰`), NAUO4 (`输出法兰盖板`) and possibly NAUO5 (`二编轴`). The
major fixed candidates are NAUO1 rear cover, NAUO2 end cover and NAUO18
housing; fasteners are separate occurrences. Visuals indicate a likely Y-axis,
but co-rotation of the encoder shaft/cover/fasteners, exact origin plane,
positive direction and zero definition remain unresolved. The variant stays
unsupported.

## Campaign evidence now

- Exact selector V2 covers all 53 source variants once through 53 unresolved,
  provenance-preserving configurations; support remains 0/44.
- All 26 assembly variants have local source/member/image-hash-bound packets
  and a tracked candidate triage manifest. One nested RMD-H package explicitly
  distinguishes 17 STEP relationships from 15 renderable leaf shapes.
- All 27 flattened variants have a tracked inventory totaling 1,628 stable
  OpenCascade components and local overview/largest-component sheets: five are
  shell-only, two are inseparable single solids, five exceed 32 solids and 15
  retain disconnected-solid candidates for manual partition.
- Candidate names and topology IDs are explicitly non-semantic. No housing,
  output, axis, export, articulation or simulation support was auto-accepted.
- A real X12-320 hypothesis now proves the downstream mechanics without
  bypassing review: 12 housing and six provisional output occurrences round-
  trip as valid separate STEP leaves, metre GLBs export, and -30/0/+30-degree
  poses preserve 109,818 output triangles with at most 0.001 mm vertex
  deviation. Five semantic/origin/sign questions remain, so accepted/support
  counts are still zero.
- The generated browser/Dropbear consumer registry covers 44 models, 53 source
  variants and 53 exact configurations. It exposes zero runtime assets, denies
  the X12 candidate, and labels procedural visuals/dynamics as non-physical
  toy evidence with constructor-level promotion checks.

## Definition of Done

- [x] Exact configuration selectors cover all 53 provenance variants.
- [x] 26/26 assembly review packets and 27/27 flattened dispositions exist.
- [x] No heuristic candidate has been auto-promoted.
- [ ] Every accepted configuration has separate real STEP/GLB artifacts and
  zero/positive/negative articulation evidence.
- [ ] Five shell-only variants have reviewed heal/re-source/blocked outcomes.
- [x] Model/config dashboard has no missing or over-promoted row.
- [x] Dropbear/web/simulator consumers accept only exact reviewed selectors.
- [x] Unified gate, traceability, generated drift and whitespace checks pass.
