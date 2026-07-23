#!/usr/bin/env python3
"""Generate and validate reviewed Dropbear graph decisions and review cohorts."""

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
from collections import defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "generated/dropbear_description/inventory.json"
SOURCE_STATUS = ROOT / "generated/dropbear_source_authority/status.json"
RECONCILIATION = ROOT / "generated/dropbear_reconciliation/reconciliation.json"
DECISION_SCHEMA = ROOT / "schemas/dropbear-graph-decision.schema.json"
PACKET_SCHEMA = ROOT / "schemas/dropbear-graph-review-packet.schema.json"
STATUS_SCHEMA = ROOT / "schemas/dropbear-graph-review-status.schema.json"
OUTPUT_ROOT = ROOT / "generated/dropbear_graph_review"
TEMPLATES = OUTPUT_ROOT / "templates"
PACKET = OUTPUT_ROOT / "packet.json"
STATUS = OUTPUT_ROOT / "status.json"
WORKBENCH = OUTPUT_ROOT / "workbench/index.html"
SUBMISSIONS = ROOT / "assets/dropbear/graph_decisions"
VERSION = "dropbear-graph-decision/1"
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
QUESTION_KINDS = (
    "cardinality_and_coupling",
    "actuator_mapping",
    "mimic_or_coupling",
    "gazebo_loop_closure_candidate",
)


class GraphReviewError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GraphReviewError(message)


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
        raise GraphReviewError(f"cannot read {path}: {error}") from error
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def atomic_write_bytes(path: Path, content: bytes) -> None:
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


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    atomic_write_bytes(path, canonical_bytes(value))


def schema_validate(value: dict[str, Any], schema_path: Path, label: str) -> None:
    schema = load(schema_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise GraphReviewError(
            f"{label} schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def source_manager() -> Any:
    name = "manage_dropbear_source_authority_for_graph"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "tools/manage_dropbear_source_authority.py"
    )
    if spec is None or spec.loader is None:
        raise GraphReviewError("cannot load source-authority validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sources() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    inventory = load(INVENTORY)
    status = load(SOURCE_STATUS)
    reconciliation = load(RECONCILIATION)
    require(
        inventory["schema_version"] == "dropbear-description-inventory/1"
        and inventory["summary"]["review_question_count"] == 161,
        "description inventory question baseline drift",
    )
    require(
        status["summary"]["accepted_decision_count"] == 0
        and status["summary"]["source_authority_selected"] is False,
        "source-authority baseline unexpectedly promoted",
    )
    require(
        reconciliation["summary"]["canonical_actuator_count"] == 12
        and reconciliation["summary"][
            "evidence_backed_ros_actuator_mapping_count"
        ]
        == 0,
        "reconciliation baseline drift",
    )
    digest = inventory["reconciliation"]["canonical_configuration_digest"]
    require(
        status["source"]["canonical_configuration_digest"] == digest
        and reconciliation["generated_from"]["canonical_configuration_digest"]
        == digest,
        "graph input configuration digest disagreement",
    )
    return inventory, status, reconciliation


def subject(
    inventory: dict[str, Any],
    status: dict[str, Any],
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "repository_commit": inventory["repository"]["commit"],
        "repository_tree_id": inventory["repository"]["tree_id"],
        "inventory_path": INVENTORY.relative_to(ROOT).as_posix(),
        "inventory_sha256": sha_file(INVENTORY),
        "inventory_schema_version": inventory["schema_version"],
        "source_authority_status_path": SOURCE_STATUS.relative_to(ROOT).as_posix(),
        "source_authority_status_sha256": sha_file(SOURCE_STATUS),
        "canonical_configuration_digest": inventory["reconciliation"][
            "canonical_configuration_digest"
        ],
        "reconciliation_path": RECONCILIATION.relative_to(ROOT).as_posix(),
        "reconciliation_sha256": sha_file(RECONCILIATION),
    }


def identifier(prefix: str, value: dict[str, Any]) -> str:
    return prefix + sha_bytes(canonical_bytes(value))[:20]


def question_hash(question: dict[str, Any]) -> str:
    return sha_bytes(canonical_bytes(question))


def empty_graph(subject_value: dict[str, Any]) -> dict[str, Any]:
    return {
        "graph_id": identifier("dropbeargraph-", subject_value),
        "graph_revision": 1,
        "base_link_id": None,
        "links": [],
        "joints": [],
        "constraints": [],
        "ownership": [],
        "actuator_bindings": [],
        "observation_bindings": [],
        "ros_command_bindings": [],
        "dependencies": {
            "cad_binding_ids": [],
            "calibration_record_ids": [],
            "limit_snapshot_ids": [],
            "route_ids": [],
        },
    }


def digest_payload(decision: dict[str, Any]) -> bytes:
    value = copy.deepcopy(decision)
    value["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(value)


def set_digest(decision: dict[str, Any]) -> None:
    decision["integrity"]["record_sha256"] = sha_bytes(digest_payload(decision))


def template() -> dict[str, Any]:
    inventory, status, reconciliation = sources()
    subject_value = subject(inventory, status, reconciliation)
    decision = {
        "schema_version": VERSION,
        "record_state": "draft",
        "record_revision": 1,
        "decision_id": identifier("graphdecision-", subject_value),
        "supersedes_decision_id": None,
        "subject": subject_value,
        "source_authority": {
            "decision_id": None,
            "decision_sha256": None,
            "admitted": False,
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
        "question_responses": [
            {
                "question_id": question["question_id"],
                "question_sha256": question_hash(question),
                "kind": question["kind"],
                "question": question["question"],
                "resolution": "unanswered",
                "answer": None,
                "evidence_refs": [],
                "graph_fact_ids": [],
            }
            for question in inventory["review_questions"]
        ],
        "decision_complete": False,
        "canonical_graph_admissible": False,
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(decision)
    validate_decision(
        decision,
        inventory_value=inventory,
        status_value=status,
        reconciliation_value=reconciliation,
    )
    return decision


def finite(values: list[float], label: str) -> None:
    require(all(math.isfinite(value) for value in values), f"non-finite {label}")


def unique_ids(records: list[dict[str, Any]], key: str, label: str) -> set[str]:
    values = [record[key] for record in records]
    require(len(values) == len(set(values)), f"duplicate {label} ID")
    return set(values)


def validate_graph(
    graph: dict[str, Any],
    reconciliation: dict[str, Any],
) -> set[str]:
    links = graph["links"]
    joints = graph["joints"]
    constraints = graph["constraints"]
    ownership = graph["ownership"]
    require(graph["base_link_id"] is not None, "graph base link is missing")
    require(links and joints, "graph links/joints are empty")
    link_ids = unique_ids(links, "link_id", "link")
    joint_ids = unique_ids(joints, "joint_id", "joint")
    constraint_ids = unique_ids(constraints, "constraint_id", "constraint")
    ownership_ids = unique_ids(ownership, "ownership_id", "ownership")
    global_ids = link_ids | joint_ids | constraint_ids | ownership_ids
    require(
        len(global_ids)
        == len(link_ids) + len(joint_ids) + len(constraint_ids) + len(ownership_ids),
        "graph ID domains collide",
    )
    require(graph["base_link_id"] in link_ids, "base link ID is unknown")
    require(
        len({link["canonical_name"] for link in links}) == len(links),
        "duplicate canonical link name",
    )
    require(
        len({joint["canonical_name"] for joint in joints}) == len(joints),
        "duplicate canonical joint name",
    )

    joint_by_id = {joint["joint_id"]: joint for joint in joints}
    incoming: dict[str, str] = {}
    children: dict[str, list[str]] = defaultdict(list)
    for joint in joints:
        require(
            joint["parent_link_id"] in link_ids
            and joint["child_link_id"] in link_ids,
            f"joint endpoint is unknown: {joint['joint_id']}",
        )
        require(
            joint["parent_link_id"] != joint["child_link_id"],
            f"joint self-edge: {joint['joint_id']}",
        )
        finite(joint["origin_xyz_m"], f"joint origin {joint['joint_id']}")
        finite(joint["origin_rpy_rad"], f"joint rotation {joint['joint_id']}")
        if joint["joint_type"] == "fixed":
            require(
                joint["activity"] == "fixed"
                and joint["axis_unit"] is None
                and joint["positive_direction"] is None
                and joint["zero_definition"] is None
                and joint["mimic"] is None,
                f"fixed joint semantics invalid: {joint['joint_id']}",
            )
        else:
            axis = joint["axis_unit"]
            require(axis is not None, f"moving joint lacks axis: {joint['joint_id']}")
            finite(axis, f"joint axis {joint['joint_id']}")
            require(
                math.isclose(
                    math.sqrt(sum(value * value for value in axis)),
                    1.0,
                    abs_tol=1e-9,
                ),
                f"joint axis is not unit: {joint['joint_id']}",
            )
            require(
                joint["positive_direction"] and joint["zero_definition"],
                f"moving joint lacks direction/zero: {joint['joint_id']}",
            )
        if joint["activity"] == "mimic":
            mimic = joint["mimic"]
            require(mimic is not None, f"mimic joint lacks equation: {joint['joint_id']}")
            require(
                mimic["driver_joint_id"] in joint_ids
                and mimic["driver_joint_id"] != joint["joint_id"],
                f"mimic driver invalid: {joint['joint_id']}",
            )
            require(
                math.isfinite(mimic["multiplier"])
                and not math.isclose(mimic["multiplier"], 0.0)
                and math.isfinite(mimic["offset_rad"]),
                f"mimic numeric semantics invalid: {joint['joint_id']}",
            )
        else:
            require(joint["mimic"] is None, "non-mimic joint carries mimic equation")
        if joint["activity"] != "simulator_only":
            child = joint["child_link_id"]
            require(child not in incoming, f"tree child has multiple parents: {child}")
            incoming[child] = joint["joint_id"]
            children[joint["parent_link_id"]].append(child)

    base = graph["base_link_id"]
    require(base not in incoming, "base link has incoming tree joint")
    require(
        link_ids - {base} == set(incoming),
        "tree links are disconnected or have no declared parent",
    )
    visited: set[str] = set()
    active_stack: set[str] = set()

    def visit(link_id: str) -> None:
        require(link_id not in active_stack, "tree contains a cycle")
        if link_id in visited:
            return
        active_stack.add(link_id)
        for child in children.get(link_id, []):
            visit(child)
        active_stack.remove(link_id)
        visited.add(link_id)

    visit(base)
    require(visited == link_ids, "tree traversal does not cover all links")

    for constraint in constraints:
        require(
            set(constraint["joint_ids"]) <= joint_ids,
            f"constraint references unknown joint: {constraint['constraint_id']}",
        )
        require(
            set(constraint["independent_joint_ids"])
            <= set(constraint["joint_ids"]),
            f"constraint independent set escapes joint set: {constraint['constraint_id']}",
        )
        if constraint["kind"] == "simulator_only_closure":
            require(
                constraint["solver_owner"] == "rigid_body_simulator"
                and constraint["physical_counterpart_status"] == "not_applicable",
                "simulator-only closure has physical/controller authority",
            )
        if constraint["kind"] == "closed_chain":
            require(
                constraint["physical_counterpart_status"] in {"reviewed", "missing"},
                "closed-chain physical counterpart invalid",
            )

    mimic_joints = {
        joint["joint_id"]: joint
        for joint in joints
        if joint["activity"] == "mimic"
    }
    for joint_id, joint in mimic_joints.items():
        matching = [
            constraint
            for constraint in constraints
            if constraint["kind"] == "mimic"
            and joint_id in constraint["joint_ids"]
            and joint["mimic"]["driver_joint_id"] in constraint["joint_ids"]
            and joint["mimic"]["driver_joint_id"]
            in constraint["independent_joint_ids"]
        ]
        require(
            len(matching) == 1,
            f"mimic joint lacks one exact declared constraint: {joint_id}",
        )

    mimic_visiting: set[str] = set()
    mimic_visited: set[str] = set()

    def visit_mimic(joint_id: str) -> None:
        require(joint_id not in mimic_visiting, "mimic dependency contains a cycle")
        if joint_id in mimic_visited:
            return
        mimic_visiting.add(joint_id)
        driver = mimic_joints[joint_id]["mimic"]["driver_joint_id"]
        if driver in mimic_joints:
            visit_mimic(driver)
        mimic_visiting.remove(joint_id)
        mimic_visited.add(joint_id)

    for joint_id in mimic_joints:
        visit_mimic(joint_id)

    simulator_joints = {
        joint["joint_id"]
        for joint in joints
        if joint["activity"] == "simulator_only"
    }
    simulator_constraints = [
        constraint
        for constraint in constraints
        if constraint["kind"] == "simulator_only_closure"
    ]
    require(
        all(
            bool(set(constraint["joint_ids"]) & simulator_joints)
            for constraint in simulator_constraints
        ),
        "simulator-only constraint lacks a simulator-only edge",
    )
    for joint_id in simulator_joints:
        require(
            sum(
                joint_id in constraint["joint_ids"]
                for constraint in simulator_constraints
            )
            == 1,
            f"simulator-only edge lacks one exact closure constraint: {joint_id}",
        )

    expected_actuators = {
        row["actuator_id"]: row["canonical_joint_name"]
        for row in reconciliation["actuators"]
    }
    bindings = graph["actuator_bindings"]
    require(len(bindings) == 12, "graph must contain exactly 12 actuator bindings")
    require(
        {row["actuator_id"]: row["canonical_joint_name"] for row in bindings}
        == expected_actuators,
        "actuator binding identity/coverage drift",
    )
    command_to_bindings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for binding in bindings:
        require(
            set(binding["joint_ids"]) <= joint_ids
            and binding["command_coordinate_joint_id"] in binding["joint_ids"],
            f"actuator binding references unknown command/joint: {binding['actuator_id']}",
        )
        command_joint = joint_by_id[binding["command_coordinate_joint_id"]]
        require(
            command_joint["activity"] in {"active", "coupled"},
            f"actuator command coordinate is not active/coupled: {binding['actuator_id']}",
        )
        require(
            binding["ownership_id"] in ownership_ids,
            f"actuator ownership is unknown: {binding['actuator_id']}",
        )
        if binding["coupling_constraint_id"] is not None:
            require(
                binding["coupling_constraint_id"] in constraint_ids,
                f"actuator coupling constraint is unknown: {binding['actuator_id']}",
            )
        command_to_bindings[binding["command_coordinate_joint_id"]].append(binding)
    for command_id, command_bindings in command_to_bindings.items():
        if len(command_bindings) > 1:
            coupling_ids = {
                row["coupling_constraint_id"] for row in command_bindings
            }
            require(
                len(coupling_ids) == 1 and None not in coupling_ids,
                f"shared command coordinate lacks one coupling: {command_id}",
            )
    active_coordinates = {
        joint["joint_id"]
        for joint in joints
        if joint["activity"] in {"active", "coupled"}
    }
    require(
        active_coordinates == set(command_to_bindings),
        "active command coordinates and actuator bindings disagree",
    )

    expected_names = set(expected_actuators.values())
    observations = graph["observation_bindings"]
    require(
        len(observations) == 12
        and {row["canonical_joint_name"] for row in observations} == expected_names,
        "observation binding coverage drift",
    )
    actuator_by_name = {
        row["canonical_joint_name"]: row for row in reconciliation["actuators"]
    }
    for observation in observations:
        expected_sensor = actuator_by_name[observation["canonical_joint_name"]][
            "feedback"
        ]["external_sensor_id"]
        if expected_sensor is None:
            require(
                observation["external_sensor_status"] == "missing"
                and observation["external_sensor_id"] is None,
                "missing external sensor was mapped/aliased",
            )
        else:
            require(
                observation["external_sensor_status"]
                == actuator_by_name[observation["canonical_joint_name"]][
                    "feedback"
                ]["external_sensor_status"]
                and observation["external_sensor_id"] == expected_sensor,
                "external sensor binding differs from exact observation",
            )

    ros = graph["ros_command_bindings"]
    require(
        len(ros) == 12
        and {row["canonical_joint_name"] for row in ros} == expected_names,
        "ROS command binding coverage drift",
    )
    expected_ros = {
        joint_id
        for group in reconciliation["ros_leg_groups"]
        for joint_id in group["joint_ids"]
    }
    mapped = [row for row in ros if row["status"] == "mapped"]
    require(
        {row["ros_joint_id"] for row in mapped} == expected_ros
        and len(mapped) == len(expected_ros),
        "ROS joint mapping does not cover exact ten observations once",
    )
    for row in ros:
        require(
            (row["status"] == "mapped") == (row["ros_joint_id"] is not None),
            f"ROS mapping presence/status disagree: {row['canonical_joint_name']}",
        )

    referenced_ownership = {row["ownership_id"] for row in bindings}
    require(
        referenced_ownership == ownership_ids,
        "ownership rows are missing or unreferenced",
    )
    require(
        all(not row["diagnostic_bypass_allowed"] for row in ownership),
        "diagnostic bypass is enabled",
    )
    return global_ids


def validate_source_authority(
    reference: dict[str, Any],
    accepted_source_decision: dict[str, Any] | None,
) -> None:
    require(reference["admitted"] is True, "source authority is not admitted")
    require(
        accepted_source_decision is not None,
        "accepted graph lacks source-authority decision",
    )
    module = source_manager()
    try:
        module.validate_decision(accepted_source_decision)
    except ValueError as error:
        raise GraphReviewError(
            f"source-authority decision failed validation: {error}"
        ) from error
    require(
        accepted_source_decision["record_state"] == "submitted"
        and accepted_source_decision["disposition"] == "accept_selection"
        and accepted_source_decision["runtime_description_complete"],
        "source-authority decision is not accepted/runtime-complete",
    )
    require(
        reference["decision_id"] == accepted_source_decision["decision_id"]
        and reference["decision_sha256"]
        == sha_bytes(canonical_bytes(accepted_source_decision)),
        "source-authority reference/hash drift",
    )


def validate_decision(
    decision: dict[str, Any],
    *,
    inventory_value: dict[str, Any] | None = None,
    status_value: dict[str, Any] | None = None,
    reconciliation_value: dict[str, Any] | None = None,
    accepted_source_decision: dict[str, Any] | None = None,
) -> None:
    if inventory_value is None or status_value is None or reconciliation_value is None:
        loaded_inventory, loaded_status, loaded_reconciliation = sources()
        inventory_value = inventory_value or loaded_inventory
        status_value = status_value or loaded_status
        reconciliation_value = reconciliation_value or loaded_reconciliation
    schema_validate(decision, DECISION_SCHEMA, "graph decision")
    expected_subject = subject(
        inventory_value, status_value, reconciliation_value
    )
    require(decision["subject"] == expected_subject, "graph decision subject drift")
    require(
        decision["decision_id"] == identifier("graphdecision-", expected_subject),
        "graph decision ID drift",
    )
    require(
        decision["graph"]["graph_id"]
        == identifier("dropbeargraph-", expected_subject),
        "graph ID drift",
    )
    require(
        decision["integrity"]["record_sha256"] == sha_bytes(digest_payload(decision)),
        "graph decision digest mismatch",
    )
    require(
        decision["support_granted"] is False
        and decision["physical_motion_authority"] is False,
        "graph decision grants support/motion",
    )

    expected_questions = inventory_value["review_questions"]
    responses = decision["question_responses"]
    require(
        [row["question_id"] for row in responses]
        == [row["question_id"] for row in expected_questions],
        "graph question coverage/order drift",
    )
    for response, question in zip(responses, expected_questions):
        require(
            response["question_sha256"] == question_hash(question)
            and response["kind"] == question["kind"]
            and response["question"] == question["question"],
            f"graph question identity/hash drift: {response['question_id']}",
        )

    if decision["record_state"] == "draft":
        require(
            decision["source_authority"] == {
                "decision_id": None,
                "decision_sha256": None,
                "admitted": False,
            },
            "draft admits source authority",
        )
        require(
            all(
                value is None
                for key, value in decision["reviewer"].items()
                if key != "signature_evidence_refs"
            )
            and decision["reviewer"]["signature_evidence_refs"] == [],
            "draft identifies graph reviewer",
        )
        require(decision["disposition"] is None, "draft has graph disposition")
        require(
            decision["graph"] == empty_graph(expected_subject),
            "draft contains graph facts",
        )
        require(
            all(
                row["resolution"] == "unanswered"
                and row["answer"] is None
                and not row["evidence_refs"]
                and not row["graph_fact_ids"]
                for row in responses
            ),
            "draft answers graph questions",
        )
        require(
            not decision["decision_complete"]
            and not decision["canonical_graph_admissible"],
            "draft claims graph completeness/admission",
        )
        return

    reviewer = decision["reviewer"]
    require(
        reviewer["reviewer_id"]
        and reviewer["organization_or_team"]
        and reviewer["mechanical_graph_competence_attested"] is True
        and reviewer["independence_attested"] is True
        and reviewer["reviewed_at"]
        and reviewer["review_assertion"]
        and reviewer["signature_evidence_refs"],
        "submitted graph decision lacks competent independent reviewer",
    )
    identity = (
        reviewer["reviewer_id"] + " " + reviewer["organization_or_team"]
    ).casefold()
    require(
        not any(token in identity for token in AUTOMATION_IDENTIFIERS),
        "automation/self-review cannot approve graph",
    )
    reviewed_at = dt.datetime.fromisoformat(
        reviewer["reviewed_at"].replace("Z", "+00:00")
    )
    require(
        reviewed_at.tzinfo is not None
        and reviewed_at.utcoffset() == dt.timedelta(0),
        "graph review timestamp must be UTC",
    )
    require(decision["disposition"] is not None, "submitted graph lacks disposition")

    resolved = True
    for response in responses:
        if response["resolution"] == "resolved_as_graph_fact":
            require(
                response["answer"]
                and response["evidence_refs"]
                and response["graph_fact_ids"],
                f"graph-fact response incomplete: {response['question_id']}",
            )
        elif response["resolution"] == "resolved_not_in_graph":
            require(
                response["answer"]
                and response["evidence_refs"]
                and not response["graph_fact_ids"],
                f"not-in-graph response incomplete: {response['question_id']}",
            )
        elif response["resolution"] == "unresolved_needs_evidence":
            resolved = False
            require(
                response["answer"] and response["evidence_refs"],
                f"unresolved response lacks rationale/evidence: {response['question_id']}",
            )
            require(
                not response["graph_fact_ids"],
                "unresolved response references graph fact",
            )
        else:
            resolved = False
            require(
                response["answer"] is None
                and not response["evidence_refs"]
                and not response["graph_fact_ids"],
                "unanswered response contains answer/evidence",
            )
    require(
        decision["decision_complete"] is resolved,
        "graph decision completeness claim disagrees",
    )

    if decision["disposition"] == "accept_graph":
        require(resolved, "accepted graph has unresolved questions")
        validate_source_authority(
            decision["source_authority"], accepted_source_decision
        )
        graph_fact_ids = validate_graph(decision["graph"], reconciliation_value)
        for response in responses:
            require(
                set(response["graph_fact_ids"]) <= graph_fact_ids,
                f"question references unknown graph fact: {response['question_id']}",
            )
        require(
            decision["canonical_graph_admissible"] is True,
            "accepted complete graph does not claim canonical admission",
        )
    else:
        require(
            decision["canonical_graph_admissible"] is False,
            "non-accept graph claims canonical admission",
        )


def build_packet(template_value: dict[str, Any]) -> dict[str, Any]:
    inventory, _, _ = sources()
    questions_by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for question in inventory["review_questions"]:
        questions_by_kind[question["kind"]].append(question)
    cohorts = []
    order = 0
    for kind in QUESTION_KINDS:
        questions = questions_by_kind[kind]
        for start in range(0, len(questions), 20):
            order += 1
            batch = questions[start : start + 20]
            cohorts.append(
                {
                    "cohort_id": f"graph-cohort-{order:03d}",
                    "review_order": order,
                    "kind": kind,
                    "question_ids": [row["question_id"] for row in batch],
                    "evidence_paths": sorted(
                        {
                            path
                            for row in batch
                            for path in row["evidence_paths"]
                        }
                    ),
                    "review_status": "unanswered",
                }
            )
    template_path = TEMPLATES / f"{template_value['decision_id']}.json"
    packet = {
        "schema_version": "dropbear-graph-review-packet/1",
        "artifact_id": "dropbear-graph-review-packet",
        "authority": "review_input_only",
        "sources": {
            "inventory_path": INVENTORY.relative_to(ROOT).as_posix(),
            "inventory_sha256": sha_file(INVENTORY),
            "source_authority_status_path": SOURCE_STATUS.relative_to(ROOT).as_posix(),
            "source_authority_status_sha256": sha_file(SOURCE_STATUS),
            "graph_template_path": template_path.relative_to(ROOT).as_posix(),
            "graph_template_sha256": sha_file(template_path),
        },
        "summary": {
            "question_count": len(inventory["review_questions"]),
            "cohort_count": len(cohorts),
            "answered_question_count": 0,
            "submitted_decision_count": 0,
            "accepted_graph_count": 0,
            "canonical_graph_count": 0,
            "runtime_ros_actuator_mapping_count": 0,
        },
        "cohorts": cohorts,
        "support_granted": False,
        "physical_motion_authority": False,
    }
    schema_validate(packet, PACKET_SCHEMA, "graph review packet")
    require(
        [question_id for cohort in cohorts for question_id in cohort["question_ids"]]
        == [
            question["question_id"]
            for kind in QUESTION_KINDS
            for question in questions_by_kind[kind]
        ],
        "review cohorts do not partition questions in kind order",
    )
    require(
        len(
            {
                question_id
                for cohort in cohorts
                for question_id in cohort["question_ids"]
            }
        )
        == 161,
        "review cohorts duplicate/drop question IDs",
    )
    return packet


def render_workbench(
    template_value: dict[str, Any], packet_value: dict[str, Any]
) -> bytes:
    # JSON is escaped for an HTML script element; no network resource or source
    # path is executed. Export remains a draft until a reviewer also supplies a
    # complete graph and source-authority decision.
    embedded_template = json.dumps(
        template_value, ensure_ascii=False, sort_keys=True
    ).replace("<", "\\u003c")
    embedded_packet = json.dumps(
        packet_value, ensure_ascii=False, sort_keys=True
    ).replace("<", "\\u003c")
    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dropbear graph review workbench</title>
<style>
body{font-family:system-ui,sans-serif;margin:2rem;max-width:1100px}
.warning{border:2px solid #9b2c2c;padding:1rem;background:#fff5f5}
.cohort{border:1px solid #bbb;padding:1rem;margin:1rem 0}
.question{padding:.7rem 0;border-top:1px solid #ddd}
label{display:block;font-weight:600;margin-top:.4rem}
textarea,input,select{width:100%;box-sizing:border-box}
textarea{min-height:5rem} code{overflow-wrap:anywhere}
</style></head><body>
<h1>Dropbear graph review workbench</h1>
<div class="warning"><strong>Review input only.</strong> This page cannot select source
authority, construct a canonical graph, grant support, or enable motion. Exported
answers remain a draft until the independent decision validator accepts all source,
graph, reviewer, integrity, and question requirements.</div>
<p id="summary"></p><div id="cohorts"></div>
<button id="export" type="button">Export answered draft JSON</button>
<script id="template" type="application/json">""" + embedded_template + """</script>
<script id="packet" type="application/json">""" + embedded_packet + """</script>
<script>
const template=JSON.parse(document.getElementById("template").textContent);
const packet=JSON.parse(document.getElementById("packet").textContent);
const byId=new Map(template.question_responses.map(q=>[q.question_id,q]));
document.getElementById("summary").textContent=
  `${packet.summary.question_count} questions in ${packet.summary.cohort_count} cohorts; `+
  "source authority and canonical graph remain absent.";
const root=document.getElementById("cohorts");
for(const cohort of packet.cohorts){
  const section=document.createElement("section");section.className="cohort";
  const h=document.createElement("h2");h.textContent=
    `${cohort.cohort_id}: ${cohort.kind} (${cohort.question_ids.length})`;
  section.appendChild(h);
  for(const id of cohort.question_ids){
    const q=byId.get(id),box=document.createElement("div");box.className="question";
    const title=document.createElement("strong");title.textContent=`${id}: ${q.question}`;
    box.appendChild(title);
    const resolution=document.createElement("select");resolution.dataset.id=id;
    resolution.dataset.field="resolution";
    for(const value of ["unanswered","resolved_as_graph_fact","resolved_not_in_graph","unresolved_needs_evidence"]){
      const option=document.createElement("option");option.value=value;option.textContent=value;
      resolution.appendChild(option);
    }
    const rl=document.createElement("label");rl.textContent="Resolution";rl.appendChild(resolution);
    box.appendChild(rl);
    for(const field of ["answer","evidence refs (one per line)","graph fact IDs (one per line)"]){
      const label=document.createElement("label");label.textContent=field;
      const area=document.createElement("textarea");area.dataset.id=id;
      area.dataset.field=field.split(" ")[0].replace("refs","evidence_refs");
      if(field.startsWith("graph"))area.dataset.field="graph_fact_ids";
      label.appendChild(area);box.appendChild(label);
    }
    section.appendChild(box);
  }
  root.appendChild(section);
}
function sorted(value){
  if(Array.isArray(value))return value.map(sorted);
  if(value&&typeof value==="object")return Object.fromEntries(
    Object.keys(value).sort().map(key=>[key,sorted(value[key])]));
  return value;
}
document.getElementById("export").onclick=async()=>{
  const value=structuredClone(template);
  const rows=new Map(value.question_responses.map(q=>[q.question_id,q]));
  for(const element of document.querySelectorAll("[data-id]")){
    const row=rows.get(element.dataset.id),field=element.dataset.field;
    if(field==="resolution")row.resolution=element.value;
    else if(field==="answer")row.answer=element.value.trim()||null;
    else row[field]=element.value.split("\\n").map(x=>x.trim()).filter(Boolean);
  }
  const prior=value.integrity.record_sha256;value.integrity.record_sha256="0".repeat(64);
  const canonical=JSON.stringify(sorted(value))+"\\n";
  const digest=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(canonical));
  value.integrity.record_sha256=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("");
  const blob=new Blob([JSON.stringify(sorted(value))+"\\n"],{type:"application/json"});
  const link=document.createElement("a");link.href=URL.createObjectURL(blob);
  link.download=`${value.decision_id}.answered-draft.json`;link.click();
  URL.revokeObjectURL(link.href);void prior;
};
</script></body></html>
"""
    return html.encode("utf-8")


def build_status(
    template_value: dict[str, Any], packet_value: dict[str, Any]
) -> dict[str, Any]:
    submissions = sorted(SUBMISSIONS.glob("*.json")) if SUBMISSIONS.is_dir() else []
    require(
        not submissions,
        "graph decision submission requires reviewed positive status V2",
    )
    template_path = TEMPLATES / f"{template_value['decision_id']}.json"
    status = {
        "schema_version": "dropbear-graph-review-status/1",
        "artifact_id": "dropbear-graph-review-status",
        "authority": "derived_denial_only",
        "sources": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha_file(path),
            }
            for path in (INVENTORY, SOURCE_STATUS, template_path, PACKET)
        ],
        "summary": {
            "question_count": len(template_value["question_responses"]),
            "unanswered_question_count": len(template_value["question_responses"]),
            "submitted_decision_count": 0,
            "accepted_graph_count": 0,
            "canonical_graph_count": 0,
            "runtime_ros_actuator_mapping_count": 0,
            "canonical_graph_admissible": False,
        },
        "accepted_graph_decision_ids": [],
        "blockers": [
            "accepted_source_authority_decision_missing",
            "independent_mechanical_graph_reviewer_missing",
            "all_161_graph_questions_unanswered",
            "six_actuator_five_ros_joint_cardinality_unresolved",
            "canonical_graph_and_runtime_mappings_absent",
        ],
        "support_granted": False,
        "physical_motion_authority": False,
    }
    schema_validate(status, STATUS_SCHEMA, "graph review status")
    return status


def generate() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    template_value = template()
    template_path = TEMPLATES / f"{template_value['decision_id']}.json"
    atomic_write(template_path, template_value)
    packet_value = build_packet(template_value)
    atomic_write(PACKET, packet_value)
    atomic_write_bytes(WORKBENCH, render_workbench(template_value, packet_value))
    status_value = build_status(template_value, packet_value)
    atomic_write(STATUS, status_value)
    return template_value, packet_value, status_value


def check() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    template_value = template()
    template_path = TEMPLATES / f"{template_value['decision_id']}.json"
    require(
        template_path.is_file()
        and template_path.read_bytes() == canonical_bytes(template_value),
        "graph decision template drift",
    )
    packet_value = build_packet(template_value)
    require(
        PACKET.is_file() and PACKET.read_bytes() == canonical_bytes(packet_value),
        "graph review packet drift",
    )
    require(
        WORKBENCH.is_file()
        and WORKBENCH.read_bytes()
        == render_workbench(template_value, packet_value),
        "graph review workbench drift",
    )
    status_value = build_status(template_value, packet_value)
    require(
        STATUS.is_file() and STATUS.read_bytes() == canonical_bytes(status_value),
        "graph review status drift",
    )
    return template_value, packet_value, status_value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--validate", type=Path)
    args = parser.parse_args()
    if args.validate:
        value = load(args.validate.resolve())
        validate_decision(value)
        print(
            "DROPBEAR_GRAPH_DECISION_OK "
            f"state={value['record_state']} disposition={value['disposition']} "
            f"complete={str(value['decision_complete']).lower()} "
            f"admissible={str(value['canonical_graph_admissible']).lower()} "
            "support=false motion=false"
        )
        return 0
    template_value, packet_value, status_value = (
        generate() if args.generate else check()
    )
    print(
        "DROPBEAR_GRAPH_REVIEW_OK "
        f"questions={len(template_value['question_responses'])} "
        f"cohorts={len(packet_value['cohorts'])} "
        f"submitted={status_value['summary']['submitted_decision_count']} "
        "accepted=0 canonical=0 mappings=0 support=false motion=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, GraphReviewError, ValueError) as error:
        print(f"Dropbear graph review failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
