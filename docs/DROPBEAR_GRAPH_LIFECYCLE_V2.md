# Dropbear graph lifecycle and projections V2

Structured graph decisions use a second governance registry after source
selection. This prevents a reviewed graph from remaining silently active when
its source, graph submission or approval lifecycle changes.

## Graph registry

The graph registry consumes:

- one exact source-registry V2 generation;
- the graph V2 migration/status subject;
- graph submission envelopes containing complete reviewed V2 decisions; and
- globally ordered accept, reject, revoke and atomic supersede events.

At most one canonical graph submission can be accepted. An accepted decision
must have an active source submission, complete V1-to-V2 migration, a
semantically valid exact twelve-actuator graph and independent competent
mechanical review. A separate independent governance approver controls the
lifecycle event.

The tracked registry is empty. Synthetic tests prove acceptance, revocation
and supersession without placing those records in project evidence.

Relevant files:

- `schemas/dropbear-graph-submission-v2.schema.json`;
- `schemas/dropbear-graph-event-v2.schema.json`;
- `schemas/dropbear-graph-registry-v2.schema.json`;
- `assets/dropbear/graph_v2/`;
- `tools/manage_dropbear_graph_registry_v2.py`; and
- `generated/dropbear_graph_registry_v2/registry.json`.

## Consumer projections

Four V2 views share exact source/graph registry generations, lifecycle counts,
active identities, blockers and graph counts:

- host: frame, actuator and command-coordinate IDs;
- ROS: reviewed joint, coordinate and actuator mapping shape;
- simulator: graph, coupling and closure IDs;
- UI: redacted lifecycle and count-only status.

Positive graph shape does not materialize URDF, create a command handle, select
a physical plant, expose evidence/local paths, grant motor support or grant
motion. Those remain separate admissions.

The host consumer independently checks strict schemas, record and generation
digests, registry/projection hash parity, lifecycle counts, active identities,
output counts and browser redaction.

Relevant files:

- `schemas/dropbear-graph-lifecycle-projection-v2.schema.json`;
- `tools/generate_dropbear_graph_lifecycle_projections_v2.py`;
- `generated/dropbear_graph_lifecycle_projection_v2/`; and
- `host/myactuator_lib/dropbear_graph_lifecycle_v2.py`.

## Runtime revocation

`AdmissionSnapshot`, `SessionContext` and every `JointHandle` now bind both:

- `source_registry_generation_sha256`; and
- `graph_registry_generation_sha256`.

The hardware session checks a generation provider at configuration and before
every handle operation. A source revocation, graph revocation, supersession or
unavailable/malformed generation faults an active session, cancels pending
work and denies the operation. The generation token does not replace the
existing configuration, graph decision, lease, deadline, readiness or backend
checks.

## Commands

```sh
python3 tools/manage_dropbear_graph_registry_v2.py --generate
python3 tools/manage_dropbear_graph_registry_v2.py --check
python3 tools/generate_dropbear_graph_lifecycle_projections_v2.py --generate
python3 tools/generate_dropbear_graph_lifecycle_projections_v2.py --check
tests/dropbear_graph_registry_v2/run_tests.sh
tests/dropbear_graph_lifecycle_projection_v2/run_tests.sh
tests/dropbear_hardware_api/run_tests.sh
```

The tracked lifecycle states are source `absent`, graph `absent`, zero
canonical graphs and zero downstream mappings.
