# Plant candidate decision records

This directory is the controlled human-review intake for plant parameters
extracted from official MYACTUATOR PDF manuals.

- `submissions/*.json` are immutable records from the assigned
  `plant_source_extractor`.
- `events/*.json` are immutable decisions from the separately assigned
  `plant_fact_reviewer`.
- Accepted values are generated under
  `generated/myactuator/plant/candidate_decisions/source_facts/`; never place
  hand-authored accepted facts there.

The lifecycle is fail-closed. Draft or incomplete reviewer assignments,
machine/automation actor identities, source-hash drift, ambiguous values
without explicit resolutions, non-independent review, conflicting active
facts, invalid transitions, and unsupported unit conversions produce no
authoritative source fact. These records grant neither motor support nor
physical-motion authority.
