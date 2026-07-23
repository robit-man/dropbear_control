# MYACTUATOR CAD and plant evidence-intake handoff

Status: `GENERATED-DRAFTS-COMPLETE / HUMAN-SUBMISSIONS-ABSENT`

The local intake package at
[`generated/myactuator/evidence_intake/index.html`](../generated/myactuator/evidence_intake/index.html)
turns the unified review queue into exact, source-bound working packets:

| Packet class | Subjects | Tasks | Ready | Blocked |
|---|---:|---:|---:|---:|
| CAD semantic review | 53 configurations | 689 | 41 | 12 |
| Plant source extraction | 44 models | 1,672 | 44 | 0 |
| **Total** | **97** | **2,361** | **85** | **12** |

Every packet binds its review-queue item, exact subject, candidate sources,
local cached source bytes, SHA-256 identities, required human roles,
submission preconditions and controlled output schema. Generation re-hashes
all referenced STEP files, PDFs, review packets and images before emitting a
draft.

These are handoff drafts, not evidence. All responses are null, assignments
are currently absent, accepted counts are zero, and every packet explicitly
denies support, physical action and motion authority.

## CAD workflow

Each exact configuration receives the same 13 explicit determinations:

1. fixed housing;
2. rotating output member or reviewed partition;
3. residual-member disposition;
4. source unit and scale;
5. source-to-canonical frame;
6. physical output axis;
7. output-joint origin;
8. zero pose;
9. positive direction and motor/encoder sign;
10. articulation behavior;
11. visual/collision mesh disposition;
12. qualified mass-property source; and
13. license or redistribution decision.

The 41 review-ready configurations have local source geometry, component or
occurrence inventories, and rendered packets. The other 12 remain
`source_or_partition_needed`: a generated form does not make an inseparable,
high-component-count or shell-only source reviewable.

A CAD packet cannot be submitted directly as a decision. Review must first
produce an exact candidate hypothesis and export/partition record. A resulting
decision belongs in `assets/myactuator/cad_decisions/` and must pass
`tools/manage_cad_review_decisions.py`.

## Plant workflow

Every catalog model receives 38 extraction tasks:

- 34 electrical, mechanical, transmission, saturation, thermal, sensor and
  latency parameters; and
- four operating-envelope ranges.

Each task names the canonical unit and only the exact candidate product-manual
occurrences for that model. If a source does not state a value, the task stays
missing. Family defaults, CAD-derived estimates, demo parameters and synthetic
plant values cannot fill it.

One observed field becomes one
`myactuator-plant-source-fact/1` record in
`assets/myactuator/plant_source_facts/`. That record must bind the exact PDF
hash, page and table/curve locator, original value/unit, explicit SI
conversion, uncertainty and operating condition. Extraction remains
unreviewed until a different qualified human accepts or rejects it.

Source-fact completion is still narrower than an admitted plant. Runtime
simulation additionally requires a qualified parameter set, fit/holdout
correlation, operating-envelope validation and exact CAD/axis binding.

## Rebuild and verification

```bash
python3 tools/generate_evidence_intake.py --check
tests/evidence_intake/run_tests.sh
```

Intentional regeneration uses:

```bash
python3 tools/generate_evidence_intake.py --write
```

The generator builds and validates the complete 97-packet package before
transactionally replacing the prior output directory. Input failure preserves
the prior package. Any queue, campaign, ledger, assignment, schema or bound
source-byte drift changes the intake identity and requires re-review.
