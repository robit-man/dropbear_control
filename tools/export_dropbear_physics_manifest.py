#!/usr/bin/env python3
"""Extract the physical contract authored in Dropbear's source USD.

This deliberately does not turn the browser GLB into a physics model. It reads
the binary source USD with OpenUSD and preserves mass, inertia, collision
envelopes, physical joints, force drives, gravity, and source identity for
backend admission and regression tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from pxr import Gf, Usd, UsdGeom, UsdPhysics


EXPECTED_SHA256 = (
    "ef4434e0adb5a74cb0fe8e779c49aac4ebdcba48998ed519cf17ab16d822e073"
)
SOURCE_COMMIT = "3c37aedce6d445205671d5714d05ae28b8c90e2c"


def vector(value: Any) -> list[float]:
    return [float(component) for component in value]


def quaternion(value: Any) -> list[float]:
    imaginary = value.GetImaginary()
    return [
        float(value.GetReal()),
        float(imaginary[0]),
        float(imaginary[1]),
        float(imaginary[2]),
    ]


def finite(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_collision_envelope(
    body: Usd.Prim,
    xforms: UsdGeom.XformCache,
    bbox_cache: UsdGeom.BBoxCache,
) -> dict[str, Any] | None:
    collision = body.GetChild("collisions")
    if not collision:
        return None
    world_box = bbox_cache.ComputeWorldBound(collision).ComputeAlignedBox()
    minimum = world_box.GetMin()
    maximum = world_box.GetMax()
    if any(not math.isfinite(float(value)) for value in (*minimum, *maximum)):
        return None
    inverse = xforms.GetLocalToWorldTransform(body).GetInverse()
    corners = [
        inverse.Transform(Gf.Vec3d(x, y, z))
        for x in (minimum[0], maximum[0])
        for y in (minimum[1], maximum[1])
        for z in (minimum[2], maximum[2])
    ]
    local_minimum = [
        min(float(corner[index]) for corner in corners) for index in range(3)
    ]
    local_maximum = [
        max(float(corner[index]) for corner in corners) for index in range(3)
    ]
    return {
        "kind": "usd-collision-group-local-envelope",
        "center": [
            (low + high) * 0.5
            for low, high in zip(local_minimum, local_maximum, strict=True)
        ],
        "halfExtents": [
            (high - low) * 0.5
            for low, high in zip(local_minimum, local_maximum, strict=True)
        ],
        "sourceCollisionPath": str(collision.GetPath()),
        "exactCollisionGeometryRequiredForHighFidelity": True,
    }


def body_record(
    prim: Usd.Prim,
    xforms: UsdGeom.XformCache,
    bbox_cache: UsdGeom.BBoxCache,
) -> dict[str, Any]:
    mass_api = UsdPhysics.MassAPI(prim)
    return {
        "name": prim.GetName(),
        "path": str(prim.GetPath()),
        "massKg": finite(mass_api.GetMassAttr().Get()),
        "centerOfMass": vector(
            mass_api.GetCenterOfMassAttr().Get() or Gf.Vec3f()
        ),
        "diagonalInertiaKgM2": vector(
            mass_api.GetDiagonalInertiaAttr().Get() or Gf.Vec3f()
        ),
        "principalAxes": quaternion(
            mass_api.GetPrincipalAxesAttr().Get() or Gf.Quatf(1)
        ),
        "worldMatrixAtRest": [
            float(value)
            for row in xforms.GetLocalToWorldTransform(prim)
            for value in row
        ],
        "collision": local_collision_envelope(
            prim, xforms, bbox_cache
        ),
    }


def joint_record(prim: Usd.Prim) -> dict[str, Any]:
    joint = UsdPhysics.Joint(prim)
    drives = {}
    for name in ("angular", "linear"):
        if not prim.HasAPI(UsdPhysics.DriveAPI, name):
            continue
        drive = UsdPhysics.DriveAPI(prim, name)
        drives[name] = {
            "type": str(drive.GetTypeAttr().Get() or ""),
            "maxForce": finite(drive.GetMaxForceAttr().Get()),
            "stiffness": finite(drive.GetStiffnessAttr().Get()),
            "damping": finite(drive.GetDampingAttr().Get()),
            "targetPosition": finite(drive.GetTargetPositionAttr().Get()),
            "targetVelocity": finite(drive.GetTargetVelocityAttr().Get()),
        }
    body0 = joint.GetBody0Rel().GetTargets()
    body1 = joint.GetBody1Rel().GetTargets()
    return {
        "name": prim.GetName(),
        "path": str(prim.GetPath()),
        "type": prim.GetTypeName(),
        "body0": str(body0[0]) if body0 else None,
        "body1": str(body1[0]) if body1 else None,
        "localPos0": vector(
            joint.GetLocalPos0Attr().Get() or Gf.Vec3f()
        ),
        "localPos1": vector(
            joint.GetLocalPos1Attr().Get() or Gf.Vec3f()
        ),
        "localRot0": quaternion(
            joint.GetLocalRot0Attr().Get() or Gf.Quatf(1)
        ),
        "localRot1": quaternion(
            joint.GetLocalRot1Attr().Get() or Gf.Quatf(1)
        ),
        "axis": str(prim.GetAttribute("physics:axis").Get() or ""),
        "lower": finite(prim.GetAttribute("physics:lowerLimit").Get()),
        "upper": finite(prim.GetAttribute("physics:upperLimit").Get()),
        "excludeFromArticulation": bool(
            prim.GetAttribute("physics:excludeFromArticulation").Get()
            or False
        ),
        "drives": drives,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("usd", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    digest = file_sha256(args.usd)
    if digest != EXPECTED_SHA256:
        raise SystemExit(
            f"source USD SHA-256 mismatch: {digest} != {EXPECTED_SHA256}"
        )
    stage = Usd.Stage.Open(str(args.usd))
    if stage is None:
        raise SystemExit(f"could not open {args.usd}")
    xforms = UsdGeom.XformCache()
    bbox_cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        [UsdGeom.Tokens.default_, UsdGeom.Tokens.proxy],
        useExtentsHint=True,
    )
    bodies = [
        body_record(prim, xforms, bbox_cache)
        for prim in stage.Traverse()
        if prim.HasAPI(UsdPhysics.RigidBodyAPI)
    ]
    joints = [
        joint_record(prim)
        for prim in stage.Traverse()
        if prim.IsA(UsdPhysics.Joint)
    ]
    scene = next(
        (
            UsdPhysics.Scene(prim)
            for prim in stage.Traverse()
            if prim.IsA(UsdPhysics.Scene)
        ),
        None,
    )
    gravity_direction = (
        scene.GetGravityDirectionAttr().Get() if scene else Gf.Vec3f(0, 0, -1)
    )
    gravity_magnitude = (
        scene.GetGravityMagnitudeAttr().Get() if scene else 9.80665
    )
    drive_count = sum(len(joint["drives"]) for joint in joints)
    payload = {
        "schema": "dropbear-usd-physics-manifest-v1",
        "source": {
            "repository": "https://github.com/Hyperspawn/dropbear_rl",
            "commit": SOURCE_COMMIT,
            "path": "dropbear_model/Dropbear/usd/dropbear.usd",
            "sha256": digest,
        },
        "stage": {
            "upAxis": str(UsdGeom.GetStageUpAxis(stage)),
            "metersPerUnit": float(UsdGeom.GetStageMetersPerUnit(stage)),
            "gravityDirection": vector(gravity_direction),
            "gravityMagnitudeMps2": float(gravity_magnitude),
        },
        "statistics": {
            "rigidBodies": len(bodies),
            "authoredMasses": sum(
                body["massKg"] is not None for body in bodies
            ),
            "collisionGroups": sum(
                body["collision"] is not None for body in bodies
            ),
            "physicsJoints": len(joints),
            "forceDrives": drive_count,
            "totalAuthoredMassKg": sum(
                body["massKg"] or 0 for body in bodies
            ),
        },
        "admission": {
            "sourceUsdRequired": True,
            "exactCollisionGeometryRequired": True,
            "browserEnvelopeCollisionHighFidelity": False,
            "authoritativeBackend": "Isaac Sim / PhysX",
        },
        "bodies": bodies,
        "joints": joints,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
