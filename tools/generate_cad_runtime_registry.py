#!/usr/bin/env python3
"""Generate the canonical local host/ROS/simulator CAD asset registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INSPECTION = ROOT / "generated/myactuator/cad/step_inspection.json"
LEDGER = ROOT / "assets/myactuator/cad_review.json"
SUPPORT = ROOT / "generated/myactuator/cad/support_report.json"
CANDIDATES = ROOT / "generated/myactuator/cad/candidate_export_reports"
DROPBEAR = ROOT / "generated/dropbear/simulator/dropbear_config.json"
OUTPUT = ROOT / "generated/myactuator/cad/runtime_asset_registry.json"
VERSION = "myactuator-cad-runtime-asset-registry/1"
ACCEPTED = {"accepted_local", "accepted_redistributable"}


class RuntimeRegistryError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeRegistryError(message)


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


def build_registry() -> dict[str, Any]:
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    support = json.loads(SUPPORT.read_text(encoding="utf-8"))
    dropbear = json.loads(DROPBEAR.read_text(encoding="utf-8"))
    reviews = {item["variant_id"]: item for item in ledger["variants"]}
    candidates: dict[str, dict[str, Any]] = {}
    for path in sorted(CANDIDATES.glob("step-*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        candidates[report["variant_id"]] = {
            "report_path": path.relative_to(ROOT).as_posix(),
            "report_sha256": sha256(path),
            "evidence_class": report["evidence_class"],
            "unresolved_question_count": len(report["unresolved_questions"]),
            "accepted_asset": report["accepted_asset"],
            "support_granted": report["support_granted"],
        }

    configurations = []
    for configuration in ledger["geometry_configurations"]:
        canonical_id = configuration["canonical_variant_id"]
        review = reviews.get(canonical_id) if canonical_id else None
        accepted = configuration["status"] in ACCEPTED
        verified = bool(review and review["artifacts"]["status"] == "verified")
        local_loadable = accepted and verified
        browser_loadable = bool(
            local_loadable
            and configuration["status"] == "accepted_redistributable"
            and review["redistribution_status"] == "redistribution_approved"
        )
        local_assets = None
        if local_loadable:
            local_assets = {
                name: review["artifacts"][name]
                for name in (
                    "housing_step",
                    "output_step",
                    "housing_glb",
                    "output_glb",
                    "collision_glb",
                )
            }
        configurations.append(
            {
                "configuration_id": configuration["configuration_id"],
                "series": configuration["series"],
                "model": configuration["model"],
                "selector_status": configuration["selector_status"],
                "selector_key": configuration["selector_key"],
                "selector_dimensions": configuration["selector_dimensions"],
                "source_variant_ids": configuration["source_variant_ids"],
                "canonical_variant_id": canonical_id,
                "review_status": configuration["status"],
                "local_runtime_loadable": local_loadable,
                "browser_loadable": browser_loadable,
                "local_assets": local_assets,
                "candidate_reports": [
                    {"variant_id": variant_id, **candidates[variant_id]}
                    for variant_id in configuration["source_variant_ids"]
                    if variant_id in candidates
                ],
            }
        )

    models = [
        {
            "series": model["series"],
            "model": model["model"],
            "review_status": model["status"],
            "configuration_ids": model["configuration_ids"],
        }
        for model in ledger["models"]
    ]
    variants = [
        {
            "variant_id": item["variant_id"],
            "series": item["series"],
            "model": item["model"],
            "step_sha256": item["step_sha256"],
            "source_structure": item["manifest_structure"],
            "review_status": reviews[item["variant_id"]]["review_status"],
            "source_step_is_runtime_asset": False,
            "candidate_report_available": item["variant_id"] in candidates,
        }
        for item in inspection["variants"]
    ]
    dropbear_registry = dropbear["registry"]
    dropbear_identity = dropbear["generated_identity"]
    registry = {
        "schema_version": VERSION,
        "source_hashes": {
            "inspection_sha256": sha256(INSPECTION),
            "review_ledger_sha256": sha256(LEDGER),
            "support_report_sha256": sha256(SUPPORT),
            "dropbear_simulator_view_sha256": sha256(DROPBEAR),
        },
        "policy": {
            "exact_configuration_required": True,
            "accepted_local_may_load_only_locally": True,
            "accepted_redistributable_required_for_browser": True,
            "source_step_is_never_runtime_asset": True,
            "candidate_is_never_runtime_asset": True,
            "artifact_hash_verification_required": True,
            "plant_parameters_are_separate": True,
        },
        "summary": {
            "models": len(models),
            "source_variants": len(variants),
            "geometry_configurations": len(configurations),
            "accepted_configurations": sum(item["review_status"] in ACCEPTED for item in configurations),
            "local_runtime_loadable_configurations": sum(item["local_runtime_loadable"] for item in configurations),
            "browser_loadable_configurations": sum(item["browser_loadable"] for item in configurations),
            "candidate_reports": len(candidates),
            "dropbear_bound_cad_assets": len(dropbear_registry["cad_assets"]),
        },
        "models": models,
        "configurations": configurations,
        "source_variants": variants,
        "dropbear": {
            "configuration_id": dropbear_identity["configuration_id"],
            "configuration_digest": dropbear_identity["canonical_digest"],
            "motion_enable_allowed": dropbear_registry["safety_admission"]["motion_enable_allowed"],
            "bound_cad_asset_ids": [item["asset_id"] for item in dropbear_registry["cad_assets"]],
        },
    }
    validate_registry(registry)
    return registry


def validate_registry(registry: dict[str, Any]) -> None:
    require(registry.get("schema_version") == VERSION, "runtime registry schema mismatch")
    summary = registry.get("summary", {})
    require(summary.get("models") == len(registry.get("models", [])) == 44, "model coverage mismatch")
    require(summary.get("source_variants") == len(registry.get("source_variants", [])) == 53, "source coverage mismatch")
    configurations = registry.get("configurations", [])
    require(summary.get("geometry_configurations") == len(configurations), "configuration coverage mismatch")
    require(len({item["configuration_id"] for item in configurations}) == len(configurations), "duplicate configuration")
    accepted = [item for item in configurations if item["review_status"] in ACCEPTED]
    local = [item for item in configurations if item["local_runtime_loadable"]]
    browser = [item for item in configurations if item["browser_loadable"]]
    require(summary.get("accepted_configurations") == len(accepted), "accepted summary drift")
    require(summary.get("local_runtime_loadable_configurations") == len(local), "local summary drift")
    require(summary.get("browser_loadable_configurations") == len(browser), "browser summary drift")
    require(all(item["review_status"] in ACCEPTED and item["local_assets"] for item in local), "unaccepted local asset")
    require(all(item["local_assets"] is None for item in configurations if not item["local_runtime_loadable"]), "unloadable local path leak")
    require(all(item["review_status"] == "accepted_redistributable" and item["local_runtime_loadable"] for item in browser), "browser asset exceeds local/redistribution evidence")
    require(all(not item["source_step_is_runtime_asset"] for item in registry["source_variants"]), "source STEP promoted")
    require(
        all(
            candidate["accepted_asset"] is False and candidate["support_granted"] is False
            for configuration in configurations
            for candidate in configuration["candidate_reports"]
        ),
        "candidate report promoted",
    )
    require(registry["dropbear"]["motion_enable_allowed"] is False, "incomplete Dropbear enablement drift")
    require(
        summary.get("dropbear_bound_cad_assets") == len(registry["dropbear"]["bound_cad_asset_ids"]),
        "Dropbear binding summary drift",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    registry = build_registry()
    rendered = canonical_json(registry)
    if args.write:
        atomic_write(OUTPUT, rendered)
    elif args.check:
        require(OUTPUT.is_file() and OUTPUT.read_text(encoding="utf-8") == rendered, "runtime registry drift")
    print(
        "CAD_RUNTIME_REGISTRY_OK "
        f"models={registry['summary']['models']} variants={registry['summary']['source_variants']} "
        f"configs={registry['summary']['geometry_configurations']} "
        f"local={registry['summary']['local_runtime_loadable_configurations']} "
        f"browser={registry['summary']['browser_loadable_configurations']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, RuntimeRegistryError, ValueError) as error:
        print(f"CAD runtime registry generation failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
