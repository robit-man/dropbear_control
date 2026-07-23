"""Fail-closed exact-subject calibration evidence and admission.

This module does not calibrate hardware.  It validates immutable records and
answers whether one explicitly selected record is applicable to one exact
installed subject at one UTC instant.  There is no model-family, joint-name,
latest-record, or synthetic-to-physical fallback.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "schemas/myactuator-calibration-registry.schema.json"
DEFAULT_REGISTRY = ROOT / "assets/myactuator/calibration_registry.json"
_UNKNOWN_MARKERS = {"unknown", "*", "any", "all", "wildcard", "n/a", "na"}
_REQUIRED_INVALIDATION_CONDITIONS = {
    "actuator_replaced",
    "sensor_replaced",
    "controller_replaced",
    "native_node_reassigned",
    "mechanical_disassembly",
    "drive_firmware_changed",
    "canonical_configuration_changed",
    "coordinate_frame_changed",
    "procedure_or_fixture_changed",
    "validity_expired",
}


class CalibrationRegistryError(ValueError):
    """The registry or a record violates the structural/semantic contract."""


class CalibrationAdmissionCode(str, Enum):
    ADMITTED = "ADMITTED"
    RECORD_NOT_FOUND = "RECORD_NOT_FOUND"
    RECORD_NOT_ACCEPTED = "RECORD_NOT_ACCEPTED"
    NONPHYSICAL_EVIDENCE = "NONPHYSICAL_EVIDENCE"
    RECORD_SUPERSEDED = "RECORD_SUPERSEDED"
    SUBJECT_MISMATCH = "SUBJECT_MISMATCH"
    NOT_YET_VALID = "NOT_YET_VALID"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class ConfigurationIdentity:
    configuration_id: str
    configuration_revision: int
    canonical_digest: str


@dataclass(frozen=True)
class ExactDriveTuple:
    manufacturer: str
    series: str
    model: str
    hardware_revision: str
    drive_firmware: str
    protocol_name: str
    protocol_revision: str
    transport: str
    control_mode: str


@dataclass(frozen=True)
class CalibrationSubject:
    robot_id: str
    robot_hardware_revision: str
    canonical_joint_name: str
    actuator_id: str
    installed_actuator_serial: str
    exact_tuple: ExactDriveTuple
    bus_id: str
    native_node_id: int
    sensor_id: str
    sensor_kind: str
    sensor_serial: str
    configuration: ConfigurationIdentity


@dataclass(frozen=True)
class CalibrationAdmission:
    allowed: bool
    code: CalibrationAdmissionCode
    record_id: str | None
    record: Mapping[str, Any] | None


def _read_object(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CalibrationRegistryError(f"cannot read {description} {path}: {error}") from error
    if not isinstance(value, dict):
        raise CalibrationRegistryError(f"{description} root must be an object")
    return value


def _canonical_digest(value: Mapping[str, Any]) -> str:
    candidate = copy.deepcopy(dict(value))
    integrity = candidate.get("integrity")
    if isinstance(integrity, dict):
        integrity.pop("digest", None)
    encoded = json.dumps(
        candidate,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def record_digest(record: Mapping[str, Any]) -> str:
    """Return the record's canonical digest with only its digest omitted."""

    return _canonical_digest(record)


def registry_digest(registry: Mapping[str, Any]) -> str:
    """Return the whole-registry canonical digest with only root digest omitted."""

    return _canonical_digest(registry)


def _utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except (TypeError, ValueError) as error:
        raise CalibrationRegistryError(f"{field} must be an ISO-8601 UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise CalibrationRegistryError(f"{field} must be UTC")
    return parsed


def _walk_finite(value: Any, path: str = "") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CalibrationRegistryError(f"non-finite number at {path or '/'}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _walk_finite(child, f"{path}/{index}")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _walk_finite(child, f"{path}/{key}")


def _subject_from_record(value: Mapping[str, Any]) -> CalibrationSubject:
    exact = value["exact_tuple"]
    config = value["configuration"]
    return CalibrationSubject(
        robot_id=value["robot_id"],
        robot_hardware_revision=value["robot_hardware_revision"],
        canonical_joint_name=value["canonical_joint_name"],
        actuator_id=value["actuator_id"],
        installed_actuator_serial=value["installed_actuator_serial"],
        exact_tuple=ExactDriveTuple(**exact),
        bus_id=value["bus_id"],
        native_node_id=value["native_node_id"],
        sensor_id=value["sensor_id"],
        sensor_kind=value["sensor_kind"],
        sensor_serial=value["sensor_serial"],
        configuration=ConfigurationIdentity(**config),
    )


def _validate_record_semantics(record: Mapping[str, Any], registry_config: Mapping[str, Any], index: int) -> None:
    prefix = f"records[{index}]"
    declared = record["integrity"]["digest"]
    computed = record_digest(record)
    if declared != computed:
        raise CalibrationRegistryError(
            f"{prefix} digest mismatch: declared={declared} computed={computed}"
        )

    subject = record["subject"]
    if subject["configuration"] != registry_config:
        raise CalibrationRegistryError(f"{prefix} configuration does not equal registry configuration")
    for field, value in subject["exact_tuple"].items():
        if value.strip().lower() in _UNKNOWN_MARKERS:
            raise CalibrationRegistryError(f"{prefix} exact_tuple.{field} is unknown or wildcard")

    procedure = record["procedure"]
    recorded_at = _utc(procedure["recorded_at"], f"{prefix}.procedure.recorded_at")
    tool_ids: set[str] = set()
    for tool_index, tool in enumerate(procedure["tools"]):
        if tool["tool_id"] in tool_ids:
            raise CalibrationRegistryError(f"{prefix} duplicate tool_id {tool['tool_id']}")
        tool_ids.add(tool["tool_id"])
        due = tool["calibration_due_at"]
        if due is not None and _utc(due, f"{prefix}.procedure.tools[{tool_index}].calibration_due_at") < recorded_at:
            raise CalibrationRegistryError(f"{prefix} uses a tool past its calibration due time")
    artifact_ids = [item["artifact_id"] for item in procedure["source_artifacts"]]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise CalibrationRegistryError(f"{prefix} has duplicate source artifact IDs")

    measurements = record["measurements"]
    samples = measurements["samples"]
    indexes = [sample["sample_index"] for sample in samples]
    if indexes != list(range(len(samples))):
        raise CalibrationRegistryError(f"{prefix} sample indexes must be dense and ordered from zero")
    observed_residual = max(abs(sample["residual_rad"]) for sample in samples)
    if not math.isclose(
        observed_residual,
        measurements["max_absolute_residual_rad"],
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise CalibrationRegistryError(f"{prefix} maximum residual does not match samples")
    expected_pass = (
        measurements["max_absolute_residual_rad"]
        <= measurements["acceptance_max_residual_rad"]
        and measurements["uncertainty_rad"]
        <= measurements["acceptance_max_uncertainty_rad"]
    )
    if measurements["acceptance_passed"] != expected_pass:
        raise CalibrationRegistryError(f"{prefix} acceptance result disagrees with thresholds")

    coordinates = record["coordinates"]
    wrap = coordinates["wrap"]
    if wrap["enabled"]:
        expected_period = abs(
            wrap["raw_period"] * coordinates["raw_to_joint_scale_rad_per_unit"]
        )
        if not math.isclose(
            expected_period,
            wrap["canonical_period_rad"],
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise CalibrationRegistryError(f"{prefix} raw and canonical wrap periods disagree")

    validity = record["validity"]
    if record["state"] == "accepted" and set(validity["invalidation_conditions"]) != _REQUIRED_INVALIDATION_CONDITIONS:
        raise CalibrationRegistryError(
            f"{prefix} accepted record must declare every required invalidation condition"
        )
    valid_from = _utc(validity["valid_from"], f"{prefix}.validity.valid_from")
    valid_until = (
        _utc(validity["valid_until"], f"{prefix}.validity.valid_until")
        if validity["valid_until"] is not None
        else None
    )
    if valid_until is not None and valid_until <= valid_from:
        raise CalibrationRegistryError(f"{prefix} validity interval is empty or reversed")

    review = record["review"]
    if review is not None:
        reviewed_at = _utc(review["reviewed_at"], f"{prefix}.review.reviewed_at")
        if reviewed_at < recorded_at:
            raise CalibrationRegistryError(f"{prefix} review precedes measurement")
        if review["reviewer_id"] == procedure["operator_id"]:
            raise CalibrationRegistryError(f"{prefix} reviewer and operator must be distinct")
        if record["state"] == "accepted" and valid_from < reviewed_at:
            raise CalibrationRegistryError(f"{prefix} accepted validity starts before review")


def validate_registry(
    registry: Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    verify_digest: bool = True,
) -> None:
    """Validate structural, integrity, provenance, and lifecycle invariants."""

    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(registry),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        first = errors[0]
        location = "/" + "/".join(map(str, first.absolute_path))
        raise CalibrationRegistryError(f"schema failure at {location}: {first.message}")
    _walk_finite(registry)

    if verify_digest:
        declared = registry["integrity"]["digest"]
        computed = registry_digest(registry)
        if declared != computed:
            raise CalibrationRegistryError(
                f"registry digest mismatch: declared={declared} computed={computed}"
            )

    records = registry["records"]
    record_ids: set[str] = set()
    family_revisions: set[tuple[str, int]] = set()
    record_by_id: dict[str, Mapping[str, Any]] = {}
    superseded_ids: set[str] = set()
    for index, record in enumerate(records):
        record_id = record["record_id"]
        family_revision = (record["calibration_family_id"], record["record_revision"])
        if record_id in record_ids:
            raise CalibrationRegistryError(f"duplicate record_id {record_id}")
        if family_revision in family_revisions:
            raise CalibrationRegistryError(f"duplicate family revision {family_revision}")
        record_ids.add(record_id)
        family_revisions.add(family_revision)
        _validate_record_semantics(record, registry["configuration"], index)

        previous_id = record["supersedes_record_id"]
        if previous_id is not None:
            if previous_id not in record_by_id:
                raise CalibrationRegistryError(
                    f"records[{index}] supersedes missing or later record {previous_id}"
                )
            if previous_id in superseded_ids:
                raise CalibrationRegistryError(f"record {previous_id} is superseded more than once")
            previous = record_by_id[previous_id]
            if previous["calibration_family_id"] != record["calibration_family_id"]:
                raise CalibrationRegistryError("superseding records must share calibration family")
            if previous["record_revision"] >= record["record_revision"]:
                raise CalibrationRegistryError("superseding revision must increase")
            if previous["subject"] != record["subject"]:
                raise CalibrationRegistryError("superseding records must have the exact same subject")
            superseded_ids.add(previous_id)
        record_by_id[record_id] = record

    accepted_physical = sum(
        record["state"] == "accepted"
        and record["evidence_class"] == "physical_bench"
        and record["record_id"] not in superseded_ids
        for record in records
    )
    if registry["physical_admission"]["accepted_physical_record_count"] != accepted_physical:
        raise CalibrationRegistryError("accepted physical record count does not match active records")


class CalibrationRegistry:
    """An immutable, fully validated exact-record admission view."""

    def __init__(self, registry: Mapping[str, Any], schema: Mapping[str, Any]):
        validate_registry(registry, schema)
        self._registry = copy.deepcopy(dict(registry))
        self._records = {item["record_id"]: item for item in self._registry["records"]}
        self._superseded = {
            item["supersedes_record_id"]
            for item in self._registry["records"]
            if item["supersedes_record_id"] is not None
        }

    @classmethod
    def load(
        cls,
        registry_path: Path = DEFAULT_REGISTRY,
        schema_path: Path = DEFAULT_SCHEMA,
    ) -> "CalibrationRegistry":
        return cls(
            _read_object(registry_path, "calibration registry"),
            _read_object(schema_path, "calibration schema"),
        )

    @property
    def accepted_physical_record_count(self) -> int:
        return self._registry["physical_admission"]["accepted_physical_record_count"]

    @property
    def motion_enable_allowed(self) -> bool:
        return False

    def admit_physical(
        self,
        record_id: str,
        subject: CalibrationSubject,
        at: datetime,
    ) -> CalibrationAdmission:
        """Admit exactly one selected physical record; never search/fallback."""

        if at.tzinfo is None or at.utcoffset() != timezone.utc.utcoffset(at):
            raise ValueError("admission time must be timezone-aware UTC")
        record = self._records.get(record_id)
        if record is None:
            return CalibrationAdmission(False, CalibrationAdmissionCode.RECORD_NOT_FOUND, None, None)
        if record["state"] != "accepted":
            return CalibrationAdmission(False, CalibrationAdmissionCode.RECORD_NOT_ACCEPTED, record_id, None)
        if record["evidence_class"] != "physical_bench":
            return CalibrationAdmission(False, CalibrationAdmissionCode.NONPHYSICAL_EVIDENCE, record_id, None)
        if record_id in self._superseded:
            return CalibrationAdmission(False, CalibrationAdmissionCode.RECORD_SUPERSEDED, record_id, None)
        if _subject_from_record(record["subject"]) != subject:
            return CalibrationAdmission(False, CalibrationAdmissionCode.SUBJECT_MISMATCH, record_id, None)
        valid_from = _utc(record["validity"]["valid_from"], "validity.valid_from")
        if at < valid_from:
            return CalibrationAdmission(False, CalibrationAdmissionCode.NOT_YET_VALID, record_id, None)
        raw_until = record["validity"]["valid_until"]
        if raw_until is not None and at > _utc(raw_until, "validity.valid_until"):
            return CalibrationAdmission(False, CalibrationAdmissionCode.EXPIRED, record_id, None)
        return CalibrationAdmission(True, CalibrationAdmissionCode.ADMITTED, record_id, copy.deepcopy(record))


__all__ = [
    "CalibrationAdmission",
    "CalibrationAdmissionCode",
    "CalibrationRegistry",
    "CalibrationRegistryError",
    "CalibrationSubject",
    "ConfigurationIdentity",
    "ExactDriveTuple",
    "record_digest",
    "registry_digest",
    "validate_registry",
]
