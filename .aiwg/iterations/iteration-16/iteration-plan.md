# Iteration 16 — model-complete actuator evidence and twin campaign

Status: active long-haul WP-140/WP-150/WP-160 execution. Deterministic
product-spec extraction, the positive-capable independent candidate
submission/event/materialization lifecycle and deterministic exact plant-set
assembly plus the reviewed V1 and full-semantic event-scheduled V2
runtime-adapter/contract paths are complete offline. Human semantic review,
accepted output shafts, accepted plant facts, reviewed real execution
profiles, exact-model runtime plants,
canonical Dropbear integration and all physical correlation remain open or
held.

## Objective

Move from “the official files exist” to a model-complete, reviewable and
testable actuator-twin foundation for all 44 catalog motors and all 53 STEP
configurations. Preserve the distinction between:

- raw official sources;
- machine-produced navigation candidates;
- independent human decisions;
- accepted geometry and source facts;
- complete exact-model assets/plants;
- simulator admission;
- protocol SIL;
- physically correlated HIL; and
- robot release.

This iteration does not authorize hardware access, firmware upload, CAN/serial
device access, drive power, eFuse operations or motion.

## Immutable rules

1. A downloaded STEP or PDF is acquisition evidence only.
2. A machine-selected CAD member or PDF value has no review authority.
3. No family, nearest-model, latest-revision or default-value fallback exists.
4. Every runtime fact binds an exact model, revision, source hash and review.
5. Every geometry configuration retains its own decision, even when source
   bytes duplicate another configuration.
6. Housing, output member, axis, origin, direction and zero pose are separate
   questions.
7. Electrical line/phase, RMS/q-axis, motor/module/output-shaft, rated/peak,
   continuous/transient and no-load/maximum semantics remain distinct.
8. Unknown values remain null and blocking.
9. Official stated, derived, fitted and bench-measured values remain separate
   evidence classes.
10. Exact-model simulation readiness never implies protocol or physical
    support.
11. Generic rigid-body and synthetic plant fixtures never become product or
    Dropbear fidelity.
12. All physical tasks remain behind explicit authorization and the G0–G3
    safety gates.
13. A complete source set is never executable until a reviewed profile and
    versioned adapter account for every source semantic without approximation.

## Entry state

| Area | Exact entry state |
|---|---|
| Product catalog | 44 models |
| Official STEP | 53 configurations acquired and hashed |
| STEP kernel import | 53/53 import; 48 closed-solid, 5 shell-only |
| Accepted housing/output/axis records | 0/53 |
| Runtime exact CAD assets | 0/53 |
| Official manual occurrences | 15 |
| Manual pages digested | 215 |
| Exact model table bindings | 44/44 |
| Product-spec candidates | 531 total; 89 direct, 317 semantic review, 125 unmapped |
| Candidate-to-plant-task references | 406 |
| Accepted candidate decisions | 0 |
| Accepted plant source facts | 0 |
| Complete exact-model plant sets | 0/44 |
| Reviewed plant execution profiles | 0 |
| Generated exact runtime contracts | 0 |
| Runtime-loadable exact-model plants | 0/44 |
| Exact-model simulator-ready | 0/44 |
| Canonical Dropbear source/graph | 0 active |
| Dropbear motion-ready actuators | 0/12 |
| Reviewer roles assigned | 0/17 |
| Physical evidence tests complete | 0/7 |

## Gate map

| Gate | Scope | Exit evidence | Current |
|---|---|---|---|
| S16.0 | Freeze source and tool identity | all PDF/STEP/catalog/plan/tool hashes and no-network rules | COMPLETE-OFFLINE |
| S16.1 | Extract full PDF content | 15 manuals, 215 page digests, explicit no-text status | COMPLETE-OFFLINE |
| S16.2 | Bind exact model tables | 44 unique model/page/header/table selections; no fallback | COMPLETE-OFFLINE |
| S16.3 | Produce non-authoritative candidates | 531 parsed coordinate-bound candidates with ambiguity preserved | COMPLETE-OFFLINE |
| S16.4 | Join human handoff | all 406 mapped candidates referenced by exact target tasks | COMPLETE-OFFLINE |
| S16.5 | Assign and qualify human reviewers | named, competent, independent source/CAD/plant roles | OPEN-HUMAN |
| S16.6 | Decide product-spec candidates | lifecycle/schema/replay COMPLETE-OFFLINE; real accept/reject/defer/remap records | OPEN-HUMAN |
| S16.7 | Materialize and select source facts | deterministic V2 fact lifecycle and all-38-fact/exact-tuple set assembler COMPLETE-OFFLINE; real reviewed facts and sets | OPEN-HUMAN |
| S16.7A | Adapt reviewed sets to executable plants | V1 conservative and V2 full-semantic profile/contract adapters, aggregate registry V4 single-active-version policy, typed session/trace/revocation tests COMPLETE-OFFLINE; real reviewed profiles/contracts | OPEN-HUMAN |
| S16.8 | Decide all STEP configurations | 53 housing/output/axis/origin/direction/zero/license records | OPEN-HUMAN |
| S16.9 | Generate exact runtime assets | deterministic accepted visual/collision/articulated artifacts | BLOCKED-S16.8 |
| S16.10 | Admit exact-model actuator twins | complete plant + CAD + applicability dependencies per model | BLOCKED-S16.7/9 |
| S16.11 | Integrate canonical Dropbear twin | accepted graph, mappings, transmissions, inertias, contacts, sensors | BLOCKED-WP120/S16.10 |
| S16.12 | Run controller/estimator SIL | unchanged typed APIs, scenario/error/fault budgets, replay parity | BLOCKED-S16.11 |
| S16.13 | Correlate on authorized hardware | one motor then one leg, holdout metrics and uncertainty updates | PHYSICAL-HOLD |
| S16.14 | Release exact configurations | signed evidence, operations, rollback and G4–G7 decisions | BLOCKED-ALL |

## Workstream A — candidate extraction and source control

### A0 — completed foundation

- [x] A0.01 Inventory all 15 local official PDF occurrences.
- [x] A0.02 Hash every PDF and bind its document occurrence.
- [x] A0.03 Lock Poppler `pdftotext` version 24.02.0 and arguments.
- [x] A0.04 Process all 215 pages, not only selected tables.
- [x] A0.05 Record one explicit `no_extractable_text` page.
- [x] A0.06 Canonicalize and hash per-page extracted text.
- [x] A0.07 Select nine product sheets covering all catalog models.
- [x] A0.08 Select one exact page/model header for each of 44 models.
- [x] A0.09 Reject family and implicit-latest fallback.
- [x] A0.10 Preserve label/unit/value bounding boxes.
- [x] A0.11 Parse scalar, range, qualified, alternative and annotated forms.
- [x] A0.12 Preserve source label/unit/value verbatim in the candidate.
- [x] A0.13 Suggest exact SI conversion only when structurally defined.
- [x] A0.14 Attach semantic blockers where the current plant field is not
  equivalent.
- [x] A0.15 Keep all 531 candidates unreviewed and non-runtime.
- [x] A0.16 Bind all 406 mapped candidates to exact evidence-intake tasks.
- [x] A0.17 Prove byte-stable local generation.
- [x] A0.18 Add candidate/page/target/authority/tool/source mutation tests.

### A1 — source change control

- [ ] A1.01 Assign a source custodian and independent source reviewer.
- [ ] A1.02 Review the exact nine product-sheet applicability choices.
- [ ] A1.03 Confirm each package revision and publication scope.
- [ ] A1.04 Record printed-page labels where they differ from PDF indexes.
- [ ] A1.05 Record tables spanning multiple pages or footnotes.
- [ ] A1.06 Record language/translation ambiguities.
- [ ] A1.07 Define vendor-revision supersession versus coexistence policy.
- [ ] A1.08 Diff any future PDF by file hash, page count and page digest.
- [ ] A1.09 Invalidate affected candidate decisions on source drift.
- [ ] A1.10 Never overwrite the accepted prior evidence lineage.

## Workstream B — human product-spec review

### B0 — campaign setup

- [ ] B0.01 Assign source extractor, manual reviewer, plant semantic reviewer
  and approval roles.
- [x] B0.02 Enforce extractor/reviewer identity separation.
- [ ] B0.03 Record reviewer competence by electrical, mechanical, thermal and
  controls domain.
- [x] B0.04 Freeze the candidate registry artifact ID and source hashes for
  the campaign batch.
- [ ] B0.05 Partition work by model and property domain without allowing a
  family-level decision.
- [x] B0.06 Define accepted, rejected, deferred and remapped dispositions.
- [x] B0.07 Define conflict, supersession and revocation records.
- [ ] B0.08 Pilot one model from each series before bulk review.

### B1 — per-candidate checklist

For each candidate:

- [ ] B1.01 Confirm document occurrence and SHA-256.
- [ ] B1.02 Confirm one-based page and visible model header.
- [ ] B1.03 Confirm label, unit and value against the rendered page.
- [ ] B1.04 Inspect table footnotes, superscripts and adjacent qualifiers.
- [ ] B1.05 Confirm exact model/revision applicability.
- [ ] B1.06 Decide scalar/range/alternative/qualification interpretation.
- [ ] B1.07 Resolve line-to-line, line-to-neutral and phase basis.
- [ ] B1.08 Resolve peak, RMS, instantaneous and q-axis current basis.
- [ ] B1.09 Resolve motor, gearbox input, module and output-shaft basis.
- [ ] B1.10 Resolve rated, continuous, peak and maximum duration.
- [ ] B1.11 Resolve no-load, rated-load and declared limit semantics.
- [ ] B1.12 Resolve temperature/voltage operating envelope versus nominal
  point.
- [ ] B1.13 Confirm conversion expression and normalized unit.
- [ ] B1.14 Assign stated tolerance or conservative documented uncertainty.
- [ ] B1.15 Record blocker resolution and decision rationale.
- [ ] B1.16 Reject or defer rather than guess.
- [ ] B1.17 Obtain independent approval.
- [ ] B1.18 Emit immutable decision event.

### B2 — priority review order

1. exact ratio and direction convention;
2. phase resistance and phase inductance basis;
3. back-EMF and torque constant basis;
4. rotor/module/output inertia basis;
5. rated and peak torque with duty duration;
6. current limits and RMS/q-axis relationship;
7. output speed limits versus no-load/rated speed;
8. voltage and temperature envelopes;
9. efficiency and operating point;
10. mass, protection and dimensions for disposition or future schemas; and
11. every unmapped value, with an explicit retain/reject/schema-change result.

## Workstream C — source facts and exact-model parameter sets

### C0 — fact materialization

- [ ] C0.01 Create one immutable source-fact record per accepted meaning.
- [ ] C0.02 Bind exact catalog key, revision, occurrence, hash, page and table.
- [ ] C0.03 Preserve original label/unit/value.
- [ ] C0.04 Record normalized SI value and conversion.
- [ ] C0.05 Record uncertainty class and rationale.
- [ ] C0.06 Record extractor, independent reviewer and UTC decision.
- [ ] C0.07 Keep derived values distinguishable from directly stated values.
- [ ] C0.08 Keep fitted and bench-measured records outside official facts.
- [ ] C0.09 Add revoke/supersede lineage without deleting prior facts.
- [ ] C0.10 Rebuild the plant evidence ledger transactionally.

### C1 — set assembly

For each of 44 models:

Offline assembly machinery is complete: a 12-test synthetic reviewed fixture
proves all-38-field closure, exact accepted-tuple binding, SI uncertainty,
operating-condition and cross-field checks, tuple split/coalesce, revocation
and transaction behavior. The following per-model evidence selections remain
open:

- [ ] C1.01 Select all required electrical facts.
- [ ] C1.02 Select all required mechanical facts.
- [ ] C1.03 Select all required transmission facts.
- [ ] C1.04 Select saturation/limit facts.
- [ ] C1.05 Select thermal facts or keep the model blocked.
- [ ] C1.06 Select sensor/quantization facts or keep the model blocked.
- [ ] C1.07 Select latency/update facts or keep the model blocked.
- [ ] C1.08 Select all four operating envelopes.
- [ ] C1.09 Check source compatibility across revisions/configurations.
- [ ] C1.10 Check sign, unit and shaft-basis consistency.
- [ ] C1.11 Check physical positivity and boundedness constraints.
- [ ] C1.12 Record missing facts without substitution.
- [ ] C1.13 Independently approve the complete set.
- [ ] C1.14 Emit a generation-bound parameter-set identity.

### C2 — cross-field validation

- [ ] C2.01 Compare torque constant and back-EMF consistency only under the
  reviewed convention.
- [ ] C2.02 Compare rated torque/current/constant without treating mismatch as
  permission to fit silently.
- [ ] C2.03 Check resistance/inductance electrical time constants.
- [ ] C2.04 Check ratio and reflected-inertia transformations.
- [ ] C2.05 Check continuous/peak torque and duty duration ordering.
- [ ] C2.06 Check output speed against rated/no-load observations.
- [ ] C2.07 Check voltage and temperature envelopes.
- [ ] C2.08 Record discrepancies as review issues, not automated corrections.
- [ ] C2.09 Revoke readiness if any selected fact is revoked or superseded.

## Workstream D — exact STEP output-shaft campaign

### D0 — 53-configuration review

For every configuration:

- [ ] D0.01 Confirm exact source ZIP and STEP hash.
- [ ] D0.02 Confirm native unit and imported scale.
- [ ] D0.03 Confirm assembly versus flattened topology.
- [ ] D0.04 Identify stationary housing members.
- [ ] D0.05 Identify moving output members.
- [ ] D0.06 Identify shaft/flange interface.
- [ ] D0.07 Define axis origin in the accepted frame.
- [ ] D0.08 Define axis unit vector and positive direction.
- [ ] D0.09 Define mechanical zero pose.
- [ ] D0.10 Verify output-only rotation.
- [ ] D0.11 Verify housing immobility.
- [ ] D0.12 Verify member preservation and no geometry loss.
- [ ] D0.13 Resolve duplicate-byte configurations independently.
- [ ] D0.14 Heal, re-source or explicitly reject five shell-only sources.
- [ ] D0.15 Record collision simplification and visual fidelity disposition.
- [ ] D0.16 Record redistribution/license decision.
- [ ] D0.17 Obtain independent semantic approval.
- [ ] D0.18 Emit accepted-local, accepted-browser or rejected state.

### D1 — deterministic asset generation

- [ ] D1.01 Export housing STEP.
- [ ] D1.02 Export output STEP.
- [ ] D1.03 Export metre-scaled visual GLB.
- [ ] D1.04 Export collision mesh with declared tolerance.
- [ ] D1.05 Hash source, conversion record and every output.
- [ ] D1.06 Test scale, frame, axis and origin.
- [ ] D1.07 Test negative/zero/positive articulation.
- [ ] D1.08 Test housing immobility and output connectivity.
- [ ] D1.09 Test browser/local redistribution gating.
- [ ] D1.10 Admit only accepted artifacts into runtime registries.

## Workstream E — exact actuator twin

For each model/configuration combination claimed:

- [ ] E0.01 Bind accepted protocol applicability scope.
- [ ] E0.02 Bind complete exact-model plant set.
- [ ] E0.02A Prepare and independently accept one exact execution profile.
- [ ] E0.02B Generate and revalidate the versioned runtime contract.
- [ ] E0.03 Bind accepted housing/output/axis record.
- [ ] E0.04 Bind runtime visual and collision artifacts.
- [ ] E0.05 Bind configuration/source generations.
- [ ] E0.06 Instantiate the deterministic electromechanical plant.
- [ ] E0.07 Instantiate output joint/transmission semantics.
- [ ] E0.08 Apply voltage/temperature/torque/speed envelopes.
- [ ] E0.09 Run analytic electrical and mechanical cases.
- [ ] E0.10 Run friction, backlash, saturation and thermal boundaries.
- [ ] E0.11 Run sensor quantization and latency cases.
- [ ] E0.12 Run repeatability and canonical trace checks.
- [ ] E0.13 Run source/config/graph revocation during a session.
- [ ] E0.14 Deny readiness if any dependency is incomplete.
- [ ] E0.15 Label evidence as datasheet-derived until physically correlated.

Completed reusable E-foundation:

- [x] EF.01 Define the closed V1 execution-profile schema.
- [x] EF.02 Require distinct human simulation preparer and controls/safety reviewer.
- [x] EF.03 Account for all 34 parameters and four operating envelopes.
- [x] EF.04 Reject nonzero noise, command delay/jitter and unequal sample rates.
- [x] EF.05 Reject nonintegral feedback delay and unsupported torque/direction semantics.
- [x] EF.06 Preserve source facts while deriving only explicit scenario/solver inputs.
- [x] EF.07 Emit deterministic hash-bound contracts and a 44-model registry.
- [x] EF.08 Integrate V1 contracts with the aggregate plant registry and
  simulator selection.
- [x] EF.09 Execute contracts only through the typed sourced-plant engine.
- [x] EF.10 Enforce source/profile/implementation/reviewer/revocation identity.
- [x] EF.11 Keep support, physical validation, physical I/O and motion false.
- [x] EF.12 Implement exact-rational V2 command/sample event scheduling.
- [x] EF.13 Implement counter-based bounded command/feedback jitter.
- [x] EF.14 Implement counter-based position/velocity/current sensor noise.
- [x] EF.15 Implement multirate capture interpolation and arbitrary latency.
- [x] EF.16 Implement distinct forward/reverse efficiency selection.
- [x] EF.17 Implement continuous and one-shot-per-reset peak regimes.
- [x] EF.18 Implement separate winding/case derate and shutdown limits.
- [x] EF.19 Implement newest-sequence watermarks and exclusive deadlines.
- [x] EF.20 Snapshot every hidden queue/time/seed/peak/sample state and verify
  exact replay plus tamper denial.
- [x] EF.21 Bind all 38 source semantics and reviewed choices into a V2 typed
  contract with implementation/configuration digests.
- [x] EF.22 Join V1/V2 through registry V4 and reject dual active contracts
  for one plant.
- [x] EF.23 Carry V2 missing/stale feedback, deadline and provenance semantics
  through the common session and pinned canonical trace.
- [x] EF.24 Add V2 core/adapter/registry/session/trace tests and repository-gate
  stages while keeping all real profiles/contracts/loadable models at zero.
- [x] EF.25 Define a permanently synthetic multi-actuator V2 composition
  boundary with no canonical graph, rigid-body, shared-bus or exact-model
  claim.
- [x] EF.26 Require one equal-clock plant per exact observed actuator slot and
  derive independent deterministic per-axis seeds.
- [x] EF.27 Require canonical all-axis command/load partitions, dense
  reset/batch/time identities and an aggregate current admission budget.
- [x] EF.28 Reject a whole batch before mutation and transactionally roll back
  every axis after forced mid-submit or mid-step failure.
- [x] EF.29 Latch a bank-wide synthetic thermal fail-stop, clear all commands
  and require explicit reset without claiming physical power removal.
- [x] EF.30 Snapshot every bank/axis hidden state, prove exact continuation and
  pin the twelve-axis trace while all authority fields remain false.
- [x] EF.31 Define the exact claim-bearing API, UI, document, tool, schema and
  generated-consumer scope without scanning raw vendor evidence or test
  fixtures as project assertions.
- [x] EF.32 Hash every one of the 674 text/JSON surfaces and all 566
  nonsemantic PNG/GLB/STEP assets into one deterministic manifest.
- [x] EF.33 Reject universal/family, acquisition, build, simulation and
  physical-authority promotion with nine lexical and three structured rules.
- [x] EF.34 Preserve explicit denial wording while allowing no inline
  suppression, warning mode or free-form exception.
- [x] EF.35 Fail closed on scope weakening, symlinks, malformed JSON,
  non-UTF-8 unclassified content, structured authority and report tamper.
- [x] EF.36 Bind the zero-finding/zero-exception report through
  Entity–Activity–Agent provenance and add it to the machine gate evidence.
- [x] EF.37 Define a bounded allocation-free fault-event record with explicit
  command, feedback and bus context and no physical-state inference.
- [x] EF.38 Preserve the primary cause, retain ordered secondary events and
  count overflow without unbounded storage.
- [x] EF.39 CRC-bind every named snapshot field and fault closed on missing,
  corrupt or semantically impossible restart input.
- [x] EF.40 Prove reconnect, configuration reload and restart cannot clear the
  latch or re-enable outputs.
- [x] EF.41 Require exact generation, durable-record/reset assertions,
  recovered prerequisites, motor-off observation and authorized supervisor
  reset before returning only to BOOT.
- [x] EF.42 Keep persistence, UTC/audit binding, exact-tuple motor-off
  observation and physical power removal explicitly open.
- [x] EF.43 Define a deterministic composed event alphabet spanning boot,
  leases, enable, queued control, expiry, renewal, shutdown/acknowledgement,
  fault/reset, prerequisite loss, configuration lifecycle, transport response
  and failure, cycle turnover and monotonic-clock regression.
- [x] EF.44 Run 17 named adversarial traces, every ordered action pair from an
  enabled prefix and 4,096 reproducibly seeded 64-action long-haul sequences.
- [x] EF.45 Inspect all 10,865 gateway polls at the final mutable boundary and
  require simultaneous ENABLED state, output permission, live owner lease,
  current motion configuration, exact session/sequence, command generation,
  route and command deadline before normal native TX.
- [x] EF.46 Require non-vacuous normal operation, correlated response
  continuation and safety preemption while auditing every retained native-TX
  disposition for both config and safety authorization.
- [x] EF.47 Preserve STOP/SHUTDOWN as software safety-action frames only;
  never infer tuple-specific motor-off or independent physical power removal.
- [x] EF.48 Define one allocation-free monitor bound to the exact recovered
  fault-evidence core and safety supervisor.
- [x] EF.49 Evaluate configuration mismatch, bus-off, response budget,
  critical drive, local limit and required feedback validity/age in one fixed
  rising-edge order.
- [x] EF.50 Preserve exact command, feedback and bus context for individual
  and simultaneous causes while bounding duplicate levels and secondary
  overflow.
- [x] EF.51 Inject every source after queued IQ and require the next final
  gateway frame to be STOP, never normal control.
- [x] EF.52 Fault closed on malformed sample, recovery omission, invalid
  policy, clock regression or supervisor/evidence misbinding and run GCC,
  ASan/UBSan, Clang and allocation checks.
- [x] EF.53 Preserve distinct native bus-off and exact consecutive-response
  budget/reset behavior in the gateway runtime while leaving the trusted
  ESP32 adapter, durable evidence transaction and physical safe state open.

## Workstream F — Dropbear low-to-high reconciliation

- [ ] F0.01 Accept one canonical Dropbear source revision.
- [ ] F0.02 Resolve all 161 graph questions.
- [ ] F0.03 Accept canonical frames, axes and chirality.
- [ ] F0.04 Bind 12 semantic joints to exact installed actuators.
- [ ] F0.05 Resolve all node IDs, buses and unique owners.
- [ ] F0.06 Bind native and external observations with validity/age rules.
- [ ] F0.07 Resolve both hip-yaw sensor gaps.
- [ ] F0.08 Bind accepted calibration and restrictive limit records.
- [ ] F0.09 Bind exact motor CAD and plant assets.
- [ ] F0.10 Generate URDF/transmission/ros2_control/simulator/UI views.
- [ ] F0.11 Prove cross-view hash and semantic parity.
- [ ] F0.12 Activate graph-gated host and ROS handles.
- [ ] F0.13 Integrate the authenticated host/session authority path.
- [ ] F0.14 Integrate the selected real CAN adapter only after its own gate.
- [ ] F0.15 Preserve one command writer and last-moment safety admission.

## Workstream G — SIL, HIL and release

### G0 — offline controller/estimator SIL

- [ ] G0.01 Select the production rigid-body engine by explicit ADR.
- [ ] G0.02 Admit the canonical Dropbear scene.
- [ ] G0.03 Run joint-level command/state parity across replay, protocol,
  plant and rigid-body backends.
- [ ] G0.04 Run estimator validity/dropout/latency scenarios.
- [ ] G0.05 Run controller limits, saturation and timing budgets.
- [ ] G0.06 Run contact, closed-chain and disturbance scenarios.
- [ ] G0.07 Run lease loss, source/graph/config revocation and safe shutdown.
- [ ] G0.08 Compare canonical traces and dispositions across backends.
- [ ] G0.09 Keep physical and model-fidelity claims false.

### G1 — physical correlation, separately authorized

- [ ] G1.01 Pass G0 physical bench readiness.
- [ ] G1.02 Observe exact installed controller and motor identity.
- [ ] G1.03 Complete listen-only capture before any command.
- [ ] G1.04 Pass exact protocol applicability review.
- [ ] G1.05 Verify independent power removal.
- [ ] G1.06 Run current-limited unloaded one-motor cases.
- [ ] G1.07 Capture voltage/current/position/velocity/temperature with fixture
  and calibration identities.
- [ ] G1.08 Fit only designated fitted parameters on the training split.
- [ ] G1.09 Evaluate declared holdout metrics.
- [ ] G1.10 Record residuals and uncertainty without overwriting official
  facts.
- [ ] G1.11 Repeat fault, stop, disconnect, reboot and bus-error cases.
- [ ] G1.12 Advance to one leg only after G2 evidence is accepted.

### G2 — release

- [ ] G2.01 Close every required P0/P1 test at its required evidence class.
- [ ] G2.02 Close or explicitly reject every candidate for claimed models.
- [ ] G2.03 Verify 44/44 model and 53/53 configuration coverage for a full
  catalog claim.
- [ ] G2.04 Verify signed source/graph/CAD/plant/protocol decisions.
- [ ] G2.05 Verify authenticated operator and artifact paths.
- [ ] G2.06 Verify operations, incident and rollback runbooks.
- [ ] G2.07 Run the complete gate from a clean reproducible environment.
- [ ] G2.08 Sign an exact release manifest; never publish a wildcard support
  claim.

## Immediate execution order

The next safe, dependency-ready actions are:

1. assign human roles without granting physical authority;
2. pilot one product-spec candidate review per series;
3. use the completed immutable candidate-decision materializer;
4. create the first reviewed source facts;
5. use the completed synthetic-proven exact-set assembler for those facts;
6. review the X12 CAD candidate's five open member/origin/sign questions;
7. then run one end-to-end exact-model twin admission pilot;
8. expand by series only after the pilot's rejection and revocation paths are
   proven;
9. keep S15.3 security and all hardware gates on hold until explicit
   authorization; and
10. update the dashboard and machine report after every admitted evidence
    class, never from manual status prose alone.

## Exit condition

Iteration 16 is not complete because the extractor passes. It completes only
when the selected campaign scope has independently accepted source facts,
complete exact-model parameter sets, accepted output-member/axis assets,
deterministic actuator-twin tests and explicit remaining physical-correlation
status. A full-catalog completion claim additionally requires 44/44 plants and
53/53 geometry configurations; anything smaller must be named as a bounded
pilot.
