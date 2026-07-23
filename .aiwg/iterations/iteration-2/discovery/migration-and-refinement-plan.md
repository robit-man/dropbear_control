# Dropbear configuration migration and refinement plan

## Migration rule

Legacy data enters an observation layer first. It becomes runtime authority
only after its exact physical subject, units, coordinate, source revision and
review evidence are established. Conflicting observations are retained and
resolved explicitly; the migration never chooses a convenient value silently.

## Dependency-ordered stages

| Stage | Work | Inputs | Exit / evidence | Enable effect |
|---|---|---|---|---|
| M0 — observation freeze | Preserve legacy identifiers, labels, chirality roles and sensor channels | pinned Dropbear source/audit | current incomplete example and digest | disabled |
| M1 — passive physical inventory | Record robot revision, controller labels/MACs, motor labels/serials, brake variants, wiring, termination and independent cut without commanding motors | approved inspection procedure; SRC-016 template | reviewed photos/records with UTC/operator | disabled |
| M2 — topology and ownership | Name physical buses, controller runtime IDs and exactly one owner for each bus/actuator | M1 | topology diagram and peer-reviewed one-owner table | disabled |
| M3 — exact tuple resolution | Join each installed motor to catalog model, hardware/firmware, protocol revision, transport and candidate modes | M1/M2; official manuals | 12 exact support records; no wildcard | disabled unless later bench evidence exists |
| M4 — coordinates, limits and sensing | Resolve sign, ratio, hard/soft limits, native/external feedback, hip-yaw sensing decision and calibration method | M2/M3; mechanical review | per-joint unit/provenance records and calibration plan | disabled |
| M5 — CAD/description reconciliation | Select canonical Dropbear description and bind reviewed housing/output geometry, origins and axes | M3/M4; WP-120/140 | joint parity and asset review records | disabled |
| M6 — generated views | Compile firmware/host/ROS/UI/simulator views from one accepted config and embed its digest | M2..M5 | clean reproducible generation plus parity tests | disabled on any mismatch |
| M7 — admission evidence | Validate independent cut, authority policy, safe action and exact-tuple prerequisites under approved bench/HIL procedures | M3..M6; WP-100/170 | signed gate evidence | only the safety gate may change enable policy |

## Refinement decisions required

1. Decide whether physical Dropbear has one shared CAN segment, one segment per
   leg, or another topology. The single bus in the example is only a software
   observation container.
2. Decide how controller runtime identity is established and signed; chirality
   alone cannot grant ownership.
3. Review whether each historical `0x14x` value is a full command identifier,
   configured actuator ID or another convention for the installed tuple.
4. Select the canonical detailed/simplified Dropbear description source before
   mapping CAD-style joint names.
5. Define native versus external feedback arbitration and an explicit hip-yaw
   observability policy.
6. Define calibration records/transactions before importing any legacy offset
   or direction multiplier.
7. Pin a Draft 2020-12 validator for structural CI or implement/review the
   necessary structural subset; do not mislabel semantic-only validation.
8. Specify generated-view schemas and hash mismatch behavior before replacing
   legacy constants.

## Conflict and rollback policy

- Physical label/firmware evidence outranks legacy symbol names but does not
  by itself prove protocol behavior.
- Applicable official manual clauses outrank comments, while actual captures
  may reveal a discrepancy that must be quarantined rather than overwritten.
- A reviewed calibration is bound to device, joint and configuration revision;
  it is invalidated by identity or coordinate changes.
- Any source, tuple, config, firmware, CAD or calibration revision change marks
  dependent generated views/evidence stale and forces motion admission false.
- Migrations are additive and reviewable; the legacy prototype remains a
  regression source and is not rewritten in place.

