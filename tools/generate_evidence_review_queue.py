#!/usr/bin/env python3
"""Generate the unified MYACTUATOR/Dropbear evidence review queue."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import html
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENTS = ROOT / "assets/myactuator/reviewer_assignments.json"
ASSIGNMENT_SCHEMA = (
    ROOT / "schemas/myactuator-reviewer-assignment-register.schema.json"
)
QUEUE_SCHEMA = ROOT / "schemas/myactuator-evidence-review-queue.schema.json"
OUTPUT = ROOT / "generated/myactuator/evidence_review/queue.json"
HTML_OUTPUT = ROOT / "generated/myactuator/evidence_review/index.html"
SOURCES = (
    ROOT / "assets/myactuator/download_index_snapshot.json",
    ROOT / "generated/myactuator/protocol_applicability/registry.json",
    ROOT / "generated/myactuator/cad/campaign/campaign.json",
    ROOT / "generated/myactuator/plant/evidence_ledger/ledger.json",
    ROOT / "generated/dropbear_source_authority/status.json",
    ROOT / "generated/dropbear_graph_review/status.json",
    ROOT / "generated/dropbear_unpowered_discovery/status.json",
    ROOT / "generated/can_adapter_intake/status.json",
    ASSIGNMENTS,
)
ROLES = (
    "vendor_source_change_approver",
    "protocol_evidence_submitter",
    "protocol_source_reviewer",
    "protocol_decision_reviewer",
    "cad_geometry_reviewer",
    "cad_license_owner",
    "plant_source_extractor",
    "plant_fact_reviewer",
    "dropbear_source_reviewer",
    "dropbear_source_approver",
    "dropbear_graph_reviewer",
    "hardware_owner_authorizer",
    "safety_reviewer",
    "u0_operator",
    "inventory_reviewer",
    "evidence_custodian",
    "can_adapter_reviewer",
)
INDEPENDENCE = {
    "vendor_source_change_approver": (),
    "protocol_evidence_submitter": (),
    "protocol_source_reviewer": ("protocol_evidence_submitter",),
    "protocol_decision_reviewer": (
        "protocol_evidence_submitter",
        "protocol_source_reviewer",
    ),
    "cad_geometry_reviewer": (),
    "cad_license_owner": (),
    "plant_source_extractor": (),
    "plant_fact_reviewer": ("plant_source_extractor",),
    "dropbear_source_reviewer": (),
    "dropbear_source_approver": ("dropbear_source_reviewer",),
    "dropbear_graph_reviewer": ("dropbear_source_approver",),
    "hardware_owner_authorizer": (),
    "safety_reviewer": ("u0_operator",),
    "u0_operator": ("safety_reviewer", "inventory_reviewer"),
    "inventory_reviewer": ("u0_operator",),
    "evidence_custodian": (),
    "can_adapter_reviewer": ("hardware_owner_authorizer",),
}
DOMAINS = (
    "protocol_applicability",
    "cad_articulation",
    "plant_evidence",
    "dropbear_source_authority",
    "dropbear_graph_authority",
    "installed_inventory",
    "can_adapter",
)
DEPENDENCIES = {
    "protocol_applicability": ("installed_inventory",),
    "cad_articulation": (),
    "plant_evidence": (),
    "dropbear_source_authority": (),
    "dropbear_graph_authority": ("dropbear_source_authority",),
    "installed_inventory": (),
    "can_adapter": ("installed_inventory",),
}
NEXT_GATES = {
    "protocol_applicability": "G14.PROTOCOL.EXACT_TUPLE_REVIEW",
    "cad_articulation": "G14.CAD.GEOMETRY_REVIEW",
    "plant_evidence": "G14.PLANT.SOURCE_FACT_REVIEW",
    "dropbear_source_authority": "G14.DROPBEAR.SOURCE_AUTHORITY",
    "dropbear_graph_authority": "G14.DROPBEAR.GRAPH_AUTHORITY",
    "installed_inventory": "G14.PHYSICAL.U0_AUTHORIZATION",
    "can_adapter": "G14.ADAPTER.LISTEN_ONLY_SELECTION",
}


class EvidenceReviewQueueError(ValueError):
    """A queue input, assignment, dependency, or output is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceReviewQueueError(message)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def stable_id(prefix: str, value: Any) -> str:
    return prefix + sha_bytes(canonical_bytes(value))[:20]


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceReviewQueueError(f"cannot load {path}: {error}") from error
    require(isinstance(value, dict), f"{path}: root must be an object")
    return value


def load_schema(path: Path) -> dict[str, Any]:
    value = load_json(path)
    Draft202012Validator.check_schema(value)
    return value


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def parse_utc(value: str, label: str) -> None:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise EvidenceReviewQueueError(
            f"{label} must be an ISO-8601 time"
        ) from error
    require(
        parsed.tzinfo is not None
        and parsed.utcoffset() == dt.timedelta(0),
        f"{label} must be UTC",
    )


def validate_assignments(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    schema = load_schema(ASSIGNMENT_SCHEMA)
    errors = sorted(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise EvidenceReviewQueueError(
            "assignment schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "assignment register digest drift",
    )
    require(
        [row["role_id"] for row in value["assignments"]] == list(ROLES),
        "assignment role coverage/order drift",
    )
    by_role = {row["role_id"]: row for row in value["assignments"]}
    for role, row in by_role.items():
        require(
            tuple(row["independent_from_role_ids"]) == INDEPENDENCE[role],
            f"{role}: independence contract drift",
        )
    assigned = [
        row for row in value["assignments"] if row["assignee_id"] is not None
    ]
    acknowledged = [
        row for row in value["assignments"] if row["acknowledged"] is True
    ]
    expected_summary = {
        "role_count": len(ROLES),
        "assigned_role_count": len(assigned),
        "acknowledged_role_count": len(acknowledged),
        "assignment_complete": (
            value["record_state"] == "submitted"
            and len(acknowledged) == len(ROLES)
        ),
    }
    require(
        value["summary"] == expected_summary,
        "assignment summary drift",
    )
    require(
        not value["support_granted"]
        and not value["physical_motion_authority"],
        "reviewer assignment promoted support/motion",
    )
    if value["record_state"] == "draft":
        require(
            not assigned
            and not acknowledged
            and all(
                row["organization_or_team"] is None
                and not row["competence_evidence_refs"]
                and row["acknowledged"] is None
                and row["due_at_utc"] is None
                for row in value["assignments"]
            ),
            "draft assignment register contains assignment claims",
        )
        return by_role
    require(
        len(assigned) == len(ROLES)
        and len(acknowledged) == len(ROLES),
        "submitted assignment register is incomplete",
    )
    for role, row in by_role.items():
        require(
            row["organization_or_team"]
            and row["competence_evidence_refs"]
            and row["due_at_utc"],
            f"{role}: submitted assignment is incomplete",
        )
        parse_utc(row["due_at_utc"], f"{role} due time")
        for independent_role in INDEPENDENCE[role]:
            require(
                row["assignee_id"]
                != by_role[independent_role]["assignee_id"],
                f"{role}: assignee conflicts with {independent_role}",
            )
    return by_role


def source_records() -> list[dict[str, str]]:
    return [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha_file(path),
        }
        for path in SOURCES
    ]


def stream_id(domain: str) -> str:
    return stable_id("reviewstream-", {"domain": domain})


def item(
    *,
    domain: str,
    subject_id: str,
    series: str | None,
    model: str | None,
    variant_id: str | None,
    priority: str,
    state: str,
    assignment_roles: tuple[str, ...],
    assignments: dict[str, dict[str, Any]],
    decision_input_ref: str | None,
    review_surface_refs: list[str],
    required_evidence: list[str],
    blockers: list[str],
    metrics: dict[str, int],
    next_action: str,
    accepted: bool = False,
) -> dict[str, Any]:
    identity = {
        "domain": domain,
        "subject_id": subject_id,
        "variant_id": variant_id,
    }
    return {
        "item_id": stable_id("reviewitem-", identity),
        "workstream_id": stream_id(domain),
        "domain": domain,
        "priority": priority,
        "subject": {
            "subject_id": subject_id,
            "series": series,
            "model": model,
            "variant_id": variant_id,
        },
        "state": state,
        "assignment_role_ids": list(assignment_roles),
        "assignment_status": (
            "assigned"
            if all(
                assignments[role]["assignee_id"] is not None
                and assignments[role]["acknowledged"] is True
                for role in assignment_roles
            )
            else "unassigned"
        ),
        "decision_input_ref": decision_input_ref,
        "review_surface_refs": review_surface_refs,
        "required_evidence": required_evidence,
        "blockers": blockers,
        "metrics": metrics,
        "next_action": next_action,
        "accepted": accepted,
        "support_granted": False,
        "physical_motion_authority": False,
        "physical_action_permitted": False,
    }


def build() -> dict[str, Any]:
    (
        download_index,
        protocol,
        cad,
        plant,
        source_status,
        graph_status,
        discovery,
        adapter,
        assignment_value,
    ) = (load_json(path) for path in SOURCES)
    assignments = validate_assignments(assignment_value)
    require(
        download_index["summary"]["tracked_exact_match"] is True,
        "vendor source index is not an exact tracked match",
    )
    items: list[dict[str, Any]] = []

    for model in protocol["models"]:
        accepted = bool(model["accepted_decision_ids"])
        has_source = bool(model["candidate_protocol_occurrence_ids"])
        if accepted:
            state = "accepted_evidence"
        elif has_source:
            state = "exact_tuple_evidence_needed"
        else:
            state = "source_acquisition_needed"
        items.append(
            item(
                domain="protocol_applicability",
                subject_id=model["model_key"],
                series=model["series"],
                model=model["model"],
                variant_id=None,
                priority="P0",
                state=state,
                assignment_roles=(
                    "protocol_evidence_submitter",
                    "protocol_source_reviewer",
                    "protocol_decision_reviewer",
                ),
                assignments=assignments,
                decision_input_ref=(
                    "schemas/myactuator-protocol-applicability-decision.schema.json"
                ),
                review_surface_refs=[
                    "docs/MYACTUATOR_PROTOCOL_APPLICABILITY.md",
                    "generated/myactuator/protocol_applicability/registry.json",
                ],
                required_evidence=[
                    "exact installed-unit inventory identity",
                    "exact hardware revision and drive firmware",
                    "reviewed protocol PDF occurrence and locator",
                    "command-response capture manifest and trace hashes",
                    "independent applicability decision signature",
                ],
                blockers=list(model["blockers"]),
                metrics={
                    "candidate_protocol_source_count": len(
                        model["candidate_protocol_occurrence_ids"]
                    ),
                    "accepted_exact_tuple_count": len(
                        model["accepted_decision_ids"]
                    ),
                },
                next_action=(
                    "Retain the accepted tuple and acquire separate CAD, plant, "
                    "support and motion evidence."
                    if accepted
                    else (
                        "Capture the exact installed tuple under authorization, "
                        "review one source occurrence, then submit the decision."
                        if has_source
                        else "Obtain and pin an exact motor-control protocol source."
                    )
                ),
                accepted=accepted,
            )
        )

    for configuration in cad["configurations"]:
        candidate = configuration["candidate_state"]
        accepted = configuration["accepted_asset"]
        reviewable = candidate["packet_reviewable_now"]
        items.append(
            item(
                domain="cad_articulation",
                subject_id=configuration["configuration_id"],
                series=configuration["series"],
                model=configuration["model"],
                variant_id=configuration["variant_id"],
                priority="P0",
                state=(
                    "accepted_evidence"
                    if accepted
                    else (
                        "ready_for_review"
                        if reviewable
                        else "source_or_partition_needed"
                    )
                ),
                assignment_roles=(
                    "cad_geometry_reviewer",
                    "cad_license_owner",
                ),
                assignments=assignments,
                decision_input_ref=(
                    "schemas/myactuator-cad-review-decision.schema.json"
                ),
                review_surface_refs=[
                    "generated/myactuator/cad/campaign/index.html",
                    configuration["packet_evidence"]["packet_json_path"],
                    configuration["packet_evidence"]["overview_path"],
                ],
                required_evidence=[
                    "fixed housing occurrence/body selection",
                    "rotating output occurrence/body selection",
                    "source unit and joint frame/origin/axis/zero/sign",
                    "articulation and collision validation",
                    "mass-property disposition and redistribution decision",
                ],
                blockers=(
                    []
                    if accepted
                    else [
                        response["question_id"]
                        for response in configuration["question_responses"]
                        if response["state"] != "answered"
                    ]
                ),
                metrics={
                    "unanswered_question_count": sum(
                        response["state"] != "answered"
                        for response in configuration["question_responses"]
                    ),
                    "packet_reviewable": int(reviewable),
                    "assembly_member_count": (
                        candidate["assembly_member_count"] or 0
                    ),
                    "flattened_component_count": (
                        candidate["flattened_component_count"] or 0
                    ),
                },
                next_action=candidate["current_action"],
                accepted=accepted,
            )
        )

    for model in plant["models"]:
        missing_parameters = sum(
            field["status"] != "accepted_source_fact"
            for field in model["parameter_evidence"]
        )
        missing_envelope = sum(
            field["status"] != "accepted_source_fact"
            for field in model["operating_envelope_evidence"]
        )
        accepted = model["source_fact_complete"]
        items.append(
            item(
                domain="plant_evidence",
                subject_id=model["model_key"],
                series=model["series"],
                model=model["model"],
                variant_id=None,
                priority="P1",
                state=(
                    "accepted_evidence"
                    if accepted
                    else "ready_for_extraction"
                ),
                assignment_roles=(
                    "plant_source_extractor",
                    "plant_fact_reviewer",
                ),
                assignments=assignments,
                decision_input_ref=(
                    "schemas/myactuator-plant-source-fact.schema.json"
                ),
                review_surface_refs=[
                    "generated/myactuator/plant/evidence_ledger/index.html",
                    "assets/myactuator/plant_source_facts/README.md",
                ],
                required_evidence=[
                    "exact PDF hash, page/table/curve locator and model identity",
                    "source value/unit and explicit SI conversion",
                    "bounded uncertainty and operating envelope",
                    "independent source-fact review",
                    "separate fit, holdout correlation and runtime plant admission",
                ],
                blockers=list(model["blockers"]),
                metrics={
                    "candidate_manual_count": len(
                        model["candidate_product_manual_occurrence_ids"]
                    ),
                    "missing_parameter_count": missing_parameters,
                    "missing_operating_envelope_count": missing_envelope,
                    "accepted_source_fact_count": len(model["source_fact_ids"]),
                },
                next_action=(
                    "Extract only exact-model facts from the candidate manuals; "
                    "record every absent field as missing."
                ),
                accepted=accepted,
            )
        )

    items.append(
        item(
            domain="dropbear_source_authority",
            subject_id=source_status["artifact_id"],
            series=None,
            model=None,
            variant_id=None,
            priority="P0",
            state=(
                "accepted_evidence"
                if source_status["summary"]["source_authority_selected"]
                else "reviewer_assignment_needed"
            ),
            assignment_roles=(
                "dropbear_source_reviewer",
                "dropbear_source_approver",
            ),
            assignments=assignments,
            decision_input_ref=source_status["template"]["path"],
            review_surface_refs=[
                source_status["template"]["path"],
                "generated/dropbear_description/inventory.json",
            ],
            required_evidence=[
                "seven source-role selections",
                "29 divergent logical-group decisions",
                "generator lineage for expanded sources",
                "independent source-authority approval",
            ],
            blockers=list(source_status["blockers"]),
            metrics={
                "source_role_count": source_status["summary"]["role_count"],
                "divergent_group_count": source_status["summary"][
                    "divergent_logical_group_count"
                ],
                "accepted_decision_count": source_status["summary"][
                    "accepted_decision_count"
                ],
            },
            next_action=(
                "Assign independent source reviewer/approver and complete the "
                "source-authority template."
            ),
            accepted=source_status["summary"]["source_authority_selected"],
        )
    )
    items.append(
        item(
            domain="dropbear_graph_authority",
            subject_id=graph_status["artifact_id"],
            series=None,
            model=None,
            variant_id=None,
            priority="P0",
            state=(
                "accepted_evidence"
                if graph_status["summary"]["accepted_graph_count"]
                else "dependency_blocked"
            ),
            assignment_roles=("dropbear_graph_reviewer",),
            assignments=assignments,
            decision_input_ref=(
                "generated/dropbear_graph_review/templates/"
                "graphdecision-63fd5467977ca2d39ce7.json"
            ),
            review_surface_refs=[
                "generated/dropbear_graph_review/workbench/index.html",
                "generated/dropbear_graph_review/packet.json",
            ],
            required_evidence=[
                "accepted source-authority generation",
                "all frame/joint/actuator/ROS ownership answers",
                "coupling, singularity and closure classifications",
                "independent graph review and lifecycle activation",
            ],
            blockers=list(graph_status["blockers"]),
            metrics={
                "question_count": graph_status["summary"]["question_count"],
                "unanswered_question_count": graph_status["summary"][
                    "unanswered_question_count"
                ],
                "accepted_graph_count": graph_status["summary"][
                    "accepted_graph_count"
                ],
            },
            next_action=(
                "Complete source authority first, then answer and independently "
                "review all graph cohorts."
            ),
            accepted=bool(graph_status["summary"]["accepted_graph_count"]),
        )
    )
    items.append(
        item(
            domain="installed_inventory",
            subject_id=discovery["artifact_id"],
            series=None,
            model=None,
            variant_id=None,
            priority="P0",
            state=(
                "accepted_evidence"
                if discovery["summary"]["submitted_inventory_count"]
                else "authorization_needed"
            ),
            assignment_roles=(
                "hardware_owner_authorizer",
                "safety_reviewer",
                "u0_operator",
                "inventory_reviewer",
                "evidence_custodian",
            ),
            assignments=assignments,
            decision_input_ref="assets/dropbear/installed_inventory_template.json",
            review_surface_refs=[
                ".aiwg/iterations/iteration-11/discovery/u0-authorization-request.md",
                ".aiwg/iterations/iteration-10/discovery/installed-inventory-capture-runbook.md",
            ],
            required_evidence=[
                "signed bounded U0 authorization",
                "asset/location/isolation/restraint and zero-energy evidence",
                "12-slot label/photo inventory with hashes",
                "independent inventory review and custody seal",
                "restoration confirmation",
            ],
            blockers=list(discovery["blockers"]),
            metrics={
                "installed_actuator_slot_count": discovery["summary"][
                    "installed_actuator_slot_count"
                ],
                "submitted_inventory_count": discovery["summary"][
                    "submitted_inventory_count"
                ],
                "authorized_action_count": discovery["summary"][
                    "authorized_action_count"
                ],
            },
            next_action=(
                "Name all U0 roles and obtain a signed, bounded visual-only "
                "authorization before touching the robot."
            ),
            accepted=bool(discovery["summary"]["submitted_inventory_count"]),
        )
    )
    items.append(
        item(
            domain="can_adapter",
            subject_id=adapter["artifact_id"],
            series=None,
            model=None,
            variant_id=None,
            priority="P0",
            state=(
                "accepted_evidence"
                if adapter["summary"]["selected_listen_only_count"]
                else "dependency_blocked"
            ),
            assignment_roles=("can_adapter_reviewer",),
            assignments=assignments,
            decision_input_ref="schemas/can-adapter-manifest.schema.json",
            review_surface_refs=[
                "docs/CAN_ADAPTER_MANIFEST_INTAKE.md",
                "docs/CAN_ADAPTER_CONFORMANCE.md",
            ],
            required_evidence=[
                "installed controller/transceiver identity",
                "exact adapter and driver/library version manifest",
                "bit timing, filters, timestamps and loss semantics",
                "independently proven physical TX disable for listen-only use",
                "separate runtime-profile review and physical authorization decisions",
            ],
            blockers=list(adapter["blockers"]),
            metrics={
                "reviewed_manifest_count": adapter["summary"][
                    "reviewed_manifest_count"
                ],
                "selected_listen_only_count": adapter["summary"][
                    "selected_listen_only_count"
                ],
                "selected_runtime_count": adapter["summary"][
                    "selected_runtime_count"
                ],
            },
            next_action=(
                "Complete installed-controller inventory, then review one exact "
                "listen-only adapter manifest and TX-disable proof."
            ),
            accepted=bool(adapter["summary"]["selected_listen_only_count"]),
        )
    )

    require(len(items) == 145, "review item coverage drift")
    by_domain = Counter(value["domain"] for value in items)
    state_counts = Counter(value["state"] for value in items)
    stream_ids = {domain: stream_id(domain) for domain in DOMAINS}
    workstreams = []
    for domain in DOMAINS:
        domain_items = [value for value in items if value["domain"] == domain]
        workstreams.append(
            {
                "workstream_id": stream_ids[domain],
                "domain": domain,
                "dependency_workstream_ids": [
                    stream_ids[dependency]
                    for dependency in DEPENDENCIES[domain]
                ],
                "item_count": len(domain_items),
                "state_counts": dict(
                    sorted(Counter(value["state"] for value in domain_items).items())
                ),
                "next_gate": NEXT_GATES[domain],
            }
        )
    sources = source_records()
    value = {
        "schema_version": "myactuator-evidence-review-queue/1",
        "queue_id": stable_id("reviewqueue-", sources),
        "authority": "review_navigation_and_dependency_status_only",
        "sources": sources,
        "policy": {
            "assignment_is_not_approval": True,
            "candidate_is_not_accepted": True,
            "independent_review_required": True,
            "source_drift_revokes": True,
            "physical_actions_require_separate_authorization": True,
            "queue_never_grants_support_or_motion": True,
        },
        "assignments": {
            "register_id": assignment_value["register_id"],
            "record_state": assignment_value["record_state"],
            "role_count": assignment_value["summary"]["role_count"],
            "assigned_role_count": assignment_value["summary"][
                "assigned_role_count"
            ],
            "assignment_complete": assignment_value["summary"][
                "assignment_complete"
            ],
        },
        "workstreams": workstreams,
        "items": items,
        "summary": {
            "item_count": len(items),
            "workstream_count": len(workstreams),
            "protocol_item_count": by_domain["protocol_applicability"],
            "cad_item_count": by_domain["cad_articulation"],
            "plant_item_count": by_domain["plant_evidence"],
            "governance_item_count": (
                by_domain["dropbear_source_authority"]
                + by_domain["dropbear_graph_authority"]
                + by_domain["installed_inventory"]
                + by_domain["can_adapter"]
            ),
            "accepted_item_count": sum(value["accepted"] for value in items),
            "assigned_item_count": sum(
                value["assignment_status"] == "assigned" for value in items
            ),
            "physical_action_permitted_count": 0,
            "state_counts": dict(sorted(state_counts.items())),
        },
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(value)
    validate(value)
    return value


def validate(value: dict[str, Any], *, verify_sources: bool = True) -> None:
    schema = load_schema(QUEUE_SCHEMA)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise EvidenceReviewQueueError(
            "queue schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "queue record digest drift",
    )
    require(
        value["queue_id"] == stable_id("reviewqueue-", value["sources"]),
        "queue identity digest drift",
    )
    if verify_sources:
        require(value["sources"] == source_records(), "queue source hash drift")
    items = value["items"]
    require(
        len({item["item_id"] for item in items}) == len(items) == 145,
        "queue item identity/count drift",
    )
    require(
        all(
            item["item_id"]
            == stable_id(
                "reviewitem-",
                {
                    "domain": item["domain"],
                    "subject_id": item["subject"]["subject_id"],
                    "variant_id": item["subject"]["variant_id"],
                },
            )
            and item["workstream_id"] == stream_id(item["domain"])
            and not item["support_granted"]
            and not item["physical_motion_authority"]
            and not item["physical_action_permitted"]
            for item in items
        ),
        "queue item identity/authority drift",
    )
    by_domain = Counter(item["domain"] for item in items)
    require(
        by_domain
        == {
            "protocol_applicability": 44,
            "cad_articulation": 53,
            "plant_evidence": 44,
            "dropbear_source_authority": 1,
            "dropbear_graph_authority": 1,
            "installed_inventory": 1,
            "can_adapter": 1,
        },
        "queue domain coverage drift",
    )
    workstreams = {
        item["domain"]: item for item in value["workstreams"]
    }
    require(
        list(workstreams) == list(DOMAINS),
        "workstream coverage/order drift",
    )
    for domain, workstream in workstreams.items():
        domain_items = [item for item in items if item["domain"] == domain]
        require(
            workstream["workstream_id"] == stream_id(domain)
            and workstream["dependency_workstream_ids"]
            == [stream_id(item) for item in DEPENDENCIES[domain]]
            and workstream["item_count"] == len(domain_items)
            and workstream["state_counts"]
            == dict(
                sorted(Counter(item["state"] for item in domain_items).items())
            )
            and workstream["next_gate"] == NEXT_GATES[domain],
            f"{domain}: workstream projection drift",
        )
    expected_summary = {
        "item_count": len(items),
        "workstream_count": len(workstreams),
        "protocol_item_count": by_domain["protocol_applicability"],
        "cad_item_count": by_domain["cad_articulation"],
        "plant_item_count": by_domain["plant_evidence"],
        "governance_item_count": 4,
        "accepted_item_count": sum(item["accepted"] for item in items),
        "assigned_item_count": sum(
            item["assignment_status"] == "assigned" for item in items
        ),
        "physical_action_permitted_count": 0,
        "state_counts": dict(
            sorted(Counter(item["state"] for item in items).items())
        ),
    }
    require(value["summary"] == expected_summary, "queue summary drift")
    require(
        not value["support_granted"]
        and not value["physical_motion_authority"],
        "queue promoted support/motion authority",
    )


def render_html(value: dict[str, Any]) -> bytes:
    rows = []
    for item_value in value["items"]:
        subject = item_value["subject"]
        label = "/".join(
            value
            for value in (
                subject["series"],
                subject["model"],
                subject["variant_id"],
            )
            if value
        ) or subject["subject_id"]
        links = " · ".join(
            f'<code>{html.escape(ref)}</code>'
            for ref in item_value["review_surface_refs"]
        )
        rows.append(
            "<tr>"
            f"<td>{html.escape(item_value['priority'])}</td>"
            f"<td>{html.escape(item_value['domain'])}</td>"
            f"<td>{html.escape(label)}</td>"
            f"<td>{html.escape(item_value['state'])}</td>"
            f"<td>{html.escape(item_value['assignment_status'])}</td>"
            f"<td>{html.escape(item_value['next_action'])}</td>"
            f"<td>{links}</td>"
            "</tr>"
        )
    summary = value["summary"]
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MYACTUATOR / Dropbear evidence review queue</title>
<style>
body{{font:14px system-ui,sans-serif;margin:24px;color:#20242a;background:#f5f7fa}}
h1{{margin-bottom:4px}}.hold{{padding:12px;background:#fff1cf;border-left:5px solid #b46b00}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}}.card{{background:white;padding:12px 18px;border:1px solid #ccd3dc;border-radius:8px}}
table{{border-collapse:collapse;width:100%;background:white}}th,td{{border:1px solid #d7dde5;padding:7px;vertical-align:top;text-align:left}}th{{position:sticky;top:0;background:#e8edf4}}code{{font-size:11px;overflow-wrap:anywhere}}
</style></head><body>
<h1>MYACTUATOR / Dropbear evidence review queue</h1>
<p><code>{html.escape(value['queue_id'])}</code></p>
<div class="hold"><strong>No physical authorization.</strong> This queue is
review navigation only. Assignment is not approval; no row grants motor
support or motion authority.</div>
<div class="cards">
<div class="card"><strong>{summary['item_count']}</strong><br>review subjects</div>
<div class="card"><strong>{summary['accepted_item_count']}</strong><br>accepted evidence items</div>
<div class="card"><strong>{summary['assigned_item_count']}</strong><br>fully assigned items</div>
<div class="card"><strong>{summary['physical_action_permitted_count']}</strong><br>physical actions permitted</div>
</div>
<table><thead><tr><th>Priority</th><th>Domain</th><th>Subject</th><th>State</th><th>Assignment</th><th>Next action</th><th>Review surfaces</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>
"""
    return document.encode("utf-8")


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", dir=path.parent
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


def write(value: dict[str, Any]) -> None:
    atomic_write(OUTPUT, canonical_bytes(value))
    atomic_write(HTML_OUTPUT, render_html(value))


def check(value: dict[str, Any]) -> None:
    require(
        OUTPUT.is_file() and OUTPUT.read_bytes() == canonical_bytes(value),
        "generated evidence review queue drift",
    )
    require(
        HTML_OUTPUT.is_file() and HTML_OUTPUT.read_bytes() == render_html(value),
        "generated evidence review HTML drift",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        value = build()
        write(value) if args.write else check(value)
        summary = value["summary"]
        print(
            "EVIDENCE_REVIEW_QUEUE_OK "
            f"queue={value['queue_id']} "
            f"items={summary['item_count']} "
            f"accepted={summary['accepted_item_count']} "
            f"assigned={summary['assigned_item_count']} "
            f"physical={summary['physical_action_permitted_count']}"
        )
        return 0
    except EvidenceReviewQueueError as error:
        print(f"EVIDENCE_REVIEW_QUEUE_ERROR {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
