# Iteration 8 plan — authoritative command spine and deterministic evidence backends

- Iteration status: `COMPLETE-OFFLINE-WITH-EXTERNAL-CARRIES`
- Phase context: P2 elaboration, P3 integration preparation
- Entry gate: Iteration 7 unified offline gate green; 77 requirements, 101
  cataloged tests, 44-model plant registry, 53 exact CAD configurations
- External carry: one X12 review workbench is ready, but no independent
  accept/amend/reject decision exists
- Support baseline: CAD accepted 0/53, catalog supported 0/44, sourced physical
  plant 0/44, Dropbear motion enable false
- Safety boundary: no powered motor, HIL, robot enable, physical sign, protocol
  applicability, plant fidelity or hardware recovery claim

## Outcomes

Iteration 8 turns the existing protocol, config, safety, gateway and transport
cores into one denial-first command spine. It also defines the inverse typed
state/disposition path, a CAN-adapter evidence contract, a deterministic
synthetic plant, and a canonical Dropbear topology gap model. None of those
offline outcomes authorizes physical motion.

## Track A — external CAD evidence lane

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I8-A01 | Preserve the X12 review packet | Packet, source, candidate and hypothesis hashes remain reproducible and validation remains green |
| I8-A02 | Receive an independent decision | Identified reviewer supplies a schema-valid accept, amend or reject decision; automation never supplies reviewer identity or judgment |
| I8-A03 | Apply a decision transactionally | Only a validated submitted decision updates the V2 ledger and generated runtime registries; all prior hashes are rechecked |
| I8-A04 | Start the exact-selector cohort | Next assembly selector is processed only after A03 establishes the review/apply loop; flattened inputs remain partition/re-source questions |

Track A is asynchronous. Lack of a human decision does not block offline Track
B work and may not be converted into an inferred acceptance.

## Track B1 — accepted host command to native gateway submission

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I8-B01 | Route-binding type | Allocation-free record binds exact actuator ID, source identity, lease owner, host config identity/revision/hash, safety config reference/generation, owner, route/bus/node, one translation kind and bounded raw-current range |
| I8-B02 | Binding self-validation | Reject empty/oversized text, duplicate selectors, inconsistent host/safety identities, noncanonical decimal revisions, unsupported schemas/modes/scales, invalid nodes/routes/owners and invalid current limits |
| I8-B03 | Session-owned ingress | The production core owns `SessionReceiver`; a caller cannot translate a decoded command that bypassed negotiated session/config/sequence/time validation |
| I8-B04 | Exact identity selection | Resolve by actuator and source, then require exact lease owner and exact config ID/revision/hash; never use family, priority, client-supplied owner or first-route fallback |
| I8-B05 | Mode closure | Initially translate only `CURRENT_Q` to V4.4 IQ control; disable, position, velocity, effort and impedance return distinct unsupported-mode evidence; effort is never interpreted as current |
| I8-B06 | Quantization policy | Accept only finite values lying on the documented 0.01 A grid within a declared numerical tolerance and inside the route-specific raw range; reject rounding, saturation and overflow |
| I8-B07 | Time mapping | Require the lease deadline to be exactly millisecond-aligned, expose the ingress evaluation millisecond and reject expired/overflowing or uint32-incompatible sessions; never extend a lease by rounding |
| I8-B08 | Proof construction | Preserve frame sequence as command generation, lease sequence as safety sequence, exact route/owner/config reference and CONTROL traffic class in a fully initialized `gateway::Submission` |
| I8-B09 | Native encoding | Use only the typed V4.4 codec; no raw payload escape and no physical applicability assertion |
| I8-B10 | Integrated enqueue/send | Feed translated output through config guard, safety supervisor, gateway core and bounded fake transport; assert exact request bytes and response expectation |
| I8-B11 | Adversarial matrix | Cover every denial, boundary raw values, sign/zero, half-LSB values, NaN/Inf, session overflow, replay/reorder, deadline edge, every non-current mode, identity/hash drift and duplicate bindings |
| I8-B12 | Embedded constraints | C++11, warnings-as-errors, no exceptions/RTTI, ASan/UBSan and undefined-symbol allocation scan all pass |
| I8-B13 | Remove test shadow logic | Existing stack test calls the production ingress core or is narrowed so no second command conversion policy survives in test code |

## Track B2 — typed gateway/native egress to Host Link V1

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I8-C01 | Disposition reason map | Every gateway phase/code maps to a stable bounded Host Link disposition reason; unknown enum values fail closed |
| I8-C02 | Correlation record | Preserve request session/sequence/actuator and transaction identity across received, admitted, TX, response, observed and rejected phases |
| I8-C03 | Native state conversion | Convert only fields evidenced by a correlated decoded response; unknown/stale values remain absent and IQ is never labeled torque |
| I8-C04 | Health/safety projection | Connectivity, bus health, drive health, response state and safety state have explicit total maps with conservative defaults |
| I8-C05 | Host envelope builder | Emit typed Host Link messages with gateway-owned session sequence/time/config; no raw native frame field crosses the boundary |
| I8-C06 | Replay parity | Golden encode/decode and emulator traces reproduce the same typed output and disposition order |

## Track B3 — ESP32 CAN adapter conformance and listen-only evidence

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I8-D01 | Adapter capability contract | Declare controller type, bitrate/mode/filter/timestamp/error-state capabilities and fail initialization when required evidence is unavailable |
| I8-D02 | Frame conformance | Standard 11-bit data frames only, DLC 8 for V4.4, exact bus identity, no RTR/extended coercion and explicit invalid-frame denial |
| I8-D03 | Error-state semantics | Would-block, TX failure, error-passive, bus-off, recovery and receive overflow remain distinct; only a confirmed driver send returns SENT |
| I8-D04 | Listen-only capture schema | Append-only capture records clock source, timestamp, bus/controller state, arbitration/flags/DLC/data, loss counters and build/config provenance |
| I8-D05 | Capture validator | Detect time regression, invalid flags/IDs/DLC, missing provenance, discontinuities and loss; never call captured traffic protocol applicability without tuple evidence |
| I8-D06 | Fake-driver conformance suite | Run the same adapter contract against deterministic fault scripts before selecting TWAI or MCP2515 production code |
| I8-D07 | Hardware hold point | Physical adapter wiring requires reviewed pinout/transceiver/termination, isolated listen-only capture and explicit user authorization |

## Track B4 — deterministic synthetic actuator plant

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I8-E01 | Backend boundary | Exact backend ID/kind/parameter-set ID and applicability tuple are mandatory; toy, synthetic-identification and physical backends cannot substitute |
| I8-E02 | Fixed-step state | Explicit electrical current, rotor/output kinematics, thermal states, sensor samples and latency queues; initialization is complete and deterministic |
| I8-E03 | Saturation/friction | Current, voltage, speed, position, torque and temperature bounds plus friction/backlash are explicit parameterized operations |
| I8-E04 | Solver contract | Fixed time step, declared integration method, finite checks, energy/residual diagnostics and stable reset/seed semantics |
| I8-E05 | Protocol coupling | Emulator request/response semantics drive/read the plant without implying a real model or firmware tuple |
| I8-E06 | Analytic fixtures | Zero input, constant torque/current, damping decay, saturation, thermal rise/cooldown and sensor-delay cases compare to bounded analytic expectations |
| I8-E07 | Determinism evidence | Repeated and cross-language golden traces are byte/hash stable under the declared numerical contract |
| I8-E08 | Real-model denial | All 44 catalog rows remain unsupported until a complete sourced parameter set and physical correlation campaign pass TST-SIM-004 |

## Track B5 — Dropbear topology reconciliation

| ID | Atomic work package | Evidence / exit condition |
|---|---|---|
| I8-F01 | Observation inventory | Reconcile repository motor names, URDF/joint names, controllers, buses, nodes, direction assumptions, limits and calibration references without inventing absent values |
| I8-F02 | Canonical actuator graph | Stable actuator IDs map one-to-one to joint/side/role observations and exact unresolved fields |
| I8-F03 | Route/config projection | Generate firmware/host/ROS/simulator views only from complete graph entries; incomplete entries emit explicit denials |
| I8-F04 | Limit provenance | Separate vendor ratings, software limits, measured safe limits and runtime derates; the most restrictive evidenced bound wins |
| I8-F05 | Calibration contract | Record zero, direction, encoder/output ratio, hard-stop/home procedure, timestamp/tool/operator and invalidation conditions |
| I8-F06 | Layer interface map | Trace intent -> planner -> controller -> host link -> gateway -> native protocol -> observation, with ownership, rate, units, frames and failure propagation at every edge |
| I8-F07 | Motion hold point | `motion_enable_allowed` remains false until all installed identities/routes/limits/calibration, protocol applicability, safety I/O and HIL gates are independently satisfied |

## Dependency and execution order

1. B01 -> B02 -> B03 -> B04..B09 -> B10..B13.
2. B03/B08 and gateway dispositions -> C01..C06.
3. Existing bounded transport runtime -> D01..D06; D07 is an external
   hardware authorization gate.
4. Existing strict plant registry -> E01..E08.
5. Existing Dropbear observations -> F01/F02 -> F03..F07.
6. A01 -> A02 -> A03 -> A04 proceeds independently and never feeds a motion
   authorization bit.
7. Every merged slice updates test catalog, traceability, build manifests and
   the unified gate before the next dependency consumes it.

## Hazard ledger for this iteration

| Hazard | Unsafe shortcut prohibited | Required control |
|---|---|---|
| H8-01 wrong actuator receives command | First/family/default route | Exact actuator+source+owner+config binding and duplicate rejection |
| H8-02 torque/current confusion | Treat effort N.m as IQ A | Closed mode translation; explicit unsupported effort result |
| H8-03 lease extended by conversion | Ceil or unchecked ns-to-ms conversion | Exact millisecond alignment and expiry recheck |
| H8-04 hostile owner selection | Trust priority/source numeric data | Reviewed source identity -> static owner mapping |
| H8-05 stale configuration | Compare only config name or hash | Exact name, canonical revision, SHA-256, schema and generation proof |
| H8-06 silent saturation | Clamp current to int16/route bound | Reject off-grid/out-of-range values |
| H8-07 false transmission/observation | Treat queue/poll as physical send/state | Adapter result feedback and correlated response/observation phases |
| H8-08 synthetic-to-real substitution | Match by model family | Exact backend kind/ID/tuple with all catalog models denied |
| H8-09 incomplete robot topology | Generate defaults for absent node/limit/calibration | Machine-readable unresolved fields and motion false |

## Iteration gates

- G8.1: production ingress core and exhaustive native tests pass.
- G8.2: full host->ingress->gateway->fake transport byte path passes with no
  duplicate translator policy.
- G8.3: typed disposition/state egress golden tests pass.
- G8.4: CAN adapter/capture conformance passes fake-driver evidence; no
  physical driver claim.
- G8.5: synthetic plant analytic/determinism suite passes and 0/44 real-model
  support is unchanged.
- G8.6: Dropbear topology artifacts regenerate deterministically and motion
  remains false.
- G8.7: requirements/test/ADR/work-package trace, generated drift, native
  sanitizers, web/host tests, ESP32 compile and whitespace checks all pass.

## Definition of Done

- [x] One production-owned path transforms a session-accepted CURRENT_Q command
  into one exact gateway submission and all ambiguity fails closed.
- [x] Typed egress represents dispositions and observed native state without
  relabeling current as effort or claiming mechanics not observed.
- [x] CAN adapter evidence can be collected and validated in listen-only mode
  before any command-capable hardware path is wired.
- [x] Deterministic synthetic plant exercises control code while remaining
  distinguishable from all real actuator models.
- [x] Dropbear topology gaps are canonical and machine-readable; motion remains
  disabled while any required installed fact is absent.
- [x] Independent CAD review is either applied exactly or carried explicitly.
- [x] Unified offline gate and Iteration 8 verification report are green.
