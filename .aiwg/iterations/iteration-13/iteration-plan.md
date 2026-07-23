# Iteration 13 plan — exact applicability, model assets and runtime handoff

- Iteration status: `COMPLETE-OFFLINE-PHYSICAL-AUTHORIZATION-HOLD`
- Phase context: P2/P4/P5 elaboration and construction
- Entry run: `b21e1e74acfdfc70816918c6`, 60/60 stages PASS
- Entry source manifest:
  `de319a3e7f7b7b1103e900b94704dd928e47a64a4e98e9c97a15dbef0b6c888b`
- Entry governance: 77 requirements, 125 catalog tests, 24 critical artifacts
- Product baseline: 44 exact models, 53 STEP configurations, 9 document
  packages and 32 pinned PDF files
- Fidelity baseline: 0 accepted articulated configurations, 0 sourced real
  plants, 0 exact model/firmware/protocol applicability decisions
- Dropbear baseline: source/graph authority absent, 161 unresolved graph
  questions, 0 actuator/ROS mappings and 0/12 motion-ready actuators

## Iteration outcome

Turn the remaining model and runtime gaps into complete, independently
reviewable evidence campaigns. Delivery will build exact source-bound
applicability, CAD, plant, rigid-body and ROS handoff machinery. Discovery
will prepare the human and physical inputs that software cannot manufacture.

No candidate mapping, extracted PDF fact, generated CAD split, synthetic
parameter, benchmark result or plugin skeleton may grant motor support,
physical fidelity, canonical Dropbear authority or motion.

## Track A — baseline and proof ownership

| ID | Atomic work package | Exit condition |
|---|---|---|
| I13-A01 | Bind entry machine run | Iteration records exact run/source/artifact counts |
| I13-A02 | Reconcile proof ledger | Every assessment proof ID maps to this or later work |
| I13-A03 | Assign evidence class | Source, candidate, reviewed, correlated and physical states cannot alias |
| I13-A04 | Define artifact ownership | Each generator has exclusive output namespaces |
| I13-A05 | Define revocation | Source/reviewer/config/tool drift identifies invalidated consumers |
| I13-A06 | Preserve user work | Existing ESP32/web runtime remains a named migration input |

## Track B — exact protocol and applicability corpus

| ID | Atomic work package | Exit condition |
|---|---|---|
| I13-B01 | Protocol-source claims schema | Closed schema binds document package/file/hash and claim scope |
| I13-B02 | Nine-package source map | Every document package appears exactly once |
| I13-B03 | Thirty-two-file partition | Every PDF is classified without dropping duplicate bytes/provenance |
| I13-B04 | Protocol revision identity | V4.2, V4.4, EtherCAT and interface documents remain exact |
| I13-B05 | Control versus sensor scope | Encoder/interface documents cannot become motor-motion protocols |
| I13-B06 | Forty-four-model candidate map | Every model receives only series/model-compatible source candidates |
| I13-B07 | RMD-X generation ambiguity | V2/V3/V4 documents remain candidates until exact drive generation exists |
| I13-B08 | FL versus FLO separation | Model prefix selects the correct product document set without family fallback |
| I13-B09 | Applicability decision schema | Exact hardware/firmware/protocol/transport/mode plus human evidence required |
| I13-B10 | Baseline denial registry | 44/44 models, zero accepted applicability and zero support |
| I13-B11 | Host exact admission | No family/latest/package-placement fallback; source drift revokes |
| I13-B12 | Simulator dependency | Exact-model protocol use consumes accepted applicability only |

## Track C — 53-configuration CAD review campaign

| ID | Atomic work package | Exit condition |
|---|---|---|
| I13-C01 | Campaign index | All 53 configurations grouped by assembly/flattened/shell status |
| I13-C02 | Assembly candidate batch | All 26 assembly sources have ranked member hypotheses |
| I13-C03 | Flattened candidate batch | All 27 flattened sources have component inventories/dispositions |
| I13-C04 | Exact output-member questions | Every configuration asks housing/output/axis/origin/zero/direction questions |
| I13-C05 | Duplicate geometry independence | Five duplicate-byte groups retain per-package decisions |
| I13-C06 | Shell-only lane | Five shell-only sources cannot become collision candidates |
| I13-C07 | Candidate export planning | Every exportable candidate names deterministic tool/input/output identities |
| I13-C08 | Local workbench index | Reviewer can open every packet without network access |
| I13-C09 | Decision ingestion | Independent decisions validate transactionally and never grant support |
| I13-C10 | Accepted asset transition | Only accepted decisions can populate housing/output runtime assets |
| I13-C11 | Browser release transition | License-approved assets only; local paths remain redacted |
| I13-C12 | Dropbear binding transition | Active graph may refine only exact accepted configurations |

## Track D — real plant evidence corpus

| ID | Atomic work package | Exit condition |
|---|---|---|
| I13-D01 | Source-fact schema | Manual clause/table/page/value/unit/envelope extraction is hash-bound |
| I13-D02 | Parameter-domain coverage | Electrical/mechanical/gear/friction/thermal/sensor domains remain explicit |
| I13-D03 | Missing-value semantics | Absent parameters are null/blockers, never family defaults |
| I13-D04 | Forty-four-model ledger | Every model has candidate source facts and exact missing fields |
| I13-D05 | Uncertainty policy | Stated, digitization and fitted uncertainty classes are non-substitutable |
| I13-D06 | Correlation protocol | Training and holdout experiments, metrics and envelopes are fixed |
| I13-D07 | Admission transition | Sourced plant and correlated plant are separate decisions |
| I13-D08 | Synthetic isolation | Existing synthetic fixture cannot satisfy a real-model dependency |

## Track E — rigid-body and trace interoperability

| ID | Atomic work package | Exit condition |
|---|---|---|
| I13-E01 | Engine benchmark contract | Headless, determinism, contact, closed-chain, ROS and workflow cases fixed |
| I13-E02 | Engine/version lock | Candidate engines and ABI/toolchain versions are exact |
| I13-E03 | Canonical scene input | Active graph, accepted CAD and admitted plants are required |
| I13-E04 | Joint/state parity | Rigid body consumes common units/interfaces/validity |
| I13-E05 | Trace interchange schema | Session commands/states/events serialize canonically |
| I13-E06 | Replay equality | Cross-backend input and disposition comparison is deterministic |
| I13-E07 | Current unavailable descriptor | Missing dependencies remain a non-loadable backend |
| I13-E08 | Positive synthetic fixture | Generic benchmark proves machinery without claiming Dropbear fidelity |

## Track F — ROS C++ and library handoff

| ID | Atomic work package | Exit condition |
|---|---|---|
| I13-F01 | ROS environment lock | Distribution, compiler, plugin ABI and dependencies are pinned |
| I13-F02 | C++ interface descriptor | Exact graph/config/generation/joint fields match Python core |
| I13-F03 | Lifecycle parity | configure/activate/deactivate/cleanup/error/shutdown vectors agree |
| I13-F04 | Read validity parity | Missing/stale/faulted values are never zero-filled |
| I13-F05 | Write admission parity | Lease/generation/sequence/deadline/interface/limit checks agree |
| I13-F06 | Plugin skeleton | Thin SystemInterface contains no native CAN or safety bypass |
| I13-F07 | Build without hardware | Fake/replay/protocol builds run without physical adapter |
| I13-F08 | Packaging/API surface | Host exports, examples and compatibility policy are documented/tested |

## Track G — integration, quality and evidence

| ID | Atomic work package | Exit condition |
|---|---|---|
| I13-G01 | Schema mutation coverage | Unknown fields, count lies, hash drift and promotions deny |
| I13-G02 | Transactional generators | Failed builds preserve last valid artifacts |
| I13-G03 | Cross-registry parity | Catalog/applicability/CAD/plant/simulator generations agree |
| I13-G04 | Browser redaction | No archive URLs, local paths or reviewer evidence payloads |
| I13-G05 | Public documentation | Claims name evidence state and exact remaining gate |
| I13-G06 | Requirements/test registration | New cases are cataloged and traced |
| I13-G07 | Machine artifact binding | Applicability/campaign/plant/benchmark artifacts are hashed |
| I13-G08 | Complete regression | Full web, host, native and ESP32 gate passes |

## Discovery track — Iteration 14 human and physical inputs

| ID | Discovery item | Definition of Ready |
|---|---|---|
| I13-X01 | Source-authority reviewers | Seven roles and 29 divergence decisions have named independent humans |
| I13-X02 | Graph review cohorts | Ten cohorts have competence, schedule and evidence windows |
| I13-X03 | CAD review campaign | Each configuration has reviewer, priority, packet and license owner |
| I13-X04 | Vendor clarification | Ambiguous output members/protocol generations have bounded questions |
| I13-X05 | Plant source acquisition | Exact manuals/curves and extraction reviewers are assigned |
| I13-X06 | Rigid-body selection | Benchmark environment and decision owner are available |
| I13-X07 | ROS build target | Target distribution and deployment machine are owned |
| I13-X08 | U0 inventory authorization | Named personnel approve visual-only scope and abort rules |
| I13-X09 | Adapter/listen-only preparation | Exact fixture and independent TX-disable measurement are reviewed |
| I13-X10 | Safe-power/HIL preparation | Power cut, restraint, current/voltage limits and stop metrics are approved |

## Dependency order

1. A fixes evidence/ownership boundaries.
2. B and C execute in parallel conceptually, but locally in bounded slices.
3. D consumes exact model/source identities from B.
4. E consumes graph/CAD/plant contracts but may use only generic fixtures now.
5. F consumes the tested session/hardware cores and pinned environment.
6. G closes each delivered slice.
7. X supplies later human/physical inputs and grants no authority by planning.

## Iteration gates

- G13.1: protocol-source/applicability registry covers 9 packages, 32 files
  and 44 models with zero unsupported promotion.
- G13.2: CAD campaign covers all 53 configurations and preserves zero
  acceptance without human decisions.
- G13.3: plant fact ledger covers 44 models and does not fill missing fields.
- G13.4: rigid-body benchmark and trace contracts execute a generic fixture
  while canonical Dropbear remains denied.
- G13.5: ROS C++ handoff matches lifecycle/read/write/revocation semantics and
  has no native bypass.
- G13.6: browser/host/generated projections agree and remain path-safe.
- G13.7: physical authorization and real support remain explicit holds.
- G13.8: traceability and full machine gate pass.

## Definition of Done

- [x] Exact applicability corpus is generated, consumed and tested.
- [x] All 53 CAD configurations have campaign/reviewer-ready coverage.
- [x] Forty-four-model plant fact/missing-evidence ledger exists.
- [x] Rigid-body benchmark/trace contracts and generic fixture pass.
- [x] ROS C++ handoff compiles/tests in a pinned nonphysical environment.
- [x] Public/API/package documentation matches implemented evidence.
- [x] Physical and human authority boundaries remain unchanged.
- [x] Full machine report passes with new critical artifacts.
