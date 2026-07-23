#!/usr/bin/env python3
"""Export and articulate an explicitly non-authoritative CAD segmentation hypothesis."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import cadquery as cq
from OCP.gp import gp_Trsf

import check_cad_toolchain
import prove_cad_toolchain as proof
from render_cad_review_packet import render


ROOT = Path(__file__).resolve().parents[1]
INSPECTION = ROOT / "generated" / "myactuator" / "cad" / "step_inspection.json"
VENDOR = ROOT / "assets" / "vendor" / "myactuator"
TOOLCHAIN_LOCK = ROOT / "tools" / "cad-toolchain-lock.json"
OUTPUT_ROOT = ROOT / "generated" / "myactuator" / "cad" / "candidate_exports"
REPORT_ROOT = ROOT / "generated" / "myactuator" / "cad" / "candidate_export_reports"
REPORT_VERSION = "myactuator-cad-candidate-export/1"
POSE_DEGREES = (-30.0, 0.0, 30.0)
ARTICULATION_ROUND_DECIMALS = 3
ARTICULATION_TOLERANCE_MM = 0.002


class CandidateExportError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateExportError(message)


def norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def rotate_points_z(
    points: list[tuple[float, float, float]], angle_degrees: float
) -> list[tuple[float, float, float]]:
    angle = math.radians(angle_degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    return sorted(
        (
            round(cosine * x - sine * y, ARTICULATION_ROUND_DECIMALS),
            round(sine * x + cosine * y, ARTICULATION_ROUND_DECIMALS),
            round(z, ARTICULATION_ROUND_DECIMALS),
        )
        for x, y, z in points
    )


def symmetric_vertex_error_mm(
    expected: list[tuple[float, float, float]],
    observed: list[tuple[float, float, float]],
) -> float:
    require(len(expected) == len(observed), "articulation vertex count changed")
    expected_set, observed_set = set(expected), set(observed)
    missing_expected = expected_set - observed_set
    missing_observed = observed_set - expected_set
    require(
        len(expected_set) == len(observed_set),
        "articulation unique-vertex count changed",
    )
    if not missing_expected:
        return 0.0
    require(bool(missing_observed), "asymmetric articulation vertex difference")
    distances = [
        min(math.dist(point, candidate) for candidate in missing_observed)
        for point in missing_expected
    ] + [
        min(math.dist(point, candidate) for candidate in missing_expected)
        for point in missing_observed
    ]
    return max(distances)


def apply_point(matrix: list[float], point: list[float], w: float) -> list[float]:
    return [
        sum(matrix[row * 4 + column] * (*point, w)[column] for column in range(4))
        for row in range(3)
    ]


def validate_hypothesis(
    hypothesis: dict[str, Any], source: dict[str, Any]
) -> tuple[list[str], list[str]]:
    require(
        hypothesis.get("schema_version") == "myactuator-cad-segmentation-hypothesis/1",
        "hypothesis schema mismatch",
    )
    require(
        hypothesis.get("variant_id") == source["variant_id"]
        and hypothesis.get("step_sha256") == source["step_sha256"],
        "hypothesis source identity mismatch",
    )
    require(source["manifest_structure"] == "assembly", "candidate pilot requires assembly source")
    require(
        hypothesis.get("evidence_class") == "automated-and-visual-candidate-not-reviewed"
        and hypothesis.get("semantic_review_complete") is False
        and hypothesis.get("support_granted") is False,
        "hypothesis promotes semantic/support authority",
    )
    housing = hypothesis.get("housing_occurrences", [])
    output = hypothesis.get("output_occurrences", [])
    expected = {
        item["occurrence_name"]["decoded"] for item in source["assembly_relationships"]
    }
    require(housing and output, "candidate requires nonempty housing/output groups")
    require(not set(housing) & set(output), "candidate groups overlap")
    require(set(housing) | set(output) == expected, "candidate groups do not cover every STEP relationship")
    require(len(housing) == len(set(housing)) and len(output) == len(set(output)), "duplicate occurrence")

    axis = hypothesis.get("source_axis_unit", [])
    origin = hypothesis.get("origin_source_mm", [])
    matrix = hypothesis.get("source_to_canonical", [])
    require(len(axis) == len(origin) == 3 and len(matrix) == 16, "candidate frame shape invalid")
    require(all(math.isfinite(value) for value in [*axis, *origin, *matrix]), "non-finite frame")
    require(math.isclose(norm(axis), 1.0, abs_tol=1e-9), "source axis is not unit length")
    require(matrix[12:16] == [0.0, 0.0, 0.0, 1.0], "candidate transform is not affine")
    rotation_rows = [matrix[0:3], matrix[4:7], matrix[8:11]]
    for row in rotation_rows:
        require(math.isclose(norm(row), 1.0, abs_tol=1e-9), "transform row is not unit length")
    for first in range(3):
        for second in range(first + 1, 3):
            require(
                math.isclose(
                    sum(rotation_rows[first][i] * rotation_rows[second][i] for i in range(3)),
                    0.0,
                    abs_tol=1e-9,
                ),
                "transform rotation is not orthogonal",
            )
    mapped_axis = apply_point(matrix, axis, 0.0)
    mapped_origin = apply_point(matrix, origin, 1.0)
    require(
        all(math.isclose(value, expected, abs_tol=1e-9) for value, expected in zip(mapped_axis, [0.0, 0.0, 1.0])),
        "source axis does not map to canonical +Z",
    )
    require(all(math.isclose(value, 0.0, abs_tol=1e-9) for value in mapped_origin), "source origin does not map to zero")
    require(len(hypothesis.get("evidence_refs", [])) >= 2, "candidate evidence refs missing")
    require(bool(hypothesis.get("rationale")), "candidate rationale missing")
    require(bool(hypothesis.get("unresolved_questions")), "candidate must retain unresolved questions")
    return housing, output


def canonical_shape(shape: cq.Shape, matrix: list[float]) -> cq.Shape:
    transform = gp_Trsf()
    transform.SetValues(*matrix[0:4], *matrix[4:8], *matrix[8:12])
    transformed = shape.moved(cq.Location(transform))
    require(transformed.isValid(), "canonical transform produced invalid B-Rep")
    return transformed


def export_step_link(
    shapes: list[tuple[str, cq.Shape]], name: str, path: Path
) -> tuple[float, int]:
    assembly = cq.Assembly(name=name)
    for occurrence, shape in shapes:
        assembly.add(shape, name=occurrence)
    assembly.export(str(path), exportType="STEP", mode="default", unit="MM", outputUnit="MM")
    require(path.is_file() and path.stat().st_size > 0, f"STEP export missing: {path.name}")
    reloaded = cq.Assembly.load(str(path))
    leaves = [child for child in reloaded.objects.values() if child.obj is not None]
    require(len(leaves) == len(shapes), f"STEP leaf count changed: {path.name}")
    require(all(child.obj.isValid() for child in leaves), f"STEP leaf B-Rep invalid: {path.name}")
    expected_volume = sum(shape.Volume() for _, shape in shapes)
    observed_volume = sum(child.obj.Volume() for child in leaves)
    return proof.relative_error(expected_volume, observed_volume), len(leaves)


def build_report(hypothesis_path: Path) -> dict[str, Any]:
    lock, required = check_cad_toolchain.validate_lock()
    check_cad_toolchain.validate_environment(lock, required)
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    source = next(
        (item for item in inspection["variants"] if item["variant_id"] == hypothesis.get("variant_id")),
        None,
    )
    require(source is not None, "hypothesis references unknown source")
    housing_refs, output_refs = validate_hypothesis(hypothesis, source)
    source_path = VENDOR / source["vendor_relative_path"]
    require(source_path.is_file() and sha256(source_path) == source["step_sha256"], "vendor source absent or changed")

    assembly = cq.Assembly.load(str(source_path))
    shapes_by_occurrence: dict[str, cq.Shape] = {}
    for kernel_name, child in assembly.objects.items():
        if child.obj is None:
            continue
        occurrence = kernel_name.rsplit("/", 1)[-1]
        if occurrence in set(housing_refs) | set(output_refs):
            require(occurrence not in shapes_by_occurrence, "duplicate kernel occurrence")
            shapes_by_occurrence[occurrence] = child.obj.located(child.loc)
    require(set(shapes_by_occurrence) == set(housing_refs) | set(output_refs), "selected assembly group lacks direct shape")

    matrix = hypothesis["source_to_canonical"]
    canonical_shapes = {
        occurrence: canonical_shape(shape, matrix)
        for occurrence, shape in shapes_by_occurrence.items()
    }
    housing_shapes = [(value, canonical_shapes[value]) for value in housing_refs]
    output_shapes = [(value, canonical_shapes[value]) for value in output_refs]
    housing = cq.Compound.makeCompound([shape for _, shape in housing_shapes])
    output_zero = cq.Compound.makeCompound([shape for _, shape in output_shapes])
    require(housing.Volume() > 0.0 and output_zero.Volume() > 0.0, "candidate links have no volume")

    directory = OUTPUT_ROOT / source["variant_id"]
    directory.mkdir(parents=True, exist_ok=True)
    housing_step = directory / "housing-candidate.step"
    output_step = directory / "output-candidate.step"
    housing_step_error, housing_step_leaves = export_step_link(
        housing_shapes, "housing-candidate", housing_step
    )
    output_step_error, output_step_leaves = export_step_link(
        output_shapes, "output-candidate", output_step
    )
    housing_glb = directory / "housing-candidate.glb"
    output_glb = directory / "output-candidate.glb"
    collision_glb = directory / "collision-zero-candidate.glb"
    housing_glb_metrics = proof.export_glb_metres(housing, "housing-candidate", housing_glb)
    output_glb_metrics = proof.export_glb_metres(output_zero, "output-candidate", output_glb)
    collision_glb_metrics = proof.export_glb_metres(
        cq.Compound.makeCompound([housing, output_zero]),
        "collision-zero-candidate",
        collision_glb,
    )

    housing_points, housing_triangles = proof.mesh_signature(housing)
    output_points, output_triangles = proof.mesh_signature(output_zero)
    pose_records = []
    image_artifacts = []
    for angle in POSE_DEGREES:
        output_pose = output_zero.moved(cq.Location((0, 0, 0), (0, 0, 1), angle))
        pose_points, pose_triangles = proof.mesh_signature(output_pose)
        require(pose_triangles == output_triangles, "output tessellation topology changed")
        expected_points = rotate_points_z(output_points, angle)
        observed_points = sorted(
            (
                round(x, ARTICULATION_ROUND_DECIMALS),
                round(y, ARTICULATION_ROUND_DECIMALS),
                round(z, ARTICULATION_ROUND_DECIMALS),
            )
            for x, y, z in pose_points
        )
        vertex_error = symmetric_vertex_error_mm(expected_points, observed_points)
        require(
            vertex_error <= ARTICULATION_TOLERANCE_MM,
            "output vertices violate declared rotation",
        )
        require(
            math.isclose(output_pose.Volume(), output_zero.Volume(), rel_tol=1e-12),
            "output volume changed during articulation",
        )
        image_path = directory / f"pose-{angle:+.0f}deg.png"
        render([("housing", housing), ("output", output_pose)], image_path, selected="output")
        image_artifacts.append(artifact(image_path))
        pose_records.append(
            {
                "angle_degrees": angle,
                "output_centroid_mm": proof.vector(output_pose.Center()),
                "triangles": pose_triangles,
                "max_vertex_deviation_mm": proof.rounded(vertex_error),
                "rigid_rotation_matches": True,
            }
        )
    require(proof.mesh_signature(housing) == (housing_points, housing_triangles), "housing changed")

    report = {
        "schema_version": REPORT_VERSION,
        "evidence_class": "offline-real-cad-candidate-not-reviewed",
        "hypothesis_path": hypothesis_path.relative_to(ROOT).as_posix(),
        "hypothesis_sha256": sha256(hypothesis_path),
        "inspection_sha256": sha256(INSPECTION),
        "toolchain_lock_sha256": sha256(TOOLCHAIN_LOCK),
        "variant_id": source["variant_id"],
        "series": source["series"],
        "model": source["model"],
        "step_sha256": source["step_sha256"],
        "source_to_canonical": matrix,
        "canonical_joint": {
            "origin_m": [0.0, 0.0, 0.0],
            "axis_unit": [0.0, 0.0, 1.0],
            "positive_direction": "right-hand rotation about canonical +Z; physical motor/encoder sign unresolved",
            "zero_definition": "exact vendor STEP assembly placement under the candidate partition",
        },
        "housing_occurrences": housing_refs,
        "output_occurrences": output_refs,
        "geometry": {
            "housing_volume_mm3": proof.rounded(housing.Volume()),
            "output_volume_mm3": proof.rounded(output_zero.Volume()),
            "housing_triangles": housing_triangles,
            "output_triangles": output_triangles,
            "housing_step_roundtrip_relative_volume_error": proof.rounded(housing_step_error),
            "output_step_roundtrip_relative_volume_error": proof.rounded(output_step_error),
            "housing_step_roundtrip_valid_leaves": housing_step_leaves,
            "output_step_roundtrip_valid_leaves": output_step_leaves,
        },
        "articulation": {
            "housing_fixed": True,
            "output_only_rigid_rotation": True,
            "vertex_comparison_tolerance_mm": ARTICULATION_TOLERANCE_MM,
            "poses": pose_records,
        },
        "artifacts": {
            "housing_step": artifact(housing_step),
            "output_step": artifact(output_step),
            "housing_glb": {**artifact(housing_glb), **housing_glb_metrics},
            "output_glb": {**artifact(output_glb), **output_glb_metrics},
            "collision_glb": {**artifact(collision_glb), **collision_glb_metrics},
            "pose_images": image_artifacts,
        },
        "unresolved_questions": hypothesis["unresolved_questions"],
        "semantic_review_complete": False,
        "accepted_asset": False,
        "support_granted": False,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hypothesis", required=True, type=Path)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    hypothesis_path = args.hypothesis.resolve()
    report = build_report(hypothesis_path)
    if args.write_report:
        REPORT_ROOT.mkdir(parents=True, exist_ok=True)
        report_path = REPORT_ROOT / f"{report['variant_id']}.json"
        report_path.write_text(canonical_json(report), encoding="utf-8")
        rendered_path = report_path.relative_to(ROOT)
    else:
        rendered_path = Path("<not-written>")
    print(
        "CAD_CANDIDATE_EXPORT_OK "
        f"variant={report['variant_id']} poses={len(report['articulation']['poses'])} "
        f"report={rendered_path} accepted=0 supported=0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, CandidateExportError, ValueError) as error:
        print(f"CAD candidate export failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
