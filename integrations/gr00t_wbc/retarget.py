"""Semantic G1-pose to Dropbear-motor retargeting at the VLA/WBC boundary.

The upstream GR00T VLA emits a 64-value motion token.  That token is *not* a
G1 joint vector and must never be relabelled as one.  A G1 SONIC decoder (or a
recorded G1 rollout driven by that decoder) first turns the token into the
canonical 29 body-joint positions below.  This module then converts those
decoded poses into the 22 commandable Dropbear motor coordinates.

The conversion is deliberately reduced-coordinate:

* only the 22 real motor coordinates are emitted;
* the knee and elbow motor commands are obtained by inverting the retained
  closed-linkage projections instead of commanding passive joints;
* calf pairs encode G1 ankle pitch/roll intent as common/differential crank
  motion; and
* every result is constrained to the normalized-action range accepted by the
  existing upstream action adapter before it reaches the ROS 2 safety guard.

Isaac/PhysX remains authoritative for the 93-body passive-joint solution and
contact response.  This dependency-free layer is the deterministic seed and
runtime contract around that solve, not a replacement for USD articulation IK.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any, Callable, Mapping, Sequence

from .action_adapter import UPSTREAM_ACTION_SEMANTICS, UpstreamSonicActionAdapter
from .closure_adapter import ClosureProjection, DropbearClosureAdapter
from .embodiment import ACTION_COUNT, ACTION_NAMES, CONTRACT, EmbodimentContractError


RETARGET_SCHEMA = "dropbear-g1-vla-semantic-retarget-v1"
SOURCE_POSE_SCHEMA = "unitree-g1-body-position-v1"
REFERENCE_SCHEMA = "dropbear-wbc-reference-v1"

# This is the body_actuated_joints order used by the pinned upstream
# G1SupplementalInfo.  It differs from the interleaved Isaac Lab order.
G1_BODY_JOINT_NAMES = (
    "left_hip_pitch_joint",
    "left_hip_roll_joint",
    "left_hip_yaw_joint",
    "left_knee_joint",
    "left_ankle_pitch_joint",
    "left_ankle_roll_joint",
    "right_hip_pitch_joint",
    "right_hip_roll_joint",
    "right_hip_yaw_joint",
    "right_knee_joint",
    "right_ankle_pitch_joint",
    "right_ankle_roll_joint",
    "waist_yaw_joint",
    "waist_roll_joint",
    "waist_pitch_joint",
    "left_shoulder_pitch_joint",
    "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint",
    "left_elbow_joint",
    "left_wrist_roll_joint",
    "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
    "right_shoulder_pitch_joint",
    "right_shoulder_roll_joint",
    "right_shoulder_yaw_joint",
    "right_elbow_joint",
    "right_wrist_roll_joint",
    "right_wrist_pitch_joint",
    "right_wrist_yaw_joint",
)

G1_MOTION_TOKEN_DIMENSION = 64
G1_SOURCE_ABSOLUTE_LIMIT_RAD = 4.0
UNREPRESENTED_G1_JOINTS = (
    "waist_yaw_joint",
    "waist_roll_joint",
    "waist_pitch_joint",
    "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
    "right_wrist_pitch_joint",
    "right_wrist_yaw_joint",
)


class RetargetingError(ValueError):
    """A source pose or requested retarget operation violates the contract."""


@dataclass(frozen=True)
class SemanticSaturation:
    """One source semantic that exceeded Dropbear's admitted action range."""

    semantic: str
    requested_rad: float
    achieved_rad: float
    reason: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "semantic": self.semantic,
            "requestedRad": self.requested_rad,
            "achievedRad": self.achieved_rad,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RetargetedPose:
    """A closure-aware absolute Dropbear motor reference."""

    joint_positions_rad: tuple[float, ...]
    normalized_actions: tuple[float, ...]
    closure: ClosureProjection
    semantic_targets_rad: Mapping[str, float]
    semantic_achieved_rad: Mapping[str, float]
    saturations: tuple[SemanticSaturation, ...]
    unrepresented_source_joints: tuple[str, ...] = UNREPRESENTED_G1_JOINTS

    def as_payload(self) -> dict[str, Any]:
        """Return the inspectable retarget result used by API/browser tooling."""

        return {
            "schema": RETARGET_SCHEMA,
            "source": {
                "schema": SOURCE_POSE_SCHEMA,
                "jointOrder": list(G1_BODY_JOINT_NAMES),
                "requiresDecodedG1Pose": True,
                "rawMotionTokenAccepted": False,
            },
            "target": {
                "jointOrder": list(ACTION_NAMES),
                "positionsRad": list(self.joint_positions_rad),
                "normalizedActions": list(self.normalized_actions),
                "actionSemantics": UPSTREAM_ACTION_SEMANTICS,
                "usdJointPositionsRad": dict(self.closure.usd_motor_positions),
                "passiveJointsCommandable": False,
            },
            "closure": {
                "maximumReducedResidualM": self.closure.maximum_residual_m,
                "allInValidatedDomain": self.closure.all_in_validated_domain,
                "fullPassiveProjectionAuthority": "Isaac/PhysX",
            },
            "semanticTargetsRad": dict(self.semantic_targets_rad),
            "semanticAchievedRad": dict(self.semantic_achieved_rad),
            "saturations": [row.as_payload() for row in self.saturations],
            "unrepresentedSourceJoints": list(self.unrepresented_source_joints),
            "hardwareAuthorized": False,
        }

    def wbc_reference_payload(
        self,
        *,
        session_id: str,
        sequence: int,
        source_token_sequence: int | None = None,
        generated_steady_time_ns: int | None = None,
    ) -> dict[str, Any]:
        """Emit the exact absolute-position frame accepted by the ROS 2 guard."""

        if not isinstance(session_id, str) or not session_id:
            raise RetargetingError("session_id is required")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise RetargetingError("sequence must be a non-negative integer")
        if source_token_sequence is not None and (
            isinstance(source_token_sequence, bool)
            or not isinstance(source_token_sequence, int)
            or source_token_sequence < 0
        ):
            raise RetargetingError(
                "source_token_sequence must be a non-negative integer"
            )
        generated = (
            time.monotonic_ns()
            if generated_steady_time_ns is None
            else generated_steady_time_ns
        )
        if isinstance(generated, bool) or not isinstance(generated, int) or generated < 0:
            raise RetargetingError(
                "generated_steady_time_ns must be a non-negative integer"
            )
        payload: dict[str, Any] = {
            "schema": REFERENCE_SCHEMA,
            "session_id": session_id,
            "sequence": sequence,
            "generated_steady_time_ns": generated,
            "joint_names": list(ACTION_NAMES),
            "positions": list(self.joint_positions_rad),
        }
        if source_token_sequence is not None:
            payload["source_token_sequence"] = source_token_sequence
        return payload


def _finite_pose_mapping(
    values: Mapping[str, float] | Sequence[float],
    source_joint_names: Sequence[str] | None,
) -> dict[str, float]:
    if isinstance(values, Mapping):
        if set(values) != set(G1_BODY_JOINT_NAMES):
            missing = sorted(set(G1_BODY_JOINT_NAMES) - set(values))
            extra = sorted(set(values) - set(G1_BODY_JOINT_NAMES))
            raise RetargetingError(
                f"G1 pose mapping mismatch; missing={missing}, extra={extra}"
            )
        result = {name: float(values[name]) for name in G1_BODY_JOINT_NAMES}
    else:
        names = tuple(source_joint_names or ())
        if names != G1_BODY_JOINT_NAMES:
            if len(values) == G1_MOTION_TOKEN_DIMENSION:
                raise RetargetingError(
                    "a 64-value VLA motion token is latent, not a G1 pose; "
                    "decode it through G1 SONIC before retargeting"
                )
            raise RetargetingError(
                "source_joint_names must exactly match the pinned 29-joint "
                "G1 body-actuated order"
            )
        if len(values) != len(G1_BODY_JOINT_NAMES):
            raise RetargetingError(
                f"G1 pose contains {len(values)} values, "
                f"expected {len(G1_BODY_JOINT_NAMES)}"
            )
        result = {
            name: float(value)
            for name, value in zip(G1_BODY_JOINT_NAMES, values)
        }
    if not all(math.isfinite(value) for value in result.values()):
        raise RetargetingError("G1 pose must contain only finite values")
    if any(abs(value) > G1_SOURCE_ABSOLUTE_LIMIT_RAD for value in result.values()):
        raise RetargetingError(
            "G1 pose exceeds the bounded decoded-source envelope "
            f"of +/-{G1_SOURCE_ABSOLUTE_LIMIT_RAD:.1f} rad"
        )
    return result


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _inverse_monotone(
    function: Callable[[float], float],
    requested: float,
    lower: float,
    upper: float,
) -> tuple[float, float, bool]:
    """Invert a monotone scalar projection and report boundary saturation."""

    low_value = function(lower)
    high_value = function(upper)
    increasing = high_value >= low_value
    minimum, maximum = sorted((low_value, high_value))
    target = _clamp(requested, minimum, maximum)
    low, high = lower, upper
    for _ in range(56):
        middle = 0.5 * (low + high)
        value = function(middle)
        if (value < target) == increasing:
            low = middle
        else:
            high = middle
    position = 0.5 * (low + high)
    achieved = function(position)
    return position, achieved, not math.isclose(
        requested,
        target,
        rel_tol=0.0,
        abs_tol=1e-8,
    )


class G1VlaDropbearRetargeter:
    """Retarget decoded G1 SONIC poses into the Dropbear action surface."""

    # Calf motor-radian seed gains.  The full 93-body USD IK/PhysX solve
    # refines these common/differential crank targets during embodiment
    # training.  Keeping them explicit makes the bootstrap deterministic.
    ANKLE_PITCH_TO_CALF_COMMON = -0.115
    ANKLE_ROLL_TO_CALF_DIFFERENTIAL = 0.115

    def __init__(self, project_root: Any | None = None) -> None:
        self.action = UpstreamSonicActionAdapter(project_root)
        self.closure = DropbearClosureAdapter(project_root)
        self._index = {name: index for index, name in enumerate(ACTION_NAMES)}
        self._effective_limits = tuple(
            (
                max(position_limit[0], center - scale),
                min(position_limit[1], center + scale),
            )
            for center, scale, position_limit in zip(
                self.action.centers,
                self.action.scales,
                self.action.limits,
            )
        )

    def _set_direct(
        self,
        positions: list[float],
        saturations: list[SemanticSaturation],
        target_name: str,
        source_name: str,
        requested: float,
    ) -> float:
        index = self._index[target_name]
        lower, upper = self._effective_limits[index]
        achieved = _clamp(requested, lower, upper)
        positions[index] = achieved
        if not math.isclose(requested, achieved, rel_tol=0.0, abs_tol=1e-8):
            saturations.append(
                SemanticSaturation(
                    semantic=source_name,
                    requested_rad=requested,
                    achieved_rad=achieved,
                    reason=f"{target_name} normalized-action range",
                )
            )
        return achieved

    def _set_calf_pair(
        self,
        positions: list[float],
        saturations: list[SemanticSaturation],
        *,
        side: str,
        ankle_pitch: float,
        ankle_roll: float,
    ) -> tuple[float, float]:
        common = ankle_pitch * self.ANKLE_PITCH_TO_CALF_COMMON
        differential = ankle_roll * self.ANKLE_ROLL_TO_CALF_DIFFERENTIAL
        # Mirrored ankle geometry reverses the right-side differential.
        if side == "right":
            differential = -differential
        outer = common + differential
        inner = common - differential
        maximum = max(abs(outer), abs(inner), 1e-12)
        pair_limits = (
            self._effective_limits[self._index[f"{side}_outer_calf"]],
            self._effective_limits[self._index[f"{side}_inner_calf"]],
        )
        pair_limit = min(
            min(abs(lower), abs(upper))
            for lower, upper in pair_limits
        )
        if maximum > pair_limit:
            factor = pair_limit / maximum
            outer *= factor
            inner *= factor
            saturations.append(
                SemanticSaturation(
                    semantic=f"{side}_ankle_pitch_roll",
                    requested_rad=maximum,
                    achieved_rad=pair_limit,
                    reason="paired calf normalized-action range",
                )
            )
        outer = self._set_direct(
            positions,
            saturations,
            f"{side}_outer_calf",
            f"{side}_ankle_pitch_roll",
            outer,
        )
        inner = self._set_direct(
            positions,
            saturations,
            f"{side}_inner_calf",
            f"{side}_ankle_pitch_roll",
            inner,
        )
        common = 0.5 * (outer + inner)
        differential = 0.5 * (outer - inner)
        return common, differential

    def _set_knee(
        self,
        positions: list[float],
        saturations: list[SemanticSaturation],
        *,
        side: str,
        hip_pitch: float,
        requested_flexion: float,
    ) -> float:
        name = f"{side}_knee"
        index = self._index[name]
        lower, upper = self._effective_limits[index]
        lock_output = self.closure._project_leg(side, hip_pitch, 0.0).output_angle_rad

        def flexion(motor: float) -> float:
            output = self.closure._project_leg(
                side,
                hip_pitch,
                motor,
            ).output_angle_rad
            return output - lock_output

        requested = max(0.0, requested_flexion)
        motor, achieved, saturated = _inverse_monotone(
            flexion,
            requested,
            lower,
            upper,
        )
        positions[index] = motor
        if requested_flexion < 0.0 or saturated:
            saturations.append(
                SemanticSaturation(
                    semantic=f"{side}_knee_flexion",
                    requested_rad=requested_flexion,
                    achieved_rad=achieved,
                    reason="knee lock/closed-linkage action range",
                )
            )
        return achieved

    def _set_elbow(
        self,
        positions: list[float],
        saturations: list[SemanticSaturation],
        *,
        side: str,
        requested_flexion: float,
    ) -> float:
        name = f"{side}_elbow_pitch"
        index = self._index[name]
        lower, upper = self._effective_limits[index]

        def flexion(motor: float) -> float:
            return self.closure._project_elbow(
                side,
                motor,
            ).output_angle_rad

        motor, achieved, saturated = _inverse_monotone(
            flexion,
            max(0.0, requested_flexion),
            lower,
            upper,
        )
        positions[index] = motor
        if requested_flexion < 0.0 or saturated:
            saturations.append(
                SemanticSaturation(
                    semantic=f"{side}_elbow_flexion",
                    requested_rad=requested_flexion,
                    achieved_rad=achieved,
                    reason="elbow closed-linkage action range",
                )
            )
        return achieved

    def retarget_g1_pose(
        self,
        source_positions_rad: Mapping[str, float] | Sequence[float],
        *,
        source_joint_names: Sequence[str] | None = None,
    ) -> RetargetedPose:
        """Retarget one decoded G1 body pose into a safe Dropbear reference."""

        source = _finite_pose_mapping(source_positions_rad, source_joint_names)
        positions = list(self.action.centers)
        saturations: list[SemanticSaturation] = []
        targets: dict[str, float] = {}
        achieved: dict[str, float] = {}

        direct = {
            "left_hip_pitch": "left_hip_pitch_joint",
            "left_hip_roll": "left_hip_roll_joint",
            "left_hip_yaw": "left_hip_yaw_joint",
            "right_hip_pitch": "right_hip_pitch_joint",
            "right_hip_roll": "right_hip_roll_joint",
            "right_hip_yaw": "right_hip_yaw_joint",
            "left_shoulder_pitch": "left_shoulder_pitch_joint",
            "left_shoulder_roll": "left_shoulder_roll_joint",
            "left_shoulder_yaw": "left_shoulder_yaw_joint",
            "left_wrist_roll": "left_wrist_roll_joint",
            "right_shoulder_pitch": "right_shoulder_pitch_joint",
            "right_shoulder_roll": "right_shoulder_roll_joint",
            "right_shoulder_yaw": "right_shoulder_yaw_joint",
            "right_wrist_roll": "right_wrist_roll_joint",
        }
        for target_name, source_name in direct.items():
            requested = source[source_name]
            targets[source_name] = requested
            achieved[source_name] = self._set_direct(
                positions,
                saturations,
                target_name,
                source_name,
                requested,
            )

        for side in ("left", "right"):
            ankle_pitch_name = f"{side}_ankle_pitch_joint"
            ankle_roll_name = f"{side}_ankle_roll_joint"
            targets[ankle_pitch_name] = source[ankle_pitch_name]
            targets[ankle_roll_name] = source[ankle_roll_name]
            common, differential = self._set_calf_pair(
                positions,
                saturations,
                side=side,
                ankle_pitch=source[ankle_pitch_name],
                ankle_roll=source[ankle_roll_name],
            )
            achieved[ankle_pitch_name] = (
                common / self.ANKLE_PITCH_TO_CALF_COMMON
            )
            mirrored = -differential if side == "right" else differential
            achieved[ankle_roll_name] = (
                mirrored / self.ANKLE_ROLL_TO_CALF_DIFFERENTIAL
            )

            knee_name = f"{side}_knee_joint"
            targets[knee_name] = source[knee_name]
            achieved[knee_name] = self._set_knee(
                positions,
                saturations,
                side=side,
                hip_pitch=positions[self._index[f"{side}_hip_pitch"]],
                requested_flexion=source[knee_name],
            )

            elbow_name = f"{side}_elbow_joint"
            targets[elbow_name] = source[elbow_name]
            achieved[elbow_name] = self._set_elbow(
                positions,
                saturations,
                side=side,
                requested_flexion=source[elbow_name],
            )

        normalized = tuple(
            _clamp((position - center) / scale, -1.0, 1.0)
            for position, center, scale in zip(
                positions,
                self.action.centers,
                self.action.scales,
            )
        )
        # Decode through the existing adapter so there is exactly one formula
        # between retargeting and the 22-axis deployment path.
        decoded = self.action.decode(normalized)
        if any(
            not math.isclose(expected, actual, rel_tol=0.0, abs_tol=1e-9)
            for expected, actual in zip(positions, decoded)
        ):
            raise EmbodimentContractError(
                "retargeted motor pose is not representable by the action adapter"
            )
        closure = self.closure.project(decoded)
        if not closure.all_in_validated_domain:
            raise EmbodimentContractError(
                "retargeted pose leaves a validated closed-linkage domain"
            )
        return RetargetedPose(
            joint_positions_rad=decoded,
            normalized_actions=normalized,
            closure=closure,
            semantic_targets_rad=targets,
            semantic_achieved_rad=achieved,
            saturations=tuple(saturations),
        )

    def retarget_chunk(
        self,
        source_frames_rad: Sequence[Mapping[str, float] | Sequence[float]],
        *,
        source_joint_names: Sequence[str] | None = None,
        maximum_frames: int = 256,
    ) -> tuple[RetargetedPose, ...]:
        """Retarget one finite decoded G1 action/pose horizon."""

        if (
            isinstance(maximum_frames, bool)
            or not isinstance(maximum_frames, int)
            or maximum_frames <= 0
        ):
            raise RetargetingError("maximum_frames must be a positive integer")
        if not source_frames_rad or len(source_frames_rad) > maximum_frames:
            raise RetargetingError(
                f"decoded G1 chunk must contain 1..{maximum_frames} frames"
            )
        return tuple(
            self.retarget_g1_pose(
                frame,
                source_joint_names=source_joint_names,
            )
            for frame in source_frames_rad
        )


def retargeting_contract() -> dict[str, Any]:
    """Return the explicit online/offline bridge contract."""

    return {
        "schema": RETARGET_SCHEMA,
        "source": {
            "schema": SOURCE_POSE_SCHEMA,
            "jointOrder": list(G1_BODY_JOINT_NAMES),
            "origin": "decoded G1 SONIC body pose driven by VLA motion token",
            "rawMotionTokenAccepted": False,
            "motionTokenDimension": G1_MOTION_TOKEN_DIMENSION,
            "handOutputsRepresented": False,
        },
        "target": {
            "jointOrder": list(ACTION_NAMES),
            "actionCount": ACTION_COUNT,
            "actionSemantics": UPSTREAM_ACTION_SEMANTICS,
            "referenceSchema": REFERENCE_SCHEMA,
            "passiveJointsCommandable": False,
        },
        "pipeline": [
            "Isaac-GR00T VLA prompt/image/state -> 64D motion token",
            "pinned G1 SONIC shadow decoder -> canonical 29D G1 body pose",
            "semantic retarget + closed-linkage inverse -> 22D Dropbear motor pose",
            "Dropbear USD Isaac/PhysX passive solve and contact validation",
            "ROS 2 Dropbear WBC safety guard -> actuator reference",
        ],
        "fullPassiveProjectionAuthority": "Isaac/PhysX",
        "unrepresentedSourceSemantics": [
            *UNREPRESENTED_G1_JOINTS,
            "left_hand_7dof",
            "right_hand_7dof",
        ],
        "hardwareAuthorized": CONTRACT["runtimeParameters"][
            "hardwareDeploymentAllowed"
        ],
    }
