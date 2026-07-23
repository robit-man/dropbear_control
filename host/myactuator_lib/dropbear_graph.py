"""Fail-closed host consumer for denial-only Dropbear graph projections."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECTION_ROOT = ROOT / "generated/dropbear_graph_projection"
DEFAULT_GRAPH_STATUS = ROOT / "generated/dropbear_graph_review/status.json"
DEFAULT_INVENTORY = ROOT / "generated/dropbear_description/inventory.json"
DEFAULT_TEMPLATE_ROOT = ROOT / "generated/dropbear_graph_review/templates"
DEFAULT_SCHEMA = ROOT / "schemas/dropbear-graph-projection.schema.json"
VIEW_KINDS = ("host", "ros", "simulator", "ui")


class DropbearGraphAdmissionError(ValueError):
    pass


@dataclass(frozen=True)
class DropbearGraphProjection:
    view_kind: str
    canonical_configuration_digest: str
    candidate_graph_decision_id: str
    blockers: tuple[str, ...]
    question_count: int
    unanswered_question_count: int
    canonical_graph_count: int
    actuator_mapping_count: int

    @property
    def canonical_graph_admissible(self) -> bool:
        return False

    @property
    def support_granted(self) -> bool:
        return False

    @property
    def physical_motion_authority(self) -> bool:
        return False


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DropbearGraphAdmissionError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise DropbearGraphAdmissionError(f"JSON root must be an object: {path}")
    return value


class DropbearGraphProjectionSet:
    def __init__(
        self,
        projections: dict[str, dict],
        schema: dict,
        graph_status: dict,
        graph_status_bytes: bytes,
        inventory: dict,
        inventory_bytes: bytes,
        template: dict,
        template_bytes: bytes,
    ):
        Draft202012Validator.check_schema(schema)
        if set(projections) != set(VIEW_KINDS):
            raise DropbearGraphAdmissionError("graph projection view set is not exact")
        validator = Draft202012Validator(schema)
        for kind, value in projections.items():
            errors = sorted(
                validator.iter_errors(value),
                key=lambda error: (list(error.absolute_path), error.message),
            )
            if errors:
                error = errors[0]
                raise DropbearGraphAdmissionError(
                    f"{kind} projection schema failure at "
                    f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
                )
            if value["view_kind"] != kind:
                raise DropbearGraphAdmissionError("projection filename/kind mismatch")

        first = projections["host"]
        for kind in VIEW_KINDS:
            value = projections[kind]
            if (
                value["subject"] != first["subject"]
                or value["summary"] != first["summary"]
                or value["blockers"] != first["blockers"]
            ):
                raise DropbearGraphAdmissionError(
                    f"{kind} projection disagrees with common denial state"
                )
        if (
            hashlib.sha256(graph_status_bytes).hexdigest()
            != first["subject"]["graph_review_status_sha256"]
        ):
            raise DropbearGraphAdmissionError("graph-review status hash drift")
        if (
            graph_status.get("schema_version")
            != "dropbear-graph-review-status/1"
            or graph_status.get("summary") != first["summary"]
            or graph_status.get("blockers") != first["blockers"]
            or graph_status.get("accepted_graph_decision_ids")
            or graph_status.get("support_granted") is not False
            or graph_status.get("physical_motion_authority") is not False
        ):
            raise DropbearGraphAdmissionError(
                "graph-review status/projection authority drift"
            )
        source_hashes = {
            row.get("path"): row.get("sha256")
            for row in graph_status.get("sources", [])
            if isinstance(row, dict)
        }
        inventory_path = "generated/dropbear_description/inventory.json"
        template_path = (
            "generated/dropbear_graph_review/templates/"
            f"{first['subject']['graph_decision_id']}.json"
        )
        inventory_sha = hashlib.sha256(inventory_bytes).hexdigest()
        template_sha = hashlib.sha256(template_bytes).hexdigest()
        if (
            source_hashes.get(inventory_path) != inventory_sha
            or first["subject"]["inventory_sha256"] != inventory_sha
            or source_hashes.get(template_path) != template_sha
        ):
            raise DropbearGraphAdmissionError(
                "graph projection inventory/template evidence hash drift"
            )
        if (
            inventory.get("schema_version")
            != "dropbear-description-inventory/1"
            or inventory.get("reconciliation", {}).get(
                "canonical_configuration_digest"
            )
            != first["subject"]["canonical_configuration_digest"]
            or template.get("decision_id")
            != first["subject"]["graph_decision_id"]
            or template.get("subject", {}).get(
                "canonical_configuration_digest"
            )
            != first["subject"]["canonical_configuration_digest"]
            or template.get("record_state") != "draft"
            or template.get("canonical_graph_admissible") is not False
        ):
            raise DropbearGraphAdmissionError(
                "graph projection inventory/template identity drift"
            )
        self._projections = projections

    @classmethod
    def load(
        cls,
        projection_root: Path = DEFAULT_PROJECTION_ROOT,
        graph_status_path: Path = DEFAULT_GRAPH_STATUS,
        inventory_path: Path = DEFAULT_INVENTORY,
        template_root: Path = DEFAULT_TEMPLATE_ROOT,
        schema_path: Path = DEFAULT_SCHEMA,
    ) -> "DropbearGraphProjectionSet":
        projections = {
            kind: _load(projection_root / f"{kind}.json")
            for kind in VIEW_KINDS
        }
        status_bytes = graph_status_path.read_bytes()
        inventory_bytes = inventory_path.read_bytes()
        decision_id = projections["host"]["subject"]["graph_decision_id"]
        template_bytes = (template_root / f"{decision_id}.json").read_bytes()
        return cls(
            projections,
            _load(schema_path),
            json.loads(status_bytes),
            status_bytes,
            json.loads(inventory_bytes),
            inventory_bytes,
            json.loads(template_bytes),
            template_bytes,
        )

    def view(self, kind: str) -> DropbearGraphProjection:
        if kind not in VIEW_KINDS:
            raise DropbearGraphAdmissionError(
                f"unknown exact graph projection view: {kind}"
            )
        value = self._projections[kind]
        mapping_count = value["outputs"].get(
            "actuator_mapping_count",
            value["outputs"].get("ros2_control_hardware_mapping_count", 0),
        )
        return DropbearGraphProjection(
            view_kind=kind,
            canonical_configuration_digest=value["subject"][
                "canonical_configuration_digest"
            ],
            candidate_graph_decision_id=value["subject"]["graph_decision_id"],
            blockers=tuple(value["blockers"]),
            question_count=value["summary"]["question_count"],
            unanswered_question_count=value["summary"][
                "unanswered_question_count"
            ],
            canonical_graph_count=0,
            actuator_mapping_count=mapping_count,
        )

    def require_canonical_graph(self) -> None:
        blockers = self.view("host").blockers
        raise DropbearGraphAdmissionError(
            "canonical Dropbear graph is unavailable: " + ",".join(blockers)
        )


__all__ = [
    "DropbearGraphAdmissionError",
    "DropbearGraphProjection",
    "DropbearGraphProjectionSet",
]
