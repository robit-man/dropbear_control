"""MuJoCo runtime compiled from the verified Dropbear USD physics manifest.

The source USD contains the authoritative rigid-body graph, masses, inertias,
joint frames, and closed-loop constraints.  Its collision groups do not expose
finite primitive envelopes outside PhysX, so this local backend derives a
conservative ellipsoid from each body's authored inertia.  It is therefore a
real gravity/contact/force simulation suitable for local policy experiments,
but its collision shapes are explicitly proxies rather than PhysX-equivalent
source meshes.

The conservative proxies currently collide with the floor only. Self-collision
stays disabled until a source-grounded pair-filter can replace unsafe
all-against-all proxy contact.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
import math
from pathlib import Path
import re
from typing import Iterable

import numpy as np

try:
    import mujoco
except ImportError:  # pragma: no cover - exercised by runtime admission
    mujoco = None


GRAVITY_MPS2 = 9.80665
# The lowest USD foot-bearing proxy rests at roughly 0.093 m once its authored
# principal-axis inertia ellipsoid is applied.
GROUND_Z_M = 0.09
ACTION_TO_USD_JOINT = (
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
    "LH_yaw",
    "LH_pitch",
    "LH_roll",
    "LH_Revolute41",
    "LH_wrist_roll",
    "RH_yaw",
    "RH_pitch",
    "RH_roll",
    "RH_Revolute41",
    "RH_wrist_roll",
)
LEFT_FOOT_BODY = "LL_basis_left_1"
RIGHT_FOOT_BODY = "RL_basis_left_1"


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return cleaned.strip("_") or "unnamed"


def _body_name(value: str) -> str:
    return f"db_{_safe_name(value)}"


def _numbers(values: Iterable[float]) -> str:
    return " ".join(f"{float(value):.9g}" for value in values)


def _matrix(row_major: list[float]) -> np.ndarray:
    return np.asarray(row_major, dtype=np.float64).reshape(4, 4)


def _matrix_to_quaternion(matrix: np.ndarray) -> np.ndarray:
    """Convert a conventional 3x3 column-vector rotation to wxyz."""

    trace = float(np.trace(matrix))
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        quat = np.array(
            [
                0.25 * scale,
                (matrix[2, 1] - matrix[1, 2]) / scale,
                (matrix[0, 2] - matrix[2, 0]) / scale,
                (matrix[1, 0] - matrix[0, 1]) / scale,
            ]
        )
    else:
        diagonal = np.diag(matrix)
        index = int(np.argmax(diagonal))
        if index == 0:
            scale = math.sqrt(
                max(1e-12, 1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2])
            ) * 2.0
            quat = np.array(
                [
                    (matrix[2, 1] - matrix[1, 2]) / scale,
                    0.25 * scale,
                    (matrix[0, 1] + matrix[1, 0]) / scale,
                    (matrix[0, 2] + matrix[2, 0]) / scale,
                ]
            )
        elif index == 1:
            scale = math.sqrt(
                max(1e-12, 1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2])
            ) * 2.0
            quat = np.array(
                [
                    (matrix[0, 2] - matrix[2, 0]) / scale,
                    (matrix[0, 1] + matrix[1, 0]) / scale,
                    0.25 * scale,
                    (matrix[1, 2] + matrix[2, 1]) / scale,
                ]
            )
        else:
            scale = math.sqrt(
                max(1e-12, 1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1])
            ) * 2.0
            quat = np.array(
                [
                    (matrix[1, 0] - matrix[0, 1]) / scale,
                    (matrix[0, 2] + matrix[2, 0]) / scale,
                    (matrix[1, 2] + matrix[2, 1]) / scale,
                    0.25 * scale,
                ]
            )
    return quat / max(float(np.linalg.norm(quat)), 1e-12)


def _proxy_radii(mass: float, inertia: list[float]) -> np.ndarray:
    """Equivalent solid-ellipsoid radii from principal moments."""

    ix, iy, iz = (max(float(value), 1e-8) for value in inertia)
    denominator = max(2.0 * mass, 1e-8)
    squared = np.array(
        [
            5.0 * (iy + iz - ix) / denominator,
            5.0 * (ix + iz - iy) / denominator,
            5.0 * (ix + iy - iz) / denominator,
        ]
    )
    # Principal inertias can describe long, thin tie rods.  A single ellipsoid
    # cannot preserve those shapes without rotating a large radius through the
    # floor at rest, so cap the contact proxy while retaining the exact inertia
    # on the body itself.
    return np.sqrt(np.clip(squared, 0.012**2, 0.075**2))


def _body_relative_transform(
    child_world: np.ndarray,
    parent_world: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    # USD matrices here use row-vector convention. M_child = M_local M_parent.
    relative = child_world @ np.linalg.inv(parent_world)
    position = relative[3, :3]
    rotation = relative[:3, :3].T
    return position, _matrix_to_quaternion(rotation)


def _quaternion_to_euler_wxyz(quaternion: np.ndarray) -> np.ndarray:
    """Return intrinsic XYZ roll, pitch, yaw from a MuJoCo wxyz quaternion."""

    w, x, y, z = (float(value) for value in quaternion)
    roll = math.atan2(
        2.0 * (w * x + y * z),
        1.0 - 2.0 * (x * x + y * y),
    )
    pitch = math.asin(
        max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
    )
    yaw = math.atan2(
        2.0 * (w * z + x * y),
        1.0 - 2.0 * (y * y + z * z),
    )
    return np.asarray((roll, pitch, yaw), dtype=np.float64)


@dataclass(frozen=True)
class CompiledDropbearModel:
    model: object
    action_joint_ids: tuple[int, ...]
    action_qpos_addresses: tuple[int, ...]
    action_dof_addresses: tuple[int, ...]
    action_references: tuple[float, ...]
    root_qpos_address: int
    root_dof_address: int
    left_foot_body_ids: tuple[int, ...]
    right_foot_body_ids: tuple[int, ...]


def compile_dropbear_model(
    project_root: Path,
    *,
    timestep: float = 0.002,
) -> CompiledDropbearModel:
    if mujoco is None:
        raise RuntimeError("MuJoCo is not installed")

    manifest_path = (
        project_root / "web" / "assets" / "robot" / "dropbear-physics-manifest.json"
    )
    articulation_path = (
        project_root / "web" / "assets" / "robot" / "dropbear-articulation.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    articulation = json.loads(articulation_path.read_text(encoding="utf-8"))
    body_physics = {body["path"]: body for body in manifest["bodies"]}
    body_visual = {body["path"]: body for body in articulation["bodies"]}
    tree_joints = [joint for joint in articulation["joints"] if joint.get("tree")]
    closure_joints = [
        joint for joint in articulation["joints"] if joint.get("closure")
    ]
    children: dict[str, list[dict]] = {}
    for joint in tree_joints:
        children.setdefault(joint["parent"], []).append(joint)

    root_path = "/humanoid/world"
    reachable = {root_path}
    frontier = [root_path]
    while frontier:
        parent = frontier.pop()
        for joint in children.get(parent, []):
            child = joint["child"]
            if child not in reachable:
                reachable.add(child)
                frontier.append(child)

    lines = [
        '<mujoco model="dropbear_usd_mass_inertia_proxy">',
        '  <compiler angle="radian" coordinate="local" balanceinertia="true"/>',
        (
            f'  <option timestep="{float(timestep):.9g}" gravity="0 0 '
            f'-{GRAVITY_MPS2}" integrator="implicitfast" iterations="80" '
            'tolerance="1e-9"/>'
        ),
        '  <size njmax="8000" nconmax="2000"/>',
        '  <default>',
        (
            '    <joint damping="0.9" armature="0.012" '
            'frictionloss="0.015" limited="true"/>'
        ),
        (
            '    <geom density="0" contype="1" conaffinity="2" '
            'friction="0.9 0.02 0.003" solref="0.004 1"/>'
        ),
        '  </default>',
        '  <worldbody>',
        (
            f'    <geom name="ground" type="plane" pos="0 0 {GROUND_Z_M}" '
            'size="8 8 0.1" '
            'contype="2" conaffinity="1" friction="1.0 0.025 0.004" '
            'rgba="0.08 0.09 0.11 1"/>'
        ),
    ]

    def add_body_child(joint: dict, parent_path: str, depth: int) -> None:
        child = joint["child"]
        if child not in reachable:
            return
        physics = body_physics[child]
        visual = body_visual[child]
        parent_world = _matrix(body_visual[parent_path]["matrix"])
        world = _matrix(visual["matrix"])
        position, quaternion = _body_relative_transform(world, parent_world)
        indent = "  " * depth
        name = _body_name(physics["name"])
        lines.append(
            f'{indent}<body name="{escape(name)}" pos="{_numbers(position)}" '
            f'quat="{_numbers(quaternion)}">'
        )
        mass = max(float(physics["massKg"]), 1e-6)
        inertia = [max(float(value), 1e-8) for value in physics["diagonalInertiaKgM2"]]
        com = physics["centerOfMass"]
        principal = physics["principalAxes"]
        lines.append(
            f'{indent}  <inertial pos="{_numbers(com)}" mass="{mass:.9g}" '
            f'diaginertia="{_numbers(inertia)}" quat="{_numbers(principal)}"/>'
        )
        if joint["type"] in {"revolute", "prismatic"}:
            local_position = (
                joint["localPos1"]
                if joint["child"] == joint["body1"]
                else joint["localPos0"]
            )
            axis_local = (
                np.asarray(joint["axisWorldAtRest"], dtype=np.float64)
                @ world[:3, :3].T
            )
            axis_local /= max(float(np.linalg.norm(axis_local)), 1e-12)
            joint_type = "hinge" if joint["type"] == "revolute" else "slide"
            lower = float(
                -180.0 if joint.get("lower") is None else joint["lower"]
            )
            upper = float(
                180.0 if joint.get("upper") is None else joint["upper"]
            )
            if joint_type == "hinge":
                lower, upper = math.radians(lower), math.radians(upper)
            if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
                lower, upper = (-math.pi, math.pi)
            reference = float(joint.get("initialPositionRad") or 0.0)
            lines.append(
                f'{indent}  <joint name="{escape(_safe_name(joint["name"]))}" '
                f'type="{joint_type}" pos="{_numbers(local_position)}" '
                f'axis="{_numbers(axis_local)}" '
                f'range="{lower:.9g} {upper:.9g}" ref="{reference:.9g}"/>'
            )
        radii = _proxy_radii(mass, inertia)
        lines.append(
            f'{indent}  <geom name="proxy_{escape(name)}" type="ellipsoid" '
            f'pos="{_numbers(com)}" quat="{_numbers(principal)}" '
            f'size="{_numbers(radii)}"/>'
        )
        for descendant in children.get(child, []):
            add_body_child(descendant, child, depth + 1)
        lines.append(f"{indent}</body>")

    # Open the root once, then recurse through the authored spanning tree.
    root_physics = body_physics[root_path]
    root_visual = body_visual[root_path]
    root_world = _matrix(root_visual["matrix"])
    root_name = _body_name(root_physics["name"])
    lines.append(
        f'    <body name="{escape(root_name)}" '
        f'pos="{_numbers(root_world[3, :3])}" '
        f'quat="{_numbers(_matrix_to_quaternion(root_world[:3, :3].T))}">'
    )
    lines.append(
        '      <joint name="root_free" type="free" limited="false" '
        'damping="6.0" armature="0.05"/>'
    )
    root_mass = max(float(root_physics["massKg"]), 1e-6)
    root_inertia = [
        max(float(value), 1e-8)
        for value in root_physics["diagonalInertiaKgM2"]
    ]
    root_com = root_physics["centerOfMass"]
    root_principal = root_physics["principalAxes"]
    lines.append(
        f'      <inertial pos="{_numbers(root_com)}" mass="{root_mass:.9g}" '
        f'diaginertia="{_numbers(root_inertia)}" '
        f'quat="{_numbers(root_principal)}"/>'
    )
    lines.append(
        f'      <geom name="proxy_{escape(root_name)}" type="ellipsoid" '
        f'pos="{_numbers(root_com)}" quat="{_numbers(root_principal)}" '
        f'size="{_numbers(_proxy_radii(root_mass, root_inertia))}"/>'
    )
    for root_joint in children.get(root_path, []):
        add_body_child(root_joint, root_path, 3)
    lines.extend(["    </body>", "  </worldbody>", "  <equality>"])
    for index, joint in enumerate(closure_joints):
        if joint["body0"] not in reachable or joint["body1"] not in reachable:
            continue
        body0_world = _matrix(body_visual[joint["body0"]]["matrix"])
        anchor = (
            np.append(
                np.asarray(joint["localPos0"], dtype=np.float64),
                1.0,
            )
            @ body0_world
        )[:3]
        lines.append(
            f'    <connect name="closure_{index}_{escape(_safe_name(joint["name"]))}" '
            f'body1="{escape(_body_name(body_physics[joint["body0"]]["name"]))}" '
            f'body2="{escape(_body_name(body_physics[joint["body1"]]["name"]))}" '
            f'anchor="{_numbers(anchor)}" '
            'solref="0.003 1"/>'
        )
    lines.extend(["  </equality>", "  <actuator>"])
    for index, joint_name in enumerate(ACTION_TO_USD_JOINT):
        lines.append(
            f'    <position name="motor_{index}" '
            f'joint="{escape(_safe_name(joint_name))}" kp="220" kv="22" '
            'ctrllimited="true" ctrlrange="-3.14159265 3.14159265" '
            'forcelimited="true" forcerange="-320 320"/>'
        )
    lines.extend(["  </actuator>", "</mujoco>"])
    xml = "\n".join(lines)
    try:
        model = mujoco.MjModel.from_xml_string(xml)
    except ValueError as error:
        raise RuntimeError(f"Dropbear MuJoCo compilation failed: {error}") from error

    action_joint_ids = tuple(
        int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, _safe_name(name)))
        for name in ACTION_TO_USD_JOINT
    )
    if any(identifier < 0 for identifier in action_joint_ids):
        raise RuntimeError("compiled Dropbear model is missing an RL motor joint")
    root_joint_id = int(
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "root_free")
    )
    return CompiledDropbearModel(
        model=model,
        action_joint_ids=action_joint_ids,
        action_qpos_addresses=tuple(
            int(model.jnt_qposadr[identifier]) for identifier in action_joint_ids
        ),
        action_dof_addresses=tuple(
            int(model.jnt_dofadr[identifier]) for identifier in action_joint_ids
        ),
        action_references=tuple(
            float(model.qpos0[int(model.jnt_qposadr[identifier])])
            for identifier in action_joint_ids
        ),
        root_qpos_address=int(model.jnt_qposadr[root_joint_id]),
        root_dof_address=int(model.jnt_dofadr[root_joint_id]),
        left_foot_body_ids=tuple(
            int(
                mujoco.mj_name2id(
                    model,
                    mujoco.mjtObj.mjOBJ_BODY,
                    _body_name(body["name"]),
                )
            )
            for body in manifest["bodies"]
            if body["path"] in reachable
            and body["name"].startswith("LL_")
            and float(body["worldMatrixAtRest"][14]) < 0.30
        ),
        right_foot_body_ids=tuple(
            int(
                mujoco.mj_name2id(
                    model,
                    mujoco.mjtObj.mjOBJ_BODY,
                    _body_name(body["name"]),
                )
            )
            for body in manifest["bodies"]
            if body["path"] in reachable
            and body["name"].startswith("RL_")
            and float(body["worldMatrixAtRest"][14]) < 0.30
        ),
    )


class MujocoDropbearBatch:
    """Small vector of source-derived MuJoCo worlds for PPO rollouts."""

    def __init__(
        self,
        project_root: Path,
        num_envs: int,
        *,
        control_dt: float,
    ):
        compiled = compile_dropbear_model(project_root)
        self.compiled = compiled
        self.model = compiled.model
        self.data = [mujoco.MjData(self.model) for _ in range(int(num_envs))]
        self.substeps = max(1, round(float(control_dt) / self.model.opt.timestep))
        self.mass_kg = float(self.model.body_mass.sum())

    def reset(self, q: np.ndarray, masks: np.ndarray) -> None:
        for index, enabled in enumerate(masks):
            if not bool(enabled):
                continue
            data = self.data[index]
            mujoco.mj_resetData(self.model, data)
            root = self.compiled.root_qpos_address
            # The authored stage puts the feet above Z=0 in the rest pose.
            data.qpos[root : root + 3] = (0.0, 0.0, 0.0)
            data.qpos[root + 3 : root + 7] = (1.0, 0.0, 0.0, 0.0)
            data.ctrl[:] = (
                q[index]
                + np.asarray(self.compiled.action_references)
            )
            mujoco.mj_forward(self.model, data)

    def step(
        self,
        targets: np.ndarray,
        *,
        vertical_constraint: bool = False,
    ) -> dict[str, np.ndarray]:
        count = len(self.data)
        q = np.zeros((count, len(ACTION_TO_USD_JOINT)), dtype=np.float32)
        dq = np.zeros_like(q)
        root = np.zeros((count, 11), dtype=np.float32)
        contacts = np.zeros((count, 4), dtype=np.float32)
        foot_heights = np.zeros_like(contacts)
        for environment, data in enumerate(self.data):
            data.ctrl[:] = (
                targets[environment]
                + np.asarray(self.compiled.action_references)
            )
            for _ in range(self.substeps):
                mujoco.mj_step(self.model, data)
                if vertical_constraint:
                    qpos = self.compiled.root_qpos_address
                    dof = self.compiled.root_dof_address
                    data.qpos[qpos + 2] = 0.0
                    data.qvel[dof + 2] = 0.0
                    mujoco.mj_forward(self.model, data)
            for action_index, address in enumerate(
                self.compiled.action_qpos_addresses
            ):
                q[environment, action_index] = (
                    data.qpos[address]
                    - self.compiled.action_references[action_index]
                )
            for action_index, address in enumerate(
                self.compiled.action_dof_addresses
            ):
                dq[environment, action_index] = data.qvel[address]
            qpos = self.compiled.root_qpos_address
            dof = self.compiled.root_dof_address
            quaternion = data.qpos[qpos + 3 : qpos + 7]
            orientation = _quaternion_to_euler_wxyz(quaternion)
            root[environment] = (
                float(data.qpos[qpos + 2]) + 0.80,
                float(data.qvel[dof + 2]),
                float(data.qpos[qpos]),
                float(data.qpos[qpos + 1]),
                float(data.qvel[dof]),
                float(orientation[0]),
                float(orientation[1]),
                float(orientation[2]),
                float(data.qvel[dof + 3]),
                float(data.qvel[dof + 4]),
                float(data.qvel[dof + 5]),
            )
            left_z = min(
                float(data.xpos[identifier, 2])
                for identifier in self.compiled.left_foot_body_ids
            ) - GROUND_Z_M
            right_z = min(
                float(data.xpos[identifier, 2])
                for identifier in self.compiled.right_foot_body_ids
            ) - GROUND_Z_M
            foot_heights[environment] = (left_z, left_z, right_z, right_z)
            left_force = 0.0
            right_force = 0.0
            for contact_index in range(data.ncon):
                contact = data.contact[contact_index]
                body1 = int(self.model.geom_bodyid[contact.geom1])
                body2 = int(self.model.geom_bodyid[contact.geom2])
                force = np.zeros(6, dtype=np.float64)
                mujoco.mj_contactForce(self.model, data, contact_index, force)
                normal_force = max(0.0, float(force[0]))
                bodies = {body1, body2}
                if bodies.intersection(self.compiled.left_foot_body_ids):
                    left_force += normal_force
                if bodies.intersection(self.compiled.right_foot_body_ids):
                    right_force += normal_force
            contacts[environment] = (
                0.5 * left_force / GRAVITY_MPS2,
                0.5 * left_force / GRAVITY_MPS2,
                0.5 * right_force / GRAVITY_MPS2,
                0.5 * right_force / GRAVITY_MPS2,
            )
        return {
            "q": q,
            "dq": dq,
            "root": root,
            "contactLoadsKg": contacts,
            "footHeights": foot_heights,
        }
