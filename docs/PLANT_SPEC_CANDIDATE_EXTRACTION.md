# Product-specification candidate extraction

## Purpose

This layer turns the locally cached, pinned MYACTUATOR PDFs into deterministic
review navigation. It does not turn PDF text into accepted plant parameters.
The separation is:

```text
official PDF page
  -> coordinate-preserving raw candidate
  -> independent applicability and semantic review
  -> immutable source fact
  -> explicitly selected complete parameter set
  -> exact-model plant admission
  -> optional physical correlation class
```

Skipping a step is forbidden. In particular, a direct label/unit match is
still not a source fact, and a complete datasheet-derived set is not a
physically correlated plant.

## Current exact result

| Measure | Result |
|---|---:|
| Pinned document occurrences processed | 15 |
| Product-specification sheets used for model tables | 9 |
| PDF pages digested | 215 |
| Pages with no extractable text | 1 |
| Catalog models with one exact table/header | 44/44 |
| Extracted candidates | 531 |
| Direct label/unit mapping candidates | 89 |
| Semantic-review mapping candidates | 317 |
| Unmapped candidates | 125 |
| Candidates linked to exact handoff tasks | 406 |
| Unreviewed candidates | 531 |
| Accepted candidates | 0 |
| Runtime-admissible candidates | 0 |
| Accepted plant source facts | 0 |
| Exact-model runtime plants | 0/44 |

The 89 direct candidates have no known label/unit mapping blocker, but still
need independent confirmation of table applicability, shaft/phase basis,
conditions and uncertainty. The 317 semantic-review candidates retain
specific blockers such as rated-versus-continuous duty, no-load-versus-limit,
line-versus-phase quantities, RMS-versus-q-axis current, motor-versus-module
torque constant, missing peak duration, or unresolved operating point. The
125 unmapped candidates remain visible because deleting inconvenient source
values would make the extraction lossy.

## Reproducible inputs and outputs

The environment is locked in
[`tools/poppler-text-environment-lock.json`](../tools/poppler-text-environment-lock.json).
The exact model/page/table selection is
[`assets/myactuator/plant_spec_extraction_plan.json`](../assets/myactuator/plant_spec_extraction_plan.json).
The generated machine registry and local review index are:

- [`generated/myactuator/plant/spec_candidates/registry.json`](../generated/myactuator/plant/spec_candidates/registry.json)
- [`generated/myactuator/plant/spec_candidates/index.html`](../generated/myactuator/plant/spec_candidates/index.html)

Generate and verify them from the repository root:

```bash
python3 tools/generate_plant_spec_candidates.py
python3 tools/generate_plant_spec_candidates.py --check
tests/plant_spec_candidates/run_tests.sh
```

The generator uses local `pdftotext` 24.02.0 with `-bbox-layout -enc UTF-8`.
It does not use network access. Every manual file hash, page text digest,
one-based PDF page index, exact model header and bounding box is retained.
Every page is processed, including pages not selected for a product table, so
a changed front matter or inserted page cannot silently preserve stale page
references.

## Candidate contract

Each selected model table binds:

- exact catalog model key, series, model and package revision;
- exact document occurrence and file SHA-256;
- one-based PDF page, canonical page-text SHA-256 and stable table ID;
- printed model-header text and bounding box;
- raw property label, unit and value with their bounding boxes;
- parsed scalar, range, qualification, alternatives or annotation;
- suggested target field, conversion type and normalized unit when possible;
- explicit semantic blockers;
- an `unreviewed` decision and false runtime admission.

There is no family fallback, “latest manual” lookup, fuzzy model selection or
automatic conflict resolution. Alternatives such as multiple ratios stay
alternatives. Ranges stay ranges. A scalar input voltage cannot fill a
required voltage envelope. Source labels are never rewritten to make a
mapping appear cleaner.

## Human review workflow

Review is performed from the generated evidence-intake packet for one exact
model:

1. Assign an extractor/reviewer pair under the role and independence rules.
2. Open the locally cached PDF referenced by the packet.
3. Navigate to the bound page and confirm the exact model header and table.
4. Compare the raw label, unit and value against the displayed page.
5. Confirm document applicability to the exact catalog model and record any
   hardware/firmware scope limitation.
6. Resolve alternatives, annotations, footnotes, duty conditions and
   line/phase, motor/module/output and input/output shaft bases.
7. Accept, reject, defer or remap the candidate with a reason.
8. For an accepted value, state the exact SI conversion and uncertainty
   class.
9. Create an immutable
   `myactuator-plant-candidate-submission/1` record under the controlled
   intake; never edit generated candidate or fact JSON into a decision.
10. Record an independent `myactuator-plant-candidate-event/1` from the
    assigned reviewer. The lifecycle alone materializes the accepted
    `myactuator-plant-source-fact/2`.
11. Select mutually compatible facts into the exact model's 34-parameter and
    four-envelope set.
12. Run schema, analytic, cross-field and exact-model plant tests.

One source value may legitimately be rejected for the current runtime
contract or may motivate a future schema addition. Rejection is not data loss
because the raw candidate remains in the registry.

## Admission boundaries

The candidate registry grants none of the following:

- motor or protocol support;
- installed hardware/firmware applicability;
- a complete real plant parameter set;
- exact-model simulation readiness;
- physical correlation;
- accepted CAD/output-shaft semantics;
- CAN access, physical action or motion authority.

Runtime admission still requires a complete, selected, reviewed parameter set
with required provenance and uncertainty, plus every independent protocol,
configuration, graph, CAD, safety and backend dependency. Physical fidelity
additionally requires an authorized fixture and declared holdout metrics.

## Verification coverage

The focused suite checks exact PDF/page/hash coverage, the one-model/one-table
plan, bounding-box provenance, representative cross-family values and
ambiguities, parse completeness, semantic distinctions, local-only
byte-stable generation, evidence-intake target binding and denial under
candidate/page/target/authority/tool/source mutations. The unified offline
gate also binds the registry as a critical artifact and records its exact
counts while asserting zero candidate acceptance and runtime admission.

The executable review and materialization contract is documented in
[`PLANT_CANDIDATE_REVIEW_LIFECYCLE.md`](PLANT_CANDIDATE_REVIEW_LIFECYCLE.md).
