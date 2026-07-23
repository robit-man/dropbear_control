# Dropbear robot-description source authority

The description inventory establishes what exists; it does not decide what is
authoritative. Iteration 10 adds a separate independent decision contract:

- schema:
  [`dropbear-source-authority-decision.schema.json`](../schemas/dropbear-source-authority-decision.schema.json);
- generated draft:
  [`templates/`](../generated/dropbear_source_authority/templates/);
- denial status:
  [`status.json`](../generated/dropbear_source_authority/status.json); and
- manager:
  [`manage_dropbear_source_authority.py`](../tools/manage_dropbear_source_authority.py).

## Decision subject

Every decision binds the exact Dropbear commit/tree, description inventory
path/schema/hash and canonical configuration digest. Its ID is derived from
that subject and its record digest covers every field.

Seven roles are decided separately:

1. kinematic tree;
2. visual geometry;
3. collision geometry;
4. inertial properties;
5. ROS 2 control;
6. Gazebo constraints; and
7. controller configuration.

A selected file carries its exact path, Git object ID, SHA-256, byte size,
logical key, package family and classification. Build/install derivatives
cannot be selected. A raw xacro/controller source is a `primary_source`; an
expanded URDF is admissible only with exact generator ID/version, argument
hash, source paths and evidence.

All 29 divergent logical groups appear in stable order. A submitted decision
must explicitly select one object, select multiple objects for distinct
roles, require amendment, reject the group, or declare it outside the selected
scope. Selected object IDs must agree exactly with role selections.

## Reviewer and completeness boundary

Drafts contain no reviewer, family policy, selection, divergence answer or
completeness claim. A submission requires an identified human reviewer/team,
independence attestation, UTC review time, assertion and signature evidence.
Automation/self-review identities are rejected.

Every role must be selected or explicitly unavailable. A complete review can
therefore remain runtime-incomplete when a required role is unavailable.
`accept_selection` requires all roles and divergence groups to be decided.
Source selection can never grant CAD support, motor/protocol applicability,
calibration, limits or physical motion authority.

## Current status and consumer

```bash
python3 tools/manage_dropbear_source_authority.py --check
tests/dropbear_source_authority/run_tests.sh
```

The generated V1 status is denial-only: seven roles unanswered, 29 divergent
groups unresolved, zero submitted/accepted/runtime-complete decisions, no
source authority, support false and motion false.

The host `DropbearSourceAuthorityStatus` rechecks the inventory and template
hashes, repository/config identity, exact role coverage and unpromoted draft
state. Exact role queries return blockers and no paths. Prefix, family, case
and generic `urdf` fallbacks do not exist.

A real human submission is intentionally not auto-promoted into V1. It must
be reviewed and admitted through a new positive status schema/gate so that
adding a file cannot silently change runtime authority.
