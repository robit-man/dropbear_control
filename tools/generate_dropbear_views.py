#!/usr/bin/env python3
"""Generate deterministic, non-authoritative Dropbear configuration views.

The canonical configuration remains the only reviewed authority.  Every input
is structurally validated as Draft 2020-12, semantically validated by the
existing dependency-free validator, and digest-checked before any output is
staged.  Generated views preserve the canonical data verbatim and may not
promote observations or fill unknown values.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator


# Dynamic loading of the read-only semantic validator must not create files
# beside canonical schema sources.
sys.dont_write_bytecode = True


TOOL_ID = "generate-dropbear-views"
TOOL_VERSION = "1.0.0"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "schemas/examples/dropbear-observed-incomplete.json"
DEFAULT_SCHEMA = REPO_ROOT / "schemas/dropbear-config.schema.json"
SEMANTIC_VALIDATOR_PATH = REPO_ROOT / "schemas/validate_dropbear_config.py"
DEFAULT_OUTPUT = REPO_ROOT / "generated/dropbear"
JSON_VIEW_KINDS = ("host", "ui", "simulator")


class GenerationError(RuntimeError):
    """An input or output failed the fail-closed generation contract."""


@dataclass(frozen=True)
class GenerationInputs:
    config_path: Path
    schema_path: Path
    config: dict[str, Any]
    identity: dict[str, Any]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _stable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GenerationError(f"cannot read {description} {path}: {error}") from error
    if not isinstance(value, dict):
        raise GenerationError(f"{description} root must be a JSON object: {path}")
    return value


def _load_semantic_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "dropbear_config_semantic_validator", SEMANTIC_VALIDATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise GenerationError(
            f"cannot load semantic validator: {SEMANTIC_VALIDATOR_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_inputs(config_path: Path, schema_path: Path) -> GenerationInputs:
    """Load and fully validate the canonical input before generation."""

    config_path = config_path.resolve()
    schema_path = schema_path.resolve()
    schema = _load_json(schema_path, "schema")
    config = _load_json(config_path, "configuration")

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as error:  # jsonschema exposes several schema error types.
        raise GenerationError(f"invalid Draft 2020-12 schema: {error}") from error
    structural_errors = sorted(
        Draft202012Validator(schema).iter_errors(config),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if structural_errors:
        rendered = " | ".join(
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
            for error in structural_errors
        )
        raise GenerationError(f"structural validation failed: {rendered}")

    semantic = _load_semantic_validator()
    semantic_issues = semantic.validate_config(config, verify_digest=True)
    if semantic_issues:
        rendered = " | ".join(issue.render() for issue in semantic_issues)
        raise GenerationError(f"semantic validation failed: {rendered}")

    declared_digest = config["configuration_integrity"]["digest"]
    computed_digest = semantic.canonical_digest(config)
    if declared_digest != computed_digest:
        raise GenerationError(
            f"canonical digest mismatch: declared={declared_digest}, "
            f"computed={computed_digest}"
        )

    identity = {
        "schema_version": config["schema_version"],
        "configuration_id": config["configuration_id"],
        "configuration_revision": config["configuration_revision"],
        "configuration_state": config["configuration_state"],
        "canonical_digest": declared_digest,
        "source": {
            "config_path": _stable_path(config_path),
            "config_file_sha256": _sha256_file(config_path),
            "schema_path": _stable_path(schema_path),
            "schema_file_sha256": _sha256_file(schema_path),
            "semantic_validator_path": _stable_path(SEMANTIC_VALIDATOR_PATH),
            "semantic_validator_sha256": _sha256_file(SEMANTIC_VALIDATOR_PATH),
        },
        "tool": {
            "tool_id": TOOL_ID,
            "tool_version": TOOL_VERSION,
            "tool_path": _stable_path(Path(__file__)),
            "tool_sha256": _sha256_file(Path(__file__)),
        },
    }
    return GenerationInputs(config_path, schema_path, config, identity)


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return json.dumps(value, allow_nan=False)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"unsupported YAML scalar: {type(value).__name__}")


def _is_scalar_or_empty(value: Any) -> bool:
    return not isinstance(value, (dict, list)) or not value


def _yaml_lines(value: Any, indent: int = 0) -> Iterable[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        if not value:
            yield prefix + "{}"
            return
        for key in sorted(value):
            child = value[key]
            rendered_key = json.dumps(str(key), ensure_ascii=False)
            if _is_scalar_or_empty(child):
                if isinstance(child, dict):
                    rendered_child = "{}"
                elif isinstance(child, list):
                    rendered_child = "[]"
                else:
                    rendered_child = _yaml_scalar(child)
                yield f"{prefix}{rendered_key}: {rendered_child}"
            else:
                yield f"{prefix}{rendered_key}:"
                yield from _yaml_lines(child, indent + 2)
    elif isinstance(value, list):
        if not value:
            yield prefix + "[]"
            return
        for child in value:
            if _is_scalar_or_empty(child):
                if isinstance(child, dict):
                    rendered_child = "{}"
                elif isinstance(child, list):
                    rendered_child = "[]"
                else:
                    rendered_child = _yaml_scalar(child)
                yield f"{prefix}- {rendered_child}"
            else:
                yield prefix + "-"
                yield from _yaml_lines(child, indent + 2)
    else:
        yield prefix + _yaml_scalar(value)


def _deterministic_yaml(value: Any) -> bytes:
    header = (
        "# Generated projection; the canonical configuration remains authoritative.\n"
    )
    return (header + "\n".join(_yaml_lines(value)) + "\n").encode("utf-8")


def _cpp_string(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError(f"C++ string requires str, got {type(value).__name__}")
    return json.dumps(value, ensure_ascii=True)


def _cpp_optional_string(value: Any) -> str:
    if value is None:
        return "{false, {}}"
    return "{true, " + _cpp_string(value) + "}"


def _cpp_optional_int(value: Any) -> str:
    if value is None:
        return "{false, 0}"
    return f"{{true, {int(value)}}}"


def _cpp_optional_double(value: Any) -> str:
    if value is None:
        return "{false, 0.0}"
    return "{true, " + repr(float(value)) + "}"


def _firmware_header(inputs: GenerationInputs) -> bytes:
    config = inputs.config
    identity = inputs.identity
    text = f"""// Generated by {TOOL_ID} {TOOL_VERSION}; DO NOT EDIT.
// Projection only: schemas/examples/dropbear-observed-incomplete.json remains authoritative.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace myactuator::generated::dropbear {{

struct OptionalString {{ bool has_value; std::string_view value; }};
struct OptionalInt32 {{ bool has_value; std::int32_t value; }};
struct OptionalDouble {{ bool has_value; double value; }};

struct JointObservation {{
  std::string_view canonical_name;
  std::string_view chirality;
  std::string_view semantic_joint;
  std::string_view actuator_id;
  OptionalInt32 motor_to_joint_sign;
  OptionalDouble output_per_motor_ratio;
  std::string_view coordinate_status;
  OptionalDouble position_lower_rad;
  OptionalDouble position_upper_rad;
  OptionalDouble max_velocity_rad_s;
  OptionalDouble max_qaxis_current_a;
  OptionalDouble max_effort_nm;
  OptionalDouble max_temperature_c;
  std::string_view limits_status;
  OptionalString external_sensor_id;
  std::string_view external_sensor_status;
  std::string_view native_drive_status;
  OptionalString calibration_id;
  std::string_view calibration_status;
  OptionalString cad_asset_id;
  std::string_view cad_status;
}};

struct ActuatorObservation {{
  std::string_view actuator_id;
  std::string_view canonical_joint_name;
  std::string_view chirality;
  std::string_view bus_id;
  OptionalString owner_controller_node_id;
  std::string_view ownership_status;
  OptionalInt32 legacy_full_command_can_id;
  OptionalInt32 native_node_id;
  std::string_view address_status;
  std::string_view manufacturer;
  std::string_view model;
  std::string_view hardware_revision;
  std::string_view drive_firmware;
  std::string_view protocol_name;
  std::string_view protocol_revision;
  std::string_view transport;
  std::string_view control_mode;
  std::string_view support_state;
}};

inline constexpr std::string_view kSchemaVersion = {_cpp_string(identity['schema_version'])};
inline constexpr std::string_view kConfigurationId = {_cpp_string(identity['configuration_id'])};
inline constexpr std::uint32_t kConfigurationRevision = {identity['configuration_revision']}U;
inline constexpr std::string_view kConfigurationState = {_cpp_string(identity['configuration_state'])};
inline constexpr std::string_view kCanonicalDigest = {_cpp_string(identity['canonical_digest'])};
inline constexpr std::string_view kSourceConfigPath = {_cpp_string(identity['source']['config_path'])};
inline constexpr std::string_view kSourceConfigFileSha256 = {_cpp_string(identity['source']['config_file_sha256'])};
inline constexpr std::string_view kSourceSchemaPath = {_cpp_string(identity['source']['schema_path'])};
inline constexpr std::string_view kSourceSchemaFileSha256 = {_cpp_string(identity['source']['schema_file_sha256'])};
inline constexpr std::string_view kSemanticValidatorPath = {_cpp_string(identity['source']['semantic_validator_path'])};
inline constexpr std::string_view kSemanticValidatorSha256 = {_cpp_string(identity['source']['semantic_validator_sha256'])};
inline constexpr std::string_view kGeneratorId = {_cpp_string(identity['tool']['tool_id'])};
inline constexpr std::string_view kGeneratorVersion = {_cpp_string(identity['tool']['tool_version'])};
inline constexpr std::string_view kGeneratorPath = {_cpp_string(identity['tool']['tool_path'])};
inline constexpr std::string_view kGeneratorSha256 = {_cpp_string(identity['tool']['tool_sha256'])};
inline constexpr bool kMotionEnableAllowed = {'true' if config['safety_admission']['motion_enable_allowed'] else 'false'};

extern const std::array<JointObservation, {len(config['joints'])}> kJoints;
extern const std::array<ActuatorObservation, {len(config['actuators'])}> kActuators;
extern const char kCanonicalRegistryJson[];
extern const std::size_t kCanonicalRegistryJsonSize;

static_assert(!kMotionEnableAllowed,
              "The observed incomplete Dropbear configuration must not enable motion");

}}  // namespace myactuator::generated::dropbear
"""
    return text.encode("utf-8")


def _firmware_source(inputs: GenerationInputs) -> bytes:
    config = inputs.config
    joint_rows: list[str] = []
    for joint in config["joints"]:
        actuation = joint["actuation"]
        limits = actuation["limits"]
        feedback = joint["feedback"]
        cad = joint["cad_binding"]
        fields = (
            _cpp_string(joint["canonical_name"]),
            _cpp_string(joint["chirality"]),
            _cpp_string(joint["semantic_joint"]),
            _cpp_string(joint["actuator_id"]),
            _cpp_optional_int(actuation["motor_to_joint_sign"]),
            _cpp_optional_double(actuation["output_per_motor_ratio"]),
            _cpp_string(actuation["coordinate_status"]),
            _cpp_optional_double(limits["position_lower_rad"]),
            _cpp_optional_double(limits["position_upper_rad"]),
            _cpp_optional_double(limits["max_velocity_rad_s"]),
            _cpp_optional_double(limits["max_qaxis_current_a"]),
            _cpp_optional_double(limits["max_effort_nm"]),
            _cpp_optional_double(limits["max_temperature_c"]),
            _cpp_string(limits["status"]),
            _cpp_optional_string(feedback["external_sensor_id"]),
            _cpp_string(feedback["external_sensor_status"]),
            _cpp_string(feedback["native_drive_status"]),
            _cpp_optional_string(joint["calibration_id"]),
            _cpp_string(joint["calibration_status"]),
            _cpp_optional_string(cad["asset_id"]),
            _cpp_string(cad["status"]),
        )
        joint_rows.append("  JointObservation{" + ", ".join(fields) + "},")

    actuator_rows: list[str] = []
    for actuator in config["actuators"]:
        address = actuator["address"]
        exact_tuple = actuator["exact_tuple"]
        fields = (
            _cpp_string(actuator["actuator_id"]),
            _cpp_string(actuator["canonical_joint_name"]),
            _cpp_string(actuator["chirality"]),
            _cpp_string(actuator["bus_id"]),
            _cpp_optional_string(actuator["owner_controller_node_id"]),
            _cpp_string(actuator["ownership_status"]),
            _cpp_optional_int(address["legacy_full_command_can_id"]),
            _cpp_optional_int(address["native_node_id"]),
            _cpp_string(address["status"]),
            _cpp_string(exact_tuple["manufacturer"]),
            _cpp_string(exact_tuple["model"]),
            _cpp_string(exact_tuple["hardware_revision"]),
            _cpp_string(exact_tuple["drive_firmware"]),
            _cpp_string(exact_tuple["protocol_name"]),
            _cpp_string(exact_tuple["protocol_revision"]),
            _cpp_string(exact_tuple["transport"]),
            _cpp_string(exact_tuple["control_mode"]),
            _cpp_string(exact_tuple["support_state"]),
        )
        actuator_rows.append("  ActuatorObservation{" + ", ".join(fields) + "},")

    registry_json = _canonical_json(config).decode("utf-8").rstrip("\n")
    raw_delimiter = "DROPCFG"
    if f"){raw_delimiter}\"" in registry_json:
        raise GenerationError("firmware raw-string delimiter collision")
    text = "\n".join(
        [
            f"// Generated by {TOOL_ID} {TOOL_VERSION}; DO NOT EDIT.",
            '#include "dropbear_config.generated.hpp"',
            "",
            "namespace myactuator::generated::dropbear {",
            "",
            f"const std::array<JointObservation, {len(joint_rows)}> kJoints = {{{{",
            *joint_rows,
            "}};",
            "",
            f"const std::array<ActuatorObservation, {len(actuator_rows)}> kActuators = {{{{",
            *actuator_rows,
            "}};",
            "",
            f'const char kCanonicalRegistryJson[] = R"{raw_delimiter}({registry_json}){raw_delimiter}";',
            "const std::size_t kCanonicalRegistryJsonSize =",
            "    sizeof(kCanonicalRegistryJson) - 1U;",
            "",
            "}  // namespace myactuator::generated::dropbear",
            "",
        ]
    )
    return text.encode("utf-8")


def build_outputs(inputs: GenerationInputs) -> dict[Path, bytes]:
    """Build every artifact entirely in memory before touching output."""

    outputs: dict[Path, bytes] = {}
    for view_kind in JSON_VIEW_KINDS:
        envelope = {
            "generated_identity": copy.deepcopy(inputs.identity),
            "registry": copy.deepcopy(inputs.config),
            "view_kind": view_kind,
        }
        outputs[Path(view_kind) / "dropbear_config.json"] = _canonical_json(envelope)

    ros_envelope = {
        "generated_identity": copy.deepcopy(inputs.identity),
        "registry": copy.deepcopy(inputs.config),
        "view_kind": "ros",
    }
    outputs[Path("ros/dropbear_config.yaml")] = _deterministic_yaml(ros_envelope)
    outputs[Path("firmware/dropbear_config.generated.hpp")] = _firmware_header(inputs)
    outputs[Path("firmware/dropbear_config.generated.cpp")] = _firmware_source(inputs)

    artifacts = [
        {
            "path": path.as_posix(),
            "sha256": _sha256_bytes(content),
            "bytes": len(content),
        }
        for path, content in sorted(outputs.items(), key=lambda item: item[0].as_posix())
    ]
    manifest = {
        "generated_identity": copy.deepcopy(inputs.identity),
        "artifacts": artifacts,
        "authority": "projection_only",
        "view_kind": "manifest",
    }
    outputs[Path("manifest.json")] = _canonical_json(manifest)
    return outputs


def _write_staging(staging: Path, outputs: Mapping[Path, bytes]) -> None:
    for relative_path, content in sorted(
        outputs.items(), key=lambda item: item[0].as_posix()
    ):
        destination = staging / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


def replace_output_atomically(output_dir: Path, outputs: Mapping[Path, bytes]) -> None:
    """Stage a complete tree and transactionally replace the output directory."""

    output_dir = output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    backup = output_dir.parent / f".{output_dir.name}.backup-{os.getpid()}"
    try:
        _write_staging(staging, outputs)
        if backup.exists():
            shutil.rmtree(backup)
        if output_dir.exists():
            os.replace(output_dir, backup)
        try:
            os.replace(staging, output_dir)
        except BaseException:
            if backup.exists() and not output_dir.exists():
                os.replace(backup, output_dir)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup.exists() and output_dir.exists():
            shutil.rmtree(backup)


def check_output(output_dir: Path, outputs: Mapping[Path, bytes]) -> list[str]:
    """Compare expected bytes without creating, deleting, or rewriting files."""

    output_dir = output_dir.resolve()
    problems: list[str] = []
    expected_paths = {path.as_posix() for path in outputs}
    actual_paths = (
        {
            path.relative_to(output_dir).as_posix()
            for path in output_dir.rglob("*")
            if path.is_file()
        }
        if output_dir.exists()
        else set()
    )
    for missing in sorted(expected_paths - actual_paths):
        problems.append(f"missing: {missing}")
    for extra in sorted(actual_paths - expected_paths):
        problems.append(f"unexpected: {extra}")
    for relative_path in sorted(expected_paths & actual_paths):
        expected = outputs[Path(relative_path)]
        actual = (output_dir / relative_path).read_bytes()
        if actual != expected:
            problems.append(
                f"mismatch: {relative_path} "
                f"expected={_sha256_bytes(expected)} actual={_sha256_bytes(actual)}"
            )
    return problems


def generate(
    config_path: Path,
    schema_path: Path,
    output_dir: Path,
    *,
    check: bool,
) -> list[str]:
    inputs = validate_inputs(config_path, schema_path)
    outputs = build_outputs(inputs)
    if check:
        return check_output(output_dir, outputs)
    replace_output_atomically(output_dir, outputs)
    return []


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare expected generated bytes without modifying output",
    )
    arguments = parser.parse_args(argv)
    try:
        problems = generate(
            arguments.config,
            arguments.schema,
            arguments.output_dir,
            check=arguments.check,
        )
    except (GenerationError, OSError) as error:
        print(f"dropbear view generation failed: {error}", file=sys.stderr)
        return 2
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    action = "checked" if arguments.check else "generated"
    print(
        json.dumps(
            {
                "action": action,
                "config": _stable_path(arguments.config),
                "output_dir": _stable_path(arguments.output_dir),
                "status": "ok",
                "tool": f"{TOOL_ID}/{TOOL_VERSION}",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
