"""Fail-closed sourced-plant to deterministic-engine adapter.

The adapter does not choose motor facts.  It combines one generated, reviewed
exact-tuple parameter set with one independently reviewed execution profile.
Only the subset exactly representable by the current fixed-step equation core
is admitted.  Unsupported noise, delay, direction, or operating-point
semantics are rejected instead of approximated.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .actuator_plant import PlantError, PlantParameters


ADAPTER_ID = "plant-adapter-deterministic-fixed-step-v1"
ADAPTER_VERSION = "myactuator-plant-runtime-contract/1"
SOLVER_ID = "semi-implicit-euler-fixed-step-v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{2,127}$")

PARAMETER_FIELDS = (
    "electrical.phase_resistance_ohm",
    "electrical.phase_inductance_h",
    "electrical.torque_constant_nm_per_a",
    "electrical.back_emf_v_s_per_rad",
    "electrical.max_qaxis_current_a",
    "mechanical.rotor_inertia_kg_m2",
    "mechanical.output_inertia_kg_m2",
    "mechanical.coulomb_friction_nm",
    "mechanical.viscous_friction_nm_s_per_rad",
    "transmission.ratio_motor_per_output",
    "transmission.forward_efficiency_ratio",
    "transmission.reverse_efficiency_ratio",
    "transmission.torsional_stiffness_nm_per_rad",
    "transmission.backlash_rad",
    "saturation.max_motor_speed_rad_s",
    "saturation.max_output_speed_rad_s",
    "saturation.max_continuous_output_torque_nm",
    "saturation.max_peak_output_torque_nm",
    "saturation.peak_duration_s",
    "thermal.winding_resistance_k_per_w",
    "thermal.case_resistance_k_per_w",
    "thermal.winding_heat_capacity_j_per_k",
    "thermal.case_heat_capacity_j_per_k",
    "thermal.max_winding_temperature_k",
    "thermal.max_case_temperature_k",
    "sensor.position_quantization_rad",
    "sensor.position_noise_stddev_rad",
    "sensor.velocity_noise_stddev_rad_s",
    "sensor.current_noise_stddev_a",
    "latency.command_delay_s",
    "latency.current_loop_period_s",
    "latency.state_sample_period_s",
    "latency.feedback_delay_s",
    "latency.delay_jitter_s",
)
ENVELOPE_FIELDS = (
    "operating_envelope.supply_voltage_v",
    "operating_envelope.ambient_temperature_k",
    "operating_envelope.output_speed_rad_s",
    "operating_envelope.output_torque_nm",
)
ALL_SOURCE_FIELDS = PARAMETER_FIELDS + ENVELOPE_FIELDS


class PlantRuntimeAdapterError(ValueError):
    """A runtime profile, source set, or generated contract is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PlantRuntimeAdapterError(message)


def _finite(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{label} must be finite",
    )
    return float(value)


def _identifier(value: Any, label: str) -> str:
    _require(
        isinstance(value, str) and bool(IDENTIFIER.fullmatch(value)),
        f"{label} must be an exact identifier",
    )
    return value


def _sha(value: Any, label: str) -> str:
    _require(
        isinstance(value, str) and bool(SHA256.fullmatch(value)),
        f"{label} must be sha256",
    )
    return value


def canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise PlantRuntimeAdapterError(
            "runtime-adapter value is not canonical JSON"
        ) from error


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    ) + "\n"


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_payload(value: Mapping[str, Any]) -> bytes:
    payload = copy.deepcopy(dict(value))
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(_digest_payload(value))


def validate_digest(value: Mapping[str, Any]) -> None:
    _require(
        isinstance(value.get("integrity"), Mapping)
        and value["integrity"].get("record_sha256")
        == sha_bytes(_digest_payload(value)),
        "runtime contract digest drift",
    )


def _parameter(
    parameter_set: Mapping[str, Any],
    group: str,
    name: str,
) -> float:
    try:
        record = parameter_set["parameters"][group][name]
    except (KeyError, TypeError) as error:
        raise PlantRuntimeAdapterError(
            f"missing source parameter {group}.{name}"
        ) from error
    _require(
        isinstance(record, Mapping),
        f"{group}.{name} source parameter must be an object",
    )
    return _finite(record.get("value"), f"{group}.{name}")


def _envelope(
    parameter_set: Mapping[str, Any],
    name: str,
) -> tuple[float, float]:
    try:
        records = parameter_set["operating_envelopes"]
        _require(
            isinstance(records, list) and len(records) == 1,
            "exactly one operating envelope is required",
        )
        record = records[0][name]
    except (KeyError, TypeError) as error:
        raise PlantRuntimeAdapterError(
            f"missing operating envelope {name}"
        ) from error
    _require(
        isinstance(record, Mapping),
        f"{name} operating envelope must be an object",
    )
    lower = _finite(record.get("minimum"), f"{name}.minimum")
    upper = _finite(record.get("maximum"), f"{name}.maximum")
    _require(lower <= upper, f"{name} operating envelope is reversed")
    return lower, upper


def _profile_actor(value: Any, label: str, role: str) -> str:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    _require(
        set(value) == {"actor_id", "actor_type", "role"},
        f"{label} field closure drift",
    )
    actor_id = _identifier(value["actor_id"], f"{label}.actor_id")
    _require(
        value["actor_type"] == "human" and value["role"] == role,
        f"{label} must be a human {role}",
    )
    return actor_id


def _source_semantics() -> list[dict[str, Any]]:
    direct = {
        "electrical.phase_resistance_ohm": ["phase_resistance_ohm"],
        "electrical.phase_inductance_h": ["phase_inductance_h"],
        "electrical.torque_constant_nm_per_a": ["torque_constant_nm_per_a"],
        "electrical.back_emf_v_s_per_rad": ["back_emf_v_s_per_rad"],
        "electrical.max_qaxis_current_a": ["maximum_qaxis_current_a"],
        "mechanical.rotor_inertia_kg_m2": ["rotor_inertia_kg_m2"],
        "mechanical.output_inertia_kg_m2": ["output_inertia_kg_m2"],
        "mechanical.coulomb_friction_nm": ["coulomb_friction_nm"],
        "mechanical.viscous_friction_nm_s_per_rad": [
            "viscous_friction_nm_s_per_rad"
        ],
        "transmission.ratio_motor_per_output": [
            "gear_ratio_motor_per_output"
        ],
        "transmission.torsional_stiffness_nm_per_rad": [
            "transmission_stiffness_nm_per_rad"
        ],
        "transmission.backlash_rad": ["backlash_rad"],
        "saturation.max_output_speed_rad_s": [
            "maximum_output_speed_rad_s"
        ],
        "saturation.max_continuous_output_torque_nm": [
            "maximum_output_torque_nm"
        ],
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
        "sensor.position_quantization_rad": ["position_quantum_rad"],
        "latency.current_loop_period_s": ["time_step_s"],
        "latency.feedback_delay_s": ["sensor_latency_steps"],
        "operating_envelope.supply_voltage_v": ["supply_voltage_v"],
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
    derived = {
        "transmission.forward_efficiency_ratio": ["gear_efficiency"],
        "transmission.reverse_efficiency_ratio": ["gear_efficiency"],
        "saturation.max_motor_speed_rad_s": [
            "maximum_motor_speed_guard_rad_s"
        ],
        "thermal.max_winding_temperature_k": [
            "shutdown_temperature_k"
        ],
        "thermal.max_case_temperature_k": [
            "maximum_case_temperature_guard_k"
        ],
    }
    guards = {
        "sensor.position_noise_stddev_rad",
        "sensor.velocity_noise_stddev_rad_s",
        "sensor.current_noise_stddev_a",
        "latency.command_delay_s",
        "latency.state_sample_period_s",
        "latency.delay_jitter_s",
    }
    excluded = {
        "saturation.max_peak_output_torque_nm",
        "saturation.peak_duration_s",
    }
    result: list[dict[str, Any]] = []
    for field_id in ALL_SOURCE_FIELDS:
        if field_id in direct:
            disposition = "direct_mapping"
            targets = direct[field_id]
        elif field_id in derived:
            disposition = "derived_or_runtime_guard"
            targets = derived[field_id]
        elif field_id in guards:
            disposition = "exact_representability_guard"
            targets = []
        else:
            _require(
                field_id in excluded,
                f"adapter source-semantic table omits {field_id}",
            )
            disposition = "excluded_by_continuous_only_profile"
            targets = []
        result.append(
            {
                "field_id": field_id,
                "disposition": disposition,
                "engine_targets": targets,
            }
        )
    return result


def adapt(
    parameter_set: Mapping[str, Any],
    profile: Mapping[str, Any],
    *,
    parameter_set_sha256: str,
    profile_sha256: str,
    adapter_implementation_sha256: str,
) -> dict[str, Any]:
    """Return one canonical executable contract or fail closed."""

    _sha(parameter_set_sha256, "parameter-set digest")
    _sha(profile_sha256, "runtime-profile digest")
    _sha(adapter_implementation_sha256, "adapter implementation digest")
    _require(
        parameter_set.get("runtime_loadable") is False
        and parameter_set.get("runtime_adapter_id") is None,
        "upstream source set must remain non-loadable",
    )
    plant_id = _identifier(parameter_set.get("plant_id"), "plant_id")
    _require(
        profile.get("schema_version")
        == "myactuator-plant-runtime-profile/1"
        and profile.get("record_state") == "submitted",
        "runtime profile identity/state mismatch",
    )
    profile_id = _identifier(profile.get("profile_id"), "profile_id")
    subject = profile.get("subject")
    _require(isinstance(subject, Mapping), "runtime profile subject missing")
    _require(
        subject.get("plant_id") == plant_id
        and subject.get("parameter_set_sha256") == parameter_set_sha256
        and subject.get("adapter_id") == ADAPTER_ID
        and subject.get("assembly_registry_generation_sha256")
        == parameter_set["assembly"][
            "assembly_registry_generation_sha256"
        ],
        "runtime profile/source-set subject binding drift",
    )
    applicability = parameter_set.get("applicability")
    _require(
        isinstance(applicability, Mapping)
        and subject.get("applicability") == applicability,
        "runtime profile applicability binding drift",
    )
    review = profile.get("review")
    _require(
        isinstance(review, Mapping)
        and review.get("status") == "accepted"
        and isinstance(review.get("rationale"), str)
        and bool(review["rationale"].strip()),
        "runtime profile is not accepted with rationale",
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
    _require(preparer != reviewer, "runtime-profile review is not independent")
    authority = profile.get("authority")
    _require(
        authority
        == {
            "support_granted": False,
            "physical_motion_authority": False,
            "physical_validation_claimed": False,
        },
        "runtime profile grants forbidden authority",
    )

    execution = profile.get("execution")
    _require(isinstance(execution, Mapping), "runtime execution profile missing")
    _require(
        execution.get("torque_regime") == "continuous_only",
        "current adapter only represents continuous-only torque",
    )
    supply = _finite(execution.get("supply_voltage_v"), "supply voltage")
    ambient = _finite(
        execution.get("ambient_temperature_k"),
        "ambient temperature",
    )
    direction = execution.get("rotation_direction")
    _require(
        direction in {"positive", "negative", "bidirectional"},
        "rotation direction is invalid",
    )
    position_lower = _finite(
        execution.get("position_lower_rad"),
        "position lower",
    )
    position_upper = _finite(
        execution.get("position_upper_rad"),
        "position upper",
    )
    _require(
        position_lower < 0.0 < position_upper,
        "execution position interval must contain the reset position",
    )
    output_load_bound = _finite(
        execution.get("output_load_torque_bound_nm"),
        "output load bound",
    )
    damping = _finite(
        execution.get("transmission_damping_nm_s_per_rad"),
        "transmission damping",
    )
    current_kp = _finite(
        execution.get("current_controller_kp_v_per_a"),
        "current-controller gain",
    )
    derate_start = _finite(
        execution.get("derate_start_temperature_k"),
        "derate start temperature",
    )
    _require(
        output_load_bound > 0.0 and damping > 0.0 and current_kp > 0.0,
        "execution bounds/gains must be positive",
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
    envelope_direction = parameter_set["operating_envelopes"][0][
        "rotation_direction"
    ]
    _require(
        envelope_direction == "bidirectional"
        or envelope_direction == direction,
        "selected direction is outside sourced envelope",
    )

    forward_efficiency = _parameter(
        parameter_set,
        "transmission",
        "forward_efficiency_ratio",
    )
    reverse_efficiency = _parameter(
        parameter_set,
        "transmission",
        "reverse_efficiency_ratio",
    )
    if direction == "positive":
        gear_efficiency = forward_efficiency
    elif direction == "negative":
        gear_efficiency = reverse_efficiency
    else:
        _require(
            forward_efficiency == reverse_efficiency,
            "bidirectional execution requires equal directional efficiencies",
        )
        gear_efficiency = forward_efficiency

    for group, name in (
        ("sensor", "position_noise_stddev_rad"),
        ("sensor", "velocity_noise_stddev_rad_s"),
        ("sensor", "current_noise_stddev_a"),
        ("latency", "command_delay_s"),
        ("latency", "delay_jitter_s"),
    ):
        _require(
            _parameter(parameter_set, group, name) == 0.0,
            f"{group}.{name} is not representable by adapter v1",
        )
    current_period = _parameter(
        parameter_set,
        "latency",
        "current_loop_period_s",
    )
    state_period = _parameter(
        parameter_set,
        "latency",
        "state_sample_period_s",
    )
    feedback_delay = _parameter(
        parameter_set,
        "latency",
        "feedback_delay_s",
    )
    _require(
        current_period > 0.0 and state_period == current_period,
        "adapter v1 requires state/current periods to be equal",
    )
    latency_ratio = feedback_delay / current_period
    latency_steps = round(latency_ratio)
    _require(
        latency_steps >= 0
        and math.isclose(
            latency_ratio,
            latency_steps,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ),
        "feedback delay must be an exact integer number of solver steps",
    )

    max_continuous_torque = _parameter(
        parameter_set,
        "saturation",
        "max_continuous_output_torque_nm",
    )
    torque_envelope_bound = max(abs(torque_range[0]), abs(torque_range[1]))
    _require(
        0.0 < output_load_bound
        <= min(max_continuous_torque, torque_envelope_bound),
        "execution output-load bound exceeds sourced continuous envelope",
    )
    source_max_speed = _parameter(
        parameter_set,
        "saturation",
        "max_output_speed_rad_s",
    )
    envelope_max_speed = max(abs(speed_range[0]), abs(speed_range[1]))
    maximum_output_speed = min(source_max_speed, envelope_max_speed)
    _require(maximum_output_speed > 0.0, "source speed intersection is empty")
    max_winding_temperature = _parameter(
        parameter_set,
        "thermal",
        "max_winding_temperature_k",
    )
    max_case_temperature = _parameter(
        parameter_set,
        "thermal",
        "max_case_temperature_k",
    )
    shutdown_temperature = min(
        max_winding_temperature,
        max_case_temperature,
    )
    _require(
        ambient < derate_start < shutdown_temperature,
        "thermal execution thresholds do not increase from ambient",
    )
    torque_constant = _parameter(
        parameter_set,
        "electrical",
        "torque_constant_nm_per_a",
    )
    maximum_current = _parameter(
        parameter_set,
        "electrical",
        "max_qaxis_current_a",
    )

    parameters = PlantParameters(
        time_step_s=current_period,
        phase_resistance_ohm=_parameter(
            parameter_set, "electrical", "phase_resistance_ohm"
        ),
        phase_inductance_h=_parameter(
            parameter_set, "electrical", "phase_inductance_h"
        ),
        torque_constant_nm_per_a=torque_constant,
        back_emf_v_s_per_rad=_parameter(
            parameter_set, "electrical", "back_emf_v_s_per_rad"
        ),
        rotor_inertia_kg_m2=_parameter(
            parameter_set, "mechanical", "rotor_inertia_kg_m2"
        ),
        output_inertia_kg_m2=_parameter(
            parameter_set, "mechanical", "output_inertia_kg_m2"
        ),
        gear_ratio_motor_per_output=_parameter(
            parameter_set, "transmission", "ratio_motor_per_output"
        ),
        gear_efficiency=gear_efficiency,
        transmission_stiffness_nm_per_rad=_parameter(
            parameter_set,
            "transmission",
            "torsional_stiffness_nm_per_rad",
        ),
        transmission_damping_nm_s_per_rad=damping,
        backlash_rad=_parameter(
            parameter_set, "transmission", "backlash_rad"
        ),
        coulomb_friction_nm=_parameter(
            parameter_set, "mechanical", "coulomb_friction_nm"
        ),
        viscous_friction_nm_s_per_rad=_parameter(
            parameter_set,
            "mechanical",
            "viscous_friction_nm_s_per_rad",
        ),
        supply_voltage_v=supply,
        maximum_qaxis_current_a=maximum_current,
        maximum_motor_torque_nm=torque_constant * maximum_current,
        maximum_output_torque_nm=max_continuous_torque,
        maximum_output_speed_rad_s=maximum_output_speed,
        position_lower_rad=position_lower,
        position_upper_rad=position_upper,
        current_controller_kp_v_per_a=current_kp,
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
        ambient_temperature_k=ambient,
        derate_start_temperature_k=derate_start,
        shutdown_temperature_k=shutdown_temperature,
        position_quantum_rad=_parameter(
            parameter_set,
            "sensor",
            "position_quantization_rad",
        ),
        velocity_quantum_rad_s=0.0,
        current_quantum_a=0.0,
        temperature_quantum_k=0.0,
        sensor_latency_steps=latency_steps,
    )
    try:
        parameters.validate()
    except PlantError as error:
        raise PlantRuntimeAdapterError(
            f"adapted engine parameters are invalid: {error}"
        ) from error
    semantics = _source_semantics()
    _require(
        [item["field_id"] for item in semantics]
        == list(ALL_SOURCE_FIELDS),
        "source-semantic accounting is not exact",
    )
    identity_payload = {
        "adapter_id": ADAPTER_ID,
        "parameter_set_sha256": parameter_set_sha256,
        "profile_id": profile_id,
        "profile_sha256": profile_sha256,
    }
    contract_id = "plantruntime-" + sha_bytes(
        canonical_bytes(identity_payload)
    )[:20]
    backend_id = f"actuator-{plant_id}"
    contract = {
        "schema_version": ADAPTER_VERSION,
        "contract_id": contract_id,
        "backend_id": backend_id,
        "plant_id": plant_id,
        "runtime_adapter_id": ADAPTER_ID,
        "solver_id": SOLVER_ID,
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
            "adapter_implementation_sha256": adapter_implementation_sha256,
        },
        "execution": copy.deepcopy(dict(execution)),
        "engine_parameters": asdict(parameters),
        "runtime_guards": {
            "maximum_motor_speed_rad_s": _parameter(
                parameter_set,
                "saturation",
                "max_motor_speed_rad_s",
            ),
            "maximum_case_temperature_k": max_case_temperature,
            "output_load_torque_bound_nm": output_load_bound,
            "rotation_direction": direction,
            "continuous_only": True,
        },
        "source_semantics": semantics,
        "validation": {
            "class": "source_only",
            "physically_validated": False,
            "exact_model_applicability_verified": True,
            "representability_restrictions_satisfied": True,
        },
        "support_granted": False,
        "physical_motion_authority": False,
        "physical_io": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(contract)
    return contract


@dataclass(frozen=True, slots=True)
class RuntimeGuards:
    maximum_motor_speed_rad_s: float
    maximum_case_temperature_k: float
    output_load_torque_bound_nm: float
    rotation_direction: str
    continuous_only: bool


@dataclass(frozen=True, slots=True)
class ExecutablePlantParameterSet:
    contract_id: str
    backend_id: str
    plant_id: str
    applicability_tuple: tuple[str, ...]
    parameters: PlantParameters
    guards: RuntimeGuards
    provenance_refs: tuple[str, ...]


def load_contract(value: Mapping[str, Any]) -> ExecutablePlantParameterSet:
    """Validate a generated contract and return its typed engine input."""

    _require(
        isinstance(value, Mapping)
        and value.get("schema_version") == ADAPTER_VERSION,
        "runtime contract version mismatch",
    )
    validate_digest(value)
    contract_id = _identifier(value.get("contract_id"), "contract_id")
    backend_id = _identifier(value.get("backend_id"), "backend_id")
    plant_id = _identifier(value.get("plant_id"), "plant_id")
    _require(
        value.get("runtime_adapter_id") == ADAPTER_ID
        and value.get("solver_id") == SOLVER_ID,
        "runtime contract implementation identity mismatch",
    )
    _require(
        value.get("support_granted") is False
        and value.get("physical_motion_authority") is False
        and value.get("physical_io") is False,
        "runtime contract grants forbidden authority",
    )
    validation = value.get("validation")
    _require(
        validation
        == {
            "class": "source_only",
            "physically_validated": False,
            "exact_model_applicability_verified": True,
            "representability_restrictions_satisfied": True,
        },
        "runtime contract validation class drift",
    )
    applicability = value.get("applicability")
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
        and all(isinstance(applicability[name], str) and applicability[name] for name in order),
        "runtime contract applicability is incomplete",
    )
    semantics = value.get("source_semantics")
    _require(
        isinstance(semantics, list)
        and [item.get("field_id") for item in semantics]
        == list(ALL_SOURCE_FIELDS)
        and semantics == _source_semantics(),
        "runtime contract source-semantic accounting drift",
    )
    parameter_value = value.get("engine_parameters")
    _require(
        isinstance(parameter_value, Mapping)
        and set(parameter_value) == set(PlantParameters.__dataclass_fields__),
        "runtime engine parameter closure drift",
    )
    parameters = PlantParameters(**parameter_value)
    try:
        parameters.validate()
    except PlantError as error:
        raise PlantRuntimeAdapterError(
            f"runtime engine parameters are invalid: {error}"
        ) from error
    guard_value = value.get("runtime_guards")
    _require(
        isinstance(guard_value, Mapping)
        and set(guard_value)
        == {
            "maximum_motor_speed_rad_s",
            "maximum_case_temperature_k",
            "output_load_torque_bound_nm",
            "rotation_direction",
            "continuous_only",
        },
        "runtime guard closure drift",
    )
    guards = RuntimeGuards(**guard_value)
    _require(
        guards.maximum_motor_speed_rad_s > 0.0
        and guards.maximum_case_temperature_k > parameters.ambient_temperature_k
        and guards.output_load_torque_bound_nm > 0.0
        and guards.rotation_direction
        in {"positive", "negative", "bidirectional"}
        and guards.continuous_only is True,
        "runtime guard semantics drift",
    )
    bindings = value.get("source_bindings")
    _require(isinstance(bindings, Mapping), "runtime source bindings missing")
    for name in (
        "parameter_set_sha256",
        "assembly_registry_generation_sha256",
        "source_fact_set_sha256",
        "profile_sha256",
        "adapter_implementation_sha256",
    ):
        _sha(bindings.get(name), f"source_bindings.{name}")
    profile_id = _identifier(bindings.get("profile_id"), "profile binding")
    return ExecutablePlantParameterSet(
        contract_id,
        backend_id,
        plant_id,
        tuple(applicability[name] for name in order),
        parameters,
        guards,
        (
            f"runtime-contract:{contract_id}",
            f"plant-parameter-set:{plant_id}",
            f"execution-profile:{profile_id}",
            f"source-fact-set:{bindings['source_fact_set_sha256']}",
            f"solver:{SOLVER_ID}",
        ),
    )


__all__ = [
    "ADAPTER_ID",
    "ADAPTER_VERSION",
    "ALL_SOURCE_FIELDS",
    "ExecutablePlantParameterSet",
    "PlantRuntimeAdapterError",
    "RuntimeGuards",
    "adapt",
    "canonical_bytes",
    "canonical_json",
    "load_contract",
    "set_digest",
    "sha_bytes",
    "validate_digest",
]
