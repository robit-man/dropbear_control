# MYACTUATOR ESP32, host and simulator completeness assessment

Assessment date: 2026-07-23  
Repository base revision: `d33490c9821584f965b61ab1a690ae70aaba0118`
plus preserved user firmware/web work and Iterations 2–13 offline work  
Latest full gate: see
[`generated/verification/offline_gate_report.json`](../generated/verification/offline_gate_report.json)
(Iteration 16 product-spec extraction/review-lifecycle/plant-set/V1+V2
runtime-adapter and WP-170 platform-trust/artifact checkpoint; the machine report
carries the current
run and source-manifest identities)  
Iteration 16 status: extraction complete offline, review campaign active;
human and physical
authorization remains held

## Executive conclusion

The repository is no longer merely a compileable skeleton. It now has a
substantial offline control foundation:

- a reproducible official-source catalog of 44 named motors and 53 exact STEP
  source variants;
- a pure, golden-vector-tested CAN V4.4 codec in Python and allocation-free
  C++;
- a deterministic V4.4 protocol-state emulator;
- a source-bound 44-model/9-package/32-PDF positive-capable protocol
  applicability lifecycle with an independent exact installed-unit consumer;
- a transactional live-index checker proving that the six current vendor
  series pages still expose exactly the tracked 44 CAD and nine document
  archives;
- a local all-53-configuration CAD review campaign with evidence packets,
  blocker lanes and 689 explicit unanswered semantic questions;
- a 44-model plant evidence ledger with 1,496 explicit parameter and 176
  operating-envelope requirements, source-fact lifecycle and no default fill;
- a Poppler-version-locked full-content extractor that binds all 15 official
  manual occurrences and 215 pages to exact product tables for 44/44 models,
  retaining 531 raw coordinate-bound candidates and linking all 406 mapped
  candidates to exact human handoff tasks without accepting a fact;
- a positive-capable, independently assigned human submission/event lifecycle
  with deterministic accept/reject/defer/revoke/supersede replay and
  Entity–Activity–Agent provenance materialization into active V2 source
  facts;
- a deterministic, positive-capable exact plant-set assembler that requires
  all 34 parameter facts, four envelope facts and an accepted exact protocol
  tuple, with upstream revocation and cross-field compatibility enforcement;
- a deterministic V1 runtime adapter that accounts for all 38 source
  semantics, requires independent human execution-profile review, emits
  hash-bound typed contracts and rejects unrepresentable noise/timing/torque/
  direction semantics;
- a separate event-scheduled V2 plant and reviewed adapter that accounts for
  the same 38 facts while exactly representing rational multirate sampling,
  arbitrary delay, counter-based noise/jitter, directional efficiency,
  one-shot peak torque, separate winding/case thermal limits, exclusive
  deadlines, command/sample ordering and complete snapshot replay;
- a fixed-step synthetic electromechanical actuator plant;
- bounded host-link, gateway, lease, safety, configuration, calibration,
  limit, observation and session cores;
- a shared Python/allocation-free-native post-authentication core with seven
  closed roles, ten actions, default-disabled physical/remote actuation,
  exact generation/lease/safety prerequisites and bounded digest-only audit;
- an exact source-bound PlatformIO/Arduino/ESP-IDF/sdkconfig/partition security
  profile intake with positive-capable independent selection and zero current
  roots, keys, private material or adapters;
- a shared 48-case Python/allocation-free-native artifact transaction core for
  exact verifier assertions, key purpose, target/envelope, rollback,
  stage/commit/abort, durable audit receipt and fail-disabled reboot semantics;
- source/graph/CAD/plant evidence registries that fail closed;
- an evidence-aware 44-model simulator runtime catalog; and
- a hash-bound 145-subject protocol/CAD/plant/Dropbear review queue with a
  validated 17-role human assignment contract;
- a 97-packet CAD/plant handoff that re-verifies cached sources and
  materializes all 2,361 still-null human tasks;
- a source-bound requirement/test/WP/gate/model/configuration dashboard that
  distinguishes 105 implemented-offline, 28 planned and seven physical-hold
  tests and exposes only 3/15 objective criteria met;
- a deterministic common simulation session for protocol state, synthetic
  plant, exact-contract sourced V2 plant and read-only replay;
- a positive-capable canonical trace interchange with dense event-chain,
  normalized command/state/disposition and generation semantics; and
- an exact MuJoCo 3.6.0 generic rigid-body benchmark with 10/10 passing
  headless, articulation, contact, excited closed-chain, replay and workflow
  cases; and
- an exact Jazzy 4.45.2 C++ `SystemInterface` package whose descriptor,
  lifecycle, read/write and revocation behavior matches the Python core and
  whose shipped backend fails closed.

It is still not a supported physical MYACTUATOR library and not a complete
Dropbear simulator. The missing work is now precise rather than hidden:

- 44/44 models have exact candidate-source coverage, but 0/44 exact
  model/firmware/protocol applicability decisions are accepted;
- 0/53 CAD configurations have reviewed housing/output separation, axis and
  redistributable runtime assets;
- 531 product-sheet values are exact review candidates, but 0 are accepted or
  runtime-admissible; 0 reviewed execution profiles/contracts exist and 0/44
  models have sourced runtime-loadable plant parameter sets or physical
  correlation;
- no concrete CAN adapter has passed intake;
- no credential/bootstrap, authenticated ESP32 transport, provisioned key
  store, actual signed-update verifier, encrypted persistent replay store,
  OTA installer or durable audit sink is integrated;
- no installed motor inventory or powered HIL result exists;
- Dropbear has no accepted canonical source/graph, no admitted actuator/ROS
  mappings and 0/12 motion-ready actuators; and
- no admitted whole-robot rigid-body backend exists.

Accordingly, one aggregate “percent complete” would be misleading. Catalog
acquisition is complete against the current vendor download pages, while
physical support and exact-model simulation fidelity remain at zero accepted
subjects.

## Evidence-state scorecard

| Capability | Current evidence state | Exact result | What it permits |
|---|---|---:|---|
| Vendor product inventory | `VERIFIED-OFFLINE` | 44 models | Exact catalog lookup and planning |
| Vendor download-index drift | `VERIFIED-LIVE-SNAPSHOT` | 6/6 pages; 53/53 normalized archive URLs exactly match tracked sources | Detect source drift and open change control; never grants support |
| Vendor STEP acquisition | `VERIFIED-SOURCE` | 53/53 source variants cached and hashed | Inspection and candidate conversion only |
| Runtime articulated CAD | `CAMPAIGN-READY / EVIDENCE-ABSENT` | 53/53 campaign rows; 41 packet-reviewable; 12 blocked; 0 accepted; 1 candidate export | Local semantic review planning only; no source STEP or candidate may load |
| Output-member/shaft definition | `EVIDENCE-ABSENT` | 0/53 reviewed housing/output/axis records | No physical joint geometry claim |
| CAN V4.4 wire layout | `VERIFIED-OFFLINE` | Python/C++ golden vectors pass | Revision-exact codec/SIL use |
| Per-model protocol applicability | `POSITIVE-LIFECYCLE-READY / EVIDENCE-ABSENT` | 44/44 candidate-source rows; 0 accepted installed-unit tuples | Controlled exact evidence intake only; no motor support claim |
| Protocol-state SIL | `IMPLEMENTED-OFFLINE` | 1 deterministic backend | Request/response, timing and protocol-state tests only |
| Synthetic actuator plant | `IMPLEMENTED-OFFLINE` | V1 and event-scheduled V2 synthetic fixtures; 0 real plants | Controller/SIL equation, timing, replay and interchange tests only |
| Synthetic twelve-axis plant bank | `IMPLEMENTED-OFFLINE / NO-ROBOT-FIDELITY` | 12 observed Dropbear-shaped actuator slots; 14 atomic batch/step/fault/snapshot tests; pinned trace `139b5626d38569be00b4034204c9fb9e463650a40ec73aa5a35358790c14ab10` | Multi-actuator control/scheduling fixture only; no canonical graph, rigid body, shared power bus, exact model or physical evidence |
| Product-spec extraction/review | `CANDIDATES-COMPLETE / LIFECYCLE-READY / REVIEW-ABSENT` | 15 manuals; 215 pages; 44 exact tables; 531 candidates; 406 mapped task links; 0 submissions/events/accepted/runtime facts | Exact human review navigation and controlled intake only; no source-fact or fidelity claim |
| Exact-model plant | `LEDGER/ASSEMBLY/V1+V2-ADAPTER-PATH-COMPLETE / EVIDENCE-ABSENT` | 44/44 matrices; 1,496 parameter + 176 envelope requirements; 106 model/manual relationships; 0 accepted facts; 0 exact sets; 0 reviewed V1/V2 profiles/contracts/loadable models | Exact acquisition/review and fail-closed V1/V2 executable-contract admission only; no real model fidelity |
| Recorded-state replay | `IMPLEMENTED-OFFLINE` | Read-only common-session adapter | Deterministic analysis; never commands |
| Browser toy simulator | `IMPLEMENTED-PROTOTYPE` | 1 visual-only backend | UI demonstration only |
| Whole-robot rigid body | `DENIED-NOT-LOADABLE` | 0 admitted backends | No Dropbear dynamics claim |
| Generic rigid-body benchmark | `VERIFIED-SYNTHETIC` | MuJoCo 3.6.0; 10/10 cases; two byte-equal 764-event traces | Engine/trace machinery only; no product or Dropbear fidelity |
| ESP32 native cores | `VERIFIED-COMPILE/OFFLINE` | Codec, host-link, gateway, safety supervisor and bounded fault-evidence/restart-latch cores compile/test; 314 supervisor plus 216 fault-context checks | Persistence/UTC/audit and real adapter integration remain open; not hardware control |
| ESP32 security profile | `OBSERVED-EXACT / UNSELECTED` | 1 candidate; 0 reviewed/selected; 0 roots/keys/adapters; Secure Boot/flash encryption/boot anti-rollback/NVS encryption disabled; legacy TLS enabled | Security remediation and provisioning planning only |
| Signed-artifact transactions | `IMPLEMENTED-OFFLINE / ADAPTER-ABSENT` | 48 Python/native vectors; exact stage/commit/abort/reboot semantics; 496-byte native engine | Verifier/persistence adapter integration only; no signature or update authenticity claim |
| Active ESP32 physical path | `PRESERVED-PROTOTYPE/HOLD` | No admitted adapter or verified receive path | No powered use |
| Host runtime core | `IMPLEMENTED-OFFLINE` | Bounded sessions/fakes/revocation tested | SIL and future adapter integration |
| ROS control boundary | `VERIFIED-OFFLINE / ADAPTER-ABSENT` | Jazzy C++ package builds/loads; 6 parity lines and 10/10 report cases pass | Plugin/API integration development only; configure correctly denies |
| Dropbear source authority | `ABSENT` | 0 active submissions | All graph/runtime mappings denied |
| Dropbear graph authority | `ABSENT` | 0 accepted graphs; 161 unresolved questions | 0 frames, 0 actuator mappings, 0 ROS mappings |
| Dropbear physical readiness | `HOLD` | 0/12 ready; 0 installed inventories | No physical handle or motion authority |
| Unified evidence review | `QUEUE-READY / HUMAN-UNASSIGNED` | 145 subjects across 7 workstreams; 17 roles; 0 assigned; 0 accepted | Local evidence triage and dependency planning only |
| CAD/plant evidence handoff | `DRAFTS-COMPLETE / HUMAN-UNASSIGNED` | 97 packets; 85 ready; 12 blocked; 2,361 tasks; 0 assigned; 0 accepted | Exact local review/extraction handoff only |
| Complete offline verification | `EVENT-PROPERTY CHECKPOINT-PASSED / FAULT-MONITOR EXPANSION PENDING` | The event-property source state passed 81/81 stages twice with identical 742-file source-manifest `f1886f10…c75`, tracked-diff `93106288…26f9`, 45 critical artifacts and 191 claims; the current entry additionally closes planned `TST-SAF-005` | The 596-check fault monitor plus 11-case native timeout/bus-off runtime pass focused verification; their expanded checkpoint, physical discovery, bench/HIL, real plant correlation and release authorization remain open |
| Program objective coverage | `STRUCTURALLY-COMPLETE / OBJECTIVE-INCOMPLETE` | 77/77 traced; 105 implemented-offline, 28 planned, 7 physical-hold tests; 3/15 objective criteria met | Gap observation only; no requirement completion, gate pass or release authority |
| Iteration 12 focused verification | `INTEGRATED-IN-GATE` | 10 catalog + 14 session + 12 ROS-core + browser regressions | Offline simulator/control foundation |
| Iteration 13 applicability slice | `VERIFIED-FOCUSED` | 10 applicability + 10 updated simulator tests; 126 catalog tests; 25 critical artifacts prepared | Source navigation and fail-closed exact admission only |
| Iteration 13 CAD campaign slice | `VERIFIED-FOCUSED` | 10 campaign tests; 53 configurations; 689 unanswered questions; 127 catalog tests; 26 critical artifacts prepared | Local review navigation only |
| Iteration 13 plant ledger slice | `VERIFIED-FOCUSED` | 10 ledger tests; 44 matrices; 1,672 explicit null/blocking requirements | Source extraction and measurement work queue only |
| Iteration 13 rigid/trace slice | `VERIFIED-FOCUSED` | 6 trace + 6 benchmark tests; 10/10 benchmark cases; 753 typed state samples | Generic offline mechanics and interchange only |
| Iteration 13 ROS C++ slice | `VERIFIED-FOCUSED` | Exact 9-package/4-ABI/3-header lock; 2/2 CTest; 6/6 repository tests; 10/10 report cases | No live authority service, concrete adapter, canonical mapping or physical I/O |
| Iteration 14 source-index slice | `VERIFIED-LIVE/OFFLINE` | 6 pages; 53 exact live/tracked archive URLs; transactional drift preservation | Change detection only; no automatic source replacement |
| Iteration 14 applicability slice | `VERIFIED-FOCUSED` | Synthetic exact acceptance plus installed-unit mismatch, listen-only, reviewer-alias and source-drift denial | Lifecycle machinery only; 0 real accepted tuples |
| Iteration 14 review-queue slice | `VERIFIED-FOCUSED` | 145 subjects; 689 CAD questions; 1,672 plant requirements; 17 roles; all physical authority false | Human handoff and work ordering only |
| Iteration 14 intake-handoff slice | `VERIFIED-FOCUSED` | 53 CAD + 44 plant drafts; 85 ready; 12 source/partition blocked; cached source hashes reverified | Generated scaffolding only; responses and evidence remain null |
| Iteration 14 coverage-dashboard slice | `VERIFIED-FOCUSED` | 77 requirements; 134 tests; 20 WPs; 8 gates; 44 models; 53 configurations; 15 exact objective criteria | Structural coverage and blocker visibility only; release/support/motion remain false |
| WP-170 platform-trust slice | `VERIFIED-FOCUSED` | 10 intake tests; one exact unselected target profile; 48 Python/native artifact vectors; allocation/sanitizer checks | Architecture/transaction semantics only; zero provisioned roots/keys/adapters and no physical authority |
| Iteration 16 product-spec candidate slice | `VERIFIED-FOCUSED / HUMAN-UNREVIEWED` | 11 extraction tests; 15 manuals; 215 pages; 44 exact table bindings; 531 candidates; all 406 mapped candidates linked to handoff tasks | Navigation and deterministic review input only; all candidate/fact/runtime admission remains zero |
| Iteration 16 plant decision slice | `VERIFIED-FOCUSED / HUMAN-UNASSIGNED` | 14 lifecycle tests; immutable submission/event schemas; positive accept, reject/defer/revoke/supersede replay; V2 provenance materialization; zero tracked submissions/events/facts | Lifecycle machinery only; no human decision, plant fidelity, support or motion authority |
| Iteration 16 plant-set assembly slice | `VERIFIED-FOCUSED / REAL-EVIDENCE-ABSENT` | 12 assembly tests; all-38-fact completeness, exact tuple, uncertainty, envelope, cross-field, split/coalesce, revocation and transaction paths; zero tracked sets | Materialization machinery only; no real parameter fidelity, support or motion authority |
| Iteration 16 plant runtime-adapter V1 slice | `VERIFIED-FOCUSED / REAL-EVIDENCE-ABSENT` | 10 adapter tests; all 38 source semantics classified; reviewed profile/contract, aggregate registry V4 and typed sourced-engine paths; zero tracked profiles/contracts/loadable models | Exact representable continuous-only V1 mechanics only; real review and correlation remain open |
| Iteration 16 plant runtime-adapter V2 slice | `VERIFIED-FOCUSED / REAL-EVIDENCE-ABSENT` | 15 core + 8 adapter tests plus positive registry/session/trace joins; all 38 source semantics represented; rational scheduling, noise/jitter, directional/peak/thermal/deadline/snapshot behavior and two pinned hashes; zero tracked profiles/contracts/loadable models | Full-semantic source-only V2 SIL machinery; no accepted model facts, physical correlation, support, I/O or motion |
| Iteration 16 twelve-axis composition slice | `VERIFIED-FOCUSED / SYNTHETIC-ONLY` | 14 tests; 12 exact actuator-slot rows; all-axis atomic batches/loads, aggregate current admission, forced rollback, thermal fail-stop, per-axis seeds, snapshot continuation and pinned trace | No canonical Dropbear graph, rigid body, shared power bus, exact MYACTUATOR model, physical validation/I/O or motion authority |

## Exact catalog and CAD state

The canonical source inventory is
[`assets/myactuator/catalog.tsv`](../assets/myactuator/catalog.tsv). The current
download coverage is:

| Series page | Named models | STEP variants |
|---|---:|---:|
| RMD-X | 14 | 19 |
| RH | 5 | 9 |
| RMD-L | 10 | 10 |
| CEM | 2 | 2 |
| RMD-H | 3 | 3 |
| FL/FLO | 10 | 10 |
| **Total** | **44** | **53** |

All 53 files are real vendor STEP sources with pinned archive/source identity.
That does not make them simulation assets. Twenty-six preserve assembly
relationships and 27 are flattened. The vendor packages do not provide a
uniform separately named output-shaft file.

The CAD evidence pipeline now correctly separates:

1. source STEP acquired;
2. bounded lexical/topology inspection;
3. candidate housing/output segmentation;
4. independent semantic review;
5. accepted exact configuration;
6. local runtime loadability;
7. redistributable browser asset; and
8. Dropbear graph binding.

Today only the first two are complete for the catalog. The local campaign now
covers all 53 configurations: 26 assembly rows and 15 disconnected-solid rows
have packets suitable for immediate human semantic investigation; two
single-solid, five high-component-count and five shell-only rows require a
better source or specialized partition/healing work first. One X12 candidate
export exists, but it is not an accepted output-member decision and grants no
runtime asset. Every source STEP remains
`source_step_runtime_asset=false`.

A complete exact motor asset still needs a reviewed housing, rotating output
member, axis, origin, zero pose, positive direction, visual mesh, collision
mesh, trusted mass properties and redistribution decision. Flattened sources
may require manual segmentation or a better native assembly from MYACTUATOR.

## Protocol, firmware and physical transport state

The V4.4 codec implements the evidenced classic-CAN layout: standard 11-bit
IDs, 8-byte frames, request ID `0x140 + motor_id`, response ID
`0x240 + motor_id`, and the supported revision-exact commands. Python/C++
golden parity, malformed-frame denial and the deterministic protocol-state
emulator are strong offline evidence.

They do not prove that any installed motor model and firmware implements that
revision. The new source-bound applicability registry losslessly partitions
all 32 pinned PDFs across nine packages, preserves 23 unique file hashes,
retains RMD-X V2/V3/V4 ambiguity, separates FL from FLO, and prevents encoder
interface documents from becoming motor-motion protocols. All 44 models have
candidate-source rows, but every row remains unsupported.

Applicability must be an exact tuple:

```text
installed unit ID + series + model + hardware revision + firmware revision
+ protocol edition + transport + control mode
+ inventory/source-review/capture hashes
+ independent submitter + source reviewer + decision reviewer
```

The controlled positive lifecycle can admit only an exact accepted tuple.
Listen-only evidence cannot establish command or control-mode applicability,
and an accepted applicability decision still sets motor support, physical
motion authority and simulation fidelity to false. No real decision is
currently accepted.

The production-oriented ESP32 cores now cover bounded framing, configuration
identity, lease/deadline safety, single-writer gateway behavior, native codec
composition and compile-only integration seams. The current user
`MotorController`, encoder, serial bridge and web edits remain preserved and
separate. They have not silently become the production route.

No physical adapter is available through the admitted factory. The adapter
intake is deliberately no-I/O, and the canonical status has no selected
controller, transceiver, oscillator, pinout, termination, TX-disable proof or
installed drive tuple. A successful ESP32 compile therefore remains compile
evidence only.

## Simulator state

The generated simulator catalog joins the exact 44-model product registry,
protocol-applicability lifecycle registry, 53 CAD configurations, plant backend
registry and Dropbear lifecycle projection. Host and browser copies are
byte-identical and path-redacted. Protocol applicability is now derived from
that source-bound registry and remains false for 44/44 models.

Five evidence classes remain distinct:

| Backend | Executable | Commands | What it models | Explicit limitation |
|---|---:|---:|---|---|
| Recorded replay | yes | no | Recorded state | No dynamics or commands |
| V4.4 protocol emulator | yes | yes | Protocol state/timing | No actuator dynamics or tuple applicability |
| Browser toy | yes | yes | Visual demonstration | No deterministic or physical plant fidelity |
| Synthetic electromechanical plant | yes | yes | Generic fixed-step equations | No real product parameters/correlation |
| Dropbear rigid body descriptor | no | no admitted use case | Nothing executable | Canonical graph/CAD/plant absent |

The common host simulation session now provides:

- exact catalog/model/configuration/backend/use-case admission;
- unconfigured/inactive/active/faulted/finalized lifecycle;
- integer virtual ticks that do not advance on read or wall clock;
- typed SI command envelopes with sequence, reset generation and deadline;
- deterministic reset and initial-state digest;
- validity-preserving state envelopes;
- engine/catalog/configuration-bound snapshots;
- transient and latched scheduled faults;
- dense rolling canonical trace hashes; and
- live catalog/source/graph revocation before further use.

This is the correct execution spine for SIL. It deliberately reports zero
exact-model fidelity and zero physical validation for all current models.

That spine now exports
[`simulation-trace-interchange/1`](../schemas/simulation-trace-interchange.schema.json):
canonical commands, states, dispositions and original chained events with
reset/backend/subject/generation identity. A generic trace cannot promote
itself; the future canonical-scene transition requires an exact backend plus
all admitted generations.

The separate
[`MYACTUATOR_RIGID_BODY_BENCHMARK.md`](MYACTUATOR_RIGID_BODY_BENCHMARK.md)
records one exact MuJoCo 3.6.0 environment and a generic nine-DOF fixture.
Two 2,500-step runs are byte-identical and all 10 cases pass, including an
actively excited equality-constrained loop and settling contact. Gazebo and
Drake are recorded but unexecuted candidates, so no production engine is
selected. The benchmark consumes no accepted Dropbear graph, CAD or plant and
the catalog's Dropbear rigid-body descriptor remains non-loadable.

The plant evidence layer now makes the zero explicit rather than leaving it as
an empty directory. All 44 exact models have the same 34-field runtime plant
contract and four required operating-envelope ranges, joined to 15 pinned
product-manual occurrences through 106 candidate relationships. The current
ledger has 0 accepted source facts and therefore 1,672 null/blocking
model-field entries. It also defines independent review, exact
hash/page/table provenance, explicit SI conversion and non-substitutable
uncertainty classes. See
[`MYACTUATOR_PLANT_EVIDENCE_LEDGER.md`](MYACTUATOR_PLANT_EVIDENCE_LEDGER.md).

The upstream navigation gap is now closed without promoting evidence. A
locked local extractor digests all 215 pages of the 15 official occurrences
and selects an exact page/table/model header for every catalog model. It
preserves bounding boxes and raw labels/units/values for 531 candidates:
89 direct label/unit suggestions, 317 suggestions requiring semantic review,
and 125 values intentionally left unmapped. All 406 mapped candidates are
referenced by their exact plant handoff tasks. Every candidate remains
unreviewed, accepted count is zero, and none is runtime-admissible. See
[`PLANT_SPEC_CANDIDATE_EXTRACTION.md`](PLANT_SPEC_CANDIDATE_EXTRACTION.md).

The executable boundary now has two non-substitutable adapter generations.
V1 deliberately accepts only its conservative fixed-step subset. V2 accounts
for all 38 source semantics through the event-scheduled engine, and aggregate
registry V4 rejects simultaneous V1/V2 activation for one plant. Synthetic
positive fixtures prove both paths; the tracked registries contain zero
profiles and zero contracts. See
[`PLANT_RUNTIME_ADAPTER_V2.md`](PLANT_RUNTIME_ADAPTER_V2.md).

## Host, ROS and Dropbear reconciliation

The host now has more than loopback framing: bounded gateway sessions,
transport fakes, V4.4 codec/emulator, calibration and limit admission, joint
observation, CAD/plant registries, graph-gated hardware API and live authority
revocation are all offline-tested.

The ROS-independent Python core now has a C++17 counterpart and thin compiled
`ros2_control::SystemInterface` in an exact Ubuntu 24.04 / Jazzy 4.45.2
environment. Descriptor, lifecycle, generation, lease, validity and
read/write/revocation vectors match byte-for-byte; pluginlib loading and
framework-managed handle export pass. The plugin deliberately has no native
transport, live authority provider or concrete session adapter, so configure
fails closed. See
[`MYACTUATOR_ROS2_CONTROL_HANDOFF.md`](MYACTUATOR_ROS2_CONTROL_HANDOFF.md).

The audited Dropbear low-level prototype remains valuable migration evidence:
12 candidate CAN addresses, six semantic actuators per leg, five external
analog sensors per leg, rough q-axis-current and stop command hypotheses, and
operator workflows. Its critical races, incorrect stop addressing, missing
receive path and unsafe remote/UI coupling are documented in
[`DROPBEAR_CONTROL_STACK_NOTES.md`](DROPBEAR_CONTROL_STACK_NOTES.md).

The broader Dropbear CAD/Gazebo/Isaac repository is visually and mechanically
substantial but lacks canonical authority. Current lifecycle projections
therefore contain:

- 0 active source submissions;
- 0 accepted canonical graphs;
- 161 unresolved graph questions;
- 0 canonical frames;
- 0 actuator mappings;
- 0 ROS mappings;
- 0 accepted Dropbear CAD bindings;
- 0 physical plant bindings; and
- 0/12 motion-ready actuators.

This explains the present low-to-high-level mismatch: rich artifacts exist,
but no reviewed machine-readable graph binds semantic joint, actuator,
transport route, sign, limit, calibration, output member, state source,
command mode and ROS interface.

## Remaining-proof ledger

Completion is driven by evidence artifacts and gates, not subjective
percentages.

| Proof ID | Missing claim | Required proving artifact | Gate that may consume it |
|---|---|---|---|
| PRF-SRC-001 | Canonical Dropbear source | Independent source-authority submission and accepted lifecycle decision | Source activation gate |
| PRF-GRF-001 | Canonical robot graph | Resolved 161-question graph submission, independent review and accepted event | Graph activation gate |
| PRF-MAP-001 | Joint/actuator/ROS mapping | Exact generated mappings bound to active source/graph generations | Simulator/ROS admission |
| PRF-CAD-001 | Exact motor articulation | Per-configuration housing/output/axis review decision | CAD acceptance gate |
| PRF-CAD-002 | Runtime motor assets | Accepted visual/collision outputs, hashes, units/transforms and license | Local/browser asset admission |
| PRF-CAD-003 | Dropbear geometry | Canonical graph joints bound to accepted exact assets | Whole-robot CAD gate |
| PRF-PRT-001 | Motor protocol support | Independent decision binding exact installed unit/model/hardware/firmware/protocol/transport/mode to inventory, source-review and observed capture hashes | Codec/device admission |
| PRF-PLT-001 | Real model plant | Sourced electrical/mechanical/thermal parameter set with uncertainty | Exact-model plant admission |
| PRF-PLT-002 | Physical plant validity | Bench/holdout correlation report with fixed metrics and fixture identity | Physical-correlation gate |
| PRF-RBD-001 | Whole-robot dynamics | Pinned deterministic engine, canonical inertias/contacts and cross-backend vectors | Rigid-body admission |
| PRF-ADP-001 | CAN adapter availability | Exact controller/transceiver/clock/pins/termination/TX-disable manifest | Adapter factory admission |
| PRF-INV-001 | Installed motor identity | Unpowered U0 visual inventory reviewed by named humans | Installed-tuple gate |
| PRF-CAP-001 | Native observed behavior | Listen-only then separately authorized request/response captures | Protocol applicability/HIL |
| PRF-SAF-001 | Safe physical stop | Independent power cut, verified motor-off behavior and fault/deadman results | Physical G0/G2 |
| PRF-HIL-001 | Physical command support | Current-limited fixture, exact firmware/voltage/load, success/failure traces | Model support gate |
| PRF-ROS-001 | ROS execution | Tested semantic core, pinned ROS ABI and C++ plugin parity | ROS integration gate |
| PRF-REL-001 | Release evidence | Clean reproducible full gate, artifact hashes, signed/owned decisions | Release gate |

## Support definition

An exact motor tuple may be called supported only when it has:

- an official-source manifest and accepted applicability decision;
- encode/decode vectors for every claimed command;
- a concrete transport with correlation, deadlines and bus-failure behavior;
- enable, disable, stop, clear-fault, command and state behavior verified on
  the exact hardware/firmware;
- motor/output units, signs, limits and calibration proven;
- protocol SIL and physical HIL evidence;
- accepted housing/output CAD with reviewed axis; and
- a sourced plant and stated correlation level if model simulation is claimed.

“Family supported,” “STEP downloaded,” “codec tests pass,” “simulator runs”
and “ESP32 compiles” are all narrower statements and must never substitute
for that matrix.
