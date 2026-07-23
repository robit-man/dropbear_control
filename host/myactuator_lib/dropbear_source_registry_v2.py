"""Fail-closed host admission for the Dropbear source-authority registry V2.

The governance tool owns registry construction.  This module is deliberately
separate: runtime consumers validate the materialized registry, replay its
lifecycle evidence, and expose only an exact currently accepted source.
Source authority never grants motor support or physical motion authority.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = ROOT / "generated/dropbear_source_registry_v2/registry.json"
DEFAULT_REGISTRY_SCHEMA = (
    ROOT / "schemas/dropbear-source-authority-registry-v2.schema.json"
)
DEFAULT_SUBMISSION_SCHEMA = (
    ROOT / "schemas/dropbear-source-authority-submission-v2.schema.json"
)
DEFAULT_EVENT_SCHEMA = (
    ROOT / "schemas/dropbear-source-authority-event-v2.schema.json"
)
EXPECTED_ROLES = {
    "kinematic_tree",
    "visual_geometry",
    "collision_geometry",
    "inertial_properties",
    "ros2_control",
    "gazebo_constraints",
    "controller_configuration",
}
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


class SourceRegistryAdmissionError(ValueError):
    """Raised when registry evidence cannot safely grant source authority."""


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_bytes(value: bytes, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceRegistryAdmissionError(f"cannot decode {label}: {error}") from error
    if not isinstance(parsed, dict):
        raise SourceRegistryAdmissionError(f"{label} JSON root must be an object")
    return parsed


def _load(path: Path) -> dict[str, Any]:
    try:
        return _load_bytes(path.read_bytes(), str(path))
    except OSError as error:
        raise SourceRegistryAdmissionError(f"cannot read {path}: {error}") from error


def _schema_validate(
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
        raise SourceRegistryAdmissionError(
            f"{label} schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def _digest(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return _sha(_canonical(payload))


def _identity(
    value: dict[str, Any], identifier: str, prefix: str
) -> str:
    payload = copy.deepcopy(value)
    payload.pop(identifier, None)
    payload.pop("integrity", None)
    return prefix + _sha(_canonical(payload))[:20]


def _utc(value: str, label: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SourceRegistryAdmissionError(f"{label} is not ISO time") from error
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise SourceRegistryAdmissionError(f"{label} is not UTC")
    return parsed


def _resolve(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise SourceRegistryAdmissionError("registry evidence path escapes root") from error
    return path


@dataclass(frozen=True)
class SourceRegistryEntry:
    submission_id: str
    decision_id: str
    lifecycle_state: str
    runtime_description_complete: bool
    superseded_by_submission_id: str | None


@dataclass(frozen=True)
class ActiveSourceAuthority:
    submission_id: str
    decision_id: str
    decision_sha256: str
    registry_generation_sha256: str
    selected_paths_by_role: Mapping[str, tuple[str, ...]]

    @property
    def support_granted(self) -> bool:
        return False

    @property
    def physical_motion_authority(self) -> bool:
        return False

    def selected_paths(self, role: str) -> tuple[str, ...]:
        try:
            return self.selected_paths_by_role[role]
        except KeyError as error:
            raise SourceRegistryAdmissionError(
                f"unknown exact source role: {role}"
            ) from error


class DropbearSourceRegistryV2:
    """Validated, lifecycle-replayed source registry snapshot."""

    def __init__(
        self,
        registry: dict[str, Any],
        registry_schema: dict[str, Any],
        submission_schema: dict[str, Any],
        event_schema: dict[str, Any],
        inventory_bytes: bytes,
        v1_status_bytes: bytes,
        submission_bytes_by_path: Mapping[str, bytes],
        event_bytes_by_path: Mapping[str, bytes],
    ):
        _schema_validate(registry, registry_schema, "source registry")
        if registry["integrity"]["record_sha256"] != _digest(registry):
            raise SourceRegistryAdmissionError("source registry digest mismatch")
        generation_payload = {
            "source": registry["source"],
            "submissions": registry["submissions"],
            "events": registry["events"],
            "active_submission_id": registry["active_submission_id"],
            "active_decision_id": registry["active_decision_id"],
            "active_decision_sha256": registry["active_decision_sha256"],
        }
        if registry["registry_generation_sha256"] != _sha(
            _canonical(generation_payload)
        ):
            raise SourceRegistryAdmissionError("source registry generation mismatch")
        if registry["support_granted"] or registry["physical_motion_authority"]:
            raise SourceRegistryAdmissionError("source registry grants support/motion")

        source = registry["source"]
        if (
            _sha(inventory_bytes) != source["inventory_sha256"]
            or _sha(v1_status_bytes) != source["v1_status_sha256"]
        ):
            raise SourceRegistryAdmissionError("source registry baseline hash drift")
        inventory = _load_bytes(inventory_bytes, "Dropbear inventory")
        v1_status = _load_bytes(v1_status_bytes, "source-authority V1 status")
        if (
            inventory.get("schema_version") != "dropbear-description-inventory/1"
            or inventory.get("repository", {}).get("commit")
            != source["repository_commit"]
            or inventory.get("repository", {}).get("tree_id")
            != source["repository_tree_id"]
            or inventory.get("reconciliation", {}).get(
                "canonical_configuration_digest"
            )
            != source["canonical_configuration_digest"]
            or v1_status.get("summary", {}).get("accepted_decision_count") != 0
            or v1_status.get("summary", {}).get("source_authority_selected")
            is not False
        ):
            raise SourceRegistryAdmissionError("source registry baseline identity drift")

        envelopes: dict[str, dict[str, Any]] = {}
        states: dict[str, str] = {}
        entries_by_id: dict[str, dict[str, Any]] = {}
        for entry in registry["submissions"]:
            path = entry["submission_path"]
            if path not in submission_bytes_by_path:
                raise SourceRegistryAdmissionError(
                    f"missing source submission evidence: {path}"
                )
            envelope = _load_bytes(
                submission_bytes_by_path[path], f"source submission {path}"
            )
            _schema_validate(envelope, submission_schema, "source submission")
            submission_id = envelope["submission_id"]
            if (
                submission_id in envelopes
                or submission_id != entry["submission_id"]
                or submission_id
                != _identity(envelope, "submission_id", "sourcesubmission-")
                or envelope["integrity"]["record_sha256"] != _digest(envelope)
                or _sha(_canonical(envelope)) != entry["submission_sha256"]
                or envelope["decision"]["decision_id"] != entry["decision_id"]
                or envelope["decision_sha256"] != entry["decision_sha256"]
                or _sha(_canonical(envelope["decision"]))
                != envelope["decision_sha256"]
                or envelope["decision"]["record_state"] != "submitted"
                or envelope["support_granted"]
                or envelope["physical_motion_authority"]
            ):
                raise SourceRegistryAdmissionError(
                    "source submission identity/integrity drift"
                )
            envelopes[submission_id] = envelope
            states[submission_id] = "submitted"
            entries_by_id[submission_id] = entry

        last_time: dt.datetime | None = None
        event_ids: set[str] = set()
        for expected_sequence, event_entry in enumerate(registry["events"], 1):
            path = event_entry["event_path"]
            if path not in event_bytes_by_path:
                raise SourceRegistryAdmissionError(
                    f"missing source lifecycle evidence: {path}"
                )
            event = _load_bytes(
                event_bytes_by_path[path], f"source lifecycle event {path}"
            )
            _schema_validate(event, event_schema, "source lifecycle event")
            event_id = event["event_id"]
            event_type = event["event_type"]
            if (
                event_id in event_ids
                or event_entry["sequence"] != expected_sequence
                or event["sequence"] != expected_sequence
                or event_id != event_entry["event_id"]
                or event_id != _identity(event, "event_id", "sourceevent-")
                or event["integrity"]["record_sha256"] != _digest(event)
                or _sha(_canonical(event)) != event_entry["event_sha256"]
                or event_type != event_entry["event_type"]
                or event["support_granted"]
                or event["physical_motion_authority"]
            ):
                raise SourceRegistryAdmissionError(
                    "source lifecycle event identity/integrity drift"
                )
            event_ids.add(event_id)
            approved_at = _utc(
                event["approver"]["approved_at"], "source lifecycle approval"
            )
            if last_time is not None and approved_at <= last_time:
                raise SourceRegistryAdmissionError(
                    "source lifecycle time order drift"
                )
            last_time = approved_at
            self._replay_event(event, envelopes, states, approved_at)
            if sum(state == "accepted" for state in states.values()) > 1:
                raise SourceRegistryAdmissionError(
                    "multiple active source authorities"
                )

        for submission_id, entry in entries_by_id.items():
            if states[submission_id] != entry["lifecycle_state"]:
                raise SourceRegistryAdmissionError(
                    "source lifecycle replay/registry state drift"
                )
        active_ids = sorted(
            submission_id
            for submission_id, state in states.items()
            if state == "accepted"
        )
        if len(active_ids) > 1:
            raise SourceRegistryAdmissionError("multiple active source authorities")
        active_id = active_ids[0] if active_ids else None
        active_envelope = envelopes.get(active_id) if active_id else None
        if (
            registry["active_submission_id"] != active_id
            or registry["active_decision_id"]
            != (
                active_envelope["decision"]["decision_id"]
                if active_envelope
                else None
            )
            or registry["active_decision_sha256"]
            != (active_envelope["decision_sha256"] if active_envelope else None)
        ):
            raise SourceRegistryAdmissionError(
                "source registry active identity/replay drift"
            )
        self._validate_summary(registry, states)
        self._registry = copy.deepcopy(registry)
        self._envelopes = envelopes

    @staticmethod
    def _replay_event(
        event: dict[str, Any],
        envelopes: Mapping[str, dict[str, Any]],
        states: dict[str, str],
        approved_at: dt.datetime,
    ) -> None:
        subject = event["subject"]
        submission_id = subject["submission_id"]
        if submission_id not in envelopes:
            raise SourceRegistryAdmissionError(
                "source lifecycle event references unknown submission"
            )
        envelope = envelopes[submission_id]
        prior, next_state = TRANSITIONS[event["event_type"]]
        if (
            states[submission_id] != prior
            or event["transition"]
            != {"prior_state": prior, "next_state": next_state}
            or subject["submission_sha256"] != _sha(_canonical(envelope))
            or subject["decision_id"] != envelope["decision"]["decision_id"]
            or subject["decision_sha256"] != envelope["decision_sha256"]
            or approved_at < _utc(envelope["submitted_at"], "source submission")
        ):
            raise SourceRegistryAdmissionError(
                "source lifecycle subject/transition drift"
            )
        approver = event["approver"]
        identity = (
            f"{approver['approver_id']} "
            f"{approver['organization_or_team']}"
        ).casefold()
        if (
            any(token in identity for token in AUTOMATION_IDENTIFIERS)
            or approver["approver_id"] == envelope["submitter"]["actor_id"]
            or approver["approver_id"]
            == envelope["decision"]["reviewer"]["reviewer_id"]
        ):
            raise SourceRegistryAdmissionError(
                "source lifecycle approver is not independent"
            )
        eligible = (
            envelope["decision"]["disposition"] == "accept_selection"
            and envelope["decision"]["decision_complete"]
            and envelope["decision"]["runtime_description_complete"]
        )
        if event["event_type"] == "accept":
            if not eligible:
                raise SourceRegistryAdmissionError(
                    "accepted source submission is not eligible"
                )
            states[submission_id] = "accepted"
        elif event["event_type"] == "reject":
            states[submission_id] = "rejected"
        elif event["event_type"] == "revoke":
            states[submission_id] = "revoked"
        else:
            replacement_id = subject["superseding_submission_id"]
            if replacement_id not in envelopes:
                raise SourceRegistryAdmissionError(
                    "source supersession replacement is unknown"
                )
            replacement = envelopes[replacement_id]
            replacement_eligible = (
                replacement["decision"]["disposition"] == "accept_selection"
                and replacement["decision"]["decision_complete"]
                and replacement["decision"]["runtime_description_complete"]
            )
            if (
                states[replacement_id] != "submitted"
                or replacement["supersedes_submission_id"] != submission_id
                or subject["superseding_submission_sha256"]
                != _sha(_canonical(replacement))
                or approved_at
                < _utc(replacement["submitted_at"], "replacement submission")
                or not replacement_eligible
                or approver["approver_id"]
                in {
                    replacement["submitter"]["actor_id"],
                    replacement["decision"]["reviewer"]["reviewer_id"],
                }
            ):
                raise SourceRegistryAdmissionError(
                    "source supersession replacement/approval drift"
                )
            states[submission_id] = "superseded"
            states[replacement_id] = "accepted"

    @staticmethod
    def _validate_summary(
        registry: dict[str, Any], states: Mapping[str, str]
    ) -> None:
        counts = {
            state: sum(value == state for value in states.values())
            for state in ("submitted", "accepted", "rejected", "revoked", "superseded")
        }
        expected = {
            "submission_count": len(states),
            "event_count": len(registry["events"]),
            "submitted_count": counts["submitted"],
            "accepted_count": counts["accepted"],
            "rejected_count": counts["rejected"],
            "revoked_count": counts["revoked"],
            "superseded_count": counts["superseded"],
            "active_runtime_complete_count": counts["accepted"],
            "source_authority_selected": counts["accepted"] == 1,
        }
        if registry["summary"] != expected:
            raise SourceRegistryAdmissionError("source registry summary drift")
        expected_blockers = (
            []
            if counts["accepted"]
            else [
                "no_active_accepted_source_submission",
                "canonical_graph_decision_missing",
            ]
        )
        if registry["blockers"] != expected_blockers:
            raise SourceRegistryAdmissionError("source registry blockers drift")

    @classmethod
    def load(
        cls,
        registry_path: Path = DEFAULT_REGISTRY,
        registry_schema_path: Path = DEFAULT_REGISTRY_SCHEMA,
        submission_schema_path: Path = DEFAULT_SUBMISSION_SCHEMA,
        event_schema_path: Path = DEFAULT_EVENT_SCHEMA,
        root: Path = ROOT,
    ) -> "DropbearSourceRegistryV2":
        registry = _load(registry_path)
        submission_paths = {
            entry["submission_path"] for entry in registry.get("submissions", [])
        }
        event_paths = {
            entry["event_path"] for entry in registry.get("events", [])
        }
        try:
            inventory_path = _resolve(root, registry["source"]["inventory_path"])
            status_path = _resolve(root, registry["source"]["v1_status_path"])
            submissions = {
                path: _resolve(root, path).read_bytes() for path in submission_paths
            }
            events = {
                path: _resolve(root, path).read_bytes() for path in event_paths
            }
            inventory_bytes = inventory_path.read_bytes()
            status_bytes = status_path.read_bytes()
        except (KeyError, OSError) as error:
            raise SourceRegistryAdmissionError(
                f"cannot load source registry evidence: {error}"
            ) from error
        return cls(
            registry,
            _load(registry_schema_path),
            _load(submission_schema_path),
            _load(event_schema_path),
            inventory_bytes,
            status_bytes,
            submissions,
            events,
        )

    @property
    def registry_generation_sha256(self) -> str:
        return self._registry["registry_generation_sha256"]

    @property
    def source_authority_selected(self) -> bool:
        return self._registry["active_submission_id"] is not None

    @property
    def support_granted(self) -> bool:
        return False

    @property
    def physical_motion_authority(self) -> bool:
        return False

    def entry(self, submission_id: str) -> SourceRegistryEntry:
        match = next(
            (
                row
                for row in self._registry["submissions"]
                if row["submission_id"] == submission_id
            ),
            None,
        )
        if match is None:
            raise SourceRegistryAdmissionError(
                f"unknown exact source submission: {submission_id}"
            )
        return SourceRegistryEntry(
            submission_id=match["submission_id"],
            decision_id=match["decision_id"],
            lifecycle_state=match["lifecycle_state"],
            runtime_description_complete=match["runtime_description_complete"],
            superseded_by_submission_id=match["superseded_by_submission_id"],
        )

    def require_active(
        self,
        *,
        role: str | None = None,
        registry_generation_sha256: str | None = None,
    ) -> ActiveSourceAuthority:
        if (
            registry_generation_sha256 is not None
            and registry_generation_sha256
            != self.registry_generation_sha256
        ):
            raise SourceRegistryAdmissionError(
                "stale source registry generation token"
            )
        submission_id = self._registry["active_submission_id"]
        if submission_id is None:
            raise SourceRegistryAdmissionError(
                "no active accepted source authority: "
                + ",".join(self._registry["blockers"])
            )
        envelope = self._envelopes[submission_id]
        role_rows = envelope["decision"]["role_decisions"]
        roles = [row["role"] for row in role_rows]
        if (
            len(roles) != len(set(roles))
            or set(roles) != EXPECTED_ROLES
            or any(
                row["status"] != "selected" or not row["selected_files"]
                for row in role_rows
            )
        ):
            raise SourceRegistryAdmissionError(
                "active source authority role coverage drift"
            )
        paths = {
            row["role"]: tuple(
                selected["path"] for selected in row["selected_files"]
            )
            for row in role_rows
        }
        authority = ActiveSourceAuthority(
            submission_id=submission_id,
            decision_id=envelope["decision"]["decision_id"],
            decision_sha256=envelope["decision_sha256"],
            registry_generation_sha256=self.registry_generation_sha256,
            selected_paths_by_role=paths,
        )
        if role is not None:
            authority.selected_paths(role)
        return authority


__all__ = [
    "ActiveSourceAuthority",
    "DropbearSourceRegistryV2",
    "SourceRegistryAdmissionError",
    "SourceRegistryEntry",
]
