# Calibration, limit and HIL campaign templates

Status: `TEMPLATES-ONLY-NO-MOVEMENT-AUTHORITY`

These campaigns are ordered after installed identity, source/graph admission,
physical adapter conformance and independent safe-power evidence. Each stage
requires a new exact authorization; success at one stage never authorizes the
next.

## Per-joint calibration template

Record exact configuration, graph, actuator serial/model/hardware/firmware,
route, tool IDs/calibration, fixture, operator, reviewer, ambient conditions,
reference feature, motor-to-joint sign, output-per-motor ratio, joint-zero
definition, uncertainty and invalidation conditions.

Planned sequence:

1. mechanically restrain every non-test axis and establish independent stop;
2. prove disabled/read-only telemetry and feedback identity;
3. verify current/travel/time limits against separately accepted limit
   evidence;
4. perform one bounded direction pulse only under approved authorization;
5. independently compare native and external observation;
6. approach reference or hard stop only by its reviewed procedure;
7. repeat from both directions to quantify backlash/repeatability;
8. remove energy and seal raw data before deriving calibration; and
9. have an independent reviewer admit the exact record.

Abort on unexpected direction, motion of another coordinate, feedback
disagreement, current/velocity/travel/time bound, fault, communication age,
mechanical interference, restraint change or power-removal unavailability.

## Limit-evidence template

Collect vendor rating, software bound, physically measured safe bound and
runtime derate as distinct signed sources. The effective limit is their exact
intersection; missing dimensions remain missing. Record units, reference
frame, statistic, uncertainty, sample population, temperature/voltage/load
envelope and invalidation conditions.

Movement begins at the lowest independently reviewed current/speed/travel
envelope and expands only through explicit hold points. STEP geometry, a URDF
limit or drive maximum is never a measured safe joint limit.

## HIL progression

| Stage | Scope | Required prior evidence | Injected faults | Pass/stop condition |
|---|---|---|---|---|
| H0 offline fake | no hardware | graph/API contracts | stale lease, wrong config, timing, parser, backend fault | all fail closed; no physical claim |
| H1 protocol emulator | no hardware | exact codec revision | CRC, timeout, reset, wrong node/status | deterministic dispositions |
| H2 isolated adapter loopback | controller/transceiver only | selected adapter and TX-disable boundary | overflow, error passive, bus off, clock wrap | bounded state/loss behavior |
| H3 one restrained actuator, power limited | one exact tuple | identity, protocol applicability, power removal, calibration/limits | host loss, CAN loss, stale state, limit and drive fault | independent stop inside approved bounds |
| H4 one actuator closed loop | one calibrated coordinate | H3 plus feedback reconciliation | sensor bias/dropout, command timeout | no bypass; quantified tracking/stop |
| H5 restrained six-actuator leg | one leg | each H4, accepted coupling/graph | duplicate owner, coupled fault, bus load | ownership/constraints preserved |
| H6 two legs/non-load-bearing | twelve actuators | both legs and whole-robot safe power | asymmetric loss, controller reset, E-stop | deterministic safe state |
| H7 bounded robot task | separately reviewed task | all prior evidence and task hazard review | task-specific | separate release gate |

Every stage names power-removal owner, operator, independent reviewer,
restraint, maximum energy/current/speed/travel/duration, rollback and evidence
outputs before authorization. Automatic recovery and progression are disabled.
