#!/usr/bin/env python3
"""Build and validate the sourced-plant and typed-backend registry."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "assets/myactuator/catalog.tsv"
PARAMETER_SET_REGISTRY = (
    ROOT / "generated/myactuator/plant/parameter_sets/registry.json"
)
PARAMETER_DIRECTORY = (
    ROOT / "generated/myactuator/plant/parameter_sets/sets"
)
RUNTIME_ADAPTER_REGISTRY = (
    ROOT / "generated/myactuator/plant/runtime_adapters/registry.json"
)
RUNTIME_CONTRACT_DIRECTORY = (
    ROOT / "generated/myactuator/plant/runtime_adapters/contracts"
)
RUNTIME_ADAPTER_V2_REGISTRY = (
    ROOT / "generated/myactuator/plant/runtime_adapters_v2/registry.json"
)
RUNTIME_CONTRACT_V2_DIRECTORY = (
    ROOT / "generated/myactuator/plant/runtime_adapters_v2/contracts"
)
SCHEMA = ROOT / "schemas/myactuator-plant-registry.schema.json"
OUTPUT = ROOT / "generated/myactuator/plant/runtime_registry.json"
WEB_OUTPUT = ROOT / "web/js/plant_backends.generated.js"
VERSION = "myactuator-plant-registry/4"
EXACT_FORBIDDEN = re.compile(
    r"(?:^|[.\-_/])(?:all|any|default|latest|none|null|tbd|unknown|unspecified)(?:$|[.\-_/])",
    re.IGNORECASE,
)
X_VERSION = re.compile(r"(?:^|[.\-_/])x(?:$|[.\-_/])", re.IGNORECASE)

EXPECTED_UNITS = {
    "electrical": {
        "phase_resistance_ohm": "ohm",
        "phase_inductance_h": "H",
        "torque_constant_nm_per_a": "N*m/A",
        "back_emf_v_s_per_rad": "V*s/rad",
        "max_qaxis_current_a": "A",
    },
    "mechanical": {
        "rotor_inertia_kg_m2": "kg*m^2",
        "output_inertia_kg_m2": "kg*m^2",
        "coulomb_friction_nm": "N*m",
        "viscous_friction_nm_s_per_rad": "N*m*s/rad",
    },
    "transmission": {
        "ratio_motor_per_output": "1",
        "forward_efficiency_ratio": "1",
        "reverse_efficiency_ratio": "1",
        "torsional_stiffness_nm_per_rad": "N*m/rad",
        "backlash_rad": "rad",
    },
    "saturation": {
        "max_motor_speed_rad_s": "rad/s",
        "max_output_speed_rad_s": "rad/s",
        "max_continuous_output_torque_nm": "N*m",
        "max_peak_output_torque_nm": "N*m",
        "peak_duration_s": "s",
    },
    "thermal": {
        "winding_resistance_k_per_w": "K/W",
        "case_resistance_k_per_w": "K/W",
        "winding_heat_capacity_j_per_k": "J/K",
        "case_heat_capacity_j_per_k": "J/K",
        "max_winding_temperature_k": "K",
        "max_case_temperature_k": "K",
    },
    "sensor": {
        "position_quantization_rad": "rad",
        "position_noise_stddev_rad": "rad",
        "velocity_noise_stddev_rad_s": "rad/s",
        "current_noise_stddev_a": "A",
    },
    "latency": {
        "command_delay_s": "s",
        "current_loop_period_s": "s",
        "state_sample_period_s": "s",
        "feedback_delay_s": "s",
        "delay_jitter_s": "s",
    },
}
EXPECTED_ENVELOPE_UNITS = {
    "supply_voltage_v": "V",
    "ambient_temperature_k": "K",
    "output_speed_rad_s": "rad/s",
    "output_torque_nm": "N*m",
}
VALIDATION_FOR_STATUS = {
    "sourced": "source_only",
    "bench_calibrated": "bench_correlated",
    "hil_validated": "hil_correlated",
    "robot_validated": "robot_correlated",
}
BACKEND_EVIDENCE_FOR_STATUS = {
    "sourced": "sil-plant-sourced",
    "bench_calibrated": "sil-plant-bench-correlated",
    "hil_validated": "sil-plant-hil-correlated",
    "robot_validated": "sil-plant-hil-correlated",
}


class PlantRegistryError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PlantRegistryError(message)


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


def load_catalog() -> list[dict[str, str]]:
    with CATALOG.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    require(len(rows) == 44, "catalog must contain exactly 44 models")
    identities = [(row["series"], row["model"]) for row in rows]
    require(len(set(identities)) == len(identities), "catalog contains duplicate model identity")
    return rows


def _parameter_validator(schema: dict[str, Any]) -> Draft202012Validator:
    wrapper = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/parameterSet",
        "$defs": schema["$defs"],
    }
    return Draft202012Validator(wrapper, format_checker=FormatChecker())


def load_parameter_sets(schema: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    validator = _parameter_validator(schema)
    result: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for path in sorted(PARAMETER_DIRECTORY.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise PlantRegistryError(f"{path}: cannot load parameter set: {error}") from error
        errors = sorted(validator.iter_errors(item), key=lambda error: list(error.absolute_path))
        if errors:
            error = errors[0]
            location = "/".join(str(value) for value in error.absolute_path)
            raise PlantRegistryError(f"{path}:{location}: {error.message}")
        validate_parameter_set(item)
        require(path.stem == item["plant_id"], f"{path}: filename must equal plant_id")
        require(path.read_text(encoding="utf-8") == canonical_json(item), f"{path}: JSON is not canonical")
        result.append(item)
        hashes[item["plant_id"]] = sha256(path)
    return result, hashes


def load_parameter_set_registry() -> dict[str, Any]:
    try:
        value = json.loads(PARAMETER_SET_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PlantRegistryError(
            f"{PARAMETER_SET_REGISTRY}: cannot load assembly registry: {error}"
        ) from error
    require(
        isinstance(value, dict)
        and value.get("schema_version")
        == "myactuator-plant-parameter-set-registry/1"
        and value.get("artifact_id")
        == "myactuator-plant-parameter-set-registry",
        "parameter-set assembly registry identity drift",
    )
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    require(
        value["integrity"]["record_sha256"]
        == hashlib.sha256(
            (
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        ).hexdigest(),
        "parameter-set assembly registry digest drift",
    )
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False,
        "parameter-set assembly registry grants authority",
    )
    return value


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_runtime_adapter_registry() -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, str],
]:
    generator = _load_module(
        "plant_runtime_adapter_generator_for_plant_registry",
        ROOT / "tools/generate_plant_runtime_adapters.py",
    )
    expected_registry, expected_contracts = generator.build()
    actual_registry = json.loads(
        RUNTIME_ADAPTER_REGISTRY.read_text(encoding="utf-8")
    )
    require(
        canonical_json(actual_registry) == canonical_json(expected_registry),
        "runtime-adapter registry replay drift",
    )
    paths = {
        path.stem: path
        for path in sorted(RUNTIME_CONTRACT_DIRECTORY.glob("*.json"))
    }
    require(
        set(paths) == set(expected_contracts),
        "runtime contract file set drift",
    )
    contracts: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for identifier, expected in expected_contracts.items():
        actual = json.loads(paths[identifier].read_text(encoding="utf-8"))
        require(
            canonical_json(actual) == canonical_json(expected)
            and paths[identifier].read_text(encoding="utf-8")
            == canonical_json(actual),
            f"{identifier}: runtime contract replay/canonical drift",
        )
        contracts[identifier] = actual
        hashes[identifier] = sha256(paths[identifier])
    return actual_registry, contracts, hashes


def load_runtime_adapter_v2_registry() -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, str],
]:
    generator = _load_module(
        "plant_runtime_adapter_v2_generator_for_plant_registry",
        ROOT / "tools/generate_plant_runtime_adapters_v2.py",
    )
    expected_registry, expected_contracts = generator.build()
    actual_registry = json.loads(
        RUNTIME_ADAPTER_V2_REGISTRY.read_text(encoding="utf-8")
    )
    require(
        canonical_json(actual_registry) == canonical_json(expected_registry),
        "V2 runtime-adapter registry replay drift",
    )
    paths = {
        path.stem: path
        for path in sorted(RUNTIME_CONTRACT_V2_DIRECTORY.glob("*.json"))
    }
    require(
        set(paths) == set(expected_contracts),
        "V2 runtime contract file set drift",
    )
    contracts: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for identifier, expected in expected_contracts.items():
        actual = json.loads(paths[identifier].read_text(encoding="utf-8"))
        require(
            canonical_json(actual) == canonical_json(expected)
            and paths[identifier].read_text(encoding="utf-8")
            == canonical_json(actual),
            f"{identifier}: V2 runtime contract replay/canonical drift",
        )
        contracts[identifier] = actual
        hashes[identifier] = sha256(paths[identifier])
    return actual_registry, contracts, hashes


def _finite_number(value: Any, context: str) -> float:
    require(
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
        f"{context}: finite number required",
    )
    return float(value)


def _exact(value: Any, context: str, *, reject_x_version: bool = False) -> str:
    require(isinstance(value, str) and value == value.strip() and value, f"{context}: exact text required")
    require(not any(character in value for character in "*?[]{}"), f"{context}: wildcard syntax forbidden")
    require(
        value.casefold() != "current"
        and not EXACT_FORBIDDEN.search(value),
        f"{context}: non-exact value forbidden",
    )
    require(not reject_x_version or not X_VERSION.search(value), f"{context}: x-version wildcard forbidden")
    return value


def parameter_items(item: Mapping[str, Any]) -> Iterable[tuple[str, Mapping[str, Any], str]]:
    for group, fields in EXPECTED_UNITS.items():
        values = item["parameters"][group]
        for name, expected_unit in fields.items():
            yield f"parameters/{group}/{name}", values[name], expected_unit


def validate_parameter_set(item: Mapping[str, Any]) -> None:
    plant_id = item["plant_id"]
    require(
        (
            item["runtime_loadable"] is True
            and isinstance(item["runtime_adapter_id"], str)
            and isinstance(item["runtime_contract_id"], str)
        )
        or (
            item["runtime_loadable"] is False
            and item["runtime_adapter_id"] is None
            and item["runtime_contract_id"] is None
        ),
        f"{plant_id}: runtime-loadable/adapter/contract binding drift",
    )
    applicability = item["applicability"]
    for name, value in applicability.items():
        _exact(
            value,
            f"{plant_id}/applicability/{name}",
            reject_x_version=name in {"hardware_revision", "drive_firmware", "protocol_version"},
        )

    sources = {source["source_id"]: source for source in item["sources"]}
    require(len(sources) == len(item["sources"]), f"{plant_id}: duplicate source IDs")
    assembly = item["assembly"]
    fact_ids = assembly["source_fact_ids"]
    require(
        len(fact_ids) == len(set(fact_ids)) == 38
        and set(fact_ids) == set(assembly["source_fact_sha256"])
        and set(fact_ids) == set(sources),
        f"{plant_id}: assembly/source-fact closure drift",
    )
    require(
        assembly["assembly_registry_artifact_id"]
        == "myactuator-plant-parameter-set-registry"
        and assembly["physical_correlation_evidence_present"] is False
        and item["physical_motion_authority"] is False,
        f"{plant_id}: invalid assembly authority state",
    )
    require(
        all(source["kind"] == "reviewed_source_fact" for source in sources.values()),
        f"{plant_id}: source-only set must reference reviewed facts",
    )
    envelopes = {value["envelope_id"]: value for value in item["operating_envelopes"]}
    require(len(envelopes) == len(item["operating_envelopes"]), f"{plant_id}: duplicate envelope IDs")
    for envelope_id, envelope in envelopes.items():
        for name, expected_unit in EXPECTED_ENVELOPE_UNITS.items():
            value = envelope[name]
            require(value["unit"] == expected_unit, f"{plant_id}/{envelope_id}/{name}: expected SI unit {expected_unit}")
            minimum = _finite_number(value["minimum"], f"{plant_id}/{envelope_id}/{name}/minimum")
            maximum = _finite_number(value["maximum"], f"{plant_id}/{envelope_id}/{name}/maximum")
            require(minimum <= maximum, f"{plant_id}/{envelope_id}/{name}: inverted range")
            uncertainty = value["uncertainty"]
            lower = _finite_number(
                uncertainty["lower"],
                f"{plant_id}/{envelope_id}/{name}/uncertainty/lower",
            )
            upper = _finite_number(
                uncertainty["upper"],
                f"{plant_id}/{envelope_id}/{name}/uncertainty/upper",
            )
            require(
                lower <= minimum <= maximum <= upper
                and uncertainty["unit"] == expected_unit,
                f"{plant_id}/{envelope_id}/{name}: invalid uncertainty",
            )
            require(
                len(value["source_refs"]) == 1
                and set(value["source_refs"]) <= set(sources),
                f"{plant_id}/{envelope_id}/{name}: source reference drift",
            )

    for context, parameter, expected_unit in parameter_items(item):
        prefix = f"{plant_id}/{context}"
        value = _finite_number(parameter["value"], f"{prefix}/value")
        require(parameter["unit"] == expected_unit, f"{prefix}: expected SI unit {expected_unit}")
        uncertainty = parameter["uncertainty"]
        lower = _finite_number(uncertainty["lower"], f"{prefix}/uncertainty/lower")
        upper = _finite_number(uncertainty["upper"], f"{prefix}/uncertainty/upper")
        require(lower <= value <= upper, f"{prefix}: value must lie inside uncertainty interval")
        require(uncertainty["unit"] == expected_unit, f"{prefix}: uncertainty unit mismatch")
        require(set(parameter["source_refs"]) <= set(sources), f"{prefix}: unknown source reference")
        require(
            set(parameter["applicability_envelope_refs"]) <= set(envelopes),
            f"{prefix}: unknown operating-envelope reference",
        )
        require(value >= 0.0, f"{prefix}: negative parameter is invalid for this model form")

    transmission = item["parameters"]["transmission"]
    for name in ("forward_efficiency_ratio", "reverse_efficiency_ratio"):
        require(0.0 < transmission[name]["value"] <= 1.0, f"{plant_id}/{name}: efficiency outside (0,1]")
    require(transmission["ratio_motor_per_output"]["value"] > 0.0, f"{plant_id}: gear ratio must be positive")
    saturation = item["parameters"]["saturation"]
    require(
        saturation["max_peak_output_torque_nm"]["value"]
        >= saturation["max_continuous_output_torque_nm"]["value"],
        f"{plant_id}: peak torque is below continuous torque",
    )
    expected_validation = VALIDATION_FOR_STATUS[item["status"]]
    validation = item["validation"]
    require(validation["class"] == expected_validation, f"{plant_id}: status/validation-class mismatch")
    if item["status"] == "sourced":
        require(
            not validation["evidence_refs"]
            and not validation["scenario_ids"]
            and validation["validated_at_utc"] is None,
            f"{plant_id}: source-only set cannot claim physical validation",
        )
    else:
        require(
            validation["evidence_refs"]
            and validation["scenario_ids"]
            and validation["validated_at_utc"] is not None,
            f"{plant_id}: correlated set requires validation evidence, scenarios and time",
        )


def _base_backends() -> list[dict[str, Any]]:
    return [
        {
            "backend_id": "canonical-recorded-state-replay-v1",
            "kind": "recorded_replay",
            "evidence_class": "offline-replay",
            "runtime_loadable": True,
            "models_physical_dynamics": False,
            "physically_validated": False,
            "parameter_set_id": None,
            "runtime_contract_id": None,
            "substitution_scope": "host-state-replay-only",
        },
        {
            "backend_id": "rmd-v44-protocol-emulator",
            "kind": "protocol_emulator",
            "evidence_class": "sil-protocol",
            "runtime_loadable": True,
            "models_physical_dynamics": False,
            "physically_validated": False,
            "parameter_set_id": None,
            "runtime_contract_id": None,
            "substitution_scope": "native-protocol-only",
        },
        {
            "backend_id": "browser-toy-demo-v1",
            "kind": "toy_demo",
            "evidence_class": "synthetic-demo-no-physical-fidelity",
            "runtime_loadable": True,
            "models_physical_dynamics": False,
            "physically_validated": False,
            "parameter_set_id": None,
            "runtime_contract_id": None,
            "substitution_scope": "browser-visualization-only",
        },
        {
            "backend_id": "synthetic-electromechanical-fixed-step-v1",
            "kind": "synthetic_actuator_plant",
            "evidence_class": "synthetic-test-equations-no-real-parameter-fidelity",
            "runtime_loadable": True,
            "models_physical_dynamics": True,
            "physically_validated": False,
            "parameter_set_id": None,
            "runtime_contract_id": None,
            "substitution_scope": "offline-controller-and-sil-tests-only",
        },
        {
            "backend_id": "dropbear-rigid-body-unavailable-v1",
            "kind": "rigid_body",
            "evidence_class": "descriptor-only-no-canonical-graph-or-assets",
            "runtime_loadable": False,
            "models_physical_dynamics": False,
            "physically_validated": False,
            "parameter_set_id": None,
            "runtime_contract_id": None,
            "substitution_scope": "whole-robot-mechanics",
        },
    ]


def build_registry() -> dict[str, Any]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    catalog = load_catalog()
    parameter_set_registry = load_parameter_set_registry()
    source_parameter_sets, parameter_hashes = load_parameter_sets(schema)
    (
        runtime_adapter_v1_registry,
        runtime_contracts_v1,
        runtime_contract_hashes_v1,
    ) = load_runtime_adapter_registry()
    (
        runtime_adapter_v2_registry,
        runtime_contracts_v2,
        runtime_contract_hashes_v2,
    ) = load_runtime_adapter_v2_registry()
    for label, runtime_registry in (
        ("V1", runtime_adapter_v1_registry),
        ("V2", runtime_adapter_v2_registry),
    ):
        require(
            runtime_registry["sources"][
                "parameter_set_registry_sha256"
            ]
            == sha256(PARAMETER_SET_REGISTRY)
            and runtime_registry["sources"][
                "parameter_set_registry_generation_sha256"
            ]
            == parameter_set_registry["registry_generation_sha256"],
            f"{label} runtime-adapter/parameter-set registry binding drift",
        )
    runtime_contracts = {
        **runtime_contracts_v1,
        **runtime_contracts_v2,
    }
    runtime_contract_hashes = {
        **runtime_contract_hashes_v1,
        **runtime_contract_hashes_v2,
    }
    require(
        len(runtime_contracts)
        == len(runtime_contracts_v1) + len(runtime_contracts_v2)
        and len(runtime_contract_hashes)
        == len(runtime_contract_hashes_v1)
        + len(runtime_contract_hashes_v2),
        "runtime contract ID collision across adapter versions",
    )
    runtime_entries: dict[
        str,
        tuple[dict[str, Any], Mapping[str, Any]],
    ] = {}
    for runtime_registry in (
        runtime_adapter_v1_registry,
        runtime_adapter_v2_registry,
    ):
        for entry in runtime_registry["contracts"]:
            require(
                entry["plant_id"] not in runtime_entries,
                f"{entry['plant_id']}: multiple active runtime adapter versions",
            )
            runtime_entries[entry["plant_id"]] = (
                entry,
                runtime_registry,
            )
    require(
        len(runtime_entries)
        == len(runtime_adapter_v1_registry["contracts"])
        + len(runtime_adapter_v2_registry["contracts"])
        == len(runtime_contracts),
        "aggregate runtime-adapter contract identity/count drift",
    )
    parameter_sets: list[dict[str, Any]] = []
    for source_item in source_parameter_sets:
        item = copy.deepcopy(source_item)
        runtime_binding = runtime_entries.get(item["plant_id"])
        if runtime_binding is not None:
            entry, runtime_registry = runtime_binding
            contract = runtime_contracts[entry["contract_id"]]
            require(
                entry["parameter_set_sha256"]
                == parameter_hashes[item["plant_id"]]
                == contract["source_bindings"]["parameter_set_sha256"]
                and entry["contract_sha256"]
                == runtime_contract_hashes[entry["contract_id"]]
                and contract["runtime_adapter_id"]
                == runtime_registry["adapter"]["adapter_id"],
                f"{item['plant_id']}: runtime contract/source binding drift",
            )
            item["runtime_loadable"] = True
            item["runtime_adapter_id"] = contract["runtime_adapter_id"]
            item["runtime_contract_id"] = contract["contract_id"]
        parameter_sets.append(item)
    registry_entries = {
        item["plant_id"]: item
        for item in parameter_set_registry["parameter_sets"]
    }
    require(
        set(registry_entries) == set(parameter_hashes),
        "parameter-set assembly registry/file set drift",
    )
    for plant_id, digest in parameter_hashes.items():
        require(
            registry_entries[plant_id]["parameter_set_sha256"] == digest,
            f"{plant_id}: parameter-set assembly hash drift",
        )
    catalog_ids = {(row["series"], row["model"]) for row in catalog}
    plant_ids: set[str] = set()
    exact_keys: set[tuple[str, ...]] = set()
    by_model: dict[tuple[str, str], list[dict[str, Any]]] = {identity: [] for identity in catalog_ids}
    for item in parameter_sets:
        plant_id = item["plant_id"]
        require(plant_id not in plant_ids, f"duplicate plant ID {plant_id}")
        plant_ids.add(plant_id)
        applicability = item["applicability"]
        identity = (applicability["series"], applicability["model"])
        require(identity in catalog_ids, f"{plant_id}: unknown catalog identity {identity}")
        exact_key = tuple(applicability[name] for name in (
            "series", "model", "hardware_revision", "drive_firmware",
            "protocol_version", "transport", "control_mode",
        ))
        require(exact_key not in exact_keys, f"duplicate exact plant applicability {exact_key}")
        exact_keys.add(exact_key)
        by_model[identity].append(item)

    coverage = []
    for row in catalog:
        items = by_model[(row["series"], row["model"])]
        statuses = {item["status"] for item in items}
        if not items:
            status = "unsupported"
            reason = "no complete sourced exact-tuple plant parameter set"
        elif statuses <= {"sourced"}:
            status = "sourced"
            reason = None
        elif "robot_validated" in statuses or "hil_validated" in statuses:
            status = "validated"
            reason = None
        else:
            status = "partially_validated"
            reason = None
        coverage.append(
            {
                "series": row["series"],
                "model": row["model"],
                "status": status,
                "plant_ids": sorted(item["plant_id"] for item in items),
                "denial_reason": reason,
            }
        )

    backends = _base_backends()
    for item in parameter_sets:
        if not item["runtime_loadable"]:
            continue
        backends.append(
            {
                "backend_id": runtime_contracts[
                    item["runtime_contract_id"]
                ]["backend_id"],
                "kind": "actuator_plant",
                "evidence_class": BACKEND_EVIDENCE_FOR_STATUS[item["status"]],
                "runtime_loadable": item["runtime_loadable"],
                "models_physical_dynamics": True,
                "physically_validated": item["status"] != "sourced",
                "parameter_set_id": item["plant_id"],
                "runtime_contract_id": item["runtime_contract_id"],
                "substitution_scope": "single-actuator-mechanics",
            }
        )
    registry = {
        "schema_version": VERSION,
        "source_hashes": {
            "catalog_sha256": sha256(CATALOG),
            "parameter_set_registry_sha256": sha256(
                PARAMETER_SET_REGISTRY
            ),
            "parameter_set_registry_generation_sha256": (
                parameter_set_registry["registry_generation_sha256"]
            ),
            "parameter_set_sha256": dict(sorted(parameter_hashes.items())),
            "runtime_adapter_v1_registry_sha256": sha256(
                RUNTIME_ADAPTER_REGISTRY
            ),
            "runtime_adapter_v1_registry_generation_sha256": (
                runtime_adapter_v1_registry["integrity"]["record_sha256"]
            ),
            "runtime_adapter_v2_registry_sha256": sha256(
                RUNTIME_ADAPTER_V2_REGISTRY
            ),
            "runtime_adapter_v2_registry_generation_sha256": (
                runtime_adapter_v2_registry["integrity"]["record_sha256"]
            ),
            "runtime_contract_sha256": dict(
                sorted(runtime_contract_hashes.items())
            ),
        },
        "policy": {
            "exact_applicability_required": True,
            "parameter_source_required": True,
            "si_units_required": True,
            "bounded_uncertainty_required": True,
            "operating_envelope_required": True,
            "validation_class_required": True,
            "lifecycle_reviewed_facts_only": True,
            "accepted_protocol_applicability_required": True,
            "hand_authored_parameter_sets_forbidden": True,
            "exact_runtime_contract_required_for_loadability": True,
            "single_active_runtime_contract_across_adapter_versions": True,
            "unrepresentable_source_semantics_deny": True,
            "toy_is_never_physical_plant": True,
            "protocol_emulator_is_never_plant": True,
            "backend_substitution_must_be_explicit": True,
            "plant_does_not_grant_hardware_support": True,
        },
        "summary": {
            "models": len(coverage),
            "sourced_parameter_sets": len(parameter_sets),
            "runtime_loadable_parameter_sets": sum(item["runtime_loadable"] for item in parameter_sets),
            "physically_validated_parameter_sets": sum(item["status"] != "sourced" for item in parameter_sets),
            "backend_descriptors": len(backends),
        },
        "model_coverage": coverage,
        "parameter_sets": parameter_sets,
        "backends": backends,
    }
    validate_registry(registry, schema=schema, catalog=catalog)
    return registry


def validate_registry(
    registry: dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
    catalog: list[dict[str, str]] | None = None,
) -> None:
    schema = schema or json.loads(SCHEMA.read_text(encoding="utf-8"))
    catalog = catalog or load_catalog()
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(registry), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        location = "/".join(str(value) for value in error.absolute_path)
        raise PlantRegistryError(f"registry schema {location}: {error.message}")
    identities = [(item["series"], item["model"]) for item in registry["model_coverage"]]
    require(identities == [(row["series"], row["model"]) for row in catalog], "model coverage/order differs from catalog")
    for item in registry["parameter_sets"]:
        validate_parameter_set(item)
    plant_ids = {item["plant_id"] for item in registry["parameter_sets"]}
    backend_ids = [item["backend_id"] for item in registry["backends"]]
    require(len(backend_ids) == len(set(backend_ids)), "duplicate backend ID")
    plant_backends = [item for item in registry["backends"] if item["kind"] == "actuator_plant"]
    runtime_plant_ids = {
        item["plant_id"]
        for item in registry["parameter_sets"]
        if item["runtime_loadable"]
    }
    require(
        {item["parameter_set_id"] for item in plant_backends}
        == runtime_plant_ids,
        "runtime parameter-set/backend parity mismatch",
    )
    runtime_contract_ids = {
        item["runtime_contract_id"]
        for item in registry["parameter_sets"]
        if item["runtime_loadable"]
    }
    require(
        runtime_contract_ids
        == set(registry["source_hashes"]["runtime_contract_sha256"])
        == {
            item["runtime_contract_id"]
            for item in plant_backends
        },
        "runtime contract/set/backend parity mismatch",
    )
    set_by_id = {
        item["plant_id"]: item for item in registry["parameter_sets"]
    }
    require(
        all(
            item["runtime_contract_id"]
            == set_by_id[item["parameter_set_id"]]["runtime_contract_id"]
            for item in plant_backends
        ),
        "plant backend/runtime-contract binding drift",
    )
    nonplants = [item for item in registry["backends"] if item["kind"] != "actuator_plant"]
    require(
        all(
            item["parameter_set_id"] is None
            and item["runtime_contract_id"] is None
            for item in nonplants
        ),
        "non-plant backend references parameters/contracts",
    )
    toy = next((item for item in registry["backends"] if item["backend_id"] == "browser-toy-demo-v1"), None)
    protocol = next((item for item in registry["backends"] if item["backend_id"] == "rmd-v44-protocol-emulator"), None)
    synthetic = next((item for item in registry["backends"] if item["backend_id"] == "synthetic-electromechanical-fixed-step-v1"), None)
    replay = next(
        (
            item
            for item in registry["backends"]
            if item["backend_id"] == "canonical-recorded-state-replay-v1"
        ),
        None,
    )
    rigid_body = next(
        (
            item
            for item in registry["backends"]
            if item["backend_id"] == "dropbear-rigid-body-unavailable-v1"
        ),
        None,
    )
    require(
        replay is not None
        and replay["kind"] == "recorded_replay"
        and replay["runtime_loadable"]
        and not replay["models_physical_dynamics"]
        and not replay["physically_validated"]
        and replay["substitution_scope"] == "host-state-replay-only",
        "recorded replay backend identity drift",
    )
    require(toy is not None and toy["kind"] == "toy_demo" and not toy["models_physical_dynamics"], "toy backend identity drift")
    require(protocol is not None and protocol["kind"] == "protocol_emulator" and not protocol["models_physical_dynamics"], "protocol backend identity drift")
    require(
        synthetic is not None
        and synthetic["kind"] == "synthetic_actuator_plant"
        and synthetic["models_physical_dynamics"]
        and not synthetic["physically_validated"]
        and synthetic["parameter_set_id"] is None,
        "synthetic actuator-plant backend identity drift",
    )
    require(
        rigid_body is not None
        and rigid_body["kind"] == "rigid_body"
        and not rigid_body["runtime_loadable"]
        and not rigid_body["models_physical_dynamics"]
        and not rigid_body["physically_validated"]
        and rigid_body["substitution_scope"] == "whole-robot-mechanics",
        "unavailable rigid-body backend identity drift",
    )
    summary = registry["summary"]
    require(summary["sourced_parameter_sets"] == len(plant_ids), "parameter-set summary drift")
    require(summary["runtime_loadable_parameter_sets"] == sum(item["runtime_loadable"] for item in registry["parameter_sets"]), "runtime summary drift")
    require(summary["physically_validated_parameter_sets"] == sum(item["status"] != "sourced" for item in registry["parameter_sets"]), "validation summary drift")
    require(summary["backend_descriptors"] == len(registry["backends"]), "backend summary drift")


def render_web_module(registry: dict[str, Any], registry_sha256: str) -> str:
    toy = next(item for item in registry["backends"] if item["backend_id"] == "browser-toy-demo-v1")
    compact = json.dumps(toy, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return (
        "// Generated by tools/generate_plant_registry.py; do not edit.\n"
        f"export const PLANT_REGISTRY_SHA256 = {json.dumps(registry_sha256)};\n"
        f"export const BROWSER_TOY_BACKEND = Object.freeze({compact});\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    registry = build_registry()
    rendered = canonical_json(registry)
    registry_hash = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    web = render_web_module(registry, registry_hash)
    if args.write:
        atomic_write(OUTPUT, rendered)
        atomic_write(WEB_OUTPUT, web)
    else:
        require(OUTPUT.is_file() and OUTPUT.read_text(encoding="utf-8") == rendered, "plant registry drift")
        require(WEB_OUTPUT.is_file() and WEB_OUTPUT.read_text(encoding="utf-8") == web, "web plant backend drift")
    print(
        "PLANT_REGISTRY_OK "
        f"models={registry['summary']['models']} "
        f"parameter_sets={registry['summary']['sourced_parameter_sets']} "
        f"loadable={registry['summary']['runtime_loadable_parameter_sets']} "
        f"backends={registry['summary']['backend_descriptors']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, PlantRegistryError, ValueError) as error:
        print(f"Plant registry generation failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
