#!/usr/bin/env python3
"""Export the Dropbear X8/X10 source STEP motors for browser articulation.

The vendor STEP assemblies are flattened, so the output member is selected by
its measured B-Rep fingerprint from the checked-in review packet.  All other
solids stay fixed as the visual housing.  This is a visual partition only: it
does not claim that the cached STEP is a calibrated dynamics or support model.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import cadquery as cq


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from prove_cad_toolchain import export_glb_metres, mesh_signature  # noqa: E402
from render_flattened_partition_packet import measured_component  # noqa: E402


OUTPUT_ROOT = ROOT / "web" / "assets" / "cad"
MANIFEST_PATH = OUTPUT_ROOT / "dropbear-motor-cad.json"

MOTORS = (
    {
        "key": "x8-pro",
        "model": "RMD-X8-25 Pro V2",
        "dropbearClass": "RMD-X8",
        "source": ROOT
        / "assets/vendor/myactuator/RMD-X/X8-25/vendor"
        / "X8-25 Product information 240814/2D 3D"
        / "X8-25 (RMD-X8 PRO 1：9 V2).step",
        "sourceSha256": "751dcbccb675b6ac1ee2d745dea1e158857f459fe21ae3ca11c054c6931677c9",
        "outputFingerprint": "66bc2c81da7aac1e8283dd89acbae2f6257c19d89e7c694a8c62bcca6e980af6",
        "axis": "y",
        "axisVector": [0, 1, 0],
        "explodeDirection": [0, 1, 0],
        "explodeDistanceM": 0.035,
        "sourceUrl": "/cad-source/dropbear-x8-pro.step",
    },
    {
        "key": "x10-s2",
        "model": "RMD-X10-100 S2 V3",
        "dropbearClass": "RMD-X10",
        "source": ROOT
        / "assets/vendor/myactuator/RMD-X/X10-100/vendor/X10-100"
        / "(RMD-X10-S2 V3)Product information 240220/2D 3D"
        / "RMD-X10-S2 V3.step",
        "sourceSha256": "81304836d486734067048fb8130e1cfd7043c1a70496f2d180ce768ed2618ade",
        "outputFingerprint": "9b3546d9034a0bf8d8e2a8a25632e0c6b1b79552b46a36680e9e1028b42a226f",
        "axis": "z",
        "axisVector": [0, 0, 1],
        "explodeDirection": [0, 0, 1],
        "explodeDistanceM": 0.045,
        "sourceUrl": "/cad-source/dropbear-x10-s2.step",
    },
)


class MotorCadExportError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compound(shapes: list[cq.Shape]) -> cq.Shape:
    if not shapes:
        raise MotorCadExportError("cannot build an empty CAD partition")
    return shapes[0] if len(shapes) == 1 else cq.Compound.makeCompound(shapes)


def dimensions(shape: cq.Shape) -> list[float]:
    box = shape.BoundingBox()
    return [round(box.xlen, 3), round(box.ylen, 3), round(box.zlen, 3)]


def brep_vertices(shape: cq.Shape) -> list[tuple[float, float, float]]:
    return sorted(
        (
            round(vertex.Center().x, 5),
            round(vertex.Center().y, 5),
            round(vertex.Center().z, 5),
        )
        for vertex in shape.Vertices()
    )


def rotate_vertices(
    points: list[tuple[float, float, float]],
    axis: tuple[int, int, int],
    degrees: float,
) -> list[tuple[float, float, float]]:
    angle = math.radians(degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    ax, ay, az = axis
    result = []
    for x, y, z in points:
        dot = ax * x + ay * y + az * z
        cross_x = ay * z - az * y
        cross_y = az * x - ax * z
        cross_z = ax * y - ay * x
        result.append((
            round(x * cosine + cross_x * sine + ax * dot * (1 - cosine), 5),
            round(y * cosine + cross_y * sine + ay * dot * (1 - cosine), 5),
            round(z * cosine + cross_z * sine + az * dot * (1 - cosine), 5),
        ))
    return sorted(result)


def point_cloud_matches(
    expected: list[tuple[float, float, float]],
    observed: list[tuple[float, float, float]],
    tolerance_mm: float = 0.0002,
) -> bool:
    if len(expected) != len(observed):
        return False
    remaining = list(observed)
    for point in expected:
        best_index, best_observed = min(
            enumerate(remaining),
            key=lambda item: math.dist(point, item[1]),
        )
        best_distance = math.dist(point, best_observed)
        if best_distance > tolerance_mm:
            return False
        remaining.pop(best_index)
    return True


def export_motor(spec: dict[str, Any]) -> dict[str, Any]:
    source = spec["source"]
    if not source.is_file():
        raise MotorCadExportError(f"source STEP is absent: {source}")
    observed_sha = sha256(source)
    if observed_sha != spec["sourceSha256"]:
        raise MotorCadExportError(
            f"{spec['model']} source SHA changed: {observed_sha}"
        )

    imported = cq.importers.importStep(str(source)).val()
    solids = list(imported.Solids())
    if not solids:
        raise MotorCadExportError(f"{spec['model']} contains no solids")

    output_shapes: list[cq.Shape] = []
    housing_shapes: list[cq.Shape] = []
    component_fingerprints: list[str] = []
    for shape in solids:
        fingerprint, _record = measured_component(shape, "solid")
        component_fingerprints.append(fingerprint)
        if fingerprint == spec["outputFingerprint"]:
            output_shapes.append(shape)
        else:
            housing_shapes.append(shape)
    if len(output_shapes) != 1:
        raise MotorCadExportError(
            f"{spec['model']} output fingerprint matched {len(output_shapes)} solids"
        )

    housing = compound(housing_shapes)
    output = compound(output_shapes)
    if not housing.isValid() or not output.isValid():
        raise MotorCadExportError(f"{spec['model']} partition is invalid")

    axis = tuple(spec["axisVector"])
    rotated = output.rotate((0, 0, 0), axis, 37)
    output_points = brep_vertices(output)
    rotated_points = brep_vertices(rotated)
    _output_mesh_points, output_triangles = mesh_signature(output)
    housing_points, housing_triangles = mesh_signature(housing)
    housing_points_again, housing_triangles_again = mesh_signature(housing)
    if (
        output_points == rotated_points
        or not point_cloud_matches(
            rotate_vertices(output_points, axis, 37),
            rotated_points,
        )
        or not math.isclose(output.Volume(), rotated.Volume(), rel_tol=1e-12)
    ):
        raise MotorCadExportError(
            f"{spec['model']} output does not articulate about {spec['axis'].upper()}"
        )
    if (
        housing_triangles != housing_triangles_again
        or housing_points != housing_points_again
    ):
        raise MotorCadExportError(f"{spec['model']} housing changed during proof")

    directory = OUTPUT_ROOT / spec["key"]
    directory.mkdir(parents=True, exist_ok=True)
    housing_path = directory / "housing.glb"
    output_path = directory / "output.glb"
    housing_glb = export_glb_metres(housing, "housing", housing_path)
    output_glb = export_glb_metres(output, "output", output_path)

    return {
        "key": spec["key"],
        "model": spec["model"],
        "dropbearClass": spec["dropbearClass"],
        "sourceStepSha256": spec["sourceSha256"],
        "sourceUrl": spec["sourceUrl"],
        "sourceRelativePath": source.relative_to(ROOT).as_posix(),
        "sourceSolidCount": len(solids),
        "housingSolidCount": len(housing_shapes),
        "outputSolidCount": len(output_shapes),
        "outputFingerprintSha256": spec["outputFingerprint"],
        "dimensionsMm": dimensions(imported),
        "axis": spec["axis"],
        "axisVector": spec["axisVector"],
        "axisOriginM": [0, 0, 0],
        "explodeDirection": spec["explodeDirection"],
        "explodeDistanceM": spec["explodeDistanceM"],
        "housingUrl": f"/assets/cad/{spec['key']}/housing.glb",
        "outputUrl": f"/assets/cad/{spec['key']}/output.glb",
        "housingTriangles": housing_triangles,
        "outputTriangles": output_triangles,
        "housingBytes": housing_path.stat().st_size,
        "outputBytes": output_path.stat().st_size,
        "housingGlb": housing_glb,
        "outputGlb": output_glb,
        "visualPartitionOnly": True,
        "acceptedDynamicsAuthority": False,
        "note": (
            "Exact source STEP-derived visual partition. Output member selected "
            "by measured B-Rep fingerprint; not a calibrated dynamics/support model."
        ),
        "componentFingerprintsSha256": sorted(component_fingerprints),
    }


def main() -> int:
    records = [export_motor(spec) for spec in MOTORS]
    payload = {
        "schema": "dropbear-motor-cad-v1",
        "generatedFromTrackedSource": True,
        "motors": {record["key"]: record for record in records},
    }
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(MANIFEST_PATH.relative_to(ROOT))
    for record in records:
        print(
            f"{record['model']}: {record['housingTriangles']:,} housing + "
            f"{record['outputTriangles']:,} output triangles; "
            f"axis +{record['axis'].upper()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
