# Phase gates and hold points

Passing a gate authorizes the next bounded scope; it does not declare all
motors supported. Evidence classes follow
[support-evidence-schema.md](../requirements/support-evidence-schema.md).

| Gate | Scope authorized after pass | Required objective evidence | Hard hold / explicit non-credit |
|---|---|---|---|
| G0 — P0 preservation and bench readiness | Offline work; then only the approved unpowered/current-limited procedure | Source/diff baseline; exact physical tuple/topology; hazard review; fixture/current limits; independent power cut and operator checklist | Current offline baseline does **not** pass physical G0: SRC-016,019 missing |
| G1 — P1 protocol truth | Implement one real adapter/emulator integration for evidenced tuple | Official clause ledger; shared typed units; dual host/embedded vectors; malformed/boundary tests; deterministic offline safety/lease tests; traceability | Does not prove firmware applicability, motor-off, brake, timing or motion |
| G2 — P2 one motor safe gateway | Current-limited one-motor development | Exact tuple/captures; real TX/RX; feedback/faults; lease/stop/disconnect/bus-off/independent-cut injection; 8-hour run | No load/leg/robot credit; any unknown safe action blocks |
| G3 — P3 one six-joint leg | Bounded one-leg controller/HIL work | Six unique owners/IDs; bus utilization/jitter; sensors/calibration/hip-yaw disposition; all motor-off paths; no missed watchdogs | Does not authorize both legs or locomotion |
| G4 — P4 complete actuator catalog/SIL | Claim model-specific asset or SIL support by evidenced tuple | 44/44 model records, 53/53 variants preserved; housing/output/axis review; license; independently reviewed parameter provenance/uncertainty; emulator/plant tests | Current output-shaft/articulation and exact-model plant support are **0/44**; STEP acquisition and 531 extracted product-sheet candidates alone get no asset/SIL credit |
| G5 — P5 Dropbear digital twin | Use one canonical Dropbear simulation baseline | Canonical registry/description; two-leg six-joint mapping; axes/transmissions/limits/inertials/collisions/sensors; engine benchmark; generated-duplicate controls | Existing visual/Gazebo/Isaac/Altair artifacts alone do not pass |
| G6 — P6 robot-control integration | Controlled current-limited robot controller tests | Shared SystemInterface; estimator/controller replay+SIL+HIL; timing/error budgets; faults and rollback | Open-loop 10 Hz demos and UI trajectories get no controller credit |
| G7 — P7 behavior/locomotion release | Release named robot configurations and behaviors | Approved G2–G6 dependencies; authenticated operator path; staged trials; exact release evidence and rollback | No wildcard motor/firmware/config release |

## Universal gate checks

Every gate also requires: no open unaccepted P0 risk for its scope; all mapped
P0/P1 requirements verified at the required evidence class; reproducible test
entry passes; trace links and evidence manifests validate; no unsupported claim
or stale evidence; source/license review; preserved user work; independent
reviewer sign-off.

Gate failures record failed criterion, owner, corrective WP/task and evidence
location. Waivers cannot convert missing physical evidence into offline proof
and cannot waive SAF-001..009 for powered motion.
