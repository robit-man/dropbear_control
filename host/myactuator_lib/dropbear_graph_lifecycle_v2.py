"""Fail-closed host consumer for Dropbear graph lifecycle projections V2."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECTION_ROOT = (
    ROOT / "generated/dropbear_graph_lifecycle_projection_v2"
)
DEFAULT_SCHEMA = (
    ROOT / "schemas/dropbear-graph-lifecycle-projection-v2.schema.json"
)
DEFAULT_GRAPH_REGISTRY = (
    ROOT / "generated/dropbear_graph_registry_v2/registry.json"
)
DEFAULT_GRAPH_REGISTRY_SCHEMA = (
    ROOT / "schemas/dropbear-graph-registry-v2.schema.json"
)
VIEW_KINDS = ("host", "ros", "simulator", "ui")


class GraphLifecycleAdmissionError(ValueError):
    """A projection set, registry, generation, or exact query is invalid."""


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_bytes(value: bytes, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GraphLifecycleAdmissionError(
            f"cannot decode {label}: {error}"
        ) from error
    if not isinstance(parsed, dict):
        raise GraphLifecycleAdmissionError(f"{label} root must be an object")
    return parsed


def _load(path: Path) -> dict[str, Any]:
    try:
        return _load_bytes(path.read_bytes(), str(path))
    except OSError as error:
        raise GraphLifecycleAdmissionError(f"cannot read {path}: {error}") from error


def _schema(
    value: dict[str, Any], schema: dict[str, Any], label: str
) -> None:
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise GraphLifecycleAdmissionError(
            f"{label} schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def _digest(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return _sha(_canonical(payload))


@dataclass(frozen=True)
class GraphAuthorityGeneration:
    canonical_configuration_digest: str
    source_registry_generation_sha256: str
    graph_registry_generation_sha256: str
    graph_submission_id: str
    graph_decision_id: str
    graph_decision_sha256: str


@dataclass(frozen=True)
class LifecycleGraphView:
    view_kind: str
    source_active_state: str
    graph_active_state: str
    canonical_graph_count: int
    actuator_mapping_count: int
    ros_mapping_count: int
    blockers: tuple[str, ...]

    @property
    def support_granted(self) -> bool:
        return False

    @property
    def physical_motion_authority(self) -> bool:
        return False


class DropbearGraphLifecycleProjectionSetV2:
    """Hash-bound four-view projection snapshot with exact generation query."""

    def __init__(
        self,
        projections: dict[str, dict[str, Any]],
        projection_schema: dict[str, Any],
        graph_registry: dict[str, Any],
        graph_registry_schema: dict[str, Any],
        graph_registry_bytes: bytes,
    ):
        if set(projections) != set(VIEW_KINDS):
            raise GraphLifecycleAdmissionError(
                "graph lifecycle projection view set is not exact"
            )
        for kind, value in projections.items():
            _schema(value, projection_schema, f"{kind} graph lifecycle projection")
            if (
                value["view_kind"] != kind
                or value["integrity"]["record_sha256"] != _digest(value)
                or value["support_granted"]
                or value["physical_motion_authority"]
            ):
                raise GraphLifecycleAdmissionError(
                    f"{kind} projection identity/digest/authority drift"
                )
        first = projections["host"]
        for kind in VIEW_KINDS:
            value = projections[kind]
            if any(
                value[field] != first[field]
                for field in (
                    "subject",
                    "lifecycle",
                    "graph_summary",
                    "blockers",
                )
            ):
                raise GraphLifecycleAdmissionError(
                    f"{kind} projection disagrees with lifecycle authority"
                )

        _schema(graph_registry, graph_registry_schema, "graph registry V2")
        if (
            graph_registry["integrity"]["record_sha256"]
            != _digest(graph_registry)
            or graph_registry["support_granted"]
            or graph_registry["physical_motion_authority"]
        ):
            raise GraphLifecycleAdmissionError(
                "graph registry digest/authority drift"
            )
        generation_payload = {
            "source": graph_registry["source"],
            "submissions": graph_registry["submissions"],
            "events": graph_registry["events"],
            "active_submission_id": graph_registry["active_submission_id"],
            "active_graph_decision_id": graph_registry[
                "active_graph_decision_id"
            ],
            "active_graph_decision_sha256": graph_registry[
                "active_graph_decision_sha256"
            ],
        }
        if graph_registry["registry_generation_sha256"] != _sha(
            _canonical(generation_payload)
        ):
            raise GraphLifecycleAdmissionError(
                "graph registry generation digest drift"
            )
        subject = first["subject"]
        if (
            subject["graph_registry_sha256"] != _sha(graph_registry_bytes)
            or subject["graph_registry_generation_sha256"]
            != graph_registry["registry_generation_sha256"]
            or subject["source_registry_generation_sha256"]
            != graph_registry["source"]["source_registry_generation_sha256"]
            or subject["canonical_configuration_digest"]
            != graph_registry["source"]["canonical_configuration_digest"]
            or subject["active_source_submission_id"]
            != graph_registry["source"]["source_active_submission_id"]
            or subject["active_graph_submission_id"]
            != graph_registry["active_submission_id"]
            or subject["active_graph_decision_id"]
            != graph_registry["active_graph_decision_id"]
            or subject["active_graph_decision_sha256"]
            != graph_registry["active_graph_decision_sha256"]
        ):
            raise GraphLifecycleAdmissionError(
                "projection/graph-registry subject drift"
            )
        source_counts = graph_registry["source"]["source_lifecycle"]
        graph_counts = {
            key: graph_registry["summary"][key]
            for key in (
                "submitted_count",
                "accepted_count",
                "rejected_count",
                "revoked_count",
                "superseded_count",
            )
        }
        lifecycle = first["lifecycle"]
        if (
            lifecycle["source_counts"] != source_counts
            or lifecycle["graph_counts"] != graph_counts
            or lifecycle["source_active_state"]
            != ("accepted" if source_counts["accepted_count"] == 1 else "absent")
            or lifecycle["graph_active_state"]
            != ("accepted" if graph_counts["accepted_count"] == 1 else "absent")
        ):
            raise GraphLifecycleAdmissionError(
                "projection/registry lifecycle counts drift"
            )
        summary = first["graph_summary"]
        active = graph_registry["active_submission_id"] is not None
        if (
            summary["canonical_graph_count"] != (1 if active else 0)
            or summary["actuator_mapping_count"]
            != graph_registry["summary"]["actuator_mapping_count"]
            or summary["ros_mapping_count"]
            != graph_registry["summary"]["ros_mapping_count"]
            or len(projections["host"]["outputs"]["frame_ids"])
            != summary["frame_count"]
            or len(projections["host"]["outputs"]["actuator_ids"])
            != summary["actuator_mapping_count"]
            or len(projections["ros"]["outputs"]["ros_joint_names"])
            != summary["ros_mapping_count"]
            or len(projections["simulator"]["outputs"]["coupling_ids"])
            != summary["coupling_count"]
            or len(projections["simulator"]["outputs"]["closure_ids"])
            != summary["closure_count"]
            or projections["host"]["outputs"]["command_handle_count"] != 0
            or projections["ros"]["outputs"]["materialized_urdf_fragment_count"]
            != 0
            or projections["simulator"]["outputs"]["physical_plant_count"] != 0
            or projections["ui"]["outputs"]["exposed_local_path_count"] != 0
        ):
            raise GraphLifecycleAdmissionError(
                "projection output/count/redaction drift"
            )
        self._projections = copy.deepcopy(projections)

    @classmethod
    def load(
        cls,
        projection_root: Path = DEFAULT_PROJECTION_ROOT,
        projection_schema_path: Path = DEFAULT_SCHEMA,
        graph_registry_path: Path = DEFAULT_GRAPH_REGISTRY,
        graph_registry_schema_path: Path = DEFAULT_GRAPH_REGISTRY_SCHEMA,
    ) -> "DropbearGraphLifecycleProjectionSetV2":
        try:
            registry_bytes = graph_registry_path.read_bytes()
        except OSError as error:
            raise GraphLifecycleAdmissionError(
                f"cannot read graph registry: {error}"
            ) from error
        return cls(
            {
                kind: _load(projection_root / f"{kind}.json")
                for kind in VIEW_KINDS
            },
            _load(projection_schema_path),
            _load_bytes(registry_bytes, "graph registry V2"),
            _load(graph_registry_schema_path),
            registry_bytes,
        )

    @property
    def canonical_configuration_digest(self) -> str:
        return self._projections["host"]["subject"][
            "canonical_configuration_digest"
        ]

    @property
    def source_registry_generation_sha256(self) -> str:
        return self._projections["host"]["subject"][
            "source_registry_generation_sha256"
        ]

    @property
    def graph_registry_generation_sha256(self) -> str:
        return self._projections["host"]["subject"][
            "graph_registry_generation_sha256"
        ]

    def view(self, kind: str) -> LifecycleGraphView:
        if kind not in VIEW_KINDS:
            raise GraphLifecycleAdmissionError(
                f"unknown exact lifecycle graph view: {kind}"
            )
        value = self._projections[kind]
        return LifecycleGraphView(
            view_kind=kind,
            source_active_state=value["lifecycle"]["source_active_state"],
            graph_active_state=value["lifecycle"]["graph_active_state"],
            canonical_graph_count=value["graph_summary"][
                "canonical_graph_count"
            ],
            actuator_mapping_count=value["graph_summary"][
                "actuator_mapping_count"
            ],
            ros_mapping_count=value["graph_summary"]["ros_mapping_count"],
            blockers=tuple(value["blockers"]),
        )

    def require_canonical_graph(
        self,
        *,
        source_registry_generation_sha256: str | None = None,
        graph_registry_generation_sha256: str | None = None,
    ) -> GraphAuthorityGeneration:
        if (
            source_registry_generation_sha256 is not None
            and source_registry_generation_sha256
            != self.source_registry_generation_sha256
        ):
            raise GraphLifecycleAdmissionError(
                "stale source registry generation"
            )
        if (
            graph_registry_generation_sha256 is not None
            and graph_registry_generation_sha256
            != self.graph_registry_generation_sha256
        ):
            raise GraphLifecycleAdmissionError(
                "stale graph registry generation"
            )
        subject = self._projections["host"]["subject"]
        if self.view("host").canonical_graph_count != 1:
            raise GraphLifecycleAdmissionError(
                "canonical Dropbear graph V2 is unavailable: "
                + ",".join(self.view("host").blockers)
            )
        return GraphAuthorityGeneration(
            canonical_configuration_digest=subject[
                "canonical_configuration_digest"
            ],
            source_registry_generation_sha256=self.source_registry_generation_sha256,
            graph_registry_generation_sha256=self.graph_registry_generation_sha256,
            graph_submission_id=subject["active_graph_submission_id"],
            graph_decision_id=subject["active_graph_decision_id"],
            graph_decision_sha256=subject["active_graph_decision_sha256"],
        )


__all__ = [
    "DropbearGraphLifecycleProjectionSetV2",
    "GraphAuthorityGeneration",
    "GraphLifecycleAdmissionError",
    "LifecycleGraphView",
]
