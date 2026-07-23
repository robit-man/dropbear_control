#!/usr/bin/env python3
"""Generate the evidence-aware MYACTUATOR simulator runtime catalog."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "assets/myactuator/catalog.tsv"
APPLICABILITY = (
    ROOT / "generated/myactuator/protocol_applicability/registry.json"
)
CAD = ROOT / "generated/myactuator/cad/runtime_asset_registry.json"
PLANT = ROOT / "generated/myactuator/plant/runtime_registry.json"
DROPBEAR = (
    ROOT / "generated/dropbear_graph_lifecycle_projection_v2/simulator.json"
)
SCHEMA = ROOT / "schemas/myactuator-simulator-runtime-catalog.schema.json"
OUTPUT = ROOT / "generated/myactuator/simulator/runtime_catalog.json"
WEB_OUTPUT = ROOT / "web/assets/simulator_runtime_catalog.generated.json"
VERSION = "myactuator-simulator-runtime-catalog/1"


class SimulatorCatalogError(ValueError):
    """A simulator catalog input, semantic relation or output is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SimulatorCatalogError(message)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SimulatorCatalogError(f"cannot load {path}: {error}") from error
    require(isinstance(value, dict), f"{path}: JSON root must be an object")
    return value


def load_catalog() -> list[dict[str, str]]:
    try:
        with CATALOG.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
    except OSError as error:
        raise SimulatorCatalogError(f"cannot load product catalog: {error}") from error
    require(
        list(rows[0]) == [
            "series",
            "model",
            "package_revision",
            "archive_url",
        ],
        "product catalog columns drift",
    )
    require(len(rows) == 44, "product catalog must contain exactly 44 models")
    identities = [(row["series"], row["model"]) for row in rows]
    require(len(set(identities)) == 44, "product catalog identity is not unique")
    require(
        all(
            row["series"]
            and row["model"]
            and row["package_revision"]
            and row["archive_url"].startswith("https://www.myactuator.com/")
            for row in rows
        ),
        "product catalog contains incomplete source rows",
    )
    return rows


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def model_key(series: str, model: str) -> str:
    return "model-" + sha_bytes(
        canonical_bytes({"model": model, "series": series})
    )[:20]


def _backend_profile(value: dict[str, Any]) -> dict[str, Any]:
    kind = value["kind"]
    runtime = value["runtime_loadable"] is True
    use_cases: list[str] = []
    blockers: list[str] = []
    command_capable = kind != "recorded_replay"
    deterministic = kind in {
        "recorded_replay",
        "protocol_emulator",
        "synthetic_actuator_plant",
        "actuator_plant",
    }
    if runtime:
        use_case = {
            "recorded_replay": "recorded_replay",
            "protocol_emulator": "protocol_state_sil",
            "toy_demo": "catalog_demo",
            "synthetic_actuator_plant": "synthetic_plant_sil",
            "actuator_plant": "exact_model_plant_sil",
            "rigid_body": "whole_robot_rigid_body",
            "physical_adapter": "physical_hil",
        }[kind]
        use_cases.append(use_case)
    else:
        blockers.append("backend_not_runtime_loadable")
    if kind == "recorded_replay":
        blockers.append("replay_trace_required_and_commands_forbidden")
    elif kind == "protocol_emulator":
        blockers.append("exact_model_firmware_applicability_unverified")
    elif kind == "toy_demo":
        blockers.append("toy_backend_has_no_physical_dynamics")
    elif kind == "synthetic_actuator_plant":
        blockers.append("synthetic_parameters_have_no_exact_model_fidelity")
    elif kind == "rigid_body" and not runtime:
        blockers.append("canonical_graph_cad_and_plant_unavailable")
    require(
        kind != "physical_adapter",
        "physical adapter cannot enter the offline simulator catalog",
    )
    return {
        "backend_id": value["backend_id"],
        "kind": kind,
        "evidence_class": value["evidence_class"],
        "substitution_scope": value["substitution_scope"],
        "runtime_loadable": runtime,
        "command_capable": command_capable,
        "deterministic_virtual_time": deterministic,
        "models_protocol_state": kind == "protocol_emulator",
        "models_actuator_dynamics": value["models_physical_dynamics"] is True,
        "models_rigid_body": (
            kind == "rigid_body"
            and value["models_physical_dynamics"] is True
        ),
        "exact_model_applicability_verified": kind == "actuator_plant",
        "physically_validated": value["physically_validated"] is True,
        "physical_io": False,
        "parameter_set_id": value["parameter_set_id"],
        "runtime_contract_id": value["runtime_contract_id"],
        "allowed_use_cases": use_cases,
        "blockers": blockers,
    }


def _by_identity(
    values: Iterable[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for value in values:
        result.setdefault((value["series"], value["model"]), []).append(value)
    return result


def build() -> dict[str, Any]:
    rows = load_catalog()
    applicability = load_json(APPLICABILITY)
    cad = load_json(CAD)
    plant = load_json(PLANT)
    dropbear = load_json(DROPBEAR)
    require(
        applicability.get("schema_version")
        == "myactuator-protocol-applicability-registry/2",
        "protocol applicability registry version drift",
    )
    require(
        cad.get("schema_version") == "myactuator-cad-runtime-asset-registry/1",
        "CAD runtime registry version drift",
    )
    require(
        plant.get("schema_version") == "myactuator-plant-registry/4",
        "plant runtime registry version drift",
    )
    require(
        dropbear.get("schema_version")
        == "dropbear-graph-lifecycle-projection/2"
        and dropbear.get("view_kind") == "simulator",
        "Dropbear simulator projection version/view drift",
    )

    catalog_identities = [(row["series"], row["model"]) for row in rows]
    applicability_models = {
        (item["series"], item["model"]): item
        for item in applicability["models"]
    }
    cad_models = {
        (item["series"], item["model"]): item for item in cad["models"]
    }
    plant_models = {
        (item["series"], item["model"]): item
        for item in plant["model_coverage"]
    }
    require(
        set(catalog_identities)
        == set(applicability_models)
        == set(cad_models)
        == set(plant_models),
        "catalog/applicability/CAD/plant model identity join is not exact",
    )
    configurations = _by_identity(cad["configurations"])
    variants = _by_identity(cad["source_variants"])
    backend_by_parameter = {
        item["parameter_set_id"]: item["backend_id"]
        for item in plant["backends"]
        if item["kind"] == "actuator_plant"
    }

    models: list[dict[str, Any]] = []
    for row in rows:
        identity = (row["series"], row["model"])
        cad_model = cad_models[identity]
        applicability_model = applicability_models[identity]
        plant_model = plant_models[identity]
        model_configurations = configurations.get(identity, [])
        model_variants = variants.get(identity, [])
        require(model_configurations, f"{identity}: no CAD configuration")
        require(model_variants, f"{identity}: no source STEP variant")
        configuration_ids = [
            item["configuration_id"] for item in model_configurations
        ]
        variant_ids = [item["variant_id"] for item in model_variants]
        require(
            configuration_ids == cad_model["configuration_ids"],
            f"{identity}: CAD model/configuration ordering drift",
        )
        accepted = [
            item
            for item in model_configurations
            if item["review_status"]
            in {"accepted_local", "accepted_redistributable"}
        ]
        local = [
            item for item in model_configurations
            if item["local_runtime_loadable"]
        ]
        browser = [
            item for item in model_configurations if item["browser_loadable"]
        ]
        candidates = sum(
            len(item["candidate_reports"]) for item in model_configurations
        )
        geometry_ready = bool(local)
        sourced_plant_evidence = bool(plant_model["plant_ids"])
        physically_correlated = plant_model["status"] == "validated"
        protocol_verified = (
            applicability_model["applicability_status"] == "accepted"
            and bool(applicability_model["accepted_decision_ids"])
        )
        admitted_backends = sorted(
            backend_by_parameter[plant_id]
            for plant_id in plant_model["plant_ids"]
            if geometry_ready and plant_id in backend_by_parameter
        )
        plant_ready = bool(admitted_backends)
        blockers: list[str] = []
        if not protocol_verified:
            blockers.append("protocol_model_firmware_applicability_unverified")
        if not geometry_ready:
            blockers.append("accepted_articulated_cad_missing")
        if not sourced_plant_evidence:
            blockers.append("sourced_exact_tuple_plant_missing")
        elif not plant_ready:
            blockers.append("runtime_plant_adapter_missing")
        if not physically_correlated:
            blockers.append("physical_plant_correlation_missing")
        models.append(
            {
                "model_key": model_key(*identity),
                "series": row["series"],
                "model": row["model"],
                "package_revision": row["package_revision"],
                "configuration_ids": configuration_ids,
                "source_variant_ids": variant_ids,
                "source_step_evidence_present": all(
                    len(item["step_sha256"]) == 64 for item in model_variants
                ),
                "source_step_runtime_asset": False,
                "cad": {
                    "review_status": cad_model["review_status"],
                    "accepted_configuration_count": len(accepted),
                    "local_runtime_loadable_configuration_count": len(local),
                    "browser_loadable_configuration_count": len(browser),
                    "candidate_report_count": candidates,
                },
                "plant": {
                    "status": plant_model["status"],
                    "plant_ids": plant_model["plant_ids"],
                },
                "protocol_model_firmware_applicability_verified": protocol_verified,
                "fidelity": {
                    "exact_model_geometry_ready": geometry_ready,
                    "exact_model_plant_ready": plant_ready,
                    "physically_correlated_plant_ready": physically_correlated,
                    "exact_model_simulation_ready": (
                        geometry_ready and plant_ready
                    ),
                    "browser_articulated_asset_ready": bool(browser),
                },
                "admitted_exact_model_backend_ids": admitted_backends,
                "blockers": blockers,
            }
        )

    lifecycle = dropbear["lifecycle"]
    graph = dropbear["graph_summary"]
    outputs = dropbear["outputs"]
    whole_graph = (
        lifecycle["source_active_state"] == "accepted"
        and lifecycle["graph_active_state"] == "accepted"
        and graph["canonical_graph_count"] == 1
        and graph["actuator_mapping_count"] == 12
        and graph["ros_mapping_count"] == 12
    )
    whole_cad = cad["summary"]["dropbear_bound_cad_assets"] > 0
    whole_plant = outputs["physical_plant_count"] > 0
    whole_runtime = whole_graph and whole_cad and whole_plant
    dropbear_blockers = list(dropbear["blockers"])
    for blocker, ready in (
        ("canonical_dropbear_graph_and_mappings_missing", whole_graph),
        ("dropbear_cad_bindings_missing", whole_cad),
        ("dropbear_physical_plant_bindings_missing", whole_plant),
    ):
        if not ready and blocker not in dropbear_blockers:
            dropbear_blockers.append(blocker)

    backends = [_backend_profile(value) for value in plant["backends"]]
    value = {
        "schema_version": VERSION,
        "artifact_id": "myactuator-simulator-runtime-catalog",
        "authority": "derived_runtime_admission_only",
        "sources": {
            "catalog_sha256": sha_file(CATALOG),
            "protocol_applicability_registry_sha256": sha_file(APPLICABILITY),
            "cad_runtime_registry_sha256": sha_file(CAD),
            "plant_runtime_registry_sha256": sha_file(PLANT),
            "dropbear_simulator_projection_sha256": sha_file(DROPBEAR),
            "source_registry_generation_sha256": dropbear["subject"][
                "source_registry_generation_sha256"
            ],
            "graph_registry_generation_sha256": dropbear["subject"][
                "graph_registry_generation_sha256"
            ],
        },
        "policy": {
            "exact_model_and_configuration_required": True,
            "backend_kind_and_use_case_required": True,
            "source_step_is_never_runtime_geometry": True,
            "candidate_is_never_runtime_geometry": True,
            "synthetic_execution_is_never_model_fidelity": True,
            "protocol_emulation_is_never_plant_fidelity": True,
            "replay_is_read_only": True,
            "whole_robot_requires_active_graph_cad_and_plant": True,
            "generation_rechecked_at_every_use": True,
            "browser_projection_contains_no_paths": True,
            "simulator_never_grants_hardware_support": True,
        },
        "summary": {
            "model_count": len(models),
            "source_variant_count": sum(
                len(item["source_variant_ids"]) for item in models
            ),
            "geometry_configuration_count": sum(
                len(item["configuration_ids"]) for item in models
            ),
            "backend_descriptor_count": len(backends),
            "runtime_loadable_backend_count": sum(
                item["runtime_loadable"] for item in backends
            ),
            "exact_model_geometry_ready_count": sum(
                item["fidelity"]["exact_model_geometry_ready"]
                for item in models
            ),
            "exact_model_plant_ready_count": sum(
                item["fidelity"]["exact_model_plant_ready"] for item in models
            ),
            "exact_model_simulation_ready_count": sum(
                item["fidelity"]["exact_model_simulation_ready"]
                for item in models
            ),
            "physically_correlated_plant_count": sum(
                item["fidelity"]["physically_correlated_plant_ready"]
                for item in models
            ),
            "browser_articulated_asset_ready_count": sum(
                item["fidelity"]["browser_articulated_asset_ready"]
                for item in models
            ),
            "dropbear_whole_robot_ready_count": int(whole_runtime),
        },
        "backends": backends,
        "models": models,
        "dropbear": {
            "canonical_configuration_digest": dropbear["subject"][
                "canonical_configuration_digest"
            ],
            "source_active_state": lifecycle["source_active_state"],
            "graph_active_state": lifecycle["graph_active_state"],
            "canonical_graph_count": graph["canonical_graph_count"],
            "actuator_mapping_count": graph["actuator_mapping_count"],
            "ros_mapping_count": graph["ros_mapping_count"],
            "frame_count": graph["frame_count"],
            "physical_plant_count": outputs["physical_plant_count"],
            "bound_cad_asset_count": cad["summary"][
                "dropbear_bound_cad_assets"
            ],
            "whole_robot_graph_ready": whole_graph,
            "whole_robot_cad_ready": whole_cad,
            "whole_robot_plant_ready": whole_plant,
            "whole_robot_runtime_ready": whole_runtime,
            "blockers": dropbear_blockers,
        },
        "support_granted": False,
        "physical_motion_authority": False,
        "physical_io_enabled": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(value)
    validate(value)
    return value


def _schema_validate(value: dict[str, Any]) -> None:
    schema = load_json(SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise SimulatorCatalogError(
            "simulator catalog schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def _iter_items(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from _iter_items(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_items(item)


def validate(
    value: dict[str, Any],
    *,
    verify_sources: bool = True,
) -> None:
    _schema_validate(value)
    require(
        value["integrity"]["record_sha256"] == sha_bytes(digest_payload(value)),
        "simulator catalog record digest mismatch",
    )
    require(
        not value["support_granted"]
        and not value["physical_motion_authority"]
        and not value["physical_io_enabled"],
        "simulator catalog grants hardware authority",
    )
    if verify_sources:
        expected = {
            "catalog_sha256": sha_file(CATALOG),
            "cad_runtime_registry_sha256": sha_file(CAD),
            "plant_runtime_registry_sha256": sha_file(PLANT),
            "dropbear_simulator_projection_sha256": sha_file(DROPBEAR),
        }
        require(
            all(value["sources"][name] == digest for name, digest in expected.items()),
            "simulator catalog source hash drift",
        )
        projection = load_json(DROPBEAR)
        require(
            value["sources"]["source_registry_generation_sha256"]
            == projection["subject"]["source_registry_generation_sha256"]
            and value["sources"]["graph_registry_generation_sha256"]
            == projection["subject"]["graph_registry_generation_sha256"],
            "simulator catalog authority generation drift",
        )

    rows = load_catalog()
    expected_identities = [(row["series"], row["model"]) for row in rows]
    actual_identities = [
        (item["series"], item["model"]) for item in value["models"]
    ]
    require(
        actual_identities == expected_identities,
        "simulator model coverage/order differs from catalog",
    )
    require(
        len({item["model_key"] for item in value["models"]}) == 44
        and all(
            item["model_key"] == model_key(item["series"], item["model"])
            for item in value["models"]
        ),
        "simulator model keys are not exact and unique",
    )
    all_configurations = [
        identifier
        for item in value["models"]
        for identifier in item["configuration_ids"]
    ]
    all_variants = [
        identifier
        for item in value["models"]
        for identifier in item["source_variant_ids"]
    ]
    require(
        len(all_configurations)
        == len(set(all_configurations))
        == value["summary"]["geometry_configuration_count"]
        == 53,
        "simulator configuration coverage is not exact",
    )
    require(
        len(all_variants)
        == len(set(all_variants))
        == value["summary"]["source_variant_count"]
        == 53,
        "simulator source-variant coverage is not exact",
    )
    backends = value["backends"]
    require(
        len({item["backend_id"] for item in backends}) == len(backends)
        == value["summary"]["backend_descriptor_count"],
        "simulator backend identity/count drift",
    )
    require(
        value["summary"]["runtime_loadable_backend_count"]
        == sum(item["runtime_loadable"] for item in backends),
        "simulator loadable-backend summary drift",
    )
    fields = (
        ("exact_model_geometry_ready_count", "exact_model_geometry_ready"),
        ("exact_model_plant_ready_count", "exact_model_plant_ready"),
        ("exact_model_simulation_ready_count", "exact_model_simulation_ready"),
        (
            "physically_correlated_plant_count",
            "physically_correlated_plant_ready",
        ),
        (
            "browser_articulated_asset_ready_count",
            "browser_articulated_asset_ready",
        ),
    )
    for summary_name, fidelity_name in fields:
        require(
            value["summary"][summary_name]
            == sum(
                item["fidelity"][fidelity_name] for item in value["models"]
            ),
            f"simulator {summary_name} drift",
        )
    for item in value["models"]:
        fidelity = item["fidelity"]
        require(
            fidelity["exact_model_simulation_ready"]
            is (
                fidelity["exact_model_geometry_ready"]
                and fidelity["exact_model_plant_ready"]
            ),
            f"{item['model_key']}: exact simulation readiness lie",
        )
        require(
            not item["source_step_runtime_asset"],
            f"{item['model_key']}: source STEP promoted to runtime geometry",
        )
        if item["admitted_exact_model_backend_ids"]:
            require(
                fidelity["exact_model_simulation_ready"],
                f"{item['model_key']}: backend admitted without exact fidelity",
            )
    dropbear = value["dropbear"]
    require(
        dropbear["whole_robot_runtime_ready"]
        is (
            dropbear["whole_robot_graph_ready"]
            and dropbear["whole_robot_cad_ready"]
            and dropbear["whole_robot_plant_ready"]
        )
        and value["summary"]["dropbear_whole_robot_ready_count"]
        == int(dropbear["whole_robot_runtime_ready"]),
        "Dropbear whole-robot readiness relation drift",
    )
    for key, item in _iter_items(value):
        folded = key.casefold()
        require(
            not (
                isinstance(item, (str, list, dict))
                and (
                    folded.endswith("_path")
                    or folded.endswith("_paths")
                    or folded.endswith("_url")
                    or folded.endswith("_urls")
                    or "locator" in folded
                )
            ),
            f"browser-safe simulator catalog contains path-like field: {key}",
        )
        if isinstance(item, str):
            require(
                "/home/" not in item
                and "file://" not in item
                and "www.myactuator.com" not in item,
                "browser-safe simulator catalog contains a local/source path",
            )


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def write(value: dict[str, Any]) -> None:
    data = canonical_bytes(value)
    atomic_write(OUTPUT, data)
    atomic_write(WEB_OUTPUT, data)


def check(value: dict[str, Any]) -> None:
    data = canonical_bytes(value)
    require(
        OUTPUT.is_file() and OUTPUT.read_bytes() == data,
        "generated simulator runtime catalog drift",
    )
    require(
        WEB_OUTPUT.is_file() and WEB_OUTPUT.read_bytes() == data,
        "browser simulator runtime catalog drift",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    value = build()
    write(value) if args.write else check(value)
    summary = value["summary"]
    print(
        "SIMULATOR_RUNTIME_CATALOG_OK "
        f"models={summary['model_count']} "
        f"variants={summary['source_variant_count']} "
        f"configs={summary['geometry_configuration_count']} "
        f"backends={summary['backend_descriptor_count']} "
        f"exact_ready={summary['exact_model_simulation_ready_count']} "
        f"dropbear_ready={summary['dropbear_whole_robot_ready_count']} "
        "support=false motion=false physical_io=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        KeyError,
        OSError,
        SimulatorCatalogError,
        TypeError,
        ValueError,
    ) as error:
        print(f"Simulator runtime catalog failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
