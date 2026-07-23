#!/usr/bin/env python3
"""Generate a fail-closed Dropbear cross-layer reconciliation artifact.

The artifact records observations from one pinned upstream commit and the
canonical incomplete Dropbear configuration.  Arithmetic address shapes,
CAD-derived ROS names, and prototype values remain observations: this tool
never turns them into an installed route, calibration, protocol-applicability
claim, ROS mapping, or motion authority.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
DROPBEAR_REPO = ROOT / "references/Dropbear"
PINNED_COMMIT = "13cf5ecaa39b8b89c794fe905dcea0490cfa7726"
CONFIG_PATH = ROOT / "schemas/examples/dropbear-observed-incomplete.json"
CONFIG_SCHEMA_PATH = ROOT / "schemas/dropbear-config.schema.json"
CONFIG_VALIDATOR_PATH = ROOT / "schemas/validate_dropbear_config.py"
SCHEMA_PATH = ROOT / "schemas/dropbear-reconciliation.schema.json"
OUTPUT_PATH = ROOT / "generated/dropbear_reconciliation/reconciliation.json"
TOOL_ID = "generate-dropbear-reconciliation"
TOOL_VERSION = "1.0.0"

SOURCE_PATHS = {
    "legacy_low_level": "Control System/Low Level Control/esp32_devkit_v1.ino",
    "ros_controllers": "Sim/Gazebo/dropbear-sim/dropbear/config/controllers.yaml",
    "ros_leg_control": "Sim/Gazebo/dropbear-sim/dropbear/urdf/ros2_control/leg.ros2_control.xacro",
    "ros_system_control": "Sim/Gazebo/dropbear-sim/dropbear/urdf/ros2_control/dropbear.ros2_control.xacro",
    "ros_trajectory_demo": "Sim/Gazebo/dropbear-sim/dropbear/dropbear/leg_trajectory_publisher.py",
    "ros_package": "Sim/Gazebo/dropbear-sim/dropbear/package.xml",
    "gazebo_leg_description": "Sim/Gazebo/dropbear-sim/dropbear/urdf/gazebo/leg.xacro",
}

TOKEN_TO_CANONICAL = {
    "LEFT_HIP_YAW": "left_hip_yaw",
    "LEFT_HIP_ROLL": "left_hip_roll",
    "LEFT_HIP_PITCH": "left_hip_pitch",
    "LEFT_KNEE": "left_knee",
    "LEFT_CALF_INNER": "left_inner_calf",
    "LEFT_CALF_OUTER": "left_outer_calf",
    "RIGHT_HIP_YAW": "right_hip_yaw",
    "RIGHT_HIP_ROLL": "right_hip_roll",
    "RIGHT_HIP_PITCH": "right_hip_pitch",
    "RIGHT_KNEE": "right_knee",
    "RIGHT_CALF_INNER": "right_inner_calf",
    "RIGHT_CALF_OUTER": "right_outer_calf",
}

EXPECTED_ROS_JOINTS = {
    "left": [
        "LL_hip_joint",
        "LL_knee_actuator_joint",
        "LL_Revolute67",
        "LL_Revolute81",
        "LL_Revolute88",
    ],
    "right": [
        "RL_hip_joint",
        "RL_knee_actuator_joint",
        "RL_Revolute67",
        "RL_Revolute81",
        "RL_Revolute88",
    ],
}


class ReconciliationError(RuntimeError):
    """Generation cannot preserve the pinned fail-closed contract."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReconciliationError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise ReconciliationError(f"JSON root must be an object: {path}")
    return value


def _git(*args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(DROPBEAR_REPO), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise ReconciliationError(
            f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout


def _load_semantic_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "dropbear_config_semantic_validator_reconciliation", CONFIG_VALIDATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise ReconciliationError("cannot load canonical config semantic validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validated_config() -> dict[str, Any]:
    config = _read_json(CONFIG_PATH)
    schema = _read_json(CONFIG_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(config),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        raise ReconciliationError(f"canonical Dropbear config is invalid: {errors[0].message}")
    validator = _load_semantic_validator()
    issues = validator.validate_config(config, verify_digest=True)
    if issues:
        raise ReconciliationError(
            "canonical Dropbear config semantics failed: "
            + " | ".join(issue.render() for issue in issues)
        )
    return config


def _source_snapshot() -> tuple[dict[str, str], list[dict[str, Any]]]:
    head = _git("rev-parse", "HEAD").decode("ascii").strip()
    if head != PINNED_COMMIT:
        raise ReconciliationError(
            f"Dropbear checkout drift: expected {PINNED_COMMIT}, found {head}"
        )
    content: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    for source_id, path in SOURCE_PATHS.items():
        raw = _git("show", f"{PINNED_COMMIT}:{path}")
        content[source_id] = raw.decode("utf-8")
        records.append(
            {
                "source_id": source_id,
                "repository_commit": PINNED_COMMIT,
                "path": path,
                "sha256": _sha256(raw),
                "authority": "upstream_observation_only",
            }
        )
    return content, records


def _legacy_addresses(text: str) -> dict[str, int]:
    found = {
        match.group(1): int(match.group(2), 16)
        for match in re.finditer(
            r"const\s+long\s+unsigned\s+int\s+ACTUATOR_ID_([A-Z_]+)\s*=\s*(0x[0-9A-Fa-f]+)\s*;",
            text,
        )
    }
    if set(found) != set(TOKEN_TO_CANONICAL):
        raise ReconciliationError(
            "legacy actuator constant set drift: "
            f"expected={sorted(TOKEN_TO_CANONICAL)} found={sorted(found)}"
        )
    values = list(found.values())
    if len(values) != len(set(values)):
        raise ReconciliationError("legacy actuator command addresses are not unique")
    return {TOKEN_TO_CANONICAL[token]: value for token, value in found.items()}


def _uncommented_lines(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _controller_joint_list(text: str, side: str) -> list[str]:
    clean = _uncommented_lines(text)
    marker = f"{side}_leg_controller:"
    match = re.search(rf"^{re.escape(marker)}\s*$", clean, re.MULTILINE)
    if match is None:
        raise ReconciliationError(f"missing ROS controller block: {marker}")
    start = match.start()
    next_side = "left" if side == "right" else None
    if next_side:
        next_match = re.search(
            rf"^{next_side}_leg_controller:\s*$",
            clean[start + len(marker) :],
            re.MULTILINE,
        )
        end = (
            start + len(marker) + next_match.start()
            if next_match is not None
            else len(clean)
        )
    else:
        end = len(clean)
    block = clean[start:end]
    prefix = "RL_" if side == "right" else "LL_"
    names = re.findall(rf"^\s*-\s+({prefix}[A-Za-z0-9_]+)\s*$", block, re.MULTILINE)
    if names != EXPECTED_ROS_JOINTS[side]:
        raise ReconciliationError(
            f"ROS {side} leg joint drift: expected={EXPECTED_ROS_JOINTS[side]} found={names}"
        )
    return names


def _require_upstream_invariants(source: dict[str, str]) -> dict[str, list[str]]:
    controller = source["ros_controllers"]
    rate = re.search(r"^\s*update_rate:\s*(\d+)\s*$", controller, re.MULTILINE)
    if rate is None or int(rate.group(1)) != 10:
        raise ReconciliationError("ROS controller-manager update rate is no longer exactly 10 Hz")
    if _uncommented_lines(controller).count("open_loop_control: true") < 2:
        raise ReconciliationError("ROS leg controllers are no longer evidenced open-loop")

    leg_control = re.sub(r"<!--.*?-->", "", source["ros_leg_control"], flags=re.DOTALL)
    active = re.findall(
        r'<xacro:joint\s+prefix="\$\{prefix\}"\s+name="([^"]+)"\s+min_value="-\$\{PI\}"\s+max_value="-\$\{PI\}">',
        leg_control,
    )
    expected_suffixes = [name.split("_", 1)[1] for name in EXPECTED_ROS_JOINTS["right"]]
    if active != expected_suffixes:
        raise ReconciliationError(
            f"active ROS leg control joints/limits drift: expected={expected_suffixes} found={active}"
        )

    system = source["ros_system_control"]
    if "<plugin>gazebo_ros2_control/GazeboSystem</plugin>" not in system:
        raise ReconciliationError("expected GazeboSystem observation is absent")
    if re.search(r"<plugin>(?!gazebo_ros2_control/GazeboSystem)[^<]+</plugin>", system):
        raise ReconciliationError("an unreviewed additional ROS hardware plugin appeared")

    demo = source["ros_trajectory_demo"]
    if "timer_period = 1.0" not in demo or "input()" not in demo:
        raise ReconciliationError("trajectory demo timing/input observation drift")
    for names in EXPECTED_ROS_JOINTS.values():
        if not all(name in demo for name in names):
            raise ReconciliationError("trajectory demo joint observation drift")

    package = source["ros_package"]
    if "<version>0.0.0</version>" not in package:
        raise ReconciliationError("ROS package version observation drift")
    return {
        "left": _controller_joint_list(controller, "left"),
        "right": _controller_joint_list(controller, "right"),
    }


def _layer(
    layer_id: str,
    status: str,
    input_contract: str,
    output_contract: str,
    rate_hz: float | None,
    units_and_frame: str,
    owner: str | None,
    failure_propagation: str,
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "layer_id": layer_id,
        "authority_status": status,
        "input_contract": input_contract,
        "output_contract": output_contract,
        "rate_hz": rate_hz,
        "units_and_frame": units_and_frame,
        "owner": owner,
        "failure_propagation": failure_propagation,
        "physical_motion_authority": False,
        "blockers": blockers,
    }


def build() -> dict[str, Any]:
    config = _validated_config()
    source, source_records = _source_snapshot()
    ros_joints = _require_upstream_invariants(source)
    addresses = _legacy_addresses(source["legacy_low_level"])

    config_actuators = {item["canonical_joint_name"]: item for item in config["actuators"]}
    if set(config_actuators) != set(addresses):
        raise ReconciliationError("canonical config and legacy actuator-name sets differ")
    for name, address in addresses.items():
        if config_actuators[name]["address"]["legacy_full_command_can_id"] != address:
            raise ReconciliationError(f"canonical legacy address drift for {name}")
        if config_actuators[name]["address"]["native_node_id"] is not None:
            raise ReconciliationError(f"canonical config improperly promotes native node for {name}")

    joint_by_name = {item["canonical_name"]: item for item in config["joints"]}
    actuators: list[dict[str, Any]] = []
    for joint in config["joints"]:
        name = joint["canonical_name"]
        address = addresses[name]
        blockers = [
            "installed_model_hardware_firmware_identity_missing",
            "native_protocol_revision_applicability_unverified",
            "exclusive_bus_route_node_owner_missing",
            "evidenced_joint_and_drive_limits_missing",
            "physical_zero_sign_ratio_calibration_missing",
            "accepted_cad_output_member_and_joint_binding_missing",
            "ros_joint_to_actuator_mapping_unresolved",
            "independent_safe_power_and_hil_evidence_missing",
        ]
        if joint["feedback"]["external_sensor_id"] is None:
            blockers.append("external_joint_feedback_missing")
        actuators.append(
            {
                "actuator_id": joint["actuator_id"],
                "canonical_joint_name": name,
                "chirality": joint["chirality"],
                "semantic_joint": joint["semantic_joint"],
                "low_level_observation": {
                    "legacy_request_arbitration_id": address,
                    "arithmetic_candidate_node_id": address - 0x140,
                    "evidence_status": "unverified_command_address_observation",
                    "candidate_is_installed_route": False,
                    "source_id": "legacy_low_level",
                },
                "installed_identity": {
                    "manufacturer": None,
                    "series": None,
                    "model": None,
                    "hardware_revision": None,
                    "drive_firmware": None,
                    "protocol_name": None,
                    "protocol_revision": None,
                    "transport": None,
                    "control_mode": None,
                    "status": "unresolved",
                },
                "route": {
                    "bus_id": None,
                    "native_node_id": None,
                    "owner_controller_node_id": None,
                    "status": "unresolved",
                },
                "limit_provenance": {
                    "vendor_rating": None,
                    "software_limit": None,
                    "measured_safe_limit": None,
                    "runtime_derate": None,
                    "effective_limit": None,
                    "status": "missing",
                },
                "calibration": {
                    "calibration_id": None,
                    "zero_reference_rad": None,
                    "motor_to_joint_sign": None,
                    "output_per_motor_ratio": None,
                    "home_or_hard_stop_procedure": None,
                    "recorded_at": None,
                    "tool_id": None,
                    "operator_id": None,
                    "invalidation_conditions": [],
                    "status": "missing",
                },
                "feedback": {
                    "native_drive_status": joint["feedback"]["native_drive_status"],
                    "external_sensor_id": joint["feedback"]["external_sensor_id"],
                    "external_sensor_status": joint["feedback"]["external_sensor_status"],
                },
                "cad_binding": {
                    "asset_id": joint["cad_binding"]["asset_id"],
                    "housing_member": joint["cad_binding"]["housing_member"],
                    "output_member": joint["cad_binding"]["output_member"],
                    "joint_origin_xyz_m": joint["cad_binding"]["joint_origin_xyz_m"],
                    "joint_axis_xyz": joint["cad_binding"]["joint_axis_xyz"],
                    "status": joint["cad_binding"]["status"],
                },
                "ros_joint_ids": [],
                "mapping_status": "unresolved_no_guess",
                "motion_ready": False,
                "blockers": blockers,
            }
        )

    if len(joint_by_name) != 12 or sum(a["feedback"]["external_sensor_id"] is not None for a in actuators) != 10:
        raise ReconciliationError("canonical joint/sensor cardinality drift")

    ros_groups = []
    for side in ("left", "right"):
        ros_groups.append(
            {
                "controller_id": f"{side}_leg_controller",
                "chirality": side,
                "joint_ids": ros_joints[side],
                "canonical_actuator_ids": [],
                "mapping_status": "unresolved_no_guess",
                "command_interface": "position",
                "state_interface": "position",
                "open_loop_control": True,
                "controller_manager_rate_hz": 10,
                "hardware_plugin": "gazebo_ros2_control/GazeboSystem",
                "physical_hardware_plugin_present": False,
                "active_limit_observation": "min_equals_max_equals_negative_pi",
            }
        )

    artifact = {
        "schema_version": "dropbear-reconciliation/1",
        "artifact_id": "dropbear-cross-layer-reconciliation",
        "authority": "derived_observation_only",
        "generated_from": {
            "dropbear_repository_commit": PINNED_COMMIT,
            "canonical_configuration_id": config["configuration_id"],
            "canonical_configuration_revision": config["configuration_revision"],
            "canonical_configuration_digest": config["configuration_integrity"]["digest"],
            "canonical_config_file_sha256": _sha256(CONFIG_PATH.read_bytes()),
            "source_files": source_records,
            "tool_id": TOOL_ID,
            "tool_version": TOOL_VERSION,
        },
        "summary": {
            "canonical_actuator_count": 12,
            "low_level_command_address_observation_count": 12,
            "external_sensor_observation_count": 10,
            "ros_leg_command_joint_count": 10,
            "evidence_backed_ros_actuator_mapping_count": 0,
            "installed_identity_count": 0,
            "runtime_route_count": 0,
            "valid_calibration_count": 0,
            "accepted_cad_binding_count": 0,
            "physical_hardware_plugin_count": 0,
            "motion_enable_allowed": False,
        },
        "actuators": actuators,
        "ros_leg_groups": ros_groups,
        "layer_interfaces": [
            _layer("high_level_intent", "missing", "operator or autonomy goal", "planned joint intent", None, "undefined", None, "no production failure contract", ["planner_and_behavior_contract_missing"]),
            _layer("ros_trajectory_demo", "demonstration_only", "stdin position prompts", "JointTrajectory", 1.0, "radians claimed; CAD joint frames unresolved", "leg_jtc_publisher_node", "logs only; repeatedly republishes fixed command", ["interactive_demo_not_command_authority", "feedback_not_consumed"]),
            _layer("ros2_control_gazebo", "simulation_only", "position trajectory", "Gazebo joint position", 10.0, "radians; CAD-named frames", "gazebo_ros2_control", "open-loop simulated state only", ["open_loop_control", "zero_range_limit_observation", "no_physical_hardware_plugin"]),
            _layer("production_host_api", "offline_unbound", "typed robot command", "Host Link command", None, "SI canonical joint frame", None, "typed denial available; Dropbear adapter absent", ["dropbear_host_adapter_missing", "ros_mapping_unresolved"]),
            _layer("host_link_v1", "offline_core", "versioned typed frame", "session-owned accepted command/disposition/state", None, "SI plus explicit validity", "session_receiver", "CRC/session/sequence/config mismatch denies", ["not_wired_to_dropbear_runtime", "authenticated_transport_missing"]),
            _layer("session_gateway", "offline_core", "exact CURRENT_Q binding", "typed native V4.4 request or denial", None, "q-axis current A to 0.01 A raw", "single_writer_gateway", "lease/config/safety/route mismatch denies", ["installed_bindings_absent", "physical_protocol_applicability_unverified"]),
            _layer("can_adapter", "offline_no_physical_driver", "standard CAN frame", "timestamped frame/result", None, "11-bit CAN at configured bitrate", None, "fake driver preserves fault distinctions", ["esp32_driver_unselected", "pinout_transceiver_termination_unreviewed", "listen_only_capture_absent"]),
            _layer("native_actuator_protocol", "unverified_observation", "legacy 0x140+candidate address shape", "native drive response", None, "V4.4 shape is a hypothesis for installed drives", None, "legacy code has no correlated RX path", ["model_firmware_protocol_tuple_missing", "bench_capture_missing"]),
            _layer("joint_observation", "incomplete_observation", "native and external samples", "timestamped joint sample", None, "external ADC units/calibration unresolved", None, "ten external observations for twelve actuators", ["native_telemetry_path_missing", "hip_yaw_external_feedback_missing", "calibrations_missing"]),
            _layer("state_estimator", "missing", "time-correlated joint/drive samples", "robot state with covariance/validity", None, "canonical robot frames", None, "no estimator or stale-state policy", ["estimator_missing", "urdf_to_actuator_mapping_unresolved"]),
        ],
        "conflicts": [
            {"conflict_id": "actuator-ros-cardinality", "severity": "critical", "observation": "six semantic actuator observations per leg but five ROS leg command joints per leg", "unsafe_inference_prohibited": "map CAD joint names to actuators by order or name similarity", "required_resolution": "reviewed one-to-one kinematic and actuation graph with explicit passive/closed-chain joints", "source_ids": ["legacy_low_level", "ros_controllers", "ros_leg_control"]},
            {"conflict_id": "hip-yaw-feedback-gap", "severity": "critical", "observation": "hip yaw is commanded in legacy firmware but absent from the five external sensors and ROS leg group", "unsafe_inference_prohibited": "reuse another hip sensor or omit hip yaw silently", "required_resolution": "define hip-yaw sensing, calibration, limits, ROS semantics, and failure behavior", "source_ids": ["legacy_low_level", "ros_controllers"]},
            {"conflict_id": "open-loop-low-rate-controller", "severity": "high", "observation": "leg trajectory control is open-loop position at a 10 Hz controller-manager rate", "unsafe_inference_prohibited": "treat Gazebo command state as measured physical state", "required_resolution": "choose loop ownership and measured rates from bandwidth/safety evidence", "source_ids": ["ros_controllers"]},
            {"conflict_id": "collapsed-leg-limits", "severity": "critical", "observation": "all five active ROS leg joints declare minimum and maximum as negative PI", "unsafe_inference_prohibited": "replace with symmetric PI or vendor ratings without provenance", "required_resolution": "source and validate per-joint hard, soft, velocity, current, effort, and thermal limits", "source_ids": ["ros_leg_control"]},
            {"conflict_id": "gazebo-only-hardware", "severity": "high", "observation": "the ROS 2 control system selects only gazebo_ros2_control/GazeboSystem", "unsafe_inference_prohibited": "claim a physical robot interface from the simulation plugin", "required_resolution": "implement and test a physical adapter behind the common typed hardware boundary", "source_ids": ["ros_system_control"]},
            {"conflict_id": "legacy-address-not-route", "severity": "critical", "observation": "0x141 through 0x14C are legacy command-address observations; installed nodes, ownership, exact tuples, and applicability are unknown", "unsafe_inference_prohibited": "promote address minus 0x140 to an installed native node ID", "required_resolution": "listen-only discovery, exact tuple inventory, reviewed ownership, and protocol applicability evidence", "source_ids": ["legacy_low_level"]},
            {"conflict_id": "ros-demo-not-planner", "severity": "high", "observation": "the ROS publisher accepts stdin positions and republishes a fixed trajectory every second", "unsafe_inference_prohibited": "treat the publisher as a planner, arbiter, watchdog, or feedback controller", "required_resolution": "define high-level intent, planning, arbitration, lease, cancellation, and feedback contracts", "source_ids": ["ros_trajectory_demo", "ros_package"]},
        ],
        "admission": {
            "motion_enable_allowed": False,
            "generation_policy": "incomplete entries emit explicit denial and never generate runtime routes or guessed mappings",
            "required_hold_points": [
                "installed_identity_and_exact_protocol_tuple_review",
                "listen_only_can_capture_and_protocol_applicability",
                "exclusive_bus_route_node_owner_review",
                "per_joint_limit_provenance_and_runtime_derate_contract",
                "physical_zero_sign_ratio_calibration",
                "accepted_cad_housing_output_joint_binding",
                "reviewed_ros_kinematic_and_actuation_mapping",
                "independent_safe_power_estop_and_fault_path",
                "sil_hil_bench_and_robot_phase_gates",
            ],
        },
    }
    validate_artifact(artifact)
    return artifact


def validate_artifact(artifact: dict[str, Any]) -> None:
    schema = _read_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(artifact),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        first = errors[0]
        location = "/" + "/".join(map(str, first.absolute_path))
        raise ReconciliationError(f"reconciliation schema failure at {location}: {first.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the generated artifact drifts")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    rendered = _canonical_json(build())
    output = args.output.resolve()
    if args.check:
        if not output.exists() or output.read_bytes() != rendered:
            raise ReconciliationError(f"generated artifact drift: {output}")
        print(f"DROPBEAR_RECONCILIATION_OK path={output.relative_to(ROOT)} sha256={_sha256(rendered)}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rendered)
    print(f"wrote {output.relative_to(ROOT)} sha256={_sha256(rendered)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ReconciliationError, subprocess.SubprocessError) as error:
        print(f"Dropbear reconciliation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
