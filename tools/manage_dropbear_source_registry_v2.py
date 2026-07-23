#!/usr/bin/env python3
"""Build and validate the positive-capable Dropbear source registry V2."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "generated/dropbear_description/inventory.json"
V1_STATUS = ROOT / "generated/dropbear_source_authority/status.json"
V1_MANAGER = ROOT / "tools/manage_dropbear_source_authority.py"
SUBMISSION_SCHEMA = (
    ROOT / "schemas/dropbear-source-authority-submission-v2.schema.json"
)
EVENT_SCHEMA = ROOT / "schemas/dropbear-source-authority-event-v2.schema.json"
REGISTRY_SCHEMA = (
    ROOT / "schemas/dropbear-source-authority-registry-v2.schema.json"
)
INTAKE_ROOT = ROOT / "assets/dropbear/source_authority_registry"
DECISIONS = INTAKE_ROOT / "decisions"
EVENTS = INTAKE_ROOT / "events"
REGISTRY = ROOT / "generated/dropbear_source_registry_v2/registry.json"
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
TRANSITIONS = {
    "accept": ("submitted", "accepted"),
    "reject": ("submitted", "rejected"),
    "revoke": ("accepted", "revoked"),
    "supersede": ("accepted", "superseded"),
}


class SourceRegistryError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceRegistryError(message)


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
        raise SourceRegistryError(f"cannot read {path}: {error}") from error
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def schema_validate(value: dict[str, Any], path: Path, label: str) -> None:
    schema = load(path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise SourceRegistryError(
            f"{label} schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def source_manager() -> Any:
    name = "manage_dropbear_source_authority_for_registry_v2"
    spec = importlib.util.spec_from_file_location(name, V1_MANAGER)
    if spec is None or spec.loader is None:
        raise SourceRegistryError("cannot load V1 source-authority validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def utc(value: str, label: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SourceRegistryError(f"{label} is not an ISO timestamp") from error
    require(
        parsed.tzinfo is not None
        and parsed.utcoffset() == dt.timedelta(0),
        f"{label} must be UTC",
    )
    return parsed


def human(identity: str, organization: str, label: str) -> None:
    combined = f"{identity} {organization}".casefold()
    require(
        not any(token in combined for token in AUTOMATION_IDENTIFIERS),
        f"{label} cannot be automation/self-review",
    )


def submission_identity_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload.pop("submission_id", None)
    payload.pop("integrity", None)
    return canonical_bytes(payload)


def expected_submission_id(value: dict[str, Any]) -> str:
    return "sourcesubmission-" + sha_bytes(submission_identity_payload(value))[:20]


def event_identity_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload.pop("event_id", None)
    payload.pop("integrity", None)
    return canonical_bytes(payload)


def expected_event_id(value: dict[str, Any]) -> str:
    return "sourceevent-" + sha_bytes(event_identity_payload(value))[:20]


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def validate_submission(value: dict[str, Any]) -> None:
    schema_validate(value, SUBMISSION_SCHEMA, "source submission")
    require(
        value["submission_id"] == expected_submission_id(value),
        "source submission ID mismatch",
    )
    require(
        value["integrity"]["record_sha256"] == sha_bytes(digest_payload(value)),
        "source submission digest mismatch",
    )
    require(
        value["decision_sha256"] == sha_bytes(canonical_bytes(value["decision"])),
        "source submission decision hash mismatch",
    )
    module = source_manager()
    try:
        module.validate_decision(value["decision"])
    except ValueError as error:
        raise SourceRegistryError(
            f"embedded V1 source decision failed: {error}"
        ) from error
    require(
        value["decision"]["record_state"] == "submitted",
        "source submission embeds a draft",
    )
    utc(value["submitted_at"], "source submission time")
    submitter = value["submitter"]
    human(
        submitter["actor_id"],
        submitter["organization_or_team"],
        "source submitter",
    )
    require(
        value["supersedes_submission_id"] != value["submission_id"],
        "source submission supersedes itself",
    )
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False,
        "source submission grants support/motion",
    )


def validate_event(value: dict[str, Any]) -> None:
    schema_validate(value, EVENT_SCHEMA, "source lifecycle event")
    require(
        value["event_id"] == expected_event_id(value),
        "source lifecycle event ID mismatch",
    )
    require(
        value["integrity"]["record_sha256"] == sha_bytes(digest_payload(value)),
        "source lifecycle event digest mismatch",
    )
    require(
        (
            value["transition"]["prior_state"],
            value["transition"]["next_state"],
        )
        == TRANSITIONS[value["event_type"]],
        "source lifecycle event transition/type mismatch",
    )
    superseding = value["subject"]["superseding_submission_id"]
    superseding_hash = value["subject"]["superseding_submission_sha256"]
    require(
        (value["event_type"] == "supersede")
        == (superseding is not None and superseding_hash is not None),
        "superseding identity presence/type mismatch",
    )
    utc(value["approver"]["approved_at"], "source lifecycle approval time")
    approver = value["approver"]
    human(
        approver["approver_id"],
        approver["organization_or_team"],
        "source lifecycle approver",
    )
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False,
        "source lifecycle event grants support/motion",
    )


def owned_json_files(directory: Path, label: str) -> list[Path]:
    if not directory.is_dir():
        return []
    files = sorted(path for path in directory.iterdir() if path.is_file())
    foreign = [path for path in files if path.suffix != ".json"]
    require(not foreign, f"{label} namespace contains non-JSON file")
    return files


def path_label(path: Path, fallback: str) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return f"synthetic-fixture/{fallback}/{path.name}"


def current_source() -> dict[str, Any]:
    inventory = load(INVENTORY)
    status = load(V1_STATUS)
    require(
        inventory["schema_version"] == "dropbear-description-inventory/1"
        and inventory["summary"]["authoritative_description_selected"] is False,
        "source registry inventory baseline drift",
    )
    require(
        status["summary"]["accepted_decision_count"] == 0
        and status["summary"]["source_authority_selected"] is False,
        "V1 status unexpectedly contains authority",
    )
    return {
        "inventory_path": INVENTORY.relative_to(ROOT).as_posix(),
        "inventory_sha256": sha_file(INVENTORY),
        "repository_commit": inventory["repository"]["commit"],
        "repository_tree_id": inventory["repository"]["tree_id"],
        "canonical_configuration_digest": inventory["reconciliation"][
            "canonical_configuration_digest"
        ],
        "v1_status_path": V1_STATUS.relative_to(ROOT).as_posix(),
        "v1_status_sha256": sha_file(V1_STATUS),
    }


def eligible_for_acceptance(envelope: dict[str, Any]) -> bool:
    decision = envelope["decision"]
    return bool(
        decision["disposition"] == "accept_selection"
        and decision["decision_complete"]
        and decision["runtime_description_complete"]
    )


def registry_generation_payload(value: dict[str, Any]) -> bytes:
    return canonical_bytes(
        {
            "source": value["source"],
            "submissions": value["submissions"],
            "events": value["events"],
            "active_submission_id": value["active_submission_id"],
            "active_decision_id": value["active_decision_id"],
            "active_decision_sha256": value["active_decision_sha256"],
        }
    )


def registry_digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def build(
    decisions_dir: Path = DECISIONS,
    events_dir: Path = EVENTS,
) -> dict[str, Any]:
    submission_paths = owned_json_files(decisions_dir, "source submission")
    event_paths = owned_json_files(events_dir, "source event")

    envelopes: dict[str, dict[str, Any]] = {}
    envelope_paths: dict[str, Path] = {}
    for path in submission_paths:
        value = load(path)
        validate_submission(value)
        submission_id = value["submission_id"]
        require(
            path.name == f"{submission_id}.json",
            "source submission filename/ID mismatch",
        )
        require(submission_id not in envelopes, "duplicate source submission ID")
        envelopes[submission_id] = value
        envelope_paths[submission_id] = path

    events: list[tuple[dict[str, Any], Path]] = []
    for path in event_paths:
        value = load(path)
        validate_event(value)
        require(
            path.name == f"{value['sequence']:06d}-{value['event_id']}.json",
            "source event filename/sequence/ID mismatch",
        )
        events.append((value, path))
    events.sort(key=lambda row: row[0]["sequence"])
    require(
        [value["sequence"] for value, _ in events]
        == list(range(1, len(events) + 1)),
        "source lifecycle event sequence is not contiguous",
    )
    require(
        len({value["event_id"] for value, _ in events}) == len(events),
        "duplicate source lifecycle event ID",
    )

    states = {submission_id: "submitted" for submission_id in envelopes}
    superseded_by: dict[str, str | None] = {
        submission_id: None for submission_id in envelopes
    }
    last_event: dict[str, str | None] = {
        submission_id: None for submission_id in envelopes
    }
    previous_time: dt.datetime | None = None
    for event, _ in events:
        subject = event["subject"]
        submission_id = subject["submission_id"]
        require(submission_id in envelopes, "event references unknown submission")
        envelope = envelopes[submission_id]
        require(
            subject["submission_sha256"]
            == sha_bytes(canonical_bytes(envelope))
            and subject["decision_id"] == envelope["decision"]["decision_id"]
            and subject["decision_sha256"] == envelope["decision_sha256"],
            "event subject submission/decision hash drift",
        )
        approved_at = utc(
            event["approver"]["approved_at"], "source lifecycle approval time"
        )
        require(
            approved_at >= utc(envelope["submitted_at"], "source submission time"),
            "source lifecycle event predates submission",
        )
        if previous_time is not None:
            require(
                approved_at > previous_time,
                "source lifecycle approval times must strictly increase",
            )
        previous_time = approved_at

        reviewer = envelope["decision"]["reviewer"]
        approver = event["approver"]
        require(
            approver["approver_id"] != reviewer["reviewer_id"]
            and approver["approver_id"]
            != envelope["submitter"]["actor_id"],
            "source lifecycle approver is not independent of reviewer/submitter",
        )
        prior, next_state = TRANSITIONS[event["event_type"]]
        require(
            states[submission_id] == prior
            and event["transition"] == {
                "prior_state": prior,
                "next_state": next_state,
            },
            "source lifecycle event prior state drift",
        )

        if event["event_type"] == "accept":
            require(
                eligible_for_acceptance(envelope),
                "accepted source submission is not runtime-complete/eligible",
            )
            states[submission_id] = "accepted"
            last_event[submission_id] = event["event_id"]
        elif event["event_type"] == "reject":
            states[submission_id] = "rejected"
            last_event[submission_id] = event["event_id"]
        elif event["event_type"] == "revoke":
            states[submission_id] = "revoked"
            last_event[submission_id] = event["event_id"]
        else:
            replacement_id = subject["superseding_submission_id"]
            require(
                replacement_id in envelopes,
                "supersede event references unknown replacement",
            )
            replacement = envelopes[replacement_id]
            require(
                replacement_id != submission_id
                and states[replacement_id] == "submitted"
                and replacement["supersedes_submission_id"] == submission_id
                and subject["superseding_submission_sha256"]
                == sha_bytes(canonical_bytes(replacement))
                and eligible_for_acceptance(replacement),
                "superseding source submission is not exact/eligible/submitted",
            )
            require(
                approved_at
                >= utc(replacement["submitted_at"], "replacement submission time"),
                "supersede event predates replacement submission",
            )
            replacement_reviewer = replacement["decision"]["reviewer"]
            require(
                approver["approver_id"] != replacement_reviewer["reviewer_id"]
                and approver["approver_id"]
                != replacement["submitter"]["actor_id"],
                "supersede approver is not independent of replacement",
            )
            states[submission_id] = "superseded"
            states[replacement_id] = "accepted"
            superseded_by[submission_id] = replacement_id
            last_event[submission_id] = event["event_id"]
            last_event[replacement_id] = event["event_id"]

        require(
            sum(state == "accepted" for state in states.values()) <= 1,
            "multiple active source authorities",
        )

    submission_entries = []
    for submission_id in sorted(envelopes):
        envelope = envelopes[submission_id]
        submission_entries.append(
            {
                "submission_id": submission_id,
                "submission_path": path_label(
                    envelope_paths[submission_id], "decisions"
                ),
                "submission_sha256": sha_bytes(canonical_bytes(envelope)),
                "decision_id": envelope["decision"]["decision_id"],
                "decision_sha256": envelope["decision_sha256"],
                "lifecycle_state": states[submission_id],
                "runtime_description_complete": envelope["decision"][
                    "runtime_description_complete"
                ],
                "superseded_by_submission_id": superseded_by[submission_id],
                "last_event_id": last_event[submission_id],
            }
        )
    event_entries = [
        {
            "sequence": value["sequence"],
            "event_id": value["event_id"],
            "event_path": path_label(path, "events"),
            "event_sha256": sha_bytes(canonical_bytes(value)),
            "event_type": value["event_type"],
        }
        for value, path in events
    ]
    active = [
        entry
        for entry in submission_entries
        if entry["lifecycle_state"] == "accepted"
    ]
    require(len(active) <= 1, "source registry has multiple active entries")
    active_entry = active[0] if active else None
    counts = {
        state: sum(entry["lifecycle_state"] == state for entry in submission_entries)
        for state in ("submitted", "accepted", "rejected", "revoked", "superseded")
    }
    registry = {
        "schema_version": "dropbear-source-authority-registry/2",
        "artifact_id": "dropbear-source-authority-registry-v2",
        "authority": "source_selection_only",
        "source": current_source(),
        "registry_generation_sha256": "0" * 64,
        "submissions": submission_entries,
        "events": event_entries,
        "active_submission_id": (
            active_entry["submission_id"] if active_entry else None
        ),
        "active_decision_id": (
            active_entry["decision_id"] if active_entry else None
        ),
        "active_decision_sha256": (
            active_entry["decision_sha256"] if active_entry else None
        ),
        "summary": {
            "submission_count": len(submission_entries),
            "event_count": len(event_entries),
            "submitted_count": counts["submitted"],
            "accepted_count": counts["accepted"],
            "rejected_count": counts["rejected"],
            "revoked_count": counts["revoked"],
            "superseded_count": counts["superseded"],
            "active_runtime_complete_count": len(active),
            "source_authority_selected": bool(active),
        },
        "blockers": (
            []
            if active
            else [
                "no_active_accepted_source_submission",
                "canonical_graph_decision_missing",
            ]
        ),
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    registry["registry_generation_sha256"] = sha_bytes(
        registry_generation_payload(registry)
    )
    registry["integrity"]["record_sha256"] = sha_bytes(
        registry_digest_payload(registry)
    )
    validate_registry(registry)
    return registry


def validate_registry(value: dict[str, Any]) -> None:
    schema_validate(value, REGISTRY_SCHEMA, "source registry")
    require(value["source"] == current_source(), "source registry subject drift")
    require(
        value["registry_generation_sha256"]
        == sha_bytes(registry_generation_payload(value)),
        "source registry generation digest mismatch",
    )
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(registry_digest_payload(value)),
        "source registry record digest mismatch",
    )
    entries = value["submissions"]
    ids = [entry["submission_id"] for entry in entries]
    require(len(ids) == len(set(ids)), "source registry submission IDs duplicate")
    event_ids = [entry["event_id"] for entry in value["events"]]
    require(
        len(event_ids) == len(set(event_ids))
        and [entry["sequence"] for entry in value["events"]]
        == list(range(1, len(event_ids) + 1)),
        "source registry event entries duplicate/reorder",
    )
    active = [
        entry for entry in entries if entry["lifecycle_state"] == "accepted"
    ]
    require(len(active) <= 1, "source registry has multiple accepted entries")
    expected_active = active[0] if active else None
    require(
        value["active_submission_id"]
        == (expected_active["submission_id"] if expected_active else None)
        and value["active_decision_id"]
        == (expected_active["decision_id"] if expected_active else None)
        and value["active_decision_sha256"]
        == (expected_active["decision_sha256"] if expected_active else None),
        "source registry active identity disagreement",
    )
    counts = {
        state: sum(entry["lifecycle_state"] == state for entry in entries)
        for state in ("submitted", "accepted", "rejected", "revoked", "superseded")
    }
    summary = value["summary"]
    require(
        summary
        == {
            "submission_count": len(entries),
            "event_count": len(value["events"]),
            "submitted_count": counts["submitted"],
            "accepted_count": counts["accepted"],
            "rejected_count": counts["rejected"],
            "revoked_count": counts["revoked"],
            "superseded_count": counts["superseded"],
            "active_runtime_complete_count": len(active),
            "source_authority_selected": bool(active),
        },
        "source registry summary disagreement",
    )
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False,
        "source registry grants support/motion",
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


def generate(
    decisions_dir: Path | None = None,
    events_dir: Path | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    value = build(decisions_dir or DECISIONS, events_dir or EVENTS)
    atomic_write(output or REGISTRY, value)
    return value


def check(
    decisions_dir: Path | None = None,
    events_dir: Path | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    value = build(decisions_dir or DECISIONS, events_dir or EVENTS)
    output_path = output or REGISTRY
    require(
        output_path.is_file()
        and output_path.read_bytes() == canonical_bytes(value),
        "tracked source registry V2 drift",
    )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--validate-submission", type=Path)
    mode.add_argument("--validate-event", type=Path)
    args = parser.parse_args()
    if args.validate_submission:
        validate_submission(load(args.validate_submission.resolve()))
        print("DROPBEAR_SOURCE_SUBMISSION_V2_OK support=false motion=false")
        return 0
    if args.validate_event:
        validate_event(load(args.validate_event.resolve()))
        print("DROPBEAR_SOURCE_EVENT_V2_OK support=false motion=false")
        return 0
    value = generate() if args.generate else check()
    summary = value["summary"]
    print(
        "DROPBEAR_SOURCE_REGISTRY_V2_OK "
        f"submissions={summary['submission_count']} events={summary['event_count']} "
        f"active={summary['accepted_count']} revoked={summary['revoked_count']} "
        f"superseded={summary['superseded_count']} "
        "support=false motion=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, SourceRegistryError, ValueError) as error:
        print(f"Dropbear source registry V2 failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
