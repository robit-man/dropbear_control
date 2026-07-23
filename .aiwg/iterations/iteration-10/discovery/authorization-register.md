# Physical-work authorization register

Status: `ALL-PHYSICAL-ACTIONS-UNAUTHORIZED`

Authorization is action-, asset-, setup-, location- and time-specific. It is
never inferred from repository access, a passing offline test, prior work or
approval of an earlier phase.

| Phase | Minimum authorizers/roles | Explicitly permitted scope | Still prohibited |
|---|---|---|---|
| U0 unpowered visual inventory | hardware owner, safety reviewer, named operator, independent inventory reviewer | exact visual/photo/document actions on named de-energized asset | connection, power, TX, motion, register read |
| U1 de-energized continuity | U0 plus qualified electrical operator | named probe points/tool after verified zero energy | cable mating, insulation defeat, powered test |
| L0 isolated adapter proof | electrical reviewer, safety reviewer, adapter owner | controller/transceiver on isolated test source | robot connection |
| L1 robot listen-only capture | hardware owner, safety reviewer, power-removal owner, electrical operator, capture reviewer | exact receive-only setup/time window | any TX, configuration change, actuator command |
| P0 safe-power survey | hardware owner, independent safety reviewer, qualified electrical team | approved topology/measurement/injection | actuator command unless separately named |
| C0 one-joint calibration/limit | all P0 roles plus mechanical operator/reviewer and controls owner | one restrained actuator and exact envelope | other axes, load-bearing operation |
| H0 one-actuator HIL | hardware/safety/controls owners, HIL operator, independent reviewer | one exact tuple, faults and bounds | leg/robot progression |
| H1 leg HIL | new stage-specific approval | one restrained six-actuator leg | two-leg/load-bearing task |
| H2 whole-robot HIL/task | formal release authority and task hazard review | exact approved task/envelope | anything outside task release |

## Required authorization record

Every authorization must name:

- authorization ID/revision and superseded record;
- physical asset/revision, controller, setup and location;
- allowed actions and explicit exclusions;
- operator, hardware owner, safety reviewer and evidence reviewer;
- valid UTC start/expiry;
- energy/current/voltage/speed/travel/load/time bounds;
- preconditions, hold points, aborts and independent power-removal owner;
- tools/fixtures/restraints and their evidence;
- expected output paths and custody;
- rollback/restoration state; and
- signatures or controlled approval references.

An expired, unsigned, ambiguous, broadened or configuration-mismatched record
is no authority. Iteration 10 creates no authorization record and permits zero
physical actions.
