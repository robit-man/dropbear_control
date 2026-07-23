#!/usr/bin/env python3
"""Create/check tracked inventories for local flattened STEP partition packets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from flattened_partition_common import (
    AUTHORITY_FIELDS,
    MANIFEST_VERSION,
    PACKET_VERSION,
    disposition,
)


ROOT = Path(__file__).resolve().parents[1]
INSPECTION = ROOT / "generated" / "myactuator" / "cad" / "step_inspection.json"
PROBE = ROOT / "generated" / "myactuator" / "cad" / "geometry_probe.json"
TOOLCHAIN_LOCK = ROOT / "tools" / "cad-toolchain-lock.json"
PACKET_ROOT = ROOT / "generated" / "myactuator" / "cad" / "flattened_review_packets"
MANIFEST = ROOT / "generated" / "myactuator" / "cad" / "flattened_partition_manifest.json"
TRIAGE = ROOT / "generated" / "myactuator" / "cad" / "flattened_partition_triage.md"
COMPONENT_ID = re.compile(r"^(solid|shell)-[0-9]{4}-[0-9a-f]{12}$")


class ManifestError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestError(message)


def validate_components(components: list[dict[str, Any]], kind: str) -> None:
    for ordinal, component in enumerate(components, start=1):
        require(component.get("kind") == kind, "mixed component kinds")
        require(component.get("valid") is True, "invalid partition topology")
        fingerprint = component.get("fingerprint_sha256", "")
        payload = {
            key: value
            for key, value in component.items()
            if key not in {"component_id", "fingerprint_sha256"}
        }
        expected_fingerprint = hashlib.sha256(
            canonical_json(payload).encode("utf-8")
        ).hexdigest()
        require(fingerprint == expected_fingerprint, "component fingerprint drift")
        require(
            component.get("component_id")
            == f"{kind}-{ordinal:04d}-{fingerprint[:12]}",
            "component stable ID/order drift",
        )


def sources_and_probe() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    sources = sorted(
        (
            source
            for source in inspection["variants"]
            if source["manifest_structure"] == "flattened"
        ),
        key=lambda source: source["variant_id"],
    )
    return sources, {record["variant_id"]: record for record in probe["variants"]}


def packet_record(
    source: dict[str, Any], probe: dict[str, Any], require_images: bool
) -> dict[str, Any]:
    packet_path = PACKET_ROOT / source["variant_id"] / "packet.json"
    require(packet_path.is_file(), f"missing flattened packet: {source['variant_id']}")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    require(packet.get("schema_version") == PACKET_VERSION, "packet schema mismatch")
    require(
        (
            packet.get("variant_id"),
            packet.get("series"),
            packet.get("model"),
            packet.get("vendor_relative_path"),
            packet.get("step_sha256"),
        )
        == (
            source["variant_id"],
            source["series"],
            source["model"],
            source["vendor_relative_path"],
            source["step_sha256"],
        ),
        "packet source identity mismatch",
    )
    require(packet.get("review_status") == "candidate_partition_only", "packet status promoted")
    require(
        all(packet.get(field) is False for field in AUTHORITY_FIELDS),
        "packet grants semantic authority",
    )
    kind = packet.get("component_kind")
    require(kind in {"solid", "shell"}, "invalid component kind")
    expected_count = probe["topology"]["solids" if kind == "solid" else "shells"]
    components = packet.get("components", [])
    require(packet.get("component_count") == len(components) == expected_count, "component count drift")
    ids = [component.get("component_id") for component in components]
    require(len(ids) == len(set(ids)), "duplicate component ID")
    require(all(COMPONENT_ID.fullmatch(value or "") for value in ids), "invalid component ID")
    validate_components(components, kind)
    require(
        packet.get("partition_disposition") == disposition(kind, len(components)),
        "partition disposition drift",
    )
    representative_ids = packet.get("representative_component_ids", [])
    require(len(representative_ids) <= 12, "too many representative components")
    require(set(representative_ids) <= set(ids), "unknown representative component")

    image_hashes: dict[str, str] = {}
    for name in ("overview", "largest_component_sheet"):
        image = packet.get("images", {}).get(name, {})
        image_path = ROOT / image.get("path", "")
        require(bool(image.get("sha256")), "packet image hash missing")
        if require_images:
            require(image_path.is_file(), f"packet image missing: {image_path}")
            require(sha256(image_path) == image["sha256"], f"packet image changed: {image_path}")
        image_hashes[f"{name}_sha256"] = image["sha256"]

    return {
        "variant_id": source["variant_id"],
        "series": source["series"],
        "model": source["model"],
        "vendor_relative_path": source["vendor_relative_path"],
        "step_sha256": source["step_sha256"],
        "packet_json_sha256": sha256(packet_path),
        "component_kind": kind,
        "component_count": len(components),
        "partition_disposition": packet["partition_disposition"],
        "components": components,
        "representative_component_ids": representative_ids,
        **image_hashes,
        "candidate_partition_only": True,
        "support_granted": False,
    }


def build_manifest() -> dict[str, Any]:
    sources, probes = sources_and_probe()
    records = [
        packet_record(source, probes[source["variant_id"]], require_images=True)
        for source in sources
    ]
    dispositions = Counter(record["partition_disposition"] for record in records)
    return {
        "schema_version": MANIFEST_VERSION,
        "inspection_sha256": sha256(INSPECTION),
        "geometry_probe_sha256": sha256(PROBE),
        "toolchain_lock_sha256": sha256(TOOLCHAIN_LOCK),
        "scope": "stable topology inventory and local candidate visuals only; no semantic partition or simulation support authority",
        "flattened_variant_count": len(records),
        "component_count": sum(record["component_count"] for record in records),
        "shell_only_variant_count": sum(record["component_kind"] == "shell" for record in records),
        "support_granted_count": 0,
        "disposition_counts": dict(sorted(dispositions.items())),
        "packets": records,
    }


def validate_manifest(manifest: dict[str, Any], check_local: bool) -> None:
    sources, probes = sources_and_probe()
    require(manifest.get("schema_version") == MANIFEST_VERSION, "manifest schema mismatch")
    require(manifest.get("inspection_sha256") == sha256(INSPECTION), "inspection drift")
    require(manifest.get("geometry_probe_sha256") == sha256(PROBE), "probe drift")
    require(manifest.get("toolchain_lock_sha256") == sha256(TOOLCHAIN_LOCK), "toolchain drift")
    require(manifest.get("flattened_variant_count") == len(sources) == 27, "flattened count mismatch")
    require(manifest.get("shell_only_variant_count") == 5, "shell-only count mismatch")
    require(manifest.get("support_granted_count") == 0, "manifest promotes support")
    records = manifest.get("packets", [])
    require(len(records) == len(sources), "manifest packet count mismatch")
    require(
        [record.get("variant_id") for record in records]
        == [source["variant_id"] for source in sources],
        "manifest exact-variant coverage/order mismatch",
    )
    require(
        manifest.get("component_count") == sum(record["component_count"] for record in records),
        "manifest component total mismatch",
    )
    expected_dispositions = Counter(record["partition_disposition"] for record in records)
    require(
        manifest.get("disposition_counts") == dict(sorted(expected_dispositions.items())),
        "manifest disposition summary drift",
    )
    for source, record in zip(sources, records, strict=True):
        require(record.get("support_granted") is False, "record promotes support")
        require(record.get("candidate_partition_only") is True, "record loses evidence class")
        require(record.get("step_sha256") == source["step_sha256"], "record source drift")
        probe = probes[source["variant_id"]]
        kind = record["component_kind"]
        expected_count = probe["topology"]["solids" if kind == "solid" else "shells"]
        require(record["component_count"] == expected_count, "record/probe count mismatch")
        validate_components(record["components"], kind)
        require(
            record["partition_disposition"] == disposition(kind, expected_count),
            "record disposition drift",
        )
        if check_local:
            require(
                record == packet_record(source, probe, require_images=True),
                "local flattened packet drift",
            )


def triage_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Flattened STEP partition triage",
        "",
        "Stable component IDs describe exact OpenCascade topology only; they are not",
        "housing/output semantics. Local overview and largest-component sheets assist",
        "manual review. All exact variants remain unsupported.",
        "",
        "| Variant | Series / model | Inventory | Representative IDs | Disposition |",
        "|---|---|---:|---|---|",
    ]
    for packet in manifest["packets"]:
        representative = ", ".join(f"`{value}`" for value in packet["representative_component_ids"])
        lines.append(
            f"| `{packet['variant_id']}` | {packet['series']} / {packet['model']} | "
            f"{packet['component_count']} {packet['component_kind']}(s) | {representative} | "
            f"{packet['partition_disposition']} |"
        )
    lines.extend(
        [
            "",
            f"Coverage: {manifest['flattened_variant_count']}/27 flattened variants; "
            f"{manifest['component_count']} stable topology components inventoried.",
            f"Shell-only: {manifest['shell_only_variant_count']}/27. "
            f"Semantic/support acceptance: {manifest['support_granted_count']}/27.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check-local", action="store_true")
    args = parser.parse_args()
    if args.write:
        manifest = build_manifest()
        MANIFEST.write_text(canonical_json(manifest), encoding="utf-8")
        TRIAGE.write_text(triage_markdown(manifest), encoding="utf-8")
    else:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    validate_manifest(manifest, check_local=args.write or args.check_local)
    require(TRIAGE.read_text(encoding="utf-8") == triage_markdown(manifest), "triage report drift")
    print(
        "FLATTENED_PARTITION_MANIFEST_OK "
        f"variants={manifest['flattened_variant_count']} "
        f"components={manifest['component_count']} supported={manifest['support_granted_count']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ManifestError, ValueError) as error:
        print(f"flattened partition manifest failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
