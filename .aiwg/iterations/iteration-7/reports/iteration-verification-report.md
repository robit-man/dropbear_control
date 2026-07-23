# Iteration 7 verification report

- Result: `PASS-OFFLINE-WITH-EXTERNAL-REVIEW-CARRY`
- Unified gate: `OFFLINE_GATE_OK`
- Evidence boundary: specification, deterministic host/native tests, generated
  artifact drift checks and ESP32 compile only
- Powered hardware, bench, HIL and robot evidence: not performed

## Delivered

### Independent CAD review mechanics

- strict independent-decision schema, semantic validator and generated X12
  draft;
- self/automation signatures, unanswered questions, incomplete/overlapping
  occurrence sets, hash drift and invalid frame review fail closed;
- local X12 workbench includes the exact 18 occurrences, five unresolved
  questions and local evidence images without network submission;
- no submitted decision exists, so X12 remains a candidate and support remains
  zero.

### CAD runtime boundary

- canonical local registry covers 44 models, 53 source variants and 53 exact
  geometry configurations;
- browser projection redacts local paths and only permits independently
  accepted redistribution-approved assets;
- host loader requires exact series/model/configuration identity, rejects
  source/candidate/procedural/traversing paths, verifies size/SHA-256 at
  admission and point of use, and permits a Dropbear binding only to refine an
  already exact selection;
- current result: 0/53 accepted configurations, 0/44 supported models, zero
  local/browser loadable assets and zero Dropbear CAD bindings.

### Plant and backend evidence boundary

- strict registry schema covers 34 required values across electrical,
  mechanical, transmission, saturation, thermal, sensor and latency domains;
- every value requires an SI unit, bounded uncertainty interval, source,
  operating-envelope applicability and validation class;
- plant applicability is exact across series, model, hardware revision, drive
  firmware, protocol version, transport and control mode;
- typed backend resolution requires exact backend ID and expected kind, so
  replay/protocol/toy/plant/rigid-body/physical identities cannot silently
  substitute;
- browser toy data is bound to the generated `browser-toy-demo-v1` descriptor;
- current result: 44/44 catalog models explicitly covered, zero sourced or
  physically validated parameter sets, zero runtime-loadable physical plants.

### ESP32 integration seam

- preserved `main.cpp`, PAL, WebSerial, `MotorController`, family drivers and
  MCP2515 paths were inventoried without being overwritten or silently wired;
- a no-loss host/config/lease/SI/native/response/state mapping and staged M0–M7
  migration sequence are documented;
- allocation-free C++11 transport runtime bounds each service call to at most
  16 RX frames and 16 TX attempts;
- explicit send failure and bus-off clear response expectations, latch safety
  and make failed safety actions retryable after transport recovery;
- `NoIoCanTransport` cannot report ready or successful I/O;
- no real ESP32 CAN adapter is installed and the production runtime remains
  disconnected from the user prototype loop.

## Verification totals

- requirements: 77
- traceability rows: 77
- sources: 20
- ADRs: 10
- work packages: 20
- test-catalog IDs: 101
- trace links: 48
- native transport-runtime scenarios: 8, normal and ASan/UBSan
- host CAD admission scenarios: 10
- plant registry/backend scenarios: 8
- ESP32 seam static assertions: 5
- web regression suites: 6, all pass
- ESP32 target: `esp32`, compile only
- RAM: 22,360 / 327,680 bytes (6.8%)
- flash: 299,325 / 1,310,720 bytes (22.8%)

## Holds and non-claims

- X12 decision: no independent submission; five questions unresolved.
- CAD: source import/candidate articulation is not semantic acceptance.
- Plant: schemas and synthetic fixtures are not real motor parameters.
- Dropbear: generated configuration digest remains
  `dd8909bceece765e80d83d7d3f93196d6967b4f3ae72e20fdee6f29d21a81cba`,
  incomplete and motion-denied.
- ESP32: legacy CAN success stub, 500 kbit/s/ID conflicts and parallel prototype
  writers remain isolated defects, not production adapters.
- No exact installed tuple, safe stop/brake behavior, independent power cut,
  physical sign/limit/calibration, HIL, endurance or robot release is proven.

## Independent X12 handoff

An identified independent reviewer must open
`generated/myactuator/cad/review_workbenches/step-e7d99e7e0d9683017c1a/index.html`,
inspect the local evidence, answer all five questions and export a decision.
The decision must pass:

```bash
python3 tools/manage_cad_review_decisions.py --validate <decision.json>
```

Only a validated submitted decision belongs in
`assets/myactuator/cad_decisions/`. Even acceptance grants no motor, plant,
firmware or robot support; released artifacts must still be rebuilt and
verified from the decision.
