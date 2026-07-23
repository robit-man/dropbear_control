# Risk register

Scales: likelihood `L` and impact `I` are 1–5; exposure is `L×I`. “Residual”
is the target after the linked retirement evidence, not the current score.

| ID | Risk / trigger | L | I | Exposure | Owner / WP | Retirement evidence | Residual target |
|---|---|---:|---:|---:|---|---|---:|
| RSK-001 | Physical model/firmware differs from manual assumed by codec | 4 | 5 | 20 | Protocol / 000,040 | Exact inventory + clause mapping + captured request/response comparison | 5 |
| RSK-002 | A command value is mislabeled torque when wire semantic is q-axis current | 4 | 5 | 20 | Protocol / 040,050 | Type/unit tests for A1; UI/API label scan; exact torque-constant evidence | 4 |
| RSK-003 | Boot or reconnect enables motion without explicit valid lease | 4 | 5 | 20 | Safety / 070 | Exhaustive transition/property tests, then HIL power-cycle/reconnect | 5 |
| RSK-004 | Multiple tasks/controllers write one actuator | 4 | 5 | 20 | Firmware / 030,070,080 | Unique-owner schema + single TX task + concurrency/contention tests | 4 |
| RSK-005 | Software stop addresses wrong IDs or is unsupported for exact tuple | 4 | 5 | 20 | Safety / 040,070,100 | Bad-ID regression, exact-tuple stop capture and observed stop/physical-cut result | 5 |
| RSK-006 | Host/link loss leaves the last command active beyond safe interval | 4 | 5 | 20 | Safety / 060,070,100 | Fake-clock lease proof plus disconnect/stop-latency HIL | 5 |
| RSK-007 | Unknown brake state permits motion or prevents stopping | 3 | 5 | 15 | Protocol/safety / 040,100 | Default-deny test and tuple-specific brake state/command bench verification | 5 |
| RSK-008 | Stub transport reports success and masks absence of I/O | 4 | 4 | 16 | Firmware / 080 | Interface requires observable TX/RX; negative stub and adapter integration tests | 4 |
| RSK-009 | Bus schedule exceeds utilization/deadline under 6/12 actuators | 4 | 5 | 20 | Real-time / 080,100 | Analytic budget, emulator stress, then one-leg/two-leg HIL timing | 5 |
| RSK-010 | Stale/missing native or analog state is treated as valid | 4 | 5 | 20 | State / 090 | Timestamp/age validity tests, dropout injection and HIL sensor disconnect | 5 |
| RSK-011 | Joint names, signs, IDs, limits or axes drift across layers | 5 | 5 | 25 | Registry / 030,120 | Canonical schema, generated views, hash admission and parity test | 5 |
| RSK-012 | Five-joint simulation hides the sixth hip-yaw actuator/sensor gap | 5 | 4 | 20 | Dropbear / 030,120 | Semantic six-joint mapping with explicit missing-state validity test | 4 |
| RSK-013 | CAD output member is guessed from flattened/ambiguous STEP | 5 | 4 | 20 | CAD / 140 | Manual/re-source articulation review and rotation/housing immobility evidence, 44/44 | 4 |
| RSK-014 | Unsourced inertial/plant values produce persuasive but invalid simulation | 5 | 4 | 20 | Simulation / 140,150 | Parameter provenance/uncertainty validator; unsupported values block release | 4 |
| RSK-015 | Duplicate Dropbear URDF/CAD/generated assets diverge from authority | 5 | 4 | 20 | Robot description / 120,160 | Canonical-source decision, reproducible generation and duplicate exclusion test | 4 |
| RSK-016 | Open-loop 10 Hz Gazebo demo is mistaken for physical controller readiness | 4 | 4 | 16 | Controls / 110,160 | Shared SystemInterface, corrected rate budgets and cross-backend controller tests | 4 |
| RSK-017 | Unauthenticated remote endpoint commands physical robot | 4 | 5 | 20 | Security / 170 | Default-disable, identity/role enforcement and bypass/negative tests | 5 |
| RSK-018 | Corrupt/replayed serial frame becomes an admitted command | 3 | 5 | 15 | Link/security / 060,070 | CRC/resync/fuzz/replay tests and sequence/session binding | 4 |
| RSK-019 | Config/calibration tamper or partial update changes safe behavior | 3 | 5 | 15 | Security/config / 030,170 | Atomic integrity-checked update, rollback and config-hash admission tests | 4 |
| RSK-020 | Vendor/download/toolchain revision silently invalidates evidence | 3 | 4 | 12 | Sources/release / 010,180 | Pin/hash diff, dependency graph invalidation and reproducible build | 4 |
| RSK-021 | Offline/SIL pass is reported as bench/HIL/model support | 5 | 5 | 25 | Assurance / 020,180 | Typed evidence classes, exact tuple schema and negative claim-generation tests | 5 |
| RSK-022 | Vendor CAD redistribution violates license/terms | 3 | 4 | 12 | CAD/legal / 140 | Per-source disposition before artifact publication | 3 |
| RSK-023 | User’s pre-existing dirty firmware/web work is overwritten or falsely attributed | 3 | 4 | 12 | Release / 000,180 | Baseline ownership snapshot and path/diff preservation gate | 3 |
| RSK-024 | Emergency safe action is delayed by diagnostics/logging or a blocked task | 3 | 5 | 15 | Firmware / 070,080,100 | Event-priority proof, bounded queues/load tests and HIL latency evidence | 5 |
| RSK-025 | Physical cut, fixture, load or power limits are inadequate for test | 3 | 5 | 15 | Bench safety / 000,100 | Reviewed hazard analysis, inspection, dry run and independent cut test | 5 |
| RSK-026 | SDK capability is mistaken for enabled/provisioned chip security, leaving firmware or identities unrooted | 4 | 5 | 20 | Security / 170 | Exact toolchain/sdkconfig/partition/chip/eFuse profile, independent selection review and boot-chain provisioning evidence | 5 |
| RSK-027 | Partial write, reboot or rollback activates an unaudited/stale config, calibration or firmware generation | 3 | 5 | 15 | Security/config / 030,170 | Verifier assertion plus atomic durable receipt/audit protocol, encrypted monotonic store and reset/power-loss fault campaign | 4 |
| RSK-028 | Release/device/operator/audit key reuse or secret leakage compromises multiple trust domains | 3 | 5 | 15 | Security/operations / 170 | Seven-purpose key separation, non-exportable/offline custody, secret scans and rotation/revocation tabletop evidence | 4 |
| RSK-029 | Machine-extracted product-sheet value is mapped to the wrong plant semantic, phase basis, shaft basis, duty class or envelope and silently becomes simulator truth | 5 | 4 | 20 | Simulation/evidence / 020,150,180 | Page/header/coordinate-bound raw candidates, explicit ambiguity blockers, independent candidate review, separate source-fact materialization and zero automatic runtime admission | 4 |

No exposure is accepted merely because a work package is scheduled. Current
P0 physical risks RSK-001, 005..007, 009..010, 025 and production security
risks RSK-026..028 remain open until their physical/provisioning/power-loss
evidence exists. RSK-029 remains open until accepted source facts and complete
per-model sets have independent semantic review.
