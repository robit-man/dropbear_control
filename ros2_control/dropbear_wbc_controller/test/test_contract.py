import math

import pytest

from dropbear_wbc_controller.contract import (
    AUTHORITY,
    CANONICAL_JOINT_ORDER,
    JOINT_COUNT,
    ActivationRequest,
    ContractError,
    JointReferenceFrame,
    MotionTokenFrame,
    RobotStateFrame,
)


def zeroes(count=JOINT_COUNT):
    return tuple(0.0 for _ in range(count))


def test_canonical_order_is_22_motor_coordinates():
    assert JOINT_COUNT == 22
    assert CANONICAL_JOINT_ORDER[:4] == (
        "left_outer_calf",
        "left_inner_calf",
        "right_inner_calf",
        "right_outer_calf",
    )
    assert CANONICAL_JOINT_ORDER[-2:] == (
        "right_elbow_pitch",
        "right_wrist_roll",
    )
    assert not any("passive" in name for name in CANONICAL_JOINT_ORDER)


def test_motion_token_json_round_trip():
    frame = MotionTokenFrame(
        session_id="run-1",
        sequence=4,
        generated_steady_time_ns=100,
        token=tuple(float(index) / 64.0 for index in range(64)),
        source="tensorrt",
    )
    assert MotionTokenFrame.from_dict(frame.to_dict()) == frame


def test_token_must_be_exactly_64_finite_values():
    with pytest.raises(ContractError, match="exactly 64"):
        MotionTokenFrame("run", 0, 0, (0.0,) * 63)
    with pytest.raises(ContractError, match="finite"):
        MotionTokenFrame("run", 0, 0, (0.0,) * 63 + (math.nan,))


def test_reference_round_trip_and_exact_order():
    frame = JointReferenceFrame(
        session_id="run",
        sequence=3,
        generated_steady_time_ns=200,
        positions=zeroes(),
        velocities=zeroes(),
        source_token_sequence=8,
    )
    assert JointReferenceFrame.from_dict(frame.to_dict()) == frame

    payload = frame.to_dict()
    payload["joint_names"][0], payload["joint_names"][1] = (
        payload["joint_names"][1],
        payload["joint_names"][0],
    )
    with pytest.raises(ContractError, match="canonical 22-axis"):
        JointReferenceFrame.from_dict(payload)


def test_state_round_trip_and_quaternion_guard():
    state = RobotStateFrame(
        source_id="isaac",
        sequence=1,
        observed_steady_time_ns=100,
        positions=zeroes(),
        velocities=zeroes(),
        foot_force_n=(120.0, 118.0),
    )
    assert RobotStateFrame.from_dict(state.to_dict()) == state
    with pytest.raises(ContractError, match="quaternion norm"):
        RobotStateFrame(
            source_id="isaac",
            sequence=2,
            observed_steady_time_ns=101,
            positions=zeroes(),
            velocities=zeroes(),
            base_quaternion_wxyz=(0.0, 0.0, 0.0, 0.0),
        )


def test_activation_is_explicitly_sil_only_and_guarded():
    request = ActivationRequest(
        session_id="run",
        sequence=1,
        issued_steady_time_ns=100,
        guarded_confirmation=ActivationRequest.CONFIRMATION,
    )
    assert request.to_dict()["authority"] == AUTHORITY
    with pytest.raises(ContractError, match="confirmation"):
        ActivationRequest("run", 1, 100, "yes")
    with pytest.raises(ContractError, match="sil_only"):
        ActivationRequest(
            "run",
            1,
            100,
            ActivationRequest.CONFIRMATION,
            authority="hardware",
        )
