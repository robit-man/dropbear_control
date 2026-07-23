"""Exact, source-bound MYACTUATOR protocol applicability admission.

The generated baseline is a candidate-source index, not a compatibility
matrix.  It retains every vendor PDF occurrence and denies all exact
model/hardware/firmware/protocol selections until an independent accepted
applicability decision exists.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .protocol_applicability_decision import (
    ProtocolApplicabilityDecisionError,
    load_directory as load_decision_directory,
    validate as validate_applicability_decision,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = (
    ROOT / "generated/myactuator/protocol_applicability/registry.json"
)
DEFAULT_SCHEMA = (
    ROOT / "schemas/myactuator-protocol-applicability-registry.schema.json"
)
DEFAULT_DECISION_DIRECTORY = (
    ROOT / "assets/myactuator/protocol_applicability/decisions"
)
DEFAULT_SOURCE_FILES = {
    "catalog_sha256": ROOT / "assets/myactuator/catalog.tsv",
    "documents_sha256": ROOT / "assets/myactuator/documents.tsv",
    "document_archives_sha256": (
        ROOT / "assets/myactuator/document_archives.tsv"
    ),
    "document_files_sha256": ROOT / "assets/myactuator/document_files.tsv",
    "source_claims_sha256": (
        ROOT / "assets/myactuator/protocol_applicability/source_claims.tsv"
    ),
}
EXACT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:/ -]{0,255}$")
MODEL_KEY = re.compile(r"^model-[0-9a-f]{20}$")
OCCURRENCE_ID = re.compile(r"^dococc-[0-9a-f]{20}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN = re.compile(
    r"(?:^|[._+:/ -])(?:all|any|current|default|latest|none|null|tbd|"
    r"unknown|unspecified)(?:$|[._+:/ -])",
    re.IGNORECASE,
)
PROTOCOL_SCOPES = {"motor_motion_protocol", "fieldbus_protocol"}
EXPECTED_SCOPE_COUNTS = {
    "drive_manual": 3,
    "fieldbus_protocol": 3,
    "motor_motion_protocol": 7,
    "product_manual": 15,
    "sensor_interface": 3,
    "setup_manual": 1,
}


class ProtocolApplicabilityError(ValueError):
    """The registry or an exact query is invalid."""


class ProtocolApplicabilityDenied(ProtocolApplicabilityError):
    """The requested exact tuple has no accepted applicability evidence."""


class ProtocolAdmissionReason(str, Enum):
    ALLOWED = "allowed"
    STALE_REGISTRY_GENERATION = "stale_registry_generation"
    MODEL_NOT_FOUND = "model_not_found"
    MODEL_IDENTITY_MISMATCH = "model_identity_mismatch"
    PROTOCOL_SOURCE_NOT_CANDIDATE = "protocol_source_not_candidate"
    PROTOCOL_SCOPE_INVALID = "protocol_scope_invalid"
    PROTOCOL_IDENTITY_MISMATCH = "protocol_identity_mismatch"
    TRANSPORT_NOT_DECLARED = "transport_not_declared"
    NO_ACCEPTED_APPLICABILITY = "no_accepted_applicability"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolApplicabilityError(message)


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProtocolApplicabilityError(f"cannot load {path}: {error}") from error
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


def _model_key(series: str, model: str) -> str:
    return "model-" + _sha(
        _canonical({"model": model, "series": series})
    )[:20]


def _candidate_document_sets(series: str, model: str) -> list[str]:
    if series == "RMD-X" and model.startswith("X"):
        return [
            "X-V2-protocol-manual",
            "X-V3-protocol-manual",
            "X-V4-protocol-manual",
        ]
    if series == "RH" and model.startswith("RH-"):
        return ["RH-dual-encoder-V4.4"]
    if series == "RMD-L" and model.startswith("L-"):
        return ["L-V3-protocol-manual"]
    if series == "CEM" and model.startswith("CEM-"):
        return ["CEM-protocol-manual"]
    if series == "RMD-H" and model.startswith("H-"):
        return ["H-S3-protocol-manual"]
    if series == "FL-FLO" and model.startswith("FL-"):
        return ["FL-user-manual"]
    if series == "FL-FLO" and model.startswith("FLO-"):
        return ["FLO-user-manual"]
    raise ProtocolApplicabilityError(
        f"{series}/{model}: no exact candidate source rule"
    )


@dataclass(frozen=True)
class ProtocolApplicabilitySelection:
    registry_generation_sha256: str
    model_key: str
    series: str
    model: str
    protocol_occurrence_id: str
    hardware_revision: str
    drive_firmware: str
    protocol_revision: str
    transport: str
    control_mode: str
    installed_unit_id: str

    def __post_init__(self) -> None:
        _exact(
            self.registry_generation_sha256,
            SHA256,
            "registry generation",
        )
        _exact(self.model_key, MODEL_KEY, "model key")
        _exact(self.series, EXACT, "series")
        _exact(self.model, EXACT, "model")
        _exact(
            self.protocol_occurrence_id,
            OCCURRENCE_ID,
            "protocol occurrence ID",
        )
        _exact(self.hardware_revision, EXACT, "hardware revision")
        _exact(self.drive_firmware, EXACT, "drive firmware")
        _exact(self.protocol_revision, EXACT, "protocol revision")
        _exact(self.transport, EXACT, "transport")
        _exact(self.control_mode, EXACT, "control mode")
        _exact(self.installed_unit_id, EXACT, "installed unit ID")


@dataclass(frozen=True)
class ProtocolAdmission:
    allowed: bool
    reason: ProtocolAdmissionReason
    blockers: tuple[str, ...]
    model_key: str | None = None
    protocol_occurrence_id: str | None = None
    decision_id: str | None = None
    support_granted: bool = False
    physical_motion_authority: bool = False

    def require(self) -> "ProtocolAdmission":
        if not self.allowed:
            raise ProtocolApplicabilityDenied(
                f"{self.reason.value}: {','.join(self.blockers)}"
            )
        return self


def _deny(
    reason: ProtocolAdmissionReason,
    *blockers: str,
) -> ProtocolAdmission:
    return ProtocolAdmission(False, reason, tuple(blockers))


class ProtocolApplicabilityRegistry:
    """Independently validates and queries the exact-tuple registry."""

    def __init__(
        self,
        value: dict[str, Any],
        schema: dict[str, Any],
        *,
        source_files: dict[str, Path] | None = None,
        decision_directory: Path | None = DEFAULT_DECISION_DIRECTORY,
    ) -> None:
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(value),
            key=lambda error: (list(error.absolute_path), error.message),
        )
        if errors:
            error = errors[0]
            raise ProtocolApplicabilityError(
                "applicability registry schema failure at "
                f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
            )
        if (
            value["integrity"]["record_sha256"] != _digest(value)
            or value["support_granted"]
            or value["physical_motion_authority"]
        ):
            raise ProtocolApplicabilityError(
                "applicability registry digest/authority drift"
            )
        sources = source_files if source_files is not None else DEFAULT_SOURCE_FILES
        _require(
            set(sources) == set(DEFAULT_SOURCE_FILES),
            "applicability source set drift",
        )
        for source_id, path in sources.items():
            try:
                digest = _sha(path.read_bytes())
            except OSError as error:
                raise ProtocolApplicabilityError(
                    f"applicability source unavailable: {source_id}: {error}"
                ) from error
            if value["sources"].get(source_id) != digest:
                raise ProtocolApplicabilityError(
                    f"applicability source changed: {source_id}"
                )

        packages = {
            item["package_id"]: copy.deepcopy(item)
            for item in value["document_packages"]
        }
        occurrences = {
            item["occurrence_id"]: copy.deepcopy(item)
            for item in value["document_file_occurrences"]
        }
        models = {
            item["model_key"]: copy.deepcopy(item)
            for item in value["models"]
        }
        if (
            len(packages) != 9
            or len(occurrences) != 32
            or len(models) != 44
            or len(packages) != len(value["document_packages"])
            or len(occurrences) != len(value["document_file_occurrences"])
            or len(models) != len(value["models"])
        ):
            raise ProtocolApplicabilityError(
                "applicability registry identity/count drift"
            )
        listed = [
            identifier
            for package in packages.values()
            for identifier in package["file_occurrence_ids"]
        ]
        if (
            len(listed) != 32
            or len(set(listed)) != 32
            or set(listed) != set(occurrences)
        ):
            raise ProtocolApplicabilityError(
                "document occurrences are not partitioned exactly once"
            )
        for occurrence in occurrences.values():
            package = packages.get(occurrence["package_id"])
            if package is None or (
                occurrence["series"],
                occurrence["document_set"],
            ) != (package["series"], package["document_set"]):
                raise ProtocolApplicabilityError(
                    f"{occurrence['occurrence_id']}: package identity drift"
                )
            claim = occurrence["source_claim"]
            if (
                claim["human_reviewed"]
                or claim["applicability_authority"]
                or (
                    claim["document_scope"] == "sensor_interface"
                    and claim["command_scope"]
                    != "sensor_electrical_interface"
                )
            ):
                raise ProtocolApplicabilityError(
                    f"{occurrence['occurrence_id']}: source scope promotion"
                )

        identities: dict[tuple[str, str], str] = {}
        for model_key, model in models.items():
            identity = (model["series"], model["model"])
            if (
                model_key != _model_key(*identity)
                or identity in identities
                or model["support_granted"]
            ):
                raise ProtocolApplicabilityError(
                    f"{model_key}: model identity/applicability promotion"
                )
            expected_sets = _candidate_document_sets(*identity)
            try:
                actual_sets = [
                    packages[identifier]["document_set"]
                    for identifier in model["candidate_package_ids"]
                ]
            except KeyError as error:
                raise ProtocolApplicabilityError(
                    f"{model_key}: candidate package is absent"
                ) from error
            if actual_sets != expected_sets:
                raise ProtocolApplicabilityError(
                    f"{model_key}: candidate source fallback/drift"
                )
            for package_id in model["candidate_package_ids"]:
                if model_key not in packages[package_id]["candidate_model_keys"]:
                    raise ProtocolApplicabilityError(
                        f"{model_key}: asymmetric package relation"
                    )
            for occurrence_id in model["candidate_protocol_occurrence_ids"]:
                occurrence = occurrences.get(occurrence_id)
                if (
                    occurrence is None
                    or occurrence["package_id"]
                    not in model["candidate_package_ids"]
                    or occurrence["source_claim"]["document_scope"]
                    not in PROTOCOL_SCOPES
                ):
                    raise ProtocolApplicabilityError(
                        f"{model_key}: cross-package/non-protocol candidate"
                    )
            identities[identity] = model_key
        for package in packages.values():
            if len(package["candidate_model_keys"]) != len(
                set(package["candidate_model_keys"])
            ):
                raise ProtocolApplicabilityError(
                    f"{package['package_id']}: duplicate candidate model"
                )
            for model_key in package["candidate_model_keys"]:
                if (
                    model_key not in models
                    or package["package_id"]
                    not in models[model_key]["candidate_package_ids"]
                ):
                    raise ProtocolApplicabilityError(
                        f"{package['package_id']}: asymmetric model relation"
                    )

        scopes = Counter(
            item["source_claim"]["document_scope"]
            for item in occurrences.values()
        )
        decisions = value["accepted_applicability_decisions"]
        decision_ids = [item["decision_id"] for item in decisions]
        if len(decision_ids) != len(set(decision_ids)):
            raise ProtocolApplicabilityError(
                "accepted applicability decision identity is not unique"
            )
        accepted_by_model: dict[str, list[str]] = {}
        for decision in decisions:
            subject = decision.get("subject", {})
            decision_model = models.get(subject.get("model_key"))
            occurrence = occurrences.get(subject.get("protocol_occurrence_id"))
            package = packages.get(subject.get("package_id"))
            if decision_model is None or occurrence is None or package is None:
                raise ProtocolApplicabilityError(
                    "accepted applicability decision source join is incomplete"
                )
            try:
                validate_applicability_decision(
                    decision,
                    decision_model,
                    occurrence,
                    package,
                )
            except ProtocolApplicabilityDecisionError as error:
                raise ProtocolApplicabilityError(str(error)) from error
            if (
                decision["record_state"] != "submitted"
                or decision["review"]["status"] != "accepted"
                or not decision["applicability_established"]
            ):
                raise ProtocolApplicabilityError(
                    "registry embeds a non-accepted applicability decision"
                )
            accepted_by_model.setdefault(
                subject["model_key"], []
            ).append(decision["decision_id"])
        for model_key, model in models.items():
            identifiers = sorted(accepted_by_model.get(model_key, []))
            if model["accepted_decision_ids"] != identifiers:
                raise ProtocolApplicabilityError(
                    f"{model_key}: accepted decision projection drift"
                )
            if identifiers:
                expected_status = "accepted"
                expected_blockers = [
                    "applicability_is_exact_tuple_scoped",
                    "complete_motor_support_not_granted",
                    "physical_motion_authority_not_granted",
                ]
            else:
                expected_status = "unsupported"
                expected_blockers = [
                    "exact_hardware_revision_missing",
                    "exact_drive_firmware_missing",
                    "independent_applicability_decision_missing",
                ]
                if not model["candidate_protocol_occurrence_ids"]:
                    expected_blockers.append(
                        "candidate_motor_control_protocol_source_missing"
                    )
            if (
                model["applicability_status"] != expected_status
                or model["blockers"] != expected_blockers
            ):
                raise ProtocolApplicabilityError(
                    f"{model_key}: applicability state projection drift"
                )
        if decision_directory is not None:
            try:
                submitted, hashes = load_decision_directory(
                    decision_directory,
                    models,
                    occurrences,
                    packages,
                )
            except ProtocolApplicabilityDecisionError as error:
                raise ProtocolApplicabilityError(str(error)) from error
            accepted = sorted(
                (
                    item
                    for item in submitted
                    if item["review"]["status"] == "accepted"
                ),
                key=lambda item: item["decision_id"],
            )
            if (
                value["sources"]["decision_file_sha256"] != hashes
                or decisions != accepted
            ):
                raise ProtocolApplicabilityError(
                    "applicability decision directory/hash projection drift"
                )
        expected_summary = {
            "model_count": len(models),
            "document_package_count": len(packages),
            "document_file_occurrence_count": len(occurrences),
            "unique_document_file_count": len(
                {item["file_sha256"] for item in occurrences.values()}
            ),
            "candidate_model_package_relationship_count": sum(
                len(item["candidate_package_ids"]) for item in models.values()
            ),
            "candidate_model_protocol_relationship_count": sum(
                len(item["candidate_protocol_occurrence_ids"])
                for item in models.values()
            ),
            "source_claim_scope_counts": dict(sorted(scopes.items())),
            "accepted_applicability_count": len(decisions),
            "accepted_model_count": len(accepted_by_model),
            "supported_model_count": 0,
        }
        if (
            dict(sorted(scopes.items())) != EXPECTED_SCOPE_COUNTS
            or value["summary"] != expected_summary
        ):
            raise ProtocolApplicabilityError(
                "applicability registry summary/scope drift"
            )
        self._value = copy.deepcopy(value)
        self._packages = packages
        self._occurrences = occurrences
        self._models = models
        self._identities = identities
        self._decisions = copy.deepcopy(decisions)

    @classmethod
    def load(
        cls,
        registry_path: Path = DEFAULT_REGISTRY,
        schema_path: Path = DEFAULT_SCHEMA,
        *,
        source_files: dict[str, Path] | None = None,
        decision_directory: Path | None = DEFAULT_DECISION_DIRECTORY,
    ) -> "ProtocolApplicabilityRegistry":
        return cls(
            _load(registry_path),
            _load(schema_path),
            source_files=source_files,
            decision_directory=decision_directory,
        )

    @property
    def generation_sha256(self) -> str:
        return self._value["integrity"]["record_sha256"]

    @property
    def model_count(self) -> int:
        return len(self._models)

    @property
    def package_count(self) -> int:
        return len(self._packages)

    @property
    def file_occurrence_count(self) -> int:
        return len(self._occurrences)

    @property
    def accepted_applicability_count(self) -> int:
        return len(self._decisions)

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
            raise ProtocolApplicabilityError("exact model key is not registered")
        if (value["series"], value["model"]) != (series, model):
            raise ProtocolApplicabilityError("model key/identity mismatch")
        return copy.deepcopy(value)

    def candidate_sources(
        self,
        model_key: str,
        *,
        series: str,
        model: str,
    ) -> dict[str, list[dict[str, Any]]]:
        value = self.model(model_key, series=series, model=model)
        return {
            "packages": [
                copy.deepcopy(self._packages[identifier])
                for identifier in value["candidate_package_ids"]
            ],
            "protocols": [
                copy.deepcopy(self._occurrences[identifier])
                for identifier in value["candidate_protocol_occurrence_ids"]
            ],
        }

    def admit(
        self,
        selection: ProtocolApplicabilitySelection,
    ) -> ProtocolAdmission:
        if selection.registry_generation_sha256 != self.generation_sha256:
            return _deny(
                ProtocolAdmissionReason.STALE_REGISTRY_GENERATION,
                "applicability_registry_generation_changed",
            )
        model = self._models.get(selection.model_key)
        if model is None:
            return _deny(
                ProtocolAdmissionReason.MODEL_NOT_FOUND,
                "exact_model_key_not_registered",
            )
        if (model["series"], model["model"]) != (
            selection.series,
            selection.model,
        ):
            return _deny(
                ProtocolAdmissionReason.MODEL_IDENTITY_MISMATCH,
                "model_key_series_model_disagree",
            )
        occurrence = self._occurrences.get(selection.protocol_occurrence_id)
        if occurrence is None or (
            selection.protocol_occurrence_id
            not in model["candidate_protocol_occurrence_ids"]
        ):
            return _deny(
                ProtocolAdmissionReason.PROTOCOL_SOURCE_NOT_CANDIDATE,
                "exact_protocol_source_not_a_model_candidate",
            )
        claim = occurrence["source_claim"]
        if claim["document_scope"] not in PROTOCOL_SCOPES:
            return _deny(
                ProtocolAdmissionReason.PROTOCOL_SCOPE_INVALID,
                "source_is_not_a_motor_control_protocol",
            )
        if claim["revision"] != selection.protocol_revision:
            return _deny(
                ProtocolAdmissionReason.PROTOCOL_IDENTITY_MISMATCH,
                "protocol_revision_disagrees_with_source_claim",
            )
        if selection.transport not in claim["transports"]:
            return _deny(
                ProtocolAdmissionReason.TRANSPORT_NOT_DECLARED,
                "transport_not_declared_by_candidate_source",
            )
        matches = [
            decision
            for decision in self._decisions
            if decision["subject"]
            == {
                "model_key": selection.model_key,
                "series": selection.series,
                "model": selection.model,
                "package_revision": model["package_revision"],
                "protocol_occurrence_id": selection.protocol_occurrence_id,
                "package_id": occurrence["package_id"],
                "document_set": occurrence["document_set"],
                "protocol_file_sha256": occurrence["file_sha256"],
                "protocol_revision": selection.protocol_revision,
                "transport": selection.transport,
                "control_mode": selection.control_mode,
                "hardware_revision": selection.hardware_revision,
                "drive_firmware": selection.drive_firmware,
                "installed_unit_id": selection.installed_unit_id,
            }
        ]
        if not matches:
            return _deny(
                ProtocolAdmissionReason.NO_ACCEPTED_APPLICABILITY,
                "exact_tuple_has_no_accepted_applicability_decision",
            )
        if len(matches) != 1:
            raise ProtocolApplicabilityError(
                "multiple accepted decisions match one exact tuple"
            )
        decision = matches[0]
        return ProtocolAdmission(
            allowed=True,
            reason=ProtocolAdmissionReason.ALLOWED,
            blockers=(),
            model_key=selection.model_key,
            protocol_occurrence_id=selection.protocol_occurrence_id,
            decision_id=decision["decision_id"],
            support_granted=False,
            physical_motion_authority=False,
        )


__all__ = [
    "ProtocolAdmission",
    "ProtocolAdmissionReason",
    "ProtocolApplicabilityDenied",
    "ProtocolApplicabilityError",
    "ProtocolApplicabilityRegistry",
    "ProtocolApplicabilitySelection",
]
