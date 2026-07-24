"""USD-derived Dropbear articulation kinematics for retargeting and preview.

This module is a direct Python port of the retained articulation solver in
``web/js/robot_3d.js``.  It consumes the browser articulation manifest, not a
hand-authored serial-chain approximation:

* body matrices are read using the column-major convention used by Three.js;
* revolute axes are rotated by their USD local-frame quaternions;
* the retained ``RL_Revolute81`` mirrored-axis correction is applied;
* all 22 motor coordinates drive the USD spanning tree; and
* 22 passive leg plus 10 passive arm coordinates are projected against the
  retained USD closure anchors with the same damped least-squares iteration.

The result is useful for task-space retargeting, deterministic browser parity,
and closure diagnostics.  It is kinematics only.  It does not implement or
claim PhysX dynamics, collision, contact, friction, or force response.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from .embodiment import (
    ACTION_COUNT,
    ACTION_NAMES,
    USD_JOINT_NAMES,
    find_project_root,
)


Matrix4 = NDArray[np.float64]
Vector3 = NDArray[np.float64]

LEG_SIDES = ("LL_", "RL_")
ARM_SIDES = ("LH_", "RH_")
LEG_PASSIVE_SUFFIXES = (
    "Revolute33",
    "Revolute46",
    "Revolute47",
    "Revolute57",
    "Revolute112",
    "Revolute111",
    "Revolute87",
    "Revolute88",
    "Revolute48",
    "Revolute49",
    "Revolute37",
)
ARM_PASSIVE_SUFFIXES = (
    "Revolute42",
    "elbow_joint",
    "Revolute32",
    "Revolute33",
    "Revolute44",
)

# These paths identify output bodies in the retained 93-body USD articulation.
# They are intentionally body targets, not invented logical joints.
SEMANTIC_BODY_PATHS: Mapping[str, str] = MappingProxyType(
    {
        "root": "/humanoid/world",
        "core": "/humanoid/world",
        "torso": "/humanoid/world",
        "left_hip_output": "/humanoid/PG_RMD_X10_V3Rotor_1",
        "right_hip_output": "/humanoid/PG_RMD_X10_V3__1_Rotor_1",
        "left_lower_leg": (
            "/humanoid/LL_double_bracket_10deg_MIR_MIR_MIR_1"
        ),
        "right_lower_leg": (
            "/humanoid/RL_double_bracket_10deg_MIR_MIR_MIR_1"
        ),
        "left_foot": "/humanoid/LL_skateboard_bearing_left_2",
        "right_foot": "/humanoid/RL_skateboard_bearing_left_2",
        "left_upper_arm": "/humanoid/LH_RMD_X8_Pro_MIR8_MIR1__3__1",
        "right_upper_arm": "/humanoid/RH_RMD_X8_Pro_MIR8_MIR1__3__1",
        "left_shoulder_output": (
            "/humanoid/LH_RMD_X8_Pro_MIR8_MIR1__3__1"
        ),
        "right_shoulder_output": (
            "/humanoid/RH_RMD_X8_Pro_MIR8_MIR1__3__1"
        ),
        "left_forearm": "/humanoid/LH_6mm_bearing__4__1",
        "right_forearm": "/humanoid/RH_6mm_bearing__4__1",
        "left_wrist": "/humanoid/LH_shoulder_ex_al_interface_1",
        "right_wrist": "/humanoid/RH_shoulder_ex_al_interface_1",
    }
)

_AXES = {
    "X": np.asarray((1.0, 0.0, 0.0), dtype=np.float64),
    "Y": np.asarray((0.0, 1.0, 0.0), dtype=np.float64),
    "Z": np.asarray((0.0, 0.0, 1.0), dtype=np.float64),
}


class DropbearKinematicsError(ValueError):
    """The articulation manifest or a requested solve violates the contract."""


@dataclass(frozen=True)
class ClosureDiagnostics:
    """Final retained-anchor mismatch after passive-joint projection."""

    per_constraint_residual_m: Mapping[str, float]
    per_side_maximum_residual_m: Mapping[str, float]
    leg_maximum_residual_m: float
    arm_maximum_residual_m: float
    other_maximum_residual_m: float

    @property
    def maximum_residual_m(self) -> float:
        """Return the worst retained closure-anchor separation in metres."""

        if not self.per_constraint_residual_m:
            return 0.0
        return max(self.per_constraint_residual_m.values())

    @property
    def maximum_residual_mm(self) -> float:
        """Return the worst retained closure-anchor separation in millimetres."""

        return self.maximum_residual_m * 1000.0

    @property
    def worst_constraint(self) -> str | None:
        """Return the name of the worst retained closure constraint."""

        if not self.per_constraint_residual_m:
            return None
        return max(
            self.per_constraint_residual_m,
            key=self.per_constraint_residual_m.__getitem__,
        )


@dataclass(frozen=True)
class KinematicsResult:
    """One solved 22-motor Dropbear pose and its passive articulation state."""

    body_matrices: Mapping[str, Matrix4]
    passive_angles_rad: Mapping[str, float]
    motor_positions_rad: Mapping[str, float]
    usd_motor_positions_rad: Mapping[str, float]
    joint_anchors_world: Mapping[str, Vector3]
    diagnostics: ClosureDiagnostics
    semantic_body_paths: Mapping[str, str] = SEMANTIC_BODY_PATHS

    @property
    def passive_angles(self) -> Mapping[str, float]:
        """Compatibility alias for callers that already carry radians."""

        return self.passive_angles_rad

    @property
    def maximum_closure_residual_m(self) -> float:
        """Return the worst final retained-anchor separation in metres."""

        return self.diagnostics.maximum_residual_m

    @property
    def maximum_closure_residual_mm(self) -> float:
        """Return the worst final retained-anchor separation in millimetres."""

        return self.diagnostics.maximum_residual_mm

    @property
    def worst_closure_constraint(self) -> str | None:
        """Return the retained constraint with the greatest final mismatch."""

        return self.diagnostics.worst_constraint

    def body_transform(self, body_path: str) -> Matrix4:
        """Return the read-only world transform for an exact USD body path."""

        try:
            return self.body_matrices[body_path]
        except KeyError as error:
            raise DropbearKinematicsError(
                f"unknown Dropbear USD body path: {body_path}"
            ) from error

    def semantic_body_transform(self, semantic: str) -> Matrix4:
        """Return the read-only world transform for a named body target."""

        try:
            path = self.semantic_body_paths[semantic]
        except KeyError as error:
            raise DropbearKinematicsError(
                f"unknown Dropbear semantic body: {semantic}"
            ) from error
        return self.body_transform(path)

    def semantic_body_position(self, semantic: str) -> Vector3:
        """Return a copy of the named body target's world-space translation."""

        return self.semantic_body_transform(semantic)[:3, 3].copy()

    def joint_anchor_world(self, joint_name: str) -> Vector3:
        """Return a copy of a joint's solved body-0 USD anchor position.

        For a motor or passive tree joint this is its world-space pivot.  For a
        closure constraint it is the body-0 endpoint; compare it with that
        constraint's residual diagnostic when closure accuracy matters.
        """

        try:
            return self.joint_anchors_world[joint_name].copy()
        except KeyError as error:
            raise DropbearKinematicsError(
                f"unknown Dropbear USD joint: {joint_name}"
            ) from error


def _readonly_matrix(matrix: Matrix4) -> Matrix4:
    result = np.asarray(matrix, dtype=np.float64).copy()
    result.setflags(write=False)
    return result


def _matrix_from_three(values: Sequence[float]) -> Matrix4:
    """Read a Three.js Matrix4 array, whose storage is column-major."""

    if len(values) != 16:
        raise DropbearKinematicsError("body matrix must contain 16 values")
    matrix = np.asarray(values, dtype=np.float64).reshape((4, 4), order="F")
    if not np.isfinite(matrix).all():
        raise DropbearKinematicsError("body matrix contains a non-finite value")
    return matrix


def _quaternion_rotation(values: Sequence[float]) -> NDArray[np.float64]:
    """Return a 3x3 rotation for a normalized USD ``[w, x, y, z]`` quat."""

    if len(values) != 4:
        raise DropbearKinematicsError("joint quaternion must contain four values")
    w, x, y, z = (float(value) for value in values)
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if not math.isfinite(norm) or norm < 1e-12:
        raise DropbearKinematicsError("joint quaternion is invalid")
    w, x, y, z = (value / norm for value in (w, x, y, z))
    return np.asarray(
        (
            (
                1.0 - 2.0 * (y * y + z * z),
                2.0 * (x * y - z * w),
                2.0 * (x * z + y * w),
            ),
            (
                2.0 * (x * y + z * w),
                1.0 - 2.0 * (x * x + z * z),
                2.0 * (y * z - x * w),
            ),
            (
                2.0 * (x * z - y * w),
                2.0 * (y * z + x * w),
                1.0 - 2.0 * (x * x + y * y),
            ),
        ),
        dtype=np.float64,
    )


def _rotation_about_axis(axis: Vector3, radians: float) -> Matrix4:
    x, y, z = axis
    cosine = math.cos(radians)
    sine = math.sin(radians)
    one_minus_cosine = 1.0 - cosine
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = np.asarray(
        (
            (
                cosine + x * x * one_minus_cosine,
                x * y * one_minus_cosine - z * sine,
                x * z * one_minus_cosine + y * sine,
            ),
            (
                y * x * one_minus_cosine + z * sine,
                cosine + y * y * one_minus_cosine,
                y * z * one_minus_cosine - x * sine,
            ),
            (
                z * x * one_minus_cosine - y * sine,
                z * y * one_minus_cosine + x * sine,
                cosine + z * z * one_minus_cosine,
            ),
        ),
        dtype=np.float64,
    )
    return result


def _translation(vector: Sequence[float]) -> Matrix4:
    result = np.eye(4, dtype=np.float64)
    result[:3, 3] = np.asarray(vector, dtype=np.float64)
    return result


def _transform_point(matrix: Matrix4, point: Sequence[float]) -> Vector3:
    homogeneous = matrix @ np.asarray((*point, 1.0), dtype=np.float64)
    if abs(float(homogeneous[3])) > 1e-12:
        homogeneous = homogeneous / homogeneous[3]
    return homogeneous[:3]


def _solve_symmetric(matrix: Matrix4, vector: Vector3) -> Vector3:
    """Port the browser solver's pivoted augmented-matrix elimination."""

    size = int(vector.size)
    augmented = np.concatenate(
        (
            np.asarray(matrix, dtype=np.float64).copy(),
            np.asarray(vector, dtype=np.float64).reshape(size, 1),
        ),
        axis=1,
    )
    for pivot in range(size):
        best = pivot + int(np.argmax(np.abs(augmented[pivot:, pivot])))
        if best != pivot:
            augmented[[pivot, best]] = augmented[[best, pivot]]
        divisor = float(augmented[pivot, pivot])
        if abs(divisor) < 1e-10:
            continue
        augmented[pivot, pivot:] /= divisor
        for row in range(size):
            if row == pivot:
                continue
            factor = float(augmented[row, pivot])
            augmented[row, pivot:] -= factor * augmented[pivot, pivot:]
    return augmented[:, size]


class DropbearUsdKinematics:
    """Evaluate the retained Dropbear USD spanning tree and loop closures."""

    def __init__(self, project_root: Path | str | None = None) -> None:
        start = None if project_root is None else Path(project_root)
        self.project_root = find_project_root(start)
        self.manifest_path = (
            self.project_root
            / "web"
            / "assets"
            / "robot"
            / "dropbear-articulation.json"
        )
        self.manifest: dict[str, Any] = json.loads(
            self.manifest_path.read_text(encoding="utf-8")
        )
        self._build_graph()

    @property
    def passive_joint_names(self) -> tuple[str, ...]:
        """Return the passive coordinates projected by the browser solver."""

        return self._passive_joint_names

    @property
    def body_paths(self) -> tuple[str, ...]:
        """Return every retained rigid-body path in manifest order."""

        return tuple(self._initial_matrices)

    def joint_axis_local(self, joint_name: str) -> Vector3:
        """Return the effective parent-local axis, including browser adaptation."""

        try:
            joint = self._joint_by_name[joint_name]
        except KeyError as error:
            raise DropbearKinematicsError(
                f"unknown Dropbear USD joint: {joint_name}"
            ) from error
        return self._joint_axis(joint, bool(joint.get("reverse"))).copy()

    def solve(
        self,
        motor_positions_rad: Sequence[float] | Mapping[str, float],
        previous_passive_angles: Mapping[str, float] | None = None,
    ) -> KinematicsResult:
        """Solve one 22-motor pose and project its passive closed linkages.

        A sequence is interpreted in canonical :data:`ACTION_NAMES` order.
        A mapping must contain exactly either the semantic action names or the
        22 retained USD motor-joint names.  Passive state is explicit so an IK
        or trajectory caller can seed each frame from the preceding solution.
        """

        semantic_positions, commanded = self._motor_positions(motor_positions_rad)
        passive = self._passive_seed(previous_passive_angles)

        def calf_weight(joint: Mapping[str, Any]) -> float:
            return (
                5.0
                if joint["name"].endswith(("Revolute115", "Revolute117"))
                else 1.0
            )
        for side in LEG_SIDES:
            self._solve_passive_closure(
                self._leg_closures[side],
                self._leg_passive[side],
                commanded,
                passive,
                iterations=10,
                weight_for=calf_weight,
            )
        for side in ARM_SIDES:
            self._solve_passive_closure(
                self._arm_closures[side],
                self._arm_passive[side],
                commanded,
                passive,
                iterations=16,
            )

        matrices = self._calculate_matrices(commanded, passive)
        residuals = {
            joint["name"]: self._constraint_residual_m(joint, matrices)
            for joint in self._closure_joints
        }
        side_maxima = {
            side: max(
                (
                    residual
                    for name, residual in residuals.items()
                    if name.startswith(side)
                ),
                default=0.0,
            )
            for side in (*LEG_SIDES, *ARM_SIDES)
        }
        other_maximum = max(
            (
                residual
                for name, residual in residuals.items()
                if not name.startswith((*LEG_SIDES, *ARM_SIDES))
            ),
            default=0.0,
        )
        diagnostics = ClosureDiagnostics(
            per_constraint_residual_m=MappingProxyType(residuals),
            per_side_maximum_residual_m=MappingProxyType(side_maxima),
            leg_maximum_residual_m=max(
                (side_maxima[side] for side in LEG_SIDES),
                default=0.0,
            ),
            arm_maximum_residual_m=max(
                (side_maxima[side] for side in ARM_SIDES),
                default=0.0,
            ),
            other_maximum_residual_m=other_maximum,
        )
        frozen_matrices = {
            path: _readonly_matrix(matrix) for path, matrix in matrices.items()
        }
        joint_anchors = {
            joint["name"]: _transform_point(
                matrices[joint["body0"]],
                joint["localPos0"],
            )
            for joint in self._joints
            if joint["body0"] in matrices
        }
        for anchor in joint_anchors.values():
            anchor.setflags(write=False)
        return KinematicsResult(
            body_matrices=MappingProxyType(frozen_matrices),
            passive_angles_rad=MappingProxyType(dict(passive)),
            motor_positions_rad=MappingProxyType(semantic_positions),
            usd_motor_positions_rad=MappingProxyType(dict(commanded)),
            joint_anchors_world=MappingProxyType(joint_anchors),
            diagnostics=diagnostics,
        )

    def _build_graph(self) -> None:
        bodies = self.manifest.get("bodies")
        joints = self.manifest.get("joints")
        if not isinstance(bodies, list) or not isinstance(joints, list):
            raise DropbearKinematicsError(
                "articulation manifest requires bodies and joints"
            )
        self._initial_matrices = {
            body["path"]: _matrix_from_three(body["matrix"]) for body in bodies
        }
        if len(self._initial_matrices) != len(bodies):
            raise DropbearKinematicsError("articulation body paths must be unique")

        self._joint_by_name = {joint["name"]: joint for joint in joints}
        self._joints = tuple(joints)
        if len(self._joint_by_name) != len(joints):
            raise DropbearKinematicsError("articulation joint names must be unique")
        missing_motors = sorted(set(USD_JOINT_NAMES) - set(self._joint_by_name))
        if missing_motors:
            raise DropbearKinematicsError(
                f"articulation is missing motor joints: {missing_motors}"
            )

        self._tree_joints = [joint for joint in joints if joint.get("tree")]
        self._tree_children: dict[str, list[Mapping[str, Any]]] = {}
        self._relative_matrices: dict[str, Matrix4] = {}
        tree_child_paths: set[str] = set()
        for joint in self._tree_joints:
            parent = joint.get("parent")
            child = joint.get("child")
            if (
                parent not in self._initial_matrices
                or child not in self._initial_matrices
            ):
                continue
            self._tree_children.setdefault(parent, []).append(joint)
            tree_child_paths.add(child)
            self._relative_matrices[joint["path"]] = (
                np.linalg.inv(self._initial_matrices[parent])
                @ self._initial_matrices[child]
            )
        self._tree_roots = tuple(
            path for path in self._initial_matrices if path not in tree_child_paths
        )

        self._closure_joints = tuple(
            joint for joint in joints if joint.get("closure")
        )
        self._leg_closures = {
            side: tuple(
                joint
                for joint in self._closure_joints
                if joint["name"].startswith(side)
            )
            for side in LEG_SIDES
        }
        self._arm_closures = {
            side: tuple(
                joint
                for joint in self._closure_joints
                if joint["name"].startswith(side)
            )
            for side in ARM_SIDES
        }
        self._leg_passive = {
            side: tuple(
                self._joint_by_name[f"{side}{suffix}"]
                for suffix in LEG_PASSIVE_SUFFIXES
                if f"{side}{suffix}" in self._joint_by_name
            )
            for side in LEG_SIDES
        }
        self._arm_passive = {
            side: tuple(
                self._joint_by_name[f"{side}{suffix}"]
                for suffix in ARM_PASSIVE_SUFFIXES
                if f"{side}{suffix}" in self._joint_by_name
            )
            for side in ARM_SIDES
        }
        passive_names = [
            joint["name"]
            for side in (*LEG_SIDES, *ARM_SIDES)
            for joint in (
                self._leg_passive[side]
                if side in LEG_SIDES
                else self._arm_passive[side]
            )
        ]
        self._passive_joint_names = tuple(passive_names)

        if len(self._tree_joints) != 89:
            raise DropbearKinematicsError(
                f"expected 89 retained tree joints, found {len(self._tree_joints)}"
            )
        if len(self._closure_joints) != 27:
            raise DropbearKinematicsError(
                f"expected 27 closure constraints, found "
                f"{len(self._closure_joints)}"
            )
        if len(self._passive_joint_names) != 32:
            raise DropbearKinematicsError(
                "expected 32 browser-projected passive joints"
            )
        missing_semantic_bodies = sorted(
            set(SEMANTIC_BODY_PATHS.values()) - set(self._initial_matrices)
        )
        if missing_semantic_bodies:
            raise DropbearKinematicsError(
                f"semantic output bodies are missing: {missing_semantic_bodies}"
            )

    def _motor_positions(
        self,
        values: Sequence[float] | Mapping[str, float],
    ) -> tuple[dict[str, float], dict[str, float]]:
        if isinstance(values, Mapping):
            keys = set(values)
            if keys == set(ACTION_NAMES):
                semantic = {
                    name: self._finite_angle(values[name], name)
                    for name in ACTION_NAMES
                }
                commanded = {
                    usd_name: semantic[action_name]
                    for action_name, usd_name in zip(ACTION_NAMES, USD_JOINT_NAMES)
                }
                return semantic, commanded
            if keys == set(USD_JOINT_NAMES):
                commanded = {
                    name: self._finite_angle(values[name], name)
                    for name in USD_JOINT_NAMES
                }
                semantic = {
                    action_name: commanded[usd_name]
                    for action_name, usd_name in zip(ACTION_NAMES, USD_JOINT_NAMES)
                }
                return semantic, commanded
            raise DropbearKinematicsError(
                "motor mapping must contain exactly the canonical 22 semantic "
                "action names or exactly the 22 retained USD motor-joint names"
            )
        if isinstance(values, (str, bytes)) or len(values) != ACTION_COUNT:
            raise DropbearKinematicsError(
                f"motor sequence must contain {ACTION_COUNT} values in "
                "canonical action order"
            )
        semantic = {
            name: self._finite_angle(value, name)
            for name, value in zip(ACTION_NAMES, values)
        }
        commanded = {
            usd_name: semantic[action_name]
            for action_name, usd_name in zip(ACTION_NAMES, USD_JOINT_NAMES)
        }
        return semantic, commanded

    @staticmethod
    def _finite_angle(value: Any, name: str) -> float:
        if isinstance(value, bool):
            raise DropbearKinematicsError(f"{name} must be a finite angle")
        try:
            result = float(value)
        except (TypeError, ValueError) as error:
            raise DropbearKinematicsError(
                f"{name} must be a finite angle"
            ) from error
        if not math.isfinite(result):
            raise DropbearKinematicsError(f"{name} must be a finite angle")
        return result

    def _passive_seed(
        self,
        previous: Mapping[str, float] | None,
    ) -> dict[str, float]:
        passive = {name: 0.0 for name in self._passive_joint_names}
        if previous is None:
            return passive
        unknown = sorted(set(previous) - set(self._passive_joint_names))
        if unknown:
            raise DropbearKinematicsError(
                f"unknown passive-joint seeds: {unknown}"
            )
        for name, value in previous.items():
            passive[name] = self._finite_angle(value, name)
        return passive

    def _joint_axis(
        self,
        joint: Mapping[str, Any],
        reverse: bool = False,
    ) -> Vector3:
        # This is the same retained browser correction documented in the
        # articulation manifest.  The source USD revision remains untouched.
        authored_axis = "Z" if joint["name"] == "RL_Revolute81" else joint["axis"]
        basis = _AXES.get(authored_axis, _AXES["X"])
        rotation = _quaternion_rotation(
            joint["localRot1"] if reverse else joint["localRot0"]
        )
        axis = rotation @ basis
        norm = float(np.linalg.norm(axis))
        if norm < 1e-12:
            raise DropbearKinematicsError(
                f"joint {joint['name']} has a degenerate axis"
            )
        return axis / norm

    def _joint_delta(
        self,
        joint: Mapping[str, Any],
        radians: float,
    ) -> Matrix4:
        reverse = bool(joint.get("reverse"))
        anchor = np.asarray(
            joint["localPos1"] if reverse else joint["localPos0"],
            dtype=np.float64,
        )
        axis = self._joint_axis(joint, reverse)
        signed_radians = -radians if reverse else radians
        return (
            _translation(anchor)
            @ _rotation_about_axis(axis, signed_radians)
            @ _translation(-anchor)
        )

    def _calculate_matrices(
        self,
        commanded: Mapping[str, float],
        passive: Mapping[str, float],
    ) -> dict[str, Matrix4]:
        matrices = {
            path: matrix.copy() for path, matrix in self._initial_matrices.items()
        }

        def visit(parent_path: str) -> None:
            parent_matrix = matrices.get(
                parent_path,
                self._initial_matrices[parent_path],
            )
            for joint in self._tree_children.get(parent_path, ()):
                radians = commanded.get(
                    joint["name"],
                    passive.get(joint["name"], 0.0),
                )
                delta = (
                    self._joint_delta(joint, radians)
                    if abs(radians) > 1e-12
                    else np.eye(4, dtype=np.float64)
                )
                matrices[joint["child"]] = (
                    parent_matrix
                    @ delta
                    @ self._relative_matrices[joint["path"]]
                )
                visit(joint["child"])

        for root in self._tree_roots:
            visit(root)
        return matrices

    def _closure_vector(
        self,
        joints: Sequence[Mapping[str, Any]],
        matrices: Mapping[str, Matrix4],
        weight_for: Callable[[Mapping[str, Any]], float] | None = None,
    ) -> Vector3:
        residual: list[float] = []
        for joint in joints:
            body0 = matrices.get(joint["body0"])
            body1 = matrices.get(joint["body1"])
            if body0 is None or body1 is None:
                continue
            point0 = _transform_point(body0, joint["localPos0"])
            point1 = _transform_point(body1, joint["localPos1"])
            weight = weight_for(joint) if weight_for else 1.0
            residual.extend(((point0 - point1) * weight).tolist())
        return np.asarray(residual, dtype=np.float64)

    def _solve_passive_closure(
        self,
        joints: Sequence[Mapping[str, Any]],
        variables: Sequence[Mapping[str, Any]],
        commanded: Mapping[str, float],
        passive: dict[str, float],
        *,
        iterations: int,
        weight_for: Callable[[Mapping[str, Any]], float] | None = None,
    ) -> None:
        epsilon = 1e-4
        if not variables or not joints:
            return
        for _ in range(iterations):
            base = self._closure_vector(
                joints,
                self._calculate_matrices(commanded, passive),
                weight_for,
            )
            base_norm = float(np.linalg.norm(base))
            if base_norm < 2e-5:
                break
            jacobian = np.zeros((base.size, len(variables)), dtype=np.float64)
            for column, joint in enumerate(variables):
                name = joint["name"]
                before = passive[name]
                passive[name] = before + epsilon
                shifted = self._closure_vector(
                    joints,
                    self._calculate_matrices(commanded, passive),
                    weight_for,
                )
                passive[name] = before
                jacobian[:, column] = (shifted - base) / epsilon

            size = len(variables)
            normal = np.zeros((size, size), dtype=np.float64)
            rhs = np.zeros(size, dtype=np.float64)
            for column in range(size):
                for row in range(base.size):
                    rhs[column] -= jacobian[row, column] * base[row]
                for other in range(size):
                    for row in range(base.size):
                        normal[column, other] += (
                            jacobian[row, column] * jacobian[row, other]
                        )
                normal[column, column] += 2e-6
            delta = _solve_symmetric(normal, rhs)
            before = [passive[joint["name"]] for joint in variables]
            accepted = False
            for scale in (1.0, 0.5, 0.25, 0.125):
                for index, joint in enumerate(variables):
                    raw = float(delta[index]) if math.isfinite(delta[index]) else 0.0
                    step = max(-0.28, min(0.28, raw * scale))
                    passive[joint["name"]] = before[index] + step
                trial = self._closure_vector(
                    joints,
                    self._calculate_matrices(commanded, passive),
                    weight_for,
                )
                if float(np.linalg.norm(trial)) < base_norm:
                    accepted = True
                    break
            if not accepted:
                for index, joint in enumerate(variables):
                    passive[joint["name"]] = before[index]
                break

    @staticmethod
    def _constraint_residual_m(
        joint: Mapping[str, Any],
        matrices: Mapping[str, Matrix4],
    ) -> float:
        body0 = matrices.get(joint["body0"])
        body1 = matrices.get(joint["body1"])
        if body0 is None or body1 is None:
            return math.inf
        point0 = _transform_point(body0, joint["localPos0"])
        point1 = _transform_point(body1, joint["localPos1"])
        return float(np.linalg.norm(point0 - point1))
