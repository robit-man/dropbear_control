# MYACTUATOR / Dropbear coverage dashboard

Status: **GENERATED-COVERAGE-COMPLETE / OBJECTIVE-EVIDENCE-INCOMPLETE**

The canonical machine-readable dashboard is
[`generated/myactuator/coverage_dashboard/dashboard.json`](../generated/myactuator/coverage_dashboard/dashboard.json).
The local, network-free review surface is
[`generated/myactuator/coverage_dashboard/index.html`](../generated/myactuator/coverage_dashboard/index.html).

## Purpose and authority boundary

The dashboard answers four different questions without collapsing them:

1. Is every requirement structurally linked to design, work packages, planned
   tests and phase gates?
2. Which cataloged verification items are implemented offline, still planned,
   or held for physical evidence?
3. What is the exact protocol/CAD/plant/simulator state of every MYACTUATOR
   model and CAD configuration?
4. Which objective-level facts still prevent a complete MYACTUATOR/Dropbear
   release?

It does **not** assert that a structurally traced requirement is satisfied.
It does not reproduce or replace the latest test result; that authority remains
with
[`generated/verification/offline_gate_report.json`](../generated/verification/offline_gate_report.json).
It is not a human review, phase-gate decision, support decision, release
approval, physical-action authorization or motion authority.

## Current exact checkpoint

The generated dashboard joins:

- 77 requirements: 39 P0, 37 P1 and one P2;
- 140 cataloged verification items:
  - 105 `EXISTS-OFFLINE`;
  - 28 `PLANNED`;
  - seven `PHYSICAL-HOLD`;
  - zero `EXISTS-BASELINE`;
- 20 work packages and eight G0–G7 phase gates;
- 44 exact MYACTUATOR model identities;
- 53 exact CAD configurations;
- the 145-item evidence queue; and
- the 97-packet CAD/plant handoff.

Only three of 15 objective criteria are currently met:

- all 77 requirements have structural trace rows;
- all 44 vendor model identities are catalogued; and
- all 53 STEP configurations are acquired and joined.

The other 12 criteria remain explicit gaps. The most important exact zeros are:

- 0/44 models with accepted protocol applicability;
- 0/53 CAD configurations with reviewed housing/output/axis semantics;
- 0/44 complete sourced plant records;
- zero reviewed V1 or V2 plant execution profiles and runtime contracts;
- 0/531 accepted product-spec candidates;
- 0/44 exact-model simulation-ready models;
- zero active Dropbear source and graph generations;
- 0/12 motion-ready Dropbear actuators;
- 0/17 reviewer roles assigned;
- 0/12 installed motor slots observed;
- zero selected runtime CAN adapters; and
- 0/7 physical evidence holds completed.

These zeros are intentional evidence facts, not generator defaults.

## Reproduction and transaction rules

Generate or refresh the complete output directory:

```bash
python3 tools/generate_coverage_dashboard.py --write
```

Verify exact source hashes, JSON projection and HTML bytes without writing:

```bash
python3 tools/generate_coverage_dashboard.py --check
tests/coverage_dashboard/run_tests.sh
```

Generation occurs in a staging directory and atomically replaces the complete
output directory only after schema and semantic validation. A malformed
requirement/trace/test join, stale embedded source digest, missing source,
unknown reference, either runtime-adapter baseline drift, summary mismatch or
authority promotion fails before the previous valid output is replaced.

## Source and projection contract

The dashboard re-hashes 24 inputs, including its generator/schema, the
requirements, traceability matrix, test catalog, master plan, phase gates,
repository test entry point, and the controlled protocol/CAD/plant-fact/
plant-set/V1-runtime-adapter/V2-runtime-adapter/Dropbear registries. Its
whole-record SHA-256 covers every source record, summary,
criterion, requirement, test, work package, phase gate, model and CAD row.

Each requirement row includes its exact planned test IDs and counts by catalog
status. Every row carries `structurally_traced=true` and
`completion_asserted=false`. Every phase-gate row carries
`pass_asserted=false`; only an independently reviewed gate decision may change
that authority outside this dashboard schema.

The HTML uses no scripts, remote styles, external resources or network
requests. It is a rendering of the canonical JSON, not a second data source.

## Next use

The dashboard is the stable progress surface for the remaining long-haul work.
After any reviewed protocol/CAD/plant/Dropbear/physical evidence is accepted,
the upstream controlled registry changes first. The dashboard must then be
regenerated, its source hash must change, its objective counts must agree with
the upstream artifacts, and the complete repository gate must pass before the
new state is reported.
