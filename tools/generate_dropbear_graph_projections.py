#!/usr/bin/env python3
"""Generate byte-stable denial-only Dropbear graph consumer projections."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/dropbear-graph-projection.schema.json"
GRAPH_MANAGER = ROOT / "tools/manage_dropbear_graph_review.py"
GRAPH_STATUS = ROOT / "generated/dropbear_graph_review/status.json"
INVENTORY = ROOT / "generated/dropbear_description/inventory.json"
OUTPUT_ROOT = ROOT / "generated/dropbear_graph_projection"
VIEW_KINDS = ("host", "ros", "simulator", "ui")
EXPECTED_OUTPUTS = {
    "host": {
        "status_only": True,
        "transform_count": 0,
        "actuator_mapping_count": 0,
        "command_handle_count": 0,
    },
    "ros": {
        "status_only": True,
        "urdf_fragment_count": 0,
        "transmission_count": 0,
        "ros2_control_hardware_mapping_count": 0,
    },
    "simulator": {
        "status_only": True,
        "authoritative_graph_count": 0,
        "physical_plant_count": 0,
        "actuator_mapping_count": 0,
    },
    "ui": {
        "status_only": True,
        "exposed_local_path_count": 0,
        "downloadable_runtime_description_count": 0,
        "actuator_mapping_count": 0,
    },
}


class GraphProjectionError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GraphProjectionError(message)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GraphProjectionError(f"cannot read {path}: {error}") from error
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def graph_manager() -> Any:
    name = "manage_dropbear_graph_review_for_projections"
    spec = importlib.util.spec_from_file_location(name, GRAPH_MANAGER)
    if spec is None or spec.loader is None:
        raise GraphProjectionError("cannot load graph-review manager")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(value: dict[str, Any]) -> None:
    schema = load(SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise GraphProjectionError(
            "graph projection schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def build() -> dict[str, dict[str, Any]]:
    module = graph_manager()
    try:
        template, _, status = module.check()
    except ValueError as error:
        raise GraphProjectionError(f"graph-review input failed: {error}") from error
    inventory = load(INVENTORY)
    require(
        status["summary"] == {
            "question_count": 161,
            "unanswered_question_count": 161,
            "submitted_decision_count": 0,
            "accepted_graph_count": 0,
            "canonical_graph_count": 0,
            "runtime_ros_actuator_mapping_count": 0,
            "canonical_graph_admissible": False,
        },
        "graph-review status is not the exact denial baseline",
    )
    require(
        not status["accepted_graph_decision_ids"]
        and status["support_granted"] is False
        and status["physical_motion_authority"] is False,
        "graph-review status contains authority",
    )
    subject = {
        "graph_review_status_sha256": sha_bytes(GRAPH_STATUS.read_bytes()),
        "inventory_sha256": sha_bytes(INVENTORY.read_bytes()),
        "canonical_configuration_digest": inventory["reconciliation"][
            "canonical_configuration_digest"
        ],
        "graph_decision_id": template["decision_id"],
    }
    projections = {}
    for kind in VIEW_KINDS:
        projection = {
            "schema_version": "dropbear-graph-projection/1",
            "artifact_id": f"dropbear-graph-projection-{kind}",
            "view_kind": kind,
            "authority": "derived_denial_only",
            "subject": subject,
            "summary": status["summary"],
            "blockers": status["blockers"],
            "outputs": EXPECTED_OUTPUTS[kind],
            "support_granted": False,
            "physical_motion_authority": False,
        }
        validate(projection)
        projections[kind] = projection
    return projections


def expected_paths() -> dict[str, Path]:
    return {kind: OUTPUT_ROOT / f"{kind}.json" for kind in VIEW_KINDS}


def unexpected_paths() -> set[Path]:
    if not OUTPUT_ROOT.is_dir():
        return set()
    return {
        path
        for path in OUTPUT_ROOT.rglob("*")
        if path.is_file() and path not in set(expected_paths().values())
    }


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def generate() -> dict[str, dict[str, Any]]:
    require(not unexpected_paths(), "projection output namespace has unexpected files")
    values = build()
    for kind, path in expected_paths().items():
        atomic_write(path, canonical_bytes(values[kind]))
    return values


def check() -> dict[str, dict[str, Any]]:
    require(not unexpected_paths(), "projection output namespace has unexpected files")
    values = build()
    for kind, path in expected_paths().items():
        require(
            path.is_file()
            and path.read_bytes() == canonical_bytes(values[kind]),
            f"{kind} graph projection drift",
        )
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--generate", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = parser.parse_args()
    values = generate() if args.generate else check()
    print(
        "DROPBEAR_GRAPH_PROJECTIONS_OK "
        f"views={len(values)} questions=161 canonical=0 mappings=0 "
        "transforms=0 urdf=0 plants=0 paths=0 support=false motion=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, GraphProjectionError, ValueError) as error:
        print(f"Dropbear graph projection failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
