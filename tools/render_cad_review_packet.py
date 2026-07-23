#!/usr/bin/env python3
"""Render local-only visual review packets for exact assembly STEP variants."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import cadquery as cq
import vtk
from PIL import Image, ImageDraw, ImageFont

from cad_review_packet_common import AUTHORITY_FIELDS, PACKET_VERSION, candidate_score


ROOT = Path(__file__).resolve().parents[1]
INSPECTION = ROOT / "generated" / "myactuator" / "cad" / "step_inspection.json"
VENDOR = ROOT / "assets" / "vendor" / "myactuator"
OUTPUT_ROOT = ROOT / "generated" / "myactuator" / "cad" / "review_packets"
LINEAR_DEFLECTION_MM = 0.08
ANGULAR_DEFLECTION = 0.12
IMAGE_SIZE = 560

PALETTE = (
    (0.18, 0.52, 0.80),
    (0.93, 0.45, 0.16),
    (0.27, 0.68, 0.40),
    (0.62, 0.38, 0.78),
    (0.85, 0.68, 0.12),
    (0.18, 0.70, 0.72),
    (0.82, 0.32, 0.46),
    (0.45, 0.53, 0.60),
)


class PacketError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rounded(value: float) -> float:
    if not math.isfinite(value):
        raise PacketError("non-finite CAD measurement")
    return round(float(value), 6)


def vtk_actor(shape: cq.Shape, color: tuple[float, float, float], opacity: float = 1.0):
    vertices, triangles = shape.tessellate(LINEAR_DEFLECTION_MM, ANGULAR_DEFLECTION)
    points = vtk.vtkPoints()
    points.SetNumberOfPoints(len(vertices))
    for index, vertex in enumerate(vertices):
        points.SetPoint(index, vertex.x, vertex.y, vertex.z)
    cells = vtk.vtkCellArray()
    for triangle in triangles:
        cell = vtk.vtkTriangle()
        for index, vertex_index in enumerate(triangle):
            cell.GetPointIds().SetId(index, vertex_index)
        cells.InsertNextCell(cell)
    polydata = vtk.vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetPolys(cells)
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(polydata)
    normals.ConsistencyOn()
    normals.AutoOrientNormalsOn()
    normals.SplittingOff()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(normals.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(*color)
    actor.GetProperty().SetOpacity(opacity)
    actor.GetProperty().SetInterpolationToPhong()
    return actor


def render(
    shapes: list[tuple[str, cq.Shape]],
    path: Path,
    selected: str | None = None,
    isolate: bool = False,
) -> None:
    renderer = vtk.vtkRenderer()
    renderer.SetBackground(0.96, 0.97, 0.98)
    for index, (name, shape) in enumerate(shapes):
        if isolate and name != selected:
            continue
        if selected is not None:
            color = (0.88, 0.16, 0.12) if name == selected else (0.72, 0.75, 0.78)
            opacity = 1.0 if name == selected else 0.18
        else:
            color = PALETTE[index % len(PALETTE)]
            opacity = 1.0
        renderer.AddActor(vtk_actor(shape, color, opacity))
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetMultiSamples(0)
    window.SetSize(IMAGE_SIZE, IMAGE_SIZE)
    window.AddRenderer(renderer)
    renderer.ResetCamera()
    camera = renderer.GetActiveCamera()
    camera.Azimuth(38)
    camera.Elevation(24)
    camera.OrthogonalizeViewUp()
    camera.ParallelProjectionOn()
    renderer.ResetCameraClippingRange()
    window.Render()
    capture = vtk.vtkWindowToImageFilter()
    capture.SetInput(window)
    capture.SetInputBufferTypeToRGB()
    capture.ReadFrontBufferOff()
    capture.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(path))
    writer.SetInputConnection(capture.GetOutputPort())
    writer.Write()
    window.Finalize()


def font(size: int):
    path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def contact_sheet(
    members: list[dict[str, Any]],
    image_paths: dict[str, Path],
    output: Path,
) -> None:
    columns = 3
    cell_width = IMAGE_SIZE
    label_height = 92
    rows = math.ceil(len(members) / columns)
    sheet = Image.new("RGB", (columns * cell_width, rows * (IMAGE_SIZE + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    title_font = font(24)
    detail_font = font(18)
    for index, member in enumerate(members):
        column = index % columns
        row = index // columns
        x = column * cell_width
        y = row * (IMAGE_SIZE + label_height)
        with Image.open(image_paths[member["occurrence"]]) as source:
            sheet.paste(source.convert("RGB"), (x, y))
        score = member["output_candidate_score"]
        occurrence_label = member["occurrence"]
        same_product = member.get("same_product_occurrences", [occurrence_label])
        if len(same_product) > 1:
            occurrence_label += f" (+{len(same_product) - 1} same-product occurrences)"
        draw.text((x + 10, y + IMAGE_SIZE + 6), f"{occurrence_label}  output score {score:+d}", fill="black", font=title_font)
        label = member["related_product_name"] or "<unresolved product name>"
        if len(label) > 58:
            label = label[:55] + "..."
        draw.text((x + 10, y + IMAGE_SIZE + 42), label, fill=(40, 40, 40), font=detail_font)
    sheet.save(output, format="PNG", optimize=True)


def build_packet(variant_id: str, output_root: Path = OUTPUT_ROOT) -> Path:
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    try:
        source = next(item for item in inspection["variants"] if item["variant_id"] == variant_id)
    except StopIteration as error:
        raise PacketError(f"unknown variant ID: {variant_id}") from error
    if source["manifest_structure"] != "assembly":
        raise PacketError("assembly review packet requires an assembly STEP source")
    path = VENDOR / source["vendor_relative_path"]
    if not path.is_file() or sha256(path) != source["step_sha256"]:
        raise PacketError("exact vendor source is absent or changed")

    assembly = cq.Assembly.load(str(path))
    relationships = {
        item["occurrence_name"]["decoded"]: item for item in source["assembly_relationships"]
    }
    children_by_occurrence: dict[str, tuple[str, Any]] = {}
    unmatched_kernel_shapes: list[str] = []
    for kernel_name, child in assembly.objects.items():
        if child.obj is None:
            continue
        occurrence = kernel_name.rsplit("/", 1)[-1]
        if occurrence not in relationships:
            unmatched_kernel_shapes.append(kernel_name)
        elif occurrence in children_by_occurrence:
            raise PacketError(f"duplicate kernel leaf occurrence: {occurrence}")
        else:
            children_by_occurrence[occurrence] = (kernel_name, child)
    if unmatched_kernel_shapes:
        raise PacketError(f"kernel shapes lack STEP relationship identity: {unmatched_kernel_shapes}")

    directory = output_root / variant_id
    directory.mkdir(parents=True, exist_ok=True)
    shapes: list[tuple[str, cq.Shape]] = []
    members: list[dict[str, Any]] = []
    for occurrence in sorted(relationships, key=lambda value: int(value.removeprefix("NAUO"))):
        relationship = relationships[occurrence]
        product_name = relationship["related_product_name"]
        score, terms = candidate_score(product_name)
        member = {
            "occurrence": occurrence,
            "product_entity_ref": f"#{relationship['related_product_id']}",
            "related_product_name": product_name,
            "output_candidate_score": score,
            "candidate_terms": terms,
        }
        kernel_child = children_by_occurrence.get(occurrence)
        if kernel_child is None:
            member.update(
                {
                    "member_kind": "assembly_group_without_direct_shape",
                    "kernel_object_name": None,
                    "visual_available": False,
                    "shape_type": None,
                    "valid": None,
                    "volume_mm3": None,
                    "center_mm": None,
                    "bbox_size_mm": None,
                }
            )
        else:
            kernel_name, child = kernel_child
            shape = child.obj.located(child.loc)
            bounding_box = shape.BoundingBox()
            member.update(
                {
                    "member_kind": "shape_occurrence",
                    "kernel_object_name": kernel_name,
                    "visual_available": True,
                    "shape_type": shape.ShapeType(),
                    "valid": bool(shape.isValid()),
                    "volume_mm3": rounded(shape.Volume()),
                    "center_mm": [rounded(shape.Center().x), rounded(shape.Center().y), rounded(shape.Center().z)],
                    "bbox_size_mm": [rounded(bounding_box.xlen), rounded(bounding_box.ylen), rounded(bounding_box.zlen)],
                }
            )
            shapes.append((occurrence, shape))
        members.append(member)

    occurrences_by_product: dict[str, list[str]] = {}
    for member in members:
        occurrences_by_product.setdefault(member["product_entity_ref"], []).append(
            member["occurrence"]
        )
    for member in members:
        member["same_product_occurrences"] = occurrences_by_product[
            member["product_entity_ref"]
        ]
    representative_members: list[dict[str, Any]] = []
    seen_products: set[str] = set()
    for member in members:
        if member["product_entity_ref"] in seen_products:
            continue
        if not member["visual_available"]:
            continue
        seen_products.add(member["product_entity_ref"])
        representative_members.append(member)

    overview = directory / "overview.png"
    render(shapes, overview)
    isolated: dict[str, Path] = {}
    for member in representative_members:
        occurrence = member["occurrence"]
        image_path = directory / f"member-{occurrence}.png"
        render(shapes, image_path, selected=occurrence, isolate=True)
        isolated[occurrence] = image_path
    sheet = directory / "member-sheet.png"
    contact_sheet(representative_members, isolated, sheet)

    packet = {
        "schema_version": PACKET_VERSION,
        "variant_id": variant_id,
        "series": source["series"],
        "model": source["model"],
        "vendor_relative_path": source["vendor_relative_path"],
        "step_sha256": source["step_sha256"],
        "tool": {
            "cadquery": cq.__version__,
            "linear_deflection_mm": LINEAR_DEFLECTION_MM,
            "angular_deflection_radians": ANGULAR_DEFLECTION,
            "camera": "orthographic isometric candidate-review view",
        },
        "review_status": "candidate_visuals_only",
        "heuristic_selects_output": False,
        "housing_member_identified": False,
        "output_member_identified": False,
        "joint_axis_identified": False,
        "simulation_supported": False,
        "members": members,
        "unrendered_relationship_occurrences": [
            member["occurrence"] for member in members if not member["visual_available"]
        ],
        "representative_product_views": len(representative_members),
        "images": {
            "overview": {"path": overview.relative_to(ROOT).as_posix(), "sha256": sha256(overview)},
            "member_sheet": {"path": sheet.relative_to(ROOT).as_posix(), "sha256": sha256(sheet)},
        },
    }
    packet_path = directory / "packet.json"
    packet_path.write_text(canonical_json(packet), encoding="utf-8")
    return packet_path


def validate_packet(packet_path: Path) -> None:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    if packet.get("schema_version") != PACKET_VERSION:
        raise PacketError("packet schema mismatch")
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    source = next(
        (item for item in inspection["variants"] if item["variant_id"] == packet["variant_id"]),
        None,
    )
    if source is None or (
        packet["series"], packet["model"], packet["vendor_relative_path"], packet["step_sha256"]
    ) != (
        source["series"], source["model"], source["vendor_relative_path"], source["step_sha256"]
    ):
        raise PacketError("packet source identity mismatch")
    expected_occurrences = {
        item["occurrence_name"]["decoded"] for item in source["assembly_relationships"]
    }
    if (
        len(packet["members"]) != len(source["assembly_relationships"])
        or {item["occurrence"] for item in packet["members"]} != expected_occurrences
    ):
        raise PacketError("packet member coverage mismatch")
    if any(
        packet.get(field) is not False
        for field in AUTHORITY_FIELDS
    ):
        raise PacketError("candidate packet promotes semantic authority")
    for image in packet["images"].values():
        path = ROOT / image["path"]
        if not path.is_file() or sha256(path) != image["sha256"]:
            raise PacketError("packet image is absent or changed")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--variant-id")
    mode.add_argument("--all-assemblies", action="store_true")
    mode.add_argument("--validate", type=Path)
    args = parser.parse_args()
    if args.validate is not None:
        validate_packet(args.validate)
        packet_path = args.validate
    elif args.all_assemblies:
        inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
        assembly_ids = [
            item["variant_id"]
            for item in inspection["variants"]
            if item["manifest_structure"] == "assembly"
        ]
        for variant_id in assembly_ids:
            validate_packet(build_packet(variant_id))
        print(f"CAD_REVIEW_PACKETS_OK variants={len(assembly_ids)} supported=0")
        return 0
    else:
        packet_path = build_packet(args.variant_id)
        validate_packet(packet_path)
    print(f"CAD_REVIEW_PACKET_OK {packet_path.relative_to(ROOT)} supported=0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, PacketError, ValueError) as error:
        print(f"CAD review packet failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
