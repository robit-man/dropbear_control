"""Reviewed sourced-plant adapter for the deterministic V2 equation core.

This module never chooses motor facts or grants hardware authority.  It binds
one immutable exact-tuple source set to one independently reviewed execution
profile and maps all 38 source semantics without the V1 approximations.
"""

from __future__ import annotations

import copy
import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from . import plant_runtime_adapter as v1
from .actuator_plant_v2 import (
    JITTER_ALGORITHM,
    NOISE_ALGORITHM,
    SOLVER_ID,
    PlantV2Configuration,
    PlantV2Error,
    PlantV2Parameters,
    PlantV2Semantics,
)


ADAPTER_ID = "plant-adapter-deterministic-event-scheduled-v2"
ADAPTER_VERSION = "myactuator-plant-runtime-contract/2"
PROFILE_VERSION = "myactuator-plant-runtime-profile/2"
ALL_SOURCE_FIELDS = v1.ALL_SOURCE_FIELDS

EXECUTION_FIELDS = (
    "torque_regime",
    "jitter_application",
    "supply_voltage_v",
    "ambient_temperature_k",
    "rotation_direction",
    "position_lower_rad",
    "position_upper_rad",
    "output_load_torque_bound_nm",
    "transmission_damping_nm_s_per_rad",
    "current_controller_kp_v_per_a",
    "winding_derate_start_temperature_k",
    "case_derate_start_temperature_k",
)

CONTRACT_FIELDS = {
    "schema_version",
    "contract_id",
    "backend_id",
    "plant_id",
    "runtime_adapter_id",
    "solver_id",
    "noise_algorithm",
    "jitter_algorithm",
    "applicability",
    "source_bindings",
    "execution",
    "engine_configuration",
    "source_semantics",
    "execution_choices",
    "validation",
    "support_granted",
    "physical_motion_authority",
    "physical_io",
    "integrity",
}


class PlantRuntimeAdapterV2Error(ValueError):
    """A V2 profile, source set, or generated contract is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PlantRuntimeAdapterV2Error(message)


def _finite(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{label} must be finite",
    )
    return float(value)


def _identifier(value: Any, label: str) -> str:
    try:
        return v1._identifier(value, label)
    except v1.PlantRuntimeAdapterError as error:
        raise PlantRuntimeAdapterV2Error(str(error)) from error


def _sha(value: Any, label: str) -> str:
    try:
        return v1._sha(value, label)
    except v1.PlantRuntimeAdapterError as error:
        raise PlantRuntimeAdapterV2Error(str(error)) from error


def canonical_bytes(value: Any) -> bytes:
    try:
        return v1.canonical_bytes(value)
    except v1.PlantRuntimeAdapterError as error:
        raise PlantRuntimeAdapterV2Error(str(error)) from error


def canonical_json(value: Any) -> str:
    return v1.canonical_json(value)


def sha_bytes(value: bytes) -> str:
    return v1.sha_bytes(value)


def _digest_payload(value: Mapping[str, Any]) -> bytes:
    payload = copy.deepcopy(dict(value))
    try:
        payload["integrity"]["record_sha256"] = "0" * 64
    except (KeyError, TypeError) as error:
        raise PlantRuntimeAdapterV2Error(
            "V2 runtime record integrity object is missing"
        ) from error
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(_digest_payload(value))


def validate_digest(value: Mapping[str, Any]) -> None:
    _require(
        isinstance(value.get("integrity"), Mapping)
        and value["integrity"].get("record_sha256")
        == sha_bytes(_digest_payload(value)),
        "V2 runtime contract digest drift",
    )


def _parameter(
    parameter_set: Mapping[str, Any],
    group: str,
    name: str,
) -> float:
    try:
        return v1._parameter(parameter_set, group, name)
    except v1.PlantRuntimeAdapterError as error:
        raise PlantRuntimeAdapterV2Error(str(error)) from error


def _envelope(
    parameter_set: Mapping[str, Any],
    name: str,
) -> tuple[float, float]:
    try:
        return v1._envelope(parameter_set, name)
    except v1.PlantRuntimeAdapterError as error:
        raise PlantRuntimeAdapterV2Error(str(error)) from error


def _profile_actor(value: Any, label: str, role: str) -> str:
    try:
        return v1._profile_actor(value, label, role)
    except v1.PlantRuntimeAdapterError as error:
        raise PlantRuntimeAdapterV2Error(str(error)) from error


def _source_semantics() -> list[dict[str, Any]]:
    targets = {
        "electrical.phase_resistance_ohm": [
            "phase_resistance_ohm"
        ],
        "electrical.phase_inductance_h": ["phase_inductance_h"],
        "electrical.torque_constant_nm_per_a": [
            "torque_constant_nm_per_a"
        ],
        "electrical.back_emf_v_s_per_rad": [
            "back_emf_v_s_per_rad"
        ],
        "electrical.max_qaxis_current_a": [
            "maximum_qaxis_current_a"
        ],
        "mechanical.rotor_inertia_kg_m2": [
            "rotor_inertia_kg_m2"
        ],
        "mechanical.output_inertia_kg_m2": [
            "output_inertia_kg_m2"
        ],
        "mechanical.coulomb_friction_nm": ["coulomb_friction_nm"],
        "mechanical.viscous_friction_nm_s_per_rad": [
            "viscous_friction_nm_s_per_rad"
        ],
        "transmission.ratio_motor_per_output": [
            "gear_ratio_motor_per_output"
        ],
        "transmission.forward_efficiency_ratio": [
            "forward_efficiency_ratio"
        ],
        "transmission.reverse_efficiency_ratio": [
            "reverse_efficiency_ratio"
        ],
        "transmission.torsional_stiffness_nm_per_rad": [
            "transmission_stiffness_nm_per_rad"
        ],
        "transmission.backlash_rad": ["backlash_rad"],
        "saturation.max_motor_speed_rad_s": [
            "maximum_motor_speed_rad_s"
        ],
        "saturation.max_output_speed_rad_s": [
            "maximum_output_speed_rad_s"
        ],
        "saturation.max_continuous_output_torque_nm": [
            "maximum_continuous_output_torque_nm"
        ],
        "saturation.max_peak_output_torque_nm": [
            "maximum_peak_output_torque_nm"
        ],
        "saturation.peak_duration_s": ["peak_duration_s"],
        "thermal.winding_resistance_k_per_w": [
            "winding_to_case_resistance_k_per_w"
        ],
        "thermal.case_resistance_k_per_w": [
            "case_to_ambient_resistance_k_per_w"
        ],
        "thermal.winding_heat_capacity_j_per_k": [
            "winding_thermal_capacity_j_per_k"
        ],
        "thermal.case_heat_capacity_j_per_k": [
            "case_thermal_capacity_j_per_k"
        ],
        "thermal.max_winding_temperature_k": [
            "maximum_winding_temperature_k"
        ],
        "thermal.max_case_temperature_k": [
            "maximum_case_temperature_k"
        ],
        "sensor.position_quantization_rad": [
            "position_quantum_rad"
        ],
        "sensor.position_noise_stddev_rad": [
            "position_noise_stddev_rad"
        ],
        "sensor.velocity_noise_stddev_rad_s": [
            "velocity_noise_stddev_rad_s"
        ],
        "sensor.current_noise_stddev_a": [
            "current_noise_stddev_a"
        ],
        "latency.command_delay_s": ["command_delay_s"],
        "latency.current_loop_period_s": [
            "current_loop_period_s"
        ],
        "latency.state_sample_period_s": [
            "state_sample_period_s"
        ],
        "latency.feedback_delay_s": ["feedback_delay_s"],
        "latency.delay_jitter_s": ["delay_jitter_s"],
        "operating_envelope.supply_voltage_v": [
            "supply_voltage_v"
        ],
        "operating_envelope.ambient_temperature_k": [
            "ambient_temperature_k"
        ],
        "operating_envelope.output_speed_rad_s": [
            "maximum_output_speed_rad_s"
        ],
        "operating_envelope.output_torque_nm": [
            "output_load_torque_bound_nm"
        ],
    }
    _require(
        tuple(targets) == ALL_SOURCE_FIELDS,
        "V2 source-semantic table order/closure drift",
    )
    envelope_fields = set(v1.ENVELOPE_FIELDS)
    return [
        {
            "field_id": field_id,
            "disposition": (
                "reviewed_envelope_selection_or_intersection"
                if field_id in envelope_fields
                else "direct_mapping"
            ),
            "engine_targets": targets[field_id],
        }
        for field_id in ALL_SOURCE_FIELDS
    ]


def _execution_choices() -> list[dict[str, str]]:
    return [
        {
            "field_id": field_id,
            "authority": "independently_reviewed_execution_profile",
        }
        for field_id in EXECUTION_FIELDS
    ]


def _validate_profile_and_source(
    parameter_set: Mapping[str, Any],
    profile: Mapping[str, Any],
    *,
    parameter_set_sha256: str,
    profile_sha256: str,
) -> tuple[str, str, Mapping[str, Any], Mapping[str, Any]]:
    _require(
        isinstance(parameter_set, Mapping)
        and isinstance(profile, Mapping),
        "V2 source set and profile must be objects",
    )
    _require(
        set(profile)
        == {
            "schema_version",
            "profile_id",
            "record_state",
            "subject",
            "execution",
            "review",
            "authority",
            "integrity",
        },
        "V2 runtime profile field closure drift",
    )
    validate_digest(profile)
    _require(
        sha_bytes(canonical_json(parameter_set).encode("utf-8"))
        == parameter_set_sha256,
        "parameter-set digest/content drift",
    )
    _require(
        sha_bytes(canonical_json(profile).encode("utf-8"))
        == profile_sha256,
        "runtime-profile digest/content drift",
    )
    _require(
        parameter_set.get("runtime_loadable") is False
        and parameter_set.get("runtime_adapter_id") is None,
        "upstream source set must remain non-loadable",
    )
    plant_id = _identifier(parameter_set.get("plant_id"), "plant_id")
    _require(
        profile.get("schema_version") == PROFILE_VERSION
        and profile.get("record_state") == "submitted",
        "V2 runtime profile identity/state mismatch",
    )
    profile_id = _identifier(profile.get("profile_id"), "profile_id")
    subject = profile.get("subject")
    _require(isinstance(subject, Mapping), "V2 runtime subject missing")
    _require(
        subject.get("plant_id") == plant_id
        and subject.get("parameter_set_sha256") == parameter_set_sha256
        and subject.get("adapter_id") == ADAPTER_ID
        and subject.get("assembly_registry_generation_sha256")
        == parameter_set["assembly"][
            "assembly_registry_generation_sha256"
        ],
        "V2 profile/source-set subject binding drift",
    )
    applicability = parameter_set.get("applicability")
    _require(
        isinstance(applicability, Mapping)
        and subject.get("applicability") == applicability,
        "V2 profile applicability binding drift",
    )
    review = profile.get("review")
    _require(
        isinstance(review, Mapping)
        and review.get("status") == "accepted"
        and isinstance(review.get("rationale"), str)
        and bool(review["rationale"].strip()),
        "V2 runtime profile is not accepted with rationale",
    )
    preparer = _profile_actor(
        review.get("prepared_by"),
        "review.prepared_by",
        "simulation_engineer",
    )
    reviewer = _profile_actor(
        review.get("reviewed_by"),
        "review.reviewed_by",
        "controls_safety_reviewer",
    )
    _require(preparer != reviewer, "V2 runtime review is not independent")
    _require(
        profile.get("authority")
        == {
            "support_granted": False,
            "physical_motion_authority": False,
            "physical_validation_claimed": False,
        },
        "V2 runtime profile grants forbidden authority",
    )
    execution = profile.get("execution")
    _require(
        isinstance(execution, Mapping)
        and set(execution) == set(EXECUTION_FIELDS),
        "V2 execution profile field closure drift",
    )
    return plant_id, profile_id, applicability, execution


def adapt(
    parameter_set: Mapping[str, Any],
    profile: Mapping[str, Any],
    *,
    parameter_set_sha256: str,
    profile_sha256: str,
    adapter_implementation_sha256: str,
    plant_implementation_sha256: str,
    profile_schema_sha256: str,
) -> dict[str, Any]:
    """Return one canonical V2 executable contract or fail closed."""

    for value, label in (
        (parameter_set_sha256, "parameter-set digest"),
        (profile_sha256, "runtime-profile digest"),
        (adapter_implementation_sha256, "adapter implementation digest"),
        (plant_implementation_sha256, "plant implementation digest"),
        (profile_schema_sha256, "profile schema digest"),
    ):
        _sha(value, label)
    plant_id, profile_id, applicability, execution = (
        _validate_profile_and_source(
            parameter_set,
            profile,
            parameter_set_sha256=parameter_set_sha256,
            profile_sha256=profile_sha256,
        )
    )

    torque_regime = execution["torque_regime"]
    jitter_application = execution["jitter_application"]
    direction = execution["rotation_direction"]
    _require(
        torque_regime
        in {"continuous_only", "peak_one_shot_per_reset"},
        "V2 torque regime is invalid",
    )
    _require(
        jitter_application
        in {"command_only", "feedback_only", "command_and_feedback"},
        "V2 jitter application is invalid",
    )
    _require(
        direction in {"positive", "negative", "bidirectional"},
        "V2 rotation direction is invalid",
    )
    supply = _finite(execution["supply_voltage_v"], "supply voltage")
    ambient = _finite(
        execution["ambient_temperature_k"],
        "ambient temperature",
    )
    position_lower = _finite(
        execution["position_lower_rad"],
        "position lower",
    )
    position_upper = _finite(
        execution["position_upper_rad"],
        "position upper",
    )
    load_bound = _finite(
        execution["output_load_torque_bound_nm"],
        "output load bound",
    )
    damping = _finite(
        execution["transmission_damping_nm_s_per_rad"],
        "transmission damping",
    )
    current_kp = _finite(
        execution["current_controller_kp_v_per_a"],
        "current-controller gain",
    )
    winding_derate = _finite(
        execution["winding_derate_start_temperature_k"],
        "winding derate start",
    )
    case_derate = _finite(
        execution["case_derate_start_temperature_k"],
        "case derate start",
    )
    _require(
        position_lower < 0.0 < position_upper
        and load_bound > 0.0
        and damping > 0.0
        and current_kp > 0.0,
        "V2 execution bounds/gains are invalid",
    )

    supply_range = _envelope(parameter_set, "supply_voltage_v")
    ambient_range = _envelope(parameter_set, "ambient_temperature_k")
    speed_range = _envelope(parameter_set, "output_speed_rad_s")
    torque_range = _envelope(parameter_set, "output_torque_nm")
    _require(
        supply_range[0] <= supply <= supply_range[1],
        "selected supply voltage is outside sourced envelope",
    )
    _require(
        ambient_range[0] <= ambient <= ambient_range[1],
        "selected ambient temperature is outside sourced envelope",
    )
    source_direction = parameter_set["operating_envelopes"][0][
        "rotation_direction"
    ]
    _require(
        source_direction == "bidirectional"
        or source_direction == direction,
        "selected direction is outside sourced envelope",
    )

    continuous_torque = _parameter(
        parameter_set,
        "saturation",
        "max_continuous_output_torque_nm",
    )
    peak_torque = _parameter(
        parameter_set,
        "saturation",
        "max_peak_output_torque_nm",
    )
    selected_torque_cap = (
        continuous_torque
        if torque_regime == "continuous_only"
        else peak_torque
    )
    envelope_torque_cap = max(
        abs(torque_range[0]),
        abs(torque_range[1]),
    )
    _require(
        load_bound <= min(selected_torque_cap, envelope_torque_cap),
        "V2 output-load bound exceeds selected sourced envelope",
    )
    source_output_speed = _parameter(
        parameter_set,
        "saturation",
        "max_output_speed_rad_s",
    )
    envelope_output_speed = max(
        abs(speed_range[0]),
        abs(speed_range[1]),
    )
    output_speed = min(source_output_speed, envelope_output_speed)
    _require(output_speed > 0.0, "V2 source speed intersection is empty")

    parameters = PlantV2Parameters(
        current_loop_period_s=_parameter(
            parameter_set,
            "latency",
            "current_loop_period_s",
        ),
        phase_resistance_ohm=_parameter(
            parameter_set,
            "electrical",
            "phase_resistance_ohm",
        ),
        phase_inductance_h=_parameter(
            parameter_set,
            "electrical",
            "phase_inductance_h",
        ),
        torque_constant_nm_per_a=_parameter(
            parameter_set,
            "electrical",
            "torque_constant_nm_per_a",
        ),
        back_emf_v_s_per_rad=_parameter(
            parameter_set,
            "electrical",
            "back_emf_v_s_per_rad",
        ),
        maximum_qaxis_current_a=_parameter(
            parameter_set,
            "electrical",
            "max_qaxis_current_a",
        ),
        rotor_inertia_kg_m2=_parameter(
            parameter_set,
            "mechanical",
            "rotor_inertia_kg_m2",
        ),
        output_inertia_kg_m2=_parameter(
            parameter_set,
            "mechanical",
            "output_inertia_kg_m2",
        ),
        coulomb_friction_nm=_parameter(
            parameter_set,
            "mechanical",
            "coulomb_friction_nm",
        ),
        viscous_friction_nm_s_per_rad=_parameter(
            parameter_set,
            "mechanical",
            "viscous_friction_nm_s_per_rad",
        ),
        gear_ratio_motor_per_output=_parameter(
            parameter_set,
            "transmission",
            "ratio_motor_per_output",
        ),
        forward_efficiency_ratio=_parameter(
            parameter_set,
            "transmission",
            "forward_efficiency_ratio",
        ),
        reverse_efficiency_ratio=_parameter(
            parameter_set,
            "transmission",
            "reverse_efficiency_ratio",
        ),
        transmission_stiffness_nm_per_rad=_parameter(
            parameter_set,
            "transmission",
            "torsional_stiffness_nm_per_rad",
        ),
        transmission_damping_nm_s_per_rad=damping,
        backlash_rad=_parameter(
            parameter_set,
            "transmission",
            "backlash_rad",
        ),
        maximum_motor_speed_rad_s=_parameter(
            parameter_set,
            "saturation",
            "max_motor_speed_rad_s",
        ),
        maximum_output_speed_rad_s=output_speed,
        maximum_continuous_output_torque_nm=continuous_torque,
        maximum_peak_output_torque_nm=peak_torque,
        peak_duration_s=_parameter(
            parameter_set,
            "saturation",
            "peak_duration_s",
        ),
        winding_to_case_resistance_k_per_w=_parameter(
            parameter_set,
            "thermal",
            "winding_resistance_k_per_w",
        ),
        case_to_ambient_resistance_k_per_w=_parameter(
            parameter_set,
            "thermal",
            "case_resistance_k_per_w",
        ),
        winding_thermal_capacity_j_per_k=_parameter(
            parameter_set,
            "thermal",
            "winding_heat_capacity_j_per_k",
        ),
        case_thermal_capacity_j_per_k=_parameter(
            parameter_set,
            "thermal",
            "case_heat_capacity_j_per_k",
        ),
        maximum_winding_temperature_k=_parameter(
            parameter_set,
            "thermal",
            "max_winding_temperature_k",
        ),
        maximum_case_temperature_k=_parameter(
            parameter_set,
            "thermal",
            "max_case_temperature_k",
        ),
        position_quantum_rad=_parameter(
            parameter_set,
            "sensor",
            "position_quantization_rad",
        ),
        position_noise_stddev_rad=_parameter(
            parameter_set,
            "sensor",
            "position_noise_stddev_rad",
        ),
        velocity_noise_stddev_rad_s=_parameter(
            parameter_set,
            "sensor",
            "velocity_noise_stddev_rad_s",
        ),
        current_noise_stddev_a=_parameter(
            parameter_set,
            "sensor",
            "current_noise_stddev_a",
        ),
        command_delay_s=_parameter(
            parameter_set,
            "latency",
            "command_delay_s",
        ),
        state_sample_period_s=_parameter(
            parameter_set,
            "latency",
            "state_sample_period_s",
        ),
        feedback_delay_s=_parameter(
            parameter_set,
            "latency",
            "feedback_delay_s",
        ),
        delay_jitter_s=_parameter(
            parameter_set,
            "latency",
            "delay_jitter_s",
        ),
        supply_voltage_v=supply,
        ambient_temperature_k=ambient,
        position_lower_rad=position_lower,
        position_upper_rad=position_upper,
        output_load_torque_bound_nm=load_bound,
        current_controller_kp_v_per_a=current_kp,
        winding_derate_start_temperature_k=winding_derate,
        case_derate_start_temperature_k=case_derate,
    )
    semantics = PlantV2Semantics(
        torque_regime=torque_regime,
        rotation_direction=direction,
        jitter_application=jitter_application,
    )
    configuration = PlantV2Configuration(
        parameter_set_id=plant_id,
        parameters=parameters,
        semantics=semantics,
    )
    try:
        configuration.validate()
    except PlantV2Error as error:
        raise PlantRuntimeAdapterV2Error(
            f"adapted V2 engine configuration is invalid: {error}"
        ) from error

    identity_payload = {
        "adapter_id": ADAPTER_ID,
        "parameter_set_sha256": parameter_set_sha256,
        "profile_id": profile_id,
        "profile_sha256": profile_sha256,
    }
    contract_id = "plantruntimev2-" + sha_bytes(
        canonical_bytes(identity_payload)
    )[:20]
    contract = {
        "schema_version": ADAPTER_VERSION,
        "contract_id": contract_id,
        "backend_id": f"actuator-v2-{plant_id}",
        "plant_id": plant_id,
        "runtime_adapter_id": ADAPTER_ID,
        "solver_id": SOLVER_ID,
        "noise_algorithm": NOISE_ALGORITHM,
        "jitter_algorithm": JITTER_ALGORITHM,
        "applicability": copy.deepcopy(dict(applicability)),
        "source_bindings": {
            "parameter_set_sha256": parameter_set_sha256,
            "assembly_registry_generation_sha256": parameter_set["assembly"][
                "assembly_registry_generation_sha256"
            ],
            "source_fact_set_sha256": parameter_set["assembly"][
                "source_fact_set_sha256"
            ],
            "profile_id": profile_id,
            "profile_sha256": profile_sha256,
            "profile_schema_sha256": profile_schema_sha256,
            "adapter_implementation_sha256": adapter_implementation_sha256,
            "plant_implementation_sha256": plant_implementation_sha256,
        },
        "execution": copy.deepcopy(dict(execution)),
        "engine_configuration": {
            "parameter_set_id": configuration.parameter_set_id,
            "parameters": asdict(configuration.parameters),
            "semantics": asdict(configuration.semantics),
            "configuration_sha256": configuration.configuration_sha256,
        },
        "source_semantics": _source_semantics(),
        "execution_choices": _execution_choices(),
        "validation": {
            "class": "source_only",
            "physically_validated": False,
            "exact_model_applicability_verified": True,
            "all_source_semantics_represented": True,
        },
        "support_granted": False,
        "physical_motion_authority": False,
        "physical_io": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(contract)
    return contract


@dataclass(frozen=True, slots=True)
class ExecutablePlantV2ParameterSet:
    contract_id: str
    backend_id: str
    plant_id: str
    applicability_tuple: tuple[str, ...]
    configuration: PlantV2Configuration
    provenance_refs: tuple[str, ...]


def load_contract(
    value: Mapping[str, Any],
) -> ExecutablePlantV2ParameterSet:
    """Validate a generated V2 contract and return typed engine input."""

    _require(
        isinstance(value, Mapping)
        and set(value) == CONTRACT_FIELDS
        and value.get("schema_version") == ADAPTER_VERSION,
        "V2 runtime contract version/field closure mismatch",
    )
    validate_digest(value)
    contract_id = _identifier(value["contract_id"], "contract_id")
    _require(
        contract_id.startswith("plantruntimev2-"),
        "V2 contract ID namespace drift",
    )
    backend_id = _identifier(value["backend_id"], "backend_id")
    plant_id = _identifier(value["plant_id"], "plant_id")
    _require(
        value["runtime_adapter_id"] == ADAPTER_ID
        and value["solver_id"] == SOLVER_ID
        and value["noise_algorithm"] == NOISE_ALGORITHM
        and value["jitter_algorithm"] == JITTER_ALGORITHM,
        "V2 runtime implementation identity mismatch",
    )
    _require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False
        and value["physical_io"] is False,
        "V2 runtime contract grants forbidden authority",
    )
    _require(
        value["validation"]
        == {
            "class": "source_only",
            "physically_validated": False,
            "exact_model_applicability_verified": True,
            "all_source_semantics_represented": True,
        },
        "V2 runtime validation class drift",
    )
    applicability = value["applicability"]
    order = (
        "series",
        "model",
        "hardware_revision",
        "drive_firmware",
        "protocol_version",
        "transport",
        "control_mode",
    )
    _require(
        isinstance(applicability, Mapping)
        and set(applicability) == set(order)
        and all(
            isinstance(applicability[name], str) and applicability[name]
            for name in order
        ),
        "V2 runtime applicability is incomplete",
    )
    _require(
        value["source_semantics"] == _source_semantics()
        and value["execution_choices"] == _execution_choices(),
        "V2 source/profile semantic accounting drift",
    )
    execution = value["execution"]
    _require(
        isinstance(execution, Mapping)
        and set(execution) == set(EXECUTION_FIELDS),
        "V2 execution field closure drift",
    )
    config_value = value["engine_configuration"]
    _require(
        isinstance(config_value, Mapping)
        and set(config_value)
        == {
            "parameter_set_id",
            "parameters",
            "semantics",
            "configuration_sha256",
        }
        and config_value["parameter_set_id"] == plant_id
        and isinstance(config_value["parameters"], Mapping)
        and set(config_value["parameters"])
        == set(PlantV2Parameters.__dataclass_fields__)
        and isinstance(config_value["semantics"], Mapping)
        and set(config_value["semantics"])
        == set(PlantV2Semantics.__dataclass_fields__),
        "V2 engine configuration closure/identity drift",
    )
    try:
        configuration = PlantV2Configuration(
            parameter_set_id=plant_id,
            parameters=PlantV2Parameters(**config_value["parameters"]),
            semantics=PlantV2Semantics(**config_value["semantics"]),
        )
        configuration.validate()
    except (PlantV2Error, TypeError, ValueError) as error:
        raise PlantRuntimeAdapterV2Error(
            f"V2 engine configuration is invalid: {error}"
        ) from error
    _require(
        config_value["configuration_sha256"]
        == configuration.configuration_sha256,
        "V2 engine configuration digest drift",
    )
    _require(
        execution["torque_regime"]
        == configuration.semantics.torque_regime
        and execution["jitter_application"]
        == configuration.semantics.jitter_application
        and execution["rotation_direction"]
        == configuration.semantics.rotation_direction
        and execution["supply_voltage_v"]
        == configuration.parameters.supply_voltage_v
        and execution["ambient_temperature_k"]
        == configuration.parameters.ambient_temperature_k
        and execution["position_lower_rad"]
        == configuration.parameters.position_lower_rad
        and execution["position_upper_rad"]
        == configuration.parameters.position_upper_rad
        and execution["output_load_torque_bound_nm"]
        == configuration.parameters.output_load_torque_bound_nm
        and execution["transmission_damping_nm_s_per_rad"]
        == configuration.parameters.transmission_damping_nm_s_per_rad
        and execution["current_controller_kp_v_per_a"]
        == configuration.parameters.current_controller_kp_v_per_a
        and execution["winding_derate_start_temperature_k"]
        == configuration.parameters.winding_derate_start_temperature_k
        and execution["case_derate_start_temperature_k"]
        == configuration.parameters.case_derate_start_temperature_k,
        "V2 execution/configuration binding drift",
    )
    bindings = value["source_bindings"]
    expected_bindings = {
        "parameter_set_sha256",
        "assembly_registry_generation_sha256",
        "source_fact_set_sha256",
        "profile_id",
        "profile_sha256",
        "profile_schema_sha256",
        "adapter_implementation_sha256",
        "plant_implementation_sha256",
    }
    _require(
        isinstance(bindings, Mapping)
        and set(bindings) == expected_bindings,
        "V2 source binding closure drift",
    )
    for name in expected_bindings - {"profile_id"}:
        _sha(bindings[name], f"source_bindings.{name}")
    profile_id = _identifier(bindings["profile_id"], "profile binding")
    return ExecutablePlantV2ParameterSet(
        contract_id=contract_id,
        backend_id=backend_id,
        plant_id=plant_id,
        applicability_tuple=tuple(
            applicability[name] for name in order
        ),
        configuration=configuration,
        provenance_refs=(
            f"runtime-contract-v2:{contract_id}",
            f"plant-parameter-set:{plant_id}",
            f"execution-profile-v2:{profile_id}",
            f"source-fact-set:{bindings['source_fact_set_sha256']}",
            f"solver:{SOLVER_ID}",
            f"noise:{NOISE_ALGORITHM}",
            f"jitter:{JITTER_ALGORITHM}",
        ),
    )


__all__ = [
    "ADAPTER_ID",
    "ADAPTER_VERSION",
    "ALL_SOURCE_FIELDS",
    "CONTRACT_FIELDS",
    "EXECUTION_FIELDS",
    "ExecutablePlantV2ParameterSet",
    "PlantRuntimeAdapterV2Error",
    "PROFILE_VERSION",
    "adapt",
    "canonical_bytes",
    "canonical_json",
    "load_contract",
    "set_digest",
    "sha_bytes",
    "validate_digest",
]
