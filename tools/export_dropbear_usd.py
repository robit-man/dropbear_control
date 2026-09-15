#!/usr/bin/env python3
"""Create a lightweight browser cache and articulation manifest from Dropbear's USD.

The source asset is not vendored by this repository. Pass the released USD
from robit-man/dropbear-locomotion and this tool will:

1. read the binary USD crate with OpenUSD,
2. retain the named rigid-body partition,
3. replace the detailed AGX Orin CAD with a proxy envelope,
4. decimate visual meshes into a responsive GLB cache, and
5. emit every physical joint plus the low-level CAN-to-USD binding table.

The generated cache is an adaptation of the CC-BY-NC-SA-4.0 source asset.
It is for visualization; Isaac/PhysX remains authoritative for loop closure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np
import trimesh
from pxr import Gf, Usd, UsdGeom, UsdPhysics, UsdShade


SOURCE_COMMIT = "a397be863fed2d328c2e8f62c3db2f1e23575eb1"
SOURCE_REPOSITORY = "https://github.com/robit-man/dropbear-locomotion"
SOURCE_SHA256 = "45586414b065cd982d487cbd868fe982108b3b8ccec64d3dfcf629652ed8db0f"
# The source head assembly contains two extremely detailed AGX carrier-board
# meshes (755,895 source triangles). Browser rendering needs their occupied
# envelope, not individual PCB features. Their rigid-body transform, mass,
# inertia, collision shapes, and every upstream/downstream joint remain in the
# manifest; only these visual mesh prims are replaced with one 12-triangle box.
AGX_PROXY_MESH_TOKENS = (
    "00_top_lvl_p3737_01142022",
    "245_82972_0000_000_asm_07192018",
)
SDK_JOINTS = [
    "LH_yaw", "LH_pitch", "LH_roll", "LH_Revolute41", "LH_wrist_roll",
    "RH_yaw", "RH_pitch", "RH_roll", "RH_Revolute41", "RH_wrist_roll",
    "PG_left_leg_pitch", "PG_left_leg_roll", "PG_right_leg_pitch", "PG_right_leg_roll",
    "LL_hip_joint", "LL_knee_actuator_joint", "RL_hip_joint", "RL_knee_actuator_joint",
    "LL_Revolute28", "LL_Revolute29", "RL_Revolute28", "RL_Revolute29",
    "head_LeadScrew1", "head_LeadScrew2", "head_LeadScrew3",
    "head_LeadScrew4", "head_LeadScrew5", "head_LeadScrew6",
]

# Physical-axis mapping between the current low-level firmware and the USD.
# PG_* naming does not match the firmware labels: the USD world axes show that
# PG_*_leg_pitch is the hip-roll axis and PG_*_leg_roll is the hip-yaw axis.
CAN_BINDINGS = [
    (0x141, "left", "outer_calf", "LL_Revolute81"),
    (0x142, "left", "inner_calf", "LL_Revolute67"),
    (0x143, "right", "inner_calf", "RL_Revolute67"),
    (0x144, "right", "outer_calf", "RL_Revolute81"),
    (0x145, "left", "knee", "LL_knee_actuator_joint"),
    (0x146, "left", "hip_pitch", "LL_hip_joint"),
    (0x147, "right", "hip_pitch", "RL_hip_joint"),
    (0x148, "right", "knee", "RL_knee_actuator_joint"),
    (0x149, "left", "hip_yaw", "PG_left_leg_roll"),
    (0x14A, "left", "hip_roll", "PG_left_leg_pitch"),
    (0x14B, "right", "hip_roll", "PG_right_leg_pitch"),
    (0x14C, "right", "hip_yaw", "PG_right_leg_roll"),
]

ARM_BINDINGS = [
    ("arm-left-shoulder-pitch", "left", "shoulder_pitch", "LH_yaw", "RMD-X10", "torso", False),
    ("arm-left-shoulder-yaw", "left", "shoulder_yaw", "LH_pitch", "RMD-X8", "arm", False),
    ("arm-left-shoulder-roll", "left", "shoulder_roll", "LH_roll", "RMD-X8", "arm", False),
    ("arm-left-elbow-pitch", "left", "elbow_pitch", "LH_Revolute41", "RMD-X8", "arm", True),
    ("arm-left-wrist-roll", "left", "wrist_roll", "LH_wrist_roll", "RMD-X8", "arm", False),
    ("arm-right-shoulder-pitch", "right", "shoulder_pitch", "RH_yaw", "RMD-X10", "torso", False),
    ("arm-right-shoulder-yaw", "right", "shoulder_yaw", "RH_pitch", "RMD-X8", "arm", False),
    ("arm-right-shoulder-roll", "right", "shoulder_roll", "RH_roll", "RMD-X8", "arm", False),
    ("arm-right-elbow-pitch", "right", "elbow_pitch", "RH_Revolute41", "RMD-X8", "arm", True),
    ("arm-right-wrist-roll", "right", "wrist_roll", "RH_wrist_roll", "RMD-X8", "arm", False),
]

INITIAL_POSITIONS = {
    "LH_elbow_joint": 0.3,
    "RH_elbow_joint": 0.3,
    "PG_left_leg_pitch": -0.1,
    "PG_right_leg_pitch": -0.1,
    "LL_hip_joint": 0.0,
    "LL_knee_actuator_joint": 0.3,
    "LL_Revolute67": -0.2,
    "LL_Revolute81": 0.0,
    "RL_hip_joint": 0.0,
    "RL_knee_actuator_joint": 0.3,
    "RL_Revolute67": -0.2,
    "RL_Revolute81": 0.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("usd", type=Path, help="Path to dropbear.usd")
    parser.add_argument("glb", type=Path, help="Output browser GLB")
    parser.add_argument("manifest", type=Path, help="Output articulation JSON")
    parser.add_argument("--ratio", type=float, default=0.025, help="Target triangle ratio per source mesh")
    parser.add_argument(
        "--meshopt-cli",
        type=Path,
        help="Optional gltf-transform CLI used to weld and simplify the complete browser GLB",
    )
    parser.add_argument(
        "--meshopt-ratio",
        type=float,
        default=0.2,
        help="Final meshoptimizer vertex ratio when --meshopt-cli is used",
    )
    return parser.parse_args()


def glb_triangle_count(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError(f"not a binary glTF: {path}")
    json_length, json_type = struct.unpack_from("<II", data, 12)
    if json_type != 0x4E4F534A:
        raise ValueError(f"GLB JSON chunk is missing: {path}")
    document = json.loads(data[20 : 20 + json_length].rstrip(b"\x00 "))
    triangles = 0
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            if primitive.get("mode", 4) != 4 or "indices" not in primitive:
                continue
            triangles += document["accessors"][primitive["indices"]]["count"] // 3
    return triangles


def matrix_for_three(matrix: Gf.Matrix4d) -> list[float]:
    # Gf serializes its row-vector matrix in the same 16-number order Three.js
    # expects for its column-major Matrix4 elements.
    return np.asarray(matrix, dtype=np.float64).reshape(16).tolist()


def matrix_for_trimesh(matrix: Gf.Matrix4d) -> np.ndarray:
    # Trimesh multiplies column vectors, so transpose the Gf row-vector matrix.
    return np.asarray(matrix, dtype=np.float64).T


def quaternion(value) -> list[float]:
    imaginary = value.GetImaginary()
    return [float(value.GetReal()), float(imaginary[0]), float(imaginary[1]), float(imaginary[2])]


def vec(value) -> list[float]:
    return [float(component) for component in value]


def material_color(mesh_prim: Usd.Prim) -> tuple[float, float, float, float]:
    display = UsdGeom.Gprim(mesh_prim).GetDisplayColorAttr().Get()
    if display:
        rgb = display[0]
        return float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0
    material, _ = UsdShade.MaterialBindingAPI(mesh_prim).ComputeBoundMaterial()
    if material:
        for child in material.GetPrim().GetChildren():
            attr = child.GetAttribute("inputs:diffuse_color_constant")
            color = attr.Get() if attr else None
            if color is not None:
                return float(color[0]), float(color[1]), float(color[2]), 1.0
    return 0.58, 0.61, 0.64, 1.0


def triangulate(counts, indices) -> np.ndarray:
    triangles: list[tuple[int, int, int]] = []
    offset = 0
    for count in counts:
        polygon = indices[offset:offset + count]
        for index in range(1, count - 1):
            triangles.append((polygon[0], polygon[index], polygon[index + 1]))
        offset += count
    return np.asarray(triangles, dtype=np.int64)


def visual_meshes(stage: Usd.Stage, body: Usd.Prim, ratio: float) -> list[tuple[trimesh.Trimesh, tuple]]:
    visual = body.GetChild("visuals")
    prototype = visual.GetPrototype() if visual else None
    if not prototype:
        return []
    xforms = UsdGeom.XformCache()
    meshes_by_color: dict[tuple, list[trimesh.Trimesh]] = defaultdict(list)
    agx_proxy_bounds: list[np.ndarray] = []
    for prim in Usd.PrimRange(prototype):
        if not prim.IsA(UsdGeom.Mesh):
            continue
        source = UsdGeom.Mesh(prim)
        points = np.asarray(source.GetPointsAttr().Get() or [], dtype=np.float64)
        counts = np.asarray(source.GetFaceVertexCountsAttr().Get() or [], dtype=np.int64)
        indices = np.asarray(source.GetFaceVertexIndicesAttr().Get() or [], dtype=np.int64)
        if len(points) < 3 or len(indices) < 3:
            continue
        faces = indices.reshape((-1, 3)) if np.all(counts == 3) else triangulate(counts, indices)
        mesh = trimesh.Trimesh(vertices=points, faces=faces, process=True, validate=False)
        mesh.apply_transform(matrix_for_trimesh(xforms.GetLocalToWorldTransform(prim)))
        if any(token in str(prim.GetPath()) for token in AGX_PROXY_MESH_TOKENS):
            agx_proxy_bounds.append(mesh.bounds)
            continue
        if len(mesh.faces) > 160:
            target = max(80, int(len(mesh.faces) * ratio))
            try:
                mesh = mesh.simplify_quadric_decimation(face_count=target, aggression=7)
            except (ValueError, RuntimeError):
                pass
        color = tuple(round(component, 4) for component in material_color(prim))
        meshes_by_color[color].append(mesh)

    if agx_proxy_bounds:
        lower = np.min(np.stack([bounds[0] for bounds in agx_proxy_bounds]), axis=0)
        upper = np.max(np.stack([bounds[1] for bounds in agx_proxy_bounds]), axis=0)
        extents = np.maximum(upper - lower, 1e-6)
        transform = np.eye(4)
        transform[:3, 3] = (lower + upper) * 0.5
        proxy = trimesh.creation.box(extents=extents, transform=transform)
        meshes_by_color[(0.18, 0.20, 0.22, 1.0)].append(proxy)

    result = []
    for color, meshes in meshes_by_color.items():
        combined = trimesh.util.concatenate(meshes)
        combined.remove_unreferenced_vertices()
        combined.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                baseColorFactor=[int(component * 255) for component in color],
                metallicFactor=0.42,
                roughnessFactor=0.48,
            )
        )
        result.append((combined, color))
    return result


def joint_record(stage: Usd.Stage, prim: Usd.Prim, xforms: UsdGeom.XformCache) -> dict | None:
    joint = UsdPhysics.Joint(prim)
    body0 = joint.GetBody0Rel().GetTargets()
    body1 = joint.GetBody1Rel().GetTargets()
    if not body0 or not body1:
        return None
    local_rot0 = joint.GetLocalRot0Attr().Get() or Gf.Quatf(1)
    local_rot1 = joint.GetLocalRot1Attr().Get() or Gf.Quatf(1)
    local_pos0 = joint.GetLocalPos0Attr().Get() or Gf.Vec3f()
    local_pos1 = joint.GetLocalPos1Attr().Get() or Gf.Vec3f()
    axis_name = str(prim.GetAttribute("physics:axis").Get() or "X")
    axis = {"X": Gf.Vec3f(1, 0, 0), "Y": Gf.Vec3f(0, 1, 0), "Z": Gf.Vec3f(0, 0, 1)}[axis_name]
    parent = stage.GetPrimAtPath(body0[0])
    axis_in_body0 = local_rot0.Transform(axis)
    axis_world = xforms.GetLocalToWorldTransform(parent).TransformDir(Gf.Vec3d(*axis_in_body0)).GetNormalized()
    lower = prim.GetAttribute("physics:lowerLimit").Get()
    upper = prim.GetAttribute("physics:upperLimit").Get()
    return {
        "name": prim.GetName(),
        "path": str(prim.GetPath()),
        "type": prim.GetTypeName().replace("Physics", "").replace("Joint", "").lower(),
        "body0": str(body0[0]),
        "body1": str(body1[0]),
        "localPos0": vec(local_pos0),
        "localPos1": vec(local_pos1),
        "localRot0": quaternion(local_rot0),
        "localRot1": quaternion(local_rot1),
        "axis": axis_name,
        "axisWorldAtRest": vec(axis_world),
        "lower": None if lower is None or not math.isfinite(float(lower)) else float(lower),
        "upper": None if upper is None or not math.isfinite(float(upper)) else float(upper),
        "sdkJoint": prim.GetName() in SDK_JOINTS,
        "initialPositionRad": INITIAL_POSITIONS.get(prim.GetName(), 0.0),
        "tree": False,
        "reverse": False,
    }


def mark_spanning_tree(joints: list[dict], root: str) -> tuple[int, int]:
    known = {root}
    pending = list(joints)
    progress = True
    while progress:
        progress = False
        for joint in list(pending):
            body0_known = joint["body0"] in known
            body1_known = joint["body1"] in known
            if body0_known == body1_known:
                continue
            joint["tree"] = True
            joint["reverse"] = body1_known
            joint["parent"] = joint["body1"] if body1_known else joint["body0"]
            joint["child"] = joint["body0"] if body1_known else joint["body1"]
            known.add(joint["child"])
            pending.remove(joint)
            progress = True
    closures = sum(1 for joint in pending if joint["body0"] in known and joint["body1"] in known)
    for joint in pending:
        joint["closure"] = joint["body0"] in known and joint["body1"] in known
    return len(known), closures


def main() -> None:
    args = parse_args()
    source_sha256 = hashlib.sha256(args.usd.read_bytes()).hexdigest()
    if source_sha256 != SOURCE_SHA256:
        raise SystemExit(
            f"source USD SHA-256 mismatch: {source_sha256} != {SOURCE_SHA256}"
        )
    stage = Usd.Stage.Open(str(args.usd))
    if stage is None:
        raise SystemExit(f"Could not open {args.usd}")
    args.glb.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    xforms = UsdGeom.XformCache()
    bodies = [prim for prim in stage.Traverse() if prim.HasAPI(UsdPhysics.RigidBodyAPI)]
    joints = [
        record
        for prim in stage.Traverse()
        if prim.IsA(UsdPhysics.Joint)
        for record in [joint_record(stage, prim, xforms)]
        if record is not None
    ]
    root = "/humanoid/world"
    connected_bodies, closure_count = mark_spanning_tree(joints, root)

    scene = trimesh.Scene()
    source_triangles = 0
    output_triangles = 0
    rendered_bodies = 0
    for index, body in enumerate(bodies, start=1):
        body_meshes = visual_meshes(stage, body, args.ratio)
        if not body_meshes:
            continue
        rendered_bodies += 1
        body_name = body.GetName()
        body_transform = matrix_for_trimesh(xforms.GetLocalToWorldTransform(body))
        for material_index, (mesh, _) in enumerate(body_meshes):
            output_triangles += len(mesh.faces)
            scene.add_geometry(
                mesh,
                node_name=f"BODY__{body_name}__{material_index}",
                geom_name=f"{body_name}__{material_index}",
                transform=body_transform,
            )
        visual = body.GetChild("visuals")
        prototype = visual.GetPrototype() if visual else None
        if prototype:
            source_triangles += sum(
                len(UsdGeom.Mesh(prim).GetFaceVertexCountsAttr().Get() or [])
                for prim in Usd.PrimRange(prototype)
                if prim.IsA(UsdGeom.Mesh)
            )
        print(f"[{index:02d}/{len(bodies)}] {body_name}: {len(body_meshes)} material groups")

    glb_bytes = scene.export(file_type="glb")
    args.glb.write_bytes(glb_bytes)
    meshopt = None
    if args.meshopt_cli:
        weld_path = args.glb.with_name(f"{args.glb.stem}.weld.glb")
        subprocess.run(
            [str(args.meshopt_cli), "weld", str(args.glb), str(weld_path)],
            check=True,
        )
        subprocess.run(
            [
                str(args.meshopt_cli),
                "simplify",
                str(weld_path),
                str(args.glb),
                "--ratio",
                str(args.meshopt_ratio),
                "--error",
                "1",
            ],
            check=True,
        )
        weld_path.unlink(missing_ok=True)
        output_triangles = glb_triangle_count(args.glb)
        meshopt = {
            "tool": "@gltf-transform/cli",
            "version": "4.2.1",
            "operations": ["weld", "meshoptimizer simplify"],
            "ratio": args.meshopt_ratio,
            "error": 1,
        }

    binding_records = []
    for can_id, side, key, usd_joint in CAN_BINDINGS:
        joint = next(record for record in joints if record["name"] == usd_joint)
        binding_records.append({
            "canId": f"0x{can_id:03X}",
            "canIdNumber": can_id,
            "side": side,
            "firmwareJoint": key,
            "usdJoint": usd_joint,
            "usdPath": joint["path"],
            "body0": joint["body0"],
            "body1": joint["body1"],
            "axisWorldAtRest": joint["axisWorldAtRest"],
            "mappingBasis": (
                f"RMD-X8 {key.replace('_', ' ')} motor driver axis; physical USD body location"
                if key in {"inner_calf", "outer_calf"}
                else "physical USD axis and body location"
            ),
        })

    arm_binding_records = []
    for identifier, side, physical_joint, usd_joint, motor, mount, closed_loop in ARM_BINDINGS:
        joint = next(record for record in joints if record["name"] == usd_joint)
        arm_binding_records.append({
            "id": identifier,
            "side": side,
            "physicalJoint": physical_joint,
            "usdJoint": usd_joint,
            "usdPath": joint["path"],
            "motor": motor,
            "mount": mount,
            **({"closedLoop": True} if closed_loop else {}),
            "firmwareCanId": None,
            "mappingBasis": (
                "Physical torso motor identification; authored USD joint name retained."
                if mount == "torso"
                else "Physical arm motor identification; authored USD joint name retained."
            ),
        })

    manifest = {
        "schema": "dropbear-browser-articulation-v1",
        "source": {
            "repository": SOURCE_REPOSITORY,
            "commit": SOURCE_COMMIT,
            "path": "dropbear_walk/isaaclab_asset/dropbear.usd",
            "sha256": source_sha256,
            "license": "CC-BY-NC-SA-4.0",
            "attribution": "Hyperspawn Robotics - Priyanshu Pareek and Cole Myers",
            "adaptation": "Visual meshes decimated and material model translated for browser rendering.",
            "postProcessing": meshopt,
        },
        "stage": {
            "defaultPrim": str(stage.GetDefaultPrim().GetPath()),
            "upAxis": str(UsdGeom.GetStageUpAxis(stage)),
            "metersPerUnit": UsdGeom.GetStageMetersPerUnit(stage),
        },
        "statistics": {
            "rigidBodies": len(bodies),
            "renderedBodies": rendered_bodies,
            "physicsJoints": len(joints),
            "treeJoints": sum(1 for joint in joints if joint["tree"]),
            "closureConstraints": closure_count,
            "connectedBodies": connected_bodies,
            "sourceTriangles": source_triangles,
            "browserTriangles": output_triangles,
            "sdkActuatedJoints": len(SDK_JOINTS),
            "rlBodyActions": 22,
            "neckLeadScrews": 6,
        },
        "bodies": [
            {
                "name": body.GetName(),
                "path": str(body.GetPath()),
                "matrix": matrix_for_three(xforms.GetLocalToWorldTransform(body)),
                "meshNodePrefix": f"BODY__{body.GetName()}__",
            }
            for body in bodies
        ],
        "joints": joints,
        "sdkJointNames": SDK_JOINTS,
        "canBindings": binding_records,
        "armMotorBindings": arm_binding_records,
        "browserKinematics": {
            "mode": "USD spanning-tree forward kinematics with damped least-squares passive-joint closure projection",
            "loopClosure": "Calf X8 and knee motor axes are commanded coordinates; passive leg joints are projected against retained USD closure anchors in-browser. Isaac/PhysX remains dynamics-authoritative.",
            "groundContact": "Lowest heel/toe foot-body patches drive a unilateral Z-only root guide with gravity settling and no-penetration projection. No friction, impact, lateral, rotational, or rigid-body dynamics are claimed.",
            "adaptations": {
                "AGX Orin": "Two detailed carrier-board visual meshes are replaced by one occupied-envelope proxy. Rigid-body mass, inertia, collision geometry, transform, and joint topology are retained.",
                "RL_Revolute81": "Use the corrected Z revolute basis authored by dropbear-locomotion.",
            },
            "armLinkages": [
                {
                    "side": "left",
                    "elbowMotor": "LH_Revolute41",
                    "passiveJoints": ["LH_Revolute42", "LH_elbow_joint", "LH_Revolute32", "LH_Revolute33", "LH_Revolute44"],
                    "closureConstraints": ["LH_Revolute123", "LH_Revolute125", "LH_Revolute127"],
                    "wristOutput": "LH_wrist_roll",
                },
                {
                    "side": "right",
                    "elbowMotor": "RH_Revolute41",
                    "passiveJoints": ["RH_Revolute42", "RH_elbow_joint", "RH_Revolute32", "RH_Revolute33", "RH_Revolute44"],
                    "closureConstraints": ["RH_Revolute123", "RH_Revolute125", "RH_Revolute127"],
                    "wristOutput": "RH_wrist_roll",
                },
            ],
            "calfLinkages": [
                {
                    "side": "left",
                    "inner": {"motorCrank": "LL_Revolute67", "rodPivot": "LL_Revolute112", "ankleClosure": "LL_Revolute117"},
                    "outer": {"motorCrank": "LL_Revolute81", "rodPivot": "LL_Revolute111", "ankleClosure": "LL_Revolute115"},
                    "footPivot": "LL_Revolute88",
                },
                {
                    "side": "right",
                    "inner": {"motorCrank": "RL_Revolute67", "rodPivot": "RL_Revolute112", "ankleClosure": "RL_Revolute117"},
                    "outer": {"motorCrank": "RL_Revolute81", "rodPivot": "RL_Revolute111", "ankleClosure": "RL_Revolute115"},
                    "footPivot": "RL_Revolute88",
                },
            ],
        },
    }
    args.manifest.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.glb} ({output_triangles:,} / {source_triangles:,} triangles)")
    print(f"Wrote {args.manifest} ({len(joints)} joints, {closure_count} closure constraints)")


if __name__ == "__main__":
    main()
