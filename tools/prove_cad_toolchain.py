#!/usr/bin/env python3
"""Prove the pinned CAD stack on synthetic housing/output articulation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import tempfile
from pathlib import Path
from typing import Any

import cadquery as cq

import check_cad_toolchain


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "tools" / "cad-toolchain-lock.json"
REPORT = ROOT / "generated" / "myactuator" / "cad" / "toolchain_proof.json"
REPORT_VERSION = "myactuator-cad-toolchain-proof/1"
ROTATION_DEGREES = 37.0
LINEAR_DEFLECTION_MM = 0.05
LINEAR_DEFLECTION_M = 0.00005
ANGULAR_DEFLECTION = 0.1


class ProofError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def rounded(value: float) -> float:
    return round(float(value), 9)


def vector(value: cq.Vector) -> list[float]:
    return [rounded(value.x), rounded(value.y), rounded(value.z)]


def build_shapes() -> tuple[cq.Shape, cq.Shape]:
    housing = cq.Workplane("XY").circle(20).circle(12).extrude(12).val()
    output = (
        cq.Workplane("XY")
        .circle(8)
        .extrude(20)
        .union(cq.Workplane("XY").workplane(offset=20).circle(12).extrude(4))
        .union(cq.Workplane("XY").workplane(offset=22).center(10, 0).box(8, 4, 4))
        .val()
    )
    if not housing.isValid() or not output.isValid():
        raise ProofError("synthetic B-Rep is invalid")
    if housing.Volume() <= 0 or output.Volume() <= 0:
        raise ProofError("synthetic B-Rep has no volume")
    return housing, output


def mesh_signature(shape: cq.Shape) -> tuple[list[tuple[float, float, float]], int]:
    vertices, triangles = shape.tessellate(LINEAR_DEFLECTION_MM, ANGULAR_DEFLECTION)
    points = sorted((round(v.x, 9), round(v.y, 9), round(v.z, 9)) for v in vertices)
    return points, len(triangles)


def rotate_points(
    points: list[tuple[float, float, float]], angle_degrees: float
) -> list[tuple[float, float, float]]:
    angle = math.radians(angle_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return sorted(
        (
            round(cosine * x - sine * y, 5),
            round(sine * x + cosine * y, 5),
            round(z, 5),
        )
        for x, y, z in points
    )


def export_step(shape: cq.Shape, path: Path) -> cq.Shape:
    cq.exporters.export(shape, str(path), exportType="STEP", unit="MM", outputUnit="MM")
    if not path.is_file() or path.stat().st_size <= 0:
        raise ProofError(f"STEP export missing: {path.name}")
    imported = cq.importers.importStep(str(path)).val()
    if not imported.isValid():
        raise ProofError(f"STEP round trip invalid: {path.name}")
    return imported


def export_glb_metres(shape_mm: cq.Shape, name: str, path: Path) -> dict[str, Any]:
    shape_m = shape_mm.scale(0.001)
    assembly = cq.Assembly()
    assembly.add(shape_m, name=name)
    assembly.export(
        str(path),
        tolerance=LINEAR_DEFLECTION_M,
        angularTolerance=ANGULAR_DEFLECTION,
    )
    data = path.read_bytes()
    if len(data) < 20:
        raise ProofError(f"GLB export too short: {path.name}")
    magic, version, declared_length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or declared_length != len(data):
        raise ProofError(f"invalid GLB header: {path.name}")
    offset = 12
    document = None
    binary_chunks = 0
    while offset < len(data):
        chunk_length, chunk_type = struct.unpack_from("<I4s", data, offset)
        payload = data[offset + 8 : offset + 8 + chunk_length]
        if len(payload) != chunk_length:
            raise ProofError(f"truncated GLB chunk: {path.name}")
        if chunk_type == b"JSON":
            document = json.loads(payload.decode("utf-8").rstrip(" \x00"))
        elif chunk_type == b"BIN\x00":
            binary_chunks += 1
        offset += 8 + chunk_length
    if document is None or binary_chunks != 1:
        raise ProofError(f"GLB chunks incomplete: {path.name}")
    node_names = {node.get("name") for node in document.get("nodes", [])}
    if name not in node_names or not document.get("meshes"):
        raise ProofError(f"GLB semantic node missing: {path.name}")
    coordinate_values: list[float] = []
    for accessor in document.get("accessors", []):
        if accessor.get("type") != "VEC3":
            continue
        coordinate_values.extend(accessor.get("min", []))
        coordinate_values.extend(accessor.get("max", []))
    if not coordinate_values or not all(math.isfinite(value) for value in coordinate_values):
        raise ProofError(f"GLB coordinate evidence missing: {path.name}")
    absolute_max = max(abs(value) for value in coordinate_values)
    if absolute_max >= 0.1:
        raise ProofError(f"GLB is not scaled to metres: {path.name}")
    return {
        "nodes": len(document["nodes"]),
        "meshes": len(document["meshes"]),
        "coordinate_abs_max_m": rounded(absolute_max),
    }


def relative_error(expected: float, observed: float) -> float:
    return abs(expected - observed) / abs(expected)


def run_proof() -> dict[str, Any]:
    lock, required = check_cad_toolchain.validate_lock()
    check_cad_toolchain.validate_environment(lock, required)
    housing, output_zero = build_shapes()
    output_rotated = output_zero.rotate((0, 0, 0), (0, 0, 1), ROTATION_DEGREES)

    housing_points_before, housing_triangles = mesh_signature(housing)
    housing_points_after, housing_triangles_after = mesh_signature(housing)
    output_points_zero, output_triangles = mesh_signature(output_zero)
    output_points_rotated, output_triangles_rotated = mesh_signature(output_rotated)
    if housing_points_before != housing_points_after or housing_triangles != housing_triangles_after:
        raise ProofError("fixed housing changed during articulation proof")
    if output_triangles != output_triangles_rotated:
        raise ProofError("output tessellation topology changed under rigid rotation")
    observed_rotated = sorted(
        (round(x, 5), round(y, 5), round(z, 5))
        for x, y, z in output_points_rotated
    )
    if rotate_points(output_points_zero, ROTATION_DEGREES) != observed_rotated:
        raise ProofError("output vertices do not follow declared joint rotation")
    if output_points_zero == output_points_rotated:
        raise ProofError("asymmetric output did not move")
    if not math.isclose(output_zero.Volume(), output_rotated.Volume(), rel_tol=1e-12):
        raise ProofError("output volume changed under rigid rotation")

    with tempfile.TemporaryDirectory(prefix="myactuator-cad-proof-") as temporary:
        directory = Path(temporary)
        imported_housing = export_step(housing, directory / "housing.step")
        imported_output = export_step(output_zero, directory / "output.step")
        housing_glb = export_glb_metres(housing, "housing", directory / "housing.glb")
        output_zero_glb = export_glb_metres(output_zero, "output", directory / "output-zero.glb")
        output_rotated_glb = export_glb_metres(
            output_rotated, "output", directory / "output-rotated.glb"
        )
        if hashlib.sha256((directory / "housing.step").read_bytes()).digest() == hashlib.sha256((directory / "output.step").read_bytes()).digest():
            raise ProofError("housing/output STEP exports are identical")
        if hashlib.sha256((directory / "output-zero.glb").read_bytes()).digest() == hashlib.sha256((directory / "output-rotated.glb").read_bytes()).digest():
            raise ProofError("zero/rotated output GLBs are identical")

    housing_error = relative_error(housing.Volume(), imported_housing.Volume())
    output_error = relative_error(output_zero.Volume(), imported_output.Volume())
    if max(housing_error, output_error) > 1e-10:
        raise ProofError("STEP round-trip volume error exceeds tolerance")

    return {
        "schema_version": REPORT_VERSION,
        "toolchain_lock_sha256": hashlib.sha256(LOCK.read_bytes()).hexdigest(),
        "evidence_class": "offline-synthetic-cad",
        "fixture": "synthetic-asymmetric-output-v1",
        "source_is_vendor_geometry": False,
        "motor_model_supported": False,
        "physical_or_plant_evidence": False,
        "articulation": {
            "axis_unit": [0.0, 0.0, 1.0],
            "origin_mm": [0.0, 0.0, 0.0],
            "rotation_degrees": ROTATION_DEGREES,
            "housing_fixed": True,
            "output_vertices_follow_rigid_rotation": True,
            "output_volume_preserved": True,
        },
        "geometry": {
            "housing_volume_mm3": rounded(housing.Volume()),
            "output_volume_mm3": rounded(output_zero.Volume()),
            "output_centroid_zero_mm": vector(output_zero.Center()),
            "output_centroid_rotated_mm": vector(output_rotated.Center()),
            "housing_mesh_vertices": len(housing_points_before),
            "housing_mesh_triangles": housing_triangles,
            "output_mesh_vertices": len(output_points_zero),
            "output_mesh_triangles": output_triangles,
        },
        "step_round_trip": {
            "housing_relative_volume_error": rounded(housing_error),
            "output_relative_volume_error": rounded(output_error),
            "valid_breps": True,
        },
        "glb": {
            "explicit_mm_to_m_scale": 0.001,
            "housing": housing_glb,
            "output_zero": output_zero_glb,
            "output_rotated": output_rotated_glb,
            "valid_glb_2": True,
        },
    }


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = run_proof()
    rendered = canonical_json(report)
    if args.write:
        atomic_write(REPORT, rendered)
    elif args.check:
        if not REPORT.is_file() or REPORT.read_text(encoding="utf-8") != rendered:
            raise ProofError("tracked CAD toolchain proof differs from current result")
    print(
        "CAD_ARTICULATION_PROOF_OK "
        f"fixture={report['fixture']} vertices={report['geometry']['output_mesh_vertices']} "
        "supported_models=0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ProofError, ValueError) as error:
        print(f"CAD articulation proof failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
