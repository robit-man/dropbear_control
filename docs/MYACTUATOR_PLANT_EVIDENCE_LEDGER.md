# MYACTUATOR exact-model plant evidence ledger

Status: `MODEL-COMPLETE / SOURCE-FACTS-UNREVIEWED-OR-MISSING / NO REAL PLANTS`

The generated ledger at
[`generated/myactuator/plant/evidence_ledger/ledger.json`](../generated/myactuator/plant/evidence_ledger/ledger.json)
turns “we need real motor models” into an exact 44-model evidence matrix. Its
local static review view is
[`generated/myactuator/plant/evidence_ledger/index.html`](../generated/myactuator/plant/evidence_ledger/index.html).

The ledger is deliberately not a parameter database populated with plausible
family values. It identifies every required field, the candidate pinned
MYACTUATOR product manuals for the exact model, accepted and pending
hash/page/table-bound facts, and every remaining blocker. A missing value is
`null`; it cannot inherit from another model, family, browser demo, CAD
geometry, protocol emulator, or synthetic test fixture.

## Exact baseline

| Item | Count |
|---|---:|
| Catalog models | 44 |
| Candidate product-manual occurrences | 15 |
| Exact model/manual candidate relationships | 106 |
| Parameter domains | 7 |
| Required parameter fields per model | 34 |
| Model/parameter requirements | 1,496 |
| Required operating-envelope ranges per model | 4 |
| Model/envelope requirements | 176 |
| Accepted source facts | 0 |
| Qualified runtime plant sets | 0 |
| Physically correlated models | 0 |

The 34 required fields implement the same contract as the runtime plant
registry:

- electrical: resistance, inductance, torque constant, back EMF, q-axis
  current limit;
- mechanical: motor and output inertia, Coulomb and viscous friction;
- transmission: ratio, forward/reverse efficiency, torsional stiffness and
  backlash;
- saturation: motor/output speed, continuous/peak torque and peak duration;
- thermal: two-node resistance/capacity and winding/case temperature limits;
- sensor: position quantization/noise, velocity noise and current noise; and
- latency: command, loop, sample and feedback delays plus jitter.

Every model also needs bounded supply voltage, ambient temperature, output
speed and output torque envelopes.

## What the pinned manuals can and cannot provide

The current official product sheets visibly contain useful exact-model
candidates such as gear ratio, rated/peak speed and torque, torque constant,
phase resistance, phase inductance and, for some families, rotor inertia.
Those values will be transcribed as individual source-fact records with the
exact PDF occurrence ID, file SHA-256, one-based PDF page index, printed page,
table or clause, original unit and label, normalized SI value, conversion and
uncertainty.

The product sheets do not appear to provide a complete physical model.
Friction, forward/reverse efficiency, output compliance, backlash in a
consistent model form, thermal RC values, sensor noise, command/feedback delay
and jitter generally require explicit vendor clarification, controlled
derivation, or bench identification. None may be fabricated to make a model
loadable.

## Source-fact lifecycle

Source facts live under
[`assets/myactuator/plant_source_facts/`](../assets/myactuator/plant_source_facts/)
and validate against
[`schemas/myactuator-plant-source-fact.schema.json`](../schemas/myactuator-plant-source-fact.schema.json).
Each record has a stable ID derived from model, target, observation and exact
document locator.

The states are intentionally separate:

1. `unreviewed`: machine-assisted or manual extraction; navigation only;
2. `accepted`: a different named reviewer has checked the exact source,
   conversion, uncertainty and model binding;
3. `rejected`, `superseded`, or `revoked`: retained provenance, no value;
4. complete source-fact matrix: all required facts and envelopes reviewed;
5. qualified runtime parameter set: the stricter plant registry additionally
   binds exact hardware/firmware/protocol/control applicability;
6. bench, HIL, or robot correlation: fixed experiment and holdout evidence;
7. model simulation admission: only the requested evidence class is exposed.

An accepted manual fact does not itself create a plant. A sourced plant and a
physically correlated plant remain different claims.

## Uncertainty policy

The schema keeps these classes non-substitutable:

- source-stated bounds;
- transcribed display resolution;
- digitization bounds;
- derivation bounds;
- fit confidence intervals;
- measurement bounds; and
- unknown.

An accepted fact requires finite bounded uncertainty in the canonical unit.
“Unknown” remains useful on an unreviewed extraction but cannot satisfy the
field. A fitted value cannot be relabeled as an official stated value, and a
training fit is not holdout correlation.

## Generation and tests

```bash
python3 tools/generate_plant_evidence_ledger.py --check
tests/plant_evidence_ledger/run_tests.sh
```

After intentionally adding canonical source-fact files:

```bash
python3 tools/generate_plant_evidence_ledger.py
```

The generator checks catalog/applicability/plant generation hashes, exact
model/package identity, candidate manual membership, document occurrence and
SHA-256, page/table locators, SI conversions, review independence, uncertainty
bounds, field cardinality, summary counts and the ledger digest. Failed input
validation occurs before output replacement.

## Current decision

The ledger is complete as a missing-evidence work queue, not as a simulator
plant corpus. It authorizes no physical I/O, motion, exact-model fidelity,
performance prediction or motor support.
