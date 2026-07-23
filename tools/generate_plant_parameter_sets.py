#!/usr/bin/env python3
"""Materialize exact-model plant sets from reviewed facts and applicability.

The materializer has no value-selection authority.  A runtime-loadable
source-only plant exists only when one model has exactly one active reviewed
fact for every one of the 34 parameter and four operating-envelope fields,
and at least one independently accepted exact protocol-applicability
decision.  Revoking either upstream evidence class removes the generated set.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "assets/myactuator/catalog.tsv"
PROTOCOL_REGISTRY = (
    ROOT / "generated/myactuator/protocol_applicability/registry.json"
)
PROTOCOL_REGISTRY_SCHEMA = (
    ROOT / "schemas/myactuator-protocol-applicability-registry.schema.json"
)
PROTOCOL_DECISION_SCHEMA = (
    ROOT / "schemas/myactuator-protocol-applicability-decision.schema.json"
)
CANDIDATE_DECISION_REGISTRY = (
    ROOT / "generated/myactuator/plant/candidate_decisions/registry.json"
)
CANDIDATE_FACT_DIRECTORY = (
    ROOT / "generated/myactuator/plant/candidate_decisions/source_facts"
)
CANDIDATE_FACT_SCHEMA = (
    ROOT / "schemas/myactuator-plant-source-fact.schema.json"
)
PLANT_REGISTRY_SCHEMA = (
    ROOT / "schemas/myactuator-plant-registry.schema.json"
)
REGISTRY_SCHEMA = (
    ROOT / "schemas/myactuator-plant-parameter-set-registry.schema.json"
)
OUTPUT_ROOT = ROOT / "generated/myactuator/plant/parameter_sets"
OUTPUT_REGISTRY = OUTPUT_ROOT / "registry.json"
OUTPUT_SET_DIRECTORY = OUTPUT_ROOT / "sets"
VERSION = "myactuator-plant-parameter-set-registry/1"

PARAMETER_FIELDS = {
    "electrical.phase_resistance_ohm": "ohm",
    "electrical.phase_inductance_h": "H",
    "electrical.torque_constant_nm_per_a": "N*m/A",
    "electrical.back_emf_v_s_per_rad": "V*s/rad",
    "electrical.max_qaxis_current_a": "A",
    "mechanical.rotor_inertia_kg_m2": "kg*m^2",
    "mechanical.output_inertia_kg_m2": "kg*m^2",
    "mechanical.coulomb_friction_nm": "N*m",
    "mechanical.viscous_friction_nm_s_per_rad": "N*m*s/rad",
    "transmission.ratio_motor_per_output": "1",
    "transmission.forward_efficiency_ratio": "1",
    "transmission.reverse_efficiency_ratio": "1",
    "transmission.torsional_stiffness_nm_per_rad": "N*m/rad",
    "transmission.backlash_rad": "rad",
    "saturation.max_motor_speed_rad_s": "rad/s",
    "saturation.max_output_speed_rad_s": "rad/s",
    "saturation.max_continuous_output_torque_nm": "N*m",
    "saturation.max_peak_output_torque_nm": "N*m",
    "saturation.peak_duration_s": "s",
    "thermal.winding_resistance_k_per_w": "K/W",
    "thermal.case_resistance_k_per_w": "K/W",
    "thermal.winding_heat_capacity_j_per_k": "J/K",
    "thermal.case_heat_capacity_j_per_k": "J/K",
    "thermal.max_winding_temperature_k": "K",
    "thermal.max_case_temperature_k": "K",
    "sensor.position_quantization_rad": "rad",
    "sensor.position_noise_stddev_rad": "rad",
    "sensor.velocity_noise_stddev_rad_s": "rad/s",
    "sensor.current_noise_stddev_a": "A",
    "latency.command_delay_s": "s",
    "latency.current_loop_period_s": "s",
    "latency.state_sample_period_s": "s",
    "latency.feedback_delay_s": "s",
    "latency.delay_jitter_s": "s",
}
ENVELOPE_FIELDS = {
    "operating_envelope.supply_voltage_v": "V",
    "operating_envelope.ambient_temperature_k": "K",
    "operating_envelope.output_speed_rad_s": "rad/s",
    "operating_envelope.output_torque_nm": "N*m",
}
ALL_FIELDS = tuple(PARAMETER_FIELDS) + tuple(ENVELOPE_FIELDS)
MODEL_FORMS = {
    "electrical": "dq-lumped-v1",
    "mechanical": "two-inertia-output-v1",
    "transmission": "ratio-efficiency-compliance-v1",
    "friction_backlash": "coulomb-viscous-deadzone-v1",
    "saturation": "current-speed-torque-duration-v1",
    "thermal": "two-node-rc-v1",
    "sensor": "quantized-biased-noisy-v1",
    "latency": "bounded-delay-jitter-v1",
    "integrator": "semi-implicit-euler-v1",
}
POLICY = {
    "exactly_one_active_fact_per_required_field": True,
    "all_34_parameters_and_4_envelopes_required": True,
    "parameter_observations_must_be_scalar": True,
    "envelope_observations_must_be_ranges": True,
    "bounded_uncertainty_required": True,
    "operating_conditions_must_fit_selected_envelope": True,
    "accepted_exact_protocol_applicability_required": True,
    "no_family_default_or_manual_parameter_file": True,
    "source_revocation_removes_materialization": True,
    "assembly_never_grants_motor_support_or_motion": True,
}


class PlantParameterSetError(ValueError):
    """An input, fact selection, assembly, or generated-set invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PlantParameterSetError(message)


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


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PlantParameterSetError(
            f"{path}: cannot load JSON: {error}"
        ) from error
    require(isinstance(value, dict), f"{path}: JSON root must be an object")
    return value


def schema_validate(
    value: dict[str, Any],
    schema: dict[str, Any],
    *,
    context: str,
) -> None:
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        location = "/".join(map(str, error.absolute_path))
        raise PlantParameterSetError(
            f"{context}: schema failure at /{location}: {error.message}"
        )


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def validate_digest(value: dict[str, Any], context: str) -> None:
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        f"{context}: record digest drift",
    )


def _finite(value: Any, context: str) -> float:
    require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value),
        f"{context}: finite number required",
    )
    return float(value)


def load_catalog(path: Path = CATALOG) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            require(
                reader.fieldnames
                == ["series", "model", "package_revision", "archive_url"],
                "catalog columns drift",
            )
            rows = list(reader)
    except OSError as error:
        raise PlantParameterSetError(f"cannot load catalog: {error}") from error
    require(len(rows) == 44, "catalog must contain exactly 44 models")
    require(
        len({(row["series"], row["model"]) for row in rows}) == 44,
        "catalog model identity is not unique",
    )
    return rows


def model_key(series: str, model: str) -> str:
    return "model-" + sha_bytes(
        canonical_bytes({"model": model, "series": series})
    )[:20]


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_verified_protocol_registry(
    path: Path = PROTOCOL_REGISTRY,
) -> dict[str, Any]:
    value = load_json(path)
    schema_validate(
        value,
        load_json(PROTOCOL_REGISTRY_SCHEMA),
        context=str(path),
    )
    validate_digest(value, str(path))
    require(
        value["schema_version"]
        == "myactuator-protocol-applicability-registry/2"
        and value["summary"]["model_count"] == 44,
        f"{path}: protocol registry identity/count drift",
    )
    decision_schema = load_json(PROTOCOL_DECISION_SCHEMA)
    decisions: dict[str, dict[str, Any]] = {}
    for decision in value["accepted_applicability_decisions"]:
        identifier = decision.get("decision_id")
        require(
            isinstance(identifier, str) and identifier not in decisions,
            f"{path}: duplicate or absent accepted decision ID",
        )
        schema_validate(
            decision,
            decision_schema,
            context=f"{path}/{identifier}",
        )
        validate_digest(decision, f"{path}/{identifier}")
        require(
            decision["record_state"] == "submitted"
            and decision["disposition"] == "accept_applicability"
            and decision["applicability_established"] is True
            and decision["review"]["status"] == "accepted"
            and decision["support_granted"] is False
            and decision["physical_motion_authority"] is False,
            f"{path}/{identifier}: decision is not active accepted evidence",
        )
        decisions[identifier] = decision
    model_decision_ids: set[str] = set()
    for model in value["models"]:
        identifiers = model["accepted_decision_ids"]
        require(
            identifiers == sorted(identifiers)
            and not (set(identifiers) & model_decision_ids),
            f"{path}/{model['model_key']}: decision ordering/ownership drift",
        )
        for identifier in identifiers:
            decision = decisions.get(identifier)
            require(
                decision is not None,
                f"{path}/{model['model_key']}: unknown accepted decision",
            )
            subject = decision["subject"]
            require(
                (
                    subject["model_key"],
                    subject["series"],
                    subject["model"],
                    subject["package_revision"],
                )
                == (
                    model["model_key"],
                    model["series"],
                    model["model"],
                    model["package_revision"],
                ),
                f"{path}/{identifier}: decision/model binding drift",
            )
        model_decision_ids.update(identifiers)
    require(
        model_decision_ids == set(decisions),
        f"{path}: embedded/model accepted-decision set drift",
    )
    return value


def load_verified_candidate_facts(
    registry_path: Path = CANDIDATE_DECISION_REGISTRY,
    fact_directory: Path = CANDIDATE_FACT_DIRECTORY,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, str]]:
    manager = _load_module(
        "plant_candidate_decision_materializer_for_set_assembly",
        ROOT / "tools/manage_plant_candidate_decisions.py",
    )
    expected_registry, expected_facts = manager.build()
    actual_registry = load_json(registry_path)
    require(
        canonical_json(actual_registry) == canonical_json(expected_registry),
        f"{registry_path}: candidate decision replay drift",
    )
    actual_paths = {
        path.stem: path for path in sorted(fact_directory.glob("*.json"))
    }
    require(
        set(actual_paths) == set(expected_facts),
        f"{fact_directory}: active source-fact file set drift",
    )
    hashes: dict[str, str] = {}
    for identifier, expected in expected_facts.items():
        path = actual_paths[identifier]
        require(
            path.read_text(encoding="utf-8") == canonical_json(expected),
            f"{path}: materialized source fact drift",
        )
        hashes[identifier] = sha_file(path)
    return actual_registry, expected_facts, hashes


def _field_id(fact: Mapping[str, Any]) -> str:
    target = fact["target"]
    return f"{target['domain']}.{target['name']}"


def _applicability(decision: Mapping[str, Any]) -> dict[str, str]:
    subject = decision["subject"]
    return {
        "series": subject["series"],
        "model": subject["model"],
        "hardware_revision": subject["hardware_revision"],
        "drive_firmware": subject["drive_firmware"],
        "protocol_version": subject["protocol_revision"],
        "transport": subject["transport"],
        "control_mode": subject["control_mode"],
    }


def _applicability_key(decision: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(_applicability(decision).values())


def _uncertainty(fact: Mapping[str, Any]) -> dict[str, Any]:
    source = fact["evidence"]["uncertainty"]
    return {
        "kind": "bounded_interval",
        "lower": source["lower"],
        "upper": source["upper"],
        "unit": source["unit"],
        "coverage_probability": source["coverage_probability"],
    }


def _validation_class(fact: Mapping[str, Any]) -> str:
    return (
        "official_specification"
        if fact["evidence"]["class"] == "official_stated"
        else "source_derived"
    )


def _rotation_direction(
    speed: Mapping[str, Any],
    torque: Mapping[str, Any],
) -> str:
    directions: list[str] = []
    for name, observation in (("speed", speed), ("torque", torque)):
        lower = _finite(
            observation["normalized_minimum"], f"envelope/{name}/minimum"
        )
        upper = _finite(
            observation["normalized_maximum"], f"envelope/{name}/maximum"
        )
        require(lower < upper, f"envelope/{name}: empty or inverted range")
        if lower < 0.0 < upper:
            directions.append("bidirectional")
        elif lower >= 0.0 and upper > 0.0:
            directions.append("positive")
        elif upper <= 0.0 and lower < 0.0:
            directions.append("negative")
        else:
            raise PlantParameterSetError(
                f"envelope/{name}: direction cannot be established"
            )
    require(
        directions[0] == directions[1],
        "speed/torque envelope direction mismatch",
    )
    return directions[0]


def _validate_fact_set(
    facts_by_field: Mapping[str, Mapping[str, Any]],
    *,
    model: Mapping[str, Any],
) -> None:
    require(
        set(facts_by_field) == set(ALL_FIELDS),
        f"{model['model_key']}: exactly 38 required facts are required",
    )
    for field_id, expected_unit in {
        **PARAMETER_FIELDS,
        **ENVELOPE_FIELDS,
    }.items():
        fact = facts_by_field[field_id]
        identity = fact["model_identity"]
        require(
            (
                identity["model_key"],
                identity["series"],
                identity["model"],
                identity["package_revision"],
            )
            == (
                model["model_key"],
                model["series"],
                model["model"],
                model["package_revision"],
            ),
            f"{field_id}: fact/model identity drift",
        )
        require(
            fact["review"]["status"] == "accepted"
            and fact["support_granted"] is False
            and fact["physical_motion_authority"] is False,
            f"{field_id}: fact is not active denial-preserving evidence",
        )
        observation = fact["observation"]
        expected_shape = (
            "scalar" if field_id in PARAMETER_FIELDS else "range"
        )
        require(
            observation["shape"] == expected_shape
            and observation["normalized_unit"] == expected_unit,
            f"{field_id}: observation shape/unit is not runtime compatible",
        )
        uncertainty = fact["evidence"]["uncertainty"]
        lower = _finite(uncertainty["lower"], f"{field_id}/uncertainty/lower")
        upper = _finite(uncertainty["upper"], f"{field_id}/uncertainty/upper")
        require(
            lower <= upper and uncertainty["unit"] == expected_unit,
            f"{field_id}: invalid canonical uncertainty",
        )
        values = (
            [observation["normalized_value"]]
            if expected_shape == "scalar"
            else [
                observation["normalized_minimum"],
                observation["normalized_maximum"],
            ]
        )
        require(
            all(lower <= _finite(item, field_id) <= upper for item in values),
            f"{field_id}: normalized observation is outside uncertainty",
        )


def _fact_source(
    field_id: str,
    fact: Mapping[str, Any],
    fact_hash: str,
) -> dict[str, Any]:
    provenance = fact["provenance"]
    return {
        "source_id": fact["fact_id"],
        "kind": "reviewed_source_fact",
        "locator": (
            f"document-occurrence:{provenance['document_occurrence_id']}"
            f"#pdf-page={provenance['pdf_page_index']}"
            f"&candidate={provenance['candidate_id']}"
        ),
        "revision": (
            "candidate-decision-generation:"
            + fact["review"][
                "candidate_decision_registry_generation_sha256"
            ]
        ),
        "sha256": fact_hash,
        "claim_scope": field_id,
        "acquired_at_utc": fact["review"]["reviewed_at_utc"],
    }


def _parameter_value(
    fact: Mapping[str, Any],
    envelope_id: str,
) -> dict[str, Any]:
    observation = fact["observation"]
    return {
        "value": observation["normalized_value"],
        "unit": observation["normalized_unit"],
        "uncertainty": _uncertainty(fact),
        "source_refs": [fact["fact_id"]],
        "applicability_envelope_refs": [envelope_id],
        "validation_class": _validation_class(fact),
    }


def _range_value(fact: Mapping[str, Any]) -> dict[str, Any]:
    observation = fact["observation"]
    return {
        "minimum": observation["normalized_minimum"],
        "maximum": observation["normalized_maximum"],
        "unit": observation["normalized_unit"],
        "uncertainty": _uncertainty(fact),
        "source_refs": [fact["fact_id"]],
        "validation_class": _validation_class(fact),
    }


def _validate_operating_conditions(
    facts_by_field: Mapping[str, Mapping[str, Any]],
    envelope: Mapping[str, Any],
) -> None:
    supply = envelope["supply_voltage_v"]
    ambient = envelope["ambient_temperature_k"]
    direction = envelope["rotation_direction"]
    for field_id, fact in facts_by_field.items():
        condition = fact["evidence"]["operating_condition"]
        voltage = condition["supply_voltage_v"]
        if voltage is not None:
            value = _finite(voltage, f"{field_id}/condition/supply_voltage_v")
            require(
                supply["minimum"] <= value <= supply["maximum"],
                f"{field_id}: source voltage is outside assembled envelope",
            )
        temperature = condition["ambient_temperature_k"]
        if temperature is not None:
            value = _finite(
                temperature,
                f"{field_id}/condition/ambient_temperature_k",
            )
            require(
                ambient["minimum"] <= value <= ambient["maximum"],
                f"{field_id}: source ambient is outside assembled envelope",
            )
        fact_direction = condition["rotation_direction"]
        require(
            fact_direction == "not_stated"
            or direction == "bidirectional"
            or fact_direction == direction,
            f"{field_id}: source rotation condition conflicts with envelope",
        )


def _validate_cross_field_semantics(item: Mapping[str, Any]) -> None:
    parameters = item["parameters"]
    transmission = parameters["transmission"]
    saturation = parameters["saturation"]
    thermal = parameters["thermal"]
    latency = parameters["latency"]
    mechanical = parameters["mechanical"]
    electrical = parameters["electrical"]
    sensor = parameters["sensor"]
    positive = [
        electrical["phase_resistance_ohm"]["value"],
        electrical["phase_inductance_h"]["value"],
        electrical["torque_constant_nm_per_a"]["value"],
        electrical["back_emf_v_s_per_rad"]["value"],
        electrical["max_qaxis_current_a"]["value"],
        mechanical["rotor_inertia_kg_m2"]["value"],
        mechanical["output_inertia_kg_m2"]["value"],
        transmission["ratio_motor_per_output"]["value"],
        transmission["torsional_stiffness_nm_per_rad"]["value"],
        saturation["max_motor_speed_rad_s"]["value"],
        saturation["max_output_speed_rad_s"]["value"],
        saturation["max_continuous_output_torque_nm"]["value"],
        saturation["max_peak_output_torque_nm"]["value"],
        saturation["peak_duration_s"]["value"],
        thermal["winding_resistance_k_per_w"]["value"],
        thermal["case_resistance_k_per_w"]["value"],
        thermal["winding_heat_capacity_j_per_k"]["value"],
        thermal["case_heat_capacity_j_per_k"]["value"],
        thermal["max_winding_temperature_k"]["value"],
        thermal["max_case_temperature_k"]["value"],
        sensor["position_quantization_rad"]["value"],
        latency["current_loop_period_s"]["value"],
        latency["state_sample_period_s"]["value"],
    ]
    require(
        all(_finite(value, "positive parameter") > 0.0 for value in positive),
        "strictly positive plant parameter is zero or negative",
    )
    nonnegative = [
        mechanical["coulomb_friction_nm"]["value"],
        mechanical["viscous_friction_nm_s_per_rad"]["value"],
        transmission["backlash_rad"]["value"],
        sensor["position_noise_stddev_rad"]["value"],
        sensor["velocity_noise_stddev_rad_s"]["value"],
        sensor["current_noise_stddev_a"]["value"],
        latency["command_delay_s"]["value"],
        latency["feedback_delay_s"]["value"],
        latency["delay_jitter_s"]["value"],
    ]
    require(
        all(_finite(value, "nonnegative parameter") >= 0.0 for value in nonnegative),
        "nonnegative plant parameter is negative",
    )
    for name in ("forward_efficiency_ratio", "reverse_efficiency_ratio"):
        efficiency = transmission[name]["value"]
        require(
            0.0 < efficiency <= 1.0,
            f"transmission/{name}: efficiency outside (0,1]",
        )
    require(
        saturation["max_peak_output_torque_nm"]["value"]
        >= saturation["max_continuous_output_torque_nm"]["value"],
        "peak output torque is below continuous output torque",
    )
    envelope = item["operating_envelopes"][0]
    require(
        max(
            abs(envelope["output_speed_rad_s"]["minimum"]),
            abs(envelope["output_speed_rad_s"]["maximum"]),
        )
        <= saturation["max_output_speed_rad_s"]["value"],
        "operating speed envelope exceeds selected maximum output speed",
    )
    require(
        max(
            abs(envelope["output_torque_nm"]["minimum"]),
            abs(envelope["output_torque_nm"]["maximum"]),
        )
        <= saturation["max_peak_output_torque_nm"]["value"],
        "operating torque envelope exceeds selected peak output torque",
    )
    require(
        envelope["ambient_temperature_k"]["maximum"]
        < min(
            thermal["max_winding_temperature_k"]["value"],
            thermal["max_case_temperature_k"]["value"],
        ),
        "ambient envelope reaches or exceeds thermal maximum",
    )


def materialize_parameter_set(
    *,
    model: Mapping[str, Any],
    facts_by_field: Mapping[str, Mapping[str, Any]],
    fact_hashes: Mapping[str, str],
    decisions: Iterable[Mapping[str, Any]],
    protocol_registry_sha256: str,
    candidate_decision_registry_sha256: str,
    candidate_decision_registry_generation_sha256: str,
    registry_generation_sha256: str,
    materializer_sha256: str,
    parameter_schema: dict[str, Any],
) -> dict[str, Any]:
    _validate_fact_set(facts_by_field, model=model)
    decisions = sorted(decisions, key=lambda item: item["decision_id"])
    require(decisions, f"{model['model_key']}: accepted applicability required")
    keys = {_applicability_key(decision) for decision in decisions}
    require(len(keys) == 1, "one materialization cannot mix applicability tuples")
    applicability = _applicability(decisions[0])
    require(
        (applicability["series"], applicability["model"])
        == (model["series"], model["model"]),
        "protocol applicability/model identity mismatch",
    )
    fact_ids = [facts_by_field[field_id]["fact_id"] for field_id in ALL_FIELDS]
    require(
        len(fact_ids) == len(set(fact_ids)) == 38
        and set(fact_ids) <= set(fact_hashes),
        "source-fact identity/hash coverage is not exact",
    )
    fact_set_payload = {
        field_id: {
            "fact_id": facts_by_field[field_id]["fact_id"],
            "fact_sha256": fact_hashes[facts_by_field[field_id]["fact_id"]],
        }
        for field_id in ALL_FIELDS
    }
    fact_set_sha256 = sha_bytes(canonical_bytes(fact_set_payload))
    envelope_id = "envelope-" + sha_bytes(
        canonical_bytes(
            {
                "model_key": model["model_key"],
                "facts": {
                    field_id: fact_set_payload[field_id]
                    for field_id in ENVELOPE_FIELDS
                },
            }
        )
    )[:20]
    speed_fact = facts_by_field["operating_envelope.output_speed_rad_s"]
    torque_fact = facts_by_field["operating_envelope.output_torque_nm"]
    envelope = {
        "envelope_id": envelope_id,
        "supply_voltage_v": _range_value(
            facts_by_field["operating_envelope.supply_voltage_v"]
        ),
        "ambient_temperature_k": _range_value(
            facts_by_field["operating_envelope.ambient_temperature_k"]
        ),
        "output_speed_rad_s": _range_value(speed_fact),
        "output_torque_nm": _range_value(torque_fact),
        "rotation_direction": _rotation_direction(
            speed_fact["observation"], torque_fact["observation"]
        ),
    }
    _validate_operating_conditions(facts_by_field, envelope)
    parameters: dict[str, dict[str, Any]] = defaultdict(dict)
    for field_id in PARAMETER_FIELDS:
        domain, name = field_id.split(".", 1)
        parameters[domain][name] = _parameter_value(
            facts_by_field[field_id], envelope_id
        )
    decision_ids = [decision["decision_id"] for decision in decisions]
    identity_payload = {
        "model_key": model["model_key"],
        "applicability": applicability,
        "accepted_protocol_decision_ids": decision_ids,
        "source_fact_set_sha256": fact_set_sha256,
        "model_forms": MODEL_FORMS,
        "registry_generation_sha256": registry_generation_sha256,
    }
    plant_id = "plant-set-" + sha_bytes(
        canonical_bytes(identity_payload)
    )[:20]
    sources = [
        _fact_source(
            field_id,
            facts_by_field[field_id],
            fact_hashes[facts_by_field[field_id]["fact_id"]],
        )
        for field_id in ALL_FIELDS
    ]
    item = {
        "plant_id": plant_id,
        "parameter_revision": 1,
        "status": "sourced",
        "runtime_loadable": False,
        "runtime_adapter_id": None,
        "runtime_contract_id": None,
        "support_granted": False,
        "physical_motion_authority": False,
        "applicability": applicability,
        "model_forms": copy.deepcopy(MODEL_FORMS),
        "sources": sources,
        "operating_envelopes": [envelope],
        "parameters": dict(parameters),
        "validation": {
            "class": "source_only",
            "evidence_refs": [],
            "scenario_ids": [],
            "validated_at_utc": None,
        },
        "assembly": {
            "assembly_registry_artifact_id": (
                "myactuator-plant-parameter-set-registry"
            ),
            "assembly_registry_generation_sha256": (
                registry_generation_sha256
            ),
            "protocol_applicability_registry_sha256": (
                protocol_registry_sha256
            ),
            "accepted_protocol_decision_ids": decision_ids,
            "candidate_decision_registry_sha256": (
                candidate_decision_registry_sha256
            ),
            "candidate_decision_registry_generation_sha256": (
                candidate_decision_registry_generation_sha256
            ),
            "source_fact_ids": fact_ids,
            "source_fact_sha256": {
                identifier: fact_hashes[identifier]
                for identifier in fact_ids
            },
            "source_fact_set_sha256": fact_set_sha256,
            "materializer_sha256": materializer_sha256,
            "physical_correlation_evidence_present": False,
        },
    }
    parameter_validator = Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": "#/$defs/parameterSet",
            "$defs": parameter_schema["$defs"],
        },
        format_checker=FormatChecker(),
    )
    errors = sorted(
        parameter_validator.iter_errors(item),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise PlantParameterSetError(
            f"{plant_id}: parameter-set schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    _validate_cross_field_semantics(item)
    return item


def _generation_payload(
    *,
    sources: Mapping[str, Any],
    model_inputs: Iterable[Mapping[str, Any]],
) -> bytes:
    return canonical_bytes(
        {
            "sources": sources,
            "policy": POLICY,
            "model_inputs": [
                {
                    "model_key": item["model_key"],
                    "series": item["series"],
                    "model": item["model"],
                    "package_revision": item["package_revision"],
                    "source_fact_ids": item["source_fact_ids"],
                    "missing_field_ids": item["missing_field_ids"],
                    "accepted_protocol_decision_ids": item[
                        "accepted_protocol_decision_ids"
                    ],
                }
                for item in model_inputs
            ],
        }
    )


def build_from_inputs(
    *,
    catalog: list[dict[str, str]],
    protocol_registry: dict[str, Any],
    candidate_decision_registry: dict[str, Any],
    facts: Mapping[str, dict[str, Any]],
    fact_hashes: Mapping[str, str],
    sources: dict[str, Any],
    parameter_schema: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    protocol_models = {
        item["model_key"]: item for item in protocol_registry["models"]
    }
    decisions = {
        item["decision_id"]: item
        for item in protocol_registry["accepted_applicability_decisions"]
    }
    by_model_and_field: dict[
        tuple[str, str], list[dict[str, Any]]
    ] = defaultdict(list)
    for fact in facts.values():
        by_model_and_field[
            (fact["model_identity"]["model_key"], _field_id(fact))
        ].append(fact)
    model_inputs: list[dict[str, Any]] = []
    fact_maps: dict[str, dict[str, dict[str, Any]]] = {}
    decision_groups: dict[
        str, dict[tuple[str, ...], list[dict[str, Any]]]
    ] = {}
    for row in catalog:
        key = model_key(row["series"], row["model"])
        protocol_model = protocol_models.get(key)
        require(
            protocol_model is not None
            and (
                protocol_model["series"],
                protocol_model["model"],
                protocol_model["package_revision"],
            )
            == (
                row["series"],
                row["model"],
                row["package_revision"],
            ),
            f"{key}: catalog/protocol model drift",
        )
        selected: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        for field_id in ALL_FIELDS:
            candidates = by_model_and_field.get((key, field_id), [])
            require(
                len(candidates) <= 1,
                f"{key}/{field_id}: conflicting active source facts",
            )
            if candidates:
                selected[field_id] = candidates[0]
            else:
                missing.append(field_id)
        identifiers = protocol_model["accepted_decision_ids"]
        grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for identifier in identifiers:
            decision = decisions.get(identifier)
            require(decision is not None, f"{key}: missing embedded decision")
            grouped[_applicability_key(decision)].append(decision)
        fact_maps[key] = selected
        decision_groups[key] = grouped
        model_inputs.append(
            {
                "model_key": key,
                "series": row["series"],
                "model": row["model"],
                "package_revision": row["package_revision"],
                "source_fact_ids": [
                    selected[field_id]["fact_id"]
                    for field_id in ALL_FIELDS
                    if field_id in selected
                ],
                "missing_field_ids": missing,
                "accepted_protocol_decision_ids": identifiers,
            }
        )
    require(
        {
            fact["model_identity"]["model_key"] for fact in facts.values()
        }
        <= {item["model_key"] for item in model_inputs},
        "active fact references a non-catalog model",
    )
    registry_generation_sha256 = sha_bytes(
        _generation_payload(sources=sources, model_inputs=model_inputs)
    )
    parameter_sets: dict[str, dict[str, Any]] = {}
    entries: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    for model_input in model_inputs:
        key = model_input["model_key"]
        plant_ids: list[str] = []
        blockers: list[str] = []
        if model_input["missing_field_ids"]:
            blockers.append("source_fact_matrix_incomplete")
        if not model_input["accepted_protocol_decision_ids"]:
            blockers.append("accepted_protocol_applicability_missing")
        if not blockers:
            try:
                for decisions_for_tuple in decision_groups[key].values():
                    item = materialize_parameter_set(
                        model=model_input,
                        facts_by_field=fact_maps[key],
                        fact_hashes=fact_hashes,
                        decisions=decisions_for_tuple,
                        protocol_registry_sha256=sources[
                            "protocol_applicability_registry_sha256"
                        ],
                        candidate_decision_registry_sha256=sources[
                            "candidate_decision_registry_sha256"
                        ],
                        candidate_decision_registry_generation_sha256=sources[
                            "candidate_decision_registry_generation_sha256"
                        ],
                        registry_generation_sha256=(
                            registry_generation_sha256
                        ),
                        materializer_sha256=sources["materializer_sha256"],
                        parameter_schema=parameter_schema,
                    )
                    require(
                        item["plant_id"] not in parameter_sets,
                        f"{item['plant_id']}: duplicate materialized plant",
                    )
                    parameter_sets[item["plant_id"]] = item
                    plant_ids.append(item["plant_id"])
            except PlantParameterSetError:
                blockers.append("parameter_set_semantic_incompatibility")
                for plant_id in plant_ids:
                    parameter_sets.pop(plant_id, None)
                plant_ids = []
        plant_ids.sort()
        if plant_ids:
            blockers.append("runtime_plant_adapter_missing")
        models.append(
            {
                **model_input,
                "plant_ids": plant_ids,
                "assembly_status": (
                    "assembled_source_only" if plant_ids else "blocked"
                ),
                "blockers": blockers,
                "support_granted": False,
            }
        )
    for plant_id in sorted(parameter_sets):
        item = parameter_sets[plant_id]
        # The registry names the materialized JSON file, so its digest must
        # bind the exact canonical file bytes rather than a second compact
        # serialization of the same object.
        content = canonical_json(item).encode("utf-8")
        entries.append(
            {
                "plant_id": plant_id,
                "parameter_set_path": (
                    "generated/myactuator/plant/parameter_sets/sets/"
                    f"{plant_id}.json"
                ),
                "parameter_set_sha256": sha_bytes(content),
                "model_key": next(
                    model["model_key"]
                    for model in models
                    if plant_id in model["plant_ids"]
                ),
                "accepted_protocol_decision_ids": item["assembly"][
                    "accepted_protocol_decision_ids"
                ],
                "source_fact_ids": item["assembly"]["source_fact_ids"],
                "applicability": item["applicability"],
                "runtime_loadable": item["runtime_loadable"],
            }
        )
    value = {
        "schema_version": VERSION,
        "artifact_id": "myactuator-plant-parameter-set-registry",
        "authority": (
            "deterministic_reviewed_fact_and_applicability_assembly_only"
        ),
        "sources": sources,
        "policy": copy.deepcopy(POLICY),
        "registry_generation_sha256": registry_generation_sha256,
        "models": models,
        "parameter_sets": entries,
        "summary": {
            "model_count": len(models),
            "required_parameter_field_count": len(PARAMETER_FIELDS),
            "required_operating_envelope_field_count": len(
                ENVELOPE_FIELDS
            ),
            "active_source_fact_count": len(facts),
            "source_fact_complete_model_count": sum(
                not model["missing_field_ids"] for model in models
            ),
            "accepted_protocol_applicability_count": len(decisions),
            "accepted_protocol_applicability_model_count": sum(
                bool(model["accepted_protocol_decision_ids"])
                for model in models
            ),
            "assembled_parameter_set_count": len(entries),
            "assembled_model_count": sum(
                bool(model["plant_ids"]) for model in models
            ),
            "runtime_loadable_parameter_set_count": 0,
            "physically_correlated_parameter_set_count": 0,
            "supported_model_count": 0,
        },
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(value)
    return value, parameter_sets


def build() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    catalog = load_catalog()
    protocol_registry = load_verified_protocol_registry()
    candidate_registry, facts, fact_hashes = (
        load_verified_candidate_facts()
    )
    sources = {
        "catalog_sha256": sha_file(CATALOG),
        "protocol_applicability_registry_sha256": sha_file(
            PROTOCOL_REGISTRY
        ),
        "candidate_decision_registry_sha256": sha_file(
            CANDIDATE_DECISION_REGISTRY
        ),
        "candidate_decision_registry_generation_sha256": (
            candidate_registry["registry_generation_sha256"]
        ),
        "source_fact_schema_sha256": sha_file(CANDIDATE_FACT_SCHEMA),
        "plant_registry_schema_sha256": sha_file(PLANT_REGISTRY_SCHEMA),
        "materializer_sha256": sha_file(Path(__file__).resolve()),
        "source_fact_file_sha256": dict(sorted(fact_hashes.items())),
    }
    return build_from_inputs(
        catalog=catalog,
        protocol_registry=protocol_registry,
        candidate_decision_registry=candidate_registry,
        facts=facts,
        fact_hashes=fact_hashes,
        sources=sources,
        parameter_schema=load_json(PLANT_REGISTRY_SCHEMA),
    )


def validate(
    value: dict[str, Any],
    parameter_sets: Mapping[str, dict[str, Any]],
    *,
    verify_sources: bool = True,
) -> None:
    schema_validate(value, load_json(REGISTRY_SCHEMA), context="registry")
    validate_digest(value, "registry")
    require(
        value["registry_generation_sha256"]
        == sha_bytes(
            _generation_payload(
                sources=value["sources"],
                model_inputs=value["models"],
            )
        ),
        "registry generation digest drift",
    )
    catalog = load_catalog()
    require(
        [
            (
                model["series"],
                model["model"],
                model["package_revision"],
            )
            for model in value["models"]
        ]
        == [
            (row["series"], row["model"], row["package_revision"])
            for row in catalog
        ],
        "registry model order/identity differs from catalog",
    )
    entries = {
        item["plant_id"]: item for item in value["parameter_sets"]
    }
    require(
        len(entries) == len(value["parameter_sets"])
        and set(entries) == set(parameter_sets),
        "parameter-set registry/file identity drift",
    )
    parameter_schema = load_json(PLANT_REGISTRY_SCHEMA)
    validator = Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": "#/$defs/parameterSet",
            "$defs": parameter_schema["$defs"],
        },
        format_checker=FormatChecker(),
    )
    for plant_id, item in parameter_sets.items():
        errors = sorted(
            validator.iter_errors(item),
            key=lambda error: (list(error.absolute_path), error.message),
        )
        if errors:
            error = errors[0]
            raise PlantParameterSetError(
                f"{plant_id}: parameter-set schema failure at "
                f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
            )
        _validate_cross_field_semantics(item)
        entry = entries[plant_id]
        require(
            entry["parameter_set_sha256"]
            == sha_bytes(canonical_json(item).encode("utf-8"))
            and entry["accepted_protocol_decision_ids"]
            == item["assembly"]["accepted_protocol_decision_ids"]
            and entry["source_fact_ids"]
            == item["assembly"]["source_fact_ids"]
            and entry["applicability"] == item["applicability"]
            and entry["runtime_loadable"] is item["runtime_loadable"],
            f"{plant_id}: registry/materialization drift",
        )
    model_plant_ids = {
        plant_id for model in value["models"] for plant_id in model["plant_ids"]
    }
    require(
        model_plant_ids == set(parameter_sets),
        "model/parameter-set ownership drift",
    )
    for model in value["models"]:
        require(
            model["assembly_status"]
            == (
                "assembled_source_only"
                if model["plant_ids"]
                else "blocked"
            ),
            f"{model['model_key']}: assembly status drift",
        )
        require(
            not model["support_granted"],
            f"{model['model_key']}: support promotion",
        )
    expected_summary = {
        "model_count": 44,
        "required_parameter_field_count": 34,
        "required_operating_envelope_field_count": 4,
        "active_source_fact_count": len(
            value["sources"]["source_fact_file_sha256"]
        ),
        "source_fact_complete_model_count": sum(
            not model["missing_field_ids"] for model in value["models"]
        ),
        "accepted_protocol_applicability_count": sum(
            len(model["accepted_protocol_decision_ids"])
            for model in value["models"]
        ),
        "accepted_protocol_applicability_model_count": sum(
            bool(model["accepted_protocol_decision_ids"])
            for model in value["models"]
        ),
        "assembled_parameter_set_count": len(parameter_sets),
        "assembled_model_count": sum(
            bool(model["plant_ids"]) for model in value["models"]
        ),
        "runtime_loadable_parameter_set_count": 0,
        "physically_correlated_parameter_set_count": 0,
        "supported_model_count": 0,
    }
    require(
        value["summary"] == expected_summary,
        "parameter-set registry summary drift",
    )
    require(
        not value["support_granted"]
        and not value["physical_motion_authority"],
        "parameter-set registry authority promotion",
    )
    if verify_sources:
        expected, expected_sets = build()
        require(
            value == expected and parameter_sets == expected_sets,
            "parameter-set registry differs from current verified inputs",
        )


def _transactional_write(
    value: dict[str, Any],
    parameter_sets: Mapping[str, dict[str, Any]],
) -> None:
    OUTPUT_ROOT.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=OUTPUT_ROOT.name + ".", dir=OUTPUT_ROOT.parent)
    )
    try:
        sets_directory = temporary / "sets"
        sets_directory.mkdir()
        (temporary / "registry.json").write_text(
            canonical_json(value), encoding="utf-8", newline="\n"
        )
        for plant_id, item in sorted(parameter_sets.items()):
            (sets_directory / f"{plant_id}.json").write_text(
                canonical_json(item), encoding="utf-8", newline="\n"
            )
        backup = OUTPUT_ROOT.with_name(OUTPUT_ROOT.name + ".old")
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


def check_or_write(*, check: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    value, parameter_sets = build()
    validate(value, parameter_sets, verify_sources=False)
    if check:
        require(
            OUTPUT_REGISTRY.is_file(),
            f"generated parameter-set registry missing: {OUTPUT_REGISTRY}",
        )
        require(
            OUTPUT_REGISTRY.read_text(encoding="utf-8")
            == canonical_json(value),
            "tracked parameter-set registry differs from verified inputs",
        )
        actual_paths = {
            path.stem: path
            for path in sorted(OUTPUT_SET_DIRECTORY.glob("*.json"))
        }
        require(
            set(actual_paths) == set(parameter_sets),
            "tracked parameter-set file set differs from materialization",
        )
        for plant_id, item in parameter_sets.items():
            require(
                actual_paths[plant_id].read_text(encoding="utf-8")
                == canonical_json(item),
                f"{plant_id}: tracked parameter-set bytes drift",
            )
    else:
        _transactional_write(value, parameter_sets)
    return value, parameter_sets


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    value, parameter_sets = check_or_write(check=args.check)
    print(
        "PASS plant parameter-set assembly verified: "
        f"facts={value['summary']['active_source_fact_count']} "
        f"complete_models={value['summary']['source_fact_complete_model_count']} "
        f"accepted_applicability="
        f"{value['summary']['accepted_protocol_applicability_count']} "
        f"sets={len(parameter_sets)} "
        f"generation={value['registry_generation_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
