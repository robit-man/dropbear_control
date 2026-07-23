#!/usr/bin/env python3
"""Generate exact, non-authoritative CAD and plant human handoff packets."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "generated/myactuator/evidence_review/queue.json"
CAD_CAMPAIGN = ROOT / "generated/myactuator/cad/campaign/campaign.json"
PLANT_LEDGER = ROOT / "generated/myactuator/plant/evidence_ledger/ledger.json"
PLANT_SPEC_CANDIDATES = (
    ROOT / "generated/myactuator/plant/spec_candidates/registry.json"
)
ASSIGNMENTS = ROOT / "assets/myactuator/reviewer_assignments.json"
PACKET_SCHEMA = ROOT / "schemas/myactuator-evidence-intake-packet.schema.json"
MANIFEST_SCHEMA = (
    ROOT / "schemas/myactuator-evidence-intake-manifest.schema.json"
)
OUTPUT_DIR = ROOT / "generated/myactuator/evidence_intake"
PACKET_DIR = OUTPUT_DIR / "packets"
MANIFEST = OUTPUT_DIR / "manifest.json"
INDEX = OUTPUT_DIR / "index.html"
VERSION = "myactuator-evidence-intake-manifest/1"
PACKET_VERSION = "myactuator-evidence-intake-packet/1"
GLOBAL_SOURCES = (
    QUEUE,
    CAD_CAMPAIGN,
    PLANT_LEDGER,
    PLANT_SPEC_CANDIDATES,
    ASSIGNMENTS,
    PACKET_SCHEMA,
    MANIFEST_SCHEMA,
)


class EvidenceIntakeError(ValueError):
    """An intake input, packet, manifest, or generated output is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceIntakeError(message)


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
    try:
        return sha_bytes(path.read_bytes())
    except OSError as error:
        raise EvidenceIntakeError(f"cannot hash {path}: {error}") from error


def stable_id(prefix: str, value: Any) -> str:
    return prefix + sha_bytes(canonical_bytes(value))[:20]


def relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError as error:
        raise EvidenceIntakeError(f"path escapes workspace: {path}") from error


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceIntakeError(f"cannot load {path}: {error}") from error
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


def source_binding(
    *,
    source_kind: str,
    occurrence_id: str,
    local_path: str,
    sha256: str,
) -> dict[str, Any]:
    identity = {
        "source_kind": source_kind,
        "occurrence_id": occurrence_id,
        "local_path": local_path,
        "sha256": sha256,
    }
    return {
        "binding_id": stable_id("intakesource-", identity),
        "source_kind": source_kind,
        "occurrence_id": occurrence_id,
        "local_path": local_path,
        "sha256": sha256,
        "candidate_only": True,
        "redistribution_authority": False,
    }


def source_binding_from_path(
    *,
    source_kind: str,
    occurrence_id: str,
    local_path: str,
    expected_sha256: str,
) -> dict[str, Any]:
    path = ROOT / local_path
    require(path.is_file(), f"intake source missing: {local_path}")
    actual = sha_file(path)
    require(
        actual == expected_sha256,
        f"intake source hash drift: {local_path}",
    )
    return source_binding(
        source_kind=source_kind,
        occurrence_id=occurrence_id,
        local_path=local_path,
        sha256=actual,
    )


def global_source_records() -> list[dict[str, str]]:
    return [
        {
            "path": relative(path),
            "sha256": sha_file(path),
        }
        for path in GLOBAL_SOURCES
    ]


def queue_items_by_domain(
    queue: dict[str, Any],
    domain: str,
) -> dict[str, dict[str, Any]]:
    rows = {
        row["subject"]["subject_id"]: row
        for row in queue["items"]
        if row["domain"] == domain
    }
    require(
        len(rows)
        == sum(row["domain"] == domain for row in queue["items"]),
        f"{domain}: duplicate queue subject",
    )
    return rows


def cad_source_bindings(configuration: dict[str, Any]) -> list[dict[str, Any]]:
    packet_evidence = configuration["packet_evidence"]
    packet_path = packet_evidence["packet_json_path"]
    packet = load_json(ROOT / packet_path)
    vendor_path = (
        Path("assets/vendor/myactuator") / packet["vendor_relative_path"]
    ).as_posix()
    bindings = [
        source_binding_from_path(
            source_kind="vendor_step",
            occurrence_id=configuration["variant_id"],
            local_path=vendor_path,
            expected_sha256=configuration["step_sha256"],
        ),
        source_binding_from_path(
            source_kind="review_packet",
            occurrence_id=configuration["variant_id"],
            local_path=packet_path,
            expected_sha256=packet_evidence["packet_json_sha256"],
        ),
        source_binding_from_path(
            source_kind="review_image",
            occurrence_id=f"{configuration['variant_id']}:overview",
            local_path=packet_evidence["overview_path"],
            expected_sha256=packet_evidence["overview_sha256"],
        ),
        source_binding_from_path(
            source_kind="review_image",
            occurrence_id=f"{configuration['variant_id']}:sheet",
            local_path=packet_evidence["sheet_path"],
            expected_sha256=packet_evidence["sheet_sha256"],
        ),
    ]
    candidate_path = configuration["candidate_state"]["candidate_export_path"]
    candidate_sha256 = configuration["candidate_state"][
        "candidate_export_sha256"
    ]
    if candidate_path is not None:
        require(
            candidate_sha256 is not None,
            "candidate export path lacks hash",
        )
        bindings.append(
            source_binding_from_path(
                source_kind="candidate_export",
                occurrence_id=f"{configuration['variant_id']}:candidate",
                local_path=candidate_path,
                expected_sha256=candidate_sha256,
            )
        )
    else:
        require(
            candidate_sha256 is None,
            "candidate export hash lacks path",
        )
    return bindings


def cad_packet(
    *,
    queue: dict[str, Any],
    queue_item: dict[str, Any],
    configuration: dict[str, Any],
    questions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    bindings = cad_source_bindings(configuration)
    source_ids = [row["binding_id"] for row in bindings]
    responses = configuration["question_responses"]
    require(
        [row["question_id"] for row in responses] == list(questions),
        f"{configuration['configuration_id']}: CAD question order drift",
    )
    tasks = [
        {
            "task_id": row["question_id"],
            "task_kind": "cad_question",
            "prompt": questions[row["question_id"]]["prompt"],
            "current_state": "unanswered",
            "canonical_unit": None,
            "candidate_source_ids": source_ids,
            "required_evidence_class": questions[row["question_id"]][
                "required_evidence_class"
            ],
            "candidate_evidence_refs": [],
            "response": None,
            "response_evidence_refs": [],
        }
        for row in responses
    ]
    readiness = queue_item["state"]
    require(
        readiness in {"ready_for_review", "source_or_partition_needed"},
        f"{configuration['configuration_id']}: invalid CAD readiness",
    )
    identity = {
        "packet_kind": "cad_semantic_review",
        "subject_id": configuration["configuration_id"],
    }
    packet = {
        "schema_version": PACKET_VERSION,
        "record_state": "generated_draft",
        "packet_id": stable_id("intakepacket-", identity),
        "packet_kind": "cad_semantic_review",
        "authority": "handoff_navigation_and_draft_scaffolding_only",
        "queue_binding": {
            "queue_id": queue["queue_id"],
            "queue_sha256": sha_file(QUEUE),
            "item_id": queue_item["item_id"],
        },
        "subject": {
            "subject_id": configuration["configuration_id"],
            "series": configuration["series"],
            "model": configuration["model"],
            "package_revision": None,
            "configuration_id": configuration["configuration_id"],
            "variant_id": configuration["variant_id"],
        },
        "workflow": {
            "readiness": readiness,
            "assignment_role_ids": queue_item["assignment_role_ids"],
            "assigned": queue_item["assignment_status"] == "assigned",
            "next_action": queue_item["next_action"],
            "output_schema": (
                "schemas/myactuator-cad-review-decision.schema.json"
            ),
            "controlled_output_directory": (
                "assets/myactuator/cad_decisions"
            ),
            "submission_preconditions": [
                (
                    "Resolve every packet task with exact evidence; blocked "
                    "lanes first require an independently reviewed partition "
                    "or replacement native assembly."
                ),
                (
                    "Generate a candidate hypothesis and export report before "
                    "constructing a semantic decision."
                ),
                (
                    "Validate the resulting submitted decision with "
                    "tools/manage_cad_review_decisions.py."
                ),
            ],
        },
        "source_bindings": bindings,
        "tasks": tasks,
        "blocker_ids": queue_item["blockers"],
        "accepted": False,
        "support_granted": False,
        "physical_motion_authority": False,
        "physical_action_permitted": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(packet)
    return packet


def plant_source_bindings(
    *,
    model: dict[str, Any],
    manuals: dict[str, dict[str, Any]],
    spec_table: dict[str, Any],
) -> list[dict[str, Any]]:
    bindings = []
    for occurrence_id in model["candidate_product_manual_occurrence_ids"]:
        manual = manuals.get(occurrence_id)
        require(
            manual is not None,
            f"{model['model_key']}: candidate manual missing",
        )
        local_path = (
            Path("assets/vendor/myactuator/docs")
            / manual["vendor_relative_path"]
        ).as_posix()
        bindings.append(
            source_binding_from_path(
                source_kind="vendor_pdf",
                occurrence_id=occurrence_id,
                local_path=local_path,
                expected_sha256=manual["file_sha256"],
            )
        )
    bindings.append(
        source_binding_from_path(
            source_kind="plant_spec_candidate_registry",
            occurrence_id=spec_table["table_id"],
            local_path=relative(PLANT_SPEC_CANDIDATES),
            expected_sha256=sha_file(PLANT_SPEC_CANDIDATES),
        )
    )
    return bindings


def plant_packet(
    *,
    queue: dict[str, Any],
    queue_item: dict[str, Any],
    model: dict[str, Any],
    manuals: dict[str, dict[str, Any]],
    spec_table: dict[str, Any],
) -> dict[str, Any]:
    bindings = plant_source_bindings(
        model=model,
        manuals=manuals,
        spec_table=spec_table,
    )
    source_ids = [row["binding_id"] for row in bindings]
    field_rows = [
        *model["parameter_evidence"],
        *model["operating_envelope_evidence"],
    ]
    tasks = []
    for row in field_rows:
        kind = (
            "plant_operating_envelope"
            if row["field_id"].startswith("operating_envelope.")
            else "plant_parameter"
        )
        tasks.append(
            {
                "task_id": row["field_id"],
                "task_kind": kind,
                "prompt": (
                    "Extract exact-model evidence for "
                    f"{row['field_id']} in {row['expected_unit']}; if the "
                    "candidate sources do not state it, preserve the field "
                    "as missing rather than inferring a family default."
                ),
                "current_state": "missing",
                "canonical_unit": row["expected_unit"],
                "candidate_source_ids": source_ids,
                "required_evidence_class": (
                    "exact_model_source_fact_with_page_locator_si_conversion_"
                    "uncertainty_and_independent_review"
                ),
                "candidate_evidence_refs": [
                    candidate["candidate_id"]
                    for candidate in spec_table["candidates"]
                    if candidate["mapping"]["target_field_id"]
                    == row["field_id"]
                ],
                "response": None,
                "response_evidence_refs": [],
            }
        )
    require(
        queue_item["state"] == "ready_for_extraction",
        f"{model['model_key']}: invalid plant readiness",
    )
    identity = {
        "packet_kind": "plant_source_extraction",
        "subject_id": model["model_key"],
    }
    packet = {
        "schema_version": PACKET_VERSION,
        "record_state": "generated_draft",
        "packet_id": stable_id("intakepacket-", identity),
        "packet_kind": "plant_source_extraction",
        "authority": "handoff_navigation_and_draft_scaffolding_only",
        "queue_binding": {
            "queue_id": queue["queue_id"],
            "queue_sha256": sha_file(QUEUE),
            "item_id": queue_item["item_id"],
        },
        "subject": {
            "subject_id": model["model_key"],
            "series": model["series"],
            "model": model["model"],
            "package_revision": model["package_revision"],
            "configuration_id": None,
            "variant_id": None,
        },
        "workflow": {
            "readiness": "ready_for_extraction",
            "assignment_role_ids": queue_item["assignment_role_ids"],
            "assigned": queue_item["assignment_status"] == "assigned",
            "next_action": queue_item["next_action"],
            "output_schema": (
                "schemas/myactuator-plant-source-fact.schema.json"
            ),
            "controlled_output_directory": (
                "assets/myactuator/plant_source_facts"
            ),
            "submission_preconditions": [
                (
                    "Create one source-fact record per observed field and "
                    "preserve all unobserved fields as missing."
                ),
                (
                    "Bind the exact model, PDF occurrence/hash, page/table "
                    "locator, source value/unit, SI conversion and uncertainty."
                ),
                (
                    "Keep extraction unreviewed until a different qualified "
                    "human performs the independent fact review."
                ),
            ],
        },
        "source_bindings": bindings,
        "tasks": tasks,
        "blocker_ids": queue_item["blockers"],
        "accepted": False,
        "support_granted": False,
        "physical_motion_authority": False,
        "physical_action_permitted": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(packet)
    return packet


def validate_packet(
    packet: dict[str, Any],
    *,
    verify_sources: bool = True,
    candidate_index: dict[str, dict[str, str | None]] | None = None,
) -> None:
    schema = load_schema(PACKET_SCHEMA)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(packet),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise EvidenceIntakeError(
            "packet schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        packet["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(packet)),
        f"{packet.get('packet_id')}: digest drift",
    )
    bindings = {
        row["binding_id"]: row for row in packet["source_bindings"]
    }
    require(
        len(bindings) == len(packet["source_bindings"]),
        f"{packet['packet_id']}: duplicate source binding",
    )
    referenced = {
        source_id
        for task in packet["tasks"]
        for source_id in task["candidate_source_ids"]
    }
    require(
        referenced <= set(bindings),
        f"{packet['packet_id']}: task references unknown source",
    )
    require(
        referenced == set(bindings),
        f"{packet['packet_id']}: unreferenced source binding",
    )
    task_ids = [row["task_id"] for row in packet["tasks"]]
    require(
        len(task_ids) == len(set(task_ids)),
        f"{packet['packet_id']}: duplicate task",
    )
    if verify_sources:
        for binding in bindings.values():
            path = ROOT / binding["local_path"]
            require(
                path.is_file() and sha_file(path) == binding["sha256"],
                f"{packet['packet_id']}: source missing or changed: "
                f"{binding['local_path']}",
            )
    require(
        not packet["accepted"]
        and not packet["support_granted"]
        and not packet["physical_motion_authority"]
        and not packet["physical_action_permitted"],
        f"{packet['packet_id']}: authority promotion",
    )
    if packet["packet_kind"] == "cad_semantic_review":
        require(
            packet["subject"]["configuration_id"]
            == packet["subject"]["subject_id"]
            and packet["subject"]["variant_id"] is not None
            and packet["subject"]["package_revision"] is None,
            f"{packet['packet_id']}: CAD subject shape drift",
        )
        require(
            len(packet["tasks"]) == 13
            and all(
                task["task_kind"] == "cad_question"
                and task["current_state"] == "unanswered"
                and task["canonical_unit"] is None
                and not task["candidate_evidence_refs"]
                for task in packet["tasks"]
            ),
            f"{packet['packet_id']}: CAD task shape drift",
        )
    else:
        if candidate_index is None:
            candidate_index = plant_candidate_index(
                load_json(PLANT_SPEC_CANDIDATES)
            )
        require(
            packet["subject"]["configuration_id"] is None
            and packet["subject"]["variant_id"] is None
            and packet["subject"]["package_revision"] is not None,
            f"{packet['packet_id']}: plant subject shape drift",
        )
        require(
            len(packet["tasks"]) == 38
            and all(
                task["task_kind"]
                in {"plant_parameter", "plant_operating_envelope"}
                and task["current_state"] == "missing"
                and task["canonical_unit"] is not None
                for task in packet["tasks"]
            ),
            f"{packet['packet_id']}: plant task shape drift",
        )
        referenced_candidates = {
            candidate_id
            for task in packet["tasks"]
            for candidate_id in task["candidate_evidence_refs"]
        }
        expected_candidates = {
            candidate_id
            for candidate_id, candidate in candidate_index.items()
            if candidate["model_key"] == packet["subject"]["subject_id"]
            and candidate["target_field_id"] is not None
        }
        require(
            referenced_candidates == expected_candidates,
            f"{packet['packet_id']}: plant candidate coverage drift",
        )
        for task in packet["tasks"]:
            for candidate_id in task["candidate_evidence_refs"]:
                candidate = candidate_index.get(candidate_id)
                require(
                    candidate is not None
                    and candidate["model_key"]
                    == packet["subject"]["subject_id"]
                    and candidate["target_field_id"] == task["task_id"],
                    f"{packet['packet_id']}: candidate evidence "
                    "identity/target drift",
                )


def plant_candidate_index(
    registry: dict[str, Any],
) -> dict[str, dict[str, str | None]]:
    require(
        registry["summary"]["model_count"] == 44
        and registry["summary"]["candidate_count"] == 531
        and registry["summary"]["accepted_candidate_count"] == 0
        and registry["summary"]["runtime_admissible_candidate_count"] == 0
        and registry["runtime_plant_admission"] is False
        and registry["support_granted"] is False
        and registry["physical_motion_authority"] is False,
        "plant specification candidate registry authority/count drift",
    )
    result: dict[str, dict[str, str | None]] = {}
    for table in registry["model_tables"]:
        model_key = table["model_identity"]["model_key"]
        for candidate in table["candidates"]:
            identifier = candidate["candidate_id"]
            require(
                identifier not in result,
                f"{identifier}: duplicate plant specification candidate",
            )
            result[identifier] = {
                "model_key": model_key,
                "target_field_id": candidate["mapping"]["target_field_id"],
            }
    require(len(result) == 531, "plant candidate index is incomplete")
    return result


def build() -> tuple[dict[str, Any], dict[str, dict[str, Any]], str]:
    queue = load_json(QUEUE)
    cad = load_json(CAD_CAMPAIGN)
    plant = load_json(PLANT_LEDGER)
    spec_candidates = load_json(PLANT_SPEC_CANDIDATES)
    assignments = load_json(ASSIGNMENTS)
    require(
        queue["summary"]["item_count"] == 145,
        "review queue is not complete",
    )
    require(
        assignments["summary"]["role_count"] == 17,
        "reviewer assignment register is not complete",
    )
    cad_queue = queue_items_by_domain(queue, "cad_articulation")
    plant_queue = queue_items_by_domain(queue, "plant_evidence")
    require(
        len(cad_queue) == 53 and len(plant_queue) == 44,
        "queue CAD/plant partition drift",
    )
    questions = {
        row["question_id"]: row for row in cad["question_catalog"]
    }
    require(len(questions) == 13, "CAD question catalog drift")
    manuals = {
        row["document_occurrence_id"]: row
        for row in plant["candidate_product_manuals"]
    }
    require(len(manuals) == 15, "plant manual catalog drift")
    spec_tables = {
        row["model_identity"]["model_key"]: row
        for row in spec_candidates["model_tables"]
    }
    require(len(spec_tables) == 44, "plant spec table coverage drift")
    candidate_index = plant_candidate_index(spec_candidates)

    packets: dict[str, dict[str, Any]] = {}
    for configuration in cad["configurations"]:
        queue_item = cad_queue.get(configuration["configuration_id"])
        require(
            queue_item is not None,
            f"{configuration['configuration_id']}: queue item missing",
        )
        packet = cad_packet(
            queue=queue,
            queue_item=queue_item,
            configuration=configuration,
            questions=questions,
        )
        validate_packet(packet)
        require(
            packet["packet_id"] not in packets,
            "duplicate intake packet ID",
        )
        packets[packet["packet_id"]] = packet
    for model in plant["models"]:
        queue_item = plant_queue.get(model["model_key"])
        require(
            queue_item is not None,
            f"{model['model_key']}: queue item missing",
        )
        packet = plant_packet(
            queue=queue,
            queue_item=queue_item,
            model=model,
            manuals=manuals,
            spec_table=spec_tables[model["model_key"]],
        )
        validate_packet(packet, candidate_index=candidate_index)
        require(
            packet["packet_id"] not in packets,
            "duplicate intake packet ID",
        )
        packets[packet["packet_id"]] = packet

    require(len(packets) == 97, "expected exactly 97 intake packets")
    packet_entries = []
    for packet in packets.values():
        content = canonical_bytes(packet)
        packet_entries.append(
            {
                "packet_id": packet["packet_id"],
                "packet_kind": packet["packet_kind"],
                "path": (
                    "generated/myactuator/evidence_intake/packets/"
                    f"{packet['packet_id']}.json"
                ),
                "sha256": sha_bytes(content),
                "subject_id": packet["subject"]["subject_id"],
                "queue_item_id": packet["queue_binding"]["item_id"],
                "readiness": packet["workflow"]["readiness"],
                "assigned": packet["workflow"]["assigned"],
                "task_count": len(packet["tasks"]),
                "accepted": False,
                "physical_action_permitted": False,
            }
        )
    cad_packets = [
        packet
        for packet in packets.values()
        if packet["packet_kind"] == "cad_semantic_review"
    ]
    plant_packets = [
        packet
        for packet in packets.values()
        if packet["packet_kind"] == "plant_source_extraction"
    ]
    ready = [
        packet
        for packet in packets.values()
        if packet["workflow"]["readiness"]
        in {"ready_for_review", "ready_for_extraction"}
    ]
    blocked = [
        packet
        for packet in packets.values()
        if packet["workflow"]["readiness"] == "source_or_partition_needed"
    ]
    sources = global_source_records()
    manifest = {
        "schema_version": VERSION,
        "intake_id": stable_id(
            "evidenceintake-",
            {
                "sources": sources,
                "packet_sha256": [
                    row["sha256"] for row in packet_entries
                ],
            },
        ),
        "authority": "human_handoff_navigation_and_generated_drafts_only",
        "sources": sources,
        "policy": {
            "generated_packet_is_not_submission": True,
            "generated_packet_is_not_review": True,
            "missing_values_remain_null": True,
            "family_defaults_forbidden": True,
            "independent_review_required": True,
            "source_drift_revokes": True,
            "physical_actions_require_separate_authorization": True,
            "intake_never_grants_support_or_motion": True,
        },
        "packets": packet_entries,
        "summary": {
            "packet_count": len(packets),
            "cad_packet_count": len(cad_packets),
            "plant_packet_count": len(plant_packets),
            "ready_packet_count": len(ready),
            "blocked_packet_count": len(blocked),
            "task_count": sum(len(packet["tasks"]) for packet in packets.values()),
            "cad_task_count": sum(
                len(packet["tasks"]) for packet in cad_packets
            ),
            "plant_task_count": sum(
                len(packet["tasks"]) for packet in plant_packets
            ),
            "assigned_packet_count": sum(
                packet["workflow"]["assigned"]
                for packet in packets.values()
            ),
            "accepted_packet_count": 0,
            "physical_action_permitted_count": 0,
        },
        "accepted": False,
        "support_granted": False,
        "physical_motion_authority": False,
        "physical_action_permitted": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(manifest)
    validate_manifest(manifest, packets=packets)
    return manifest, packets, render_index(manifest, packets)


def validate_manifest(
    value: dict[str, Any],
    *,
    packets: dict[str, dict[str, Any]],
    verify_sources: bool = True,
) -> None:
    schema = load_schema(MANIFEST_SCHEMA)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise EvidenceIntakeError(
            "manifest schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "intake manifest digest drift",
    )
    candidate_index = plant_candidate_index(
        load_json(PLANT_SPEC_CANDIDATES)
    )
    if verify_sources:
        require(
            value["sources"] == global_source_records(),
            "intake manifest source drift",
        )
    require(
        [row["packet_id"] for row in value["packets"]]
        == list(packets),
        "intake packet order/coverage drift",
    )
    for row in value["packets"]:
        packet = packets[row["packet_id"]]
        validate_packet(
            packet,
            verify_sources=verify_sources,
            candidate_index=candidate_index,
        )
        require(
            row["sha256"] == sha_bytes(canonical_bytes(packet))
            and row["packet_kind"] == packet["packet_kind"]
            and row["subject_id"] == packet["subject"]["subject_id"]
            and row["queue_item_id"] == packet["queue_binding"]["item_id"]
            and row["readiness"] == packet["workflow"]["readiness"]
            and row["assigned"] == packet["workflow"]["assigned"]
            and row["task_count"] == len(packet["tasks"]),
            f"{row['packet_id']}: manifest projection drift",
        )
    expected_summary = {
        "packet_count": len(packets),
        "cad_packet_count": sum(
            packet["packet_kind"] == "cad_semantic_review"
            for packet in packets.values()
        ),
        "plant_packet_count": sum(
            packet["packet_kind"] == "plant_source_extraction"
            for packet in packets.values()
        ),
        "ready_packet_count": sum(
            packet["workflow"]["readiness"]
            in {"ready_for_review", "ready_for_extraction"}
            for packet in packets.values()
        ),
        "blocked_packet_count": sum(
            packet["workflow"]["readiness"]
            == "source_or_partition_needed"
            for packet in packets.values()
        ),
        "task_count": sum(
            len(packet["tasks"]) for packet in packets.values()
        ),
        "cad_task_count": sum(
            len(packet["tasks"])
            for packet in packets.values()
            if packet["packet_kind"] == "cad_semantic_review"
        ),
        "plant_task_count": sum(
            len(packet["tasks"])
            for packet in packets.values()
            if packet["packet_kind"] == "plant_source_extraction"
        ),
        "assigned_packet_count": sum(
            packet["workflow"]["assigned"]
            for packet in packets.values()
        ),
        "accepted_packet_count": 0,
        "physical_action_permitted_count": 0,
    }
    require(
        value["summary"] == expected_summary,
        "intake manifest summary drift",
    )
    require(
        not value["accepted"]
        and not value["support_granted"]
        and not value["physical_motion_authority"]
        and not value["physical_action_permitted"],
        "intake manifest authority promotion",
    )


def render_index(
    manifest: dict[str, Any],
    packets: dict[str, dict[str, Any]],
) -> str:
    rows = []
    for entry in manifest["packets"]:
        packet = packets[entry["packet_id"]]
        subject = packet["subject"]
        rows.append(
            "<tr>"
            f"<td>{html.escape(entry['packet_kind'])}</td>"
            f"<td>{html.escape(subject['series'])}</td>"
            f"<td>{html.escape(subject['model'])}</td>"
            f"<td>{html.escape(entry['readiness'])}</td>"
            f"<td>{entry['task_count']}</td>"
            f"<td>{'assigned' if entry['assigned'] else 'unassigned'}</td>"
            f"<td><a href=\"packets/{html.escape(entry['packet_id'])}.json\">"
            "packet</a></td>"
            "</tr>"
        )
    summary = manifest["summary"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MYACTUATOR evidence intake</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;line-height:1.4}}
.hold{{border:2px solid #9a5b00;background:#fff4dd;padding:1rem}}
.cards{{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}}
.card{{border:1px solid #bbb;padding:.7rem;min-width:10rem}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccc;padding:.4rem;text-align:left}}
th{{background:#eee;position:sticky;top:0}}
</style>
</head>
<body>
<h1>MYACTUATOR CAD and plant evidence intake</h1>
<div class="hold"><strong>Generated handoff only.</strong> These packets are
not submissions, reviews, accepted evidence, motor support, physical-action
authorization or motion authority. Missing values remain null until named
humans provide and independently review exact evidence.</div>
<div class="cards">
<div class="card"><strong>{summary['packet_count']}</strong><br>packets</div>
<div class="card"><strong>{summary['ready_packet_count']}</strong><br>ready for human work</div>
<div class="card"><strong>{summary['blocked_packet_count']}</strong><br>source/partition blocked</div>
<div class="card"><strong>{summary['task_count']}</strong><br>explicit tasks</div>
<div class="card"><strong>{summary['assigned_packet_count']}</strong><br>assigned</div>
<div class="card"><strong>0</strong><br>accepted</div>
</div>
<p>Manifest: <a href="manifest.json">{html.escape(manifest['intake_id'])}</a></p>
<table>
<thead><tr><th>Kind</th><th>Series</th><th>Model</th><th>Readiness</th>
<th>Tasks</th><th>Assignment</th><th>Draft</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>
"""


def expected_files(
    manifest: dict[str, Any],
    packets: dict[str, dict[str, Any]],
    index: str,
) -> dict[str, bytes]:
    files = {
        "manifest.json": canonical_bytes(manifest),
        "index.html": index.encode("utf-8"),
    }
    for packet_id, packet in packets.items():
        files[f"packets/{packet_id}.json"] = canonical_bytes(packet)
    return files


def check_outputs(files: dict[str, bytes]) -> None:
    require(OUTPUT_DIR.is_dir(), "evidence intake output directory missing")
    actual = {
        path.relative_to(OUTPUT_DIR).as_posix()
        for path in OUTPUT_DIR.rglob("*")
        if path.is_file()
    }
    expected = set(files)
    require(
        actual == expected,
        "evidence intake output file set drift",
    )
    for name, content in files.items():
        require(
            (OUTPUT_DIR / name).read_bytes() == content,
            f"evidence intake output drift: {name}",
        )


def write_outputs(files: dict[str, bytes]) -> None:
    OUTPUT_DIR.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=".evidence_intake.",
            dir=OUTPUT_DIR.parent,
        )
    )
    backup = OUTPUT_DIR.parent / ".evidence_intake.backup"
    try:
        for name, content in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        if backup.exists():
            shutil.rmtree(backup)
        if OUTPUT_DIR.exists():
            os.replace(OUTPUT_DIR, backup)
        os.replace(staging, OUTPUT_DIR)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if not OUTPUT_DIR.exists() and backup.exists():
            os.replace(backup, OUTPUT_DIR)
        raise


def generate(*, check: bool) -> dict[str, Any]:
    """Build and either verify or transactionally replace the intake package."""
    manifest, packets, index = build()
    files = expected_files(manifest, packets, index)
    if check:
        check_outputs(files)
    else:
        write_outputs(files)
        check_outputs(files)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    manifest = generate(check=arguments.check)
    summary = manifest["summary"]
    print(
        "EVIDENCE_INTAKE_OK "
        f"intake={manifest['intake_id']} "
        f"packets={summary['packet_count']} "
        f"cad={summary['cad_packet_count']} "
        f"plant={summary['plant_packet_count']} "
        f"ready={summary['ready_packet_count']} "
        f"blocked={summary['blocked_packet_count']} "
        f"tasks={summary['task_count']} "
        f"assigned={summary['assigned_packet_count']} "
        "accepted=0 physical=0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvidenceIntakeError, KeyError, OSError, ValueError) as error:
        print(f"EVIDENCE_INTAKE_ERROR {error}", file=os.sys.stderr)
        raise SystemExit(2)
