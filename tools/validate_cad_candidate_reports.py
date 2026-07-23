#!/usr/bin/env python3
"""Validate tracked real-CAD candidate export reports without promoting support."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
INSPECTION = ROOT / "generated" / "myactuator" / "cad" / "step_inspection.json"
TOOLCHAIN_LOCK = ROOT / "tools" / "cad-toolchain-lock.json"
HYPOTHESES = ROOT / "assets" / "myactuator" / "cad_hypotheses"
REPORTS = ROOT / "generated" / "myactuator" / "cad" / "candidate_export_reports"
SCHEMA = ROOT / "schemas" / "myactuator-cad-segmentation-hypothesis.schema.json"
REPORT_VERSION = "myactuator-cad-candidate-export/1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CandidateReportError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateReportError(message)


def validate_artifact(value: dict[str, Any], prefix: str, check_local: bool) -> None:
    require(set(value) >= {"path", "sha256", "bytes"}, f"{prefix}: artifact fields missing")
    require(SHA256.fullmatch(value["sha256"]) is not None, f"{prefix}: invalid hash")
    require(isinstance(value["bytes"], int) and value["bytes"] > 0, f"{prefix}: invalid size")
    path = ROOT / value["path"]
    require(
        path.is_relative_to(ROOT / "generated/myactuator/cad/candidate_exports"),
        f"{prefix}: artifact escapes candidate export root",
    )
    if check_local:
        require(path.is_file(), f"{prefix}: local artifact missing")
        require(path.stat().st_size == value["bytes"] and sha256(path) == value["sha256"], f"{prefix}: local artifact drift")


def validate_pair(
    hypothesis: dict[str, Any],
    hypothesis_path: Path,
    report: dict[str, Any],
    source: dict[str, Any],
    check_local: bool,
) -> None:
    require(report.get("schema_version") == REPORT_VERSION, "report schema mismatch")
    require(
        report.get("evidence_class") == "offline-real-cad-candidate-not-reviewed",
        "report evidence class promoted",
    )
    require(
        report.get("hypothesis_path") == hypothesis_path.relative_to(ROOT).as_posix()
        and report.get("hypothesis_sha256") == sha256(hypothesis_path),
        "hypothesis provenance drift",
    )
    require(report.get("inspection_sha256") == sha256(INSPECTION), "inspection provenance drift")
    require(report.get("toolchain_lock_sha256") == sha256(TOOLCHAIN_LOCK), "toolchain provenance drift")
    require(
        (report.get("variant_id"), report.get("series"), report.get("model"), report.get("step_sha256"))
        == (source["variant_id"], source["series"], source["model"], source["step_sha256"]),
        "source identity drift",
    )
    require(
        report.get("housing_occurrences") == hypothesis["housing_occurrences"]
        and report.get("output_occurrences") == hypothesis["output_occurrences"],
        "candidate member grouping drift",
    )
    require(
        report.get("source_to_canonical") == hypothesis["source_to_canonical"],
        "candidate canonical transform drift",
    )
    require(
        report.get("unresolved_questions") == hypothesis["unresolved_questions"],
        "unresolved questions lost",
    )
    require(
        report.get("semantic_review_complete") is False
        and report.get("accepted_asset") is False
        and report.get("support_granted") is False,
        "candidate report promotes acceptance/support",
    )

    joint = report.get("canonical_joint", {})
    require(joint.get("origin_m") == [0.0, 0.0, 0.0], "canonical origin drift")
    require(joint.get("axis_unit") == [0.0, 0.0, 1.0], "canonical axis drift")
    require(bool(joint.get("positive_direction")) and bool(joint.get("zero_definition")), "canonical joint evidence missing")
    geometry = report.get("geometry", {})
    require(geometry.get("housing_volume_mm3", 0) > 0 and geometry.get("output_volume_mm3", 0) > 0, "candidate link volume missing")
    require(geometry.get("housing_triangles", 0) > 0 and geometry.get("output_triangles", 0) > 0, "candidate tessellation missing")
    require(
        geometry.get("housing_step_roundtrip_valid_leaves") == len(hypothesis["housing_occurrences"])
        and geometry.get("output_step_roundtrip_valid_leaves") == len(hypothesis["output_occurrences"]),
        "STEP leaf round-trip coverage drift",
    )
    for field in (
        "housing_step_roundtrip_relative_volume_error",
        "output_step_roundtrip_relative_volume_error",
    ):
        require(
            isinstance(geometry.get(field), (int, float))
            and math.isfinite(geometry[field])
            and geometry[field] <= 1e-9,
            f"{field} exceeds tolerance",
        )

    articulation = report.get("articulation", {})
    require(articulation.get("housing_fixed") is True, "housing immobility not proven")
    require(articulation.get("output_only_rigid_rotation") is True, "output rigid rotation not proven")
    require(
        articulation.get("vertex_comparison_tolerance_mm", math.inf) <= 0.002,
        "articulation tolerance too loose",
    )
    poses = articulation.get("poses", [])
    require([pose.get("angle_degrees") for pose in poses] == [-30.0, 0.0, 30.0], "pose coverage drift")
    require(all(pose.get("rigid_rotation_matches") is True for pose in poses), "pose rotation mismatch")
    require(
        all(
            isinstance(pose.get("max_vertex_deviation_mm"), (int, float))
            and pose["max_vertex_deviation_mm"] <= articulation["vertex_comparison_tolerance_mm"]
            for pose in poses
        ),
        "pose vertex deviation exceeds tolerance",
    )

    artifacts = report.get("artifacts", {})
    for name in ("housing_step", "output_step", "housing_glb", "output_glb", "collision_glb"):
        validate_artifact(artifacts.get(name, {}), name, check_local)
    images = artifacts.get("pose_images", [])
    require(len(images) == 3, "pose image coverage mismatch")
    for index, image in enumerate(images):
        validate_artifact(image, f"pose_images[{index}]", check_local)


def validate_all(check_local: bool = False) -> int:
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    sources = {item["variant_id"]: item for item in inspection["variants"]}
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    hypothesis_paths = sorted(HYPOTHESES.glob("*.json"))
    require(bool(hypothesis_paths), "no CAD candidate hypotheses")
    seen: set[str] = set()
    for hypothesis_path in hypothesis_paths:
        hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
        errors = sorted(validator.iter_errors(hypothesis), key=lambda item: list(item.path))
        require(not errors, f"hypothesis schema validation failed: {errors[0].message if errors else ''}")
        variant_id = hypothesis["variant_id"]
        require(variant_id not in seen and variant_id in sources, "duplicate/unknown hypothesis variant")
        seen.add(variant_id)
        report_path = REPORTS / f"{variant_id}.json"
        require(report_path.is_file(), f"candidate report missing: {variant_id}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        validate_pair(hypothesis, hypothesis_path, report, sources[variant_id], check_local)
    report_ids = {path.stem for path in REPORTS.glob("step-*.json")}
    require(report_ids == seen, "orphan/missing candidate report")
    return len(seen)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-local", action="store_true")
    args = parser.parse_args()
    count = validate_all(args.check_local)
    print(f"CAD_CANDIDATE_REPORTS_OK candidates={count} accepted=0 supported=0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, CandidateReportError, ValueError) as error:
        print(f"CAD candidate report validation failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
