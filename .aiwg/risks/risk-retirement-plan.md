# Risk retirement plan

Retirement is evidence generation in dependency order; it is not rewriting a
score. Results attach using [evidence-format.md](../testing/evidence-format.md).

| Order | Experiment / decision | Risks | Entry condition | Pass / stop rule | Opens |
|---:|---|---|---|---|---|
| 1 | Freeze dirty-work ownership and upstream/vendor source identities | 020,023 | Repository readable | All changes attributable; 44/53/9 inventories reproduce | Baseline work |
| 2 | Exact physical inventory without power | 001,005,007,011,025 | Safe physical access | Labels/firmware/bus/brake/topology captured or remains UNKNOWN | Applicability review |
| 3 | Exact-tuple/claim schema negative tests | 001,020,021 | Source register | Unknown/wildcard/stale evidence always yields unsupported | Offline claims |
| 4 | Canonical registry migration and parity test | 004,011,012,019 | Inventory candidates | Unique owner/name/ID; six joints explicit; hash mismatch blocks enable | Firmware/ROS generation |
| 5 | Independent V4.4 clause/vector review | 001,002,005,007 | Pinned manual | Two-person transcription agrees; ambiguities logged, not guessed | Pure codec |
| 6 | Pure codec boundary/malformed/property suite | 002,005,018 | Reviewed vectors | Host and embedded core agree; no overflow/malformed emission | Emulator/scheduler |
| 7 | Fake-clock safety/admission state exploration | 003,004,006,018,024 | Typed config/codec | No sequence reaches motion without state+owner+lease; failure preempts TX | Offline P1 gate |
| 8 | Link parser fuzz/replay/config mismatch campaign | 006,018,019 | Link contract | No malformed/replayed/mismatched command admitted; bounded resync | Host integration |
| 9 | Multi-node emulator schedule saturation/fault campaign | 004,008..010,024 | Emulator + scheduler | Declared utilization/jitter/deadlines hold; safe action cannot starve | Hardware planning |
| 10 | CAD pilot: one assembly and one flattened file | 013,014,022 | Conversion schema/license review | Output member reviewed, rotation/scale pass, or explicitly unsupported | 44-model conversion |
| 11 | Dropbear canonical-description comparison | 011,012,015,016 | Registry + CAD pilot | One authority chosen; joint/axis/limit issues enumerated and parity tested | Digital-twin integration |
| 12 | Security bypass/tamper tabletop and negative tests | 017..020 | Identities/roles/update design | Default-deny and rollback evidence; no diagnostic safety bypass | Bench authorization |
| 13 | Unpowered bench inspection and safe-cut dry run | 005..007,025 | Approved hazard/runbook; exact tuple | Independent reviewer passes wiring, fixture, cut and current limits | First powered pulse |
| 14 | Current-limited one-motor discovery/read/disable only | 001,005,007..010,024..025 | G0 physical approval | Identity matches; safe action/telemetry observed; any discrepancy stops | Motion-mode tests |
| 15 | One-motor disconnect/fault/limit/stop injection | 003,005..010,024 | Step 14 pass | Measured safe-action latency within approved budget; cut works | Endurance |
| 16 | Eight-hour unloaded/current-limited endurance | 006,009..010,024..025 | Step 15 pass | No deadline/watchdog breach; thermal/electrical limits hold | One-leg HIL |
| 17 | Six-actuator leg, then two-leg ownership/timing | 004,009,011..012,024..025 | Electrical/mechanical re-review | No cross-bus owner/contention; all stop paths verified | Robot integration |
| 18 | Cross-backend controller/estimator comparison | 014..016,021 | Validated plant/twin/HIL | Error envelopes explained and within approved budgets | G6/G7 |

Physical orders 13–18 are `PHYSICAL-HOLD`. Any unexpected motion, identity,
firmware, brake, bus, thermal or stop behavior aborts the experiment, removes
power and creates a new evidence-backed risk review before retry.

