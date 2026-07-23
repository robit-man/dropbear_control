# ADR-008: Evidence-preserving CAD conversion and manual articulation review

- Status: Accepted
- Requirements: CAD-001..006, VER-005
- Work packages: WP-140, WP-150

## Decision

Preserve vendor ZIP/STEP and hashes; reproducibly derive reviewed housing and
output members, joint frames, GLB visual meshes, collision meshes and metadata.
Require rotation/immobility tests and provenance for inertial properties.
Flattened or ambiguously named geometry stays unsupported pending review or a
better source.

Canonical motor link geometry is right-handed and expressed in a shared link
frame whose joint origin is `[0,0,0]` and output axis is `+Z`. The reviewed
source-to-canonical rigid transform places the evidenced output-axis/reference-
plane intersection at that origin and maps the selected source positive axis to
`+Z`. Separate housing and output STEP derivatives retain millimetres; GLB
derivatives store metre coordinates explicitly. CAD zero is the vendor assembly
placement. Positive simulator articulation follows the right-hand rule about
`+Z`; the physical encoder/motor-to-joint sign remains a separate exact robot
configuration fact and cannot be inferred from geometry.

Automated names, topology, spatial clustering and pilot exports may create
review hypotheses, but those hypotheses must be labeled non-semantic and cannot
populate the accepted ledger. Acceptance still requires a reviewer to resolve
all externally relevant members, origin/reference plane and remaining
configuration-specific questions.

## Consequences

All 53 variants remain auditable while runtime formats are fit for purpose.
No automated segmentation result can self-approve; 44/44 model review is a
real P4 gate and output-shaft completion is currently 0/44.
