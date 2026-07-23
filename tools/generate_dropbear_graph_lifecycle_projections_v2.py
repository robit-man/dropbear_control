#!/usr/bin/env python3
"""Generate lifecycle-aware V2 Dropbear graph consumer projections."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/dropbear-graph-lifecycle-projection-v2.schema.json"
GRAPH_REGISTRY = ROOT / "generated/dropbear_graph_registry_v2/registry.json"
REGISTRY_MANAGER = ROOT / "tools/manage_dropbear_graph_registry_v2.py"
GRAPH_MANAGER = ROOT / "tools/manage_dropbear_graph_v2.py"
OUTPUT_ROOT = ROOT / "generated/dropbear_graph_lifecycle_projection_v2"
VIEW_KINDS = ("host", "ros", "simulator", "ui")


class GraphLifecycleProjectionError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GraphLifecycleProjectionError(message)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GraphLifecycleProjectionError(f"cannot read {path}: {error}") from error
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def module_from(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise GraphLifecycleProjectionError(f"cannot load validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def validate(value: dict[str, Any]) -> None:
    schema = load(SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise GraphLifecycleProjectionError(
            "graph lifecycle projection schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        value["integrity"]["record_sha256"] == sha_bytes(digest_payload(value)),
        "graph lifecycle projection digest mismatch",
    )


def validate_registry_artifact(registry: dict[str, Any]) -> None:
    registry_manager = module_from(
        REGISTRY_MANAGER, "graph_registry_for_lifecycle_projection"
    )
    schema = load(registry_manager.REGISTRY_SCHEMA)
    errors = list(Draft202012Validator(schema).iter_errors(registry))
    require(not errors, "graph registry schema failed before projection")
    require(
        registry["registry_generation_sha256"]
        == sha_bytes(registry_manager.registry_generation_payload(registry))
        and registry["integrity"]["record_sha256"]
        == sha_bytes(registry_manager.digest_payload(registry)),
        "graph registry digest failed before projection",
    )


def build_from_registry(
    registry: dict[str, Any],
    active_decision: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    validate_registry_artifact(registry)
    active = registry["active_submission_id"] is not None
    require(
        active
        == (
            registry["active_graph_decision_id"] is not None
            and registry["active_graph_decision_sha256"] is not None
            and registry["summary"]["canonical_graph_count"] == 1
        ),
        "graph registry active identity/count drift before projection",
    )
    if active:
        require(active_decision is not None, "active graph decision is missing")
        require(
            active_decision["decision_id"]
            == registry["active_graph_decision_id"]
            and sha_bytes(canonical_bytes(active_decision))
            == registry["active_graph_decision_sha256"]
            and active_decision["canonical_graph_admissible"] is True
            and active_decision["subject"]["source_registry_generation_sha256"]
            == registry["source"]["source_registry_generation_sha256"],
            "active graph decision/registry identity drift",
        )
        try:
            module_from(
                GRAPH_MANAGER, "graph_manager_for_lifecycle_projection"
            ).validate_graph(active_decision["graph"], require_dropbear=True)
        except ValueError as error:
            raise GraphLifecycleProjectionError(
                f"active graph semantics failed before projection: {error}"
            ) from error
        graph = active_decision["graph"]
    else:
        require(active_decision is None, "inactive registry carries graph decision")
        graph = {
            "graph_id": None,
            "frames": [],
            "links": [],
            "joints": [],
            "couplings": [],
            "closures": [],
            "dof_ledger": {"coordinates": [], "summary": {"independent": 0}},
            "actuator_bindings": [],
            "ros_mappings": [],
        }
    source_counts = registry["source"]["source_lifecycle"]
    graph_counts = {
        key: registry["summary"][key]
        for key in (
            "submitted_count",
            "accepted_count",
            "rejected_count",
            "revoked_count",
            "superseded_count",
        )
    }
    subject = {
        "source_registry_generation_sha256": registry["source"][
            "source_registry_generation_sha256"
        ],
        "canonical_configuration_digest": registry["source"][
            "canonical_configuration_digest"
        ],
        "graph_registry_path": GRAPH_REGISTRY.relative_to(ROOT).as_posix(),
        "graph_registry_sha256": sha_bytes(canonical_bytes(registry)),
        "graph_registry_generation_sha256": registry[
            "registry_generation_sha256"
        ],
        "active_source_submission_id": registry["source"][
            "source_active_submission_id"
        ],
        "active_graph_submission_id": registry["active_submission_id"],
        "active_graph_decision_id": registry["active_graph_decision_id"],
        "active_graph_decision_sha256": registry[
            "active_graph_decision_sha256"
        ],
    }
    lifecycle = {
        "source_active_state": (
            "accepted" if source_counts["accepted_count"] == 1 else "absent"
        ),
        "source_counts": source_counts,
        "graph_active_state": "accepted" if active else "absent",
        "graph_counts": graph_counts,
    }
    graph_summary = {
        "canonical_graph_count": 1 if active else 0,
        "frame_count": len(graph["frames"]),
        "link_count": len(graph["links"]),
        "joint_count": len(graph["joints"]),
        "coordinate_count": len(graph["dof_ledger"]["coordinates"]),
        "independent_coordinate_count": graph["dof_ledger"]["summary"][
            "independent"
        ],
        "coupling_count": len(graph["couplings"]),
        "closure_count": len(graph["closures"]),
        "actuator_mapping_count": len(graph["actuator_bindings"]),
        "ros_mapping_count": len(graph["ros_mappings"]),
    }
    require(
        graph_summary["actuator_mapping_count"]
        == registry["summary"]["actuator_mapping_count"]
        and graph_summary["ros_mapping_count"]
        == registry["summary"]["ros_mapping_count"],
        "graph registry/projected mapping counts drift",
    )
    outputs = {
        "host": {
            "status_only": not active,
            "frame_ids": sorted(row["frame_id"] for row in graph["frames"]),
            "actuator_ids": sorted(
                row["actuator_id"] for row in graph["actuator_bindings"]
            ),
            "command_coordinate_ids": sorted(
                row["command_coordinate_id"]
                for row in graph["actuator_bindings"]
            ),
            "command_handle_count": 0,
        },
        "ros": {
            "status_only": not active,
            "ros_joint_names": sorted(
                row["ros_joint_name"] for row in graph["ros_mappings"]
            ),
            "mapped_coordinate_ids": sorted(
                row["coordinate_id"] for row in graph["ros_mappings"]
                if row["status"] == "mapped"
            ),
            "actuator_ids": sorted(
                {
                    actuator_id
                    for row in graph["ros_mappings"]
                    for actuator_id in row["actuator_ids"]
                }
            ),
            "materialized_urdf_fragment_count": 0,
        },
        "simulator": {
            "status_only": not active,
            "authoritative_graph_ids": [graph["graph_id"]] if active else [],
            "coupling_ids": sorted(
                row["coupling_id"] for row in graph["couplings"]
            ),
            "closure_ids": sorted(
                row["closure_id"] for row in graph["closures"]
            ),
            "physical_plant_count": 0,
        },
        "ui": {
            "status_only": not active,
            "canonical_graph_count": graph_summary["canonical_graph_count"],
            "actuator_mapping_count": graph_summary["actuator_mapping_count"],
            "ros_mapping_count": graph_summary["ros_mapping_count"],
            "revoked_count": graph_counts["revoked_count"],
            "superseded_count": graph_counts["superseded_count"],
            "exposed_local_path_count": 0,
        },
    }
    projections = {}
    for kind in VIEW_KINDS:
        value = {
            "schema_version": "dropbear-graph-lifecycle-projection/2",
            "artifact_id": f"dropbear-graph-lifecycle-projection-{kind}",
            "view_kind": kind,
            "authority": "derived_graph_projection_only",
            "subject": subject,
            "lifecycle": lifecycle,
            "graph_summary": graph_summary,
            "blockers": registry["blockers"],
            "outputs": outputs[kind],
            "support_granted": False,
            "physical_motion_authority": False,
            "integrity": {"record_sha256": "0" * 64},
        }
        value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))
        validate(value)
        projections[kind] = value
    validate_projection_set(projections)
    return projections


def validate_projection_set(values: dict[str, dict[str, Any]]) -> None:
    require(set(values) == set(VIEW_KINDS), "projection V2 view set is not exact")
    first = values["host"]
    for kind in VIEW_KINDS:
        value = values[kind]
        validate(value)
        require(value["view_kind"] == kind, "projection V2 kind drift")
        require(
            value["subject"] == first["subject"]
            and value["lifecycle"] == first["lifecycle"]
            and value["graph_summary"] == first["graph_summary"]
            and value["blockers"] == first["blockers"],
            "projection V2 consumer parity drift",
        )
    summary = first["graph_summary"]
    require(
        len(values["host"]["outputs"]["frame_ids"]) == summary["frame_count"]
        and len(values["host"]["outputs"]["actuator_ids"])
        == summary["actuator_mapping_count"]
        and len(values["ros"]["outputs"]["ros_joint_names"])
        == summary["ros_mapping_count"]
        and len(values["simulator"]["outputs"]["coupling_ids"])
        == summary["coupling_count"]
        and len(values["simulator"]["outputs"]["closure_ids"])
        == summary["closure_count"]
        and values["ui"]["outputs"]["canonical_graph_count"]
        == summary["canonical_graph_count"]
        and values["ui"]["outputs"]["exposed_local_path_count"] == 0,
        "projection V2 output/count/redaction parity drift",
    )


def build() -> dict[str, dict[str, Any]]:
    manager = module_from(REGISTRY_MANAGER, "graph_registry_for_tracked_projection")
    try:
        registry = manager.check()
    except ValueError as error:
        raise GraphLifecycleProjectionError(
            f"tracked graph registry failed: {error}"
        ) from error
    return build_from_registry(registry)


def expected_paths() -> dict[str, Path]:
    return {kind: OUTPUT_ROOT / f"{kind}.json" for kind in VIEW_KINDS}


def unexpected_paths() -> set[Path]:
    expected = set(expected_paths().values())
    if not OUTPUT_ROOT.is_dir():
        return set()
    return {
        path
        for path in OUTPUT_ROOT.rglob("*")
        if path.is_file() and path not in expected
    }


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def generate() -> dict[str, dict[str, Any]]:
    require(not unexpected_paths(), "projection V2 namespace has unexpected files")
    values = build()
    for kind, path in expected_paths().items():
        atomic_write(path, values[kind])
    return values


def check() -> dict[str, dict[str, Any]]:
    require(not unexpected_paths(), "projection V2 namespace has unexpected files")
    values = build()
    for kind, path in expected_paths().items():
        require(
            path.is_file()
            and path.read_bytes() == canonical_bytes(values[kind]),
            f"{kind} graph lifecycle projection V2 drift",
        )
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    values = generate() if args.generate else check()
    summary = values["host"]["graph_summary"]
    lifecycle = values["host"]["lifecycle"]
    print(
        "DROPBEAR_GRAPH_LIFECYCLE_PROJECTIONS_V2_OK "
        f"views={len(values)} source={lifecycle['source_active_state']} "
        f"graph={lifecycle['graph_active_state']} "
        f"frames={summary['frame_count']} "
        f"actuators={summary['actuator_mapping_count']} "
        f"ros={summary['ros_mapping_count']} support=false motion=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, GraphLifecycleProjectionError, ValueError) as error:
        print(f"Dropbear graph lifecycle projections V2 failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
