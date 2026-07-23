"""Typed, fail-closed selection of simulation and actuator-plant backends.

Backends are selected by exact ID and expected kind.  An actuator plant also
requires the complete physical applicability tuple used by the support policy.
There is no family/default/latest fallback.  Resolving a sourced plant remains
SIL evidence and never grants permission to command hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import re
from pathlib import Path
from typing import Any, Mapping


REGISTRY_VERSION = "myactuator-plant-registry/4"
_FORBIDDEN_EXACT = re.compile(
    r"(?:^|[.\-_/])(?:all|any|default|latest|none|null|tbd|unknown|unspecified)(?:$|[.\-_/])",
    re.IGNORECASE,
)
_X_VERSION = re.compile(r"(?:^|[.\-_/])x(?:$|[.\-_/])", re.IGNORECASE)
_PARAMETER_GROUP_FIELDS = {
    "electrical": {
        "phase_resistance_ohm",
        "phase_inductance_h",
        "torque_constant_nm_per_a",
        "back_emf_v_s_per_rad",
        "max_qaxis_current_a",
    },
    "mechanical": {
        "rotor_inertia_kg_m2",
        "output_inertia_kg_m2",
        "coulomb_friction_nm",
        "viscous_friction_nm_s_per_rad",
    },
    "transmission": {
        "ratio_motor_per_output",
        "forward_efficiency_ratio",
        "reverse_efficiency_ratio",
        "torsional_stiffness_nm_per_rad",
        "backlash_rad",
    },
    "saturation": {
        "max_motor_speed_rad_s",
        "max_output_speed_rad_s",
        "max_continuous_output_torque_nm",
        "max_peak_output_torque_nm",
        "peak_duration_s",
    },
    "thermal": {
        "winding_resistance_k_per_w",
        "case_resistance_k_per_w",
        "winding_heat_capacity_j_per_k",
        "case_heat_capacity_j_per_k",
        "max_winding_temperature_k",
        "max_case_temperature_k",
    },
    "sensor": {
        "position_quantization_rad",
        "position_noise_stddev_rad",
        "velocity_noise_stddev_rad_s",
        "current_noise_stddev_a",
    },
    "latency": {
        "command_delay_s",
        "current_loop_period_s",
        "state_sample_period_s",
        "feedback_delay_s",
        "delay_jitter_s",
    },
}
_ENVELOPE_FIELDS = {
    "supply_voltage_v",
    "ambient_temperature_k",
    "output_speed_rad_s",
    "output_torque_nm",
}


class PlantRegistryError(ValueError):
    """The backend/parameter registry is malformed or weakens policy."""


class BackendKind(str, Enum):
    RECORDED_REPLAY = "recorded_replay"
    PROTOCOL_EMULATOR = "protocol_emulator"
    TOY_DEMO = "toy_demo"
    SYNTHETIC_ACTUATOR_PLANT = "synthetic_actuator_plant"
    ACTUATOR_PLANT = "actuator_plant"
    RIGID_BODY = "rigid_body"
    PHYSICAL_ADAPTER = "physical_adapter"


class BackendAdmissionReason(str, Enum):
    ALLOWED = "allowed"
    INVALID_REQUEST = "invalid_request"
    BACKEND_NOT_FOUND = "backend_not_found"
    BACKEND_KIND_MISMATCH = "backend_kind_mismatch"
    BACKEND_NOT_LOADABLE = "backend_not_loadable"
    PLANT_APPLICABILITY_REQUIRED = "plant_applicability_required"
    PLANT_APPLICABILITY_FORBIDDEN = "plant_applicability_forbidden"
    PARAMETER_SET_NOT_FOUND = "parameter_set_not_found"
    PLANT_APPLICABILITY_MISMATCH = "plant_applicability_mismatch"


@dataclass(frozen=True, slots=True)
class PlantApplicability:
    series: str
    model: str
    hardware_revision: str
    drive_firmware: str
    protocol_version: str
    transport: str
    control_mode: str

    def as_tuple(self) -> tuple[str, ...]:
        return (
            self.series,
            self.model,
            self.hardware_revision,
            self.drive_firmware,
            self.protocol_version,
            self.transport,
            self.control_mode,
        )


@dataclass(frozen=True, slots=True)
class SimulationBackend:
    backend_id: str
    kind: BackendKind
    evidence_class: str
    runtime_loadable: bool
    models_physical_dynamics: bool
    physically_validated: bool
    parameter_set_id: str | None
    runtime_contract_id: str | None
    substitution_scope: str


@dataclass(frozen=True, slots=True)
class BackendAdmission:
    allowed: bool
    reason: BackendAdmissionReason
    detail: str
    backend: SimulationBackend | None = None
    parameter_set: Mapping[str, Any] | None = None


def _deny(reason: BackendAdmissionReason, detail: str) -> BackendAdmission:
    return BackendAdmission(False, reason, detail)


def _exact(value: Any, *, reject_x_version: bool = False) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and value.casefold() != "current"
        and not any(character in value for character in "*?[]{}")
        and not _FORBIDDEN_EXACT.search(value)
        and (not reject_x_version or not _X_VERSION.search(value))
    )


class SimulationBackendRegistry:
    """Runtime view of explicit, evidence-labelled backend substitutions."""

    def __init__(self, registry: Mapping[str, Any]) -> None:
        if not isinstance(registry, Mapping):
            raise PlantRegistryError("plant registry root must be an object")
        self._registry = registry
        self._backends: dict[str, SimulationBackend] = {}
        self._parameter_sets: dict[str, Mapping[str, Any]] = {}
        self._validate()

    @classmethod
    def from_path(cls, path: Path) -> "SimulationBackendRegistry":
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise PlantRegistryError(f"cannot load plant registry {path}: {error}") from error
        return cls(value)

    @property
    def backend_ids(self) -> tuple[str, ...]:
        return tuple(self._backends)

    @property
    def parameter_set_count(self) -> int:
        return len(self._parameter_sets)

    def _validate(self) -> None:
        if self._registry.get("schema_version") != REGISTRY_VERSION:
            raise PlantRegistryError("plant registry schema version mismatch")
        policy = self._registry.get("policy")
        required_policy = (
            "exact_applicability_required",
            "parameter_source_required",
            "si_units_required",
            "bounded_uncertainty_required",
            "operating_envelope_required",
            "validation_class_required",
            "lifecycle_reviewed_facts_only",
            "accepted_protocol_applicability_required",
            "hand_authored_parameter_sets_forbidden",
            "exact_runtime_contract_required_for_loadability",
            "single_active_runtime_contract_across_adapter_versions",
            "unrepresentable_source_semantics_deny",
            "toy_is_never_physical_plant",
            "protocol_emulator_is_never_plant",
            "backend_substitution_must_be_explicit",
            "plant_does_not_grant_hardware_support",
        )
        if not isinstance(policy, Mapping) or any(policy.get(name) is not True for name in required_policy):
            raise PlantRegistryError("plant registry weakens a required policy")

        raw_sets = self._registry.get("parameter_sets")
        if not isinstance(raw_sets, list):
            raise PlantRegistryError("parameter_sets must be an array")
        exact_keys: set[tuple[str, ...]] = set()
        for value in raw_sets:
            if not isinstance(value, Mapping):
                raise PlantRegistryError("parameter set must be an object")
            plant_id = value.get("plant_id")
            applicability = value.get("applicability")
            if not _exact(plant_id) or plant_id in self._parameter_sets:
                raise PlantRegistryError("parameter-set IDs must be unique and exact")
            if not isinstance(applicability, Mapping):
                raise PlantRegistryError(f"{plant_id}: applicability is missing")
            fields = (
                "series", "model", "hardware_revision", "drive_firmware",
                "protocol_version", "transport", "control_mode",
            )
            exact_key = tuple(applicability.get(name) for name in fields)
            if not all(
                _exact(part, reject_x_version=index in {2, 3, 4})
                for index, part in enumerate(exact_key)
            ):
                raise PlantRegistryError(f"{plant_id}: applicability is not exact")
            if exact_key in exact_keys:
                raise PlantRegistryError(f"duplicate exact plant applicability {exact_key}")
            exact_keys.add(exact_key)
            if (
                not isinstance(value.get("runtime_loadable"), bool)
                or value.get("support_granted") is not False
                or (
                    value["runtime_loadable"]
                    and (
                        not _exact(value.get("runtime_adapter_id"))
                        or not _exact(value.get("runtime_contract_id"))
                    )
                )
                or (
                    not value["runtime_loadable"]
                    and (
                        value.get("runtime_adapter_id") is not None
                        or value.get("runtime_contract_id") is not None
                    )
                )
            ):
                raise PlantRegistryError(f"{plant_id}: invalid load/support state")
            contract_hashes = self._registry.get("source_hashes", {}).get(
                "runtime_contract_sha256"
            )
            if value["runtime_loadable"] and (
                not isinstance(contract_hashes, Mapping)
                or value["runtime_contract_id"] not in contract_hashes
            ):
                raise PlantRegistryError(
                    f"{plant_id}: runtime contract hash binding missing"
                )
            if value.get("physical_motion_authority") is not False:
                raise PlantRegistryError(
                    f"{plant_id}: parameter set grants physical authority"
                )
            assembly = value.get("assembly")
            if not isinstance(assembly, Mapping):
                raise PlantRegistryError(
                    f"{plant_id}: generated assembly evidence is missing"
                )
            fact_ids = assembly.get("source_fact_ids")
            fact_hashes = assembly.get("source_fact_sha256")
            decisions = assembly.get("accepted_protocol_decision_ids")
            if (
                not isinstance(fact_ids, list)
                or len(fact_ids) != 38
                or len(set(fact_ids)) != 38
                or not isinstance(fact_hashes, Mapping)
                or set(fact_hashes) != set(fact_ids)
                or not isinstance(decisions, list)
                or not decisions
                or len(decisions) != len(set(decisions))
                or assembly.get("physical_correlation_evidence_present")
                is not False
            ):
                raise PlantRegistryError(
                    f"{plant_id}: assembly fact/decision closure drift"
                )
            sources = value.get("sources")
            if (
                not isinstance(sources, list)
                or any(not isinstance(source, Mapping) for source in sources)
                or {
                    source.get("source_id")
                    for source in sources
                    if isinstance(source, Mapping)
                }
                != set(fact_ids)
                or any(
                    source.get("kind") != "reviewed_source_fact"
                    for source in sources
                    if isinstance(source, Mapping)
                )
            ):
                raise PlantRegistryError(
                    f"{plant_id}: reviewed source-fact closure drift"
                )
            parameters = value.get("parameters")
            if not isinstance(parameters, Mapping) or set(parameters) != set(
                _PARAMETER_GROUP_FIELDS
            ):
                raise PlantRegistryError(
                    f"{plant_id}: parameter group closure drift"
                )
            envelope_ids = {
                envelope.get("envelope_id")
                for envelope in value.get("operating_envelopes", [])
                if isinstance(envelope, Mapping)
            }
            if len(envelope_ids) != 1:
                raise PlantRegistryError(
                    f"{plant_id}: exactly one sourced envelope is required"
                )
            for group, names in _PARAMETER_GROUP_FIELDS.items():
                fields = parameters[group]
                if not isinstance(fields, Mapping) or set(fields) != names:
                    raise PlantRegistryError(
                        f"{plant_id}: {group} parameter closure drift"
                    )
                for parameter in fields.values():
                    if (
                        not isinstance(parameter, Mapping)
                        or len(parameter.get("source_refs", [])) != 1
                        or not set(parameter["source_refs"]) <= set(fact_ids)
                        or set(parameter.get("applicability_envelope_refs", []))
                        != envelope_ids
                    ):
                        raise PlantRegistryError(
                            f"{plant_id}: parameter provenance closure drift"
                        )
            envelopes = value.get("operating_envelopes")
            if not isinstance(envelopes, list) or len(envelopes) != 1:
                raise PlantRegistryError(
                    f"{plant_id}: operating envelope closure drift"
                )
            envelope = envelopes[0]
            if (
                not isinstance(envelope, Mapping)
                or not _ENVELOPE_FIELDS <= set(envelope)
            ):
                raise PlantRegistryError(
                    f"{plant_id}: operating envelope fields drift"
                )
            for name in _ENVELOPE_FIELDS:
                bounded = envelope[name]
                if (
                    not isinstance(bounded, Mapping)
                    or len(bounded.get("source_refs", [])) != 1
                    or not set(bounded["source_refs"]) <= set(fact_ids)
                ):
                    raise PlantRegistryError(
                        f"{plant_id}: envelope provenance closure drift"
                    )
            self._parameter_sets[str(plant_id)] = value

        raw_backends = self._registry.get("backends")
        if not isinstance(raw_backends, list):
            raise PlantRegistryError("backends must be an array")
        for value in raw_backends:
            if not isinstance(value, Mapping) or not _exact(value.get("backend_id")):
                raise PlantRegistryError("backend must have an exact ID")
            backend_id = str(value["backend_id"])
            if backend_id in self._backends:
                raise PlantRegistryError(f"duplicate backend ID {backend_id}")
            try:
                kind = BackendKind(value.get("kind"))
            except (TypeError, ValueError) as error:
                raise PlantRegistryError(f"{backend_id}: unknown backend kind") from error
            backend = SimulationBackend(
                backend_id=backend_id,
                kind=kind,
                evidence_class=str(value.get("evidence_class")),
                runtime_loadable=value.get("runtime_loadable") is True,
                models_physical_dynamics=value.get("models_physical_dynamics") is True,
                physically_validated=value.get("physically_validated") is True,
                parameter_set_id=value.get("parameter_set_id"),
                runtime_contract_id=value.get("runtime_contract_id"),
                substitution_scope=str(value.get("substitution_scope")),
            )
            if kind is BackendKind.ACTUATOR_PLANT:
                if (
                    not backend.models_physical_dynamics
                    or backend.parameter_set_id not in self._parameter_sets
                    or backend.runtime_contract_id
                    != self._parameter_sets[backend.parameter_set_id][
                        "runtime_contract_id"
                    ]
                    or backend.substitution_scope != "single-actuator-mechanics"
                ):
                    raise PlantRegistryError(f"{backend_id}: actuator plant is not bound to one valid parameter set")
            elif (
                backend.parameter_set_id is not None
                or backend.runtime_contract_id is not None
            ):
                raise PlantRegistryError(
                    f"{backend_id}: non-plant backend references plant parameters/contracts"
                )
            if kind in {BackendKind.TOY_DEMO, BackendKind.PROTOCOL_EMULATOR} and (
                backend.models_physical_dynamics or backend.physically_validated
            ):
                raise PlantRegistryError(f"{backend_id}: toy/protocol backend claims physical dynamics")
            if kind is BackendKind.RECORDED_REPLAY and (
                backend.models_physical_dynamics
                or backend.physically_validated
                or backend.substitution_scope != "host-state-replay-only"
            ):
                raise PlantRegistryError(
                    f"{backend_id}: recorded replay identity weakens read-only policy"
                )
            if kind is BackendKind.SYNTHETIC_ACTUATOR_PLANT and (
                not backend.models_physical_dynamics
                or backend.physically_validated
                or backend.parameter_set_id is not None
                or backend.runtime_contract_id is not None
                or backend.substitution_scope
                != "offline-controller-and-sil-tests-only"
            ):
                raise PlantRegistryError(
                    f"{backend_id}: synthetic plant identity weakens substitution policy"
                )
            if kind is BackendKind.RIGID_BODY and not backend.runtime_loadable and (
                backend.models_physical_dynamics
                or backend.physically_validated
                or backend.substitution_scope != "whole-robot-mechanics"
            ):
                raise PlantRegistryError(
                    f"{backend_id}: unavailable rigid-body descriptor claims fidelity"
                )
            self._backends[backend_id] = backend

        plant_backend_sets = {
            backend.parameter_set_id
            for backend in self._backends.values()
            if backend.kind is BackendKind.ACTUATOR_PLANT
        }
        runtime_parameter_sets = {
            identifier
            for identifier, value in self._parameter_sets.items()
            if value["runtime_loadable"]
        }
        if plant_backend_sets != runtime_parameter_sets:
            raise PlantRegistryError("actuator-plant backend/parameter-set parity mismatch")

    def resolve(
        self,
        backend_id: str,
        expected_kind: BackendKind,
        *,
        applicability: PlantApplicability | None = None,
    ) -> BackendAdmission:
        if not _exact(backend_id) or not isinstance(expected_kind, BackendKind):
            return _deny(BackendAdmissionReason.INVALID_REQUEST, "exact backend ID and typed expected kind are required")
        backend = self._backends.get(backend_id)
        if backend is None:
            return _deny(BackendAdmissionReason.BACKEND_NOT_FOUND, "backend ID is not registered; fallback is forbidden")
        if backend.kind is not expected_kind:
            return _deny(
                BackendAdmissionReason.BACKEND_KIND_MISMATCH,
                f"backend kind is {backend.kind.value}, not requested {expected_kind.value}",
            )
        if not backend.runtime_loadable:
            return _deny(BackendAdmissionReason.BACKEND_NOT_LOADABLE, "backend is recorded but not runtime loadable")
        if backend.kind is not BackendKind.ACTUATOR_PLANT:
            if applicability is not None:
                return _deny(
                    BackendAdmissionReason.PLANT_APPLICABILITY_FORBIDDEN,
                    "a non-plant backend cannot consume physical plant applicability",
                )
            return BackendAdmission(True, BackendAdmissionReason.ALLOWED, "exact typed backend admitted", backend)
        if not isinstance(applicability, PlantApplicability) or not all(
            _exact(value, reject_x_version=index in {2, 3, 4})
            for index, value in enumerate(applicability.as_tuple())
        ):
            return _deny(
                BackendAdmissionReason.PLANT_APPLICABILITY_REQUIRED,
                "complete exact series/model/hardware/firmware/protocol/transport/control-mode applicability is required",
            )
        parameter_set = self._parameter_sets.get(str(backend.parameter_set_id))
        if parameter_set is None:
            return _deny(BackendAdmissionReason.PARAMETER_SET_NOT_FOUND, "backend parameter set is unavailable")
        record = parameter_set["applicability"]
        actual = tuple(
            record[name]
            for name in (
                "series", "model", "hardware_revision", "drive_firmware",
                "protocol_version", "transport", "control_mode",
            )
        )
        if actual != applicability.as_tuple():
            return _deny(
                BackendAdmissionReason.PLANT_APPLICABILITY_MISMATCH,
                "exact plant applicability mismatch; model/family fallback is forbidden",
            )
        return BackendAdmission(
            True,
            BackendAdmissionReason.ALLOWED,
            "exact sourced plant backend admitted for SIL only; hardware support remains separate",
            backend,
            parameter_set,
        )


__all__ = [
    "BackendAdmission",
    "BackendAdmissionReason",
    "BackendKind",
    "PlantApplicability",
    "PlantRegistryError",
    "SimulationBackend",
    "SimulationBackendRegistry",
]
