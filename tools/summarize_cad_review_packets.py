#!/usr/bin/env python3
"""Create/check tracked metadata for local-only assembly review packets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cad_review_packet_common import (
    AUTHORITY_FIELDS,
    MANIFEST_VERSION,
    PACKET_VERSION,
    candidate_score,
)


ROOT = Path(__file__).resolve().parents[1]
INSPECTION = ROOT / "generated" / "myactuator" / "cad" / "step_inspection.json"
TOOLCHAIN_LOCK = ROOT / "tools" / "cad-toolchain-lock.json"
PACKET_ROOT = ROOT / "generated" / "myactuator" / "cad" / "review_packets"
MANIFEST = ROOT / "generated" / "myactuator" / "cad" / "review_packet_manifest.json"
TRIAGE = ROOT / "generated" / "myactuator" / "cad" / "review_packet_triage.md"


class ManifestError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestError(message)


def assembly_sources() -> list[dict[str, Any]]:
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    return sorted(
        (
            source
            for source in inspection["variants"]
            if source["manifest_structure"] == "assembly"
        ),
        key=lambda source: source["variant_id"],
    )


def packet_record(source: dict[str, Any], require_images: bool) -> dict[str, Any]:
    packet_path = PACKET_ROOT / source["variant_id"] / "packet.json"
    require(packet_path.is_file(), f"missing packet: {source['variant_id']}")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    identity = (
        packet.get("variant_id"),
        packet.get("series"),
        packet.get("model"),
        packet.get("vendor_relative_path"),
        packet.get("step_sha256"),
    )
    expected_identity = (
        source["variant_id"],
        source["series"],
        source["model"],
        source["vendor_relative_path"],
        source["step_sha256"],
    )
    require(packet.get("schema_version") == PACKET_VERSION, "packet schema mismatch")
    require(identity == expected_identity, f"packet identity mismatch: {source['variant_id']}")
    require(packet.get("review_status") == "candidate_visuals_only", "packet status promoted")
    require(
        all(packet.get(field) is False for field in AUTHORITY_FIELDS),
        f"packet grants semantic authority: {source['variant_id']}",
    )

    expected_members = {
        relationship["occurrence_name"]["decoded"]: relationship
        for relationship in source["assembly_relationships"]
    }
    members = packet.get("members", [])
    require(len(members) == len(expected_members), "packet member count mismatch")
    require(
        {member.get("occurrence") for member in members} == set(expected_members),
        "packet occurrence coverage mismatch",
    )
    candidates: list[dict[str, Any]] = []
    for member in members:
        relationship = expected_members[member["occurrence"]]
        name = relationship["related_product_name"]
        score, terms = candidate_score(name)
        require(member.get("related_product_name") == name, "packet product-name mismatch")
        require(
            member.get("product_entity_ref") == f"#{relationship['related_product_id']}",
            "packet product-entity mismatch",
        )
        require(
            member.get("output_candidate_score") == score
            and member.get("candidate_terms") == terms,
            "packet candidate-score drift",
        )
        if score > 0:
            candidates.append(
                {
                    "candidate_terms": terms,
                    "occurrence": member["occurrence"],
                    "output_candidate_score": score,
                    "product_entity_ref": member["product_entity_ref"],
                    "related_product_name": name,
                    "visual_available": member.get("visual_available", True),
                }
            )

    images: dict[str, str] = {}
    for name in ("overview", "member_sheet"):
        image = packet.get("images", {}).get(name, {})
        image_path = ROOT / image.get("path", "")
        require(bool(image.get("sha256")), "packet image hash missing")
        if require_images:
            require(image_path.is_file(), f"packet image missing: {image_path}")
            require(sha256(image_path) == image["sha256"], f"packet image changed: {image_path}")
        images[f"{name}_sha256"] = image["sha256"]

    return {
        "variant_id": source["variant_id"],
        "series": source["series"],
        "model": source["model"],
        "vendor_relative_path": source["vendor_relative_path"],
        "step_sha256": source["step_sha256"],
        "packet_json_sha256": sha256(packet_path),
        "member_count": len(members),
        "representative_product_views": packet["representative_product_views"],
        "positive_name_candidates": candidates,
        **images,
        "candidate_visuals_only": True,
        "support_granted": False,
    }


def build_manifest() -> dict[str, Any]:
    records = [packet_record(source, require_images=True) for source in assembly_sources()]
    return {
        "schema_version": MANIFEST_VERSION,
        "inspection_sha256": sha256(INSPECTION),
        "toolchain_lock_sha256": sha256(TOOLCHAIN_LOCK),
        "scope": "local candidate visuals only; no CAD semantic or simulation support authority",
        "assembly_variant_count": len(records),
        "support_granted_count": 0,
        "packets": records,
    }


def triage_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Assembly CAD candidate-review triage",
        "",
        "This is a deterministic candidate index, not a semantic CAD review. Name",
        "scores only prioritize local images for a human reviewer. Housing/output",
        "membership, joint frames, articulation and simulator support remain ungranted.",
        "",
        "| Variant | Series / model | Members / representative products | Positive name candidates | Disposition |",
        "|---|---|---:|---|---|",
    ]
    for packet in manifest["packets"]:
        candidates = "; ".join(
            f"{item['occurrence']} {item['related_product_name']} "
            f"({item['output_candidate_score']:+d})"
            f"{' [group/no direct shape]' if not item['visual_available'] else ''}"
            for item in packet["positive_name_candidates"]
        ) or "none"
        candidates = candidates.replace("|", "\\|")
        lines.append(
            f"| `{packet['variant_id']}` | {packet['series']} / {packet['model']} | "
            f"{packet['member_count']} / {packet['representative_product_views']} | "
            f"{candidates} | candidate visuals only; unsupported |"
        )
    lines.extend(
        [
            "",
            f"Coverage: {manifest['assembly_variant_count']}/26 assembly variants. ",
            f"Semantic/support acceptance: {manifest['support_granted_count']}/26.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_manifest(manifest: dict[str, Any], check_local: bool) -> None:
    sources = assembly_sources()
    require(manifest.get("schema_version") == MANIFEST_VERSION, "manifest schema mismatch")
    require(manifest.get("inspection_sha256") == sha256(INSPECTION), "inspection drift")
    require(manifest.get("toolchain_lock_sha256") == sha256(TOOLCHAIN_LOCK), "toolchain drift")
    require(manifest.get("assembly_variant_count") == len(sources) == 26, "assembly count mismatch")
    require(manifest.get("support_granted_count") == 0, "manifest promotes support")
    records = manifest.get("packets", [])
    require(len(records) == len(sources), "manifest packet count mismatch")
    require(
        [record.get("variant_id") for record in records]
        == [source["variant_id"] for source in sources],
        "manifest exact-variant coverage/order mismatch",
    )
    for source, record in zip(sources, records, strict=True):
        require(record.get("support_granted") is False, "record promotes support")
        require(record.get("candidate_visuals_only") is True, "record loses evidence class")
        require(record.get("step_sha256") == source["step_sha256"], "record source drift")
        require(record.get("vendor_relative_path") == source["vendor_relative_path"], "record path drift")
        if check_local:
            require(record == packet_record(source, require_images=True), "local packet drift")


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
    validate_manifest(manifest, check_local=args.check_local or args.write)
    require(TRIAGE.read_text(encoding="utf-8") == triage_markdown(manifest), "triage report drift")
    print(
        "CAD_REVIEW_PACKET_MANIFEST_OK "
        f"variants={manifest['assembly_variant_count']} supported={manifest['support_granted_count']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ManifestError, ValueError) as error:
        print(f"CAD review packet manifest failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
