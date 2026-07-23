# Dropbear actuator readiness projection

The generated
[`readiness.json`](../generated/dropbear_readiness/readiness.json) is the
current exact per-actuator consumer boundary for Dropbear. It joins the
canonical 12-actuator configuration to pinned reconciliation observations,
the physical calibration registry and the physical limit registry. Every
input path and byte hash is recorded.

## Denial-only V1

Schema version `dropbear-readiness/1` is deliberately denial-only. Every
actuator has exactly these dependency categories:

1. canonical configuration identity;
2. installed actuator identity;
3. native protocol applicability;
4. exclusive runtime route;
5. physical calibration;
6. a complete applicable four-class limit set;
7. external feedback;
8. native telemetry;
9. a reviewed feedback-reconciliation policy;
10. an accepted CAD binding;
11. a reviewed ROS actuation mapping;
12. independent safe-power evidence; and
13. HIL evidence.

Only the canonical configuration identity is verified, and that verification
does not make the observed configuration complete or motion-capable. The ten
configured external sensors remain unverified observations. Both hip-yaw rows
preserve external feedback as missing rather than aliasing a neighboring
sensor.

The schema requires all installed tuples, routes, physical calibration IDs,
effective limit IDs, feedback policies, CAD bindings and ROS mappings to
remain absent. It also fixes per-actuator and global motion readiness to false.
Future positive readiness must use a new schema version with acceptance rules;
weakening V1 would be generated-evidence drift.

## Generation and consumption

```bash
python3 tools/generate_dropbear_readiness.py
tests/dropbear_readiness/run_tests.sh
```

The generator requires the canonical configuration digest to agree across all
four inputs and performs strict schema/semantic validation before writing its
exclusive output namespace. `--check` compares exact canonical bytes.

The host `DropbearReadinessRegistry` revalidates the schema, all source hashes,
unique exact actuator identities and complete dependency coverage on load.
Queries have no family, prefix or index fallback. `require_motion_ready()`
always returns the row's ordered denial in V1; the consumer exposes no
materialized route, calibration, limit or policy object.

This projection performs no hardware discovery and does not establish protocol
applicability, CAD support, calibration, limit, SIL, bench, HIL or robot
evidence.
