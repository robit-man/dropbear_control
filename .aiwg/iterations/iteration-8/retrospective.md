# Iteration 8 retrospective

## What worked

- Making the production ingress own the session receiver removed a subtle
  bypass class: downstream translation can no longer receive an allegedly
  accepted command without sequence/config/time validation.
- Exact 0.01 A grid admission made units and quantization observable. Rejecting
  rounding and clamp avoids silently changing a host command at the native
  boundary.
- Modeling egress separately from ingress forced receipt, admission,
  transmission, native response and observed state to remain distinct.
- A controller-independent CAN contract exposed capabilities and driver
  outcomes that concrete libraries often collapse into a success boolean.
- Adding a deliberately synthetic plant now exercises dynamics and protocol
  coupling without weakening the empty real-parameter registry.
- Reading sparse upstream Dropbear content through pinned Git objects allowed
  broad provenance coverage without downloading or trusting generated build
  trees and large LFS payloads.
- The machine reconciliation made the 12-actuator / 10-sensor / 10-ROS-joint
  mismatch testable while prohibiting a convenient but unsafe ordering guess.

## What the gate caught

The first unified run stopped because the new reconciliation file shared the
`generated/dropbear` directory owned transactionally by the existing view
generator. Its strict unexpected-file check worked as designed. The
reconciliation generator was moved to its own
`generated/dropbear_reconciliation` namespace, preserving atomic replacement
and stale-file detection for both producers. The complete gate then passed.

Generator ownership must be defined at directory boundaries before adding a
peer artifact. Shared generated roots otherwise create deletion or false-drift
hazards even when the files themselves are correct.

## What remains difficult

- The five CAD-named ROS leg joints cannot be safely associated with six
  semantic actuators without mechanical/kinematic review of active, passive,
  coupled and closed-chain members.
- All useful physical questions still depend on an exact installed inventory:
  model, serial, firmware, protocol, brake, bus/node/owner, wiring and robot
  revision.
- External analog sensor offsets and signs are observations with no
  transaction, procedure, uncertainty or invalidation semantics.
- Selecting a concrete ESP32 CAN adapter requires hardware information and
  an isolated listen-only plan. Compile success does not answer those facts.
- Real actuator plant values are absent from current vendor evidence and will
  require sourced curves or identification campaigns.
- Independent CAD semantics remain a human decision. Automation can assemble
  and validate the packet but cannot become the independent reviewer.

## Process changes for Iteration 9

1. Give every generator an exclusive output namespace and test that ownership.
2. Extend the Dropbear schema with explicit active/passive/coupled joint graph
   observations, but emit no runtime ROS edge until reviewed completeness.
3. Define transactional calibration and limit-provenance records before
   implementing sensor fusion or applying legacy offsets.
4. Implement timestamp/age/validity cores using synthetic sources, preserving
   missing hip yaw and unknown native telemetry as first-class states.
5. Build a Dropbear host/ROS adapter against fake and synthetic backends only;
   keep the fail-only physical adapter as default.
6. Continue the independent CAD lane without making it block unrelated
   offline work or relaxing acceptance authority.
7. Add machine-readable unified gate summaries so reports need not reconstruct
   totals from console output.
