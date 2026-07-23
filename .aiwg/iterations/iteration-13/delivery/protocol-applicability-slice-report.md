# Iteration 13 protocol/applicability slice verification

Status: `PASS / G13.1 BASELINE CLOSED`

## Outcome

The project now has one source-bound, model-complete protocol applicability
denial corpus:

- 44 exact catalog models;
- 9 exact vendor document packages;
- 32 provenance-preserving PDF occurrences;
- 23 unique PDF hashes;
- 72 candidate model/package relationships;
- 83 candidate model/protocol-source relationships;
- 6 exact PDF-hash source-text claim fingerprints;
- 0 accepted applicability decisions;
- 0 supported models; and
- no physical or motion authority.

RMD-X V2/V3/V4 ambiguity remains explicit. FL and FLO package selection is
prefix-exact. Sensor interfaces, product manuals, drive manuals and setup
manuals cannot become motor-control protocols.

## Implemented boundaries

- strict Draft 2020-12 generated-registry schema;
- transactional source/document/archive/file/claim generator;
- exact source hashes and deterministic record identity;
- independent host schema, digest, source, join and semantic validation;
- exact model/hardware/firmware/protocol/transport/mode query;
- distinct stale/model/source/revision/transport/no-decision denials;
- no family/default/current/latest fallback;
- simulator catalog dependency on accepted applicability rather than a
  hard-coded model flag;
- critical-artifact and zero-acceptance machine-report invariants; and
- requirements/test trace registration.

This slice creates no positive applicability lifecycle. A later human-reviewed
submission/decision/event schema must bind exact installed identity and
capture evidence before any row can become accepted.

## Focused verification

- `tests/protocol_applicability/run_tests.sh`: 10/10 PASS
- `tests/simulator_runtime/run_tests.sh`: 10/10 PASS
- `tests/offline_gate_report/run_tests.sh`: 7/7 PASS
- `python3 tools/validate_traceability.py`: 77 requirements, 126 tests PASS

## Canonical full gate

- run ID: `b9de30766e95f904909567d1`
- result: `PASS`
- stages: 61/61
- critical artifacts: 25
- source manifest files: 566
- source manifest SHA-256:
  `7b2b81b8b3843c8cb93c87b19325bbb1aa92502d132cbc59d3e9d4cee2a49250`
- accepted applicability: 0/44
- exact-model simulation ready: 0/44
- browser articulated assets ready: 0/44
- Dropbear whole-robot ready: 0
- physical work: false
- motion enable: false

## Bound artifact hashes

| Artifact | SHA-256 |
|---|---|
| Source claims TSV | `dda9520526c004fc4752404be90d3488ffdc92b66548eb2f0d31abf3890dad20` |
| Applicability schema | `8f6fd25df7eac07cea58bb4e99122ac83f156dd66314b2a78e29d177feeb1af1` |
| Generated applicability registry | `3c258cd2e9fc58307845a6a0fe6f048eabeedadf10878542e53ff5beb8d60937` |
| Independent host consumer | `2bd151a73c5148c44a6a9b7254fb96b48dc69d4a91061624b97321515cab70d8` |
| Host/browser simulator catalog | `29a2c0abc2b5f4fde5d27c14eb1a4277c33692c33cafe8a48b4a19275f83fee6` |

## Remaining G13.1 follow-on

The candidate/denial baseline is complete. Positive admission remains a later
controlled transition requiring:

1. an exact installed hardware and firmware identity;
2. an exact source occurrence and protocol/transport/mode;
3. observed command/response capture hashes;
4. an independent competent human reviewer and approver;
5. validity/expiry and revocation semantics; and
6. a support-false decision that grants only applicability.
