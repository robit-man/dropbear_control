from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from integrations.gr00t_wbc.closure_adapter import DropbearClosureAdapter
from integrations.gr00t_wbc.embodiment import (
    ACTION_COUNT,
    ACTION_NAMES,
    CONTRACT,
    OBSERVATION_DIM,
    USD_JOINT_NAMES,
    EmbodimentContractError,
    validate_contract,
    verify_source_assets,
)
from integrations.gr00t_wbc.order_converter import DropbearOrderConverter


ROOT = Path(__file__).resolve().parents[2]

EXPECTED_ACTIONS = (
    "left_outer_calf",
    "left_inner_calf",
    "right_inner_calf",
    "right_outer_calf",
    "left_knee",
    "left_hip_pitch",
    "right_hip_pitch",
    "right_knee",
    "left_hip_yaw",
    "left_hip_roll",
    "right_hip_roll",
    "right_hip_yaw",
    "left_shoulder_pitch",
    "left_shoulder_yaw",
    "left_shoulder_roll",
    "left_elbow_pitch",
    "left_wrist_roll",
    "right_shoulder_pitch",
    "right_shoulder_yaw",
    "right_shoulder_roll",
    "right_elbow_pitch",
    "right_wrist_roll",
)

EXPECTED_USD_JOINTS = (
    "LL_Revolute81",
    "LL_Revolute67",
    "RL_Revolute67",
    "RL_Revolute81",
    "LL_knee_actuator_joint",
    "LL_hip_joint",
    "RL_hip_joint",
    "RL_knee_actuator_joint",
    "PG_left_leg_roll",
    "PG_left_leg_pitch",
    "PG_right_leg_pitch",
    "PG_right_leg_roll",
    "LH_yaw",
    "LH_pitch",
    "LH_roll",
    "LH_Revolute41",
    "LH_wrist_roll",
    "RH_yaw",
    "RH_pitch",
    "RH_roll",
    "RH_Revolute41",
    "RH_wrist_roll",
)


def test_contract_is_exactly_the_existing_22_motor_surface():
    validate_contract()
    assert ACTION_COUNT == 22
    assert ACTION_NAMES == EXPECTED_ACTIONS
    assert USD_JOINT_NAMES == EXPECTED_USD_JOINTS
    assert OBSERVATION_DIM == 784
    assert CONTRACT["actionContract"]["passiveJointsCommandable"] is False
    assert CONTRACT["runtimeParameters"]["hardwareDeploymentAllowed"] is False


def test_source_assets_hashes_statistics_and_bindings_are_verified():
    result = verify_source_assets(ROOT)
    assert len(result.verified_paths) == 3
    assert result.articulation_statistics["rigidBodies"] == 93
    assert result.articulation_statistics["physicsJoints"] == 116
    assert result.articulation_statistics["closureConstraints"] == 27
    assert result.articulation_statistics["rlBodyActions"] == 22
    assert result.physics_statistics["rigidBodies"] == 93
    assert result.physics_statistics["physicsJoints"] == 117


def test_upstream_is_pinned_and_no_code_or_weights_are_vendored():
    lock = json.loads(
        (ROOT / "integrations/gr00t_wbc/UPSTREAM_LOCK.json").read_text()
    )
    assert lock["commit"] == "4141c34280abb67c82e115342a8720f4a83d750d"
    assert lock["sourceLicense"]["spdx"] == "Apache-2.0"
    assert lock["modelWeightsLicense"]["name"] == "NVIDIA Open Model License"
    assert lock["sourceCodeVendored"] is False
    assert lock["modelWeightsVendored"] is False


def test_embodiment_json_schema_is_well_formed_and_matches_contract():
    schema_path = (
        ROOT
        / "integrations/gr00t_wbc/schemas/"
        "dropbear-sonic-embodiment-v1.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    assert schema["properties"]["schema"]["const"] == CONTRACT["schema"]
    assert schema["properties"]["actions"]["minItems"] == 22
    assert (
        schema["properties"]["observationContract"]["properties"][
            "decoderTotalDimension"
        ]["const"]
        == OBSERVATION_DIM
    )
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(CONTRACT, schema)


def test_order_conversion_round_trips_and_labels_explicitly():
    converter = DropbearOrderConverter()
    assert converter.status("usd") == "verified-source-manifest"
    assert converter.status("ros2") == "verified-sil-contract"
    assert converter.status("mujoco") == "declared-target-unverified"
    assert converter.status("isaaclab") == "declared-target-unverified"
    values = list(range(ACTION_COUNT))
    usd = converter.convert_vector(values, "policy", "usd")
    assert usd == values
    assert converter.convert_vector(usd, "usd", "policy") == values

    policy_map = dict(zip(ACTION_NAMES, values))
    usd_map = converter.convert_mapping(policy_map, "policy", "usd")
    assert tuple(usd_map) == EXPECTED_USD_JOINTS
    assert usd_map["LL_knee_actuator_joint"] == 4
    assert converter.convert_mapping(usd_map, "usd", "policy") == policy_map

    with pytest.raises(EmbodimentContractError):
        converter.convert_vector(values[:-1], "policy", "usd")
    with pytest.raises(EmbodimentContractError):
        converter.convert_mapping({"left_outer_calf": 1}, "policy", "usd")


def test_closure_adapter_exposes_manifest_topology_and_reduced_projection():
    adapter = DropbearClosureAdapter(ROOT)
    assert adapter.full_passive_projection_supported is False
    assert adapter.topology["fullPassiveProjectionAuthority"] == "Isaac/PhysX"
    assert adapter.topology["arms"]["left"]["motor"] == "LH_Revolute41"
    assert adapter.topology["arms"]["left"]["passiveJoints"] == (
        "LH_Revolute42",
        "LH_elbow_joint",
        "LH_Revolute32",
        "LH_Revolute33",
        "LH_Revolute44",
    )
    assert adapter.topology["arms"]["left"]["closureConstraints"] == (
        "LH_Revolute123",
        "LH_Revolute125",
        "LH_Revolute127",
    )
    assert adapter.topology["legs"]["right"]["motorCranks"] == (
        "RL_Revolute81",
        "RL_Revolute67",
    )
    assert adapter.topology["legs"]["right"]["closureConstraints"] == (
        "RL_Revolute115",
        "RL_Revolute117",
    )

    neutral = [float(row["centerRad"]) for row in CONTRACT["actions"]]
    projected = adapter.project(neutral)
    assert set(projected.usd_motor_positions) == set(EXPECTED_USD_JOINTS)
    assert len(projected.linkage_outputs) == 4
    assert projected.maximum_residual_m < 1e-8
    assert projected.all_in_validated_domain
    assert all(math.isfinite(row.output_angle_rad) for row in projected.linkage_outputs)


def test_knee_lock_and_elbow_surrogate_domains_fail_closed():
    adapter = DropbearClosureAdapter(ROOT)
    neutral = [float(row["centerRad"]) for row in CONTRACT["actions"]]
    neutral[4] = -0.001
    with pytest.raises(EmbodimentContractError, match="left_knee"):
        adapter.project(neutral)

    neutral = [float(row["centerRad"]) for row in CONTRACT["actions"]]
    neutral[20] = 1.4
    with pytest.raises(EmbodimentContractError, match="right_elbow_pitch"):
        adapter.project(neutral)
