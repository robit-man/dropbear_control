# System requirements baseline

Status: **P1 proposed baseline**. “Shall” defines the intended production
system; it does not assert implementation or verification. Evidence status is
tracked in [traceability-matrix.md](traceability-matrix.md) and gates in
[phase-gates.md](../gates/phase-gates.md).

Priority: `P0` prevents unsafe or false claims; `P1` is required for the first
usable release; `P2` may follow without weakening P0/P1 behavior.

## Scope and authority

| ID | Pri | Requirement | Basis |
|---|---:|---|---|
| SYS-001 | P0 | The project shall maintain one controlled source register identifying revision, origin, authority and permitted use for each external source. | SRC-001..020 |
| SYS-002 | P0 | The project shall compute support for an exact model/hardware/firmware/protocol/transport/mode tuple and shall fail closed when any applicability field is unknown. | SRC-013, support schema |
| SYS-003 | P0 | The project shall distinguish catalogued, offline-conformant, SIL, bench, HIL and robot-release evidence in every API, UI and document claim. | SRC-013, SRC-015 |
| SYS-004 | P1 | The project shall preserve provenance from requirement through design decision, implementation revision, test result and release gate. | SRC-015 |
| SYS-005 | P0 | The project shall preserve the current Dropbear prototype as migration and regression input, not silently treat its IDs, signs, limits or calibrations as production truth. | SRC-014 |
| SYS-006 | P1 | The project shall provide one reproducible repository test entry point with machine-readable result and evidence locations. | SRC-013 |

## Inventory and configuration

| ID | Pri | Requirement | Basis |
|---|---:|---|---|
| CFG-001 | P0 | The system shall use a versioned canonical robot registry for controller nodes, buses, joints, actuator tuples, IDs, signs, ratios, limits, encoders, CAD frames and calibration hashes. | SRC-014, SRC-020 |
| CFG-002 | P0 | Firmware, host, UI, URDF/xacro and simulators shall consume generated or schema-validated views of the same registry. | SRC-014, SRC-015 |
| CFG-003 | P0 | Runtime configuration shall be schema-versioned, integrity-checked and rejected atomically when incomplete, stale or incompatible. | SRC-014 |
| CFG-004 | P0 | Calibration shall identify device, joint, method, units, author, UTC time and source revision and shall update atomically. | SRC-014 |
| CFG-005 | P0 | Each actuator shall have exactly one declared bus owner and one canonical joint name, with aliases used only at import boundaries. | SRC-014 |
| CFG-006 | P1 | Configuration and telemetry shall carry a deterministic schema/configuration hash so mismatched layers cannot enable motion. | SRC-015 |

## Native protocols and units

| ID | Pri | Requirement | Basis |
|---|---:|---|---|
| PRO-001 | P0 | Each native codec shall be versioned independently from transport and model parameters. | SRC-003..011, SRC-015 |
| PRO-002 | P0 | An RMD CAN V4.4 codec shall encode standard 8-byte command frames at identifier `0x140 + node_id` and decode responses at `0x240 + node_id` for admitted node IDs. | SRC-003 |
| PRO-003 | P0 | The codec shall reject invalid identifiers, lengths, reserved-bit violations, unknown opcodes and arithmetic overflow without emitting a command. | SRC-003 |
| PRO-004 | P0 | Every wire field shall define signedness, endianness, scale, valid range, rounding, saturation/rejection policy and motor/output coordinate. | SRC-003..011 |
| PRO-005 | P0 | The `0xA1` quantity shall be represented as q-axis current in 0.01 A/LSB unless exact-tuple evidence proves another documented semantic; it shall not be labeled torque. | SRC-003, SRC-014 |
| PRO-006 | P0 | Brake-equipped tuple command admission shall require an evidenced brake-state protocol and shall otherwise reject motion commands. | SRC-003, SRC-006 |
| PRO-007 | P1 | Request/response handling shall correlate node, opcode, sequence context and deadline and shall expose timeout, malformed and unexpected-response results. | SRC-003, SRC-015 |
| PRO-008 | P1 | Each claimed capability shall have reviewed official-source golden vectors plus independent boundary and malformed vectors executable in host and platform-independent embedded tests. | SRC-003..011 |

## Gateway safety and real-time behavior

| ID | Pri | Requirement | Basis |
|---|---:|---|---|
| SAF-001 | P0 | The gateway shall boot with actuation disabled and shall emit no motion command until configuration, discovery, health and lease prerequisites pass. | SRC-013..015 |
| SAF-002 | P0 | The gateway shall implement the states BOOT, DISCOVERY, DISABLED, ARMED, ENABLED, SHUTDOWN and latched FAULT with only the transitions in the approved safety specification; SHUTDOWN shall withhold completion until the required motor-off acknowledgement is observed. | SRC-015 |
| SAF-003 | P0 | Each actuator shall have exactly one command writer selected by deterministic arbitration. | SRC-014, SRC-015 |
| SAF-004 | P0 | Every motion command shall include a bounded validity interval and shall expire locally using a monotonic clock. | SRC-015 |
| SAF-005 | P0 | Missing/expired lease, configuration mismatch, bus-off, response-budget violation, drive fault or local limit violation shall leave ENABLED and request the tuple-specific evidenced motor-off action. | SRC-013..015 |
| SAF-006 | P0 | FAULT shall latch cause, time, command/state context and bus evidence and shall require an authorized explicit reset after prerequisites recover. | SRC-015 |
| SAF-007 | P0 | Position, velocity, current/effort, temperature, voltage and following limits shall be enforced in the correct coordinate using provenance-tagged values; unknown required limits shall prevent enable. | SRC-013..015 |
| SAF-008 | P0 | Diagnostic/configuration traffic shall be scheduled and bounded so it cannot starve control or motor-off traffic. | SRC-015 |
| SAF-009 | P0 | Software safety shall not substitute for an independently testable physical power-removal path. | SRC-015, SRC-019 |
| SAF-010 | P1 | Every admission and safety-state transition shall be deterministic, auditable and executable in host tests with fault and time injection. | SRC-015 |

## ESP32 gateway and host link

| ID | Pri | Requirement | Basis |
|---|---:|---|---|
| FW-001 | P0 | The ESP32 gateway shall use a real configured transport adapter and shall not report successful I/O from a stub. | SRC-013 |
| FW-002 | P1 | The CAN scheduler shall measure and enforce per-cycle utilization, response deadlines, retry budgets and bus-off recovery policy. | SRC-013..015 |
| FW-003 | P1 | Native drive feedback shall expose timestamped position, velocity, current, temperature, voltage, status/error and connectivity with validity flags. | SRC-013, SRC-015 |
| FW-004 | P1 | External sensors shall expose independent sample time, calibration identity, validity and fusion status; missing hip-yaw sensing shall remain explicit. | SRC-014 |
| FW-005 | P0 | Production firmware shall not start actuation from play mode, a UI connection or chirality alone. | SRC-014 |
| FW-006 | P1 | Timing-critical protocol, arbitration and safety cores shall compile and test without ESP32 hardware adapters. | SRC-013, SRC-015 |
| LNK-001 | P0 | The host link shall use bounded binary framing with protocol version, length, sequence, monotonic timestamp, message type and CRC plus deterministic stream resynchronization. | SRC-013..015 |
| LNK-002 | P0 | Command messages shall contain desired enable state, command mode, SI-unit values, lease duration, config hash and source identity. | SRC-015 |
| LNK-003 | P1 | State messages shall contain sample timestamps, validity, joint state, drive health, bus health, safety state, fault and config hash. | SRC-015 |
| LNK-004 | P1 | Acknowledgements shall bind to request sequence and report accepted, rejected, expired or executed disposition without equating transport receipt to actuator execution. | SRC-015 |
| LNK-005 | P1 | Link capability/rate negotiation shall fail closed on incompatible major versions or required capabilities. | SRC-015 |

## Host, ROS and high-level control

| ID | Pri | Requirement | Basis |
|---|---:|---|---|
| HST-001 | P1 | The host library shall expose one coherent asynchronous transport/device API with concrete serial, replay, emulator and later CAN/HIL adapters. | SRC-013 |
| HST-002 | P1 | Vendor bytes shall terminate at codec/device boundaries; robot controllers shall use typed SI-unit joint commands and timestamped state. | SRC-015 |
| HST-003 | P1 | A `ros2_control` SystemInterface shall expose hardware, protocol-emulated SIL and whole-robot backends through the same joint command/state contract. | SRC-014, SRC-015 |
| HST-004 | P0 | Robot controllers, diagnostics and remote clients shall not bypass gateway arbitration, leases or safety state. | SRC-014, SRC-015 |
| HST-005 | P1 | Recorded telemetry/command replay shall be deterministic enough to reproduce parser, timing, controller and estimator regressions. | SRC-015 |

## CAD and model catalog

| ID | Pri | Requirement | Basis |
|---|---:|---|---|
| CAD-001 | P1 | The asset pipeline shall preserve all 44 catalog model identities and all 53 source STEP variants with archive revision, URL and SHA-256. | SRC-001, SRC-012 |
| CAD-002 | P0 | A simulation-ready asset shall identify separately reviewed fixed housing and rotating output geometry; an inferred or unnamed output shaft shall remain unsupported. | SRC-012, SRC-018 |
| CAD-003 | P1 | Each accepted asset shall record source units, source-to-robot transform, output origin/axis/positive direction and zero pose. | SRC-012, SRC-015 |
| CAD-004 | P1 | Visual and collision meshes shall be derived reproducibly, named separately and checked for scale, orientation, topology and geometric regression. | SRC-015 |
| CAD-005 | P0 | Mass, center of mass and inertia shall carry trusted provenance and shall not be released from unqualified CAD material assignments. | SRC-012, SRC-014 |
| CAD-006 | P1 | Redistribution/license disposition shall be recorded before vendor-derived CAD or converted meshes are distributed. | SRC-012 |

## Simulation and Dropbear reconciliation

| ID | Pri | Requirement | Basis |
|---|---:|---|---|
| SIM-001 | P1 | The simulator shall separate byte-accurate protocol emulation, single-actuator plant and whole-robot rigid-body levels behind controlled interfaces. | SRC-013, SRC-015 |
| SIM-002 | P1 | The protocol emulator shall model admitted opcodes, responses, timing, state and injectable malformed, timeout, bus and drive faults by protocol revision. | SRC-015 |
| SIM-003 | P1 | Each actuator plant shall identify electrical, mechanical, gear, friction/backlash, saturation, thermal, sensor and latency parameters with source and uncertainty. | SRC-013, SRC-015 |
| SIM-004 | P1 | Whole-robot simulation shall use the canonical joint registry and same hardware interface, units, limits and observable state as physical control. | SRC-014, SRC-015 |
| SIM-005 | P1 | Engine selection shall be supported by a reproducible benchmark for contact stability, controller integration, deterministic replay, headless CI and developer workflow. | SRC-015 |
| SIM-006 | P2 | The browser shall consume converted GLB/catalog/telemetry artifacts and shall not be the authoritative rigid-body or plant simulator. | SRC-013, SRC-015 |
| ROB-001 | P0 | Dropbear shall establish semantic canonical names and map five-joint simulated legs and six-actuator hardware legs without silently dropping hip yaw. | SRC-014 |
| ROB-002 | P1 | A reviewed Dropbear description shall reconcile two-leg topology, joint axes/origins, transmissions, limits, mass/inertia, collisions and sensors. | SRC-014 |
| ROB-003 | P1 | Detailed and simplified descriptions shall be generated from or checked against one canonical source; committed build/install duplicates shall not be authoritative. | SRC-014 |
| ROB-004 | P0 | A physical hardware plugin shall use the same gateway interface and shall not be represented by GazeboSystem or open-loop position control. | SRC-014 |
| ROB-005 | P1 | Estimator and joint/whole-body controller tests shall run unchanged against replay, SIL and the hardware interface, with backend-specific tolerances declared. | SRC-015 |
| ROB-006 | P1 | Locomotion, behavior and operator tools shall consume versioned robot state and command leases and shall not directly own native motor traffic. | SRC-014, SRC-015 |
| ROB-007 | P0 | Remote physical actuation shall be authenticated, authorized, audited and disabled by default. | SRC-014 |

## Security, verification and release

| ID | Pri | Requirement | Basis |
|---|---:|---|---|
| SEC-001 | P0 | Physical command endpoints shall authenticate operator/service identity and authorize least-privilege actions. | SRC-014 |
| SEC-002 | P0 | Network diagnostic clients shall be unable to bypass command arbitration or enable state, even after parser or client compromise. | SRC-014, SRC-015 |
| SEC-003 | P1 | Configuration, calibration, firmware and generated artifacts shall have integrity, provenance and rollback controls appropriate to their safety effect. | SRC-014 |
| SEC-004 | P1 | Logs shall avoid secrets while retaining actor, decision, state transition, configuration and fault audit evidence. | SRC-014 |
| SEC-005 | P1 | Dependency, toolchain and vendor-asset updates shall be pinned, reviewed and reproducible. | SRC-001, SRC-002 |
| VER-001 | P0 | Tests shall classify offline, SIL, bench, HIL and robot evidence and shall never promote one class to another. | support schema |
| VER-002 | P1 | Every P0/P1 requirement shall map to planned verification and a phase gate; open hardware evidence shall be visible. | SRC-015 |
| VER-003 | P1 | Protocol tests shall cover official golden vectors, round trips, limits, rounding, overflow, malformed length/ID/opcode and unexpected response. | SRC-003..011 |
| VER-004 | P0 | Safety tests shall use a fake monotonic clock and injected loss/fault events to prove boot-disabled, lease expiration, single writer, latching and reset guards. | SRC-015 |
| VER-005 | P1 | CAD tests shall check inventory/hash plus reviewed scale, articulation, output axis, housing immobility, collisions and renders for 44/44 models. | SRC-001, SRC-012 |
| VER-006 | P1 | Bench/HIL records shall identify exact tuple, wiring, power/current limits, load, instruments, firmware/config revisions, operator and UTC time. | SRC-016..019 |
| VER-007 | P0 | A release gate shall reject unsupported claims, failed required tests, whitespace errors, unreviewed generated changes and loss of preserved user work. | SRC-013 |
