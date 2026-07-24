"""Task-space G1-to-Dropbear retargeting against the retained USD graph.

This is the geometry stage between the released G1 SONIC decoder and a future
native Dropbear decoder.  It does not copy G1 joint angles into Dropbear.  It:

1. evaluates the decoded 29-joint G1 pose in the pinned G1 MJCF tree;
2. converts motion relative to the released G1 standing pose into normalized
   foot, lower-leg, forearm, and wrist body targets, with scale measured from
   corresponding hip/shoulder motor anchors rather than either robot's root;
3. evaluates candidate 22-motor poses through the retained 93-body Dropbear
   articulation and all browser-projected knee/calf/elbow loop closures; and
4. applies bounded damped least-squares updates to reduce body-space error.

The result is a deterministic non-real-time preview and an offline teacher-data
seed.  A refined frame currently requires many full passive-closure solves; it
is not the 50 Hz production decoder.  Isaac/PhysX must still settle
collision/contact and validate force-level loop constraints before a frame can
become authoritative training data.
"""

from __future__ import annotations

from dataclasses import dataclass
import functools
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .action_adapter import UpstreamSonicActionAdapter
from .closure_adapter import DropbearClosureAdapter
from .embodiment import (
    ACTION_NAMES,
    CONTRACT,
    USD_JOINT_NAMES,
    SourceVerification,
    verify_source_assets,
)
from .g1_kinematics import (
    G1Kinematics,
    G1KinematicsResult,
    G1_RELEASE_STANDING_POSE_RAD,
)
from .retarget import (
    G1_BODY_JOINT_NAMES,
    G1VlaDropbearRetargeter,
    RetargetedPose,
    RetargetingError,
)
from .usd_kinematics import DropbearUsdKinematics, KinematicsResult


USD_RETARGET_SCHEMA = "dropbear-g1-usd-task-retarget-v1"


def _source_asset_signature(root: Path) -> tuple[tuple[str, int, int, int], ...]:
    """Return a stat key that invalidates the expensive source hash cache."""

    rows: list[tuple[str, int, int, int]] = []
    for artifact in CONTRACT["sourceAssets"]:
        path = root / artifact["path"]
        try:
            stat = path.stat()
        except OSError:
            # Preserve the useful fail-closed error from the full verifier.
            return ()
        rows.append(
            (
                artifact["path"],
                stat.st_size,
                stat.st_mtime_ns,
                stat.st_ctime_ns,
            )
        )
    return tuple(rows)


@functools.lru_cache(maxsize=8)
def _verified_source_snapshot(
    root_text: str,
    signature: tuple[tuple[str, int, int, int], ...],
) -> SourceVerification:
    del signature
    return verify_source_assets(Path(root_text))


def _verify_retained_source(root: Path) -> SourceVerification:
    return _verified_source_snapshot(
        str(root.resolve()),
        _source_asset_signature(root),
    )


@dataclass(frozen=True)
class _BodyTask:
    dropbear_body: str
    g1_body: str
    g1_reference: str
    g1_scale_anchor_body: str
    dropbear_scale_anchor_action: str
    position_weight: float
    orientation_weight: float


_BODY_TASKS = (
    _BodyTask(
        "left_lower_leg",
        "left_knee",
        "core",
        "left_hip_pitch_link",
        "left_hip_pitch",
        3.0,
        0.30,
    ),
    _BodyTask(
        "right_lower_leg",
        "right_knee",
        "core",
        "right_hip_pitch_link",
        "right_hip_pitch",
        3.0,
        0.30,
    ),
    _BodyTask(
        "left_foot",
        "left_foot",
        "core",
        "left_hip_pitch_link",
        "left_hip_pitch",
        7.0,
        0.85,
    ),
    _BodyTask(
        "right_foot",
        "right_foot",
        "core",
        "right_hip_pitch_link",
        "right_hip_pitch",
        7.0,
        0.85,
    ),
    _BodyTask(
        "left_upper_arm",
        "left_shoulder",
        "torso",
        "left_shoulder_pitch_link",
        "left_shoulder_pitch",
        1.5,
        0.22,
    ),
    _BodyTask(
        "right_upper_arm",
        "right_shoulder",
        "torso",
        "right_shoulder_pitch_link",
        "right_shoulder_pitch",
        1.5,
        0.22,
    ),
    _BodyTask(
        "left_forearm",
        "left_elbow",
        "torso",
        "left_shoulder_pitch_link",
        "left_shoulder_pitch",
        3.0,
        0.30,
    ),
    _BodyTask(
        "right_forearm",
        "right_elbow",
        "torso",
        "right_shoulder_pitch_link",
        "right_shoulder_pitch",
        3.0,
        0.30,
    ),
    _BodyTask(
        "left_wrist",
        "left_wrist",
        "torso",
        "left_shoulder_pitch_link",
        "left_shoulder_pitch",
        5.0,
        0.45,
    ),
    _BodyTask(
        "right_wrist",
        "right_wrist",
        "torso",
        "right_shoulder_pitch_link",
        "right_shoulder_pitch",
        5.0,
        0.45,
    ),
)


@dataclass(frozen=True)
class BodyTargetDiagnostic:
    target: str
    source: str
    target_position_m: tuple[float, float, float]
    achieved_position_m: tuple[float, float, float]
    position_error_m: float
    orientation_error_rad: float

    def as_payload(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "source": self.source,
            "targetPositionM": list(self.target_position_m),
            "achievedPositionM": list(self.achieved_position_m),
            "positionErrorM": self.position_error_m,
            "orientationErrorRad": self.orientation_error_rad,
        }


@dataclass(frozen=True)
class UsdRetargetDiagnostics:
    iterations_requested: int
    iterations_accepted: int
    seed_task_error: float
    final_task_error: float
    maximum_closure_residual_m: float
    worst_closure_constraint: str | None
    body_targets: tuple[BodyTargetDiagnostic, ...]
    source_torso_delta_rotation_matrix: tuple[float, ...]
    stance_contacts: Mapping[str, bool]

    @property
    def improved(self) -> bool:
        return self.final_task_error <= self.seed_task_error + 1e-10

    def as_payload(self) -> dict[str, Any]:
        return {
            "iterationsRequested": self.iterations_requested,
            "iterationsAccepted": self.iterations_accepted,
            "seedTaskError": self.seed_task_error,
            "finalTaskError": self.final_task_error,
            "improved": self.improved,
            "maximumClosureResidualM": self.maximum_closure_residual_m,
            "worstClosureConstraint": self.worst_closure_constraint,
            "bodyTargets": [row.as_payload() for row in self.body_targets],
            "sourceTorsoDeltaRotationMatrix": list(
                self.source_torso_delta_rotation_matrix
            ),
            "sourceTorsoDeltaApplied": False,
            "stanceContacts": dict(self.stance_contacts),
            "stanceContactUse": "task weighting only; no contact solve",
        }


@dataclass(frozen=True)
class UsdRetargetedPose:
    """One 22-motor reference refined through the retained USD articulation."""

    pose: RetargetedPose
    usd_solution: KinematicsResult
    diagnostics: UsdRetargetDiagnostics
    source_verification: Mapping[str, Any]

    @property
    def joint_positions_rad(self) -> tuple[float, ...]:
        return self.pose.joint_positions_rad

    @property
    def normalized_actions(self) -> tuple[float, ...]:
        return self.pose.normalized_actions

    def as_payload(self) -> dict[str, Any]:
        payload = self.pose.as_payload()
        payload["schema"] = USD_RETARGET_SCHEMA
        payload["usdTaskSpace"] = {
            **self.diagnostics.as_payload(),
            "solver": (
                "retained USD spanning-tree FK + passive-loop DLS + "
                "bounded motor-space DLS"
            ),
            "semanticBodyPaths": dict(self.usd_solution.semantic_body_paths),
            "passiveAnglesRad": dict(self.usd_solution.passive_angles_rad),
            "usdGeometryApplied": True,
            "kinematicsAuthoritative": False,
            "kinematicsModel": (
                "retained browser articulation spanning tree with "
                "passive-loop DLS"
            ),
            "contactDynamicsAuthoritative": False,
            "physxValidationRequired": True,
            "realTimeCapable": False,
            "semanticAngleFieldsDescribeSeed": True,
            "sourceVerification": dict(self.source_verification),
        }
        payload["hardwareAuthorized"] = False
        return payload

    def wbc_reference_payload(self, **kwargs: Any) -> dict[str, Any]:
        return self.pose.wbc_reference_payload(**kwargs)


def _rotation_log(rotation: np.ndarray) -> np.ndarray:
    cosine = max(-1.0, min(1.0, 0.5 * (float(np.trace(rotation)) - 1.0)))
    angle = math.acos(cosine)
    if angle < 1e-9:
        return np.asarray(
            (
                0.5 * (rotation[2, 1] - rotation[1, 2]),
                0.5 * (rotation[0, 2] - rotation[2, 0]),
                0.5 * (rotation[1, 0] - rotation[0, 1]),
            ),
            dtype=np.float64,
        )
    sine = math.sin(angle)
    if abs(sine) < 1e-8:
        values, vectors = np.linalg.eigh(0.5 * (rotation + np.eye(3)))
        axis = vectors[:, int(np.argmax(values))]
        return axis * angle
    axis = np.asarray(
        (
            rotation[2, 1] - rotation[1, 2],
            rotation[0, 2] - rotation[2, 0],
            rotation[1, 0] - rotation[0, 1],
        ),
        dtype=np.float64,
    ) / (2.0 * sine)
    return axis * angle


def _relative(matrix: np.ndarray, reference: np.ndarray) -> np.ndarray:
    return np.linalg.inv(reference) @ matrix


class G1UsdDropbearRetargeter:
    """Refine decoded G1 poses against Dropbear's retained USD body graph."""

    def __init__(self, project_root: Path | str | None = None) -> None:
        self.project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[2]
        )
        self.source_verification = _verify_retained_source(self.project_root)
        self.action = UpstreamSonicActionAdapter(self.project_root)
        self.closure = DropbearClosureAdapter(self.project_root)
        self.seed = G1VlaDropbearRetargeter(self.project_root)
        self.g1 = G1Kinematics(self.project_root)
        self.usd = DropbearUsdKinematics(self.project_root)
        self._g1_neutral = self.g1.forward(G1_RELEASE_STANDING_POSE_RAD)
        self._dropbear_neutral = self.usd.solve(self.action.centers)
        self._usd_joint_for_action = dict(zip(ACTION_NAMES, USD_JOINT_NAMES))
        self._motion_scales = self._calculate_motion_scales()
        self._lower = np.asarray(
            [
                max(limit[0], center - scale)
                for limit, center, scale in zip(
                    self.action.limits,
                    self.action.centers,
                    self.action.scales,
                )
            ],
            dtype=np.float64,
        )
        self._upper = np.asarray(
            [
                min(limit[1], center + scale)
                for limit, center, scale in zip(
                    self.action.limits,
                    self.action.centers,
                    self.action.scales,
                )
            ],
            dtype=np.float64,
        )
        self._scales = np.asarray(self.action.scales, dtype=np.float64)

    def source_verification_payload(self) -> dict[str, Any]:
        """Describe the source lock proven before this solver was created."""

        return {
            "schema": "dropbear-retarget-source-verification-v1",
            "verified": True,
            "authoritativeUsdRequired": True,
            "solverInput": "source-locked derived articulation cache",
            "assetCount": len(self.source_verification.verified_paths),
            "assets": [
                {
                    "role": artifact["role"],
                    "path": artifact["path"],
                    "sha256": artifact["sha256"],
                }
                for artifact in CONTRACT["sourceAssets"]
            ],
        }

    def _calculate_motion_scales(self) -> Mapping[str, float]:
        """Measure corresponding limb radii without including root height.

        Pose deltas remain expressed in the G1 core/torso frame, which retains
        hip and shoulder motion.  Only the scale is measured from the
        corresponding proximal actuator anchor to the task body.  Measuring
        root-to-wrist would incorrectly include Dropbear's full torso height
        and amplify arm motion by roughly seven times.
        """

        scales: dict[str, float] = {}
        for task in _BODY_TASKS:
            source_anchor = self._g1_neutral.body_matrices[
                task.g1_scale_anchor_body
            ][:3, 3]
            source_endpoint = self._g1_neutral.semantic_body_position(
                task.g1_body
            )
            target_joint = self._usd_joint_for_action[
                task.dropbear_scale_anchor_action
            ]
            target_anchor = self._dropbear_neutral.joint_anchor_world(
                target_joint
            )
            target_endpoint = self._dropbear_neutral.semantic_body_position(
                task.dropbear_body
            )
            source_length = float(np.linalg.norm(source_endpoint - source_anchor))
            target_length = float(np.linalg.norm(target_endpoint - target_anchor))
            if source_length < 0.02 or target_length < 0.02:
                raise RetargetingError(
                    f"degenerate retarget scale for {task.dropbear_body!r}"
                )
            scale = target_length / source_length
            if not math.isfinite(scale) or not 0.25 <= scale <= 4.0:
                raise RetargetingError(
                    f"implausible retarget scale {scale:.6f} for "
                    f"{task.dropbear_body!r}"
                )
            scales[task.dropbear_body] = scale
        return scales

    @staticmethod
    def _contacts(
        contacts: Mapping[str, bool] | None,
    ) -> dict[str, bool]:
        if contacts is None:
            return {"left": False, "right": False}
        if set(contacts) != {"left", "right"}:
            raise RetargetingError(
                "stance_contacts must contain exact left/right boolean keys"
            )
        if not all(isinstance(value, bool) for value in contacts.values()):
            raise RetargetingError("stance_contacts values must be booleans")
        return dict(contacts)

    def _target_matrices(
        self,
        source: G1KinematicsResult,
    ) -> tuple[dict[str, np.ndarray], np.ndarray]:
        targets: dict[str, np.ndarray] = {}
        for task in _BODY_TASKS:
            current_reference = source.semantic_body_transform(task.g1_reference)
            neutral_reference = self._g1_neutral.semantic_body_transform(
                task.g1_reference
            )
            current = _relative(
                source.semantic_body_transform(task.g1_body),
                current_reference,
            )
            neutral = _relative(
                self._g1_neutral.semantic_body_transform(task.g1_body),
                neutral_reference,
            )
            drop_reference = self._dropbear_neutral.semantic_body_transform(
                "core"
            )
            drop_neutral = _relative(
                self._dropbear_neutral.semantic_body_transform(
                    task.dropbear_body
                ),
                drop_reference,
            )
            scale = self._motion_scales[task.dropbear_body]
            target = drop_neutral.copy()
            target[:3, 3] += scale * (current[:3, 3] - neutral[:3, 3])
            reference_delta = current[:3, :3] @ neutral[:3, :3].T
            target[:3, :3] = reference_delta @ drop_neutral[:3, :3]
            targets[task.dropbear_body] = drop_reference @ target

        g1_root = source.semantic_body_transform("core")
        g1_torso = source.semantic_body_transform("torso")
        neutral_root = self._g1_neutral.semantic_body_transform("core")
        neutral_torso = self._g1_neutral.semantic_body_transform("torso")
        torso_delta = (
            _relative(g1_torso, g1_root)[:3, :3]
            @ _relative(neutral_torso, neutral_root)[:3, :3].T
        )
        return targets, torso_delta

    def _task_residual(
        self,
        solution: KinematicsResult,
        q: np.ndarray,
        *,
        targets: Mapping[str, np.ndarray],
        seed_q: np.ndarray,
        previous_q: np.ndarray | None,
        contacts: Mapping[str, bool],
    ) -> np.ndarray:
        residual: list[float] = []
        for task in _BODY_TASKS:
            achieved = solution.semantic_body_transform(task.dropbear_body)
            target = targets[task.dropbear_body]
            stance_scale = (
                1.8
                if task.dropbear_body.endswith("_foot")
                and contacts[task.dropbear_body.split("_", 1)[0]]
                else 1.0
            )
            residual.extend(
                (
                    (achieved[:3, 3] - target[:3, 3])
                    * task.position_weight
                    * stance_scale
                ).tolist()
            )
            orientation_error = _rotation_log(
                target[:3, :3].T @ achieved[:3, :3]
            )
            residual.extend(
                (
                    orientation_error
                    * task.orientation_weight
                    * stance_scale
                ).tolist()
            )
        residual.extend(((q - seed_q) / self._scales * 0.055).tolist())
        if previous_q is not None:
            residual.extend(((q - previous_q) / self._scales * 0.11).tolist())
        residual.extend(
            (
                np.asarray(
                    list(solution.diagnostics.per_constraint_residual_m.values()),
                    dtype=np.float64,
                )
                * 12.0
            ).tolist()
        )
        return np.asarray(residual, dtype=np.float64)

    def _refined_pose(
        self,
        q: np.ndarray,
        seed_pose: RetargetedPose,
    ) -> RetargetedPose:
        normalized = tuple(
            float(np.clip((value - center) / scale, -1.0, 1.0))
            for value, center, scale in zip(
                q,
                self.action.centers,
                self.action.scales,
            )
        )
        decoded = self.action.decode(normalized)
        closure = self.closure.project(decoded)
        return RetargetedPose(
            joint_positions_rad=tuple(decoded),
            normalized_actions=normalized,
            closure=closure,
            semantic_targets_rad=seed_pose.semantic_targets_rad,
            semantic_achieved_rad=seed_pose.semantic_achieved_rad,
            saturations=seed_pose.saturations,
        )

    def retarget_g1_pose(
        self,
        source_positions_rad: Mapping[str, float] | Sequence[float],
        *,
        previous_motor_positions_rad: Sequence[float] | None = None,
        previous_passive_angles_rad: Mapping[str, float] | None = None,
        stance_contacts: Mapping[str, bool] | None = None,
        refinement_iterations: int = 2,
    ) -> UsdRetargetedPose:
        if (
            isinstance(refinement_iterations, bool)
            or not isinstance(refinement_iterations, int)
            or not 0 <= refinement_iterations <= 6
        ):
            raise RetargetingError("refinement_iterations must be an integer in 0..6")
        contacts = self._contacts(stance_contacts)
        source = self.g1.forward(source_positions_rad)
        seed_pose = self.seed.retarget_g1_pose(
            source_positions_rad,
            source_joint_names=(
                G1_BODY_JOINT_NAMES
                if not isinstance(source_positions_rad, Mapping)
                else None
            ),
        )
        q = np.asarray(seed_pose.joint_positions_rad, dtype=np.float64)
        previous_q = None
        if previous_motor_positions_rad is not None:
            if len(previous_motor_positions_rad) != len(ACTION_NAMES):
                raise RetargetingError(
                    "previous_motor_positions_rad must contain 22 values"
                )
            previous_q = np.asarray(
                previous_motor_positions_rad,
                dtype=np.float64,
            )
            if not np.all(np.isfinite(previous_q)):
                raise RetargetingError(
                    "previous_motor_positions_rad must be finite"
                )
        targets, source_torso_delta_rotation = self._target_matrices(source)
        solution = self.usd.solve(q, previous_passive_angles_rad)
        seed_q = q.copy()
        residual = self._task_residual(
            solution,
            q,
            targets=targets,
            seed_q=seed_q,
            previous_q=previous_q,
            contacts=contacts,
        )
        seed_error = float(np.linalg.norm(residual))
        accepted = 0
        epsilon = 2e-4
        damping = 3e-3

        for _ in range(refinement_iterations):
            jacobian = np.zeros((residual.size, q.size), dtype=np.float64)
            for column in range(q.size):
                shifted_q = q.copy()
                shifted_q[column] = min(
                    self._upper[column],
                    shifted_q[column] + epsilon,
                )
                actual_step = shifted_q[column] - q[column]
                if actual_step < 1e-9:
                    shifted_q[column] = max(
                        self._lower[column],
                        q[column] - epsilon,
                    )
                    actual_step = shifted_q[column] - q[column]
                shifted_solution = self.usd.solve(
                    shifted_q,
                    solution.passive_angles_rad,
                )
                shifted = self._task_residual(
                    shifted_solution,
                    shifted_q,
                    targets=targets,
                    seed_q=seed_q,
                    previous_q=previous_q,
                    contacts=contacts,
                )
                jacobian[:, column] = (shifted - residual) / actual_step
            normal = jacobian.T @ jacobian + damping * np.eye(q.size)
            gradient = jacobian.T @ residual
            try:
                delta = -np.linalg.solve(normal, gradient)
            except np.linalg.LinAlgError:
                delta = -np.linalg.lstsq(normal, gradient, rcond=1e-8)[0]
            delta = np.clip(delta, -0.16, 0.16)
            improved = False
            base_norm = float(np.linalg.norm(residual))
            for scale in (1.0, 0.5, 0.25, 0.125):
                trial_q = np.clip(q + delta * scale, self._lower, self._upper)
                trial_solution = self.usd.solve(
                    trial_q,
                    solution.passive_angles_rad,
                )
                trial_residual = self._task_residual(
                    trial_solution,
                    trial_q,
                    targets=targets,
                    seed_q=seed_q,
                    previous_q=previous_q,
                    contacts=contacts,
                )
                if float(np.linalg.norm(trial_residual)) + 1e-10 < base_norm:
                    q = trial_q
                    solution = trial_solution
                    residual = trial_residual
                    accepted += 1
                    improved = True
                    break
            if not improved:
                break

        refined_pose = self._refined_pose(q, seed_pose)
        refined_q = np.asarray(
            refined_pose.joint_positions_rad,
            dtype=np.float64,
        )
        final_solution = self.usd.solve(
            refined_pose.joint_positions_rad,
            solution.passive_angles_rad,
        )
        final_residual = self._task_residual(
            final_solution,
            refined_q,
            targets=targets,
            seed_q=seed_q,
            previous_q=previous_q,
            contacts=contacts,
        )
        body_rows: list[BodyTargetDiagnostic] = []
        for task in _BODY_TASKS:
            achieved = final_solution.semantic_body_transform(
                task.dropbear_body
            )
            target = targets[task.dropbear_body]
            body_rows.append(
                BodyTargetDiagnostic(
                    target=task.dropbear_body,
                    source=task.g1_body,
                    target_position_m=tuple(float(v) for v in target[:3, 3]),
                    achieved_position_m=tuple(float(v) for v in achieved[:3, 3]),
                    position_error_m=float(
                        np.linalg.norm(achieved[:3, 3] - target[:3, 3])
                    ),
                    orientation_error_rad=float(
                        np.linalg.norm(
                            _rotation_log(
                                target[:3, :3].T @ achieved[:3, :3]
                            )
                        )
                    ),
                )
            )
        diagnostics = UsdRetargetDiagnostics(
            iterations_requested=refinement_iterations,
            iterations_accepted=accepted,
            seed_task_error=seed_error,
            final_task_error=float(np.linalg.norm(final_residual)),
            maximum_closure_residual_m=(
                final_solution.maximum_closure_residual_m
            ),
            worst_closure_constraint=(
                final_solution.worst_closure_constraint
            ),
            body_targets=tuple(body_rows),
            source_torso_delta_rotation_matrix=tuple(
                float(value)
                for value in source_torso_delta_rotation.reshape(-1)
            ),
            stance_contacts=contacts,
        )
        return UsdRetargetedPose(
            pose=refined_pose,
            usd_solution=final_solution,
            diagnostics=diagnostics,
            source_verification=self.source_verification_payload(),
        )

    def retarget_chunk(
        self,
        source_frames_rad: Sequence[Mapping[str, float] | Sequence[float]],
        *,
        stance_contacts: Sequence[Mapping[str, bool]] | None = None,
        refinement_iterations: int = 1,
        maximum_frames: int = 40,
    ) -> tuple[UsdRetargetedPose, ...]:
        if not source_frames_rad or len(source_frames_rad) > maximum_frames:
            raise RetargetingError(
                f"decoded G1 chunk must contain 1..{maximum_frames} frames"
            )
        if stance_contacts is not None and len(stance_contacts) != len(
            source_frames_rad
        ):
            raise RetargetingError(
                "stance_contacts frame count must match the G1 chunk"
            )
        results: list[UsdRetargetedPose] = []
        previous_q: tuple[float, ...] | None = None
        previous_passive: Mapping[str, float] | None = None
        for index, frame in enumerate(source_frames_rad):
            result = self.retarget_g1_pose(
                frame,
                previous_motor_positions_rad=previous_q,
                previous_passive_angles_rad=previous_passive,
                stance_contacts=(
                    stance_contacts[index]
                    if stance_contacts is not None
                    else None
                ),
                refinement_iterations=refinement_iterations,
            )
            results.append(result)
            previous_q = result.joint_positions_rad
            previous_passive = result.usd_solution.passive_angles_rad
        return tuple(results)
