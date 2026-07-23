# Canonical Dropbear configuration handoff

## Delivered contract

| Artifact | Authority |
|---|---|
| `schemas/dropbear-config.schema.json` | Structural Draft 2020-12 contract |
| `schemas/validate_dropbear_config.py` | Dependency-free cross-record and fail-closed semantic checks; **not** a JSON Schema implementation |
| `schemas/examples/dropbear-observed-incomplete.json` | Migration observation only; deliberately non-enableable |
| `tests/schema/test_dropbear_config.py` | Executable invariants and regression evidence |

The canonical representation is JSON in this handoff so every check can run
with the Python standard library. A later reviewed YAML authoring surface may
compile into this JSON representation, but it must not introduce a second
authority or a non-deterministic hash.

## Observed facts retained

These are software-source observations at Dropbear commit
`13cf5ecaa39b8b89c794fe905dcea0490cfa7726`, not physical verification:

| Observation | Representation |
|---|---|
| Legacy sketch constants span full command identifiers `0x141` through `0x14C` | `address.legacy_full_command_can_id` values 321..332 with `unverified_observation` |
| Labels identify left/right outer calf, inner calf, knee, hip pitch, hip yaw and hip roll actuators | exactly six canonical semantic joints per leg |
| Runtime configuration has left/right chirality roles | two controller-role observations with unknown device identities and runtime node IDs |
| Sketch initializes an MCP2515 API at 1 Mbit/s and declares GPIO 5/17 | one unverified bus observation; physical topology and ownership remain unknown |
| Per leg role, source maps outer calf/inner calf/hip pitch/knee/hip roll to GPIO 14/27/26/25/33 | five external encoder observations per chirality role |
| No sampled external encoder is mapped to hip yaw | explicit `missing` external feedback on both hip-yaw joints |

The source also contains offset and constraint values, but this example does
not adopt them because their device identity, units, method, coordinate,
revision and physical validity are not established.

## Unknowns retained as blockers

- physical Dropbear hardware revision;
- controller identities, runtime node IDs, firmware and physical bus count;
- one-owner bus and actuator assignments;
- whether legacy full identifiers correspond to any specific native protocol
  addressing rule on installed drives;
- all 12 motor models, serials, hardware revisions, drive firmware, brakes,
  protocol revisions and admitted modes;
- motor-to-joint sign/ratio and sourced limits in motor/output coordinates;
- native feedback applicability, encoder calibration and hip-yaw feedback
  strategy;
- joint CAD assets, fixed housing/output members, origins and axes;
- independently verified power removal and any authorized enable identity.

Consequently all exact tuples are `unsupported`, bus/actuator owners are null,
native node IDs are null, calibrations/CAD bindings are absent and motion
enable is false.

## Identifier and naming rules

1. `legacy_full_command_can_id` is historical input. It is never silently
   converted into `native_node_id`.
2. Canonical names are the exact set
   `{left,right}_{hip_yaw,hip_roll,hip_pitch,knee,inner_calf,outer_calf}`.
3. Aliases live only in top-level `boundary_aliases`, include a named boundary
   and direction, and cannot become internal joint keys.
4. Controller stable IDs, runtime node IDs, bus IDs, actuator IDs, joint names,
   sensor IDs and known native node IDs are uniqueness checked.
5. An actuator owner must match the owner of its referenced bus. Unknown owner
   is legal only while the configuration stays disabled/incomplete.

## Exact-tuple and enable rules

Exact support is indexed by manufacturer, model, hardware revision, drive
firmware, protocol name/revision, transport and control mode. Wildcards are
invalid. Any `UNKNOWN` field forces `support_state=unsupported`.

Setting `motion_enable_allowed=true` is rejected unless independently computed
motion prerequisites are complete: reviewed robot/controller/bus identities,
single ownership, native addressing, bench-or-stronger exact tuple evidence,
coordinates, limits, calibration, feedback, CAD binding, enable authority,
independent power removal and a valid configuration digest. A declared
`complete_verified` flag cannot override missing evidence.

## Configuration hash

`json-sort-keys-utf8-omit-digest-v1` means:

1. deep-copy the JSON value;
2. remove only `/configuration_integrity/digest`;
3. serialize UTF-8 JSON with sorted object keys, no insignificant whitespace
   and non-ASCII preserved;
4. compute lowercase SHA-256.

Consumers must reject a generated view whose digest differs from the active
reviewed configuration. This iteration validates the hash but does not yet
generate firmware/host/ROS/UI/simulator views.

## Verification command

```bash
python3 schemas/validate_dropbear_config.py \
  schemas/examples/dropbear-observed-incomplete.json
tests/schema/run_tests.sh
```

The semantic CLI result explicitly reports
`json_schema_validation: not_performed` because that command has no
third-party runtime dependency. The test entry point separately uses installed
`jsonschema` 4.10.3 `Draft202012Validator` to check the schema and example,
including missing-required and additional-property negative cases. Production
CI must pin this structural dependency; semantic validation remains mandatory.
