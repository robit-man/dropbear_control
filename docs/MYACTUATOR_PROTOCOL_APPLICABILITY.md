# MYACTUATOR protocol-source and applicability registry

Status: `POSITIVE-LIFECYCLE-READY / ZERO REAL ACCEPTED APPLICABILITY`

The registry at
[`generated/myactuator/protocol_applicability/registry.json`](../generated/myactuator/protocol_applicability/registry.json)
provides a complete, deterministic navigation layer over the pinned vendor
manual corpus:

- 44 exact catalog models;
- 9 document packages;
- 32 PDF occurrences;
- 23 unique PDF byte hashes;
- 72 model-to-package candidate relationships;
- 83 model-to-motor-control-protocol-source candidate relationships; and
- 0 accepted model/hardware/firmware/protocol applicability decisions.

These are candidate source relationships only. Package placement, a vendor
filename, PDF text extraction, shared bytes, a protocol revision, or a passing
codec test does not prove compatibility with a motor.

## Evidence boundaries

The generator classifies every PDF occurrence into one non-substitutable
scope:

| Scope | Occurrences | Permitted use |
|---|---:|---|
| Motor-motion protocol | 7 | Candidate wire-command evidence |
| Fieldbus protocol | 3 | Candidate EtherCAT control evidence |
| Sensor interface | 3 | Encoder/electrical interface investigation only |
| Drive manual | 3 | Candidate drive configuration evidence |
| Product manual | 15 | Product characteristics/source-fact extraction |
| Setup manual | 1 | Setup-tool investigation |

All six source-text claim fingerprints remain
`source_*_unreviewed`, `human_reviewed=false`, and
`applicability_authority=false`. The checked-in claims bind exact PDF SHA-256
to the extracted cover/catalog locator. They are not review signatures.

Duplicate bytes retain occurrence identity. For example, the V4.4 PDF shared
by RH, CEM, and RMD-H has one byte hash but three package occurrences. No
applicability decision may cross those occurrence/package boundaries
implicitly.

## Candidate selection rules

- RMD-X models retain the V2, V3, and V4 package candidates simultaneously.
  The registry does not infer a drive generation from a marketing model or
  package date.
- RH, RMD-L, CEM, and RMD-H models receive only their exact series package.
- `FL-*` and `FLO-*` select separate document packages even though the
  catalog series label is `FL-FLO`.
- FL/FLO encoder-interface manuals do not enter
  `candidate_protocol_occurrence_ids`.
- There is no family, wildcard, default, current, or latest-document lookup.

## Runtime behavior

The host consumer
[`protocol_applicability.py`](../host/myactuator_lib/protocol_applicability.py)
requires an exact registry generation, model key, series, model, installed
unit, source occurrence, hardware revision, drive firmware, protocol revision,
transport, and control mode. It distinguishes stale generation, wrong model,
cross-package source, revision disagreement, and undeclared transport.

The current terminal result for a syntactically and relationally valid tuple
is still:

```text
no_accepted_applicability
```

The V2 registry can now carry independently reviewed exact-tuple decisions.
Admission compares every field and returns `allowed` only for a byte-for-byte
matching accepted subject. Applicability acceptance still returns
`support_granted=false` and `physical_motion_authority=false`.

The simulator runtime catalog hashes and independently consumes this registry.
Consequently,
`protocol_model_firmware_applicability_verified` is derived from accepted
evidence rather than hard-coded. It remains false for 44/44 models.

## Exact-tuple decision lifecycle

Create a draft only after the exact installed identity is available:

```bash
python3 tools/manage_protocol_applicability_decisions.py \
  --write-template /tmp/protocol-decision.json \
  --model-key MODEL_KEY \
  --protocol-occurrence-id OCCURRENCE_ID \
  --hardware-revision EXACT_REVISION \
  --drive-firmware EXACT_FIRMWARE \
  --installed-unit-id EXACT_UNIT_ID \
  --transport classic_can \
  --control-mode EXACT_CONTROL_MODE
```

An accepted submission must bind the installed-inventory entry and artifact
hash; exact PDF occurrence/hash/revision/locator; exact hardware, firmware,
transport and control mode; command/response or bench manifest and trace
hashes; and distinct evidence submitter, source reviewer and decision reviewer
identities.

A listen-only trace may inform discovery but cannot establish command/control
mode applicability. Drafts, self-review, automation identities, cross-package
sources, source drift and filename/decision-ID disagreement fail validation.
Only submitted records named `protocoldecision-<digest>.json` enter the
controlled decision directory.

## Rebuild and verify

```bash
python3 tools/generate_protocol_applicability_registry.py --check
python3 tools/manage_protocol_applicability_decisions.py --check-directory
tests/protocol_applicability/run_tests.sh
tests/simulator_runtime/run_tests.sh
```

Regeneration is intentional:

```bash
python3 tools/generate_protocol_applicability_registry.py
python3 tools/generate_simulator_runtime_catalog.py --write
```

Source TSV or generated-registry drift revokes host and simulator admission.
Failed generation does not replace the last valid output.

## Real acceptance still required

The positive lifecycle and synthetic acceptance/denial tests now exist, but
the real decision directory remains empty. A real decision must bind:

```text
installed unit + series + model + hardware revision + drive firmware
+ protocol revision + transport + control mode
+ source/capture hashes + independent reviewer decision
```

That decision will establish protocol applicability only. It must not grant
complete motor support, physical motion authority, CAD fidelity, plant
fidelity, safe-stop evidence, or HIL success.
