# Iteration 7 dual-track plan — review authority and runtime/control convergence

- Iteration status: `CLOSED-OFFLINE-FOUNDATION-EXTERNAL-REVIEW-CARRY`
- Phase context: P1/P2 elaboration and P3 integration preparation
- Starting point: 44/53/53 exact CAD registry, one real X12 candidate, 0/53
  accepted configurations, 0/44 supported models, complete offline gate green
- Safety boundary: no powered motor, HIL, robot enable, physical sign, plant
  fidelity or firmware applicability claim

## Track A — independent CAD decisions and released-asset mechanics

| ID | Deliverable | Acceptance |
|---|---|---|
| I7-A01 | Review-decision contract | Strict schema records exact selector, reviewer/time, source+packet+hypothesis hashes, housing/output membership, source unit, axis/origin/reference plane, direction/zero, unresolved answers, disposition and redistribution evidence |
| I7-A02 | Review workbench | Deterministic X12 packet/questionnaire plus local images; reviewer cannot submit acceptance with unanswered questions, overlapping/incomplete members or candidate-hash drift |
| I7-A03 | Independent decision | X12 candidate is accepted, amended or rejected by an identified independent reviewer; automation cannot sign itself |
| I7-A04 | Accepted exporter | Only an accepted decision may populate the V2 ledger and released local artifacts; candidate hashes are rebuilt and reverified rather than relabeled |
| I7-A05 | Cohort campaign | Assembly variants processed in exact-selector order; flattened/shell sources receive reviewed partition/heal/re-source decisions |

## Track B — shared runtime assets, plant evidence and control integration

| ID | Deliverable | Acceptance |
|---|---|---|
| I7-B01 | Shared runtime asset registry — COMPLETE | Canonical host/ROS/simulator registry distinguishes accepted-local from accepted-redistributable; browser copy is redacted and exact parity tested |
| I7-B02 | Host/ROS CAD admission — COMPLETE | Typed loader requires exact series/model/configuration identity, rechecks reviewed artifact hashes, and denies source/candidate/procedural paths; Dropbear bindings can only refine an exact admitted selection |
| I7-B03 | Plant parameter schema — COMPLETE CONTRACT | A 34-value electrical/mechanical/transmission/saturation/thermal/sensor/latency schema requires SI units, bounded uncertainty, source, operating envelope, validation class and a seven-field exact applicability tuple; all 44 models remain unsupported until real data arrives |
| I7-B04 | Toy/plant substitution — FOUNDATION COMPLETE | Exact backend ID plus expected-kind checks distinguish protocol, toy and synthetic plant paths without fallback; browser consumes the generated toy descriptor. Real sourced-plant integration and rigid-body engines remain future slices |
| I7-B05 | ESP32 integration seam — COMPLETE | Preserved PAL/WebSerial/driver writers are inventoried against host-link/config/safety/gateway cores; a no-loss mapping and M0–M7 staged migration forbid silent wiring or fallback |
| I7-B06 | Real transport core — OFFLINE FOUNDATION | Allocation-free bounded RX/TX runtime and fail-only adapter contract distinguish sent/failure/bus-off, clear response expectations, latch safety and retry safety actions. Real ESP32 adapter, measured utilization and recovery remain open |
| I7-B07 | Host/ROS seam | Real serial adapter and ROS hardware lifecycle remain lease/config/safety mediated with deterministic replay backend |

## Dependency graph

1. I7-A01 -> I7-A02 -> I7-A03 -> I7-A04 -> I7-A05.
2. I7-A01 and current exact registry -> I7-B01 -> I7-B02.
3. I7-B03 -> I7-B04; neither depends on physical CAD acceptance, but model
   population requires exact hardware/data evidence.
4. Current native cores -> I7-B05 -> I7-B06 -> I7-B07.
5. No accepted CAD decision may authorize powered motion; CAD, plant, protocol
   applicability, robot configuration and hardware evidence remain independent
   gates.

## Execution slices

1. Implement and adversarially test the review-decision schema and X12
   questionnaire without changing support.
2. Split the current web-oriented registry into canonical local runtime and
   redacted browser projections; add host loader denials.
3. Define sourced plant schema and migrate browser toy parameters to a typed
   demo backend record.
4. Audit the exact ESP32 runtime integration seam against preserved user files,
   then implement only new adapter/core paths with compile and native tests.
5. Present the X12 packet for independent decision. Apply acceptance only after
   all schema/evidence/signature checks pass.

## Definition of Done

- [x] Independent review tooling cannot self-sign or accept unanswered input.
- [ ] X12 has a recorded accept/amend/reject decision; support reflects it
  exactly and never exceeds artifact/redistribution evidence.
- [x] Shared host/ROS/simulator registry, exact host admission and browser
  redaction pass drift/adversarial tests; current loadable count remains zero.
- [x] Plant schema exists, covers 44 models without fabricated values, and toy,
  protocol and actuator-plant identities cannot be confused or substituted.
- [x] ESP32 integration seam is documented and at least one bounded adapter
  slice compiles/tests without overwriting preserved user runtime work.
- [x] Unified gate, traceability, generated drift and whitespace checks pass.

The unchecked X12 decision is intentionally carried forward: the review
contract forbids automation/self-signature and no independent reviewer has
submitted a decision. I7-A04/A05 consequently remain dependency-blocked rather
than being bypassed.
