"""Exact-subject, provenance-complete actuator/joint limit selection."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

from .calibration import ConfigurationIdentity, ExactDriveTuple


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "schemas/myactuator-limit-registry.schema.json"
DEFAULT_REGISTRY = ROOT / "assets/myactuator/limit_registry.json"
PROVENANCE_CLASSES = (
    "vendor_rating",
    "software_command_limit",
    "measured_safe_robot_limit",
    "runtime_derate",
)
_UNKNOWN_MARKERS = {"unknown", "*", "any", "all", "wildcard", "n/a", "na"}
_UNIT_BY_QUANTITY = {
    "position": "rad",
    "velocity": "rad/s",
    "qaxis_current": "A",
    "effort": "N*m",
    "temperature": "degC",
    "voltage": "V",
}
_COORDINATES_BY_QUANTITY = {
    "position": {"motor", "output", "joint"},
    "velocity": {"motor", "output", "joint"},
    "qaxis_current": {"electrical"},
    "effort": {"motor", "output", "joint"},
    "temperature": {"thermal"},
    "voltage": {"electrical"},
}
_EVIDENCE_BY_CLASS = {
    "vendor_rating": ("vendor_manual", "identified_human"),
    "software_command_limit": ("software_configuration", "identified_human"),
    "measured_safe_robot_limit": ("physical_measurement", "identified_human"),
    "runtime_derate": ("runtime_derate_policy", "runtime_controller"),
}


class LimitRegistryError(ValueError):
    """A limit registry violates its structural or semantic contract."""


class LimitSelectionCode(str, Enum):
    SELECTED = "SELECTED"
    RECORD_NOT_FOUND = "RECORD_NOT_FOUND"
    RECORD_NOT_ACCEPTED = "RECORD_NOT_ACCEPTED"
    SUBJECT_MISMATCH = "SUBJECT_MISMATCH"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    NOT_YET_VALID = "NOT_YET_VALID"
    EXPIRED = "EXPIRED"
    OPERATING_POINT_MISSING = "OPERATING_POINT_MISSING"
    OPERATING_ENVELOPE_MISMATCH = "OPERATING_ENVELOPE_MISMATCH"
    RUNTIME_GENERATION_MISMATCH = "RUNTIME_GENERATION_MISMATCH"
    RUNTIME_SNAPSHOT_STALE = "RUNTIME_SNAPSHOT_STALE"
    MISSING_PROVENANCE_CLASS = "MISSING_PROVENANCE_CLASS"
    MISSING_DIRECTION = "MISSING_DIRECTION"
    CONTRADICTORY_BOUNDS = "CONTRADICTORY_BOUNDS"


@dataclass(frozen=True)
class LimitSubject:
    robot_id: str
    robot_hardware_revision: str
    canonical_joint_name: str
    actuator_id: str
    installed_actuator_serial: str
    exact_tuple: ExactDriveTuple
    bus_id: str
    native_node_id: int
    configuration: ConfigurationIdentity


@dataclass(frozen=True)
class OperatingPoint:
    at: datetime
    monotonic_time_ns: int
    supply_voltage_v: float | None
    temperature_c: float | None
    speed_abs_rad_s: float | None


@dataclass(frozen=True)
class LimitQuery:
    subject: LimitSubject
    quantity: str
    coordinate: str
    control_mode: str
    required_provenance_classes: tuple[str, ...]
    required_directions: tuple[str, ...]
    runtime_generation: int | None
    operating_point: OperatingPoint


@dataclass(frozen=True)
class EffectiveLimit:
    lower: float | None
    upper: float | None
    magnitude: float | None
    si_unit: str
    record_ids: tuple[str, ...]


@dataclass(frozen=True)
class LimitSelection:
    allowed: bool
    code: LimitSelectionCode
    failing_record_id: str | None
    missing_provenance_class: str | None
    missing_direction: str | None
    effective: EffectiveLimit | None


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LimitRegistryError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise LimitRegistryError(f"{label} root must be an object")
    return value


def _digest(value: Mapping[str, Any]) -> str:
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
    return _digest(record)


def registry_digest(registry: Mapping[str, Any]) -> str:
    return _digest(registry)


def _utc(value: str, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except (TypeError, ValueError) as error:
        raise LimitRegistryError(f"{field} must be an ISO-8601 UTC timestamp") from error
    if result.tzinfo is None or result.utcoffset() != timezone.utc.utcoffset(result):
        raise LimitRegistryError(f"{field} must be UTC")
    return result


def _finite(value: Any, path: str = "") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LimitRegistryError(f"non-finite number at {path or '/'}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _finite(child, f"{path}/{index}")
    elif isinstance(value, dict):
        for key, child in value.items():
            _finite(child, f"{path}/{key}")


def _subject(value: Mapping[str, Any]) -> LimitSubject:
    return LimitSubject(
        robot_id=value["robot_id"],
        robot_hardware_revision=value["robot_hardware_revision"],
        canonical_joint_name=value["canonical_joint_name"],
        actuator_id=value["actuator_id"],
        installed_actuator_serial=value["installed_actuator_serial"],
        exact_tuple=ExactDriveTuple(**value["exact_tuple"]),
        bus_id=value["bus_id"],
        native_node_id=value["native_node_id"],
        configuration=ConfigurationIdentity(**value["configuration"]),
    )


def _validate_record(record: Mapping[str, Any], config: Mapping[str, Any], index: int) -> None:
    prefix = f"records[{index}]"
    if record["integrity"]["digest"] != record_digest(record):
        raise LimitRegistryError(f"{prefix} digest mismatch")
    if record["subject"]["configuration"] != config:
        raise LimitRegistryError(f"{prefix} configuration does not equal registry configuration")
    for field, value in record["subject"]["exact_tuple"].items():
        if value.strip().lower() in _UNKNOWN_MARKERS:
            raise LimitRegistryError(f"{prefix} exact_tuple.{field} is unknown or wildcard")
    quantity = record["quantity"]
    if record["si_unit"] != _UNIT_BY_QUANTITY[quantity]:
        raise LimitRegistryError(f"{prefix} unit does not match quantity")
    if record["coordinate"] not in _COORDINATES_BY_QUANTITY[quantity]:
        raise LimitRegistryError(f"{prefix} coordinate does not match quantity")
    if record["direction"] == "magnitude" and record["bound_value"] < 0:
        raise LimitRegistryError(f"{prefix} magnitude must be nonnegative")

    envelope = record["operating_envelope"]
    for low, high in (
        ("supply_voltage_min_v", "supply_voltage_max_v"),
        ("temperature_min_c", "temperature_max_c"),
    ):
        if envelope[low] is not None and envelope[high] is not None and envelope[low] > envelope[high]:
            raise LimitRegistryError(f"{prefix} operating envelope {low}/{high} is reversed")

    valid_from = _utc(record["valid_from"], f"{prefix}.valid_from")
    valid_until = _utc(record["valid_until"], f"{prefix}.valid_until") if record["valid_until"] is not None else None
    if valid_until is not None and valid_until <= valid_from:
        raise LimitRegistryError(f"{prefix} validity interval is empty or reversed")
    reviewed_at = _utc(record["evidence"]["reviewed_at"], f"{prefix}.evidence.reviewed_at")
    if record["state"] == "accepted" and valid_from < reviewed_at:
        raise LimitRegistryError(f"{prefix} validity begins before evidence review")
    expected_authority, expected_reviewer = _EVIDENCE_BY_CLASS[record["provenance_class"]]
    evidence = record["evidence"]
    if (evidence["authority"], evidence["reviewer_kind"]) != (expected_authority, expected_reviewer):
        raise LimitRegistryError(f"{prefix} evidence authority/reviewer does not match provenance class")

    snapshot = record["runtime_snapshot"]
    if snapshot is not None:
        if snapshot["valid_until_ns"] <= snapshot["sample_time_ns"]:
            raise LimitRegistryError(f"{prefix} runtime snapshot interval is empty or reversed")


def validate_registry(registry: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(registry),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        first = errors[0]
        location = "/" + "/".join(map(str, first.absolute_path))
        raise LimitRegistryError(f"schema failure at {location}: {first.message}")
    _finite(registry)
    if registry["integrity"]["digest"] != registry_digest(registry):
        raise LimitRegistryError("registry digest mismatch")
    seen: set[str] = set()
    for index, record in enumerate(registry["records"]):
        if record["record_id"] in seen:
            raise LimitRegistryError(f"duplicate record_id {record['record_id']}")
        seen.add(record["record_id"])
        _validate_record(record, registry["configuration"], index)
    measured = sum(
        row["state"] == "accepted" and row["provenance_class"] == "measured_safe_robot_limit"
        for row in registry["records"]
    )
    if registry["physical_admission"]["accepted_measured_record_count"] != measured:
        raise LimitRegistryError("accepted measured record count does not match records")


def _denied(code: LimitSelectionCode, record_id: str | None = None, provenance: str | None = None, direction: str | None = None) -> LimitSelection:
    return LimitSelection(False, code, record_id, provenance, direction, None)


class LimitRegistry:
    def __init__(self, registry: Mapping[str, Any], schema: Mapping[str, Any]):
        validate_registry(registry, schema)
        self._registry = copy.deepcopy(dict(registry))
        self._records = {row["record_id"]: row for row in self._registry["records"]}

    @classmethod
    def load(cls, registry_path: Path = DEFAULT_REGISTRY, schema_path: Path = DEFAULT_SCHEMA) -> "LimitRegistry":
        return cls(_read_object(registry_path, "limit registry"), _read_object(schema_path, "limit schema"))

    @property
    def accepted_measured_record_count(self) -> int:
        return self._registry["physical_admission"]["accepted_measured_record_count"]

    @property
    def motion_enable_allowed(self) -> bool:
        return False

    def select(self, record_ids: Sequence[str], query: LimitQuery) -> LimitSelection:
        """Intersect explicitly selected exact records; never search or default."""

        point = query.operating_point
        if point.at.tzinfo is None or point.at.utcoffset() != timezone.utc.utcoffset(point.at):
            raise ValueError("operating time must be timezone-aware UTC")
        if point.monotonic_time_ns < 0:
            raise ValueError("monotonic time must be nonnegative")
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("record IDs must be unique")
        if not query.required_provenance_classes or len(query.required_provenance_classes) != len(set(query.required_provenance_classes)):
            raise ValueError("required provenance classes must be nonempty and unique")
        if not query.required_directions or len(query.required_directions) != len(set(query.required_directions)):
            raise ValueError("required directions must be nonempty and unique")
        if any(item not in PROVENANCE_CLASSES for item in query.required_provenance_classes):
            raise ValueError("unknown required provenance class")
        if any(item not in {"lower", "upper", "magnitude"} for item in query.required_directions):
            raise ValueError("unknown required direction")

        selected: list[Mapping[str, Any]] = []
        for record_id in record_ids:
            record = self._records.get(record_id)
            if record is None:
                return _denied(LimitSelectionCode.RECORD_NOT_FOUND, record_id)
            if record["state"] != "accepted":
                return _denied(LimitSelectionCode.RECORD_NOT_ACCEPTED, record_id)
            if _subject(record["subject"]) != query.subject:
                return _denied(LimitSelectionCode.SUBJECT_MISMATCH, record_id)
            if (
                record["quantity"] != query.quantity
                or record["coordinate"] != query.coordinate
                or query.control_mode not in record["control_modes"]
            ):
                return _denied(LimitSelectionCode.SCOPE_MISMATCH, record_id)
            if point.at < _utc(record["valid_from"], "valid_from"):
                return _denied(LimitSelectionCode.NOT_YET_VALID, record_id)
            if record["valid_until"] is not None and point.at > _utc(record["valid_until"], "valid_until"):
                return _denied(LimitSelectionCode.EXPIRED, record_id)

            envelope = record["operating_envelope"]
            checks = (
                ("supply_voltage_min_v", "supply_voltage_max_v", point.supply_voltage_v),
                ("temperature_min_c", "temperature_max_c", point.temperature_c),
                (None, "speed_abs_max_rad_s", point.speed_abs_rad_s),
            )
            for low_key, high_key, actual in checks:
                low = envelope[low_key] if low_key else None
                high = envelope[high_key]
                if (low is not None or high is not None) and actual is None:
                    return _denied(LimitSelectionCode.OPERATING_POINT_MISSING, record_id)
                if actual is not None and ((low is not None and actual < low) or (high is not None and actual > high)):
                    return _denied(LimitSelectionCode.OPERATING_ENVELOPE_MISMATCH, record_id)

            snapshot = record["runtime_snapshot"]
            if snapshot is not None:
                if query.runtime_generation != snapshot["generation"]:
                    return _denied(LimitSelectionCode.RUNTIME_GENERATION_MISMATCH, record_id)
                if not snapshot["sample_time_ns"] <= point.monotonic_time_ns <= snapshot["valid_until_ns"]:
                    return _denied(LimitSelectionCode.RUNTIME_SNAPSHOT_STALE, record_id)
            selected.append(record)

        coverage = {(row["provenance_class"], row["direction"]) for row in selected}
        for provenance in query.required_provenance_classes:
            if not any(item[0] == provenance for item in coverage):
                return _denied(LimitSelectionCode.MISSING_PROVENANCE_CLASS, provenance=provenance)
            for direction in query.required_directions:
                if (provenance, direction) not in coverage:
                    return _denied(LimitSelectionCode.MISSING_DIRECTION, provenance=provenance, direction=direction)

        values = {direction: [row["bound_value"] for row in selected if row["direction"] == direction] for direction in ("lower", "upper", "magnitude")}
        lower = max(values["lower"]) if values["lower"] else None
        upper = min(values["upper"]) if values["upper"] else None
        magnitude = min(values["magnitude"]) if values["magnitude"] else None
        if magnitude is not None:
            lower = max(lower, -magnitude) if lower is not None else -magnitude
            upper = min(upper, magnitude) if upper is not None else magnitude
        if lower is not None and upper is not None and lower > upper:
            return _denied(LimitSelectionCode.CONTRADICTORY_BOUNDS)
        effective = EffectiveLimit(
            lower=lower,
            upper=upper,
            magnitude=magnitude,
            si_unit=_UNIT_BY_QUANTITY[query.quantity],
            record_ids=tuple(record_ids),
        )
        return LimitSelection(True, LimitSelectionCode.SELECTED, None, None, None, effective)


__all__ = [
    "EffectiveLimit",
    "LimitQuery",
    "LimitRegistry",
    "LimitRegistryError",
    "LimitSelection",
    "LimitSelectionCode",
    "LimitSubject",
    "OperatingPoint",
    "PROVENANCE_CLASSES",
    "record_digest",
    "registry_digest",
    "validate_registry",
]
