# Iteration 16 product-spec candidate slice

## Delivered

- strict extraction-plan and candidate-registry schemas;
- a Poppler 24.02.0 environment lock;
- full-content processing for 15 official PDFs and 215 pages;
- exact page/table/header selection for all 44 catalog models;
- 531 coordinate-preserving raw candidates;
- structured scalar, range, qualified and alternative parsing;
- 89 direct label/unit suggestions, 317 semantic-review suggestions and 125
  intentionally unmapped values;
- exact candidate references on all 406 mappable plant handoff tasks;
- local, network-free machine JSON and human HTML outputs;
- adversarial source/page/header/target/tool/authority drift tests;
- traceability, dashboard, unified-gate and machine-report integration; and
- explicit zero acceptance, zero runtime admission, zero plant facts and zero
  exact-model simulation readiness.

## Evidence

The authoritative run result is always
[`generated/verification/offline_gate_report.json`](../../../../generated/verification/offline_gate_report.json).
The focused entry is:

```bash
tests/plant_spec_candidates/run_tests.sh
```

The generated candidate registry is:

```text
generated/myactuator/plant/spec_candidates/registry.json
```

## Non-credit

This slice does not review a candidate, create a source fact, complete a
parameter set, accept a STEP output member, establish motor support, select a
physical adapter, correlate a plant or authorize motion. Those outcomes remain
in the Iteration 16 human, CAD, simulator and physical gates.
