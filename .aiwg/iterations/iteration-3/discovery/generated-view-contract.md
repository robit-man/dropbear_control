# Iteration 3 generated Dropbear view contract

- Delivery status: `COMPLETE-OFFLINE`
- Work package: WP-030-T05 offline generated-view steel thread
- Requirements: CFG-001..006, SYS-005, SAF-001, VER-001
- Canonical input: `schemas/examples/dropbear-observed-incomplete.json`
- Generator: `tools/generate_dropbear_views.py` version `1.0.0`
- Tracked output root: `generated/dropbear/`
- Evidence boundary: projection and compile evidence only; no physical, bench,
  HIL, CAD-articulation or enable claim

## Authority model

The reviewed canonical configuration is the sole configuration authority.
Generated files are deterministic, tracked projections for integration; they
cannot be edited into authority, fill missing facts or make the incomplete
observation enableable. Consumers must reject a view if its identity does not
match the active canonical digest and expected schema/config revision.

Generation proceeds only after all three gates pass:

1. `jsonschema.Draft202012Validator` checks the schema and configuration
   structure;
2. `schemas/validate_dropbear_config.py` checks cross-record references,
   uniqueness, ownership, exact tuple, provenance, alias, digest and safety
   semantics;
3. the declared canonical digest is independently recomputed and compared.

Failure occurs before a staging directory or destination replacement is
attempted.

## Common generated identity

Every JSON/YAML view and the manifest carries an identical
`generated_identity`; firmware exposes the same fields as typed constants.

| Field | Contract |
|---|---|
| `schema_version` | Canonical schema version; currently `1.0.0` |
| `configuration_id` | Stable canonical configuration identity |
| `configuration_revision` | Monotonic reviewed source revision |
| `configuration_state` | Preserved source state; currently `incomplete_observation` |
| `canonical_digest` | Canonical configuration SHA-256, never a generated-file hash |
| `source.*` | Stable config/schema/semantic-validator paths and file SHA-256 values |
| `tool.*` | Generator ID/version/path and generator source SHA-256 |

The manifest additionally records the path, byte length and SHA-256 for every
non-manifest generated artifact. The manifest does not recursively hash itself.

## Layer views and integration limits

| View | Format and consumer contract | Authority limits |
|---|---|---|
| Firmware | `firmware/dropbear_config.generated.hpp/.cpp`; C++17 structs/tables, identity constants, disabled static assertion and full canonical JSON byte payload | Compile-safe observation data only. It does not bind an ESP32 transport, grant a writer, derive a node ID or authorize native TX. Consumers must remain boot-disabled. |
| Host | canonical sorted/minified `host/dropbear_config.json` envelope | Input to typed host-device/config negotiation only. It cannot upgrade `unsupported`, manufacture SI limits or bypass gateway admission. |
| ROS | deterministic `ros/dropbear_config.yaml`, parsed equivalently to the canonical JSON envelope | Parameter/import input only. It is not a URDF, transmission, `ros2_control` hardware plugin or controller authorization. Aliases remain import-boundary data. |
| UI | canonical sorted/minified `ui/dropbear_config.json` envelope | Display/diagnostic projection only. UI controls may show blockers but cannot reinterpret unknowns or expose enable authority. |
| Simulator | canonical sorted/minified `simulator/dropbear_config.json` envelope | Registry seed only. It does not supply actuator plants, reviewed CAD output geometry, limits, calibrations or hardware evidence. Unknown dynamics remain unsupported. |
| Manifest | canonical sorted/minified `manifest.json` with generated identity and artifact hashes | Integrity/index metadata only; it does not sign, approve or release the configuration. |

JSON views and the ROS YAML carry the complete canonical registry rather than
a lossy layer-specific subset. `view_kind` is projection metadata outside the
registry. Equality tests prove the embedded `registry` value is exactly equal
to the canonical parsed JSON in every view.

## Preservation and fail-closed rules

The generator performs no defaulting or derivation. In particular it preserves:

- `legacy_full_command_can_id` as an observation and `native_node_id=null`;
- bus and actuator owner fields as null/unknown;
- motor model, hardware revision, drive firmware, protocol and control-mode
  fields as `UNKNOWN`;
- every exact tuple as `unsupported`;
- joint sign, ratio and numerical limits as null/unknown;
- calibration and CAD bindings as null/unknown;
- no enable authority and `motion_enable_allowed=false`.

The firmware header has `kMotionEnableAllowed=false` and a compile-time
`static_assert`. This protects the current incomplete source only; future
complete configurations still require runtime safety-state/config-hash
admission and cannot rely on a generated constant as a safety mechanism.

## Generation and check operations

Generate the tracked tree or an isolated candidate tree:

```bash
python3 tools/generate_dropbear_views.py
python3 tools/generate_dropbear_views.py --output-dir /tmp/dropbear-views
```

Check tracked bytes without creating, replacing, deleting or touching files:

```bash
python3 tools/generate_dropbear_views.py --check
```

Normal generation constructs every artifact in memory, writes a complete
sibling staging directory, moves an existing output tree to a sibling backup,
atomically renames the staged directory into place and restores the backup if
replacement fails. Stale files cannot survive successful replacement.
`--check` compares path sets and bytes directly and reports missing,
unexpected or mismatched artifacts without rewriting.

## Verification evidence

Run:

```bash
tests/config_views/run_tests.sh
```

The iteration-3 suite proves:

- tracked `--check` parity;
- identical identity and lossless registry equality across host, ROS, UI and
  simulator views;
- canonical JSON encoding and deterministic YAML parsing;
- preservation of all unknown/null/unverified/unsupported/disabled values;
- manifest byte counts and hashes;
- firmware C++17 compile, link and disabled runtime observation;
- byte-for-byte reproducibility across independent output directories;
- read-only check behavior for both matching and mismatched trees;
- staged replacement removes stale files;
- digest tamper rejection without changing an existing output;
- missing-required structural rejection before output creation;
- a rehashed but factually incomplete configuration cannot generate with
  motion enable set true.

## Current limitations and next Discovery items

- The tracked source is deliberately incomplete; these views are not yet wired
  into production firmware, host, ROS, UI or simulator runtime paths.
- Structural generation depends on installed `jsonschema` 4.10.3 and should be
  pinned by the repository dependency policy before release.
- Firmware output targets a portable C++17 core. ESP32 toolchain compilation
  and flash/RAM impact remain separate integration evidence.
- ROS YAML is a configuration projection, not a generated URDF/xacro or
  controller parameter release.
- No code-generation consumer may remove the config hash check or treat
  compilation as support evidence.
- Iteration 4 Discovery must define consumer adapters and mismatch tests before
  replacing any legacy constant; physical identity/topology, exact tuples,
  limits/calibration, CAD articulation and enable evidence remain upstream
  blockers.

