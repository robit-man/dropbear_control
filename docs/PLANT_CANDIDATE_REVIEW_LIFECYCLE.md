# Plant candidate review lifecycle

## Authority boundary

The product-spec candidate registry is machine-produced navigation evidence.
It cannot accept a value. An active plant source fact exists only when the
controlled lifecycle replays:

```text
exact PDF candidate
  -> immutable assigned-human extractor submission
  -> immutable independent assigned-human review event
  -> deterministic active V2 source fact
  -> plant evidence ledger
```

The current tracked baseline has 531 candidates, zero submissions, zero
events, zero accepted decisions and zero active facts. Both plant review roles
remain unassigned. Nothing in this workflow grants motor support, physical
I/O or motion authority.

## Controlled records

Human records live under
`assets/myactuator/plant_candidate_decisions/`:

- `submissions/*.json` conform to
  `myactuator-plant-candidate-submission/1`;
- `events/*.json` conform to
  `myactuator-plant-candidate-event/1`.

Generated outputs live under
`generated/myactuator/plant/candidate_decisions/`:

- `registry.json` is the replay result;
- `source_facts/*.json` contains only currently active accepted
  `myactuator-plant-source-fact/2` records.

Do not hand-edit generated facts. The plant evidence ledger verifies its file
set and every fact hash against the decision registry.

## Submission requirements

An acceptance proposal binds the exact candidate-registry hash, candidate
hash, table, model and extractor assignment revision. It must:

1. identify a declared plant-contract target;
2. preserve the raw source unit and select exact parsed number indexes;
3. provide an exact normalized SI value or reviewed derivation;
4. resolve every mapping blocker and any qualifier, annotation or alternative;
5. state bounded uncertainty in the canonical target unit;
6. preserve operating-condition unknowns rather than inventing defaults; and
7. carry no support or motion authority.

Reject and defer submissions cannot contain a proposed fact.

## Independent event replay

Events have one global, contiguous sequence and strictly increasing UTC review
times. The assigned `plant_fact_reviewer` must be a human distinct from the
assigned `plant_source_extractor`. Valid transitions are:

| Event | Transition |
|---|---|
| `accept` | `submitted -> accepted` |
| `reject` | `submitted -> rejected` |
| `defer` | `submitted -> deferred` |
| `revoke` | `accepted -> revoked` |
| `supersede` | old `accepted -> superseded` and replacement `submitted -> accepted` atomically |

Replay denies multiple active facts for one candidate and multiple active
facts for the same exact model/target field.

## Provenance

Each materialized V2 fact contains an Entity–Activity–Agent lineage:

- the generated fact is the entity;
- the exact candidate and PDF SHA-256 entity are its derivations;
- the accepting review event is the generation activity;
- extractor and reviewer are distinct hashed agents.

The fact also binds submission/event hashes and a decision-registry generation
hash. That generation hash deliberately covers registry sources, submissions,
events and replay states before generated fact hashes are added; the complete
registry digest then binds the resulting fact list. This avoids a digest
cycle while preserving both directions of verification.

## Reproduction

```bash
python3 tools/generate_plant_spec_candidates.py --check
python3 tools/manage_plant_candidate_decisions.py --check
python3 tools/generate_plant_evidence_ledger.py --check
tests/plant_candidate_decisions/run_tests.sh
```

The focused lifecycle suite includes a positive synthetic review path plus
assignment, actor independence, source binding, ambiguity, conversion,
transition, ordering, conflict, revocation, supersession, transaction and
authority adversaries. It performs no hardware I/O.
