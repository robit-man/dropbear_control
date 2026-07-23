"""Fail-closed host consumer for Dropbear source-authority status V1."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATUS = ROOT / "generated/dropbear_source_authority/status.json"
DEFAULT_SCHEMA = ROOT / "schemas/dropbear-source-authority-status.schema.json"
EXPECTED_ROLES = {
    "kinematic_tree",
    "visual_geometry",
    "collision_geometry",
    "inertial_properties",
    "ros2_control",
    "gazebo_constraints",
    "controller_configuration",
}


class SourceAuthorityAdmissionError(ValueError):
    pass


@dataclass(frozen=True)
class SourceRoleDecision:
    role: str
    selected: bool
    selected_paths: tuple[str, ...]
    blockers: tuple[str, ...]


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SourceAuthorityAdmissionError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise SourceAuthorityAdmissionError(f"JSON root must be an object: {path}")
    return value


def _resolve(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise SourceAuthorityAdmissionError("evidence path escapes repository") from error
    return path


class DropbearSourceAuthorityStatus:
    def __init__(self, status: dict, schema: dict, root: Path = ROOT):
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(status),
            key=lambda error: (list(error.absolute_path), error.message),
        )
        if errors:
            error = errors[0]
            raise SourceAuthorityAdmissionError(
                f"schema failure at /{'/'.join(map(str, error.absolute_path))}: "
                f"{error.message}"
            )
        inventory_path = _resolve(root, status["source"]["inventory_path"])
        template_path = _resolve(root, status["template"]["path"])
        for path, expected in (
            (inventory_path, status["source"]["inventory_sha256"]),
            (template_path, status["template"]["sha256"]),
        ):
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise SourceAuthorityAdmissionError(
                    f"source-authority evidence missing or changed: {path}"
                )
        inventory = _load(inventory_path)
        template = _load(template_path)
        if (
            inventory["repository"]["commit"] != status["source"]["repository_commit"]
            or inventory["repository"]["tree_id"]
            != status["source"]["repository_tree_id"]
            or inventory["reconciliation"]["canonical_configuration_digest"]
            != status["source"]["canonical_configuration_digest"]
        ):
            raise SourceAuthorityAdmissionError("inventory/source status identity drift")
        if (
            template["decision_id"] != status["template"]["decision_id"]
            or template["record_state"] != "draft"
            or template["disposition"] is not None
            or template["decision_complete"]
            or template["runtime_description_complete"]
        ):
            raise SourceAuthorityAdmissionError("tracked source decision template is promoted")
        roles = [row["role"] for row in template["role_decisions"]]
        if (
            set(roles) != EXPECTED_ROLES
            or len(roles) != len(set(roles))
            or any(
                row["status"] != "unanswered" or row["selected_files"]
                for row in template["role_decisions"]
            )
        ):
            raise SourceAuthorityAdmissionError("template source-role coverage is not exact")
        if (
            status["accepted_decision_ids"]
            or status["summary"]["accepted_decision_count"] != 0
            or status["summary"]["source_authority_selected"]
        ):
            raise SourceAuthorityAdmissionError("denial-only V1 contains source authority")
        self._status = status

    @classmethod
    def load(
        cls,
        status_path: Path = DEFAULT_STATUS,
        schema_path: Path = DEFAULT_SCHEMA,
    ) -> "DropbearSourceAuthorityStatus":
        return cls(_load(status_path), _load(schema_path))

    @property
    def source_authority_selected(self) -> bool:
        return False

    @property
    def physical_motion_authority(self) -> bool:
        return False

    def decision(self, role: str) -> SourceRoleDecision:
        if role not in EXPECTED_ROLES:
            raise SourceAuthorityAdmissionError(f"unknown exact source role: {role}")
        return SourceRoleDecision(
            role=role,
            selected=False,
            selected_paths=(),
            blockers=tuple(self._status["blockers"]),
        )

    def require_selected(self, role: str) -> tuple[str, ...]:
        decision = self.decision(role)
        raise SourceAuthorityAdmissionError(
            f"{decision.role} has no accepted source authority: "
            f"{','.join(decision.blockers)}"
        )


__all__ = [
    "DropbearSourceAuthorityStatus",
    "SourceAuthorityAdmissionError",
    "SourceRoleDecision",
]
