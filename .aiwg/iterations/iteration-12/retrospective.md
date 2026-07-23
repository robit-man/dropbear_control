# Iteration 12 retrospective

Status: `COMPLETE-OFFLINE`

## What changed

The project gained a single evidence-aware simulator catalog and one
deterministic session contract instead of allowing each demo/backend to define
its own meaning of model identity, time, state and fidelity. A dependency-free
ROS control core now consumes the existing graph-gated hardware API rather
than creating a new path around leases and authority generations.

## What worked

1. Joining existing source, CAD, plant and graph registries exposed real zeros
   without losing the useful 44/53 acquisition coverage.
2. Reusing the fixed-step plant and V4.4 emulator through adapters preserved
   their tests and evidence classes.
3. Cross-backend lifecycle/time/fault/trace vectors found contract issues
   earlier than a ROS or rigid-body integration would.
4. A browser consumer could be added without changing the preserved toy UI or
   exposing source paths.
5. The machine report now makes simulator fidelity zeros release invariants.

## Corrections made during delivery

- backend-kind validation originally used the backend-ID grammar and was
  corrected to accept only the explicit underscore-bearing kind grammar;
- engine admission was strengthened to compare evidence class and
  deterministic-time claims, not only ID/kind/use case;
- ROS activation failure now faults/cancels the already-active underlying
  hardware session instead of leaving lifecycle disagreement; and
- the original percentage assessment was retired because it conflated source
  acquisition with physical and simulation readiness.

## Remaining risk

The new interfaces make missing evidence visible but cannot create it.
Iteration 13 must still obtain human source/graph decisions, reviewed
housing/output CAD, exact model/firmware applicability, sourced/correlated
plants, a pinned rigid-body engine/ROS ABI and separately authorized unpowered
then physical evidence. The user ESP32/web prototypes remain migration inputs,
not admitted production paths.
