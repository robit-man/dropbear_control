# Iteration 13 delivery implementation plan

Status: `COMPLETE-OFFLINE / G13.1-G13.8 SOFTWARE CLOSED`

## Vertical slices

1. Generate and independently consume a model-complete protocol-source and
   applicability denial registry.
2. Generate one reviewer campaign index over all 53 exact CAD configurations.
3. Generate a model-complete manual-fact/plant missing-evidence ledger.
4. Define canonical trace interchange and benchmark a generic rigid-body
   fixture without creating Dropbear fidelity.
5. Build a thin C++ ROS handoff over the tested semantic core.
6. Close packaging, traceability, critical artifact binding and the full gate.

## Exclusive namespaces

- `assets/myactuator/protocol_applicability/` — human submissions/decisions;
- `generated/myactuator/protocol_applicability/` — generated registry/status;
- `generated/myactuator/cad/campaign/` — generated campaign index;
- `generated/myactuator/plant/evidence_ledger/` — generated source-fact ledger;
- `generated/myactuator/rigid_body_benchmark/` — benchmark status;
- `host/myactuator_lib/protocol_applicability.py` — exact host consumer;
- `host/myactuator_lib/trace_interchange.py` — canonical trace contract; and
- `ros2_control/` — thin C++ plugin and ROS-free semantic handoff.

Generators do not write vendor sources, human submissions, current ESP32
runtime files, physical evidence or upstream Dropbear source.

## Implementation constraints

- Input hashes/generations are checked at generation and use time.
- Package placement is a candidate source relationship, never applicability.
- Unknown hardware/firmware stays absent and blocks exact decisions.
- Generated extraction cannot sign human review.
- Duplicate CAD bytes never merge source-package decision identity.
- Synthetic parameters and generic rigid fixtures stay outside real-model rows.
- The ROS handoff owns no native transport and cannot bypass the gateway.
