import math

import pytest

from dropbear_trajectory_bringup.protocol import (
    JOINT_NAMES,
    ProtocolError,
    SCHEMA,
    validate_trajectory,
)


def request():
    return {
        "type": "follow_joint_trajectory",
        "request_id": "test-goal",
        "joint_names": list(JOINT_NAMES),
        "points": [
            {"positions": [0.0] * 12, "time_from_start": 0.5},
            {"positions": [0.1] * 12, "time_from_start": 1.5},
        ],
    }


def test_schema_and_exact_joint_order():
    assert SCHEMA == "dropbear-ros2-passthrough-v1"
    assert len(JOINT_NAMES) == 12
    assert JOINT_NAMES[:4] == (
        "LL_Revolute81",
        "LL_Revolute67",
        "RL_Revolute67",
        "RL_Revolute81",
    )
    normalized = validate_trajectory(request())
    assert normalized["joint_names"] == list(JOINT_NAMES)
    assert normalized["points"][1]["positions"] == [0.1] * 12


def test_arbitrary_complete_joint_order_is_accepted():
    payload = request()
    payload["joint_names"].reverse()
    assert validate_trajectory(payload)["joint_names"] == payload["joint_names"]


def test_knee_lock_rejects_negative_ros_coordinate():
    payload = request()
    payload["points"][0]["positions"][4] = -0.001
    with pytest.raises(ProtocolError, match="LL_knee_actuator_joint"):
        validate_trajectory(payload)


def test_non_knee_joint_still_accepts_negative_coordinate():
    payload = request()
    payload["points"][0]["positions"][0] = -0.5
    assert validate_trajectory(payload)["points"][0]["positions"][0] == -0.5


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["joint_names"].pop(),
        lambda value: value["joint_names"].__setitem__(0, "not_a_dropbear_joint"),
        lambda value: value["points"][0]["positions"].pop(),
        lambda value: value["points"][0]["positions"].__setitem__(0, math.nan),
        lambda value: value["points"][0]["positions"].__setitem__(0, math.pi + 0.01),
        lambda value: value["points"][1].__setitem__("time_from_start", 0.4),
    ],
)
def test_invalid_trajectory_is_denied(mutate):
    payload = request()
    mutate(payload)
    with pytest.raises(ProtocolError):
        validate_trajectory(payload)
