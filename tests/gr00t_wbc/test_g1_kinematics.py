from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from integrations.gr00t_wbc.g1_kinematics import (
    G1Kinematics,
    G1_SEMANTIC_BODY_NAMES,
)
from integrations.gr00t_wbc.retarget import (
    G1_BODY_JOINT_NAMES,
    RetargetingError,
)


ROOT = Path(__file__).resolve().parents[2]


def test_pinned_g1_tree_exposes_exact_decoder_joint_order() -> None:
    kinematics = G1Kinematics(ROOT)
    result = kinematics.forward([0.0] * len(G1_BODY_JOINT_NAMES))
    assert result.joint_positions_rad == (0.0,) * 29
    assert set(result.semantic_body_matrices) == set(G1_SEMANTIC_BODY_NAMES)
    assert np.allclose(result.body_matrices["pelvis"][:3, 3], [0, 0, 0.793])
    assert result.semantic_body_position("left_foot")[1] > 0
    assert result.semantic_body_position("right_foot")[1] < 0


def test_g1_fk_matches_mujoco_for_random_pose_when_available() -> None:
    mujoco = pytest.importorskip("mujoco")
    kinematics = G1Kinematics(ROOT)
    pose = np.asarray(
        [
            lower + 0.37 * (upper - lower)
            for lower, upper in kinematics.joint_limits_rad
        ]
    )
    expected = kinematics.forward(pose)

    model = mujoco.MjModel.from_xml_path(str(kinematics.source_path))
    data = mujoco.MjData(model)
    data.qpos[:7] = [0.0, 0.0, 0.793, 1.0, 0.0, 0.0, 0.0]
    data.qpos[7:] = pose
    mujoco.mj_forward(model, data)
    for name in (
        "pelvis",
        "left_knee_link",
        "left_ankle_roll_link",
        "right_ankle_roll_link",
        "torso_link",
        "left_wrist_yaw_link",
        "right_wrist_yaw_link",
    ):
        body_id = mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            name,
        )
        matrix = expected.body_matrices[name]
        assert matrix[:3, 3] == pytest.approx(data.xpos[body_id], abs=2e-7)
        assert matrix[:3, :3] == pytest.approx(
            data.xmat[body_id].reshape(3, 3),
            abs=2e-7,
        )


def test_g1_semantic_body_motion_is_not_joint_angle_copying() -> None:
    kinematics = G1Kinematics(ROOT)
    neutral = kinematics.forward([0.0] * 29)
    pose = {name: 0.0 for name in G1_BODY_JOINT_NAMES}
    pose["left_hip_pitch_joint"] = 0.45
    pose["left_knee_joint"] = 0.72
    bent = kinematics.forward(pose)
    assert not np.allclose(
        neutral.semantic_body_position("left_foot"),
        bent.semantic_body_position("left_foot"),
    )
    assert np.allclose(
        neutral.semantic_body_position("right_foot"),
        bent.semantic_body_position("right_foot"),
    )


def test_g1_fk_contract_rejects_wrong_pose_shape_and_unknown_semantic() -> None:
    kinematics = G1Kinematics(ROOT)
    with pytest.raises(RetargetingError, match="contains 28"):
        kinematics.forward([0.0] * 28)
    result = kinematics.forward([0.0] * 29)
    with pytest.raises(RetargetingError, match="unknown G1 semantic"):
        result.semantic_body_transform("left_paw")
    outside_limit = [0.0] * 29
    outside_limit[G1_BODY_JOINT_NAMES.index("left_knee_joint")] = -0.2
    with pytest.raises(RetargetingError, match="left_knee_joint.*outside"):
        kinematics.forward(outside_limit)
    with pytest.raises(RetargetingError, match="cannot be booleans"):
        kinematics.forward([False] * 29)


def test_default_g1_tree_rejects_source_digest_drift(tmp_path: Path) -> None:
    relative = "gear_sonic/data/robots/g1/g1_29dof.xml"
    source = ROOT / "references" / "GR00T-WholeBodyControl" / relative
    target = tmp_path / "references" / "GR00T-WholeBodyControl" / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    lock_path = (
        tmp_path
        / "integrations"
        / "gr00t_wbc"
        / "UPSTREAM_LOCK.json"
    )
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        json.dumps(
            {
                "g1Kinematics": {
                    "sourcePath": relative,
                    "sha256": "0" * 64,
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RetargetingError, match="MJCF digest drift"):
        G1Kinematics(tmp_path)
