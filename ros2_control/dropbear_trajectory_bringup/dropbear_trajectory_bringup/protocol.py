"""Dependency-free validation for the dashboard/ROS 2 trajectory protocol."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping


SCHEMA = "dropbear-ros2-passthrough-v1"
JOINT_NAMES = (
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
)
JOINT_SET = frozenset(JOINT_NAMES)
MAX_ABSOLUTE_POSITION_RAD = math.pi
JOINT_LIMITS_RAD = {
    "LL_knee_actuator_joint": (0.0, math.pi),
    "RL_knee_actuator_joint": (0.0, math.pi),
}
MAX_TRAJECTORY_DURATION_SEC = 120.0
MAX_POINTS = 500


class ProtocolError(ValueError):
    """A dashboard request is malformed or exceeds the SIL safety envelope."""


def _finite_vector(value: Any, field: str, expected: int) -> List[float]:
    if not isinstance(value, list) or len(value) != expected:
        raise ProtocolError(f"{field} must contain exactly {expected} values")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ProtocolError(f"{field} must contain only finite values")
    return result


def validate_trajectory(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and normalize a full twelve-axis trajectory request."""

    names = payload.get("joint_names")
    if not isinstance(names, list) or len(names) != len(JOINT_NAMES):
        raise ProtocolError("joint_names must contain all twelve Dropbear axes")
    if len(set(names)) != len(names) or frozenset(names) != JOINT_SET:
        raise ProtocolError("joint_names must be the exact unique Dropbear USD joint set")

    points = payload.get("points")
    if not isinstance(points, list) or not points or len(points) > MAX_POINTS:
        raise ProtocolError(f"points must contain between 1 and {MAX_POINTS} waypoints")

    normalized_points: List[Dict[str, Any]] = []
    previous_time = -1.0
    for index, point in enumerate(points):
        if not isinstance(point, Mapping):
            raise ProtocolError(f"point {index} must be an object")
        positions = _finite_vector(point.get("positions"), f"point {index} positions", len(names))
        for joint_name, position in zip(names, positions):
            lower, upper = JOINT_LIMITS_RAD.get(
                joint_name, (-MAX_ABSOLUTE_POSITION_RAD, MAX_ABSOLUTE_POSITION_RAD)
            )
            if position < lower or position > upper:
                raise ProtocolError(
                    f"point {index} {joint_name} exceeds its {lower:.6f}…{upper:.6f} rad envelope"
                )
        time_from_start = float(point.get("time_from_start", 0.0))
        if not math.isfinite(time_from_start) or time_from_start <= previous_time:
            raise ProtocolError("time_from_start values must be finite and strictly increasing")
        if time_from_start < 0.02 or time_from_start > MAX_TRAJECTORY_DURATION_SEC:
            raise ProtocolError("time_from_start must remain within 0.02–120 seconds")
        previous_time = time_from_start
        normalized = {"positions": positions, "time_from_start": time_from_start}
        if "velocities" in point and point["velocities"] is not None:
            normalized["velocities"] = _finite_vector(
                point["velocities"], f"point {index} velocities", len(names)
            )
        if "accelerations" in point and point["accelerations"] is not None:
            normalized["accelerations"] = _finite_vector(
                point["accelerations"], f"point {index} accelerations", len(names)
            )
        normalized_points.append(normalized)

    request_id = str(payload.get("request_id", ""))[:128]
    return {
        "request_id": request_id,
        "joint_names": list(names),
        "points": normalized_points,
    }
