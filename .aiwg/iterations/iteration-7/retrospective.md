# Iteration 7 retrospective

## What worked

- Splitting local CAD authority from browser redistribution made every consumer
  fail closed without discarding useful vendor/candidate material.
- Treating Dropbear bindings as a refinement of an explicit exact selection
  exposed the V1 schema's missing geometry-configuration ID without inventing
  one.
- A model-complete empty plant registry proved more useful than populating
  family defaults: simulator gaps are now machine-readable and cannot be
  confused with the browser toy.
- Auditing the preserved firmware before integration prevented the canonical
  runtime from becoming a third physical command writer.
- Adding adapter failure feedback to the gateway closed the false response-slot
  state that otherwise followed a failed hardware send.

## What remains difficult

- Independent geometric semantics cannot be automated from names/renderings
  alone. The X12 packet is ready, but a human/mechanical reviewer must own the
  accept/amend/reject decision.
- The current Dropbear registry contains observations rather than installed
  motor identities, routes, limits or calibration. Generated views are useful
  for denial but not yet runtime tables.
- Real plant values are not present in the acquired vendor data. Identification
  procedures and measurement evidence are required; CAD cannot safely fill
  electrical, friction, thermal or control latency parameters.
- The user prototype firmware remains easy to compile but structurally unsafe
  to power. Replacing its writers must be staged and regression-driven, not a
  broad rewrite.

## Process changes for Iteration 8

1. Treat the independent X12 decision as an external input lane; continue
   non-CAD work without weakening the reviewer boundary.
2. Implement the Host Link V1 command-to-gateway translator as a pure native
   core so every field in the seam table becomes executable and fuzzable.
3. Add typed state/disposition translation back to Host Link V1 before any real
   serial task.
4. Define the exact ESP32 CAN adapter conformance harness and listen-only
   capture format before selecting or modifying MCP2515/TWAI code.
5. Build the generic deterministic actuator-plant engine against synthetic
   parameter fixtures while keeping all 44 real models unsupported.
6. Begin Dropbear canonical topology reconciliation independently of physical
   actuator enablement.
