"""Fail-closed consumer for the generated Dropbear readiness projection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT = ROOT / "generated/dropbear_readiness/readiness.json"
DEFAULT_SCHEMA = ROOT / "schemas/dropbear-readiness.schema.json"


class DropbearReadinessError(ValueError):
    pass


@dataclass(frozen=True)
class ReadinessDecision:
    actuator_id: str
    canonical_joint_name: str
    motion_ready: bool
    blockers: tuple[str, ...]


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DropbearReadinessError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise DropbearReadinessError(f"JSON root must be an object: {path}")
    return value


class DropbearReadinessRegistry:
    def __init__(self, artifact: dict, schema: dict, root: Path = ROOT):
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(artifact), key=lambda e: (list(e.absolute_path), e.message))
        if errors:
            error = errors[0]
            raise DropbearReadinessError(f"schema failure at /{'/'.join(map(str, error.absolute_path))}: {error.message}")
        for source in artifact["sources"]:
            path = (root / source["path"]).resolve()
            try:
                path.relative_to(root.resolve())
            except ValueError as error:
                raise DropbearReadinessError("source path escapes repository") from error
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                raise DropbearReadinessError(f"source missing or changed: {source['path']}")
        rows = artifact["actuators"]
        ids = [row["actuator_id"] for row in rows]
        names = [row["canonical_joint_name"] for row in rows]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise DropbearReadinessError("actuator IDs and canonical names must be unique")
        expected_dependencies = {
            "configuration_identity", "installed_actuator_identity", "native_protocol_applicability",
            "exclusive_runtime_route", "physical_calibration", "complete_limit_set", "external_feedback",
            "native_telemetry", "feedback_reconciliation_policy", "accepted_cad_binding",
            "reviewed_ros_actuation_mapping", "independent_safe_power", "hil_evidence",
        }
        for row in rows:
            dependencies = [item["dependency"] for item in row["dependencies"]]
            if set(dependencies) != expected_dependencies or len(dependencies) != len(set(dependencies)):
                raise DropbearReadinessError(f"dependency coverage is not exact: {row['actuator_id']}")
            if row["motion_ready"] or not row["blockers"]:
                raise DropbearReadinessError("denial-only V1 row cannot be ready or blocker-free")
        self._artifact = artifact
        self._rows = {row["actuator_id"]: row for row in rows}

    @classmethod
    def load(cls, artifact_path: Path = DEFAULT_ARTIFACT, schema_path: Path = DEFAULT_SCHEMA) -> "DropbearReadinessRegistry":
        return cls(_load(artifact_path), _load(schema_path))

    @property
    def motion_enable_allowed(self) -> bool:
        return False

    def decision(self, actuator_id: str) -> ReadinessDecision:
        row = self._rows.get(actuator_id)
        if row is None:
            raise DropbearReadinessError(f"unknown exact actuator ID: {actuator_id}")
        return ReadinessDecision(row["actuator_id"], row["canonical_joint_name"], False, tuple(row["blockers"]))

    def require_motion_ready(self, actuator_id: str) -> None:
        decision = self.decision(actuator_id)
        raise DropbearReadinessError(
            f"{decision.actuator_id} is not motion ready: {','.join(decision.blockers)}"
        )


__all__ = ["DropbearReadinessError", "DropbearReadinessRegistry", "ReadinessDecision"]
