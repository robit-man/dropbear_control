# Iteration 5 retrospective

## Outcome

The repository now distinguishes five facts that were previously blurred:
source acquisition, lexical STEP structure, CAD-kernel importability, semantic
housing/output articulation and released simulator support. All real sources
reach the first three layers; none reaches the last two.

## Discoveries that changed the work

- The 53 manifest rows represent 48 unique geometries but remain 53 provenance
  variants. Byte duplicates cannot inherit a review automatically.
- FL-85-23 advertises metres while the other 52 variants advertise
  millimetres. OpenCascade normalizes imported geometry into its millimetre
  working space, so source unit evidence and conversion-space units must remain
  separate.
- Five valid imported files have no closed solids. “Imports successfully” is
  insufficient for collision readiness.
- GLB unit arguments did not change stored accessor coordinate scale in the
  locked exporter path. Explicit shape scaling and accessor verification are
  now mandatory.
- Exactly half of the model names are assembly-backed and half are
  flattened-only. They require different review/segmentation workflows.
- Some RH model packages contain distinct brake/non-brake STEP variants. One
  canonical file per marketing model would erase a real geometry-selection
  dimension.

## What worked

- Source-hash-bound generated evidence keeps the ignored 285 MB cache auditable
  without redistributing geometry.
- A synthetic two-link fixture proved the conversion machinery without using
  it to promote any vendor model.
- Process isolation let the long OpenCascade sweep complete without sharing
  kernel state or leaked memory between files.
- The semantic validator makes acceptance expensive in exactly the right
  places: reviewer/evidence, unit, rigid frame, disjoint members, joint,
  separate artifacts, visual checks and license disposition.

## Debt carried forward

- Exact geometry-configuration selector schema for multi-variant packages.
- Local review packets/contact sheets for 26 assembly variants.
- Reviewed solid/face partition workflow for 27 flattened variants.
- Output group membership, axis/origin/direction/zero for every configuration.
- Real housing/output STEP+GLB/collision exports and rotation/immobility tests.
- Healing or improved source for the five shell-only variants.
- Redistribution decisions and model-specific mass/COM/inertia provenance.

