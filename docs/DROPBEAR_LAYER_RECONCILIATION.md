# Dropbear cross-layer reconciliation and completion roadmap

This is the current handoff between the MYACTUATOR library work and the
Dropbear robot. The machine-readable companion is
[`generated/dropbear_reconciliation/reconciliation.json`](../generated/dropbear_reconciliation/reconciliation.json),
validated by
[`schemas/dropbear-reconciliation.schema.json`](../schemas/dropbear-reconciliation.schema.json)
and regenerated from pinned evidence with
[`tools/generate_dropbear_reconciliation.py`](../tools/generate_dropbear_reconciliation.py).

The artifact is a derived observation, not configuration authority. The
canonical Dropbear configuration remains
[`schemas/examples/dropbear-observed-incomplete.json`](../schemas/examples/dropbear-observed-incomplete.json),
whose digest is still
`dd8909bceece765e80d83d7d3f93196d6967b4f3ae72e20fdee6f29d21a81cba`
and whose motion admission remains false.

## Reconciled facts

The evidence is bound to `Hyperspawn/Dropbear` commit
`13cf5ecaa39b8b89c794fe905dcea0490cfa7726`. Source paths and object hashes
are recorded in the generated artifact. No generated `build/` or `install/`
copy is treated as authority.

| Evidence surface | Observed | Trusted runtime meaning |
|---|---:|---|
| Canonical semantic leg actuators | 12 | Stable IDs/names only |
| Legacy CAN command addresses | 12 (`0x141..0x14C`) | Unverified command-address observations |
| Arithmetic `address - 0x140` candidates | 12 (`1..12`) | Protocol-shape candidates, never installed node IDs |
| External analog sensor roles | 10 | Unverified observations; both hip-yaw roles are missing |
| Active ROS leg command joints | 10 (five per leg) | CAD-named Gazebo joints with no actuator mapping |
| Evidence-backed ROS-to-actuator mappings | 0 | No ordering/name-similarity guesses allowed |
| Complete installed motor tuples | 0/12 | No series/model/hardware/firmware/protocol applicability claim |
| Exclusive runtime routes | 0/12 | Bus, node and owner remain unresolved |
| Valid physical calibrations | 0/12 | Zero, sign, ratio and procedure remain unresolved |
| Accepted Dropbear CAD bindings | 0/12 | Housing/output member, origin and axis remain unresolved |
| Physical ROS hardware plugins | 0 | Only `gazebo_ros2_control/GazeboSystem` is observed |
| Motion-ready actuators | 0/12 | Motion is denied |

The existing assets therefore show substantial mechanical and simulation
progress without establishing the connective control authority required for a
physical robot. Visual completeness must not substitute for installed motor,
topology, calibration, state, or safety evidence.

## Current layer map

| Layer | What exists | Current authority | Principal gap before integration |
|---|---|---|---|
| High-level intent / behavior | No production Dropbear planner contract | Missing | Define goals, action space, cancellation, validity horizon and degraded behavior |
| ROS trajectory publisher | Interactive stdin demo, fixed command republished at 1 Hz | Demonstration only | Replace with a typed client of the common robot API; it must not own hardware |
| ROS 2 control / Gazebo | Position command/state, open-loop, controller manager at 10 Hz | Simulation only | Resolve joint graph, loop ownership, rates, limits and measured feedback |
| Production host API | Generic typed offline session/CAD surfaces exist | Offline, unbound to Dropbear | Add an adapter generated from complete canonical graph entries only |
| Host Link V1 | Bounded versioned frames, session/lease/config checks and typed dispositions | Tested offline core | Select/authenticate transport and integrate without a legacy bypass |
| ESP32 ingress / gateway | Exact `CURRENT_Q` binding to typed V4.4 IQ and single-writer fake transport | Tested offline core | Supply reviewed installed bindings; wire through one production runtime task |
| CAN adapter | Controller-independent contract and fake-driver fault/capture suite | Offline, no physical driver | Review controller/transceiver/pins/termination, then isolated listen-only capture |
| Native drive protocol | Official V4.4 codec/emulator and legacy address shape | Codec tested; installed applicability unknown | Inventory exact drive tuple and verify requests/responses against capture/manual |
| Joint observation | Ten uncalibrated external sensor roles; no legacy motor RX path | Incomplete observation | Native telemetry, hip-yaw sensing, timestamps, calibration, consistency/fault policy |
| State estimator | No reconciled joint/robot estimator | Missing | Define frames, fusion, covariance/validity, sample-age and stale-state shutdown |

Every current layer has `physical_motion_authority=false` in the generated
artifact. There is no valid shortcut from the ROS demo or legacy serial/Flask
path to CAN transmission.

## Conflicts that must be resolved deliberately

### Six actuators versus five ROS joints per leg

The firmware exposes hip yaw, hip roll, hip pitch, knee, inner calf and outer
calf. The ROS leg groups expose `*_hip_joint`, `*_knee_actuator_joint`, and
three numbered revolute joints. Closed-chain/passive joint behavior is not
documented well enough to determine which five names, if any, correspond to
the six actuators. Mapping by array order or name similarity is prohibited.

The required result is a reviewed actuation graph that explicitly identifies:

1. every actuated, passive, mimic and closed-chain joint;
2. motor housing and output members;
3. canonical joint origin, axis, positive direction and zero;
4. motor-to-joint coupling/ratio, including multi-actuator constraints;
5. the observation used to close each control loop;
6. simulator constraint implementation and physical counterpart.

### ROS control behavior is not a physical-controller specification

Both leg trajectory controllers are open-loop position controllers. The
manager updates at 10 Hz, while the demo sends fixed goals at 1 Hz. Each active
leg joint in the xacro declares `min_value=-PI` and `max_value=-PI`, a collapsed
range. These observations cannot be automatically replaced with `[-PI, PI]`,
vendor maximum ratings, or arbitrary high rates. Per-joint limits and rates
must come from mechanical review, motor/drive evidence, control bandwidth and
safe test results.

### Legacy CAN addresses are not installed topology

The twelve values `0x141..0x14C` match the shape of V4.4 request identifiers,
so candidate node numbers `1..12` are recorded for investigation. That
arithmetic does not prove the installed drive model, node configuration,
firmware, protocol revision, bus wiring, exclusive owner or response address.
Those route fields intentionally remain null in both canonical and generated
configuration.

### Feedback is incomplete and unqualified

The legacy sketch samples five external analog channels for each leg and has
no external hip-yaw role or correlated motor response path. Offsets and
direction multipliers are migration candidates, not calibrations: they lack a
robot revision, actuator serial/tuple, procedure, reference fixture, tool,
operator, time, result uncertainty and invalidation rules.

## Target authority chain

The production path should be one continuous, observable contract:

```text
behavior goal
  -> time-bounded canonical joint intent
  -> planner / trajectory with limits and collision validity
  -> common Dropbear hardware API and lease owner
  -> Host Link V1 session, sequence, deadline and configuration identity
  -> exact actuator/source/owner/route binding
  -> safety supervisor and single-writer gateway
  -> typed protocol codec
  -> confirmed CAN-driver send
  -> correlated drive response plus independent joint observation
  -> timestamped fused state and fault/validity propagation
  -> controller, planner and operator disposition
```

No downstream stage may accept a command that bypassed an upstream identity,
lease, configuration, limit or safety decision. No upstream stage may report
mechanical state based only on queue admission, transmission, a simulated
command interface, or q-axis current.

## Canonical records still required

### Installed actuator identity and topology

For each of the 12 actuator IDs, record manufacturer, series/model, serial,
hardware revision, drive firmware, exact protocol/revision, transport,
supported control modes, brake applicability, bus, native node, physical
connector and exclusive controller owner. Discovery records must include the
tool, timestamp, operator, robot hardware revision and evidence hashes.

### Limit provenance and selection

Keep four classes separate:

- vendor electrical/thermal/mechanical ratings;
- software command and motion limits;
- physically measured safe robot limits;
- runtime derates from voltage, temperature, bus, estimator and safety state.

The effective bound is the most restrictive currently valid evidenced bound.
An unknown required bound denies the relevant mode; it is never represented
as infinity, zero-by-accident, a family default or a neighboring actuator's
value.

### Calibration

Each joint needs an immutable calibration record containing installed identity
and robot revision, external/native zero references, motor-to-joint sign,
output-per-motor ratio, encoder wrap convention, hard-stop/home/reference
procedure, fixture/tool/operator/time, measurements and uncertainty, result
hash, and invalidation conditions. Motor replacement, node reassignment,
mechanical disassembly, encoder replacement, firmware changes that affect
position, or configuration mismatch must invalidate the applicable record.

### CAD and rigid-body binding

An accepted exact motor asset still needs a Dropbear installation binding:
asset configuration, housing/output members, joint origin/axis/direction/zero,
mount transforms, collision geometry, mass/COM/inertia provenance and the
robot-link association. The official motor STEP pipeline and Dropbear URDF
candidate meshes provide evidence inputs, but neither currently proves those
installation semantics.

## Execution sequence

### Phase 1 — preserve and classify

- Keep the legacy ESP32/Flask code read-only as prototype evidence and
  regression input.
- Select a single source ROS package; remove generated `build/` and `install/`
  products from source authority.
- Inventory native CAD/URDF/USD/Altair variants by path/hash and classify
  source, derivative, candidate and accepted artifacts.
- Keep all generated mappings and routes empty while facts are incomplete.

Exit: regeneration and provenance tests pass; there is still no physical
motion authority.

### Phase 2 — graph and description

- Review the physical kinematic/closed-chain graph with mechanical owners.
- Bind all twelve semantic actuators and all observation sources.
- Establish canonical frames, names, aliases, joint types and passive
  constraints.
- Generate URDF/xacro, simulator and UI views from the reviewed graph instead
  of maintaining independent name lists.

Exit: every ROS joint is mapped or explicitly passive/unmapped; cardinalities
reconcile without a guessed edge; model checks and static transforms pass.

### Phase 3 — unpowered installed discovery

- Record the exact motor/drive/controller/transceiver topology.
- Review power-off wiring, termination, grounding, bus ownership and emergency
  power removal.
- Use the adapter's physically TX-disabled listen-only mode to capture traffic.
- Validate capture loss/timestamps and compare only to the exact applicable
  protocol manual/tuple.

Exit: reviewed identities and read-only observations may populate discovery
records. Command-capable operation remains disabled.

### Phase 4 — calibration and limits under controlled authority

- Approve a constrained bench plan per joint/drive configuration.
- Establish hard/soft/current/velocity/thermal bounds and derating.
- Calibrate zero, sign, ratio and independent observation consistency.
- Exercise physical motor-off, drive faults, bus loss, stale observations,
  watchdogs and independent power removal before load-bearing operation.

Exit: signed calibration/limit records and bench evidence exist for each exact
installed tuple. Any missing actuator keeps robot motion disabled.

### Phase 5 — SIL/HIL common interface

- Implement the Dropbear host adapter and ROS 2 hardware plugin as clients of
  the same typed hardware interface.
- Run protocol emulator, synthetic actuator plant and rigid-body simulation as
  explicitly distinct backends.
- Replay host/native captures through controller tests.
- Run HIL with loads removed or constrained, fault injection, deadline/queue
  stress and estimator validity checks.

Exit: backend substitution is exact and visible; command/state/disposition
semantics match; safety failures propagate end-to-end.

### Phase 6 — incremental robot enable

- Enable one reviewed actuator/joint at a time with constrained current,
  travel, speed, support and independent stop authority.
- Progress from unloaded to supported single-joint, coupled mechanism, one
  leg, both legs and whole-body testing through explicit gates.
- Validate high-level cancellation, lease expiry, stale-state behavior and
  operator/remote authority at every expansion.

Exit: only the reviewed cohort is enableable. Project-wide “supported” or
“motion ready” remains a per-tuple, per-robot-revision evidence decision.

## Near-term implementation backlog

1. Finish the offline command spine integration without wiring legacy writers.
2. Select the actual ESP32 CAN controller path only after its hardware facts
   are reviewed; retain the fail-only adapter as the default.
3. Define a complete graph schema for passive/closed-chain/coupled joints and
   migrate the current 12-actuator observations into it.
4. Build a deterministic ROS/xacro generator that refuses incomplete
   actuator edges and removes the zero-range placeholder limits.
5. Add the Dropbear host API/ROS adapter against fake and synthetic backends.
6. Add timestamped external sensor acquisition/calibration/fusion cores,
   including an explicit hip-yaw strategy.
7. Add physical discovery, calibration, HIL and robot test procedures as
   gated evidence templates—never as pre-filled pass records.
8. Continue independent exact motor CAD review and then bind accepted assets
   to reviewed Dropbear installation members.

## Regeneration and verification

Run:

```bash
python3 tools/generate_dropbear_reconciliation.py --check
tests/dropbear_reconciliation/run_tests.sh
```

The tests re-read each pinned upstream Git object, verify hashes and exact
observations, assert 12/10/10/0 cardinalities, ensure every actuator and layer
remains blocked, and mutate the artifact to prove the schema rejects unsafe
route, identity, calibration, ROS-mapping and motion promotions.
