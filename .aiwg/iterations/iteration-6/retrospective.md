# Iteration 6 retrospective

## What changed

The CAD program moved from importability evidence to an exact, reviewable
candidate pipeline. Model-level canonical-file selection was rejected after the
RH packages demonstrated that brake/non-brake and other package variants can
share a marketing model while retaining distinct provenance. The ledger now
uses exact configuration selectors and begins with one unresolved selector per
source.

Local visual evidence now exists for all 26 assembly variants and stable
topology inventories for all 27 flattened variants. The real X12 pilot proves
that reviewed occurrence groups can flow through canonical transforms,
separate STEP assemblies, metre GLB and rigid articulation tests without
granting semantic authority.

## Useful failures

- CadQuery flattens some nested assembly names to hierarchical kernel paths and
  represents product groups without direct shapes. Review packets must preserve
  all STEP relationships separately from renderable leaves.
- Flattened does not mean one solid: the corpus ranges from one inseparable
  solid to 517 disconnected solids, while five variants contain shells only.
  A single segmentation heuristic would be both inaccurate and unreviewable.
- A compound STEP export can re-import as invalid when colocated assembly parts
  are collapsed. Separate occurrence-preserving link assemblies retain valid
  leaf B-Reps and exact summed volume.
- Exact rounded vertex-set equality was too brittle at cylindrical tessellation
  boundaries. Symmetric deviation with unchanged vertex/triangle counts and a
  0.002 mm cap preserves a much tighter bound than the 0.05 mm mesh tolerance.
- A real successful export is still not a correct output-member decision. The
  X12 candidate therefore retains all five unresolved questions in every
  consumer-facing report.

## Keep

- Exact provenance and configuration selectors before model aggregation.
- Vendor-derived images/artifacts local until redistribution approval.
- Candidate, semantic review, conversion verification and support as separate
  states.
- Generated consumer registries that default to zero loadable assets.
- Toy protocol/plant/visual evidence explicitly separated from physical and
  rigid-body claims.

## Next iteration

1. Build an independent-review workflow that records reviewer identity,
   timestamp, exact occurrence/component choices, origin plane and physical-
   sign questions without editing generated evidence by hand.
2. Review/reject the X12 pilot, then process the assembly cohort in risk order;
   route flattened and shell-only sources through explicit re-source/partition/
   healing decisions.
3. Generate a shared host/ROS/simulator runtime asset registry, with local-only
   and redistributable publication states kept distinct.
4. Replace browser demo plant constants with a formal sourced/uncertainty
   schema before any model-specific fidelity claim.
5. Continue the control stack: real ESP32 transport/PAL wiring, scheduler retry/
   bus-off behavior, host adapters and ROS hardware interface remain open.
