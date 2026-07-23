"""Exact-tuple protocol applicability review records.

An accepted record establishes only that one installed
model/hardware/firmware/protocol/transport/control-mode tuple has reviewed
applicability evidence. It never grants complete motor support or motion
authority.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = (
    ROOT / "schemas/myactuator-protocol-applicability-decision.schema.json"
)
VERSION = "myactuator-protocol-applicability-decision/1"
EXACT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:/ @#()-]{0,511}$")
FORBIDDEN = re.compile(
    r"(?:^|[._+:/ @#()-])(?:all|any|current|default|latest|none|null|tbd|"
    r"unknown|unspecified)(?:$|[._+:/ @#()-])",
    re.IGNORECASE,
)
AUTOMATION_IDENTIFIERS = {
    "ai",
    "automation",
    "bot",
    "codex",
    "generator",
    "llm",
    "script",
    "system",
}
PROTOCOL_SCOPES = {"motor_motion_protocol", "fieldbus_protocol"}


class ProtocolApplicabilityDecisionError(ValueError):
    """A review record is malformed, stale, or self-authorized."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolApplicabilityDecisionError(message)


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


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def exact(value: str, label: str) -> None:
    require(
        isinstance(value, str)
        and bool(EXACT.fullmatch(value))
        and not FORBIDDEN.search(value),
        f"{label} must be an exact non-placeholder identity",
    )


def parse_utc(value: str, label: str) -> None:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ProtocolApplicabilityDecisionError(
            f"{label} must be an ISO-8601 timestamp"
        ) from error
    require(
        parsed.tzinfo is not None
        and parsed.utcoffset() == dt.timedelta(0),
        f"{label} must be UTC",
    )


def decision_id_for(subject: dict[str, Any]) -> str:
    return "protocoldecision-" + sha_bytes(canonical_bytes(subject))[:20]


def load_schema(path: Path = DEFAULT_SCHEMA) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProtocolApplicabilityDecisionError(
            f"cannot load applicability decision schema: {error}"
        ) from error
    require(isinstance(value, dict), "decision schema root must be an object")
    return value


def subject_for(
    model: dict[str, Any],
    occurrence: dict[str, Any],
    package: dict[str, Any],
    *,
    hardware_revision: str,
    drive_firmware: str,
    installed_unit_id: str,
    transport: str,
    control_mode: str,
) -> dict[str, Any]:
    claim = occurrence["source_claim"]
    require(
        occurrence["occurrence_id"]
        in model["candidate_protocol_occurrence_ids"],
        "protocol occurrence is not a candidate for this model",
    )
    require(
        occurrence["package_id"] in model["candidate_package_ids"]
        and occurrence["package_id"] == package["package_id"],
        "protocol package is not a candidate for this model",
    )
    require(
        claim["document_scope"] in PROTOCOL_SCOPES,
        "source is not a motor-control protocol",
    )
    require(
        claim["revision"] is not None,
        "protocol source has no exact revision",
    )
    require(
        transport in claim["transports"],
        "transport is not declared by the selected protocol source",
    )
    for label, value in (
        ("hardware revision", hardware_revision),
        ("drive firmware", drive_firmware),
        ("installed unit ID", installed_unit_id),
        ("transport", transport),
        ("control mode", control_mode),
    ):
        exact(value, label)
    return {
        "model_key": model["model_key"],
        "series": model["series"],
        "model": model["model"],
        "package_revision": model["package_revision"],
        "protocol_occurrence_id": occurrence["occurrence_id"],
        "package_id": package["package_id"],
        "document_set": package["document_set"],
        "protocol_file_sha256": occurrence["file_sha256"],
        "protocol_revision": claim["revision"],
        "transport": transport,
        "control_mode": control_mode,
        "hardware_revision": hardware_revision,
        "drive_firmware": drive_firmware,
        "installed_unit_id": installed_unit_id,
    }


def template(
    model: dict[str, Any],
    occurrence: dict[str, Any],
    package: dict[str, Any],
    *,
    hardware_revision: str,
    drive_firmware: str,
    installed_unit_id: str,
    transport: str,
    control_mode: str,
) -> dict[str, Any]:
    subject = subject_for(
        model,
        occurrence,
        package,
        hardware_revision=hardware_revision,
        drive_firmware=drive_firmware,
        installed_unit_id=installed_unit_id,
        transport=transport,
        control_mode=control_mode,
    )
    value = {
        "schema_version": VERSION,
        "record_state": "draft",
        "record_revision": 1,
        "decision_id": decision_id_for(subject),
        "supersedes_record_sha256": None,
        "subject": subject,
        "evidence": {
            "submitter_id": None,
            "inventory": {
                "artifact_ref": None,
                "artifact_sha256": None,
                "entry_id": None,
            },
            "source_review": {
                "reviewer_id": None,
                "reviewed_at_utc": None,
                "locator": None,
                "evidence_refs": [],
            },
            "capture": {
                "observation_class": None,
                "manifest_ref": None,
                "manifest_sha256": None,
                "trace_sha256": None,
                "observed_at_utc": None,
            },
            "rationale": None,
            "evidence_refs": [],
        },
        "review": {
            "status": "unreviewed",
            "reviewer_id": None,
            "organization_or_team": None,
            "independence_attested": None,
            "reviewed_at_utc": None,
            "decision_note": None,
            "signature_evidence_refs": [],
        },
        "disposition": None,
        "applicability_established": False,
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(value)
    validate(value, model, occurrence, package)
    return value


def validate(
    value: dict[str, Any],
    model: dict[str, Any],
    occurrence: dict[str, Any],
    package: dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
) -> None:
    schema = schema or load_schema()
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise ProtocolApplicabilityDecisionError(
            "decision schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "decision record digest mismatch",
    )
    subject = value["subject"]
    expected = subject_for(
        model,
        occurrence,
        package,
        hardware_revision=subject["hardware_revision"],
        drive_firmware=subject["drive_firmware"],
        installed_unit_id=subject["installed_unit_id"],
        transport=subject["transport"],
        control_mode=subject["control_mode"],
    )
    require(subject == expected, "decision subject/source identity drift")
    require(
        value["decision_id"] == decision_id_for(subject),
        "decision ID digest drift",
    )
    require(
        not value["support_granted"]
        and not value["physical_motion_authority"],
        "protocol applicability decision promoted support/motion authority",
    )

    review = value["review"]
    evidence = value["evidence"]
    if value["record_state"] == "draft":
        require(value["disposition"] is None, "draft has a disposition")
        require(
            review
            == {
                "status": "unreviewed",
                "reviewer_id": None,
                "organization_or_team": None,
                "independence_attested": None,
                "reviewed_at_utc": None,
                "decision_note": None,
                "signature_evidence_refs": [],
            },
            "draft contains a review assertion",
        )
        require(
            not value["applicability_established"],
            "draft establishes applicability",
        )
        return

    require(
        review["status"] in {"accepted", "rejected", "needs_more_evidence"},
        "submitted decision has no terminal review status",
    )
    require(
        review["reviewer_id"]
        and review["organization_or_team"]
        and review["independence_attested"] is True
        and review["reviewed_at_utc"]
        and review["decision_note"]
        and review["signature_evidence_refs"],
        "submitted decision lacks independent reviewer evidence",
    )
    parse_utc(review["reviewed_at_utc"], "review time")
    reviewer_identity = (
        review["reviewer_id"] + " " + review["organization_or_team"]
    ).casefold()
    require(
        not any(token in reviewer_identity for token in AUTOMATION_IDENTIFIERS),
        "automation cannot sign a protocol applicability decision",
    )
    expected_disposition = {
        "accepted": "accept_applicability",
        "rejected": "reject_applicability",
        "needs_more_evidence": "needs_more_evidence",
    }[review["status"]]
    require(
        value["disposition"] == expected_disposition,
        "review status and disposition disagree",
    )
    require(
        value["applicability_established"]
        is (review["status"] == "accepted"),
        "applicability state and review status disagree",
    )

    if review["status"] != "accepted":
        require(
            evidence["rationale"] and evidence["evidence_refs"],
            "submitted non-acceptance lacks rationale/evidence",
        )
        return

    inventory = evidence["inventory"]
    source_review = evidence["source_review"]
    capture = evidence["capture"]
    require(
        evidence["submitter_id"]
        and inventory["artifact_ref"]
        and inventory["artifact_sha256"]
        and inventory["entry_id"]
        and source_review["reviewer_id"]
        and source_review["reviewed_at_utc"]
        and source_review["locator"]
        and source_review["evidence_refs"]
        and capture["manifest_ref"]
        and capture["manifest_sha256"]
        and capture["trace_sha256"]
        and capture["observed_at_utc"]
        and evidence["rationale"]
        and evidence["evidence_refs"],
        "accepted applicability lacks installed/source/capture evidence",
    )
    require(
        capture["observation_class"]
        in {"command_response", "bench_confirmation"},
        "listen-only evidence cannot establish command/control-mode applicability",
    )
    parse_utc(source_review["reviewed_at_utc"], "source review time")
    parse_utc(capture["observed_at_utc"], "capture observation time")
    identities = {
        evidence["submitter_id"].casefold(),
        source_review["reviewer_id"].casefold(),
        review["reviewer_id"].casefold(),
    }
    require(
        len(identities) == 3,
        "submitter, source reviewer, and decision reviewer must be independent",
    )
    require(
        all(
            not any(token in identity for token in AUTOMATION_IDENTIFIERS)
            for identity in identities
        ),
        "automation identity cannot supply accepted human evidence",
    )


def load_directory(
    directory: Path,
    models: dict[str, dict[str, Any]],
    occurrences: dict[str, dict[str, Any]],
    packages: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    decisions = []
    hashes: dict[str, str] = {}
    if not directory.exists():
        return decisions, hashes
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProtocolApplicabilityDecisionError(
                f"cannot load {path}: {error}"
            ) from error
        require(isinstance(value, dict), f"{path}: root must be an object")
        subject = value.get("subject")
        require(isinstance(subject, dict), f"{path}: subject missing")
        model = models.get(subject.get("model_key"))
        occurrence = occurrences.get(subject.get("protocol_occurrence_id"))
        package = packages.get(subject.get("package_id"))
        require(model is not None, f"{path}: exact model is absent")
        require(occurrence is not None, f"{path}: protocol occurrence is absent")
        require(package is not None, f"{path}: document package is absent")
        validate(value, model, occurrence, package)
        require(
            value["record_state"] == "submitted",
            f"{path}: controlled decision directory contains a draft",
        )
        require(
            path.name == value["decision_id"] + ".json",
            f"{path}: filename must equal the decision ID",
        )
        decisions.append(value)
        hashes[path.name] = sha_bytes(path.read_bytes())
    identifiers = [value["decision_id"] for value in decisions]
    require(
        len(identifiers) == len(set(identifiers)),
        "decision directory contains duplicate exact tuple IDs",
    )
    accepted_subjects = [
        canonical_bytes(value["subject"])
        for value in decisions
        if value["review"]["status"] == "accepted"
    ]
    require(
        len(accepted_subjects) == len(set(accepted_subjects)),
        "multiple accepted decisions claim one exact tuple",
    )
    return decisions, hashes


__all__ = [
    "ProtocolApplicabilityDecisionError",
    "canonical_bytes",
    "decision_id_for",
    "digest_payload",
    "load_directory",
    "load_schema",
    "set_digest",
    "sha_bytes",
    "subject_for",
    "template",
    "validate",
]
