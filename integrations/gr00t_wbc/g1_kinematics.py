"""Pinned Unitree G1 kinematics used only at the retarget boundary.

GR00T-WholeBodyControl's VLA emits a 64D SONIC motion token.  The released
G1 decoder turns that latent token into the canonical 29 G1 joint positions;
this module then evaluates the matching G1 body tree so retargeting can compare
body-space objectives instead of copying joint angles between embodiments.

The body tree is read from the pinned upstream checkout rather than duplicated
here.  Mesh files and MuJoCo are not needed: only the MJCF body/joint poses are
parsed.  The source checkout and revision are controlled by
``UPSTREAM_LOCK.json`` and ``tools/bootstrap_gr00t_wbc.sh``.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence
import xml.etree.ElementTree as ET

import numpy as np

from .retarget import G1_BODY_JOINT_NAMES, RetargetingError


G1_SEMANTIC_BODY_NAMES = (
    "core",
    "torso",
    "left_hip",
    "left_knee",
    "left_foot",
    "right_hip",
    "right_knee",
    "right_foot",
    "left_shoulder",
    "left_elbow",
    "left_wrist",
    "right_shoulder",
    "right_elbow",
    "right_wrist",
)

# Released G1 SONIC standing angles in canonical MuJoCo/body order.  These are
# the decoder's action offset, not an inferred Dropbear pose.
G1_RELEASE_STANDING_POSE_RAD = (
    -0.312,
    0.0,
    0.0,
    0.669,
    -0.363,
    0.0,
    -0.312,
    0.0,
    0.0,
    0.669,
    -0.363,
    0.0,
    0.0,
    0.0,
    0.0,
    0.2,
    0.2,
    0.0,
    0.6,
    0.0,
    0.0,
    0.0,
    0.2,
    -0.2,
    0.0,
    0.6,
    0.0,
    0.0,
    0.0,
)


@dataclass(frozen=True)
class _BodyNode:
    name: str
    parent: str | None
    position: np.ndarray
    quaternion_wxyz: np.ndarray
    joint_name: str | None
    joint_position: np.ndarray
    joint_axis: np.ndarray
    joint_range_rad: tuple[float, float] | None


@dataclass(frozen=True)
class G1KinematicsResult:
    """One decoded G1 pose evaluated in its pinned MJCF body tree."""

    joint_positions_rad: tuple[float, ...]
    body_matrices: Mapping[str, np.ndarray]
    semantic_body_matrices: Mapping[str, np.ndarray]

    def semantic_body_transform(self, name: str) -> np.ndarray:
        try:
            return self.semantic_body_matrices[name].copy()
        except KeyError as error:
            raise RetargetingError(
                f"unknown G1 semantic body {name!r}; "
                f"expected one of {G1_SEMANTIC_BODY_NAMES}"
            ) from error

    def semantic_body_position(self, name: str) -> np.ndarray:
        return self.semantic_body_transform(name)[:3, 3]


def _numbers(raw: str | None, count: int, default: Sequence[float]) -> np.ndarray:
    if raw is None:
        return np.asarray(default, dtype=np.float64)
    values = np.asarray([float(value) for value in raw.split()], dtype=np.float64)
    if values.shape != (count,) or not np.all(np.isfinite(values)):
        raise RetargetingError(f"invalid {count}-value MJCF vector {raw!r}")
    return values


def _joint_range(raw: str | None, joint_name: str) -> tuple[float, float]:
    if raw is None:
        raise RetargetingError(
            f"G1 MJCF joint {joint_name!r} has no declared range"
        )
    values = _numbers(raw, 2, ())
    lower, upper = (float(value) for value in values)
    if lower >= upper:
        raise RetargetingError(
            f"G1 MJCF joint {joint_name!r} has an invalid range"
        )
    return lower, upper


def _translation(vector: Sequence[float]) -> np.ndarray:
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, 3] = vector
    return matrix


def _quaternion_matrix(quaternion_wxyz: Sequence[float]) -> np.ndarray:
    w, x, y, z = np.asarray(quaternion_wxyz, dtype=np.float64)
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if not math.isfinite(norm) or norm < 1e-12:
        raise RetargetingError("MJCF body quaternion is invalid")
    w, x, y, z = w / norm, x / norm, y / norm, z / norm
    rotation = np.asarray(
        [
            [
                1.0 - 2.0 * (y * y + z * z),
                2.0 * (x * y - z * w),
                2.0 * (x * z + y * w),
            ],
            [
                2.0 * (x * y + z * w),
                1.0 - 2.0 * (x * x + z * z),
                2.0 * (y * z - x * w),
            ],
            [
                2.0 * (x * z - y * w),
                2.0 * (y * z + x * w),
                1.0 - 2.0 * (x * x + y * y),
            ],
        ],
        dtype=np.float64,
    )
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = rotation
    return matrix


def _axis_angle_matrix(axis: Sequence[float], radians: float) -> np.ndarray:
    vector = np.asarray(axis, dtype=np.float64)
    norm = float(np.linalg.norm(vector))
    if norm < 1e-12:
        raise RetargetingError("MJCF joint axis is invalid")
    x, y, z = vector / norm
    cosine = math.cos(radians)
    sine = math.sin(radians)
    complement = 1.0 - cosine
    rotation = np.asarray(
        [
            [
                cosine + x * x * complement,
                x * y * complement - z * sine,
                x * z * complement + y * sine,
            ],
            [
                y * x * complement + z * sine,
                cosine + y * y * complement,
                y * z * complement - x * sine,
            ],
            [
                z * x * complement - y * sine,
                z * y * complement + x * sine,
                cosine + z * z * complement,
            ],
        ],
        dtype=np.float64,
    )
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = rotation
    return matrix


class G1Kinematics:
    """Evaluate the exact 29-DOF G1 MJCF tree without loading its meshes."""

    def __init__(
        self,
        project_root: Path | str | None = None,
        *,
        mjcf_path: Path | str | None = None,
    ) -> None:
        root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[2]
        )
        if mjcf_path is None:
            upstream = root / "references" / "GR00T-WholeBodyControl"
            lock_path = root / "integrations" / "gr00t_wbc" / "UPSTREAM_LOCK.json"
            try:
                lock = json.loads(lock_path.read_text(encoding="utf-8"))
                source_contract = lock["g1Kinematics"]
                relative_source = source_contract["sourcePath"]
                expected_sha256 = source_contract["sha256"]
            except (KeyError, OSError, TypeError, ValueError) as error:
                raise RetargetingError(
                    f"pinned G1 kinematics contract is invalid: {error}"
                ) from error
            if (
                not isinstance(relative_source, str)
                or not relative_source
                or not isinstance(expected_sha256, str)
                or len(expected_sha256) != 64
            ):
                raise RetargetingError(
                    "pinned G1 kinematics path or SHA-256 is invalid"
                )
            source = (upstream / relative_source).resolve()
            if upstream.resolve() not in source.parents or not source.is_file():
                raise RetargetingError(
                    "pinned G1 MJCF is unavailable; run "
                    "tools/bootstrap_gr00t_wbc.sh"
                )
            actual_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
            if actual_sha256 != expected_sha256:
                raise RetargetingError(
                    "pinned G1 MJCF digest drift; rerun "
                    "tools/bootstrap_gr00t_wbc.sh"
                )
        else:
            source = Path(mjcf_path).resolve()
            if not source.is_file():
                raise RetargetingError(f"G1 MJCF does not exist: {source}")
        self.source_path = source
        self._nodes = self._parse(source)
        discovered = tuple(
            node.joint_name
            for node in self._nodes
            if node.joint_name is not None
        )
        if discovered != G1_BODY_JOINT_NAMES:
            raise RetargetingError(
                "pinned G1 MJCF joint order does not match the decoder contract; "
                f"found={discovered}"
            )
        self.joint_limits_rad = tuple(
            node.joint_range_rad
            for node in self._nodes
            if node.joint_name is not None
        )
        if any(limit is None for limit in self.joint_limits_rad):
            raise RetargetingError(
                "pinned G1 MJCF is missing an actuated-joint range"
            )
        self._joint_index = {
            name: index for index, name in enumerate(G1_BODY_JOINT_NAMES)
        }

    @staticmethod
    def _parse(source: Path) -> tuple[_BodyNode, ...]:
        try:
            root = ET.parse(source).getroot()
        except (ET.ParseError, OSError) as error:
            raise RetargetingError(f"cannot parse pinned G1 MJCF: {error}") from error
        compiler = root.find("compiler")
        if compiler is None or compiler.get("angle") != "radian":
            raise RetargetingError(
                "pinned G1 MJCF must declare compiler angle='radian'"
            )
        worldbody = root.find("worldbody")
        pelvis = worldbody.find("body") if worldbody is not None else None
        if pelvis is None or pelvis.get("name") != "pelvis":
            raise RetargetingError("pinned G1 MJCF has no pelvis root body")
        nodes: list[_BodyNode] = []

        def visit(element: ET.Element, parent: str | None) -> None:
            name = element.get("name")
            if not name:
                raise RetargetingError("G1 MJCF contains an unnamed body")
            joints = element.findall("joint")
            actuated = [
                joint
                for joint in joints
                if joint.get("name") != "floating_base_joint"
            ]
            if len(actuated) > 1:
                raise RetargetingError(
                    f"G1 body {name!r} contains multiple hinge joints"
                )
            joint = actuated[0] if actuated else None
            if joint is not None and joint.get("type", "hinge") != "hinge":
                raise RetargetingError(
                    f"G1 joint {joint.get('name')!r} is not a hinge"
                )
            joint_name = joint.get("name") if joint is not None else None
            if joint is not None and not joint_name:
                raise RetargetingError(
                    f"G1 body {name!r} contains an unnamed actuated joint"
                )
            nodes.append(
                _BodyNode(
                    name=name,
                    parent=parent,
                    position=_numbers(element.get("pos"), 3, (0.0, 0.0, 0.0)),
                    quaternion_wxyz=_numbers(
                        element.get("quat"),
                        4,
                        (1.0, 0.0, 0.0, 0.0),
                    ),
                    joint_name=joint_name,
                    joint_position=_numbers(
                        joint.get("pos") if joint is not None else None,
                        3,
                        (0.0, 0.0, 0.0),
                    ),
                    joint_axis=_numbers(
                        joint.get("axis") if joint is not None else None,
                        3,
                        (0.0, 0.0, 1.0),
                    ),
                    joint_range_rad=(
                        _joint_range(joint.get("range"), joint_name)
                        if joint is not None and joint_name is not None
                        else None
                    ),
                )
            )
            for child in element.findall("body"):
                visit(child, name)

        visit(pelvis, None)
        return tuple(nodes)

    def _pose(
        self,
        values: Mapping[str, float] | Sequence[float],
    ) -> tuple[float, ...]:
        if isinstance(values, Mapping):
            if set(values) != set(G1_BODY_JOINT_NAMES):
                missing = sorted(set(G1_BODY_JOINT_NAMES) - set(values))
                extra = sorted(set(values) - set(G1_BODY_JOINT_NAMES))
                raise RetargetingError(
                    f"G1 FK pose mapping mismatch; missing={missing}, extra={extra}"
                )
            raw_pose = tuple(values[name] for name in G1_BODY_JOINT_NAMES)
        else:
            if len(values) != len(G1_BODY_JOINT_NAMES):
                raise RetargetingError(
                    f"G1 FK pose contains {len(values)} values, expected "
                    f"{len(G1_BODY_JOINT_NAMES)}"
                )
            raw_pose = tuple(values)
        if any(isinstance(value, (bool, np.bool_)) for value in raw_pose):
            raise RetargetingError("G1 FK pose values cannot be booleans")
        try:
            pose = tuple(float(value) for value in raw_pose)
        except (TypeError, ValueError) as error:
            raise RetargetingError("G1 FK pose must contain numeric values") from error
        if not all(math.isfinite(value) for value in pose):
            raise RetargetingError("G1 FK pose must contain only finite values")
        for name, value, limit in zip(
            G1_BODY_JOINT_NAMES,
            pose,
            self.joint_limits_rad,
        ):
            assert limit is not None
            lower, upper = limit
            if value < lower - 1e-7 or value > upper + 1e-7:
                raise RetargetingError(
                    f"G1 FK pose joint {name!r} is outside the pinned "
                    f"[{lower:.6f}, {upper:.6f}] rad range"
                )
        return pose

    def forward(
        self,
        joint_positions_rad: Mapping[str, float] | Sequence[float],
    ) -> G1KinematicsResult:
        pose = self._pose(joint_positions_rad)
        matrices: dict[str, np.ndarray] = {}
        for node in self._nodes:
            parent = (
                np.eye(4, dtype=np.float64)
                if node.parent is None
                else matrices[node.parent]
            )
            local = _translation(node.position) @ _quaternion_matrix(
                node.quaternion_wxyz
            )
            if node.joint_name is not None:
                radians = pose[self._joint_index[node.joint_name]]
                local = (
                    local
                    @ _translation(node.joint_position)
                    @ _axis_angle_matrix(node.joint_axis, radians)
                    @ _translation(-node.joint_position)
                )
            matrices[node.name] = parent @ local

        frozen_matrices: dict[str, np.ndarray] = {}
        for name, matrix in matrices.items():
            frozen = matrix.copy()
            frozen.setflags(write=False)
            frozen_matrices[name] = frozen

        semantic = {
            "core": frozen_matrices["pelvis"],
            "torso": frozen_matrices["torso_link"],
            "left_hip": frozen_matrices["left_hip_yaw_link"],
            "left_knee": frozen_matrices["left_knee_link"],
            "left_foot": (
                frozen_matrices["left_ankle_roll_link"]
                @ _translation((0.035, 0.0, -0.03))
            ),
            "right_hip": frozen_matrices["right_hip_yaw_link"],
            "right_knee": frozen_matrices["right_knee_link"],
            "right_foot": (
                frozen_matrices["right_ankle_roll_link"]
                @ _translation((0.035, 0.0, -0.03))
            ),
            "left_shoulder": frozen_matrices["left_shoulder_yaw_link"],
            "left_elbow": frozen_matrices["left_elbow_link"],
            "left_wrist": (
                frozen_matrices["left_wrist_yaw_link"]
                @ _translation((0.0415, 0.003, 0.0))
            ),
            "right_shoulder": frozen_matrices["right_shoulder_yaw_link"],
            "right_elbow": frozen_matrices["right_elbow_link"],
            "right_wrist": (
                frozen_matrices["right_wrist_yaw_link"]
                @ _translation((0.0415, -0.003, 0.0))
            ),
        }
        for matrix in semantic.values():
            matrix.setflags(write=False)
        return G1KinematicsResult(
            joint_positions_rad=pose,
            body_matrices=MappingProxyType(frozen_matrices),
            semantic_body_matrices=MappingProxyType(semantic),
        )

    @staticmethod
    def relative_transform(
        result: G1KinematicsResult,
        body: str,
        reference: str = "core",
    ) -> np.ndarray:
        return (
            np.linalg.inv(result.semantic_body_transform(reference))
            @ result.semantic_body_transform(body)
        )


def g1_kinematics_status(
    project_root: Path | str | None = None,
) -> dict[str, Any]:
    """Return a dashboard-safe G1 body-tree readiness report."""

    try:
        kinematics = G1Kinematics(project_root)
    except RetargetingError as error:
        return {
            "available": False,
            "reason": str(error),
            "jointCount": len(G1_BODY_JOINT_NAMES),
            "semanticBodies": list(G1_SEMANTIC_BODY_NAMES),
        }
    return {
        "available": True,
        "sourcePath": str(kinematics.source_path),
        "jointCount": len(G1_BODY_JOINT_NAMES),
        "semanticBodies": list(G1_SEMANTIC_BODY_NAMES),
    }
