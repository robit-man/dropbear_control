#!/usr/bin/env python3
"""Generate the browser CAD registry from exact fail-closed review evidence."""

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
RUNTIME = ROOT / "generated/myactuator/cad/runtime_asset_registry.json"
OUTPUT = ROOT / "web/assets/cad_support.generated.json"
VERSION = "myactuator-web-cad-registry/1"


class RegistryError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RegistryError(message)


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
    variant_by_id = {item["variant_id"]: item for item in inspection["variants"]}
    review_by_id = {item["variant_id"]: item for item in ledger["variants"]}
    candidate_by_id = {}
    for path in sorted(CANDIDATES.glob("step-*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        candidate_by_id[report["variant_id"]] = {
            "report_path": path.relative_to(ROOT).as_posix(),
            "report_sha256": sha256(path),
            "accepted_asset": report["accepted_asset"],
            "support_granted": report["support_granted"],
            "unresolved_question_count": len(report["unresolved_questions"]),
        }

    configurations = []
    for configuration in ledger["geometry_configurations"]:
        canonical_id = configuration["canonical_variant_id"]
        canonical_review = review_by_id.get(canonical_id) if canonical_id else None
        accepted = configuration["status"] in {"accepted_local", "accepted_redistributable"}
        browser_loadable = bool(
            accepted
            and canonical_review
            and canonical_review["artifacts"]["status"] == "verified"
            and canonical_review["artifacts"]["housing_glb"]
            and canonical_review["artifacts"]["output_glb"]
            and canonical_review["redistribution_status"] == "redistribution_approved"
        )
        assets = None
        if browser_loadable:
            assets = {
                "housing_glb": canonical_review["artifacts"]["housing_glb"],
                "output_glb": canonical_review["artifacts"]["output_glb"],
                "collision_glb": canonical_review["artifacts"]["collision_glb"],
            }
        configurations.append(
            {
                "configuration_id": configuration["configuration_id"],
                "series": configuration["series"],
                "model": configuration["model"],
                "selector_status": configuration["selector_status"],
                "selector_key": configuration["selector_key"],
                "source_variant_ids": configuration["source_variant_ids"],
                "canonical_variant_id": canonical_id,
                "review_status": configuration["status"],
                "browser_loadable": browser_loadable,
                "assets": assets,
                "candidate_reports": [
                    {"variant_id": variant_id, **candidate_by_id[variant_id]}
                    for variant_id in configuration["source_variant_ids"]
                    if variant_id in candidate_by_id
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
            "review_status": review_by_id[item["variant_id"]]["review_status"],
            "source_step_is_runtime_asset": False,
            "candidate_report_available": item["variant_id"] in candidate_by_id,
        }
        for item in inspection["variants"]
    ]
    accepted_configurations = sum(
        item["review_status"] in {"accepted_local", "accepted_redistributable"}
        for item in configurations
    )
    browser_loadable_configurations = sum(item["browser_loadable"] for item in configurations)
    dropbear_registry = dropbear["registry"]
    dropbear_identity = dropbear["generated_identity"]
    dropbear_cad_assets = dropbear_registry["cad_assets"]
    registry = {
        "schema_version": VERSION,
        "source_hashes": {
            "inspection_sha256": sha256(INSPECTION),
            "review_ledger_sha256": sha256(LEDGER),
            "support_report_sha256": sha256(SUPPORT),
            "dropbear_simulator_view_sha256": sha256(DROPBEAR),
            "runtime_asset_registry_sha256": sha256(RUNTIME),
        },
        "policy": {
            "exact_configuration_required": True,
            "source_step_is_never_runtime_asset": True,
            "candidate_is_never_released_asset": True,
            "redistribution_approval_required_for_browser": True,
            "procedural_fallback_is_toy_visual_only": True,
            "plant_parameters_are_separate_from_cad_support": True,
        },
        "summary": {
            "models": len(models),
            "source_variants": len(variants),
            "geometry_configurations": len(configurations),
            "accepted_configurations": accepted_configurations,
            "browser_loadable_configurations": browser_loadable_configurations,
            "candidate_reports": len(candidate_by_id),
            "dropbear_bound_cad_assets": len(dropbear_cad_assets),
        },
        "models": models,
        "configurations": configurations,
        "source_variants": variants,
        "dropbear": {
            "configuration_id": dropbear_identity["configuration_id"],
            "configuration_digest": dropbear_identity["canonical_digest"],
            "motion_enable_allowed": dropbear_registry["safety_admission"]["motion_enable_allowed"],
            "bound_cad_asset_ids": [item["asset_id"] for item in dropbear_cad_assets],
        },
    }
    validate_registry(registry)
    return registry


def validate_registry(registry: dict[str, Any]) -> None:
    require(registry.get("schema_version") == VERSION, "registry schema mismatch")
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    require(
        registry.get("source_hashes", {}).get("runtime_asset_registry_sha256")
        == sha256(RUNTIME),
        "runtime registry provenance drift",
    )
    summary = registry.get("summary", {})
    require(summary.get("models") == len(registry.get("models", [])) == 44, "model count mismatch")
    require(summary.get("source_variants") == len(registry.get("source_variants", [])) == 53, "variant count mismatch")
    require(
        summary.get("geometry_configurations") == len(registry.get("configurations", [])),
        "configuration count mismatch",
    )
    require(
        len({item["configuration_id"] for item in registry["configurations"]})
        == len(registry["configurations"]),
        "duplicate configuration ID",
    )
    runtime_by_id = {
        item["configuration_id"]: item for item in runtime["configurations"]
    }
    require(
        set(runtime_by_id)
        == {item["configuration_id"] for item in registry["configurations"]},
        "browser/runtime exact configuration coverage drift",
    )
    for item in registry["configurations"]:
        canonical = runtime_by_id[item["configuration_id"]]
        require(
            (
                item["series"],
                item["model"],
                item["source_variant_ids"],
                item["canonical_variant_id"],
                item["review_status"],
                item["browser_loadable"],
            )
            == (
                canonical["series"],
                canonical["model"],
                canonical["source_variant_ids"],
                canonical["canonical_variant_id"],
                canonical["review_status"],
                canonical["browser_loadable"],
            ),
            "browser/runtime configuration parity drift",
        )
    accepted = [
        item
        for item in registry["configurations"]
        if item["review_status"] in {"accepted_local", "accepted_redistributable"}
    ]
    loadable = [item for item in registry["configurations"] if item["browser_loadable"]]
    require(summary.get("accepted_configurations") == len(accepted), "accepted summary mismatch")
    require(summary.get("browser_loadable_configurations") == len(loadable), "loadable summary mismatch")
    require(all(item["review_status"] == "accepted_redistributable" for item in loadable), "local-only asset exposed to browser")
    require(all(item["assets"] is not None for item in loadable), "loadable asset metadata missing")
    require(all(item["assets"] is None for item in registry["configurations"] if not item["browser_loadable"]), "unloadable configuration leaks asset paths")
    require(all(not item["source_step_is_runtime_asset"] for item in registry["source_variants"]), "vendor source promoted to runtime asset")
    require(
        all(
            candidate["accepted_asset"] is False and candidate["support_granted"] is False
            for configuration in registry["configurations"]
            for candidate in configuration["candidate_reports"]
        ),
        "candidate report promoted",
    )
    require(registry["dropbear"]["motion_enable_allowed"] is False, "incomplete Dropbear unexpectedly enableable")
    require(
        summary.get("dropbear_bound_cad_assets")
        == len(registry["dropbear"]["bound_cad_asset_ids"]),
        "Dropbear CAD summary mismatch",
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
        require(OUTPUT.is_file() and OUTPUT.read_text(encoding="utf-8") == rendered, "web CAD registry drift")
    print(
        "WEB_CAD_REGISTRY_OK "
        f"models={registry['summary']['models']} variants={registry['summary']['source_variants']} "
        f"configs={registry['summary']['geometry_configurations']} "
        f"loadable={registry['summary']['browser_loadable_configurations']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, RegistryError, ValueError) as error:
        print(f"web CAD registry generation failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
