from __future__ import annotations

import math
from pathlib import Path
import sys

import pytest

from integrations.gr00t_wbc.action_adapter import UpstreamSonicActionAdapter
from integrations.gr00t_wbc.embodiment import ACTION_NAMES, CONTRACT
from integrations.gr00t_wbc.retarget import (
    G1_BODY_JOINT_NAMES,
    G1VlaDropbearRetargeter,
    RETARGET_SCHEMA,
    RetargetingError,
    retargeting_contract,
)


ROOT = Path(__file__).resolve().parents[2]


def neutral_g1() -> dict[str, float]:
    return {name: 0.0 for name in G1_BODY_JOINT_NAMES}


def test_contract_makes_the_latent_decode_boundary_explicit():
    contract = retargeting_contract()
    assert contract["schema"] == RETARGET_SCHEMA
    assert contract["source"]["motionTokenDimension"] == 64
    assert contract["source"]["rawMotionTokenAccepted"] is False
    assert contract["source"]["jointOrder"] == list(G1_BODY_JOINT_NAMES)
    assert contract["target"]["jointOrder"] == list(ACTION_NAMES)
    assert contract["target"]["passiveJointsCommandable"] is False
    assert contract["fullPassiveProjectionAuthority"] == "Isaac/PhysX"
    assert contract["hardwareAuthorized"] is False


def test_neutral_g1_pose_is_action_representable_and_closure_valid():
    retargeter = G1VlaDropbearRetargeter(ROOT)
    result = retargeter.retarget_g1_pose(neutral_g1())
    adapter = UpstreamSonicActionAdapter(ROOT)

    assert len(result.joint_positions_rad) == 22
    assert len(result.normalized_actions) == 22
    assert adapter.decode(result.normalized_actions) == pytest.approx(
        result.joint_positions_rad
    )
    assert result.closure.all_in_validated_domain
    assert result.closure.maximum_residual_m < 1e-8
    assert set(result.closure.usd_motor_positions) == {
        row["usdJoint"] for row in CONTRACT["actions"]
    }
    assert all(-1.0 <= value <= 1.0 for value in result.normalized_actions)


def test_direct_semantics_and_mirrored_calf_differential_are_mapped():
    retargeter = G1VlaDropbearRetargeter(ROOT)
    source = neutral_g1()
    source.update(
        {
            "left_hip_pitch_joint": 0.31,
            "right_hip_pitch_joint": -0.27,
            "left_shoulder_pitch_joint": -0.41,
            "right_shoulder_yaw_joint": 0.22,
            "left_ankle_pitch_joint": -0.4,
            "right_ankle_pitch_joint": -0.4,
            "left_ankle_roll_joint": 0.1,
            "right_ankle_roll_joint": 0.1,
        }
    )
    result = retargeter.retarget_g1_pose(source)
    q = dict(zip(ACTION_NAMES, result.joint_positions_rad))

    assert q["left_hip_pitch"] == pytest.approx(0.31)
    assert q["right_hip_pitch"] == pytest.approx(-0.27)
    assert q["left_shoulder_pitch"] == pytest.approx(-0.41)
    assert q["right_shoulder_yaw"] == pytest.approx(0.22)
    assert q["left_outer_calf"] > q["left_inner_calf"]
    assert q["right_outer_calf"] < q["right_inner_calf"]
    assert 0.5 * (
        q["left_outer_calf"] + q["left_inner_calf"]
    ) == pytest.approx(
        0.5 * (q["right_outer_calf"] + q["right_inner_calf"])
    )


def test_knee_and_elbow_are_inverted_through_reduced_closures():
    retargeter = G1VlaDropbearRetargeter(ROOT)
    source = neutral_g1()
    source["left_hip_pitch_joint"] = 0.2
    source["right_hip_pitch_joint"] = -0.15
    source["left_knee_joint"] = 0.35
    source["right_knee_joint"] = 0.30
    source["left_elbow_joint"] = 0.18
    source["right_elbow_joint"] = 0.16

    result = retargeter.retarget_g1_pose(source)
    assert result.semantic_achieved_rad["left_knee_joint"] == pytest.approx(
        0.35, abs=1e-7
    )
    assert result.semantic_achieved_rad["right_knee_joint"] == pytest.approx(
        0.30, abs=1e-7
    )
    assert result.semantic_achieved_rad["left_elbow_joint"] == pytest.approx(
        0.18, abs=1e-7
    )
    assert result.semantic_achieved_rad["right_elbow_joint"] == pytest.approx(
        0.16, abs=1e-7
    )
    assert not {
        "left_knee_flexion",
        "right_knee_flexion",
        "left_elbow_flexion",
        "right_elbow_flexion",
    }.intersection(row.semantic for row in result.saturations)


def test_unreachable_flexion_saturates_without_leaving_motor_domains():
    retargeter = G1VlaDropbearRetargeter(ROOT)
    source = neutral_g1()
    source["left_knee_joint"] = 2.7
    source["right_elbow_joint"] = 2.0
    result = retargeter.retarget_g1_pose(source)
    q = dict(zip(ACTION_NAMES, result.joint_positions_rad))

    assert q["left_knee"] <= 1.1
    assert q["right_elbow_pitch"] <= 0.8
    semantics = {row.semantic for row in result.saturations}
    assert "left_knee_flexion" in semantics
    assert "right_elbow_flexion" in semantics
    assert (
        result.semantic_achieved_rad["left_knee_joint"]
        < source["left_knee_joint"]
    )
    assert (
        result.semantic_achieved_rad["right_elbow_joint"]
        < source["right_elbow_joint"]
    )
    assert result.closure.all_in_validated_domain


def test_source_contract_rejects_latent_nonfinite_and_wrong_order():
    retargeter = G1VlaDropbearRetargeter(ROOT)
    with pytest.raises(RetargetingError, match="64-value VLA motion token"):
        retargeter.retarget_g1_pose(
            [0.0] * 64,
            source_joint_names=("motion_token",) * 64,
        )

    source = neutral_g1()
    source["left_knee_joint"] = math.nan
    with pytest.raises(RetargetingError, match="finite"):
        retargeter.retarget_g1_pose(source)

    source = neutral_g1()
    source["left_ankle_pitch_joint"] = 5.0
    with pytest.raises(RetargetingError, match="decoded-source envelope"):
        retargeter.retarget_g1_pose(source)

    with pytest.raises(RetargetingError, match="source_joint_names"):
        retargeter.retarget_g1_pose(
            [0.0] * 29,
            source_joint_names=tuple(reversed(G1_BODY_JOINT_NAMES)),
        )


def test_wbc_reference_payload_is_accepted_by_existing_ros_contract():
    package_root = ROOT / "ros2_control/dropbear_wbc_controller"
    sys.path.insert(0, str(package_root))
    try:
        from dropbear_wbc_controller.contract import JointReferenceFrame

        result = G1VlaDropbearRetargeter(ROOT).retarget_g1_pose(neutral_g1())
        payload = result.wbc_reference_payload(
            session_id="g1-shadow-1",
            sequence=7,
            source_token_sequence=21,
            generated_steady_time_ns=123456,
        )
        parsed = JointReferenceFrame.from_dict(payload)
    finally:
        sys.path.remove(str(package_root))

    assert parsed.session_id == "g1-shadow-1"
    assert parsed.sequence == 7
    assert parsed.source_token_sequence == 21
    assert parsed.positions == pytest.approx(result.joint_positions_rad)


def test_chunk_is_bounded_and_preserves_frame_count():
    retargeter = G1VlaDropbearRetargeter(ROOT)
    source = neutral_g1()
    chunk = retargeter.retarget_chunk([source, source, source])
    assert len(chunk) == 3
    with pytest.raises(RetargetingError, match="1..2"):
        retargeter.retarget_chunk([source, source, source], maximum_frames=2)
