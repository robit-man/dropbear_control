# ADR-006: One robot hardware interface across replay, SIL and hardware

- Status: Accepted
- Requirements: HST-002..005, SIM-004, ROB-004..006
- Work packages: WP-110, WP-130, WP-160

## Decision

Implement a typed SI-unit `ros2_control` SystemInterface boundary. Replay,
protocol/plant SIL, rigid-body simulation and the physical gateway are backend
adapters to this contract; controllers do not import vendor bytes or direct
serial/CAN ownership.

## Consequences

Controller/estimator tests become reusable and backend differences explicit.
The existing GazeboSystem/open-loop configuration remains a migration artifact
until mapped to the canonical interface.

