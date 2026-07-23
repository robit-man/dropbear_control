#!/usr/bin/env python3
"""Generate reviewed exact sourced-plant contracts for the V2 plant core."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "host"))

from tools import generate_plant_runtime_adapters as v1_generator
from myactuator_lib import plant_runtime_adapter_v2 as adapter


CATALOG = v1_generator.CATALOG
PARAMETER_SET_REGISTRY = v1_generator.PARAMETER_SET_REGISTRY
PARAMETER_SET_DIRECTORY = v1_generator.PARAMETER_SET_DIRECTORY
PROFILE_DIRECTORY = ROOT / "assets/myactuator/plant_runtime_profiles_v2"
PROFILE_SCHEMA = (
    ROOT / "schemas/myactuator-plant-runtime-profile-v2.schema.json"
)
REGISTRY_SCHEMA = (
    ROOT
    / "schemas/myactuator-plant-runtime-adapter-registry-v2.schema.json"
)
ADAPTER_IMPLEMENTATION = (
    ROOT / "host/myactuator_lib/plant_runtime_adapter_v2.py"
)
PLANT_IMPLEMENTATION = (
    ROOT / "host/myactuator_lib/actuator_plant_v2.py"
)
OUTPUT_ROOT = ROOT / "generated/myactuator/plant/runtime_adapters_v2"
OUTPUT_REGISTRY = OUTPUT_ROOT / "registry.json"
OUTPUT_CONTRACT_DIRECTORY = OUTPUT_ROOT / "contracts"
VERSION = "myactuator-plant-runtime-adapter-registry/2"

POLICY = {
    "generated_source_set_required": True,
    "accepted_exact_execution_profile_required": True,
    "all_38_source_semantics_represented": True,
    "directional_efficiency_never_averaged": True,
    "peak_recovery_never_invented": True,
    "solver_and_scenario_choices_explicit": True,
    "source_facts_never_rewritten": True,
    "no_family_default_or_profile_fallback": True,
    "adapter_never_grants_support_motion_or_physical_validation": True,
}
LIMITATIONS = [
    "source-only offline SIL is not physical validation or motor support",
    "state sample period must not be faster than the current-loop solver period",
    "delay-jitter routing requires an independently reviewed execution choice",
    "peak torque is one-shot per reset because no recovery fact is sourced",
    "linear interpolation does not model unreviewed internal sensor dynamics",
    "bit-exact noise traces are bound to the pinned Python floating-point runtime",
    "scenario bounds damping controller gain and two derate thresholds require independent review",
]


class PlantRuntimeAdapterV2RegistryError(ValueError):
    """A V2 profile, contract, source, or registry invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PlantRuntimeAdapterV2RegistryError(message)


canonical_json = v1_generator.canonical_json
canonical_bytes = v1_generator.canonical_bytes
sha_bytes = v1_generator.sha_bytes
sha_file = v1_generator.sha_file
load_json = v1_generator.load_json
schema_validate = v1_generator.schema_validate
model_key = v1_generator.model_key
load_catalog = v1_generator.load_catalog
load_verified_parameter_sets = v1_generator.load_verified_parameter_sets


def digest_payload(value: Mapping[str, Any]) -> bytes:
    payload = copy.deepcopy(dict(value))
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def validate_digest(value: Mapping[str, Any], context: str) -> None:
    require(
        isinstance(value.get("integrity"), Mapping)
        and value["integrity"].get("record_sha256")
        == sha_bytes(digest_payload(value)),
        f"{context}: integrity digest drift",
    )


def profile_id_for(subject: Mapping[str, Any]) -> str:
    return "plantprofilev2-" + sha_bytes(
        canonical_bytes(subject)
    )[:20]


def load_profiles(
    directory: Path = PROFILE_DIRECTORY,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    schema = load_json(PROFILE_SCHEMA)
    allowed_non_json = {"README.md"}
    foreign = sorted(
        path.name
        for path in directory.iterdir()
        if path.is_file()
        and path.suffix != ".json"
        and path.name not in allowed_non_json
    )
    require(
        not foreign,
        f"{directory}: foreign files are forbidden: {foreign}",
    )
    profiles: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for path in sorted(directory.glob("*.json")):
        value = load_json(path)
        schema_validate(value, schema, str(path))
        validate_digest(value, str(path))
        identifier = value["profile_id"]
        require(
            identifier == profile_id_for(value["subject"]),
            f"{path}: V2 profile ID/subject drift",
        )
        require(
            identifier not in profiles and path.stem == identifier,
            f"{path}: duplicate or filename/profile ID drift",
        )
        require(
            path.read_text(encoding="utf-8") == canonical_json(value),
            f"{path}: V2 profile JSON is not canonical",
        )
        profiles[identifier] = value
        hashes[identifier] = sha_file(path)
    return profiles, hashes


def build_from_inputs(
    *,
    catalog: list[dict[str, str]],
    parameter_registry: Mapping[str, Any],
    parameter_sets: Mapping[str, Mapping[str, Any]],
    parameter_hashes: Mapping[str, str],
    profiles: Mapping[str, Mapping[str, Any]],
    profile_hashes: Mapping[str, str],
    sources: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    require(
        set(parameter_sets) == set(parameter_hashes),
        "V2 parameter-set/hash key drift",
    )
    require(
        set(profiles) == set(profile_hashes),
        "V2 profile/hash key drift",
    )
    by_plant: dict[
        str,
        list[tuple[str, Mapping[str, Any]]],
    ] = defaultdict(list)
    for identifier, profile in profiles.items():
        require(
            identifier == profile_id_for(profile["subject"]),
            f"{identifier}: V2 profile ID/subject drift",
        )
        plant_id = profile["subject"]["plant_id"]
        require(
            plant_id in parameter_sets,
            f"{identifier}: exact source plant is unavailable",
        )
        by_plant[plant_id].append((identifier, profile))
    for plant_id, items in by_plant.items():
        require(
            len(items) == 1,
            f"{plant_id}: multiple active V2 profiles are forbidden",
        )

    contracts: dict[str, dict[str, Any]] = {}
    entries: list[dict[str, Any]] = []
    runtime_by_plant: dict[str, str] = {}
    for plant_id in sorted(parameter_sets):
        items = by_plant.get(plant_id, [])
        if not items:
            continue
        profile_id, profile = items[0]
        try:
            contract = adapter.adapt(
                parameter_sets[plant_id],
                profile,
                parameter_set_sha256=parameter_hashes[plant_id],
                profile_sha256=profile_hashes[profile_id],
                adapter_implementation_sha256=sources[
                    "adapter_implementation_sha256"
                ],
                plant_implementation_sha256=sources[
                    "plant_implementation_sha256"
                ],
                profile_schema_sha256=sources[
                    "profile_schema_sha256"
                ],
            )
        except adapter.PlantRuntimeAdapterV2Error as error:
            raise PlantRuntimeAdapterV2RegistryError(
                f"{profile_id}: {error}"
            ) from error
        contract_id = contract["contract_id"]
        require(
            contract_id not in contracts
            and plant_id not in runtime_by_plant,
            "V2 runtime contract identity collision",
        )
        contracts[contract_id] = contract
        runtime_by_plant[plant_id] = contract_id
        entries.append(
            {
                "contract_id": contract_id,
                "plant_id": plant_id,
                "backend_id": contract["backend_id"],
                "profile_id": profile_id,
                "contract_path": f"contracts/{contract_id}.json",
                "contract_sha256": sha_bytes(
                    canonical_json(contract).encode("utf-8")
                ),
                "parameter_set_sha256": parameter_hashes[plant_id],
            }
        )

    plant_by_model: dict[tuple[str, str], list[str]] = defaultdict(list)
    for plant_id, item in parameter_sets.items():
        applicability = item["applicability"]
        plant_by_model[
            (applicability["series"], applicability["model"])
        ].append(plant_id)
    coverage: list[dict[str, Any]] = []
    for row in catalog:
        identity = (row["series"], row["model"])
        plant_ids = sorted(plant_by_model.get(identity, []))
        runtime_ids = sorted(
            runtime_by_plant[plant_id]
            for plant_id in plant_ids
            if plant_id in runtime_by_plant
        )
        loadable = sorted(
            plant_id
            for plant_id in plant_ids
            if plant_id in runtime_by_plant
        )
        blockers: list[str] = []
        if not plant_ids:
            blockers.append("sourced_exact_tuple_plant_missing")
        elif not loadable:
            blockers.append(
                "accepted_runtime_execution_profile_v2_missing"
            )
        coverage.append(
            {
                "model_key": model_key(*identity),
                "series": row["series"],
                "model": row["model"],
                "source_plant_ids": plant_ids,
                "runtime_contract_ids": runtime_ids,
                "runtime_loadable_plant_ids": loadable,
                "blockers": blockers,
            }
        )

    runtime_model_count = sum(
        bool(item["runtime_loadable_plant_ids"]) for item in coverage
    )
    registry = {
        "schema_version": VERSION,
        "artifact_id": "myactuator-plant-runtime-adapter-registry-v2",
        "authority": "derived_runtime_adapter_admission_only",
        "sources": {
            "catalog_sha256": sources["catalog_sha256"],
            "parameter_set_registry_sha256": sources[
                "parameter_set_registry_sha256"
            ],
            "parameter_set_registry_generation_sha256": parameter_registry[
                "registry_generation_sha256"
            ],
            "adapter_implementation_sha256": sources[
                "adapter_implementation_sha256"
            ],
            "plant_implementation_sha256": sources[
                "plant_implementation_sha256"
            ],
            "profile_schema_sha256": sources[
                "profile_schema_sha256"
            ],
            "profile_sha256": dict(sorted(profile_hashes.items())),
        },
        "policy": dict(POLICY),
        "adapter": {
            "adapter_id": adapter.ADAPTER_ID,
            "solver_id": adapter.SOLVER_ID,
            "noise_algorithm": adapter.NOISE_ALGORITHM,
            "jitter_algorithm": adapter.JITTER_ALGORITHM,
            "source_semantic_count": len(adapter.ALL_SOURCE_FIELDS),
            "torque_regimes": [
                "continuous_only",
                "peak_one_shot_per_reset",
            ],
            "physical_io": False,
            "limitations": LIMITATIONS,
        },
        "model_coverage": coverage,
        "contracts": sorted(
            entries,
            key=lambda item: item["contract_id"],
        ),
        "summary": {
            "model_count": len(coverage),
            "source_parameter_set_count": len(parameter_sets),
            "profile_submission_count": len(profiles),
            "runtime_contract_count": len(contracts),
            "runtime_loadable_parameter_set_count": len(runtime_by_plant),
            "runtime_loadable_model_count": runtime_model_count,
            "physically_validated_contract_count": 0,
        },
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(registry)
    validate(
        registry,
        contracts,
        parameter_sets=parameter_sets,
        parameter_hashes=parameter_hashes,
        profiles=profiles,
        profile_hashes=profile_hashes,
        catalog=catalog,
        verify_sources=False,
    )
    return registry, contracts


def build() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    catalog = load_catalog()
    parameter_registry, parameter_sets, parameter_hashes = (
        load_verified_parameter_sets()
    )
    profiles, profile_hashes = load_profiles()
    sources = {
        "catalog_sha256": sha_file(CATALOG),
        "parameter_set_registry_sha256": sha_file(
            PARAMETER_SET_REGISTRY
        ),
        "adapter_implementation_sha256": sha_file(
            ADAPTER_IMPLEMENTATION
        ),
        "plant_implementation_sha256": sha_file(PLANT_IMPLEMENTATION),
        "profile_schema_sha256": sha_file(PROFILE_SCHEMA),
    }
    return build_from_inputs(
        catalog=catalog,
        parameter_registry=parameter_registry,
        parameter_sets=parameter_sets,
        parameter_hashes=parameter_hashes,
        profiles=profiles,
        profile_hashes=profile_hashes,
        sources=sources,
    )


def validate(
    registry: Mapping[str, Any],
    contracts: Mapping[str, Mapping[str, Any]],
    *,
    parameter_sets: Mapping[str, Mapping[str, Any]],
    parameter_hashes: Mapping[str, str],
    profiles: Mapping[str, Mapping[str, Any]],
    profile_hashes: Mapping[str, str],
    catalog: list[dict[str, str]],
    verify_sources: bool,
) -> None:
    schema_validate(
        registry,
        load_json(REGISTRY_SCHEMA),
        "V2 runtime-adapter registry",
    )
    validate_digest(registry, "V2 runtime-adapter registry")
    require(
        registry["policy"] == POLICY
        and registry["support_granted"] is False
        and registry["physical_motion_authority"] is False,
        "V2 runtime-adapter policy/authority drift",
    )
    require(
        registry["adapter"]["source_semantic_count"]
        == len(adapter.ALL_SOURCE_FIELDS)
        == 38
        and registry["adapter"]["limitations"] == LIMITATIONS,
        "V2 runtime-adapter descriptor drift",
    )
    expected_models = [
        (
            model_key(row["series"], row["model"]),
            row["series"],
            row["model"],
        )
        for row in catalog
    ]
    actual_models = [
        (item["model_key"], item["series"], item["model"])
        for item in registry["model_coverage"]
    ]
    require(
        actual_models == expected_models,
        "V2 runtime-adapter model coverage/order drift",
    )
    entries = registry["contracts"]
    require(
        len(entries)
        == len(contracts)
        == len({item["contract_id"] for item in entries})
        == len({item["plant_id"] for item in entries}),
        "V2 runtime contract count/identity drift",
    )
    entry_by_id = {item["contract_id"]: item for item in entries}
    for contract_id, contract in contracts.items():
        require(
            contract_id in entry_by_id,
            f"{contract_id}: V2 contract is absent from registry",
        )
        entry = entry_by_id[contract_id]
        executable = adapter.load_contract(contract)
        require(
            executable.contract_id == contract_id
            and executable.plant_id == entry["plant_id"]
            and executable.backend_id == entry["backend_id"],
            f"{contract_id}: typed V2 contract identity drift",
        )
        require(
            sha_bytes(canonical_json(contract).encode("utf-8"))
            == entry["contract_sha256"]
            and parameter_hashes[entry["plant_id"]]
            == entry["parameter_set_sha256"],
            f"{contract_id}: V2 contract/parameter hash drift",
        )
        profile_id = entry["profile_id"]
        require(
            profile_id in profiles
            and profile_hashes[profile_id]
            == contract["source_bindings"]["profile_sha256"],
            f"{contract_id}: V2 profile binding drift",
        )
        expected = adapter.adapt(
            parameter_sets[entry["plant_id"]],
            profiles[profile_id],
            parameter_set_sha256=parameter_hashes[entry["plant_id"]],
            profile_sha256=profile_hashes[profile_id],
            adapter_implementation_sha256=registry["sources"][
                "adapter_implementation_sha256"
            ],
            plant_implementation_sha256=registry["sources"][
                "plant_implementation_sha256"
            ],
            profile_schema_sha256=registry["sources"][
                "profile_schema_sha256"
            ],
        )
        require(
            canonical_json(expected) == canonical_json(contract),
            f"{contract_id}: V2 adapter replay drift",
        )
    summary = registry["summary"]
    runtime_plants = {item["plant_id"] for item in entries}
    runtime_models = sum(
        bool(item["runtime_loadable_plant_ids"])
        for item in registry["model_coverage"]
    )
    require(
        summary
        == {
            "model_count": 44,
            "source_parameter_set_count": len(parameter_sets),
            "profile_submission_count": len(profiles),
            "runtime_contract_count": len(contracts),
            "runtime_loadable_parameter_set_count": len(runtime_plants),
            "runtime_loadable_model_count": runtime_models,
            "physically_validated_contract_count": 0,
        },
        "V2 runtime-adapter summary drift",
    )
    covered_source = {
        plant_id
        for item in registry["model_coverage"]
        for plant_id in item["source_plant_ids"]
    }
    covered_runtime = {
        plant_id
        for item in registry["model_coverage"]
        for plant_id in item["runtime_loadable_plant_ids"]
    }
    require(
        covered_source == set(parameter_sets)
        and covered_runtime == runtime_plants,
        "V2 runtime-adapter model/plant partition drift",
    )
    if verify_sources:
        require(
            registry["sources"]["catalog_sha256"] == sha_file(CATALOG)
            and registry["sources"]["parameter_set_registry_sha256"]
            == sha_file(PARAMETER_SET_REGISTRY)
            and registry["sources"]["adapter_implementation_sha256"]
            == sha_file(ADAPTER_IMPLEMENTATION)
            and registry["sources"]["plant_implementation_sha256"]
            == sha_file(PLANT_IMPLEMENTATION)
            and registry["sources"]["profile_schema_sha256"]
            == sha_file(PROFILE_SCHEMA),
            "V2 runtime-adapter source digest drift",
        )


def _transactional_write(
    registry: Mapping[str, Any],
    contracts: Mapping[str, Mapping[str, Any]],
) -> None:
    OUTPUT_ROOT.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=OUTPUT_ROOT.name + ".",
            dir=OUTPUT_ROOT.parent,
        )
    )
    try:
        (temporary / "contracts").mkdir()
        (temporary / "registry.json").write_text(
            canonical_json(registry),
            encoding="utf-8",
            newline="\n",
        )
        for identifier, contract in sorted(contracts.items()):
            (temporary / "contracts" / f"{identifier}.json").write_text(
                canonical_json(contract),
                encoding="utf-8",
                newline="\n",
            )
        backup = OUTPUT_ROOT.with_name(OUTPUT_ROOT.name + ".previous")
        if backup.exists():
            shutil.rmtree(backup)
        if OUTPUT_ROOT.exists():
            os.replace(OUTPUT_ROOT, backup)
        os.replace(temporary, OUTPUT_ROOT)
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def check(
    registry: Mapping[str, Any],
    contracts: Mapping[str, Mapping[str, Any]],
) -> None:
    require(
        OUTPUT_REGISTRY.is_file()
        and OUTPUT_REGISTRY.read_text(encoding="utf-8")
        == canonical_json(registry),
        "V2 runtime-adapter registry drift",
    )
    paths = (
        {
            path.stem: path
            for path in OUTPUT_CONTRACT_DIRECTORY.glob("*.json")
        }
        if OUTPUT_CONTRACT_DIRECTORY.is_dir()
        else {}
    )
    require(
        set(paths) == set(contracts),
        "V2 runtime-adapter contract file set drift",
    )
    for identifier, contract in contracts.items():
        require(
            paths[identifier].read_text(encoding="utf-8")
            == canonical_json(contract),
            f"{identifier}: V2 runtime contract drift",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        registry, contracts = build()
        if arguments.write:
            _transactional_write(registry, contracts)
        else:
            check(registry, contracts)
        summary = registry["summary"]
        print(
            "PLANT_RUNTIME_ADAPTER_V2_OK "
            f"models={summary['model_count']} "
            f"source_sets={summary['source_parameter_set_count']} "
            f"profiles={summary['profile_submission_count']} "
            f"contracts={summary['runtime_contract_count']} "
            f"loadable={summary['runtime_loadable_parameter_set_count']} "
            "physical=0 motion=false"
        )
        return 0
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        PlantRuntimeAdapterV2RegistryError,
        adapter.PlantRuntimeAdapterV2Error,
    ) as error:
        print(f"PLANT_RUNTIME_ADAPTER_V2_ERROR {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
