#!/usr/bin/env python3
"""Generate and validate the structured Dropbear graph V2 denial baseline."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "generated/dropbear_description/inventory.json"
SOURCE_REGISTRY = ROOT / "generated/dropbear_source_registry_v2/registry.json"
V1_TEMPLATE_ROOT = ROOT / "generated/dropbear_graph_review/templates"
DECISION_SCHEMA = ROOT / "schemas/dropbear-graph-v2-decision.schema.json"
STATUS_SCHEMA = ROOT / "schemas/dropbear-graph-v2-status.schema.json"
OUTPUT_ROOT = ROOT / "generated/dropbear_graph_v2"
CANDIDATE_ROOT = OUTPUT_ROOT / "candidates"
STATUS = OUTPUT_ROOT / "status.json"
VERSION = "dropbear-graph-decision/2"
EXPECTED_ACTUATORS = {
    f"actuator-{side}-{joint}"
    for side in ("left", "right")
    for joint in (
        "hip-yaw",
        "hip-roll",
        "hip-pitch",
        "knee",
        "inner-calf",
        "outer-calf",
    )
}
AUTOMATION_IDENTIFIERS = (
    "automated",
    "automation",
    "codex",
    "generator",
    "same-agent",
    "self-review",
    "language-model",
    " llm",
)
ACTIVITY_CLASS = {
    "active": "independent",
    "passive": "passive",
    "mimic": "dependent",
    "coupled": "dependent",
    "fixed": "fixed",
    "simulator_only": "simulator_only",
}


class GraphV2Error(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GraphV2Error(message)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GraphV2Error(f"cannot read {path}: {error}") from error
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def schema_validate(
    value: dict[str, Any], schema: dict[str, Any], label: str
) -> None:
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise GraphV2Error(
            f"{label} schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def one_v1_template() -> tuple[Path, dict[str, Any]]:
    paths = sorted(V1_TEMPLATE_ROOT.glob("graphdecision-*.json"))
    require(len(paths) == 1, "graph V2 requires exactly one V1 migration template")
    value = load(paths[0])
    require(
        value["schema_version"] == "dropbear-graph-decision/1"
        and len(value["question_responses"]) == 161,
        "V1 graph migration subject drift",
    )
    return paths[0], value


def source_registry_manager() -> Any:
    name = "manage_dropbear_source_registry_for_graph_v2"
    path = ROOT / "tools/manage_dropbear_source_registry_v2.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise GraphV2Error("cannot load source registry V2 validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def current_inputs() -> tuple[dict[str, Any], dict[str, Any], Path, dict[str, Any]]:
    inventory = load(INVENTORY)
    registry = load(SOURCE_REGISTRY)
    v1_path, v1 = one_v1_template()
    require(
        inventory["schema_version"] == "dropbear-description-inventory/1"
        and inventory["summary"]["review_question_count"] == 161,
        "graph V2 inventory baseline drift",
    )
    require(
        registry["schema_version"] == "dropbear-source-authority-registry/2"
        and registry["support_granted"] is False
        and registry["physical_motion_authority"] is False,
        "graph V2 source registry baseline drift",
    )
    try:
        source_registry_manager().check()
    except ValueError as error:
        raise GraphV2Error(f"source registry V2 replay failed: {error}") from error
    return inventory, registry, v1_path, v1


def subject(
    inventory: dict[str, Any],
    registry: dict[str, Any],
    v1_path: Path,
    v1: dict[str, Any],
) -> dict[str, Any]:
    return {
        "repository_commit": inventory["repository"]["commit"],
        "repository_tree_id": inventory["repository"]["tree_id"],
        "canonical_configuration_digest": inventory["reconciliation"][
            "canonical_configuration_digest"
        ],
        "inventory_path": INVENTORY.relative_to(ROOT).as_posix(),
        "inventory_sha256": sha_file(INVENTORY),
        "source_registry_path": SOURCE_REGISTRY.relative_to(ROOT).as_posix(),
        "source_registry_sha256": sha_bytes(canonical_bytes(registry)),
        "source_registry_generation_sha256": registry[
            "registry_generation_sha256"
        ],
        "active_source_submission_id": registry["active_submission_id"],
        "active_source_decision_id": registry["active_decision_id"],
        "active_source_decision_sha256": registry["active_decision_sha256"],
        "v1_graph_path": v1_path.relative_to(ROOT).as_posix(),
        "v1_graph_sha256": sha_bytes(canonical_bytes(v1)),
        "v1_graph_decision_id": v1["decision_id"],
        "v1_question_count": len(v1["question_responses"]),
    }


def identifier(prefix: str, payload: Any) -> str:
    return prefix + sha_bytes(canonical_bytes(payload))[:20]


def empty_graph(subject_value: dict[str, Any]) -> dict[str, Any]:
    return {
        "graph_id": identifier("dropbeargraphv2-", subject_value),
        "graph_revision": 2,
        "base_frame_id": None,
        "frames": [],
        "aliases": [],
        "links": [],
        "joints": [],
        "symmetry_pairs": [],
        "couplings": [],
        "singularities": [],
        "closures": [],
        "dof_ledger": {
            "coordinates": [],
            "summary": {
                "independent": 0,
                "dependent": 0,
                "passive": 0,
                "fixed": 0,
                "simulator_only": 0,
                "total_coordinates": 0,
                "physical_generalized_dof": 0,
            },
        },
        "ownership": [],
        "dependencies": [],
        "actuator_bindings": [],
        "ros_mappings": [],
    }


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def template(
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inventory, current_registry, v1_path, v1 = current_inputs()
    registry_value = registry if registry is not None else current_registry
    source_registry_manager().validate_registry(registry_value)
    subject_value = subject(inventory, registry_value, v1_path, v1)
    decision = {
        "schema_version": VERSION,
        "record_state": "draft",
        "record_revision": 2,
        "decision_id": identifier("graphv2decision-", subject_value),
        "supersedes_decision_id": None,
        "subject": subject_value,
        "migration": {
            "mode": "explicit_v1_to_v2",
            "v1_decision_id": v1["decision_id"],
            "v1_decision_sha256": sha_bytes(canonical_bytes(v1)),
            "v1_question_count": 161,
            "resolved_v1_question_count": 0,
            "unresolved_v1_question_count": 161,
            "migration_complete": False,
            "evidence_refs": [],
        },
        "reviewer": {
            "reviewer_id": None,
            "organization_or_team": None,
            "mechanical_graph_competence_attested": None,
            "independence_attested": None,
            "reviewed_at": None,
            "review_assertion": None,
            "signature_evidence_refs": [],
        },
        "disposition": None,
        "graph": empty_graph(subject_value),
        "decision_complete": False,
        "canonical_graph_admissible": False,
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(decision)
    return decision


def finite(values: list[float], label: str) -> None:
    require(all(math.isfinite(value) for value in values), f"{label} is not finite")


def unique_rows(rows: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    identifiers = [row[key] for row in rows]
    require(
        len(identifiers) == len(set(identifiers)),
        f"duplicate {label} identifier",
    )
    return {row[key]: row for row in rows}


def no_cycles(parent_by_child: dict[str, str | None], label: str) -> None:
    for start in parent_by_child:
        seen: set[str] = set()
        node: str | None = start
        while node is not None:
            require(node not in seen, f"{label} cycle")
            seen.add(node)
            node = parent_by_child.get(node)


def validate_graph(
    graph: dict[str, Any],
    *,
    require_dropbear: bool = False,
) -> None:
    decision_schema = load(DECISION_SCHEMA)
    graph_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/graph",
        "$defs": decision_schema["$defs"],
    }
    schema_validate(graph, graph_schema, "structured graph V2")
    collections = (
        graph["frames"],
        graph["aliases"],
        graph["links"],
        graph["joints"],
        graph["symmetry_pairs"],
        graph["couplings"],
        graph["singularities"],
        graph["closures"],
        graph["dof_ledger"]["coordinates"],
        graph["ownership"],
        graph["dependencies"],
        graph["actuator_bindings"],
        graph["ros_mappings"],
    )
    if not any(collections):
        require(
            graph["base_frame_id"] is None
            and graph["dof_ledger"]["summary"]
            == {
                "independent": 0,
                "dependent": 0,
                "passive": 0,
                "fixed": 0,
                "simulator_only": 0,
                "total_coordinates": 0,
                "physical_generalized_dof": 0,
            },
            "empty graph V2 is partially promoted",
        )
        require(not require_dropbear, "complete Dropbear graph V2 is empty")
        return

    frames = unique_rows(graph["frames"], "frame_id", "frame")
    require(graph["base_frame_id"] in frames, "base frame is missing")
    roots = [
        frame["frame_id"]
        for frame in graph["frames"]
        if frame["parent_frame_id"] is None
    ]
    require(roots == [graph["base_frame_id"]], "frame graph does not have one exact root")
    parents: dict[str, str | None] = {}
    for frame in graph["frames"]:
        parent = frame["parent_frame_id"]
        transform = frame["transform"]
        require(
            parent is None or parent in frames,
            "frame parent reference is missing",
        )
        require(
            transform["expressed_in_parent_frame_id"] == parent,
            "frame transform expressed-in parent drift",
        )
        finite(transform["translation_xyz_m"], "frame translation")
        finite(transform["rotation_xyzw"], "frame quaternion")
        norm = math.sqrt(sum(value * value for value in transform["rotation_xyzw"]))
        require(abs(norm - 1.0) <= 1e-9, "frame quaternion is not unit length")
        parents[frame["frame_id"]] = parent
    no_cycles(parents, "frame")

    links = unique_rows(graph["links"], "link_id", "link")
    link_frames: set[str] = set()
    for link in graph["links"]:
        require(
            link["frame_id"] in frames
            and frames[link["frame_id"]]["kind"] in {"base", "link"}
            and link["frame_id"] not in link_frames
            and frames[link["frame_id"]]["chirality"] == link["chirality"],
            "link/frame identity or chirality drift",
        )
        link_frames.add(link["frame_id"])
    root_links = [
        link_id
        for link_id, link in links.items()
        if link["frame_id"] == graph["base_frame_id"]
    ]
    require(len(root_links) == 1, "graph does not have one base link")

    joints = unique_rows(graph["joints"], "joint_id", "joint")
    child_parent: dict[str, str] = {}
    for joint in graph["joints"]:
        require(
            joint["parent_link_id"] in links
            and joint["child_link_id"] in links
            and joint["parent_link_id"] != joint["child_link_id"],
            "joint link reference is missing/self-referential",
        )
        require(
            joint["origin_frame_id"] in frames,
            "joint origin frame is missing",
        )
        require(
            joint["chirality"] == links[joint["child_link_id"]]["chirality"],
            "joint/child chirality drift",
        )
        if joint["joint_type"] == "fixed":
            require(
                joint["activity"] == "fixed" and joint["axis"] is None,
                "fixed joint activity/axis drift",
            )
        else:
            require(joint["axis"] is not None, "moving joint axis is missing")
            axis = joint["axis"]
            require(
                axis["expressed_in_frame_id"] in frames,
                "joint axis expressed-in frame is missing",
            )
            finite(axis["xyz_unit"], "joint axis")
            require(
                abs(math.sqrt(sum(value * value for value in axis["xyz_unit"])) - 1.0)
                <= 1e-9,
                "joint axis is not unit length",
            )
        if joint["activity"] != "simulator_only":
            child = joint["child_link_id"]
            require(child not in child_parent, "physical link has multiple parents")
            child_parent[child] = joint["parent_link_id"]
    require(root_links[0] not in child_parent, "base link has a parent")
    for link_id in links:
        seen: set[str] = set()
        cursor = link_id
        while cursor in child_parent:
            require(cursor not in seen, "physical joint cycle")
            seen.add(cursor)
            cursor = child_parent[cursor]
        require(cursor == root_links[0], "physical link is disconnected")

    coordinates = unique_rows(
        graph["dof_ledger"]["coordinates"], "coordinate_id", "coordinate"
    )
    coordinate_joint_ids: set[str] = set()
    counts = Counter()
    for coordinate in coordinates.values():
        joint_id = coordinate["joint_id"]
        require(
            joint_id in joints and joint_id not in coordinate_joint_ids,
            "coordinate joint reference is missing/duplicate",
        )
        coordinate_joint_ids.add(joint_id)
        joint = joints[joint_id]
        require(
            coordinate["coordinate_id"] == joint["coordinate_id"]
            and coordinate["classification"] == ACTIVITY_CLASS[joint["activity"]]
            and coordinate["commandable"]
            == (coordinate["classification"] == "independent"),
            "joint/coordinate activity or commandability drift",
        )
        expected_unit = "m" if joint["joint_type"] == "prismatic" else (
            "dimensionless" if joint["joint_type"] == "fixed" else "rad"
        )
        require(coordinate["unit"] == expected_unit, "coordinate unit drift")
        counts[coordinate["classification"]] += 1
    require(
        coordinate_joint_ids == set(joints),
        "joint/DOF ledger coverage is not exact",
    )
    expected_summary = {
        "independent": counts["independent"],
        "dependent": counts["dependent"],
        "passive": counts["passive"],
        "fixed": counts["fixed"],
        "simulator_only": counts["simulator_only"],
        "total_coordinates": len(coordinates),
        "physical_generalized_dof": (
            counts["independent"] + counts["passive"]
        ),
    }
    require(
        graph["dof_ledger"]["summary"] == expected_summary,
        "DOF ledger summary disagreement",
    )

    aliases: set[tuple[str, str]] = set()
    targets = {
        "frame": set(frames),
        "link": set(links),
        "joint": set(joints),
        "coordinate": set(coordinates),
        "actuator": {
            row["actuator_id"] for row in graph["actuator_bindings"]
        },
    }
    for alias in graph["aliases"]:
        key = (alias["alias_namespace"], alias["alias"])
        require(key not in aliases, "alias namespace/name collision")
        aliases.add(key)
        require(
            alias["target_id"] in targets[alias["target_kind"]],
            "alias target is missing",
        )

    couplings = unique_rows(graph["couplings"], "coupling_id", "coupling")
    coupling_outputs: set[str] = set()
    for coupling in graph["couplings"]:
        inputs = coupling["input_coordinate_ids"]
        output = coupling["output_coordinate_id"]
        require(
            all(identifier_value in coordinates for identifier_value in inputs)
            and output in coordinates
            and output not in inputs
            and coordinates[output]["classification"] == "dependent"
            and output not in coupling_outputs,
            "coupling coordinate closure/output ownership drift",
        )
        coupling_outputs.add(output)
        terms = coupling["equation"]["terms"]
        finite(
            [row["coefficient"] for row in terms]
            + [coupling["equation"]["offset_si"]],
            "coupling equation",
        )
        require(
            {row["coordinate_id"] for row in terms} == set(inputs)
            and len(terms) == len(inputs)
            and all(row["coefficient"] != 0.0 for row in terms),
            "coupling equation terms do not exactly cover inputs",
        )
        domains = coupling["valid_domain"]
        require(
            {row["coordinate_id"] for row in domains} == set(inputs)
            and len(domains) == len(inputs)
            and all(
                math.isfinite(row["lower"])
                and math.isfinite(row["upper"])
                and row["lower"] < row["upper"]
                and row["unit"] == coordinates[row["coordinate_id"]]["unit"]
                for row in domains
            ),
            "coupling valid domain drift",
        )
        output_joint = joints[coordinates[output]["joint_id"]]
        require(
            (coupling["kind"] == "mimic") == (output_joint["activity"] == "mimic"),
            "mimic coupling/joint activity drift",
        )
    expected_dependent = {
        identifier_value
        for identifier_value, coordinate in coordinates.items()
        if coordinate["classification"] == "dependent"
    }
    require(
        coupling_outputs == expected_dependent,
        "dependent coordinates do not have one exact coupling",
    )

    singularities = unique_rows(
        graph["singularities"], "singularity_id", "singularity"
    )
    for singularity in singularities.values():
        require(
            singularity["coupling_id"] in couplings,
            "singularity coupling is missing",
        )
        coupling = couplings[singularity["coupling_id"]]
        require(
            singularity["detection"]["coordinate_id"]
            in (
                set(coupling["input_coordinate_ids"])
                | {coupling["output_coordinate_id"]}
            )
            and math.isfinite(singularity["detection"]["threshold"]),
            "singularity detection coordinate/threshold drift",
        )
    for coupling in couplings.values():
        if coupling["kind"] in {"four_bar", "nonlinear"}:
            require(
                any(
                    row["coupling_id"] == coupling["coupling_id"]
                    for row in singularities.values()
                ),
                "nonlinear/four-bar coupling lacks singularity policy",
            )

    closures = unique_rows(graph["closures"], "closure_id", "closure")
    for closure in closures.values():
        require(
            all(frame_id in frames for frame_id in closure["endpoint_frame_ids"])
            and all(joint_id in joints for joint_id in closure["joint_ids"]),
            "closure frame/joint reference is missing",
        )
        if closure["kind"] == "physical_closed_chain":
            require(
                closure["physical_counterpart_status"] == "reviewed"
                and closure["solver_owner"]
                in {"physical_mechanism", "controller", "rigid_body_simulator"},
                "physical closure review/solver drift",
            )
        else:
            require(
                closure["physical_counterpart_status"] == "not_applicable"
                and closure["solver_owner"] == "rigid_body_simulator",
                "simulator-only closure leaks into physical graph",
            )

    ownership_rows = graph["ownership"]
    ownership_ids = [row["coordinate_id"] for row in ownership_rows]
    independent = {
        identifier_value
        for identifier_value, coordinate in coordinates.items()
        if coordinate["classification"] == "independent"
    }
    require(
        len(ownership_ids) == len(set(ownership_ids))
        and set(ownership_ids) == independent,
        "independent coordinate writer ownership is not exact",
    )

    dependencies = unique_rows(
        graph["dependencies"], "dependency_id", "dependency"
    )
    for dependency in dependencies.values():
        if dependency["state"] == "missing":
            require(
                dependency["subject_id"] is None
                and not dependency["evidence_refs"],
                "missing dependency contains subject/evidence",
            )
        else:
            require(
                dependency["subject_id"] is not None
                and dependency["evidence_refs"],
                "present/admitted dependency lacks subject/evidence",
            )

    actuators = unique_rows(
        graph["actuator_bindings"], "actuator_id", "actuator"
    )
    command_coordinates: set[str] = set()
    for actuator in actuators.values():
        coordinate_id = actuator["command_coordinate_id"]
        require(
            coordinate_id in independent
            and coordinate_id not in command_coordinates
            and all(joint_id in joints for joint_id in actuator["joint_ids"])
            and joints[coordinates[coordinate_id]["joint_id"]]["joint_id"]
            in actuator["joint_ids"],
            "actuator command/joint binding drift",
        )
        command_coordinates.add(coordinate_id)
        expected_side = (
            "left" if actuator["actuator_id"].startswith("actuator-left-")
            else "right"
        )
        require(actuator["chirality"] == expected_side, "actuator chirality drift")
        dependency_rows = [
            dependencies[dependency_id]
            for dependency_id in actuator["dependency_ids"]
            if dependency_id in dependencies
        ]
        require(
            len(dependency_rows) == len(actuator["dependency_ids"])
            and {row["kind"] for row in dependency_rows}
            == {"cad", "calibration", "limit", "route"}
            and all(row["state"] == "admitted" for row in dependency_rows),
            "actuator dependency closure is not exactly admitted",
        )

    entity_maps = {
        "link": links,
        "joint": joints,
        "actuator": actuators,
    }
    paired: dict[str, set[str]] = {
        "link": set(),
        "joint": set(),
        "actuator": set(),
    }
    symmetry_ids: set[str] = set()
    for pair in graph["symmetry_pairs"]:
        require(pair["symmetry_id"] not in symmetry_ids, "duplicate symmetry ID")
        symmetry_ids.add(pair["symmetry_id"])
        entities = entity_maps[pair["entity_kind"]]
        left_id = pair["left_id"]
        right_id = pair["right_id"]
        require(
            left_id in entities
            and right_id in entities
            and entities[left_id]["chirality"] == "left"
            and entities[right_id]["chirality"] == "right"
            and left_id not in paired[pair["entity_kind"]]
            and right_id not in paired[pair["entity_kind"]],
            "symmetry pair identity/chirality/uniqueness drift",
        )
        finite(
            [pair["coordinate_sign"], pair["coordinate_offset_si"]],
            "symmetry transform",
        )
        require(
            pair["coordinate_sign"] != 0.0,
            "symmetry coordinate sign cannot be zero",
        )
        paired[pair["entity_kind"]].update((left_id, right_id))
    for kind, entities in entity_maps.items():
        expected_paired = {
            identifier_value
            for identifier_value, entity in entities.items()
            if entity["chirality"] in {"left", "right"}
        }
        require(
            paired[kind] == expected_paired,
            f"{kind} chirality lacks exact symmetry disposition",
        )

    mapping_ids = unique_rows(graph["ros_mappings"], "mapping_id", "ROS mapping")
    del mapping_ids
    ros_names: set[str] = set()
    mapped_coordinates: set[str] = set()
    for mapping in graph["ros_mappings"]:
        require(mapping["ros_joint_name"] not in ros_names, "duplicate ROS joint name")
        ros_names.add(mapping["ros_joint_name"])
        require(
            mapping["coordinate_id"] in coordinates
            and all(actuator_id in actuators for actuator_id in mapping["actuator_ids"]),
            "ROS mapping coordinate/actuator reference is missing",
        )
        if mapping["status"] == "mapped":
            require(
                mapping["coordinate_id"] in independent
                and mapping["actuator_ids"]
                and mapping["coordinate_id"] not in mapped_coordinates,
                "mapped ROS coordinate is not exact/independent",
            )
            mapped_coordinates.add(mapping["coordinate_id"])
        else:
            require(
                not mapping["actuator_ids"],
                "uncommanded/passive ROS mapping contains actuator",
            )

    if require_dropbear:
        require(
            set(actuators) == EXPECTED_ACTUATORS
            and len(actuators) == 12,
            "canonical Dropbear graph lacks exact twelve actuators",
        )


def validate_decision(
    value: dict[str, Any],
    registry: dict[str, Any] | None = None,
) -> None:
    schema_validate(value, load(DECISION_SCHEMA), "graph V2 decision")
    inventory, current_registry, v1_path, v1 = current_inputs()
    registry_value = registry if registry is not None else current_registry
    source_registry_manager().validate_registry(registry_value)
    expected_subject = subject(inventory, registry_value, v1_path, v1)
    require(value["subject"] == expected_subject, "graph V2 subject drift")
    require(
        value["decision_id"]
        == identifier("graphv2decision-", expected_subject),
        "graph V2 decision ID drift",
    )
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "graph V2 decision digest mismatch",
    )
    migration = value["migration"]
    require(
        migration["v1_decision_id"] == v1["decision_id"]
        and migration["v1_decision_sha256"] == sha_bytes(canonical_bytes(v1))
        and migration["resolved_v1_question_count"]
        + migration["unresolved_v1_question_count"]
        == 161
        and migration["migration_complete"]
        == (migration["unresolved_v1_question_count"] == 0),
        "graph V2 migration accounting/source drift",
    )
    validate_graph(
        value["graph"],
        require_dropbear=value["canonical_graph_admissible"],
    )
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False,
        "graph V2 grants support/motion",
    )
    reviewer = value["reviewer"]
    if value["record_state"] == "draft":
        require(
            all(
                reviewer[field] is None
                for field in (
                    "reviewer_id",
                    "organization_or_team",
                    "mechanical_graph_competence_attested",
                    "independence_attested",
                    "reviewed_at",
                    "review_assertion",
                )
            )
            and not reviewer["signature_evidence_refs"]
            and value["disposition"] is None
            and not value["decision_complete"]
            and not value["canonical_graph_admissible"],
            "draft graph V2 is promoted/reviewed",
        )
        return
    identity = (
        f"{reviewer['reviewer_id']} {reviewer['organization_or_team']}"
    ).casefold()
    require(
        reviewer["mechanical_graph_competence_attested"] is True
        and reviewer["independence_attested"] is True
        and reviewer["reviewed_at"] is not None
        and reviewer["review_assertion"] is not None
        and reviewer["signature_evidence_refs"]
        and not any(token in identity for token in AUTOMATION_IDENTIFIERS),
        "submitted graph V2 lacks independent competent human review",
    )
    try:
        reviewed = dt.datetime.fromisoformat(
            reviewer["reviewed_at"].replace("Z", "+00:00")
        )
    except ValueError as error:
        raise GraphV2Error("graph V2 review time is invalid") from error
    require(
        reviewed.tzinfo is not None
        and reviewed.utcoffset() == dt.timedelta(0),
        "graph V2 review time is not UTC",
    )
    if value["disposition"] == "accept_graph":
        require(
            registry_value["active_submission_id"] is not None
            and registry_value["summary"]["accepted_count"] == 1
            and migration["migration_complete"]
            and value["decision_complete"]
            and value["canonical_graph_admissible"],
            "accepted graph V2 lacks active source/migration/completeness",
        )
    else:
        require(
            value["disposition"] == "reject_graph"
            and value["decision_complete"]
            and not value["canonical_graph_admissible"],
            "submitted graph V2 disposition/completeness drift",
        )


def status_digest(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return sha_bytes(canonical_bytes(payload))


def build() -> tuple[Path, dict[str, Any], dict[str, Any]]:
    decision = template()
    validate_decision(decision)
    candidate_path = CANDIDATE_ROOT / f"{decision['decision_id']}.json"
    registry = load(SOURCE_REGISTRY)
    _, _, v1_path, _ = current_inputs()
    value = {
        "schema_version": "dropbear-graph-v2-status/1",
        "artifact_id": "dropbear-graph-v2-status",
        "authority": "derived_graph_lifecycle_status",
        "source": {
            "source_registry_path": SOURCE_REGISTRY.relative_to(ROOT).as_posix(),
            "source_registry_sha256": sha_file(SOURCE_REGISTRY),
            "source_registry_generation_sha256": registry[
                "registry_generation_sha256"
            ],
            "v1_graph_path": v1_path.relative_to(ROOT).as_posix(),
            "v1_graph_sha256": sha_file(v1_path),
        },
        "candidate": {
            "path": candidate_path.relative_to(ROOT).as_posix(),
            "sha256": sha_bytes(canonical_bytes(decision)),
            "decision_id": decision["decision_id"],
            "source_registry_generation_sha256": decision["subject"][
                "source_registry_generation_sha256"
            ],
        },
        "active_graph_decision_id": None,
        "summary": {
            "candidate_count": 1,
            "submitted_count": 0,
            "accepted_count": 0,
            "canonical_graph_count": 0,
            "source_authority_active_count": 0,
            "v1_question_count": 161,
            "v1_unresolved_question_count": 161,
            "frame_count": 0,
            "coordinate_count": 0,
            "actuator_mapping_count": 0,
            "ros_mapping_count": 0,
            "canonical_graph_admissible": False,
        },
        "blockers": [
            "source_registry_has_no_active_submission",
            "v1_graph_questions_unresolved_161",
            "structured_graph_v2_review_missing",
            "canonical_graph_v2_absent",
            "runtime_mapping_generation_blocked",
        ],
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    value["integrity"]["record_sha256"] = status_digest(value)
    validate_status(value, candidate_path, decision)
    return candidate_path, decision, value


def validate_status(
    value: dict[str, Any],
    candidate_path: Path | None = None,
    candidate: dict[str, Any] | None = None,
) -> None:
    schema_validate(value, load(STATUS_SCHEMA), "graph V2 status")
    require(
        value["integrity"]["record_sha256"] == status_digest(value),
        "graph V2 status digest mismatch",
    )
    registry = load(SOURCE_REGISTRY)
    _, _, v1_path, _ = current_inputs()
    require(
        value["source"]
        == {
            "source_registry_path": SOURCE_REGISTRY.relative_to(ROOT).as_posix(),
            "source_registry_sha256": sha_file(SOURCE_REGISTRY),
            "source_registry_generation_sha256": registry[
                "registry_generation_sha256"
            ],
            "v1_graph_path": v1_path.relative_to(ROOT).as_posix(),
            "v1_graph_sha256": sha_file(v1_path),
        },
        "graph V2 status source drift",
    )
    candidate_value = candidate
    if candidate_value is None:
        path = (
            candidate_path
            if candidate_path is not None
            else ROOT / value["candidate"]["path"]
        )
        candidate_value = load(path)
    validate_decision(candidate_value)
    require(
        value["candidate"]["decision_id"] == candidate_value["decision_id"]
        and value["candidate"]["sha256"]
        == sha_bytes(canonical_bytes(candidate_value))
        and value["candidate"]["source_registry_generation_sha256"]
        == candidate_value["subject"]["source_registry_generation_sha256"],
        "graph V2 status/candidate identity drift",
    )


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


def generate() -> dict[str, Any]:
    candidate_path, decision, value = build()
    atomic_write(candidate_path, decision)
    atomic_write(STATUS, value)
    return value


def check() -> dict[str, Any]:
    candidate_path, decision, value = build()
    require(
        candidate_path.is_file()
        and candidate_path.read_bytes() == canonical_bytes(decision)
        and STATUS.is_file()
        and STATUS.read_bytes() == canonical_bytes(value),
        "tracked graph V2 candidate/status drift",
    )
    validate_status(value, candidate_path, decision)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--validate-decision", type=Path)
    args = parser.parse_args()
    if args.validate_decision:
        validate_decision(load(args.validate_decision.resolve()))
        print("DROPBEAR_GRAPH_V2_DECISION_OK support=false motion=false")
        return 0
    value = generate() if args.generate else check()
    summary = value["summary"]
    print(
        "DROPBEAR_GRAPH_V2_OK "
        f"candidate={summary['candidate_count']} "
        f"source_active={summary['source_authority_active_count']} "
        f"unresolved={summary['v1_unresolved_question_count']} "
        f"canonical={summary['canonical_graph_count']} "
        "support=false motion=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, GraphV2Error, ValueError) as error:
        print(f"Dropbear graph V2 failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
