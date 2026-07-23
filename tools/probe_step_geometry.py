#!/usr/bin/env python3
"""Probe exact vendor STEP importability with the pinned OpenCascade stack."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INSPECTION = ROOT / "generated" / "myactuator" / "cad" / "step_inspection.json"
VENDOR = ROOT / "assets" / "vendor" / "myactuator"
TOOLCHAIN_LOCK = ROOT / "tools" / "cad-toolchain-lock.json"
REPORT = ROOT / "generated" / "myactuator" / "cad" / "geometry_probe.json"
REPORT_VERSION = "myactuator-step-geometry-probe/1"
WORKER_TIMEOUT_SECONDS = 300


class ProbeError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def rounded(value: float) -> float:
    if not math.isfinite(value):
        raise ProbeError("CAD kernel returned a non-finite measurement")
    return round(float(value), 9)


def worker_probe(path: Path) -> dict[str, Any]:
    import cadquery as cq

    imported = cq.importers.importStep(str(path))
    shape = imported.val()
    bounding_box = shape.BoundingBox()
    solids = shape.Solids()
    shells = shape.Shells()
    faces = shape.Faces()
    result = {
        "shape_type": shape.ShapeType(),
        "valid": bool(shape.isValid()),
        "closed_top_level": bool(shape.Closed()),
        "topology": {
            "compounds": len(shape.Compounds()),
            "compsolids": len(shape.CompSolids()),
            "solids": len(solids),
            "shells": len(shells),
            "faces": len(faces),
            "wires": len(shape.Wires()),
            "edges": len(shape.Edges()),
            "vertices": len(shape.Vertices()),
        },
        "occt_internal_bbox_mm": {
            "min": [rounded(bounding_box.xmin), rounded(bounding_box.ymin), rounded(bounding_box.zmin)],
            "max": [rounded(bounding_box.xmax), rounded(bounding_box.ymax), rounded(bounding_box.zmax)],
            "size": [rounded(bounding_box.xlen), rounded(bounding_box.ylen), rounded(bounding_box.zlen)],
            "diagonal": rounded(bounding_box.DiagonalLength),
        },
        "closed_solid_volume_mm3": rounded(sum(solid.Volume() for solid in solids)),
        "surface_area_mm2": rounded(sum(face.Area() for face in faces)),
        "member_identity_preserved": False,
        "housing_member_identified": False,
        "output_member_identified": False,
        "joint_axis_identified": False,
        "simulation_supported": False,
    }
    result["readiness"] = {
        "step_imported": True,
        "valid_topology": result["valid"],
        "visual_tessellation_candidate": result["valid"] and result["topology"]["faces"] > 0,
        "closed_solid_collision_candidate": result["valid"] and result["topology"]["solids"] > 0,
        "requires_healing_or_solidification": result["topology"]["solids"] == 0,
        "requires_semantic_member_review": True,
    }
    return result


def _probe_subprocess(path: Path) -> dict[str, Any]:
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", str(path)]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=WORKER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise ProbeError(f"STEP import timeout: {path}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ProbeError(f"STEP import failed: {path}: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ProbeError(f"STEP worker returned invalid JSON: {path}") from error


def build_report() -> dict[str, Any]:
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    if inspection.get("schema_version") != "myactuator-step-inspection/1":
        raise ProbeError("inspection schema mismatch")
    by_hash: dict[str, dict[str, Any]] = {}
    first_variant: dict[str, str] = {}
    variants: list[dict[str, Any]] = []
    for inspected in inspection["variants"]:
        digest = inspected["step_sha256"]
        path = VENDOR / inspected["vendor_relative_path"]
        if not path.is_file():
            raise ProbeError(f"vendor STEP source missing: {path}")
        if path.stat().st_size != inspected["bytes"]:
            raise ProbeError(f"vendor STEP byte count changed: {path}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ProbeError(f"vendor STEP hash changed: {path}")
        if digest not in by_hash:
            by_hash[digest] = _probe_subprocess(path)
            first_variant[digest] = inspected["variant_id"]
        probe = json.loads(json.dumps(by_hash[digest]))
        variants.append(
            {
                "variant_id": inspected["variant_id"],
                "series": inspected["series"],
                "model": inspected["model"],
                "vendor_relative_path": inspected["vendor_relative_path"],
                "step_sha256": digest,
                "bytes": inspected["bytes"],
                "manifest_structure": inspected["manifest_structure"],
                "length_unit_candidate": inspected["length_unit_candidate"],
                "geometry_reused_from_variant_id": (
                    None if first_variant[digest] == inspected["variant_id"] else first_variant[digest]
                ),
                **probe,
            }
        )

    readiness_counts = Counter(
        "closed_solids" if item["topology"]["solids"] > 0 else "no_closed_solids"
        for item in variants
    )
    return {
        "schema_version": REPORT_VERSION,
        "inspection_report_sha256": hashlib.sha256(INSPECTION.read_bytes()).hexdigest(),
        "toolchain_lock_sha256": hashlib.sha256(TOOLCHAIN_LOCK.read_bytes()).hexdigest(),
        "evidence_class": "offline-cad-import",
        "source_geometry_interpreted_semantically": False,
        "summary": {
            "models": len({(item["series"], item["model"]) for item in variants}),
            "variants": len(variants),
            "unique_geometries_probed": len(by_hash),
            "imports_succeeded": sum(item["readiness"]["step_imported"] for item in variants),
            "valid_topologies": sum(item["valid"] for item in variants),
            "closed_solid_variants": readiness_counts["closed_solids"],
            "no_closed_solid_variants": readiness_counts["no_closed_solids"],
            "visual_tessellation_candidates": sum(
                item["readiness"]["visual_tessellation_candidate"] for item in variants
            ),
            "supported_models": 0,
        },
        "variants": variants,
    }


def validate_report_identity(report: dict[str, Any]) -> None:
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    if report.get("schema_version") != REPORT_VERSION:
        raise ProbeError("geometry probe schema mismatch")
    if report.get("inspection_report_sha256") != hashlib.sha256(INSPECTION.read_bytes()).hexdigest():
        raise ProbeError("geometry probe inspection hash mismatch")
    if report.get("toolchain_lock_sha256") != hashlib.sha256(TOOLCHAIN_LOCK.read_bytes()).hexdigest():
        raise ProbeError("geometry probe toolchain hash mismatch")
    expected = {
        item["variant_id"]: (
            item["series"], item["model"], item["vendor_relative_path"],
            item["step_sha256"], item["bytes"], item["manifest_structure"],
        )
        for item in inspection["variants"]
    }
    observed = {
        item["variant_id"]: (
            item["series"], item["model"], item["vendor_relative_path"],
            item["step_sha256"], item["bytes"], item["manifest_structure"],
        )
        for item in report.get("variants", [])
    }
    if observed != expected or len(observed) != 53:
        raise ProbeError("geometry probe does not exactly join the inspection report")
    for item in report["variants"]:
        if any(
            item.get(field) is not False
            for field in (
                "member_identity_preserved",
                "housing_member_identified",
                "output_member_identified",
                "joint_axis_identified",
                "simulation_supported",
            )
        ):
            raise ProbeError(f"geometry probe promotes semantic authority: {item['variant_id']}")


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
    mode.add_argument("--validate-only", action="store_true")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker is not None:
        print(json.dumps(worker_probe(args.worker), separators=(",", ":"), sort_keys=True))
        return 0
    if args.validate_only:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        validate_report_identity(report)
    else:
        report = build_report()
        validate_report_identity(report)
        rendered = canonical_json(report)
        if args.write:
            atomic_write(REPORT, rendered)
        elif args.check:
            if not REPORT.is_file() or REPORT.read_text(encoding="utf-8") != rendered:
                raise ProbeError("tracked geometry probe differs from current imports")
    summary = report["summary"]
    print(
        "STEP_GEOMETRY_PROBE_OK "
        f"variants={summary['variants']} unique={summary['unique_geometries_probed']} "
        f"valid={summary['valid_topologies']} closed_solids={summary['closed_solid_variants']} "
        "supported=0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ProbeError, ValueError) as error:
        print(f"STEP geometry probe failed: {error}", file=sys.stderr)
        raise SystemExit(1)

