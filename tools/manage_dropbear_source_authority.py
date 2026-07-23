#!/usr/bin/env python3
"""Generate and validate independent Dropbear source-authority decisions."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "generated/dropbear_description/inventory.json"
DECISION_SCHEMA = ROOT / "schemas/dropbear-source-authority-decision.schema.json"
STATUS_SCHEMA = ROOT / "schemas/dropbear-source-authority-status.schema.json"
OUTPUT_ROOT = ROOT / "generated/dropbear_source_authority"
TEMPLATES = OUTPUT_ROOT / "templates"
STATUS = OUTPUT_ROOT / "status.json"
SUBMISSIONS = ROOT / "assets/dropbear/source_authority_decisions"
VERSION = "dropbear-source-authority-decision/1"
ROLES = (
    "kinematic_tree",
    "visual_geometry",
    "collision_geometry",
    "inertial_properties",
    "ros2_control",
    "gazebo_constraints",
    "controller_configuration",
)
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


class SourceAuthorityError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceAuthorityError(message)


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
        raise SourceAuthorityError(f"cannot read {path}: {error}") from error
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


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


def digest_payload(decision: dict[str, Any]) -> bytes:
    value = copy.deepcopy(decision)
    value["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(value)


def set_digest(decision: dict[str, Any]) -> None:
    decision["integrity"]["record_sha256"] = sha_bytes(digest_payload(decision))


def inventory() -> dict[str, Any]:
    value = load(INVENTORY)
    require(
        value["schema_version"] == "dropbear-description-inventory/1",
        "inventory schema version drift",
    )
    require(
        value["summary"]["authoritative_description_selected"] is False
        and value["summary"]["runtime_ros_actuator_mapping_count"] == 0,
        "inventory has unexpected authority",
    )
    return value


def subject(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "repository_path": value["repository"]["path"],
        "repository_commit": value["repository"]["commit"],
        "repository_tree_id": value["repository"]["tree_id"],
        "inventory_path": INVENTORY.relative_to(ROOT).as_posix(),
        "inventory_schema_version": value["schema_version"],
        "inventory_sha256": sha_file(INVENTORY),
        "canonical_configuration_digest": value["reconciliation"][
            "canonical_configuration_digest"
        ],
    }


def decision_id_for(subject_value: dict[str, Any]) -> str:
    return "sourceauthority-" + sha_bytes(canonical_bytes(subject_value))[:20]


def template() -> dict[str, Any]:
    value = inventory()
    subject_value = subject(value)
    decision = {
        "schema_version": VERSION,
        "record_state": "draft",
        "record_revision": 1,
        "decision_id": decision_id_for(subject_value),
        "supersedes_decision_id": None,
        "subject": subject_value,
        "reviewer": {
            "reviewer_id": None,
            "organization_or_team": None,
            "independence_attested": None,
            "reviewed_at": None,
            "review_assertion": None,
            "signature_evidence_refs": [],
        },
        "disposition": None,
        "family_policy": {
            "mode": None,
            "primary_family": None,
            "rationale": None,
            "evidence_refs": [],
        },
        "role_decisions": [
            {
                "role": role,
                "status": "unanswered",
                "selected_files": [],
                "unavailability_reason": None,
                "rationale": None,
                "evidence_refs": [],
            }
            for role in ROLES
        ],
        "divergence_decisions": [
            {
                "logical_key": group["logical_key"],
                "candidate_git_object_ids": group["git_object_ids"],
                "disposition": "unanswered",
                "selected_git_object_ids": [],
                "rationale": None,
                "evidence_refs": [],
            }
            for group in value["logical_groups"]
            if group["status"] == "divergent"
        ],
        "decision_complete": False,
        "runtime_description_complete": False,
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(decision)
    validate_decision(decision, value)
    return decision


def schema_validate(value: dict[str, Any], path: Path, label: str) -> None:
    schema = load(path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    require(
        not errors,
        f"{label} schema failure at "
        f"/{'/'.join(map(str, errors[0].absolute_path))}: "
        f"{errors[0].message}" if errors else "",
    )


def selection_from_file(file_record: dict[str, Any]) -> dict[str, Any]:
    classification = file_record["classification"]
    require(
        classification in {"source_candidate", "expanded_generated_candidate"},
        "derivative file cannot be selected",
    )
    return {
        "path": file_record["path"],
        "git_object_id": file_record["git_object_id"],
        "sha256": file_record["sha256"],
        "size_bytes": file_record["size_bytes"],
        "logical_key": file_record["logical_key"],
        "package_family": file_record["package_family"],
        "classification": classification,
        "selection_kind": (
            "primary_source"
            if classification == "source_candidate"
            else "expanded_with_lineage"
        ),
        "generated_lineage": None,
    }


def validate_decision(
    decision: dict[str, Any], inventory_value: dict[str, Any] | None = None
) -> None:
    inventory_value = inventory_value or inventory()
    schema_validate(decision, DECISION_SCHEMA, "source-authority decision")
    expected_subject = subject(inventory_value)
    require(decision["subject"] == expected_subject, "decision subject/hash drift")
    require(
        decision["decision_id"] == decision_id_for(expected_subject),
        "decision ID drift",
    )
    require(
        decision["integrity"]["record_sha256"] == sha_bytes(digest_payload(decision)),
        "decision record digest mismatch",
    )
    require(decision["support_granted"] is False, "source decision grants support")
    require(
        decision["physical_motion_authority"] is False,
        "source decision grants motion authority",
    )
    require(
        [row["role"] for row in decision["role_decisions"]] == list(ROLES),
        "source role coverage/order drift",
    )
    expected_groups = [
        group for group in inventory_value["logical_groups"]
        if group["status"] == "divergent"
    ]
    require(
        [row["logical_key"] for row in decision["divergence_decisions"]]
        == [group["logical_key"] for group in expected_groups],
        "divergence coverage/order drift",
    )
    for row, group in zip(decision["divergence_decisions"], expected_groups):
        require(
            row["candidate_git_object_ids"] == group["git_object_ids"],
            f"divergence object set drift: {row['logical_key']}",
        )

    files_by_path = {row["path"]: row for row in inventory_value["files"]}
    selected: list[dict[str, Any]] = []
    for role in decision["role_decisions"]:
        require(
            len({row["path"] for row in role["selected_files"]})
            == len(role["selected_files"]),
            f"duplicate selected path: {role['role']}",
        )
        for selection in role["selected_files"]:
            source = files_by_path.get(selection["path"])
            require(source is not None, f"unknown selected path: {selection['path']}")
            expected = selection_from_file(source)
            if source["classification"] == "expanded_generated_candidate":
                expected["generated_lineage"] = selection["generated_lineage"]
            require(selection == expected, f"selected file identity drift: {selection['path']}")
            if source["classification"] == "source_candidate":
                require(
                    selection["selection_kind"] == "primary_source"
                    and selection["generated_lineage"] is None,
                    "primary source selection has generated lineage",
                )
            else:
                lineage = selection["generated_lineage"]
                require(
                    selection["selection_kind"] == "expanded_with_lineage"
                    and lineage is not None,
                    "expanded selection lacks generator lineage",
                )
                for source_path in lineage["source_paths"]:
                    lineage_source = files_by_path.get(source_path)
                    require(
                        lineage_source is not None
                        and lineage_source["classification"] == "source_candidate",
                        "expanded lineage source is not an exact source candidate",
                    )
                require(
                    bool(lineage["evidence_refs"]),
                    "expanded lineage lacks evidence",
                )
            selected.append(selection)
        if role["role"] == "controller_configuration" and role["selected_files"]:
            require(
                all(
                    files_by_path[item["path"]]["description_kind"]
                    == "controller_yaml"
                    for item in role["selected_files"]
                ),
                "controller role selects non-controller file",
            )
        if role["role"] == "ros2_control" and role["selected_files"]:
            require(
                all("/ros2_control/" in item["path"] for item in role["selected_files"]),
                "ros2_control role selects path outside ros2_control",
            )
        if role["role"] == "gazebo_constraints" and role["selected_files"]:
            require(
                all("/gazebo/" in item["path"] for item in role["selected_files"]),
                "Gazebo role selects path outside gazebo",
            )

    selected_oids_by_key: dict[str, set[str]] = {}
    for item in selected:
        selected_oids_by_key.setdefault(item["logical_key"], set()).add(
            item["git_object_id"]
        )
    for divergence in decision["divergence_decisions"]:
        selected_oids = selected_oids_by_key.get(divergence["logical_key"], set())
        require(
            set(divergence["selected_git_object_ids"]) == selected_oids,
            f"divergence selection disagreement: {divergence['logical_key']}",
        )

    if decision["record_state"] == "draft":
        require(decision["disposition"] is None, "draft has disposition")
        require(
            all(value is None for key, value in decision["reviewer"].items()
                if key != "signature_evidence_refs")
            and decision["reviewer"]["signature_evidence_refs"] == [],
            "draft identifies reviewer",
        )
        require(
            decision["family_policy"] == {
                "mode": None,
                "primary_family": None,
                "rationale": None,
                "evidence_refs": [],
            },
            "draft selects family policy",
        )
        require(
            all(
                role["status"] == "unanswered"
                and not role["selected_files"]
                and role["unavailability_reason"] is None
                and role["rationale"] is None
                and not role["evidence_refs"]
                for role in decision["role_decisions"]
            ),
            "draft answers a source role",
        )
        require(
            all(
                row["disposition"] == "unanswered"
                and not row["selected_git_object_ids"]
                and row["rationale"] is None
                and not row["evidence_refs"]
                for row in decision["divergence_decisions"]
            ),
            "draft answers divergence",
        )
        require(
            not decision["decision_complete"]
            and not decision["runtime_description_complete"],
            "draft claims completeness",
        )
        return

    reviewer = decision["reviewer"]
    require(
        reviewer["reviewer_id"]
        and reviewer["organization_or_team"]
        and reviewer["independence_attested"] is True
        and reviewer["reviewed_at"]
        and reviewer["review_assertion"]
        and reviewer["signature_evidence_refs"],
        "submitted decision lacks independent reviewer evidence",
    )
    identity = (
        reviewer["reviewer_id"] + " " + reviewer["organization_or_team"]
    ).casefold()
    require(
        not any(token in identity for token in AUTOMATION_IDENTIFIERS),
        "automation/self-review cannot sign source authority",
    )
    reviewed_at = dt.datetime.fromisoformat(
        reviewer["reviewed_at"].replace("Z", "+00:00")
    )
    require(
        reviewed_at.tzinfo is not None
        and reviewed_at.utcoffset() == dt.timedelta(0),
        "review time must be UTC",
    )
    require(decision["disposition"] is not None, "submitted decision lacks disposition")
    require(decision["family_policy"]["mode"] is not None, "family policy unanswered")
    require(
        decision["family_policy"]["rationale"]
        and decision["family_policy"]["evidence_refs"],
        "family policy lacks rationale/evidence",
    )

    selected_families = {item["package_family"] for item in selected}
    policy = decision["family_policy"]
    if policy["mode"] == "single_family":
        require(
            policy["primary_family"] is not None
            and selected_families <= {policy["primary_family"]},
            "single-family policy disagrees with selections",
        )
    else:
        require(
            policy["primary_family"] is not None,
            "mixed-family policy lacks primary family",
        )

    all_roles_decided = True
    all_roles_selected = True
    for role in decision["role_decisions"]:
        if role["status"] == "selected":
            require(
                bool(role["selected_files"])
                and role["unavailability_reason"] is None
                and role["rationale"]
                and role["evidence_refs"],
                f"selected role incomplete: {role['role']}",
            )
        elif role["status"] == "unavailable":
            all_roles_selected = False
            require(
                not role["selected_files"]
                and role["unavailability_reason"]
                and role["rationale"]
                and role["evidence_refs"],
                f"unavailable role incomplete: {role['role']}",
            )
        else:
            all_roles_decided = False
            all_roles_selected = False
            require(
                not role["selected_files"]
                and role["unavailability_reason"] is None,
                f"unanswered role contains selection: {role['role']}",
            )

    divergences_decided = True
    for row in decision["divergence_decisions"]:
        if row["disposition"] == "unanswered":
            divergences_decided = False
            require(
                not row["selected_git_object_ids"]
                and row["rationale"] is None
                and not row["evidence_refs"],
                "unanswered divergence contains decision evidence",
            )
            continue
        require(
            row["rationale"] and row["evidence_refs"],
            f"decided divergence lacks rationale/evidence: {row['logical_key']}",
        )
        selected_count = len(row["selected_git_object_ids"])
        if row["disposition"] == "select_object":
            require(selected_count == 1, "select_object requires exactly one object")
        elif row["disposition"] == "select_multiple_with_roles":
            require(selected_count >= 2, "select_multiple requires multiple objects")
        elif row["disposition"] in {
            "amend_before_use",
            "reject_group",
            "not_in_selected_scope",
        }:
            require(selected_count == 0, "non-selection divergence carries object IDs")

    complete = all_roles_decided and divergences_decided
    runtime_complete = complete and all_roles_selected
    require(
        decision["decision_complete"] is complete,
        "decision completeness claim disagrees",
    )
    require(
        decision["runtime_description_complete"] is runtime_complete,
        "runtime completeness claim disagrees",
    )
    if decision["disposition"] == "accept_selection":
        require(complete, "accepted selection is incomplete")
    else:
        require(
            not decision["runtime_description_complete"],
            "non-accept decision claims runtime completeness",
        )


def build_status(template_value: dict[str, Any]) -> dict[str, Any]:
    value = inventory()
    submissions = sorted(SUBMISSIONS.glob("*.json")) if SUBMISSIONS.is_dir() else []
    submitted_values = [load(path) for path in submissions]
    for decision in submitted_values:
        validate_decision(decision, value)
        require(
            decision["record_state"] == "submitted",
            "submission directory contains draft",
        )
    accepted = [
        decision for decision in submitted_values
        if decision["disposition"] == "accept_selection"
    ]
    runtime_complete = [
        decision for decision in accepted
        if decision["runtime_description_complete"]
    ]
    # V1 baseline is deliberately locked to zero accepted external decisions.
    # A real submission changes the schema/status contract in a reviewed
    # iteration rather than silently promoting this denial artifact.
    require(not submissions, "source-authority submission requires reviewed status V2")
    template_path = TEMPLATES / f"{template_value['decision_id']}.json"
    status = {
        "schema_version": "dropbear-source-authority-status/1",
        "artifact_id": "dropbear-source-authority-status",
        "authority": "derived_denial_only",
        "source": {
            "inventory_path": INVENTORY.relative_to(ROOT).as_posix(),
            "inventory_sha256": sha_file(INVENTORY),
            "repository_commit": value["repository"]["commit"],
            "repository_tree_id": value["repository"]["tree_id"],
            "canonical_configuration_digest": value["reconciliation"][
                "canonical_configuration_digest"
            ],
        },
        "template": {
            "path": template_path.relative_to(ROOT).as_posix(),
            "sha256": sha_file(template_path),
            "decision_id": template_value["decision_id"],
        },
        "summary": {
            "role_count": len(ROLES),
            "divergent_logical_group_count": value["summary"][
                "divergent_logical_group_count"
            ],
            "submitted_decision_count": len(submitted_values),
            "accepted_decision_count": len(accepted),
            "runtime_complete_decision_count": len(runtime_complete),
            "source_authority_selected": False,
            "support_granted": False,
            "physical_motion_authority": False,
        },
        "accepted_decision_ids": [],
        "blockers": [
            "independent_source_authority_reviewer_missing",
            "all_seven_source_roles_unanswered",
            "all_divergent_logical_groups_unresolved",
            "canonical_robot_graph_decision_missing",
        ],
    }
    schema_validate(status, STATUS_SCHEMA, "source-authority status")
    return status


def generate() -> tuple[dict[str, Any], dict[str, Any]]:
    template_value = template()
    template_path = TEMPLATES / f"{template_value['decision_id']}.json"
    atomic_write(template_path, template_value)
    status_value = build_status(template_value)
    atomic_write(STATUS, status_value)
    return template_value, status_value


def check() -> tuple[dict[str, Any], dict[str, Any]]:
    expected_template = template()
    template_path = TEMPLATES / f"{expected_template['decision_id']}.json"
    require(
        template_path.is_file()
        and template_path.read_bytes() == canonical_bytes(expected_template),
        "source-authority template drift",
    )
    expected_status = build_status(expected_template)
    require(
        STATUS.is_file() and STATUS.read_bytes() == canonical_bytes(expected_status),
        "source-authority status drift",
    )
    return expected_template, expected_status


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
            "DROPBEAR_SOURCE_AUTHORITY_DECISION_OK "
            f"state={value['record_state']} disposition={value['disposition']} "
            f"complete={str(value['decision_complete']).lower()} "
            "support=false motion=false"
        )
        return 0
    template_value, status_value = generate() if args.generate else check()
    print(
        "DROPBEAR_SOURCE_AUTHORITY_OK "
        f"roles={len(template_value['role_decisions'])} "
        f"divergent={len(template_value['divergence_decisions'])} "
        f"submitted={status_value['summary']['submitted_decision_count']} "
        "accepted=0 runtime=0 support=false motion=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, SourceAuthorityError, ValueError) as error:
        print(f"Dropbear source authority failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
