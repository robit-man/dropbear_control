#!/usr/bin/env python3
"""Deterministic semantic checks for a canonical Dropbear configuration.

This module deliberately uses only the Python standard library.  It is not a
JSON Schema implementation and does not claim Draft 2020-12 structural
validation.  The companion ``dropbear-config.schema.json`` is the structural
contract; this validator implements cross-record and fail-closed invariants
that JSON Schema alone cannot express conveniently.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "1.0.0"
CANONICAL_JOINTS = frozenset(
    f"{side}_{semantic}"
    for side in ("left", "right")
    for semantic in (
        "hip_yaw",
        "hip_roll",
        "hip_pitch",
        "knee",
        "inner_calf",
        "outer_calf",
    )
)
EXACT_TUPLE_FIELDS = (
    "manufacturer",
    "model",
    "hardware_revision",
    "drive_firmware",
    "protocol_name",
    "protocol_revision",
    "transport",
    "control_mode",
)
MOTION_EVIDENCE_STATES = frozenset(
    {"bench_validated", "hil_validated", "robot_released"}
)
ALIAS_KEYS = frozenset({"alias", "aliases", "legacy_name", "legacy_names"})


@dataclass(frozen=True, order=True)
class ValidationIssue:
    """One stable validation result."""

    code: str
    path: str
    message: str

    def render(self) -> str:
        return f"{self.code} {self.path}: {self.message}"


def canonical_digest(config: Mapping[str, Any]) -> str:
    """Return the v1 digest, omitting only the digest field itself."""

    canonical = copy.deepcopy(dict(config))
    integrity = canonical.get("configuration_integrity")
    if isinstance(integrity, dict):
        integrity.pop("digest", None)
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def set_canonical_digest(config: dict[str, Any]) -> str:
    """Set and return the canonical digest; useful to tooling and tests."""

    digest = canonical_digest(config)
    config.setdefault("configuration_integrity", {})["digest"] = digest
    return digest


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _add(
    issues: list[ValidationIssue], code: str, path: str, message: str
) -> None:
    issues.append(ValidationIssue(code, path, message))


def _check_unique(
    records: Sequence[Any],
    field: str,
    path: str,
    code: str,
    issues: list[ValidationIssue],
    *,
    allow_null: bool = False,
) -> None:
    seen: dict[Any, int] = {}
    for index, candidate in enumerate(records):
        record = _mapping(candidate)
        value = record.get(field)
        if value is None and allow_null:
            continue
        if value is None:
            _add(issues, code, f"{path}/{index}/{field}", "value is required")
            continue
        if value in seen:
            _add(
                issues,
                code,
                f"{path}/{index}/{field}",
                f"duplicate {value!r}; first seen at index {seen[value]}",
            )
        else:
            seen[value] = index


def _walk_alias_leaks(value: Any, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            in_boundary_record = path.startswith("/boundary_aliases/")
            if key in ALIAS_KEYS and not in_boundary_record:
                yield child_path, key
            yield from _walk_alias_leaks(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_alias_leaks(child, f"{path}/{index}")


def _is_wildcard(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().upper()
    return (
        normalized in {"ANY", "ALL", "WILDCARD"}
        or any(character in value for character in "*?[]")
    )


def _unknown(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.upper() == "UNKNOWN")


def _source_refs(value: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if key == "source_refs":
                for index, ref in enumerate(_sequence(child)):
                    yield f"{child_path}/{index}", ref
            else:
                yield from _source_refs(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _source_refs(child, f"{path}/{index}")


def _motion_blockers(config: Mapping[str, Any], digest_valid: bool) -> list[str]:
    """Compute motion-admission blockers independently of declared state."""

    blockers: list[str] = []
    robot = _mapping(config.get("robot"))
    nodes = _sequence(config.get("controller_nodes"))
    buses = _sequence(config.get("buses"))
    joints = _sequence(config.get("joints"))
    actuators = _sequence(config.get("actuators"))
    calibrations = {
        item.get("calibration_id"): item
        for item in map(_mapping, _sequence(config.get("calibrations")))
        if item.get("calibration_id") is not None
    }
    cad_assets = {
        item.get("asset_id"): item
        for item in map(_mapping, _sequence(config.get("cad_assets")))
        if item.get("asset_id") is not None
    }
    safety = _mapping(config.get("safety_admission"))

    if config.get("configuration_state") != "complete_verified":
        blockers.append("configuration_state is not complete_verified")
    if (
        _unknown(robot.get("hardware_revision"))
        or robot.get("hardware_revision_status") != "verified"
    ):
        blockers.append("robot hardware revision is not verified")
    if not nodes:
        blockers.append("no controller nodes are defined")
    for node in map(_mapping, nodes):
        node_id = node.get("controller_node_id", "<unknown>")
        if (
            node.get("identity_status") != "verified"
            or not isinstance(node.get("runtime_node_id"), int)
            or _unknown(node.get("hardware_identity"))
            or _unknown(node.get("firmware_revision"))
        ):
            blockers.append(f"controller node {node_id} identity is incomplete")
    for bus in map(_mapping, buses):
        bus_id = bus.get("bus_id", "<unknown>")
        if (
            bus.get("ownership_status") != "verified"
            or bus.get("owner_controller_node_id") is None
        ):
            blockers.append(f"bus {bus_id} ownership is not verified")
        if bus.get("timing_status") != "verified" or not isinstance(
            bus.get("bitrate_bps"), int
        ):
            blockers.append(f"bus {bus_id} timing is not verified")
    for actuator in map(_mapping, actuators):
        actuator_id = actuator.get("actuator_id", "<unknown>")
        address = _mapping(actuator.get("address"))
        exact_tuple = _mapping(actuator.get("exact_tuple"))
        if (
            actuator.get("ownership_status") != "verified"
            or actuator.get("owner_controller_node_id") is None
        ):
            blockers.append(f"actuator {actuator_id} ownership is not verified")
        if address.get("status") != "verified" or not isinstance(
            address.get("native_node_id"), int
        ):
            blockers.append(f"actuator {actuator_id} native address is not verified")
        if any(_unknown(exact_tuple.get(field)) for field in EXACT_TUPLE_FIELDS):
            blockers.append(f"actuator {actuator_id} exact tuple is incomplete")
        if exact_tuple.get("support_state") not in MOTION_EVIDENCE_STATES:
            blockers.append(f"actuator {actuator_id} lacks bench-or-stronger evidence")
    for joint in map(_mapping, joints):
        joint_name = joint.get("canonical_name", "<unknown>")
        actuation = _mapping(joint.get("actuation"))
        limits = _mapping(actuation.get("limits"))
        feedback = _mapping(joint.get("feedback"))
        cad_binding = _mapping(joint.get("cad_binding"))
        if (
            actuation.get("coordinate_status") != "verified"
            or actuation.get("motor_to_joint_sign") not in {-1, 1}
            or not isinstance(actuation.get("output_per_motor_ratio"), (int, float))
        ):
            blockers.append(f"joint {joint_name} actuation coordinates are incomplete")
        limit_fields = (
            "position_lower_rad",
            "position_upper_rad",
            "max_velocity_rad_s",
            "max_qaxis_current_a",
            "max_temperature_c",
        )
        if limits.get("status") != "verified" or any(
            limits.get(field) is None for field in limit_fields
        ):
            blockers.append(f"joint {joint_name} required limits are incomplete")
        lower = limits.get("position_lower_rad")
        upper = limits.get("position_upper_rad")
        if isinstance(lower, (int, float)) and isinstance(upper, (int, float)):
            if lower >= upper:
                blockers.append(f"joint {joint_name} position limits are not ordered")
        calibration_id = joint.get("calibration_id")
        calibration = _mapping(calibrations.get(calibration_id))
        if (
            joint.get("calibration_status") != "verified"
            or not calibration_id
            or calibration.get("status") != "verified"
        ):
            blockers.append(f"joint {joint_name} calibration is not verified")
        if feedback.get("native_drive_status") != "verified" and feedback.get(
            "external_sensor_status"
        ) != "verified":
            blockers.append(f"joint {joint_name} has no verified feedback source")
        asset_id = cad_binding.get("asset_id")
        asset = _mapping(cad_assets.get(asset_id))
        if (
            cad_binding.get("status") != "verified"
            or not asset_id
            or asset.get("review_status") != "verified"
        ):
            blockers.append(f"joint {joint_name} CAD binding is not verified")
    if safety.get("enable_authority_status") != "verified" or not safety.get(
        "enable_authority_id"
    ):
        blockers.append("enable authority is not verified")
    if safety.get("independent_power_removal_status") != "verified":
        blockers.append("independent power-removal path is not verified")
    if not digest_valid:
        blockers.append("configuration digest is invalid")
    return blockers


def validate_config(config: Any, *, verify_digest: bool = True) -> list[ValidationIssue]:
    """Validate cross-record semantics and return a stable sorted issue list."""

    issues: list[ValidationIssue] = []
    if not isinstance(config, dict):
        return [
            ValidationIssue("E_ROOT_TYPE", "/", "configuration root must be an object")
        ]

    required_collections = (
        "controller_nodes",
        "buses",
        "joints",
        "actuators",
        "sensors",
        "cad_assets",
        "calibrations",
        "boundary_aliases",
        "provenance_sources",
    )
    if config.get("schema_version") != SCHEMA_VERSION:
        _add(
            issues,
            "E_SCHEMA_VERSION",
            "/schema_version",
            f"expected {SCHEMA_VERSION!r}",
        )
    for field in required_collections:
        if not isinstance(config.get(field), list):
            _add(issues, "E_STRUCTURE", f"/{field}", "must be an array")

    nodes = _sequence(config.get("controller_nodes"))
    buses = _sequence(config.get("buses"))
    joints = _sequence(config.get("joints"))
    actuators = _sequence(config.get("actuators"))
    sensors = _sequence(config.get("sensors"))
    cad_assets = _sequence(config.get("cad_assets"))
    calibrations = _sequence(config.get("calibrations"))
    aliases = _sequence(config.get("boundary_aliases"))
    sources = _sequence(config.get("provenance_sources"))

    _check_unique(
        nodes,
        "controller_node_id",
        "/controller_nodes",
        "E_CONTROLLER_ID_DUPLICATE",
        issues,
    )
    _check_unique(
        nodes,
        "runtime_node_id",
        "/controller_nodes",
        "E_RUNTIME_NODE_ID_DUPLICATE",
        issues,
        allow_null=True,
    )
    _check_unique(buses, "bus_id", "/buses", "E_BUS_ID_DUPLICATE", issues)
    _check_unique(
        joints,
        "canonical_name",
        "/joints",
        "E_JOINT_NAME_DUPLICATE",
        issues,
    )
    _check_unique(
        actuators,
        "actuator_id",
        "/actuators",
        "E_ACTUATOR_ID_DUPLICATE",
        issues,
    )
    _check_unique(
        actuators,
        "canonical_joint_name",
        "/actuators",
        "E_ACTUATOR_JOINT_DUPLICATE",
        issues,
    )
    _check_unique(sensors, "sensor_id", "/sensors", "E_SENSOR_ID_DUPLICATE", issues)
    _check_unique(cad_assets, "asset_id", "/cad_assets", "E_CAD_ID_DUPLICATE", issues)
    _check_unique(
        calibrations,
        "calibration_id",
        "/calibrations",
        "E_CALIBRATION_ID_DUPLICATE",
        issues,
    )
    _check_unique(sources, "source_id", "/provenance_sources", "E_SOURCE_ID_DUPLICATE", issues)

    joint_records = {
        record.get("canonical_name"): record
        for record in map(_mapping, joints)
        if record.get("canonical_name") is not None
    }
    actual_joints = set(joint_records)
    if actual_joints != CANONICAL_JOINTS:
        missing = sorted(CANONICAL_JOINTS - actual_joints)
        extra = sorted(actual_joints - CANONICAL_JOINTS)
        _add(
            issues,
            "E_CANONICAL_JOINT_SET",
            "/joints",
            f"expected exact two-leg semantic set; missing={missing}, extra={extra}",
        )
    for index, joint in enumerate(map(_mapping, joints)):
        expected = f"{joint.get('chirality')}_{joint.get('semantic_joint')}"
        if joint.get("canonical_name") != expected:
            _add(
                issues,
                "E_CANONICAL_JOINT_FORM",
                f"/joints/{index}/canonical_name",
                f"expected {expected!r} from chirality and semantic_joint",
            )

    for path, key in _walk_alias_leaks(config):
        _add(
            issues,
            "E_ALIAS_OUTSIDE_BOUNDARY",
            path,
            f"{key!r} is permitted only in /boundary_aliases records",
        )
    alias_keys: dict[tuple[Any, Any], int] = {}
    for index, alias in enumerate(map(_mapping, aliases)):
        key = (alias.get("boundary"), alias.get("alias"))
        if key in alias_keys:
            _add(
                issues,
                "E_ALIAS_DUPLICATE",
                f"/boundary_aliases/{index}",
                f"duplicate boundary alias; first seen at index {alias_keys[key]}",
            )
        else:
            alias_keys[key] = index
        if alias.get("canonical_name") not in CANONICAL_JOINTS:
            _add(
                issues,
                "E_ALIAS_TARGET",
                f"/boundary_aliases/{index}/canonical_name",
                "alias target is not a canonical Dropbear joint",
            )
        if alias.get("alias") in CANONICAL_JOINTS:
            _add(
                issues,
                "E_ALIAS_REDUNDANT",
                f"/boundary_aliases/{index}/alias",
                "canonical names must be used directly, not registered as aliases",
            )

    node_ids = {
        item.get("controller_node_id") for item in map(_mapping, nodes)
    }
    bus_records = {
        item.get("bus_id"): item
        for item in map(_mapping, buses)
        if item.get("bus_id") is not None
    }
    for index, bus in enumerate(map(_mapping, buses)):
        owner = bus.get("owner_controller_node_id")
        if owner is not None and owner not in node_ids:
            _add(
                issues,
                "E_BUS_OWNER_REFERENCE",
                f"/buses/{index}/owner_controller_node_id",
                f"unknown controller node {owner!r}",
            )
        if owner is None and bus.get("ownership_status") == "verified":
            _add(
                issues,
                "E_BUS_OWNER_STATUS",
                f"/buses/{index}/ownership_status",
                "verified ownership requires exactly one owner_controller_node_id",
            )

    actuator_records = {
        item.get("actuator_id"): item
        for item in map(_mapping, actuators)
        if item.get("actuator_id") is not None
    }
    actuator_joint_records = {
        item.get("canonical_joint_name"): item
        for item in map(_mapping, actuators)
        if item.get("canonical_joint_name") is not None
    }
    native_addresses: dict[tuple[Any, Any], int] = {}
    legacy_addresses: dict[tuple[Any, Any], int] = {}
    for index, actuator in enumerate(map(_mapping, actuators)):
        joint_name = actuator.get("canonical_joint_name")
        bus_id = actuator.get("bus_id")
        bus = _mapping(bus_records.get(bus_id))
        owner = actuator.get("owner_controller_node_id")
        if joint_name not in CANONICAL_JOINTS:
            _add(
                issues,
                "E_ACTUATOR_JOINT_REFERENCE",
                f"/actuators/{index}/canonical_joint_name",
                f"unknown canonical joint {joint_name!r}",
            )
        if bus_id not in bus_records:
            _add(
                issues,
                "E_ACTUATOR_BUS_REFERENCE",
                f"/actuators/{index}/bus_id",
                f"unknown bus {bus_id!r}",
            )
        if owner is not None and owner not in node_ids:
            _add(
                issues,
                "E_ACTUATOR_OWNER_REFERENCE",
                f"/actuators/{index}/owner_controller_node_id",
                f"unknown controller node {owner!r}",
            )
        if owner is None and actuator.get("ownership_status") == "verified":
            _add(
                issues,
                "E_ACTUATOR_OWNER_STATUS",
                f"/actuators/{index}/ownership_status",
                "verified ownership requires exactly one owner_controller_node_id",
            )
        bus_owner = bus.get("owner_controller_node_id")
        if owner is not None and bus_owner is not None and owner != bus_owner:
            _add(
                issues,
                "E_ACTUATOR_OWNER_MISMATCH",
                f"/actuators/{index}/owner_controller_node_id",
                f"actuator owner {owner!r} differs from bus owner {bus_owner!r}",
            )
        address = _mapping(actuator.get("address"))
        for address_field, seen, code in (
            (
                "native_node_id",
                native_addresses,
                "E_NATIVE_NODE_ID_DUPLICATE",
            ),
            (
                "legacy_full_command_can_id",
                legacy_addresses,
                "E_LEGACY_CAN_ID_DUPLICATE",
            ),
        ):
            address_value = address.get(address_field)
            if address_value is not None:
                key = (bus_id, address_value)
                if key in seen:
                    _add(
                        issues,
                        code,
                        f"/actuators/{index}/address/{address_field}",
                        f"duplicate address {address_value!r} on bus {bus_id!r}; first seen at actuator index {seen[key]}",
                    )
                else:
                    seen[key] = index
        exact_tuple = _mapping(actuator.get("exact_tuple"))
        for field in EXACT_TUPLE_FIELDS:
            value = exact_tuple.get(field)
            if _is_wildcard(value):
                _add(
                    issues,
                    "E_TUPLE_WILDCARD",
                    f"/actuators/{index}/exact_tuple/{field}",
                    "wildcards are forbidden in exact support tuples",
                )
        if any(_unknown(exact_tuple.get(field)) for field in EXACT_TUPLE_FIELDS):
            if exact_tuple.get("support_state") != "unsupported":
                _add(
                    issues,
                    "E_UNKNOWN_TUPLE_SUPPORTED",
                    f"/actuators/{index}/exact_tuple/support_state",
                    "any UNKNOWN exact-tuple field forces support_state=unsupported",
                )

    for index, joint in enumerate(map(_mapping, joints)):
        actuator_id = joint.get("actuator_id")
        actuator = _mapping(actuator_records.get(actuator_id))
        if actuator_id not in actuator_records:
            _add(
                issues,
                "E_JOINT_ACTUATOR_REFERENCE",
                f"/joints/{index}/actuator_id",
                f"unknown actuator {actuator_id!r}",
            )
        elif actuator.get("canonical_joint_name") != joint.get("canonical_name"):
            _add(
                issues,
                "E_JOINT_ACTUATOR_MISMATCH",
                f"/joints/{index}/actuator_id",
                "joint and actuator mappings are not reciprocal",
            )
    if set(actuator_joint_records) != CANONICAL_JOINTS:
        _add(
            issues,
            "E_ACTUATOR_JOINT_SET",
            "/actuators",
            "actuators must map one-to-one onto the twelve canonical joints",
        )

    sensor_records = {
        item.get("sensor_id"): item
        for item in map(_mapping, sensors)
        if item.get("sensor_id") is not None
    }
    external_joint_sensors: dict[Any, int] = {}
    for index, sensor in enumerate(map(_mapping, sensors)):
        joint_name = sensor.get("canonical_joint_name")
        controller_node_id = sensor.get("controller_node_id")
        if joint_name is not None and joint_name not in CANONICAL_JOINTS:
            _add(
                issues,
                "E_SENSOR_JOINT_REFERENCE",
                f"/sensors/{index}/canonical_joint_name",
                f"unknown canonical joint {joint_name!r}",
            )
        if controller_node_id is not None and controller_node_id not in node_ids:
            _add(
                issues,
                "E_SENSOR_NODE_REFERENCE",
                f"/sensors/{index}/controller_node_id",
                f"unknown controller node {controller_node_id!r}",
            )
        if sensor.get("sensor_type") == "external_absolute_encoder":
            if joint_name in external_joint_sensors:
                _add(
                    issues,
                    "E_EXTERNAL_SENSOR_DUPLICATE",
                    f"/sensors/{index}/canonical_joint_name",
                    f"second external encoder for {joint_name!r}; first at index {external_joint_sensors[joint_name]}",
                )
            else:
                external_joint_sensors[joint_name] = index
    for index, joint in enumerate(map(_mapping, joints)):
        feedback = _mapping(joint.get("feedback"))
        sensor_id = feedback.get("external_sensor_id")
        sensor = _mapping(sensor_records.get(sensor_id))
        if sensor_id is None:
            if feedback.get("external_sensor_status") not in {"missing", "unknown"}:
                _add(
                    issues,
                    "E_FEEDBACK_SENSOR_STATUS",
                    f"/joints/{index}/feedback/external_sensor_status",
                    "a non-existent sensor cannot be observed or verified",
                )
        elif sensor_id not in sensor_records:
            _add(
                issues,
                "E_FEEDBACK_SENSOR_REFERENCE",
                f"/joints/{index}/feedback/external_sensor_id",
                f"unknown sensor {sensor_id!r}",
            )
        elif sensor.get("canonical_joint_name") != joint.get("canonical_name"):
            _add(
                issues,
                "E_FEEDBACK_SENSOR_MISMATCH",
                f"/joints/{index}/feedback/external_sensor_id",
                "sensor and joint mappings are not reciprocal",
            )

    cad_ids = {item.get("asset_id") for item in map(_mapping, cad_assets)}
    calibration_ids = {
        item.get("calibration_id") for item in map(_mapping, calibrations)
    }
    for index, joint in enumerate(map(_mapping, joints)):
        cad_id = _mapping(joint.get("cad_binding")).get("asset_id")
        calibration_id = joint.get("calibration_id")
        if cad_id is not None and cad_id not in cad_ids:
            _add(
                issues,
                "E_CAD_REFERENCE",
                f"/joints/{index}/cad_binding/asset_id",
                f"unknown CAD asset {cad_id!r}",
            )
        if calibration_id is not None and calibration_id not in calibration_ids:
            _add(
                issues,
                "E_CALIBRATION_REFERENCE",
                f"/joints/{index}/calibration_id",
                f"unknown calibration {calibration_id!r}",
            )

    source_ids = {item.get("source_id") for item in map(_mapping, sources)}
    for path, source_ref in _source_refs(config):
        if source_ref not in source_ids:
            _add(
                issues,
                "E_SOURCE_REFERENCE",
                path,
                f"unknown provenance source {source_ref!r}",
            )

    integrity = _mapping(config.get("configuration_integrity"))
    expected_digest = canonical_digest(config)
    digest_valid = (
        not verify_digest
        or (
            integrity.get("algorithm") == "sha256"
            and integrity.get("canonicalization")
            == "json-sort-keys-utf8-omit-digest-v1"
            and integrity.get("digest") == expected_digest
        )
    )
    if verify_digest and not digest_valid:
        _add(
            issues,
            "E_CONFIG_DIGEST",
            "/configuration_integrity/digest",
            f"digest mismatch; expected {expected_digest}",
        )

    safety = _mapping(config.get("safety_admission"))
    if (
        config.get("configuration_state") == "incomplete_observation"
        and not safety.get("motion_enable_allowed", False)
        and not _sequence(safety.get("blockers"))
    ):
        _add(
            issues,
            "E_BLOCKERS_REQUIRED",
            "/safety_admission/blockers",
            "an incomplete disabled configuration must explain its blockers",
        )
    if safety.get("motion_enable_allowed") is True:
        blockers = _motion_blockers(config, digest_valid)
        if blockers:
            _add(
                issues,
                "E_ENABLE_INCOMPLETE",
                "/safety_admission/motion_enable_allowed",
                "motion cannot be enabled: " + "; ".join(blockers),
            )

    return sorted(set(issues))


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("configuration root must be a JSON object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run dependency-free semantic Dropbear configuration validation."
    )
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "--print-digest",
        action="store_true",
        help="print the canonical digest without validating",
    )
    arguments = parser.parse_args(argv)
    try:
        config = load_config(arguments.config)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True))
        return 2
    if arguments.print_digest:
        print(canonical_digest(config))
        return 0
    issues = validate_config(config)
    result = {
        "config": str(arguments.config),
        "semantic_validator": "dropbear-config-semantics-v1",
        "json_schema_validation": "not_performed",
        "valid": not issues,
        "issue_count": len(issues),
        "issues": [issue.render() for issue in issues],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
