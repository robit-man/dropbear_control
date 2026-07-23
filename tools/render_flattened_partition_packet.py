#!/usr/bin/env python3
"""Inventory and render local-only candidate partitions for flattened STEP sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import cadquery as cq
from PIL import Image, ImageDraw

from flattened_partition_common import AUTHORITY_FIELDS, PACKET_VERSION, disposition
from render_cad_review_packet import IMAGE_SIZE, font, render


ROOT = Path(__file__).resolve().parents[1]
INSPECTION = ROOT / "generated" / "myactuator" / "cad" / "step_inspection.json"
PROBE = ROOT / "generated" / "myactuator" / "cad" / "geometry_probe.json"
VENDOR = ROOT / "assets" / "vendor" / "myactuator"
OUTPUT_ROOT = ROOT / "generated" / "myactuator" / "cad" / "flattened_review_packets"
MAX_REPRESENTATIVE_VIEWS = 12


class PartitionPacketError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rounded(value: float) -> float:
    if not math.isfinite(value):
        raise PartitionPacketError("non-finite CAD measurement")
    return round(float(value), 6)


def topology(shape: cq.Shape) -> dict[str, int]:
    return {
        "solids": len(shape.Solids()),
        "shells": len(shape.Shells()),
        "faces": len(shape.Faces()),
        "edges": len(shape.Edges()),
        "vertices": len(shape.Vertices()),
    }


def measured_component(shape: cq.Shape, kind: str) -> tuple[str, dict[str, Any]]:
    box = shape.BoundingBox()
    center = shape.Center()
    record = {
        "kind": kind,
        "valid": bool(shape.isValid()),
        "volume_mm3": rounded(shape.Volume()),
        "surface_area_mm2": rounded(shape.Area()),
        "center_mm": [rounded(center.x), rounded(center.y), rounded(center.z)],
        "bbox_min_mm": [rounded(box.xmin), rounded(box.ymin), rounded(box.zmin)],
        "bbox_max_mm": [rounded(box.xmax), rounded(box.ymax), rounded(box.zmax)],
        "bbox_size_mm": [rounded(box.xlen), rounded(box.ylen), rounded(box.zlen)],
        "topology": topology(shape),
    }
    fingerprint = hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()
    return fingerprint, record


def contact_sheet(
    components: list[dict[str, Any]], image_paths: dict[str, Path], output: Path
) -> None:
    columns = 3
    label_height = 94
    rows = math.ceil(len(components) / columns)
    sheet = Image.new("RGB", (columns * IMAGE_SIZE, rows * (IMAGE_SIZE + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    title_font = font(24)
    detail_font = font(17)
    for index, component in enumerate(components):
        column, row = index % columns, index // columns
        x, y = column * IMAGE_SIZE, row * (IMAGE_SIZE + label_height)
        with Image.open(image_paths[component["component_id"]]) as source:
            sheet.paste(source.convert("RGB"), (x, y))
        draw.text(
            (x + 10, y + IMAGE_SIZE + 6),
            f"{component['component_id']}  {component['kind']}",
            fill="black",
            font=title_font,
        )
        size = " x ".join(f"{value:g}" for value in component["bbox_size_mm"])
        draw.text(
            (x + 10, y + IMAGE_SIZE + 44),
            f"bbox mm {size}; volume {component['volume_mm3']:g} mm^3",
            fill=(40, 40, 40),
            font=detail_font,
        )
    sheet.save(output, format="PNG", optimize=True)


def build_packet(variant_id: str, output_root: Path = OUTPUT_ROOT) -> Path:
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    source = next(
        (item for item in inspection["variants"] if item["variant_id"] == variant_id),
        None,
    )
    if source is None:
        raise PartitionPacketError(f"unknown variant ID: {variant_id}")
    if source["manifest_structure"] != "flattened":
        raise PartitionPacketError("flattened partition packet requires a flattened STEP source")
    source_path = VENDOR / source["vendor_relative_path"]
    if not source_path.is_file() or sha256(source_path) != source["step_sha256"]:
        raise PartitionPacketError("exact vendor source is absent or changed")

    imported = cq.importers.importStep(str(source_path)).val()
    solids = list(imported.Solids())
    component_kind = "solid" if solids else "shell"
    shapes = solids if solids else list(imported.Shells())
    if not shapes:
        raise PartitionPacketError("import contains neither solids nor shells")

    measured = []
    for shape in shapes:
        fingerprint, record = measured_component(shape, component_kind)
        measured.append((fingerprint, record, shape))
    measured.sort(
        key=lambda item: (
            item[0],
            item[1]["center_mm"],
            item[1]["bbox_size_mm"],
        )
    )
    components: list[dict[str, Any]] = []
    shape_by_id: dict[str, cq.Shape] = {}
    for ordinal, (fingerprint, record, shape) in enumerate(measured, start=1):
        component_id = f"{component_kind}-{ordinal:04d}-{fingerprint[:12]}"
        record = {"component_id": component_id, "fingerprint_sha256": fingerprint, **record}
        components.append(record)
        shape_by_id[component_id] = shape

    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    probe_record = next(item for item in probe["variants"] if item["variant_id"] == variant_id)
    expected_count = probe_record["topology"]["solids" if solids else "shells"]
    if expected_count != len(components):
        raise PartitionPacketError("partition component count disagrees with import probe")

    ranked = sorted(
        components,
        key=lambda item: (
            item["volume_mm3"],
            item["surface_area_mm2"],
            math.dist(item["bbox_min_mm"], item["bbox_max_mm"]),
            item["component_id"],
        ),
        reverse=True,
    )[:MAX_REPRESENTATIVE_VIEWS]

    directory = output_root / variant_id
    directory.mkdir(parents=True, exist_ok=True)
    overview = directory / "overview.png"
    render([("exact-import", imported)], overview)
    isolated: dict[str, Path] = {}
    for component in ranked:
        component_id = component["component_id"]
        image_path = directory / f"component-{component_id}.png"
        render([(component_id, shape_by_id[component_id])], image_path)
        isolated[component_id] = image_path
    sheet = directory / "largest-component-sheet.png"
    contact_sheet(ranked, isolated, sheet)

    packet = {
        "schema_version": PACKET_VERSION,
        "variant_id": variant_id,
        "series": source["series"],
        "model": source["model"],
        "vendor_relative_path": source["vendor_relative_path"],
        "step_sha256": source["step_sha256"],
        "review_status": "candidate_partition_only",
        "component_kind": component_kind,
        "component_count": len(components),
        "partition_disposition": disposition(component_kind, len(components)),
        "stable_component_ids_are_semantic": False,
        "housing_member_identified": False,
        "output_member_identified": False,
        "joint_axis_identified": False,
        "simulation_supported": False,
        "components": components,
        "representative_component_ids": [item["component_id"] for item in ranked],
        "images": {
            "overview": {"path": overview.relative_to(ROOT).as_posix(), "sha256": sha256(overview)},
            "largest_component_sheet": {"path": sheet.relative_to(ROOT).as_posix(), "sha256": sha256(sheet)},
        },
    }
    packet_path = directory / "packet.json"
    packet_path.write_text(canonical_json(packet), encoding="utf-8")
    return packet_path


def validate_packet(packet_path: Path) -> None:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    if packet.get("schema_version") != PACKET_VERSION:
        raise PartitionPacketError("packet schema mismatch")
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    source = next(
        (item for item in inspection["variants"] if item["variant_id"] == packet.get("variant_id")),
        None,
    )
    if source is None or source["manifest_structure"] != "flattened":
        raise PartitionPacketError("packet does not identify a flattened source")
    if (
        packet.get("series"),
        packet.get("model"),
        packet.get("vendor_relative_path"),
        packet.get("step_sha256"),
    ) != (
        source["series"],
        source["model"],
        source["vendor_relative_path"],
        source["step_sha256"],
    ):
        raise PartitionPacketError("packet source identity mismatch")
    if packet.get("review_status") != "candidate_partition_only":
        raise PartitionPacketError("packet review status promoted")
    for field in AUTHORITY_FIELDS:
        if packet.get(field) is not False:
            raise PartitionPacketError("candidate partition promotes semantic authority")
    components = packet.get("components", [])
    if packet.get("component_count") != len(components) or len(
        {item["component_id"] for item in components}
    ) != len(components):
        raise PartitionPacketError("component coverage/identity mismatch")
    for image in packet["images"].values():
        image_path = ROOT / image["path"]
        if not image_path.is_file() or sha256(image_path) != image["sha256"]:
            raise PartitionPacketError("packet image is absent or changed")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--variant-id")
    mode.add_argument("--all-flattened", action="store_true")
    mode.add_argument("--validate", type=Path)
    args = parser.parse_args()
    if args.validate is not None:
        validate_packet(args.validate)
        packet_path = args.validate
    elif args.all_flattened:
        inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
        variant_ids = [
            item["variant_id"]
            for item in inspection["variants"]
            if item["manifest_structure"] == "flattened"
        ]
        for variant_id in variant_ids:
            validate_packet(build_packet(variant_id))
        print(f"FLATTENED_PARTITION_PACKETS_OK variants={len(variant_ids)} supported=0")
        return 0
    else:
        packet_path = build_packet(args.variant_id)
        validate_packet(packet_path)
    print(f"FLATTENED_PARTITION_PACKET_OK {packet_path.relative_to(ROOT)} supported=0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, PartitionPacketError, ValueError) as error:
        print(f"flattened partition packet failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
