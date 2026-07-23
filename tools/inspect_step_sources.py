#!/usr/bin/env python3
"""Inspect cached MYACTUATOR STEP sources without interpreting geometry.

This is a bounded ISO-10303-21 lexical inventory, not a CAD kernel. It retains
source identity, useful review candidates and explicit limits while refusing
to claim a housing/output split, joint axis, transformed bounding box or
simulation readiness.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "assets" / "myactuator" / "step_manifest.tsv"
VENDOR = ROOT / "assets" / "vendor" / "myactuator"
DEFAULT_OUTPUT = ROOT / "generated" / "myactuator" / "cad" / "step_inspection.json"

SCHEMA_VERSION = "myactuator-step-inspection/1"
MAX_STEP_BYTES = 128 * 1024 * 1024
MAX_STORED_NAMES = 256
MAX_NAME_BYTES = 1024

ENTITY_RE = re.compile(rb"#\s*(\d+)\s*=\s*([A-Z][A-Z0-9_]*)\s*\(", re.I)
ENTITY_START_RE = re.compile(rb"(?m)^\s*#\s*\d+\s*=")
FILE_SCHEMA_RE = re.compile(rb"FILE_SCHEMA\s*\(\s*\((.*?)\)\s*\)", re.I | re.S)
SI_UNIT_RE = re.compile(rb"SI_UNIT\s*\((.*?)\)", re.I | re.S)
PRODUCT_RE = re.compile(
    rb"#\s*(\d+)\s*=\s*PRODUCT\s*\(\s*'((?:''|[^'])*)'(.*?)\)\s*;",
    re.I | re.S,
)
FORMATION_RE = re.compile(
    rb"#\s*(\d+)\s*=\s*PRODUCT_DEFINITION_FORMATION(?:_WITH_SPECIFIED_SOURCE)?"
    rb"\s*\((.*?)\)\s*;",
    re.I | re.S,
)
PRODUCT_DEFINITION_RE = re.compile(
    rb"#\s*(\d+)\s*=\s*PRODUCT_DEFINITION\s*\((.*?)\)\s*;",
    re.I | re.S,
)
ASSEMBLY_RE = re.compile(
    rb"#\s*(\d+)\s*=\s*NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\("
    rb"\s*'((?:''|[^'])*)'(.*?)\)\s*;",
    re.I | re.S,
)
CARTESIAN_POINT_RE = re.compile(
    rb"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(([^)]*)\)\s*\)",
    re.I | re.S,
)
REFERENCE_RE = re.compile(rb"#\s*(\d+)")


class InspectionError(ValueError):
    """A source cannot produce trustworthy static inspection evidence."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def read_manifest(path: Path = MANIFEST) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    required = {
        "series",
        "model",
        "vendor_relative_path",
        "step_sha256",
        "bytes",
        "step_structure",
        "simulation_review",
        "output_member",
        "axis_origin_units_review",
        "redistribution_status",
    }
    if not rows or set(rows[0]) != required:
        raise InspectionError(f"{path}: unexpected manifest columns")
    paths = [row["vendor_relative_path"] for row in rows]
    if len(rows) != 53 or len(paths) != len(set(paths)):
        raise InspectionError("STEP manifest must contain 53 unique source paths")
    return rows


def variant_id(row: dict[str, str]) -> str:
    identity = "\0".join(
        (row["series"], row["model"], row["vendor_relative_path"], row["step_sha256"])
    )
    return "step-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def _decode_name(raw: bytes) -> dict[str, str]:
    raw = raw.replace(b"''", b"'")
    if len(raw) > MAX_NAME_BYTES:
        raw = raw[:MAX_NAME_BYTES]
    raw_latin1 = raw.decode("latin-1")
    if all(byte < 0x80 for byte in raw):
        return {"raw_latin1": raw_latin1, "decoded": raw.decode("ascii"), "encoding": "ascii"}
    for encoding in ("utf-8", "gb18030"):
        try:
            decoded = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if decoded.encode(encoding) == raw:
            return {"raw_latin1": raw_latin1, "decoded": decoded, "encoding": encoding}
    return {"raw_latin1": raw_latin1, "decoded": raw_latin1, "encoding": "latin-1"}


def _quoted_tokens(blob: bytes) -> list[bytes]:
    return [match.replace(b"''", b"'") for match in re.findall(rb"'((?:''|[^'])*)'", blob)]


def _references(blob: bytes) -> list[int]:
    return [int(value) for value in REFERENCE_RE.findall(blob)]


def _unit_inventory(data: bytes) -> tuple[list[dict[str, Any]], str]:
    counter: Counter[str] = Counter()
    for body in SI_UNIT_RE.findall(data):
        normalized = re.sub(rb"\s+", b"", body).upper().decode("ascii", errors="replace")
        counter[normalized] += 1
    units = [{"token": token, "count": counter[token]} for token in sorted(counter)]
    length_tokens = [token for token in counter if ".METRE." in token]
    millimetre = any(".MILLI." in token for token in length_tokens)
    metre = any(token.startswith("$,") for token in length_tokens)
    if millimetre and not metre:
        candidate = "millimetre"
    elif metre and not millimetre:
        candidate = "metre"
    elif metre and millimetre:
        candidate = "ambiguous"
    else:
        candidate = "unknown"
    return units, candidate


def _point_inventory(data: bytes) -> dict[str, Any]:
    total = 0
    parsed = 0
    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    for match in CARTESIAN_POINT_RE.finditer(data):
        total += 1
        fields = [field.strip() for field in match.group(1).split(b",")]
        if len(fields) != 3:
            continue
        try:
            values = [float(field.replace(b"D", b"E").replace(b"d", b"e")) for field in fields]
        except ValueError:
            continue
        if not all(math.isfinite(value) for value in values):
            continue
        parsed += 1
        for index, value in enumerate(values):
            minimum[index] = min(minimum[index], value)
            maximum[index] = max(maximum[index], value)
    return {
        "total": total,
        "parsed": parsed,
        "parse_failures": total - parsed,
        "untransformed_min": minimum if parsed else None,
        "untransformed_max": maximum if parsed else None,
        "authoritative_bounding_box": False,
    }


def _product_inventory(data: bytes) -> tuple[list[dict[str, Any]], dict[int, str]]:
    result: list[dict[str, Any]] = []
    names_by_id: dict[int, str] = {}
    all_name_bytes = hashlib.sha256()
    omitted = 0
    for match in PRODUCT_RE.finditer(data):
        entity_id = int(match.group(1))
        raw_name = match.group(2).replace(b"''", b"'")
        all_name_bytes.update(len(raw_name).to_bytes(4, "big"))
        all_name_bytes.update(raw_name)
        decoded = _decode_name(raw_name)
        names_by_id[entity_id] = decoded["decoded"]
        if len(result) < MAX_STORED_NAMES:
            result.append({"entity_id": entity_id, **decoded})
        else:
            omitted += 1
    result.sort(key=lambda item: item["entity_id"])
    return result, names_by_id | {-1: f"sha256:{all_name_bytes.hexdigest()};omitted:{omitted}"}


def _assembly_inventory(data: bytes, product_names: dict[int, str]) -> list[dict[str, Any]]:
    formations: dict[int, int] = {}
    for match in FORMATION_RE.finditer(data):
        refs = _references(match.group(2))
        if refs:
            formations[int(match.group(1))] = refs[-1]

    definitions: dict[int, int] = {}
    for match in PRODUCT_DEFINITION_RE.finditer(data):
        refs = _references(match.group(2))
        formation = next((ref for ref in refs if ref in formations), None)
        if formation is not None:
            definitions[int(match.group(1))] = formation

    relationships: list[dict[str, Any]] = []
    for match in ASSEMBLY_RE.finditer(data):
        refs = _references(match.group(3))
        relating = refs[-2] if len(refs) >= 2 else None
        related = refs[-1] if len(refs) >= 2 else None

        def product_for(definition: int | None) -> tuple[int | None, str | None]:
            formation = definitions.get(definition) if definition is not None else None
            product = formations.get(formation) if formation is not None else None
            return product, product_names.get(product) if product is not None else None

        relating_product, relating_name = product_for(relating)
        related_product, related_name = product_for(related)
        relationships.append(
            {
                "entity_id": int(match.group(1)),
                "occurrence_name": _decode_name(match.group(2)),
                "relating_definition_id": relating,
                "related_definition_id": related,
                "relating_product_id": relating_product,
                "related_product_id": related_product,
                "relating_product_name": relating_name,
                "related_product_name": related_name,
            }
        )
    relationships.sort(key=lambda item: item["entity_id"])
    return relationships


def inspect_bytes(row: dict[str, str], data: bytes) -> dict[str, Any]:
    expected_bytes = int(row["bytes"])
    if len(data) != expected_bytes:
        raise InspectionError(
            f"{row['vendor_relative_path']}: byte count {len(data)} != {expected_bytes}"
        )
    digest = sha256_bytes(data)
    if digest != row["step_sha256"]:
        raise InspectionError(f"{row['vendor_relative_path']}: SHA-256 mismatch")
    if len(data) > MAX_STEP_BYTES:
        raise InspectionError(f"{row['vendor_relative_path']}: exceeds bounded source size")
    if not data.lstrip().upper().startswith(b"ISO-10303-21;"):
        raise InspectionError(f"{row['vendor_relative_path']}: missing Part 21 header")
    if b"END-ISO-10303-21;" not in data.upper()[-1024:]:
        raise InspectionError(f"{row['vendor_relative_path']}: missing Part 21 trailer")

    type_counts: Counter[str] = Counter(
        match.group(2).decode("ascii").upper() for match in ENTITY_RE.finditer(data)
    )
    histogram_text = "\n".join(
        f"{name}\t{type_counts[name]}" for name in sorted(type_counts)
    ).encode("ascii")
    schema_values = []
    for body in FILE_SCHEMA_RE.findall(data):
        schema_values.extend(token.decode("ascii", errors="replace") for token in _quoted_tokens(body))
    units, unit_candidate = _unit_inventory(data)
    products, product_names = _product_inventory(data)
    name_metadata = product_names.pop(-1)
    assembly = _assembly_inventory(data, product_names)
    detected_structure = "assembly" if assembly else "flattened"
    if detected_structure != row["step_structure"]:
        raise InspectionError(
            f"{row['vendor_relative_path']}: manifest structure {row['step_structure']} "
            f"!= detected {detected_structure}"
        )

    return {
        "variant_id": variant_id(row),
        "series": row["series"],
        "model": row["model"],
        "vendor_relative_path": row["vendor_relative_path"],
        "step_sha256": digest,
        "bytes": len(data),
        "manifest_structure": row["step_structure"],
        "part21_schema": sorted(set(schema_values)),
        "entity_count": len(ENTITY_START_RE.findall(data)),
        "simple_entity_count": sum(type_counts.values()),
        "complex_entity_count": len(ENTITY_START_RE.findall(data)) - sum(type_counts.values()),
        "entity_type_fingerprint_sha256": sha256_bytes(histogram_text),
        "semantic_entity_counts": {
            name: type_counts.get(name, 0)
            for name in (
                "ADVANCED_BREP_SHAPE_REPRESENTATION",
                "CLOSED_SHELL",
                "MANIFOLD_SOLID_BREP",
                "NEXT_ASSEMBLY_USAGE_OCCURRENCE",
                "PRODUCT",
                "SHAPE_REPRESENTATION",
            )
        },
        "length_unit_tokens": units,
        "length_unit_candidate": unit_candidate,
        "length_unit_reviewed": False,
        "products": products,
        "product_name_set_metadata": name_metadata,
        "assembly_relationships": assembly,
        "cartesian_points": _point_inventory(data),
        "static_inspection_only": True,
        "source_transform_applied": False,
        "housing_member_identified": False,
        "output_member_identified": False,
        "joint_axis_identified": False,
        "simulation_supported": False,
    }


def inspect_sources(
    rows: Iterable[dict[str, str]], vendor_root: Path = VENDOR
) -> dict[str, Any]:
    variants: list[dict[str, Any]] = []
    by_digest: dict[str, list[str]] = defaultdict(list)
    model_keys: set[tuple[str, str]] = set()
    total_bytes = 0
    for row in rows:
        path = vendor_root / row["vendor_relative_path"]
        try:
            data = path.read_bytes()
        except OSError as error:
            raise InspectionError(f"cannot read source {path}: {error}") from error
        inspected = inspect_bytes(row, data)
        variants.append(inspected)
        by_digest[row["step_sha256"]].append(inspected["variant_id"])
        model_keys.add((row["series"], row["model"]))
        total_bytes += len(data)

    duplicate_groups = [
        {"step_sha256": digest, "variant_ids": sorted(ids)}
        for digest, ids in sorted(by_digest.items())
        if len(ids) > 1
    ]
    unit_counts = Counter(variant["length_unit_candidate"] for variant in variants)
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "evidence_class": "offline-static",
        "authoritative_geometry_interpretation": False,
        "summary": {
            "models": len(model_keys),
            "variants": len(variants),
            "unique_step_hashes": len(by_digest),
            "duplicate_hash_groups": len(duplicate_groups),
            "assembly_variants": sum(v["manifest_structure"] == "assembly" for v in variants),
            "flattened_variants": sum(v["manifest_structure"] == "flattened" for v in variants),
            "total_step_bytes": total_bytes,
            "length_unit_candidates": dict(sorted(unit_counts.items())),
            "housing_members_identified": 0,
            "output_members_identified": 0,
            "simulation_supported_models": 0,
        },
        "duplicate_geometry_groups": duplicate_groups,
        "variants": variants,
    }


def validate_report_against_manifest(report: dict[str, Any], rows: list[dict[str, str]]) -> None:
    if report.get("schema_version") != SCHEMA_VERSION:
        raise InspectionError("inspection report schema version mismatch")
    expected_manifest_hash = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    if report.get("manifest_sha256") != expected_manifest_hash:
        raise InspectionError("inspection report manifest hash mismatch")
    variants = report.get("variants")
    if not isinstance(variants, list) or len(variants) != len(rows):
        raise InspectionError("inspection report does not cover every STEP variant")
    expected = {
        variant_id(row): (
            row["series"],
            row["model"],
            row["vendor_relative_path"],
            row["step_sha256"],
            int(row["bytes"]),
            row["step_structure"],
        )
        for row in rows
    }
    observed: dict[str, tuple[Any, ...]] = {}
    for item in variants:
        if not isinstance(item, dict):
            raise InspectionError("inspection report variant is not an object")
        key = item.get("variant_id")
        if key in observed:
            raise InspectionError(f"duplicate inspection variant ID: {key}")
        observed[key] = (
            item.get("series"),
            item.get("model"),
            item.get("vendor_relative_path"),
            item.get("step_sha256"),
            item.get("bytes"),
            item.get("manifest_structure"),
        )
        if any(
            item.get(flag) is not False
            for flag in (
                "length_unit_reviewed",
                "source_transform_applied",
                "housing_member_identified",
                "output_member_identified",
                "joint_axis_identified",
                "simulation_supported",
            )
        ):
            raise InspectionError(f"static report promotes geometry authority: {key}")
    if observed != expected:
        raise InspectionError("inspection report identity rows differ from STEP manifest")


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
    mode.add_argument("--write", action="store_true", help="replace the tracked inspection report")
    mode.add_argument("--check", action="store_true", help="require exact generated-report parity")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--require-cache", action="store_true")
    args = parser.parse_args()

    rows = read_manifest()
    cache_present = all((VENDOR / row["vendor_relative_path"]).is_file() for row in rows)
    if args.write or cache_present:
        report = inspect_sources(rows)
        rendered = canonical_json(report)
        if args.write:
            atomic_write(args.output, rendered)
        elif not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise InspectionError("tracked STEP inspection report differs from source cache")
    else:
        if args.require_cache:
            raise InspectionError("complete vendor STEP cache is required")
        if not args.output.is_file():
            raise InspectionError("source cache and tracked STEP inspection report are absent")
        report = json.loads(args.output.read_text(encoding="utf-8"))
        validate_report_against_manifest(report, rows)

    summary = report["summary"]
    print(
        "STEP_INSPECTION_OK "
        f"models={summary['models']} variants={summary['variants']} "
        f"unique={summary['unique_step_hashes']} assemblies={summary['assembly_variants']} "
        f"flattened={summary['flattened_variants']} supported=0 "
        f"({'cache inspected' if cache_present else 'tracked evidence only'})"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (InspectionError, json.JSONDecodeError, OSError, ValueError) as error:
        print(f"STEP inspection failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)

