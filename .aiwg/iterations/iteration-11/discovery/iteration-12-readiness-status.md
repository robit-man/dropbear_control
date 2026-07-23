# Iteration 12 entry readiness status

Overall status: `NOT-READY-FOR-EXECUTION`

Offline preparation is reviewable, but human authority and installed evidence
are absent. This ledger prevents “software complete” from being interpreted
as “safe to touch, power or command the robot.”

| Gate | Required evidence | Current state | Disposition |
|---|---|---|---|
| R12-01 offline regression | unified gate, web and ESP32 compile pass | pass | ready |
| R12-02 source review | seven roles and 29 divergent groups decided | 0 decided | blocked |
| R12-03 source approval | independent accepted lifecycle event active | 0 submissions/events/active | blocked |
| R12-04 graph review | 161 questions plus structured V2 decision complete | 161 unresolved | blocked |
| R12-05 graph approval | independent accepted lifecycle event active | 0 submissions/events/active | blocked |
| R12-06 U0 request | bounded visual-only request available | draft available | reviewable |
| R12-07 people | owner/operator/reviewers/custodian named | all unassigned | blocked |
| R12-08 asset/window/location | exact physical scope and expiry named | unverified/unassigned | blocked |
| R12-09 zero-energy case | isolation, stored-energy controls and verifier evidence | absent | blocked |
| R12-10 custody | approved storage/access/retention assigned | absent | blocked |
| R12-11 installed inventory | twelve slots independently captured/reviewed | 0 submissions | blocked |
| R12-12 controller decision | installed board/controller/transceiver facts reviewed | 0 selected | blocked |
| R12-13 adapter conformance | exact reviewed manifest for purpose | 0 reviewed/selected | blocked |
| R12-14 CAD acceptance | installed exact model/output member reviewed | 0/53 accepted configurations | blocked |
| R12-15 physical support | exact tuple evidence reaches required class | 0 supported models | blocked |

## Permitted next work

Without additional physical authority, the project may:

- assign independent reviewers and schedule review sessions;
- complete source and graph decisions from existing repository evidence;
- review the U0 request, storage location and role boundaries;
- prepare isolated-fixture designs without connecting hardware;
- continue protocol, ROS, simulator, plant and CAD tooling with explicit
  synthetic/offline evidence labels; and
- strengthen negative tests and release evidence.

It may not access the robot, connect a cable, power a controller, capture CAN,
transmit, release a brake, calibrate, run HIL or move an actuator.

## Promotion rule

U0 may change to `AUTHORIZED-PENDING-PRECONDITIONS` only when the exact request
has all required controlled approvals and a valid UTC window. It may change to
`READY-FOR-EXECUTION` only at the worksite after the safety reviewer releases
H0 and H1. U0 completion cannot promote L1 or any powered phase.
