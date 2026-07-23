#!/usr/bin/env python3
"""Prepare and validate independent exact CAD semantic-review decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "myactuator-cad-review-decision.schema.json"
INSPECTION = ROOT / "generated" / "myactuator" / "cad" / "step_inspection.json"
LEDGER = ROOT / "assets" / "myactuator" / "cad_review.json"
PACKET_MANIFEST = ROOT / "generated" / "myactuator" / "cad" / "review_packet_manifest.json"
REPORTS = ROOT / "generated" / "myactuator" / "cad" / "candidate_export_reports"
TEMPLATES = ROOT / "generated" / "myactuator" / "cad" / "review_decision_templates"
DECISIONS = ROOT / "assets" / "myactuator" / "cad_decisions"
VERSION = "myactuator-cad-review-decision/1"
AUTOMATION_IDENTIFIERS = ("automated", "automation", "codex", "generator", "same-agent", "self-review")


class DecisionError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DecisionError(message)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def context_for_hypothesis(hypothesis_path: Path) -> dict[str, Any]:
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    packets = json.loads(PACKET_MANIFEST.read_text(encoding="utf-8"))
    variant_id = hypothesis["variant_id"]
    source = next((item for item in inspection["variants"] if item["variant_id"] == variant_id), None)
    require(source is not None, "hypothesis source is unknown")
    configuration = next(
        (
            item
            for item in ledger["geometry_configurations"]
            if variant_id in item["source_variant_ids"]
        ),
        None,
    )
    require(configuration is not None, "hypothesis source lacks exact configuration")
    packet = next((item for item in packets["packets"] if item["variant_id"] == variant_id), None)
    require(packet is not None, "hypothesis source lacks review packet record")
    report_path = REPORTS / f"{variant_id}.json"
    require(report_path.is_file(), "hypothesis source lacks candidate export report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "hypothesis": hypothesis,
        "hypothesis_path": hypothesis_path,
        "source": source,
        "configuration": configuration,
        "packet": packet,
        "report": report,
        "report_path": report_path,
    }


def build_template(hypothesis_path: Path) -> dict[str, Any]:
    context = context_for_hypothesis(hypothesis_path)
    hypothesis = context["hypothesis"]
    source = context["source"]
    configuration = context["configuration"]
    report = context["report"]
    identity = canonical_json(
        {
            "configuration_id": configuration["configuration_id"],
            "variant_id": source["variant_id"],
            "hypothesis_sha256": sha256(hypothesis_path),
            "candidate_export_report_sha256": sha256(context["report_path"]),
        }
    )
    candidate_evidence = [
        hypothesis_path.relative_to(ROOT).as_posix(),
        context["report_path"].relative_to(ROOT).as_posix(),
        *hypothesis["evidence_refs"],
    ]
    length_unit = source["length_unit_candidate"]
    require(length_unit in {"millimetre", "metre", "inch"}, "source unit candidate is not singular")
    scale = {"millimetre": 0.001, "metre": 1.0, "inch": 0.0254}[length_unit]
    decision = {
        "schema_version": VERSION,
        "record_state": "draft",
        "decision_id": f"caddecision-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:20]}",
        "configuration_id": configuration["configuration_id"],
        "variant_id": source["variant_id"],
        "source_hashes": {
            "step_sha256": source["step_sha256"],
            "inspection_sha256": sha256(INSPECTION),
            "review_packet_manifest_sha256": sha256(PACKET_MANIFEST),
            "candidate_hypothesis_sha256": sha256(hypothesis_path),
            "candidate_export_report_sha256": sha256(context["report_path"]),
        },
        "reviewer": {
            "reviewer_id": None,
            "independence_attested": None,
            "reviewed_at": None,
            "review_assertion": None,
            "signature_evidence_refs": [],
        },
        "disposition": None,
        "member_review": {
            "status": "candidate",
            "housing_occurrences": hypothesis["housing_occurrences"],
            "output_occurrences": hypothesis["output_occurrences"],
            "evidence_refs": candidate_evidence,
            "rationale": None,
        },
        "unit_review": {
            "status": "candidate",
            "source_length_unit": length_unit,
            "scale_to_m": scale,
            "evidence_refs": [
                f"{INSPECTION.relative_to(ROOT).as_posix()}#{source['variant_id']}"
            ],
            "override_rationale": None,
        },
        "frame_review": {
            "status": "candidate",
            "source_axis_unit": hypothesis["source_axis_unit"],
            "origin_source_mm": hypothesis["origin_source_mm"],
            "source_to_canonical": hypothesis["source_to_canonical"],
            "origin_reference": "candidate assumption: source-axis intersection at source coordinate origin; reviewer must identify the physical reference plane",
            "evidence_refs": candidate_evidence,
            "rationale": None,
        },
        "joint_review": {
            "status": "candidate",
            "joint_type": "continuous",
            "origin_m": report["canonical_joint"]["origin_m"],
            "axis_unit": report["canonical_joint"]["axis_unit"],
            "positive_direction": report["canonical_joint"]["positive_direction"],
            "zero_definition": report["canonical_joint"]["zero_definition"],
            "physical_sign_resolved": False,
            "evidence_refs": candidate_evidence,
            "rationale": None,
        },
        "question_responses": [
            {
                "question_sha256": sha256_text(question),
                "question": question,
                "resolution": "unanswered",
                "response": None,
                "evidence_refs": [],
            }
            for question in hypothesis["unresolved_questions"]
        ],
        "redistribution_review": {
            "status": "license_review_required",
            "evidence_refs": [],
            "rationale": None,
        },
        "semantic_review_complete": False,
        "support_granted": False,
    }
    validate_decision(decision, context)
    return decision


def apply_point(matrix: list[float], point: list[float], w: float) -> list[float]:
    values = [*point, w]
    return [
        sum(matrix[row * 4 + column] * values[column] for column in range(4))
        for row in range(3)
    ]


def vector_norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def validate_frame(frame: dict[str, Any]) -> None:
    axis = frame["source_axis_unit"]
    origin = frame["origin_source_mm"]
    matrix = frame["source_to_canonical"]
    require(all(math.isfinite(value) for value in [*axis, *origin, *matrix]), "non-finite frame value")
    require(math.isclose(vector_norm(axis), 1.0, abs_tol=1e-9), "source axis is not unit")
    require(matrix[12:16] == [0.0, 0.0, 0.0, 1.0], "transform affine row invalid")
    rows = [matrix[0:3], matrix[4:7], matrix[8:11]]
    for row in rows:
        require(math.isclose(vector_norm(row), 1.0, abs_tol=1e-9), "transform row is not unit")
    for first in range(3):
        for second in range(first + 1, 3):
            require(
                math.isclose(sum(rows[first][i] * rows[second][i] for i in range(3)), 0.0, abs_tol=1e-9),
                "transform is not orthogonal",
            )
    require(
        all(math.isclose(value, expected, abs_tol=1e-9) for value, expected in zip(apply_point(matrix, axis, 0.0), [0.0, 0.0, 1.0])),
        "source axis does not map to canonical +Z",
    )
    require(
        all(math.isclose(value, 0.0, abs_tol=1e-9) for value in apply_point(matrix, origin, 1.0)),
        "source origin does not map to canonical zero",
    )


def validate_decision(decision: dict[str, Any], context: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(decision), key=lambda error: list(error.path))
    require(not errors, f"decision schema error: {errors[0].message if errors else ''}")
    hypothesis = context["hypothesis"]
    source = context["source"]
    configuration = context["configuration"]
    require(
        decision["configuration_id"] == configuration["configuration_id"]
        and decision["variant_id"] == source["variant_id"],
        "decision exact identity drift",
    )
    expected_hashes = {
        "step_sha256": source["step_sha256"],
        "inspection_sha256": sha256(INSPECTION),
        "review_packet_manifest_sha256": sha256(PACKET_MANIFEST),
        "candidate_hypothesis_sha256": sha256(context["hypothesis_path"]),
        "candidate_export_report_sha256": sha256(context["report_path"]),
    }
    require(decision["source_hashes"] == expected_hashes, "decision evidence hash drift")
    expected_occurrences = {
        item["occurrence_name"]["decoded"] for item in source["assembly_relationships"]
    }
    housing = set(decision["member_review"]["housing_occurrences"])
    output = set(decision["member_review"]["output_occurrences"])
    require(not housing & output, "reviewed groups overlap")
    require(housing | output == expected_occurrences, "reviewed groups do not cover every occurrence")
    validate_frame(decision["frame_review"])
    require(decision["joint_review"]["origin_m"] == [0.0, 0.0, 0.0], "canonical joint origin drift")
    require(decision["joint_review"]["axis_unit"] == [0.0, 0.0, 1.0], "canonical joint axis drift")
    expected_questions = hypothesis["unresolved_questions"]
    require(
        [item["question"] for item in decision["question_responses"]] == expected_questions,
        "review question coverage/order drift",
    )
    require(
        all(item["question_sha256"] == sha256_text(item["question"]) for item in decision["question_responses"]),
        "review question hash drift",
    )
    require(decision["support_granted"] is False, "review decision cannot grant support")

    if decision["record_state"] == "draft":
        require(decision["disposition"] is None, "draft cannot have disposition")
        require(
            all(value is None for key, value in decision["reviewer"].items() if key != "signature_evidence_refs")
            and decision["reviewer"]["signature_evidence_refs"] == [],
            "draft cannot identify a reviewer",
        )
        require(
            all(decision[name]["status"] == "candidate" for name in ("member_review", "unit_review", "frame_review", "joint_review")),
            "draft review status promoted",
        )
        require(
            all(item["resolution"] == "unanswered" and item["response"] is None and not item["evidence_refs"] for item in decision["question_responses"]),
            "draft contains answered review questions",
        )
        require(decision["semantic_review_complete"] is False, "draft claims complete review")
        return

    reviewer = decision["reviewer"]
    require(
        reviewer["reviewer_id"]
        and reviewer["independence_attested"] is True
        and reviewer["reviewed_at"]
        and reviewer["review_assertion"],
        "submitted decision requires independent reviewer assertion",
    )
    lowered_reviewer = reviewer["reviewer_id"].casefold()
    require(
        not any(token in lowered_reviewer for token in AUTOMATION_IDENTIFIERS),
        "automation/self-review identifier cannot sign an independent decision",
    )
    reviewed_at = datetime.fromisoformat(reviewer["reviewed_at"].replace("Z", "+00:00"))
    require(reviewed_at.tzinfo is not None and reviewed_at.utcoffset() == timezone.utc.utcoffset(reviewed_at), "review timestamp must be UTC")
    require(decision["disposition"] is not None, "submitted decision lacks disposition")

    if decision["disposition"] == "accept_geometry":
        require(decision["semantic_review_complete"] is True, "accepted geometry must mark semantic review complete")
        for name in ("member_review", "unit_review", "frame_review", "joint_review"):
            require(decision[name]["status"] == "reviewed", f"accepted geometry requires reviewed {name}")
            require(bool(decision[name]["evidence_refs"]), f"accepted geometry requires {name} evidence")
        for name in ("member_review", "frame_review", "joint_review"):
            require(bool(decision[name]["rationale"]), f"accepted geometry requires {name} rationale")
        require(
            all(
                item["resolution"] == "resolved"
                and item["response"]
                and item["evidence_refs"]
                for item in decision["question_responses"]
            ),
            "accepted geometry has unanswered/unresolved questions",
        )
    else:
        require(decision["semantic_review_complete"] is False, "non-accept disposition cannot complete semantic review")


def find_context_for_decision(decision: dict[str, Any]) -> dict[str, Any]:
    for hypothesis_path in sorted((ROOT / "assets/myactuator/cad_hypotheses").glob("*.json")):
        hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
        if hypothesis["variant_id"] == decision.get("variant_id"):
            return context_for_hypothesis(hypothesis_path)
    raise DecisionError("decision has no source hypothesis")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write-template", type=Path)
    mode.add_argument("--check-templates", action="store_true")
    mode.add_argument("--validate", type=Path)
    args = parser.parse_args()
    if args.write_template:
        hypothesis_path = args.write_template.resolve()
        decision = build_template(hypothesis_path)
        path = TEMPLATES / f"{decision['variant_id']}.json"
        atomic_write(path, canonical_json(decision))
        print(f"CAD_REVIEW_TEMPLATE_OK {path.relative_to(ROOT)}")
        return 0
    if args.validate:
        decision = json.loads(args.validate.read_text(encoding="utf-8"))
        validate_decision(decision, find_context_for_decision(decision))
        print(
            f"CAD_REVIEW_DECISION_OK state={decision['record_state']} "
            f"disposition={decision['disposition']} support=0"
        )
        return 0
    hypothesis_paths = sorted((ROOT / "assets/myactuator/cad_hypotheses").glob("*.json"))
    require(bool(hypothesis_paths), "no candidate hypotheses")
    for hypothesis_path in hypothesis_paths:
        expected = build_template(hypothesis_path)
        path = TEMPLATES / f"{expected['variant_id']}.json"
        require(path.is_file() and path.read_text(encoding="utf-8") == canonical_json(expected), "review template drift")
    for decision_path in sorted(DECISIONS.glob("*.json")) if DECISIONS.is_dir() else []:
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        validate_decision(decision, find_context_for_decision(decision))
        require(decision["record_state"] == "submitted", "decision directory contains a draft")
    print(f"CAD_REVIEW_TEMPLATES_OK templates={len(hypothesis_paths)} submitted=0 support=0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, DecisionError, ValueError) as error:
        print(f"CAD review decision failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
