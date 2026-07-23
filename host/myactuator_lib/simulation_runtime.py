"""Exact, generation-bound admission for MYACTUATOR simulation backends.

The catalog joins product, CAD, plant and Dropbear lifecycle evidence.  It
permits explicitly labelled replay/protocol/toy/synthetic execution while
keeping exact-model, whole-robot and physical fidelity fail-closed.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = (
    ROOT / "generated/myactuator/simulator/runtime_catalog.json"
)
DEFAULT_SCHEMA = (
    ROOT / "schemas/myactuator-simulator-runtime-catalog.schema.json"
)
DEFAULT_SOURCE_FILES = {
    "catalog_sha256": ROOT / "assets/myactuator/catalog.tsv",
    "protocol_applicability_registry_sha256": (
        ROOT / "generated/myactuator/protocol_applicability/registry.json"
    ),
    "cad_runtime_registry_sha256": (
        ROOT / "generated/myactuator/cad/runtime_asset_registry.json"
    ),
    "plant_runtime_registry_sha256": (
        ROOT / "generated/myactuator/plant/runtime_registry.json"
    ),
    "dropbear_simulator_projection_sha256": (
        ROOT
        / "generated/dropbear_graph_lifecycle_projection_v2/simulator.json"
    ),
}
EXACT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
MODEL_KEY = re.compile(r"^model-[0-9a-f]{20}$")
CONFIGURATION_ID = re.compile(r"^cadcfg-[0-9a-f]{20}$")
BACKEND_ID = re.compile(r"^[a-z][a-z0-9-]{2,127}$")
BACKEND_KIND = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN = re.compile(
    r"(?:^|[._+-])(?:all|any|current|default|latest|none|null|tbd|"
    r"unknown|unspecified)(?:$|[._+-])",
    re.IGNORECASE,
)


class SimulationRuntimeError(ValueError):
    """A simulation runtime catalog or exact selection is invalid."""


class SimulationAdmissionDenied(SimulationRuntimeError):
    """The selected backend/use case lacks the requested evidence."""


class SimulationUseCase(str, Enum):
    RECORDED_REPLAY = "recorded_replay"
    PROTOCOL_STATE_SIL = "protocol_state_sil"
    CATALOG_DEMO = "catalog_demo"
    SYNTHETIC_PLANT_SIL = "synthetic_plant_sil"
    EXACT_MODEL_PLANT_SIL = "exact_model_plant_sil"
    WHOLE_ROBOT_RIGID_BODY = "whole_robot_rigid_body"
    PHYSICAL_HIL = "physical_hil"


class SimulationAdmissionReason(str, Enum):
    ALLOWED = "allowed"
    STALE_CATALOG_GENERATION = "stale_catalog_generation"
    MODEL_NOT_FOUND = "model_not_found"
    MODEL_IDENTITY_MISMATCH = "model_identity_mismatch"
    CONFIGURATION_NOT_FOUND = "configuration_not_found"
    BACKEND_NOT_FOUND = "backend_not_found"
    BACKEND_KIND_MISMATCH = "backend_kind_mismatch"
    BACKEND_NOT_LOADABLE = "backend_not_loadable"
    USE_CASE_NOT_SUPPORTED = "use_case_not_supported"
    EXACT_MODEL_FIDELITY_UNAVAILABLE = "exact_model_fidelity_unavailable"
    PHYSICAL_VALIDATION_UNAVAILABLE = "physical_validation_unavailable"
    WHOLE_ROBOT_FIDELITY_UNAVAILABLE = "whole_robot_fidelity_unavailable"
    PHYSICAL_IO_DISABLED = "physical_io_disabled"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SimulationRuntimeError(message)


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SimulationRuntimeError(f"cannot load {path}: {error}") from error
    _require(isinstance(value, dict), f"{path}: JSON root must be an object")
    return value


def _digest(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return _sha(_canonical(payload))


def _exact(value: str, pattern: re.Pattern[str], label: str) -> None:
    _require(
        isinstance(value, str)
        and bool(pattern.fullmatch(value))
        and not FORBIDDEN.search(value),
        f"{label} must be exact",
    )


@dataclass(frozen=True)
class SimulationSelection:
    catalog_generation_sha256: str
    model_key: str
    series: str
    model: str
    configuration_id: str
    backend_id: str
    backend_kind: str
    use_case: SimulationUseCase
    require_exact_model_fidelity: bool
    require_physical_validation: bool
    require_dropbear_whole_robot: bool

    def __post_init__(self) -> None:
        _exact(
            self.catalog_generation_sha256,
            SHA256,
            "catalog generation",
        )
        _exact(self.model_key, MODEL_KEY, "model key")
        _exact(self.series, EXACT, "series")
        _exact(self.model, EXACT, "model")
        _exact(self.configuration_id, CONFIGURATION_ID, "configuration ID")
        _exact(self.backend_id, BACKEND_ID, "backend ID")
        _exact(self.backend_kind, BACKEND_KIND, "backend kind")
        _require(
            isinstance(self.use_case, SimulationUseCase),
            "use case must be typed",
        )
        for value, label in (
            (self.require_exact_model_fidelity, "exact-model requirement"),
            (self.require_physical_validation, "physical-validation requirement"),
            (self.require_dropbear_whole_robot, "whole-robot requirement"),
        ):
            _require(isinstance(value, bool), f"{label} must be bool")
        if self.require_physical_validation:
            _require(
                self.require_exact_model_fidelity,
                "physical validation requires exact-model fidelity",
            )
        if self.require_dropbear_whole_robot:
            _require(
                self.use_case is SimulationUseCase.WHOLE_ROBOT_RIGID_BODY,
                "whole-robot requirement must use the rigid-body use case",
            )


@dataclass(frozen=True)
class SimulationAdmission:
    allowed: bool
    reason: SimulationAdmissionReason
    blockers: tuple[str, ...]
    backend_id: str | None = None
    model_key: str | None = None
    command_capable: bool = False
    evidence_class: str | None = None
    exact_model_fidelity: bool = False
    physically_validated: bool = False
    physical_io: bool = False

    def require(self) -> "SimulationAdmission":
        if not self.allowed:
            raise SimulationAdmissionDenied(
                f"{self.reason.value}: {','.join(self.blockers)}"
            )
        return self


def _deny(
    reason: SimulationAdmissionReason,
    *blockers: str,
) -> SimulationAdmission:
    return SimulationAdmission(False, reason, tuple(blockers))


class SimulationRuntimeCatalog:
    """Independently validated, exact-query simulator runtime catalog."""

    def __init__(
        self,
        value: dict[str, Any],
        schema: dict[str, Any],
        *,
        source_files: dict[str, Path] | None = None,
    ) -> None:
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(value),
            key=lambda error: (list(error.absolute_path), error.message),
        )
        if errors:
            error = errors[0]
            raise SimulationRuntimeError(
                "simulator catalog schema failure at "
                f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
            )
        if (
            value["integrity"]["record_sha256"] != _digest(value)
            or value["support_granted"]
            or value["physical_motion_authority"]
            or value["physical_io_enabled"]
        ):
            raise SimulationRuntimeError(
                "simulator catalog digest/authority drift"
            )
        sources = source_files if source_files is not None else DEFAULT_SOURCE_FILES
        for source_id, path in sources.items():
            try:
                digest = _sha(path.read_bytes())
            except OSError as error:
                raise SimulationRuntimeError(
                    f"simulator catalog source unavailable: {source_id}: {error}"
                ) from error
            if value["sources"].get(source_id) != digest:
                raise SimulationRuntimeError(
                    f"simulator catalog source changed: {source_id}"
                )
        projection = _load(
            sources["dropbear_simulator_projection_sha256"]
        )
        applicability = _load(
            sources["protocol_applicability_registry_sha256"]
        )
        if (
            applicability.get("schema_version")
            != "myactuator-protocol-applicability-registry/2"
            or applicability.get("support_granted")
            or applicability.get("physical_motion_authority")
        ):
            raise SimulationRuntimeError(
                "simulator catalog applicability authority drift"
            )
        applicability_models = {
            (item["series"], item["model"]): item
            for item in applicability["models"]
        }
        if (
            value["sources"]["source_registry_generation_sha256"]
            != projection["subject"]["source_registry_generation_sha256"]
            or value["sources"]["graph_registry_generation_sha256"]
            != projection["subject"]["graph_registry_generation_sha256"]
            or value["dropbear"]["canonical_configuration_digest"]
            != projection["subject"]["canonical_configuration_digest"]
        ):
            raise SimulationRuntimeError(
                "simulator catalog Dropbear generation/configuration drift"
            )

        models: dict[str, dict[str, Any]] = {}
        identities: dict[tuple[str, str], str] = {}
        configurations: set[str] = set()
        variants: set[str] = set()
        for model in value["models"]:
            key = model["model_key"]
            identity = (model["series"], model["model"])
            if (
                key in models
                or identity in identities
                or configurations.intersection(model["configuration_ids"])
                or variants.intersection(model["source_variant_ids"])
            ):
                raise SimulationRuntimeError(
                    "simulator catalog duplicate model/configuration identity"
                )
            if model["fidelity"]["exact_model_simulation_ready"] is not (
                model["fidelity"]["exact_model_geometry_ready"]
                and model["fidelity"]["exact_model_plant_ready"]
            ):
                raise SimulationRuntimeError(
                    f"{key}: exact-model readiness relation drift"
                )
            if (
                model["source_step_runtime_asset"]
                or (
                    model["admitted_exact_model_backend_ids"]
                    and not model["fidelity"]["exact_model_simulation_ready"]
                )
            ):
                raise SimulationRuntimeError(
                    f"{key}: source/backend fidelity promotion"
                )
            applicability_model = applicability_models.get(identity)
            if applicability_model is None:
                raise SimulationRuntimeError(
                    f"{key}: exact applicability model missing"
                )
            applicability_verified = (
                applicability_model["applicability_status"] == "accepted"
                and bool(applicability_model["accepted_decision_ids"])
            )
            if (
                model["protocol_model_firmware_applicability_verified"]
                is not applicability_verified
            ):
                raise SimulationRuntimeError(
                    f"{key}: protocol applicability projection drift"
                )
            models[key] = copy.deepcopy(model)
            identities[identity] = key
            configurations.update(model["configuration_ids"])
            variants.update(model["source_variant_ids"])
        if (
            len(models) != 44
            or len(configurations) != 53
            or len(variants) != 53
            or value["summary"]["model_count"] != len(models)
            or value["summary"]["geometry_configuration_count"]
            != len(configurations)
            or value["summary"]["source_variant_count"] != len(variants)
        ):
            raise SimulationRuntimeError(
                "simulator catalog model/configuration count drift"
            )
        fidelity_summaries = (
            ("exact_model_geometry_ready_count", "exact_model_geometry_ready"),
            ("exact_model_plant_ready_count", "exact_model_plant_ready"),
            (
                "exact_model_simulation_ready_count",
                "exact_model_simulation_ready",
            ),
            (
                "physically_correlated_plant_count",
                "physically_correlated_plant_ready",
            ),
            (
                "browser_articulated_asset_ready_count",
                "browser_articulated_asset_ready",
            ),
        )
        for summary_name, fidelity_name in fidelity_summaries:
            if value["summary"][summary_name] != sum(
                model["fidelity"][fidelity_name]
                for model in models.values()
            ):
                raise SimulationRuntimeError(
                    f"simulator catalog {summary_name} drift"
                )

        backends = {
            item["backend_id"]: copy.deepcopy(item)
            for item in value["backends"]
        }
        if (
            len(backends) != len(value["backends"])
            or value["summary"]["backend_descriptor_count"] != len(backends)
            or value["summary"]["runtime_loadable_backend_count"]
            != sum(item["runtime_loadable"] for item in backends.values())
        ):
            raise SimulationRuntimeError(
                "simulator catalog backend identity/count drift"
            )
        for backend in backends.values():
            if backend["physical_io"]:
                raise SimulationRuntimeError(
                    "simulator catalog contains a physical-I/O backend"
                )
            if (
                backend["kind"] == "recorded_replay"
                and backend["command_capable"]
            ):
                raise SimulationRuntimeError(
                    "recorded replay is command-capable"
                )
            if (
                backend["kind"] in {"protocol_emulator", "toy_demo"}
                and backend["models_actuator_dynamics"]
            ):
                raise SimulationRuntimeError(
                    "protocol/toy backend claims actuator dynamics"
                )
            if (
                backend["kind"] == "synthetic_actuator_plant"
                and backend["exact_model_applicability_verified"]
            ):
                raise SimulationRuntimeError(
                    "synthetic plant claims exact-model applicability"
                )
            if backend["kind"] == "actuator_plant":
                if (
                    not backend["parameter_set_id"]
                    or not backend["runtime_contract_id"]
                ):
                    raise SimulationRuntimeError(
                        "actuator plant lacks parameter/runtime contract"
                    )
            elif (
                backend["parameter_set_id"] is not None
                or backend["runtime_contract_id"] is not None
            ):
                raise SimulationRuntimeError(
                    "non-plant backend references parameter/runtime contract"
                )
        dropbear = value["dropbear"]
        if dropbear["whole_robot_runtime_ready"] is not (
            dropbear["whole_robot_graph_ready"]
            and dropbear["whole_robot_cad_ready"]
            and dropbear["whole_robot_plant_ready"]
        ):
            raise SimulationRuntimeError(
                "Dropbear whole-robot readiness relation drift"
            )
        self._value = copy.deepcopy(value)
        self._models = models
        self._identities = identities
        self._backends = backends

    @classmethod
    def load(
        cls,
        catalog_path: Path = DEFAULT_CATALOG,
        schema_path: Path = DEFAULT_SCHEMA,
        *,
        source_files: dict[str, Path] | None = None,
    ) -> "SimulationRuntimeCatalog":
        return cls(
            _load(catalog_path),
            _load(schema_path),
            source_files=source_files,
        )

    @property
    def generation_sha256(self) -> str:
        return self._value["integrity"]["record_sha256"]

    @property
    def source_registry_generation_sha256(self) -> str:
        return self._value["sources"][
            "source_registry_generation_sha256"
        ]

    @property
    def graph_registry_generation_sha256(self) -> str:
        return self._value["sources"]["graph_registry_generation_sha256"]

    @property
    def model_count(self) -> int:
        return len(self._models)

    @property
    def backend_count(self) -> int:
        return len(self._backends)

    @property
    def dropbear_whole_robot_ready(self) -> bool:
        return self._value["dropbear"]["whole_robot_runtime_ready"]

    def dropbear_readiness(self) -> dict[str, Any]:
        return copy.deepcopy(self._value["dropbear"])

    def model(
        self,
        model_key: str,
        *,
        series: str,
        model: str,
    ) -> dict[str, Any]:
        _exact(model_key, MODEL_KEY, "model key")
        _exact(series, EXACT, "series")
        _exact(model, EXACT, "model")
        value = self._models.get(model_key)
        if value is None:
            raise SimulationRuntimeError("exact model key is not registered")
        if (value["series"], value["model"]) != (series, model):
            raise SimulationRuntimeError("model key/identity mismatch")
        return copy.deepcopy(value)

    def backend(self, backend_id: str, *, kind: str) -> dict[str, Any]:
        _exact(backend_id, BACKEND_ID, "backend ID")
        _exact(kind, BACKEND_KIND, "backend kind")
        value = self._backends.get(backend_id)
        if value is None:
            raise SimulationRuntimeError("exact backend ID is not registered")
        if value["kind"] != kind:
            raise SimulationRuntimeError("backend ID/kind mismatch")
        return copy.deepcopy(value)

    def admit(self, selection: SimulationSelection) -> SimulationAdmission:
        if selection.catalog_generation_sha256 != self.generation_sha256:
            return _deny(
                SimulationAdmissionReason.STALE_CATALOG_GENERATION,
                "catalog_generation_changed",
            )
        model = self._models.get(selection.model_key)
        if model is None:
            return _deny(
                SimulationAdmissionReason.MODEL_NOT_FOUND,
                "exact_model_key_not_registered",
            )
        if (model["series"], model["model"]) != (
            selection.series,
            selection.model,
        ):
            return _deny(
                SimulationAdmissionReason.MODEL_IDENTITY_MISMATCH,
                "model_key_series_model_disagree",
            )
        if selection.configuration_id not in model["configuration_ids"]:
            return _deny(
                SimulationAdmissionReason.CONFIGURATION_NOT_FOUND,
                "exact_configuration_not_owned_by_model",
            )
        backend = self._backends.get(selection.backend_id)
        if backend is None:
            return _deny(
                SimulationAdmissionReason.BACKEND_NOT_FOUND,
                "exact_backend_not_registered",
            )
        if backend["kind"] != selection.backend_kind:
            return _deny(
                SimulationAdmissionReason.BACKEND_KIND_MISMATCH,
                "backend_id_kind_disagree",
            )
        if not backend["runtime_loadable"]:
            return _deny(
                SimulationAdmissionReason.BACKEND_NOT_LOADABLE,
                *backend["blockers"],
            )
        if selection.use_case.value not in backend["allowed_use_cases"]:
            return _deny(
                SimulationAdmissionReason.USE_CASE_NOT_SUPPORTED,
                "backend_use_case_mismatch",
            )
        if selection.use_case is SimulationUseCase.PHYSICAL_HIL:
            return _deny(
                SimulationAdmissionReason.PHYSICAL_IO_DISABLED,
                "offline_simulator_catalog_has_no_physical_io",
            )
        if selection.require_dropbear_whole_robot and not (
            self.dropbear_whole_robot_ready
            and selection.use_case
            is SimulationUseCase.WHOLE_ROBOT_RIGID_BODY
        ):
            return _deny(
                SimulationAdmissionReason.WHOLE_ROBOT_FIDELITY_UNAVAILABLE,
                *self._value["dropbear"]["blockers"],
            )
        exact = (
            model["fidelity"]["exact_model_simulation_ready"]
            and backend["exact_model_applicability_verified"]
            and backend["backend_id"]
            in model["admitted_exact_model_backend_ids"]
        )
        if selection.require_exact_model_fidelity and not exact:
            return _deny(
                SimulationAdmissionReason.EXACT_MODEL_FIDELITY_UNAVAILABLE,
                *model["blockers"],
            )
        physical = (
            exact
            and model["fidelity"]["physically_correlated_plant_ready"]
            and backend["physically_validated"]
        )
        if selection.require_physical_validation and not physical:
            return _deny(
                SimulationAdmissionReason.PHYSICAL_VALIDATION_UNAVAILABLE,
                "physically_correlated_exact_model_backend_missing",
            )
        return SimulationAdmission(
            allowed=True,
            reason=SimulationAdmissionReason.ALLOWED,
            blockers=(),
            backend_id=backend["backend_id"],
            model_key=model["model_key"],
            command_capable=backend["command_capable"],
            evidence_class=backend["evidence_class"],
            exact_model_fidelity=exact,
            physically_validated=physical,
            physical_io=False,
        )


__all__ = [
    "SimulationAdmission",
    "SimulationAdmissionDenied",
    "SimulationAdmissionReason",
    "SimulationRuntimeCatalog",
    "SimulationRuntimeError",
    "SimulationSelection",
    "SimulationUseCase",
]
