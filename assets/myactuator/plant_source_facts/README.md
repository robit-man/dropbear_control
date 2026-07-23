# Plant source facts (legacy intake retired)

Do not add accepted facts to this directory.

Authoritative source facts are materialized only by the independently reviewed
candidate lifecycle in `assets/myactuator/plant_candidate_decisions/` and are
written to
`generated/myactuator/plant/candidate_decisions/source_facts/`.

This directory remains only to make the retired hand-authored intake explicit.
It grants neither motor support nor physical-motion authority.

This directory holds exact-model facts transcribed or derived from pinned
MYACTUATOR documents. Each JSON file is one
`myactuator-plant-source-fact/1` record and its filename must equal
`<fact_id>.json`.

A source fact must identify the catalog model and package revision, the exact
document occurrence and SHA-256, a one-based PDF page index, printed page
label, table or clause, original label and unit, normalized SI value, explicit
conversion, uncertainty class, extraction identity, and independent review
state.

An unreviewed extraction is useful navigation evidence only. It does not fill
a plant requirement. Acceptance requires an independent reviewer; the
reviewer and extractor identities must differ. A fact never grants motor
support, physical I/O, or motion authority.

The deterministic navigation layer is
`generated/myactuator/plant/spec_candidates/registry.json`. Generate or check
it with:

```bash
python3 tools/generate_plant_spec_candidates.py
python3 tools/generate_plant_spec_candidates.py --check
```

Reviewers start from the exact candidate IDs linked in each generated plant
handoff packet. They must verify the displayed page/table/header and original
label, unit and value against the local PDF, resolve alternatives and
semantic blockers, state the SI conversion and uncertainty, and then create a
new source-fact record. Candidate JSON is generated and must not be edited or
copied wholesale into this directory. Direct label/unit mappings still
require independent review.

Do not place synthetic parameters, family defaults, inferred values from CAD,
or browser-demo values here. Fitted and bench-measured records remain distinct
from official stated facts and cannot be relabeled to increase source
coverage.
