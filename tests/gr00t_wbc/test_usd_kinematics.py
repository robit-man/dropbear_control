from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from integrations.gr00t_wbc.embodiment import ACTION_NAMES, USD_JOINT_NAMES
from integrations.gr00t_wbc.usd_kinematics import (
    DropbearKinematicsError,
    DropbearUsdKinematics,
    SEMANTIC_BODY_PATHS,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def kinematics() -> DropbearUsdKinematics:
    return DropbearUsdKinematics(PROJECT_ROOT)


@pytest.fixture(scope="module")
def rest_result(kinematics: DropbearUsdKinematics):
    return kinematics.solve([0.0] * len(ACTION_NAMES))


def test_manifest_graph_and_semantic_outputs_are_complete(
    kinematics: DropbearUsdKinematics,
    rest_result,
) -> None:
    assert len(kinematics.body_paths) == 93
    assert len(kinematics.passive_joint_names) == 32
    assert len(rest_result.body_matrices) == 93
    assert len(rest_result.passive_angles_rad) == 32
    assert len(rest_result.diagnostics.per_constraint_residual_m) == 27
    for semantic, path in SEMANTIC_BODY_PATHS.items():
        assert path in rest_result.body_matrices
        assert np.array_equal(
            rest_result.semantic_body_transform(semantic),
            rest_result.body_transform(path),
        )
        assert rest_result.semantic_body_position(semantic).shape == (3,)
    assert rest_result.joint_anchor_world("LL_hip_joint").shape == (3,)
    assert rest_result.joint_anchor_world("LH_yaw").shape == (3,)


def test_three_js_column_major_body_matrices_are_preserved(
    kinematics: DropbearUsdKinematics,
    rest_result,
) -> None:
    manifest = json.loads(kinematics.manifest_path.read_text(encoding="utf-8"))
    source = next(
        body for body in manifest["bodies"] if body["path"] != "/humanoid/world"
    )
    expected = np.asarray(source["matrix"], dtype=np.float64).reshape(
        (4, 4),
        order="F",
    )
    actual = rest_result.body_transform(source["path"])
    # At a zero command and zero/rest closure, a solved passive chain can move
    # descendants.  The selected first non-world body is an articulation root
    # output and remains at the authored transform.
    assert np.allclose(actual, expected, atol=1e-12)
    assert np.allclose(actual[:3, 3], source["matrix"][12:15], atol=1e-12)
    assert actual.flags.writeable is False


def test_right_outer_calf_uses_retained_mirrored_z_axis(
    kinematics: DropbearUsdKinematics,
) -> None:
    manifest_joint = next(
        joint
        for joint in kinematics.manifest["joints"]
        if joint["name"] == "RL_Revolute81"
    )
    assert manifest_joint["axis"] == "X"
    effective = kinematics.joint_axis_local("RL_Revolute81")
    assert np.linalg.norm(effective) == pytest.approx(1.0)
    assert abs(effective[0]) < 1e-12
    assert abs(effective[2]) > 0.9


def test_sequence_semantic_and_usd_mappings_produce_same_pose(
    kinematics: DropbearUsdKinematics,
) -> None:
    values = np.linspace(-0.12, 0.13, len(ACTION_NAMES))
    values[4] = 0.20
    values[7] = 0.18
    semantic = dict(zip(ACTION_NAMES, values))
    usd = dict(zip(USD_JOINT_NAMES, values))
    from_sequence = kinematics.solve(values)
    from_semantic = kinematics.solve(semantic)
    from_usd = kinematics.solve(usd)
    for semantic_body in ("left_foot", "right_foot", "left_wrist", "right_wrist"):
        expected = from_sequence.semantic_body_transform(semantic_body)
        assert np.allclose(
            from_semantic.semantic_body_transform(semantic_body),
            expected,
            atol=1e-10,
        )
        assert np.allclose(
            from_usd.semantic_body_transform(semantic_body),
            expected,
            atol=1e-10,
        )


def test_motor_targets_move_usd_output_bodies_and_close_linkages(
    kinematics: DropbearUsdKinematics,
    rest_result,
) -> None:
    values = np.zeros(len(ACTION_NAMES), dtype=np.float64)
    values[ACTION_NAMES.index("left_hip_pitch")] = 0.28
    values[ACTION_NAMES.index("left_knee")] = 0.38
    values[ACTION_NAMES.index("left_outer_calf")] = 0.08
    values[ACTION_NAMES.index("left_inner_calf")] = -0.05
    values[ACTION_NAMES.index("right_shoulder_pitch")] = -0.18
    values[ACTION_NAMES.index("right_elbow_pitch")] = 0.32
    moved = kinematics.solve(
        values,
        previous_passive_angles=rest_result.passive_angles_rad,
    )
    assert np.linalg.norm(
        moved.semantic_body_position("left_foot")
        - rest_result.semantic_body_position("left_foot")
    ) > 0.02
    assert np.linalg.norm(
        moved.semantic_body_position("right_wrist")
        - rest_result.semantic_body_position("right_wrist")
    ) > 0.01
    assert math.isfinite(moved.maximum_closure_residual_m)
    assert moved.maximum_closure_residual_m < 0.03
    assert moved.diagnostics.leg_maximum_residual_m < 0.03
    assert moved.diagnostics.arm_maximum_residual_m < 0.03
    assert moved.worst_closure_constraint in (
        moved.diagnostics.per_constraint_residual_m
    )


def test_previous_passive_angles_are_explicit_and_reusable(
    kinematics: DropbearUsdKinematics,
    rest_result,
) -> None:
    values = np.zeros(len(ACTION_NAMES), dtype=np.float64)
    values[0] = 0.04
    values[1] = -0.03
    first = kinematics.solve(
        values,
        previous_passive_angles=rest_result.passive_angles,
    )
    second = kinematics.solve(
        values,
        previous_passive_angles=first.passive_angles,
    )
    assert set(second.passive_angles) == set(kinematics.passive_joint_names)
    assert second.maximum_closure_residual_m <= (
        first.maximum_closure_residual_m + 1e-9
    )


@pytest.mark.parametrize(
    "values",
    (
        [0.0] * 21,
        [0.0] * 21 + [math.nan],
        {"left_outer_calf": 0.0},
    ),
)
def test_motor_contract_rejects_malformed_inputs(
    kinematics: DropbearUsdKinematics,
    values,
) -> None:
    with pytest.raises(DropbearKinematicsError):
        kinematics.solve(values)


def test_passive_seed_rejects_unknown_or_non_finite_values(
    kinematics: DropbearUsdKinematics,
) -> None:
    with pytest.raises(DropbearKinematicsError, match="unknown passive"):
        kinematics.solve([0.0] * 22, {"not_a_joint": 0.0})
    with pytest.raises(DropbearKinematicsError, match="finite angle"):
        kinematics.solve(
            [0.0] * 22,
            {kinematics.passive_joint_names[0]: math.inf},
        )
