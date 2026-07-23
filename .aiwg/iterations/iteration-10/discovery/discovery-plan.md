# Iteration 11 discovery plan — unpowered installed identity and physical adapter readiness

Status: `READY-FOR-HUMAN-REVIEW-NOT-AUTHORIZED-FOR-EXECUTION`

## Target handoff

Prepare a reviewable, authorization-aware package for unpowered discovery.
Nothing in this discovery track permits connecting to, powering, transmitting
to or moving the robot.

## Workstreams

### Installed identity

- Define exact robot revision, controller PCB/serial, transceiver, bus,
  connector, motor/drive serial, model/hardware/firmware, protocol revision,
  native node and brake observations.
- Bind tool/operator/time/photo/log hashes and distinguish observed,
  read-from-device and manually transcribed values.
- Define duplicate node, conflicting serial, inaccessible label and unknown
  applicability dispositions.

### ESP32 CAN path

- Inventory actual board/controller/transceiver/pins/clock/termination facts.
- Compare native TWAI and external MCP2515 capabilities for 1-Mbit/s timing,
  standard filters, timestamps, loss/overflow, error-passive/bus-off and
  physically enforced listen-only.
- Require a reviewed decision; library popularity or current include files do
  not select hardware.

### Listen-only evidence

- Draft isolation, power, termination, ground and TX-disable preconditions.
- Define operator/reviewer roles, abort conditions, capture duration/load,
  timestamp/loss acceptance and file custody.
- Keep capture observations separate from protocol applicability and support.

### Safety and staged campaigns

- Document independent power-removal survey and measurement plan.
- Prepare calibration/limit templates for one constrained actuator at a time.
- Define HIL progression and injected host/bus/drive/sensor/limit faults.
- List explicit approvals required before each physical phase.

### CAD and plant evidence

- Prioritize output-member review cohorts using assembly/flattened status and
  Dropbear installation relevance.
- Define re-source/heal requirements for shell-only or inseparable variants.
- Define real plant parameter source, uncertainty, envelope and correlation
  acceptance without extracting dynamics from STEP geometry.

## Definition of Ready

- schemas/runbooks/templates are strict and tested with synthetic examples;
- every physical step identifies owner, reviewer, prerequisites, abort and
  evidence output;
- controller selection unknowns are explicit;
- no command-capable path is enabled;
- the user can review and authorize one bounded unpowered campaign without
  granting later powered phases implicitly.

All Definition-of-Ready artifacts are now hash-bound by
`generated/dropbear_unpowered_discovery/status.json`. The installed template
has twelve exact unobserved slots; submitted inventories, selected CAN
controllers and authorized actions remain zero.
