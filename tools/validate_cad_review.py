#!/usr/bin/env python3
"""Create and validate the exact-variant CAD review and support ledgers."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "myactuator-cad-review.schema.json"
INSPECTION = ROOT / "generated" / "myactuator" / "cad" / "step_inspection.json"
LEDGER = ROOT / "assets" / "myactuator" / "cad_review.json"
SUPPORT_REPORT = ROOT / "generated" / "myactuator" / "cad" / "support_report.json"

CAD_REVIEW_VERSION = "myactuator-cad-review/2"
SUPPORT_REPORT_VERSION = "myactuator-cad-support-report/2"
ACCEPTED = {"accepted_local", "accepted_redistributable"}

INSPECTOR_SPEC = importlib.util.spec_from_file_location(
    "inspect_step_sources", ROOT / "tools" / "inspect_step_sources.py"
)
assert INSPECTOR_SPEC is not None and INSPECTOR_SPEC.loader is not None
inspector = importlib.util.module_from_spec(INSPECTOR_SPEC)
INSPECTOR_SPEC.loader.exec_module(inspector)


class CadReviewError(ValueError):
    """CAD semantic evidence is incomplete or inconsistent."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _unreviewed_variant(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "variant_id": item["variant_id"],
        "series": item["series"],
        "model": item["model"],
        "vendor_relative_path": item["vendor_relative_path"],
        "step_sha256": item["step_sha256"],
        "bytes": item["bytes"],
        "step_structure": item["manifest_structure"],
        "review_status": "unreviewed",
        "reviewer": None,
        "reviewed_at": None,
        "review_evidence_refs": [],
        "unit": {
            "status": "unreviewed",
            "source_length_unit": None,
            "scale_to_m": None,
            "override_rationale": None,
            "evidence_refs": [],
        },
        "members": {
            "status": "unreviewed",
            "method": None,
            "housing_refs": [],
            "output_refs": [],
            "evidence_refs": [],
        },
        "frame": {
            "status": "unreviewed",
            "source_to_canonical": None,
            "evidence_refs": [],
        },
        "joint": {
            "status": "unreviewed",
            "joint_type": None,
            "origin_m": None,
            "axis_unit": None,
            "positive_direction": None,
            "zero_definition": None,
            "evidence_refs": [],
        },
        "artifacts": {
            "status": "unreviewed",
            "source_variant_sha256": None,
            "toolchain_lock_sha256": None,
            "housing_step": None,
            "output_step": None,
            "housing_glb": None,
            "output_glb": None,
            "collision_glb": None,
            "visual_evidence_refs": [],
        },
        "redistribution_status": "license_review_required",
        "redistribution_evidence_refs": [],
        "denial_reason": "semantic housing/output/axis review not performed",
    }


def configuration_id(item: dict[str, Any]) -> str:
    identity = "\0".join((item["series"], item["model"], item["variant_id"]))
    return "cadcfg-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def create_empty_ledger(inspection: dict[str, Any]) -> dict[str, Any]:
    variants = [_unreviewed_variant(item) for item in inspection["variants"]]
    model_keys = sorted({(item["series"], item["model"]) for item in variants})
    configurations = [
        {
            "configuration_id": configuration_id(item),
            "series": item["series"],
            "model": item["model"],
            "source_variant_ids": [item["variant_id"]],
            "selector_status": "unresolved",
            "selector_key": None,
            "selector_dimensions": [],
            "canonical_variant_id": None,
            "status": "unsupported",
            "reviewer": None,
            "reviewed_at": None,
            "evidence_refs": [],
            "denial_reason": "geometry configuration selector not reviewed",
        }
        for item in variants
    ]
    return {
        "schema_version": CAD_REVIEW_VERSION,
        "inspection_schema_version": inspection["schema_version"],
        "inspection_manifest_sha256": inspection["manifest_sha256"],
        "variants": variants,
        "geometry_configurations": configurations,
        "models": [
            {
                "series": series,
                "model": model,
                "status": "unsupported",
                "configuration_ids": [
                    item["configuration_id"]
                    for item in configurations
                    if (item["series"], item["model"]) == (series, model)
                ],
                "denial_reason": "no accepted exact geometry configuration",
            }
            for series, model in model_keys
        ],
    }


def migrate_v1_to_v2(ledger: dict[str, Any], inspection: dict[str, Any]) -> dict[str, Any]:
    if ledger.get("schema_version") != "myactuator-cad-review/1":
        raise CadReviewError("migration input is not CAD review V1")
    variants = ledger.get("variants", [])
    models = ledger.get("models", [])
    if len(variants) != 53 or any(item.get("review_status") != "unreviewed" for item in variants):
        raise CadReviewError("refusing V1 migration with non-default variant review work")
    if len(models) != 44 or any(
        item.get("status") != "unsupported" or item.get("canonical_variant_id") is not None
        for item in models
    ):
        raise CadReviewError("refusing V1 migration with model selection work")
    migrated = create_empty_ledger(inspection)
    expected_ids = [item["variant_id"] for item in migrated["variants"]]
    if [item.get("variant_id") for item in variants] != expected_ids:
        raise CadReviewError("V1 migration variant ordering/identity mismatch")
    migrated["variants"] = variants
    return migrated


def _validate_timestamp(value: str, context: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CadReviewError(f"{context}: invalid reviewed_at") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CadReviewError(f"{context}: reviewed_at must include UTC offset")


def _safe_relative_ref(value: str, context: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value.startswith("file:"):
        raise CadReviewError(f"{context}: evidence/artifact path is not safe-relative")


def _require_refs(values: list[str], count: int, context: str) -> None:
    if len(values) < count:
        raise CadReviewError(f"{context}: at least {count} evidence reference(s) required")
    for value in values:
        _safe_relative_ref(value, context)


def _validate_transform(values: list[float], context: str) -> None:
    if len(values) != 16 or not all(math.isfinite(value) for value in values):
        raise CadReviewError(f"{context}: transform must contain 16 finite values")
    if any(abs(values[12 + index] - expected) > 1e-9 for index, expected in enumerate((0.0, 0.0, 0.0, 1.0))):
        raise CadReviewError(f"{context}: transform last row must be [0,0,0,1]")
    rotation = [values[0:3], values[4:7], values[8:11]]
    for index, row in enumerate(rotation):
        norm = math.sqrt(sum(value * value for value in row))
        if abs(norm - 1.0) > 1e-6:
            raise CadReviewError(f"{context}: rotation row {index} is not unit length")
    for first in range(3):
        for second in range(first + 1, 3):
            dot = sum(rotation[first][i] * rotation[second][i] for i in range(3))
            if abs(dot) > 1e-6:
                raise CadReviewError(f"{context}: rotation rows are not orthogonal")
    determinant = (
        rotation[0][0] * (rotation[1][1] * rotation[2][2] - rotation[1][2] * rotation[2][1])
        - rotation[0][1] * (rotation[1][0] * rotation[2][2] - rotation[1][2] * rotation[2][0])
        + rotation[0][2] * (rotation[1][0] * rotation[2][1] - rotation[1][1] * rotation[2][0])
    )
    if abs(determinant - 1.0) > 1e-6:
        raise CadReviewError(f"{context}: rotation determinant must be +1")


def _validate_axis(values: list[float], context: str) -> None:
    if len(values) != 3 or not all(math.isfinite(value) for value in values):
        raise CadReviewError(f"{context}: axis must contain three finite values")
    if abs(math.sqrt(sum(value * value for value in values)) - 1.0) > 1e-6:
        raise CadReviewError(f"{context}: axis must be unit length")


def _validate_artifact(value: dict[str, Any], context: str) -> None:
    _safe_relative_ref(value["path"], context)
    if value["bytes"] <= 0 or len(value["sha256"]) != 64:
        raise CadReviewError(f"{context}: invalid artifact identity")


def _validate_clean_unreviewed(item: dict[str, Any]) -> None:
    context = item["variant_id"]
    if item["reviewer"] is not None or item["reviewed_at"] is not None or item["review_evidence_refs"]:
        raise CadReviewError(f"{context}: unreviewed row contains review authority")
    for key in ("unit", "members", "frame", "joint"):
        if item[key]["status"] != "unreviewed":
            raise CadReviewError(f"{context}: unreviewed row has reviewed {key}")
    if item["artifacts"]["status"] != "unreviewed":
        raise CadReviewError(f"{context}: unreviewed row has verified artifacts")


def _validate_accepted(
    item: dict[str, Any], inspection_item: dict[str, Any]
) -> None:
    context = item["variant_id"]
    if not item["reviewer"] or not item["reviewed_at"]:
        raise CadReviewError(f"{context}: accepted review requires reviewer and time")
    _validate_timestamp(item["reviewed_at"], context)
    _require_refs(item["review_evidence_refs"], 1, context)

    unit = item["unit"]
    expected_scale = {"millimetre": 0.001, "metre": 1.0, "inch": 0.0254}
    if unit["status"] != "reviewed" or unit["source_length_unit"] not in expected_scale:
        raise CadReviewError(f"{context}: accepted review requires explicit source unit")
    if not math.isclose(unit["scale_to_m"], expected_scale[unit["source_length_unit"]], rel_tol=0.0, abs_tol=1e-12):
        raise CadReviewError(f"{context}: unit scale does not match source unit")
    _require_refs(unit["evidence_refs"], 1, context)
    candidate = inspection_item["length_unit_candidate"]
    if candidate in expected_scale and candidate != unit["source_length_unit"]:
        if not unit["override_rationale"]:
            raise CadReviewError(f"{context}: unit candidate override requires rationale")
    elif unit["override_rationale"] is not None:
        raise CadReviewError(f"{context}: unit override rationale without an override")

    members = item["members"]
    if members["status"] != "reviewed" or not members["housing_refs"] or not members["output_refs"]:
        raise CadReviewError(f"{context}: housing and output selections are required")
    if set(members["housing_refs"]) & set(members["output_refs"]):
        raise CadReviewError(f"{context}: housing/output selections must be disjoint")
    _require_refs(members["evidence_refs"], 1, context)
    if item["step_structure"] == "assembly":
        if members["method"] != "assembly_product_entities":
            raise CadReviewError(f"{context}: assembly requires product-entity selection")
        allowed = {f"#{product['entity_id']}" for product in inspection_item["products"]}
        if not set(members["housing_refs"] + members["output_refs"]) <= allowed:
            raise CadReviewError(f"{context}: assembly selection references unknown product")
    else:
        if members["method"] != "reviewed_partition":
            raise CadReviewError(f"{context}: flattened source requires reviewed partition")
        _require_refs(members["evidence_refs"], 2, context)

    frame = item["frame"]
    if frame["status"] != "reviewed" or frame["source_to_canonical"] is None:
        raise CadReviewError(f"{context}: canonical frame review required")
    _validate_transform(frame["source_to_canonical"], context)
    _require_refs(frame["evidence_refs"], 1, context)

    joint = item["joint"]
    if joint["status"] != "reviewed" or joint["joint_type"] not in {"revolute", "continuous"}:
        raise CadReviewError(f"{context}: revolute joint review required")
    if joint["origin_m"] is None or len(joint["origin_m"]) != 3 or not all(math.isfinite(value) for value in joint["origin_m"]):
        raise CadReviewError(f"{context}: finite SI joint origin required")
    if joint["axis_unit"] is None:
        raise CadReviewError(f"{context}: joint axis required")
    _validate_axis(joint["axis_unit"], context)
    if not joint["positive_direction"] or not joint["zero_definition"]:
        raise CadReviewError(f"{context}: direction and zero definitions required")
    _require_refs(joint["evidence_refs"], 1, context)

    artifacts = item["artifacts"]
    if artifacts["status"] != "verified":
        raise CadReviewError(f"{context}: verified exports required")
    if artifacts["source_variant_sha256"] != item["step_sha256"]:
        raise CadReviewError(f"{context}: artifact source hash mismatch")
    if artifacts["toolchain_lock_sha256"] is None:
        raise CadReviewError(f"{context}: toolchain lock hash required")
    required_artifacts = ("housing_step", "output_step", "housing_glb", "output_glb", "collision_glb")
    for name in required_artifacts:
        if artifacts[name] is None:
            raise CadReviewError(f"{context}: missing {name}")
        _validate_artifact(artifacts[name], f"{context}/{name}")
    if artifacts["housing_step"]["sha256"] == artifacts["output_step"]["sha256"]:
        raise CadReviewError(f"{context}: housing and output STEP artifacts are identical")
    if artifacts["housing_glb"]["sha256"] == artifacts["output_glb"]["sha256"]:
        raise CadReviewError(f"{context}: housing and output GLB artifacts are identical")
    _require_refs(artifacts["visual_evidence_refs"], 2, context)

    if item["review_status"] == "accepted_local":
        if item["redistribution_status"] != "local_only":
            raise CadReviewError(f"{context}: accepted_local requires local_only disposition")
    else:
        if item["redistribution_status"] != "redistribution_approved":
            raise CadReviewError(f"{context}: redistribution acceptance requires approval")
        _require_refs(item["redistribution_evidence_refs"], 1, context)


def validate_ledger(ledger: dict[str, Any], inspection: dict[str, Any]) -> None:
    schema = load_json(SCHEMA)
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(validator.iter_errors(ledger), key=lambda error: list(error.absolute_path))
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path)
        raise CadReviewError(f"schema {location}: {first.message}")

    if ledger["inspection_schema_version"] != inspection["schema_version"]:
        raise CadReviewError("inspection schema version mismatch")
    if ledger["inspection_manifest_sha256"] != inspection["manifest_sha256"]:
        raise CadReviewError("inspection manifest hash mismatch")

    inspection_by_id = {item["variant_id"]: item for item in inspection["variants"]}
    variants_by_id: dict[str, dict[str, Any]] = {}
    for item in ledger["variants"]:
        key = item["variant_id"]
        if key in variants_by_id or key not in inspection_by_id:
            raise CadReviewError(f"duplicate or unknown variant: {key}")
        source = inspection_by_id[key]
        joined = (
            item["series"], item["model"], item["vendor_relative_path"],
            item["step_sha256"], item["bytes"], item["step_structure"],
        )
        expected = (
            source["series"], source["model"], source["vendor_relative_path"],
            source["step_sha256"], source["bytes"], source["manifest_structure"],
        )
        if joined != expected:
            raise CadReviewError(f"source identity mismatch: {key}")
        if item["review_status"] == "unreviewed":
            _validate_clean_unreviewed(item)
        elif item["review_status"] in ACCEPTED:
            _validate_accepted(item, source)
        elif item["reviewer"] is None or item["reviewed_at"] is None:
            raise CadReviewError(f"{key}: non-default review state requires reviewer/time")
        variants_by_id[key] = item
    if set(variants_by_id) != set(inspection_by_id):
        raise CadReviewError("review ledger does not cover all inspection variants")

    expected_models = {
        (item["series"], item["model"]) for item in inspection["variants"]
    }
    configurations_by_id: dict[str, dict[str, Any]] = {}
    covered_variant_ids: set[str] = set()
    selector_keys: set[tuple[str, str, str]] = set()
    for configuration in ledger["geometry_configurations"]:
        key = configuration["configuration_id"]
        model_key = (configuration["series"], configuration["model"])
        if key in configurations_by_id or model_key not in expected_models:
            raise CadReviewError(f"duplicate or unknown geometry configuration: {key}")
        source_ids = configuration["source_variant_ids"]
        if any(source_id not in variants_by_id for source_id in source_ids):
            raise CadReviewError(f"{key}: unknown source variant")
        if any(
            (variants_by_id[source_id]["series"], variants_by_id[source_id]["model"])
            != model_key
            for source_id in source_ids
        ):
            raise CadReviewError(f"{key}: source variant belongs to another model")
        overlap = covered_variant_ids & set(source_ids)
        if overlap:
            raise CadReviewError(f"{key}: source variant covered by multiple selectors: {sorted(overlap)}")
        covered_variant_ids.update(source_ids)

        selector_status = configuration["selector_status"]
        if selector_status == "unresolved":
            if len(source_ids) != 1:
                raise CadReviewError(f"{key}: unresolved selector cannot merge sources")
            if any(
                (
                    configuration["selector_key"] is not None,
                    bool(configuration["selector_dimensions"]),
                    configuration["canonical_variant_id"] is not None,
                    configuration["reviewer"] is not None,
                    configuration["reviewed_at"] is not None,
                    bool(configuration["evidence_refs"]),
                )
            ):
                raise CadReviewError(f"{key}: unresolved selector contains review authority")
            if configuration["status"] not in {"unsupported"}:
                raise CadReviewError(f"{key}: unresolved selector must remain unsupported")
        else:
            if not configuration["selector_key"] or not configuration["reviewer"] or not configuration["reviewed_at"]:
                raise CadReviewError(f"{key}: reviewed selector requires key/reviewer/time")
            _validate_timestamp(configuration["reviewed_at"], key)
            _require_refs(configuration["evidence_refs"], 1, key)
            selector_identity = (*model_key, configuration["selector_key"])
            if selector_identity in selector_keys:
                raise CadReviewError(f"{key}: duplicate selector key within model")
            selector_keys.add(selector_identity)
            dimension_names = [item["name"] for item in configuration["selector_dimensions"]]
            if len(dimension_names) != len(set(dimension_names)):
                raise CadReviewError(f"{key}: duplicate selector dimension")
            for dimension in configuration["selector_dimensions"]:
                _require_refs(dimension["evidence_refs"], 1, key)
            canonical_id = configuration["canonical_variant_id"]
            if canonical_id not in source_ids:
                raise CadReviewError(f"{key}: canonical variant is outside selector sources")
            if len(source_ids) > 1 and not configuration["evidence_refs"]:
                raise CadReviewError(f"{key}: merged sources require equivalence evidence")
            if configuration["status"] in {"candidate", "blocked", "unsupported"}:
                pass
            elif configuration["status"] in ACCEPTED:
                expected_variant_status = configuration["status"]
                if variants_by_id[canonical_id]["review_status"] != expected_variant_status:
                    raise CadReviewError(f"{key}: configuration support exceeds canonical variant evidence")
            else:
                raise CadReviewError(f"{key}: invalid reviewed selector state")
        configurations_by_id[key] = configuration
    if covered_variant_ids != set(variants_by_id):
        raise CadReviewError("geometry configurations do not cover every source variant exactly once")

    models_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for model in ledger["models"]:
        key = (model["series"], model["model"])
        if key in models_by_key or key not in expected_models:
            raise CadReviewError(f"duplicate or unknown model row: {key}")
        expected_configuration_ids = {
            configuration_id
            for configuration_id, configuration in configurations_by_id.items()
            if (configuration["series"], configuration["model"]) == key
        }
        if set(model["configuration_ids"]) != expected_configuration_ids:
            raise CadReviewError(f"{key}: model configuration coverage mismatch")
        configurations = [configurations_by_id[value] for value in model["configuration_ids"]]
        accepted = [item for item in configurations if item["status"] in ACCEPTED]
        if not accepted:
            expected_status = "unsupported"
        elif len(accepted) < len(configurations):
            expected_status = "partially_supported_local"
        elif all(item["status"] == "accepted_redistributable" for item in configurations):
            expected_status = "supported_redistributable"
        else:
            expected_status = "supported_local"
        if model["status"] != expected_status:
            raise CadReviewError(f"{key}: model status does not match exact configuration evidence")
        models_by_key[key] = model
    if set(models_by_key) != expected_models:
        raise CadReviewError("model ledger does not cover all 44 models")


def build_support_report(ledger: dict[str, Any]) -> dict[str, Any]:
    variant_counts = Counter(item["review_status"] for item in ledger["variants"])
    configuration_counts = Counter(item["status"] for item in ledger["geometry_configurations"])
    model_counts = Counter(item["status"] for item in ledger["models"])
    return {
        "schema_version": SUPPORT_REPORT_VERSION,
        "ledger_sha256": hashlib.sha256(canonical_json(ledger).encode("utf-8")).hexdigest(),
        "evidence_class": "offline-static",
        "summary": {
            "variants": len(ledger["variants"]),
            "geometry_configurations": len(ledger["geometry_configurations"]),
            "models": len(ledger["models"]),
            "variant_statuses": dict(sorted(variant_counts.items())),
            "configuration_statuses": dict(sorted(configuration_counts.items())),
            "model_statuses": dict(sorted(model_counts.items())),
            "partially_supported_models": model_counts["partially_supported_local"],
            "supported_models": model_counts["supported_local"] + model_counts["supported_redistributable"],
        },
        "geometry_configurations": ledger["geometry_configurations"],
        "models": ledger["models"],
    }


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
    parser.add_argument("--init", action="store_true", help="create an empty ledger; refuse overwrite")
    parser.add_argument("--migrate-v2", action="store_true", help="migrate a pristine V1 denial ledger")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--check-report", action="store_true")
    args = parser.parse_args()

    inspection = load_json(INSPECTION)
    inspector.validate_report_against_manifest(inspection, inspector.read_manifest())
    if args.init:
        if LEDGER.exists():
            raise CadReviewError(f"refusing to overwrite existing review ledger: {LEDGER}")
        atomic_write(LEDGER, canonical_json(create_empty_ledger(inspection)))
    if args.migrate_v2:
        current = load_json(LEDGER)
        atomic_write(LEDGER, canonical_json(migrate_v1_to_v2(current, inspection)))
    ledger = load_json(LEDGER)
    validate_ledger(ledger, inspection)
    report_text = canonical_json(build_support_report(ledger))
    if args.write_report:
        atomic_write(SUPPORT_REPORT, report_text)
    if args.check_report:
        if not SUPPORT_REPORT.is_file() or SUPPORT_REPORT.read_text(encoding="utf-8") != report_text:
            raise CadReviewError("generated CAD support report is stale")

    summary = build_support_report(ledger)["summary"]
    print(
        "CAD_REVIEW_OK "
        f"variants={summary['variants']} models={summary['models']} "
        f"supported={summary['supported_models']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CadReviewError, json.JSONDecodeError, OSError, ValueError) as error:
        print(f"CAD review validation failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
