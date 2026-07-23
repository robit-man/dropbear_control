#!/usr/bin/env python3
"""Build and validate the positive-capable Dropbear graph registry V2."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTRY = ROOT / "generated/dropbear_source_registry_v2/registry.json"
GRAPH_STATUS = ROOT / "generated/dropbear_graph_v2/status.json"
GRAPH_MANAGER = ROOT / "tools/manage_dropbear_graph_v2.py"
SOURCE_MANAGER = ROOT / "tools/manage_dropbear_source_registry_v2.py"
SUBMISSION_SCHEMA = ROOT / "schemas/dropbear-graph-submission-v2.schema.json"
EVENT_SCHEMA = ROOT / "schemas/dropbear-graph-event-v2.schema.json"
REGISTRY_SCHEMA = ROOT / "schemas/dropbear-graph-registry-v2.schema.json"
INTAKE_ROOT = ROOT / "assets/dropbear/graph_v2"
DECISIONS = INTAKE_ROOT / "decisions"
EVENTS = INTAKE_ROOT / "events"
REGISTRY = ROOT / "generated/dropbear_graph_registry_v2/registry.json"
TRANSITIONS = {
    "accept": ("submitted", "accepted"),
    "reject": ("submitted", "rejected"),
    "revoke": ("accepted", "revoked"),
    "supersede": ("accepted", "superseded"),
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


class GraphRegistryError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GraphRegistryError(message)


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
        raise GraphRegistryError(f"cannot read {path}: {error}") from error
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def module_from(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise GraphRegistryError(f"cannot load validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def graph_manager() -> Any:
    return module_from(GRAPH_MANAGER, "manage_graph_v2_for_graph_registry")


def source_manager() -> Any:
    return module_from(SOURCE_MANAGER, "manage_source_v2_for_graph_registry")


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
        raise GraphRegistryError(
            f"{label} schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def utc(value: str, label: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GraphRegistryError(f"{label} is not ISO time") from error
    require(
        parsed.tzinfo is not None
        and parsed.utcoffset() == dt.timedelta(0),
        f"{label} is not UTC",
    )
    return parsed


def human(identity: str, organization: str, label: str) -> None:
    combined = f"{identity} {organization}".casefold()
    require(
        not any(token in combined for token in AUTOMATION_IDENTIFIERS),
        f"{label} cannot be automation/self-review",
    )


def identity_payload(value: dict[str, Any], id_field: str) -> bytes:
    payload = copy.deepcopy(value)
    payload.pop(id_field, None)
    payload.pop("integrity", None)
    return canonical_bytes(payload)


def expected_submission_id(value: dict[str, Any]) -> str:
    return "graphsubmission-" + sha_bytes(
        identity_payload(value, "submission_id")
    )[:20]


def expected_event_id(value: dict[str, Any]) -> str:
    return "graphevent-" + sha_bytes(identity_payload(value, "event_id"))[:20]


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def validate_submission(
    value: dict[str, Any],
    source_registry: dict[str, Any] | None = None,
) -> None:
    schema_validate(value, SUBMISSION_SCHEMA, "graph submission")
    require(
        value["submission_id"] == expected_submission_id(value)
        and value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "graph submission ID/digest mismatch",
    )
    require(
        value["decision_sha256"]
        == sha_bytes(canonical_bytes(value["decision"])),
        "graph submission decision hash mismatch",
    )
    registry = source_registry if source_registry is not None else load(SOURCE_REGISTRY)
    require(
        value["source_registry_generation_sha256"]
        == registry["registry_generation_sha256"]
        == value["decision"]["subject"]["source_registry_generation_sha256"],
        "graph submission source registry generation drift",
    )
    try:
        graph_manager().validate_decision(value["decision"], registry)
    except ValueError as error:
        raise GraphRegistryError(f"embedded graph V2 decision failed: {error}") from error
    require(
        value["decision"]["record_state"] == "submitted"
        and value["decision"]["decision_complete"],
        "graph submission decision is not submitted/complete",
    )
    submitter = value["submitter"]
    human(
        submitter["actor_id"],
        submitter["organization_or_team"],
        "graph submitter",
    )
    utc(value["submitted_at"], "graph submission time")
    require(
        value["supersedes_submission_id"] != value["submission_id"],
        "graph submission supersedes itself",
    )
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False,
        "graph submission grants support/motion",
    )


def validate_event(
    value: dict[str, Any],
    source_registry: dict[str, Any] | None = None,
) -> None:
    schema_validate(value, EVENT_SCHEMA, "graph lifecycle event")
    require(
        value["event_id"] == expected_event_id(value)
        and value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "graph lifecycle event ID/digest mismatch",
    )
    require(
        (
            value["transition"]["prior_state"],
            value["transition"]["next_state"],
        )
        == TRANSITIONS[value["event_type"]],
        "graph lifecycle transition/type mismatch",
    )
    registry = source_registry if source_registry is not None else load(SOURCE_REGISTRY)
    require(
        value["source_registry_generation_sha256"]
        == registry["registry_generation_sha256"],
        "graph event source registry generation drift",
    )
    superseding = value["subject"]["superseding_submission_id"]
    superseding_hash = value["subject"]["superseding_submission_sha256"]
    require(
        (value["event_type"] == "supersede")
        == (superseding is not None and superseding_hash is not None),
        "graph superseding identity presence/type mismatch",
    )
    approver = value["approver"]
    human(
        approver["approver_id"],
        approver["organization_or_team"],
        "graph lifecycle approver",
    )
    utc(approver["approved_at"], "graph lifecycle approval time")
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False,
        "graph lifecycle event grants support/motion",
    )


def current_source(
    source_registry: dict[str, Any] | None = None,
    graph_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = source_registry if source_registry is not None else load(SOURCE_REGISTRY)
    status = graph_status if graph_status is not None else load(GRAPH_STATUS)
    if source_registry is None:
        try:
            source_manager().check()
        except ValueError as error:
            raise GraphRegistryError(f"source registry replay failed: {error}") from error
    else:
        source_manager().validate_registry(registry)
    if graph_status is None:
        try:
            graph_manager().check()
        except ValueError as error:
            raise GraphRegistryError(f"graph V2 status failed: {error}") from error
    require(
        status["source"]["source_registry_generation_sha256"]
        == registry["registry_generation_sha256"],
        "graph status/source registry generation drift",
    )
    candidate = load(ROOT / status["candidate"]["path"])
    require(
        sha_bytes(canonical_bytes(candidate)) == status["candidate"]["sha256"],
        "graph status candidate hash drift",
    )
    return {
        "source_registry_path": SOURCE_REGISTRY.relative_to(ROOT).as_posix(),
        "source_registry_sha256": sha_bytes(canonical_bytes(registry)),
        "source_registry_generation_sha256": registry[
            "registry_generation_sha256"
        ],
        "source_active_submission_id": registry["active_submission_id"],
        "source_lifecycle": {
            key: registry["summary"][key]
            for key in (
                "submitted_count",
                "accepted_count",
                "rejected_count",
                "revoked_count",
                "superseded_count",
            )
        },
        "canonical_configuration_digest": candidate["subject"][
            "canonical_configuration_digest"
        ],
        "graph_v2_status_path": GRAPH_STATUS.relative_to(ROOT).as_posix(),
        "graph_v2_status_sha256": sha_bytes(canonical_bytes(status)),
    }


def owned_json_files(directory: Path, label: str) -> list[Path]:
    if not directory.is_dir():
        return []
    files = sorted(path for path in directory.iterdir() if path.is_file())
    require(
        all(path.suffix == ".json" for path in files),
        f"{label} namespace contains non-JSON file",
    )
    return files


def path_label(path: Path, fallback: str) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return f"synthetic-fixture/{fallback}/{path.name}"


def eligible(envelope: dict[str, Any]) -> bool:
    decision = envelope["decision"]
    return bool(
        decision["disposition"] == "accept_graph"
        and decision["decision_complete"]
        and decision["canonical_graph_admissible"]
        and decision["migration"]["migration_complete"]
    )


def registry_generation_payload(value: dict[str, Any]) -> bytes:
    return canonical_bytes(
        {
            "source": value["source"],
            "submissions": value["submissions"],
            "events": value["events"],
            "active_submission_id": value["active_submission_id"],
            "active_graph_decision_id": value["active_graph_decision_id"],
            "active_graph_decision_sha256": value[
                "active_graph_decision_sha256"
            ],
        }
    )


def build(
    decisions_dir: Path = DECISIONS,
    events_dir: Path = EVENTS,
    *,
    source_registry: dict[str, Any] | None = None,
    graph_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = source_registry if source_registry is not None else load(SOURCE_REGISTRY)
    source_value = current_source(registry if source_registry is not None else None, graph_status)
    envelopes: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    for path in owned_json_files(decisions_dir, "graph submission"):
        value = load(path)
        validate_submission(value, registry)
        submission_id = value["submission_id"]
        require(
            path.name == f"{submission_id}.json",
            "graph submission filename/ID mismatch",
        )
        require(submission_id not in envelopes, "duplicate graph submission ID")
        envelopes[submission_id] = value
        paths[submission_id] = path

    events: list[tuple[dict[str, Any], Path]] = []
    for path in owned_json_files(events_dir, "graph event"):
        value = load(path)
        validate_event(value, registry)
        require(
            path.name == f"{value['sequence']:06d}-{value['event_id']}.json",
            "graph event filename/sequence/ID mismatch",
        )
        events.append((value, path))
    events.sort(key=lambda row: row[0]["sequence"])
    require(
        [row[0]["sequence"] for row in events]
        == list(range(1, len(events) + 1))
        and len({row[0]["event_id"] for row in events}) == len(events),
        "graph lifecycle sequence/ID order drift",
    )

    states = {submission_id: "submitted" for submission_id in envelopes}
    superseded_by = {submission_id: None for submission_id in envelopes}
    last_event = {submission_id: None for submission_id in envelopes}
    previous_time: dt.datetime | None = None
    for event, _ in events:
        subject = event["subject"]
        submission_id = subject["submission_id"]
        require(submission_id in envelopes, "graph event references unknown submission")
        envelope = envelopes[submission_id]
        require(
            subject["submission_sha256"] == sha_bytes(canonical_bytes(envelope))
            and subject["decision_id"] == envelope["decision"]["decision_id"]
            and subject["decision_sha256"] == envelope["decision_sha256"],
            "graph event subject identity/hash drift",
        )
        approved = utc(event["approver"]["approved_at"], "graph approval")
        require(
            approved >= utc(envelope["submitted_at"], "graph submission"),
            "graph event predates submission",
        )
        if previous_time is not None:
            require(approved > previous_time, "graph event times are not increasing")
        previous_time = approved
        approver_id = event["approver"]["approver_id"]
        require(
            approver_id != envelope["submitter"]["actor_id"]
            and approver_id != envelope["decision"]["reviewer"]["reviewer_id"],
            "graph approver is not independent of submitter/reviewer",
        )
        prior, next_state = TRANSITIONS[event["event_type"]]
        require(
            states[submission_id] == prior
            and event["transition"]
            == {"prior_state": prior, "next_state": next_state},
            "graph lifecycle prior state drift",
        )
        if event["event_type"] == "accept":
            require(eligible(envelope), "accepted graph submission is not eligible")
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
                "graph supersession replacement is unknown",
            )
            replacement = envelopes[replacement_id]
            require(
                replacement_id != submission_id
                and states[replacement_id] == "submitted"
                and replacement["supersedes_submission_id"] == submission_id
                and subject["superseding_submission_sha256"]
                == sha_bytes(canonical_bytes(replacement))
                and eligible(replacement)
                and approved
                >= utc(replacement["submitted_at"], "replacement submission")
                and approver_id != replacement["submitter"]["actor_id"]
                and approver_id
                != replacement["decision"]["reviewer"]["reviewer_id"],
                "graph supersession replacement/approval drift",
            )
            states[submission_id] = "superseded"
            states[replacement_id] = "accepted"
            superseded_by[submission_id] = replacement_id
            last_event[submission_id] = event["event_id"]
            last_event[replacement_id] = event["event_id"]
        require(
            sum(state == "accepted" for state in states.values()) <= 1,
            "multiple active canonical graphs",
        )

    submission_entries = []
    for submission_id in sorted(envelopes):
        envelope = envelopes[submission_id]
        decision = envelope["decision"]
        submission_entries.append(
            {
                "submission_id": submission_id,
                "submission_path": path_label(paths[submission_id], "decisions"),
                "submission_sha256": sha_bytes(canonical_bytes(envelope)),
                "decision_id": decision["decision_id"],
                "decision_sha256": envelope["decision_sha256"],
                "source_registry_generation_sha256": envelope[
                    "source_registry_generation_sha256"
                ],
                "lifecycle_state": states[submission_id],
                "canonical_graph_admissible": decision[
                    "canonical_graph_admissible"
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
        row for row in submission_entries if row["lifecycle_state"] == "accepted"
    ]
    require(len(active) <= 1, "multiple active graph registry entries")
    active_entry = active[0] if active else None
    active_decision = (
        envelopes[active_entry["submission_id"]]["decision"]
        if active_entry
        else None
    )
    counts = {
        state: sum(row["lifecycle_state"] == state for row in submission_entries)
        for state in ("submitted", "accepted", "rejected", "revoked", "superseded")
    }
    value = {
        "schema_version": "dropbear-graph-registry/2",
        "artifact_id": "dropbear-graph-registry-v2",
        "authority": "canonical_graph_selection_only",
        "source": source_value,
        "registry_generation_sha256": "0" * 64,
        "submissions": submission_entries,
        "events": event_entries,
        "active_submission_id": (
            active_entry["submission_id"] if active_entry else None
        ),
        "active_graph_decision_id": (
            active_entry["decision_id"] if active_entry else None
        ),
        "active_graph_decision_sha256": (
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
            "canonical_graph_count": len(active),
            "actuator_mapping_count": (
                len(active_decision["graph"]["actuator_bindings"])
                if active_decision
                else 0
            ),
            "ros_mapping_count": (
                len(active_decision["graph"]["ros_mappings"])
                if active_decision
                else 0
            ),
            "canonical_graph_admissible": bool(active),
        },
        "blockers": (
            []
            if active
            else [
                (
                    "source_registry_has_no_active_submission"
                    if registry["active_submission_id"] is None
                    else "canonical_graph_submission_not_accepted"
                ),
                "runtime_mapping_generation_blocked",
            ]
        ),
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    value["registry_generation_sha256"] = sha_bytes(
        registry_generation_payload(value)
    )
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))
    validate_registry(value, registry, status=graph_status)
    return value


def validate_registry(
    value: dict[str, Any],
    source_registry: dict[str, Any] | None = None,
    *,
    status: dict[str, Any] | None = None,
) -> None:
    schema_validate(value, REGISTRY_SCHEMA, "graph registry")
    require(
        value["source"] == current_source(source_registry, status),
        "graph registry source drift",
    )
    require(
        value["registry_generation_sha256"]
        == sha_bytes(registry_generation_payload(value))
        and value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "graph registry generation/record digest mismatch",
    )
    entries = value["submissions"]
    active = [row for row in entries if row["lifecycle_state"] == "accepted"]
    require(len(active) <= 1, "graph registry has multiple accepted entries")
    expected = active[0] if active else None
    require(
        value["active_submission_id"]
        == (expected["submission_id"] if expected else None)
        and value["active_graph_decision_id"]
        == (expected["decision_id"] if expected else None)
        and value["active_graph_decision_sha256"]
        == (expected["decision_sha256"] if expected else None),
        "graph registry active identity disagreement",
    )
    counts = Counter(row["lifecycle_state"] for row in entries)
    summary = value["summary"]
    require(
        summary["submission_count"] == len(entries)
        and summary["event_count"] == len(value["events"])
        and summary["submitted_count"] == counts["submitted"]
        and summary["accepted_count"] == counts["accepted"]
        and summary["rejected_count"] == counts["rejected"]
        and summary["revoked_count"] == counts["revoked"]
        and summary["superseded_count"] == counts["superseded"]
        and summary["canonical_graph_count"] == len(active)
        and summary["canonical_graph_admissible"] == bool(active)
        and (bool(active) or (
            summary["actuator_mapping_count"] == 0
            and summary["ros_mapping_count"] == 0
        )),
        "graph registry summary disagreement",
    )
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False,
        "graph registry grants support/motion",
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
    value = build()
    atomic_write(REGISTRY, value)
    return value


def check() -> dict[str, Any]:
    value = build()
    require(
        REGISTRY.is_file()
        and REGISTRY.read_bytes() == canonical_bytes(value),
        "tracked graph registry V2 drift",
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
        print("DROPBEAR_GRAPH_SUBMISSION_V2_OK support=false motion=false")
        return 0
    if args.validate_event:
        validate_event(load(args.validate_event.resolve()))
        print("DROPBEAR_GRAPH_EVENT_V2_OK support=false motion=false")
        return 0
    value = generate() if args.generate else check()
    summary = value["summary"]
    print(
        "DROPBEAR_GRAPH_REGISTRY_V2_OK "
        f"submissions={summary['submission_count']} "
        f"events={summary['event_count']} active={summary['accepted_count']} "
        f"revoked={summary['revoked_count']} "
        f"superseded={summary['superseded_count']} "
        "support=false motion=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, GraphRegistryError, ValueError) as error:
        print(f"Dropbear graph registry V2 failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
