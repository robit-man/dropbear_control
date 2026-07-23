# Master test plan

Purpose: prove requirements at the lowest useful layer while preventing
offline evidence from being confused with powered validation. The canonical
catalog is [test-catalog.md](test-catalog.md), records use
[evidence-format.md](evidence-format.md), and requirement coverage is in
[traceability-matrix.md](../requirements/traceability-matrix.md).

## Evidence levels and environments

| Level | Environment | May prove | Cannot prove |
|---|---|---|---|
| `OFFLINE-STATIC` | Source/manifests/schema/linters | Inventory, provenance, trace consistency, forbidden claims | Runtime behavior |
| `OFFLINE-UNIT` | Host-native pure codec/safety/config tests | Deterministic functions, state/lease properties, golden vectors | ESP32 timing or physical applicability |
| `OFFLINE-BUILD` | Pinned ESP32/host/web build toolchains | Compilation, link, size and generated-view consistency | Real I/O or motor behavior |
| `SIL-PROTOCOL` | Deterministic protocol emulator | Request/response/timing/fault integration to declared emulator model | Electrical/mechanical fidelity |
| `SIL-PLANT` | Sourced actuator plant | Mode/limit/thermal response within declared assumptions | Exact physical tuple without validation |
| `SIL-ROBOT` | Headless rigid-body backend | Description, contacts, estimator/controller scenarios | Hardware stop/timing |
| `BENCH` | Exact one-motor current-limited fixture | Tuple applicability and bounded device behavior tested | Multi-node/robot behavior |
| `HIL` | Real ESP32/bus with exact actuator(s)/emulated load | Scheduler, disconnect, fault and stop timing in stated topology | Unstated load/configuration |
| `ROBOT` | Released Dropbear configuration | Integrated behavior within approved envelope | Other tuple/configuration |

## Test design rules

- Each result names requirement IDs, test ID/version, code/config/tool
  revisions, evidence class and exact support tuple when physical.
- Official golden vectors are independently transcribed and cite document
  revision plus section/table/page. Encoder and decoder expectations are not
  generated solely by the implementation under test.
- Fake monotonic clocks control lease, sample age, response and rollover tests.
- Property/model exploration must include event interleavings between admission
  and TX; fixed happy-path sequences are insufficient for SAF-001..010.
- Malformed/native/link fuzzing has deterministic seeds, bounded resource
  assertions and a retained minimized corpus.
- Simulation comparisons publish parameter sources, uncertainty and tolerances
  before execution. Tolerances are not retrofitted to make a run pass.
- Powered tests require passed G0 procedure, independent cut and immediate stop
  on unexpected identity/motion/brake/thermal/bus behavior.

## Verification stages

| Stage | Required suites | Entry | Exit |
|---|---|---|---|
| Commit/offline | SRC, CLM, CFG, PRO, SAF, LNK, build, trace, whitespace | Pinned toolchain/cache | All required offline tests pass; artifacts retained |
| SIL protocol | PRO + FW scheduler + emulator faults | G1 codec/safety core | Deterministic rates/deadlines and injected faults pass |
| Asset/plant | CAD + plant units/dynamics | Reviewed source/parameter schema | Claimed models have complete asset/uncertainty evidence |
| SIL robot | ROB + controllers/estimator/replay | Canonical registry/description | Cross-backend scenarios meet declared envelopes |
| Bench/HIL | HW fault/stop/endurance | G0 physical + exact tuple | G2/G3 evidence, reviewer and no unresolved P0 result |
| Release | Full applicable suites + security/claim validator | Candidate revision frozen | Gate checklist and evidence dependency graph pass |

## One-entry orchestration contract

WP-180 shall provide a repository command (name selected during implementation)
that, by default, runs without hardware and executes:

1. source/catalog/document/CAD acquisition-manifest validation;
2. host library tests and native codec golden/boundary/malformed tests;
3. platform-independent safety/admission/config tests;
4. ESP32 environment matrix compilation with generated config checks;
5. web protocol/simulation/UI regression tests without fabricated support;
6. trace/evidence/unsupported-claim/link/whitespace validation.

It emits one machine-readable summary and per-suite logs. Hardware/SIL tiers
are explicit opt-in profiles with fixture/backend identity; missing hardware is
`NOT_RUN`, never pass or skip-equivalent. A required `NOT_RUN` fails its gate.

## Coverage and acceptance

- 100% of P0/P1 requirement IDs map to at least one planned test and gate.
- Protocol opcode capability coverage is generated from the exact support
  record; untested capabilities are absent rather than “partial pass”.
- Safety transition/rejection-code table coverage is 100%; state/event property
  exploration records seed and explored sequence count.
- CAD inventory is 44/44 model rows and 53/53 variants; articulation acceptance
  is separately 44/44 and currently 0/44.
- Required tests have no retry-to-green policy. A flaky result fails until root
  cause and determinism evidence are reviewed.
- Coverage metrics are diagnostic; passing line coverage never substitutes for
  vector, boundary, fault, timing or physical acceptance criteria.

## Defect and evidence handling

Every failure records observed vs expected behavior, minimal reproducer,
affected tuple/requirements/risks, logs and disposition. A fix invalidates
dependent results. Results are append-only; reruns supersede by reference and
do not erase failures. Release exceptions require scope, expiry, owner and
gate approval, and cannot waive unknown safe action or physical power removal.

