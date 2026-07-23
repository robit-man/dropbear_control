# Iteration 13 exact-model plant evidence ledger verification

Status: `PASS / G13.3 SOFTWARE LEDGER CLOSED`

## Outcome

The project now has one model-complete, hash-bound plant evidence work queue:

- 44 exact catalog model identities and package revisions;
- 15 pinned product-manual occurrences;
- 106 exact model/manual candidate relationships;
- 7 parameter domains;
- 34 required parameter fields per model;
- 1,496 explicit model/parameter requirements;
- 4 required operating-envelope ranges per model;
- 176 explicit model/envelope requirements;
- 0 accepted source facts;
- 1,672 null/blocking evidence states;
- 0 qualified runtime plants;
- 0 correlated models; and
- no support, physical I/O or motion authority.

The ledger uses the same parameter names, units and model forms as the runtime
plant registry. Every model has exact candidate manual navigation, but package
placement does not fill a value. RMD-X retains four candidate product-manual
occurrences across V2/V3/V4 packages; FL and FLO remain prefix-exact.

## Implemented boundaries

- strict Draft 2020-12 source-fact and generated-ledger schemas;
- exact model/key/package and document occurrence/SHA joins;
- one-based PDF page, printed page, table/clause and source-label provenance;
- explicit source unit, normalized SI unit and conversion semantics;
- separate source-stated, transcription, digitization, derivation, fit,
  measurement and unknown uncertainty classes;
- independent reviewer identity for acceptance;
- no family/default/latest, CAD-derived, browser-demo or synthetic fill;
- separate source-fact, runtime-plant and correlation states;
- a static local no-network review/index view;
- transactional failure before output replacement;
- critical-artifact and zero-promotion machine-report invariants; and
- requirements/test trace registration.

The pinned product sheets visibly contain candidate values for fields such as
gear ratio, rated/peak speed and torque, torque constant, resistance,
inductance and some rotor inertias. They have not been mass-transcribed or
independently reviewed in this baseline. Friction, compliance, efficiency,
thermal RC, sensor noise and latency generally remain bench/vendor work.

## Focused verification

- `tests/plant_evidence_ledger/run_tests.sh`: 10/10 PASS
- `tests/offline_gate_report/run_tests.sh`: 7/7 PASS
- `python3 tools/validate_traceability.py`: 77 requirements / 128 tests PASS

## Canonical full gate

- run ID: `8fa70dffd42a189e804a97cc`
- result: `PASS`
- stages: 63/63
- critical artifacts: 27
- source manifest files: 581
- source manifest SHA-256:
  `43a1ab23c42b440aa2b5ada594feeaf1d8c5e190e5eba08d9e71f2b0943d213a`
- tracked diff SHA-256:
  `bbd6ab4b33d751a687883df6a4e741821fd6cbd5a71247f3139b6c66c008cf80`
- accepted source facts: 0
- real plant parameter sets: 0
- exact-model simulation ready: 0/44
- physical work: false
- motion enable: false

## Bound artifact hashes

| Artifact | SHA-256 |
|---|---|
| Source-fact schema | `9bdc332400af9a29d4818270e052dfdde83c1ee83041dc06f3c4a52d70b0a67e` |
| Evidence-ledger schema | `d00a58578cf9e8ff6b61512ce2c114796577d99abf55b7ed9ec6393680c0b562` |
| Generator | `348b336a948ea0fdc0f828a7a57843e61b7ac7cb472952975880eaef573f0573` |
| Generated ledger | `e667bfca290fa39b1b755a4502ade8577b9251df7dd4856881fd4b9e6fc2e428` |
| Local HTML index | `965177d16d13c5ce628249a49b7938c7faee2c89c6f554b5ede63056cc0d60d6` |
| Canonical gate report | `d9772731700b5d8c779a3d2a95910d20074b2f80328d0da29f4070e9dbf24999` |

## Next evidence transition

G13.3 closes the model-complete missing-evidence ledger, not the plant corpus.
The next controlled transitions are:

1. transcribe exact product-sheet facts with PDF page/table provenance;
2. independently review conversion and uncertainty;
3. acquire vendor clarification or bench-identify absent domains;
4. freeze training/holdout correlation protocols and operating envelopes;
5. create complete exact-tuple runtime parameter sets; and
6. admit sourced and physically correlated evidence classes separately.
