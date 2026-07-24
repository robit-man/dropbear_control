from __future__ import annotations

from pathlib import Path

import pytest

from integrations.gr00t_wbc.embodiment import EmbodimentContractError
from integrations.gr00t_wbc.g1_kinematics import (
    G1_RELEASE_STANDING_POSE_RAD,
)
from integrations.gr00t_wbc.retarget import G1_BODY_JOINT_NAMES, RetargetingError
from integrations.gr00t_wbc.usd_retarget import (
    G1UsdDropbearRetargeter,
    USD_RETARGET_SCHEMA,
)


ROOT = Path(__file__).resolve().parents[2]


def test_usd_retarget_evaluates_exact_body_graph_and_closures() -> None:
    retargeter = G1UsdDropbearRetargeter(ROOT)
    result = retargeter.retarget_g1_pose(
        G1_RELEASE_STANDING_POSE_RAD,
        refinement_iterations=0,
    )
    payload = result.as_payload()
    assert payload["schema"] == USD_RETARGET_SCHEMA
    assert len(result.joint_positions_rad) == 22
    assert payload["usdTaskSpace"]["usdGeometryApplied"] is True
    assert payload["usdTaskSpace"]["kinematicsAuthoritative"] is False
    assert payload["usdTaskSpace"]["contactDynamicsAuthoritative"] is False
    assert payload["usdTaskSpace"]["physxValidationRequired"] is True
    assert payload["usdTaskSpace"]["realTimeCapable"] is False
    source = payload["usdTaskSpace"]["sourceVerification"]
    assert source["verified"] is True
    assert source["authoritativeUsdRequired"] is True
    assert source["assetCount"] == 3
    assert len(payload["usdTaskSpace"]["passiveAnglesRad"]) == 32
    assert result.usd_solution.maximum_closure_residual_m < 0.003


def test_usd_dls_reduces_body_target_error_for_asymmetric_pose() -> None:
    retargeter = G1UsdDropbearRetargeter(ROOT)
    source = dict(zip(G1_BODY_JOINT_NAMES, G1_RELEASE_STANDING_POSE_RAD))
    source.update(
        {
            "left_hip_pitch_joint": 0.38,
            "left_knee_joint": 1.05,
            "left_ankle_pitch_joint": -0.42,
            "right_shoulder_pitch_joint": -0.48,
            "right_elbow_joint": 1.10,
        }
    )
    result = retargeter.retarget_g1_pose(
        source,
        stance_contacts={"left": False, "right": True},
        refinement_iterations=1,
    )
    assert result.diagnostics.iterations_accepted in (0, 1)
    assert result.diagnostics.improved
    assert (
        result.diagnostics.final_task_error
        <= result.diagnostics.seed_task_error + 1e-10
    )
    assert result.diagnostics.stance_contacts == {
        "left": False,
        "right": True,
    }
    assert len(result.diagnostics.body_targets) == 10
    arm_errors = [
        row.position_error_m
        for row in result.diagnostics.body_targets
        if any(
            part in row.target for part in ("upper_arm", "forearm", "wrist")
        )
    ]
    assert max(arm_errors) < 0.2
    assert 0.9 < retargeter._motion_scales["right_wrist"] < 1.3
    assert 0.9 < retargeter._motion_scales["left_upper_arm"] < 1.3


def test_usd_retarget_rejects_bad_contact_and_previous_pose_contracts() -> None:
    retargeter = G1UsdDropbearRetargeter(ROOT)
    with pytest.raises(RetargetingError, match="exact left/right"):
        retargeter.retarget_g1_pose(
            G1_RELEASE_STANDING_POSE_RAD,
            stance_contacts={"left": True},
        )
    with pytest.raises(RetargetingError, match="22 values"):
        retargeter.retarget_g1_pose(
            G1_RELEASE_STANDING_POSE_RAD,
            previous_motor_positions_rad=[0.0] * 21,
        )
    with pytest.raises(RetargetingError, match="0..6"):
        retargeter.retarget_g1_pose(
            G1_RELEASE_STANDING_POSE_RAD,
            refinement_iterations=7,
        )


def test_usd_retarget_requires_pinned_authoritative_source(
    tmp_path: Path,
) -> None:
    with pytest.raises(EmbodimentContractError, match="missing source asset"):
        G1UsdDropbearRetargeter(tmp_path)
