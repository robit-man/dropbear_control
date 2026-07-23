#!/usr/bin/env python3
"""Validate, replay, and materialize independently reviewed plant facts.

The extracted PDF candidate registry is navigation evidence, not authority.
Only an immutable extractor submission followed by an immutable event from the
separately assigned plant fact reviewer can produce an active source fact.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_REGISTRY = (
    ROOT / "generated/myactuator/plant/spec_candidates/registry.json"
)
ASSIGNMENTS = ROOT / "assets/myactuator/reviewer_assignments.json"
ASSIGNMENT_SCHEMA = (
    ROOT / "schemas/myactuator-reviewer-assignment-register.schema.json"
)
SUBMISSION_SCHEMA = (
    ROOT / "schemas/myactuator-plant-candidate-submission.schema.json"
)
EVENT_SCHEMA = (
    ROOT / "schemas/myactuator-plant-candidate-event.schema.json"
)
FACT_SCHEMA = ROOT / "schemas/myactuator-plant-source-fact.schema.json"
REGISTRY_SCHEMA = (
    ROOT
    / "schemas/myactuator-plant-candidate-decision-registry.schema.json"
)
INPUT_ROOT = ROOT / "assets/myactuator/plant_candidate_decisions"
SUBMISSION_DIRECTORY = INPUT_ROOT / "submissions"
EVENT_DIRECTORY = INPUT_ROOT / "events"
OUTPUT_ROOT = ROOT / "generated/myactuator/plant/candidate_decisions"
OUTPUT_REGISTRY = OUTPUT_ROOT / "registry.json"
OUTPUT_FACT_DIRECTORY = OUTPUT_ROOT / "source_facts"
VERSION = "myactuator-plant-candidate-decision-registry/1"

EXTRACTOR_ROLE = "plant_source_extractor"
REVIEWER_ROLE = "plant_fact_reviewer"
AUTOMATION_ACTOR = re.compile(
    r"(?:^|[^a-z])(codex|chatgpt|openai|generator|automation|bot|agent)"
    r"(?:[^a-z]|$)",
    re.IGNORECASE,
)

PARAMETER_FIELDS = {
    "electrical.phase_resistance_ohm": "ohm",
    "electrical.phase_inductance_h": "H",
    "electrical.torque_constant_nm_per_a": "N*m/A",
    "electrical.back_emf_v_s_per_rad": "V*s/rad",
    "electrical.max_qaxis_current_a": "A",
    "mechanical.rotor_inertia_kg_m2": "kg*m^2",
    "mechanical.output_inertia_kg_m2": "kg*m^2",
    "mechanical.coulomb_friction_nm": "N*m",
    "mechanical.viscous_friction_nm_s_per_rad": "N*m*s/rad",
    "transmission.ratio_motor_per_output": "1",
    "transmission.forward_efficiency_ratio": "1",
    "transmission.reverse_efficiency_ratio": "1",
    "transmission.torsional_stiffness_nm_per_rad": "N*m/rad",
    "transmission.backlash_rad": "rad",
    "saturation.max_motor_speed_rad_s": "rad/s",
    "saturation.max_output_speed_rad_s": "rad/s",
    "saturation.max_continuous_output_torque_nm": "N*m",
    "saturation.max_peak_output_torque_nm": "N*m",
    "saturation.peak_duration_s": "s",
    "thermal.winding_resistance_k_per_w": "K/W",
    "thermal.case_resistance_k_per_w": "K/W",
    "thermal.winding_heat_capacity_j_per_k": "J/K",
    "thermal.case_heat_capacity_j_per_k": "J/K",
    "thermal.max_winding_temperature_k": "K",
    "thermal.max_case_temperature_k": "K",
    "sensor.position_quantization_rad": "rad",
    "sensor.position_noise_stddev_rad": "rad",
    "sensor.velocity_noise_stddev_rad_s": "rad/s",
    "sensor.current_noise_stddev_a": "A",
    "latency.command_delay_s": "s",
    "latency.current_loop_period_s": "s",
    "latency.state_sample_period_s": "s",
    "latency.feedback_delay_s": "s",
    "latency.delay_jitter_s": "s",
}
ENVELOPE_FIELDS = {
    "operating_envelope.supply_voltage_v": "V",
    "operating_envelope.ambient_temperature_k": "K",
    "operating_envelope.output_speed_rad_s": "rad/s",
    "operating_envelope.output_torque_nm": "N*m",
}


class PlantCandidateDecisionError(ValueError):
    """A candidate decision record or replay invariant is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PlantCandidateDecisionError(message)


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


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PlantCandidateDecisionError(
            f"{path}: cannot load JSON: {error}"
        ) from error
    require(isinstance(value, dict), f"{path}: JSON root must be an object")
    return value


def schema_validate(
    value: dict[str, Any],
    schema: dict[str, Any],
    *,
    context: str,
) -> None:
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
        raise PlantCandidateDecisionError(
            f"{context}: schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def validate_digest(value: dict[str, Any], context: str) -> None:
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        f"{context}: record digest drift",
    )


def _identity_payload(value: dict[str, Any], identifier_key: str) -> bytes:
    payload = copy.deepcopy(value)
    payload.pop(identifier_key, None)
    payload.pop("integrity", None)
    return canonical_bytes(payload)


def expected_submission_id(value: dict[str, Any]) -> str:
    return "plantcandidatesubmission-" + sha_bytes(
        _identity_payload(value, "submission_id")
    )[:20]


def expected_event_id(value: dict[str, Any]) -> str:
    return "plantcandidateevent-" + sha_bytes(
        _identity_payload(value, "event_id")
    )[:20]


def expected_fact_id(value: dict[str, Any]) -> str:
    payload = {
        "candidate_id": value["provenance"]["candidate_id"],
        "candidate_sha256": value["provenance"]["candidate_sha256"],
        "submission_id": value["review"]["submission_id"],
        "submission_sha256": value["review"]["submission_sha256"],
        "acceptance_event_id": value["review"]["acceptance_event_id"],
        "acceptance_event_sha256": value["review"][
            "acceptance_event_sha256"
        ],
        "model_identity": value["model_identity"],
        "target": value["target"],
        "observation": value["observation"],
    }
    return "plantfact-" + sha_bytes(canonical_bytes(payload))[:20]


def finalize_submission(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["submission_id"] = expected_submission_id(result)
    set_digest(result)
    return result


def finalize_event(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["event_id"] = expected_event_id(result)
    set_digest(result)
    return result


def _finite(value: Any, context: str) -> float:
    require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value),
        f"{context}: finite number required",
    )
    return float(value)


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)


def _timestamp(value: str, context: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PlantCandidateDecisionError(
            f"{context}: invalid UTC timestamp"
        ) from error
    require(
        result.utcoffset() is not None
        and result.utcoffset().total_seconds() == 0,
        f"{context}: timestamp must be UTC",
    )
    return result


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return "synthetic-fixture/" + path.name


def _validate_assignment_register(
    value: dict[str, Any],
    *,
    path: Path,
) -> dict[str, dict[str, Any]]:
    schema_validate(
        value,
        load_json(ASSIGNMENT_SCHEMA),
        context=str(path),
    )
    validate_digest(value, str(path))
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False,
        f"{path}: assignment register grants authority",
    )
    roles = [item["role_id"] for item in value["assignments"]]
    require(
        len(roles) == len(set(roles)) == 17,
        f"{path}: reviewer roles must be unique and complete",
    )
    assigned = sum(
        item["assignee_id"] is not None
        and item["organization_or_team"] is not None
        and bool(item["competence_evidence_refs"])
        for item in value["assignments"]
    )
    acknowledged = sum(
        item["acknowledged"] is True for item in value["assignments"]
    )
    require(
        value["summary"]
        == {
            "role_count": 17,
            "assigned_role_count": assigned,
            "acknowledged_role_count": acknowledged,
            "assignment_complete": assigned == acknowledged == 17,
        },
        f"{path}: assignment summary drift",
    )
    return {item["role_id"]: item for item in value["assignments"]}


def _validate_assigned_actor(
    actor: dict[str, Any],
    *,
    role_id: str,
    assignments: dict[str, dict[str, Any]],
    register: dict[str, Any],
    context: str,
) -> None:
    require(
        register["record_state"] == "submitted"
        and register["summary"]["assignment_complete"] is True,
        f"{context}: submitted complete reviewer assignment register required",
    )
    assignment = assignments[role_id]
    require(
        actor["role_id"] == role_id,
        f"{context}: reviewer role mismatch",
    )
    require(
        actor["actor_id"] == assignment["assignee_id"]
        and actor["organization_or_team"]
        == assignment["organization_or_team"],
        f"{context}: actor does not match assigned reviewer",
    )
    require(
        actor["assignment_register_revision"]
        == register["record_revision"],
        f"{context}: assignment revision mismatch",
    )
    require(
        actor["competence_evidence_refs"]
        == assignment["competence_evidence_refs"],
        f"{context}: competence evidence differs from assignment",
    )
    require(
        actor["human_attested"] is True,
        f"{context}: human attestation required",
    )
    require(
        not AUTOMATION_ACTOR.search(actor["actor_id"]),
        f"{context}: automation cannot act as a human reviewer",
    )


def load_candidate_registry(
    path: Path = CANDIDATE_REGISTRY,
) -> tuple[
    dict[str, Any],
    dict[str, tuple[dict[str, Any], dict[str, Any]]],
]:
    value = load_json(path)
    require(
        value.get("schema_version")
        == "myactuator-plant-spec-candidate-registry/1"
        and value.get("artifact_id")
        == "myactuator-plant-spec-candidate-registry",
        f"{path}: candidate registry identity drift",
    )
    validate_digest(value, str(path))
    require(
        value["summary"]["candidate_count"] == 531
        and len(value["model_tables"]) == 44,
        f"{path}: candidate/model count drift",
    )
    index: dict[
        str, tuple[dict[str, Any], dict[str, Any]]
    ] = {}
    for table in value["model_tables"]:
        for candidate in table["candidates"]:
            identifier = candidate["candidate_id"]
            require(
                identifier not in index,
                f"{path}: duplicate candidate {identifier}",
            )
            index[identifier] = (table, candidate)
    require(len(index) == 531, f"{path}: candidate index drift")
    return value, index


def _target_definition(
    target: dict[str, Any],
    *,
    context: str,
) -> tuple[str, str]:
    field_id = f"{target['domain']}.{target['name']}"
    definitions = {
        **PARAMETER_FIELDS,
        **ENVELOPE_FIELDS,
    }
    unit = definitions.get(field_id)
    require(unit is not None, f"{context}: unknown target {field_id}")
    kind = (
        "operating_envelope"
        if field_id in ENVELOPE_FIELDS
        else "parameter"
    )
    require(
        target["requirement_kind"] == kind
        and target["canonical_unit"] == unit,
        f"{context}: target kind or canonical unit drift",
    )
    return field_id, kind


def _validate_observation(
    observation: dict[str, Any],
    *,
    candidate: dict[str, Any],
    selected_indices: list[int],
    canonical_unit: str,
    expected_shape: str,
    context: str,
) -> None:
    require(
        observation["shape"] == expected_shape,
        f"{context}: target requires {expected_shape} observation",
    )
    numbers = candidate["parse"]["numbers"]
    require(
        selected_indices == sorted(selected_indices)
        and len(selected_indices) == (1 if expected_shape == "scalar" else 2)
        and all(index < len(numbers) for index in selected_indices),
        f"{context}: invalid selected source-number indices",
    )
    require(
        observation["source_unit"] == candidate["source"]["unit_text"],
        f"{context}: source unit must preserve candidate text",
    )
    require(
        observation["normalized_unit"] == canonical_unit,
        f"{context}: normalized unit is not canonical",
    )
    conversion = observation["conversion"]
    scale = _finite(conversion["scale"], f"{context}/scale")
    offset = _finite(conversion["offset"], f"{context}/offset")
    require(scale != 0.0, f"{context}: zero conversion scale")
    if conversion["kind"] == "identity":
        require(
            scale == 1.0
            and offset == 0.0
            and conversion["expression"] is None
            and observation["source_unit"] == canonical_unit,
            f"{context}: invalid identity conversion",
        )
    else:
        require(
            conversion["expression"] is not None,
            f"{context}: non-identity conversion expression required",
        )
    if expected_shape == "scalar":
        source = _finite(
            observation["source_value"],
            f"{context}/source_value",
        )
        require(
            _close(source, float(numbers[selected_indices[0]])),
            f"{context}: selected candidate value mismatch",
        )
        normalized = _finite(
            observation["normalized_value"],
            f"{context}/normalized_value",
        )
        if conversion["kind"] != "reviewed_derivation":
            require(
                _close(normalized, source * scale + offset),
                f"{context}: normalized scalar conversion mismatch",
            )
    else:
        source_minimum = _finite(
            observation["source_minimum"],
            f"{context}/source_minimum",
        )
        source_maximum = _finite(
            observation["source_maximum"],
            f"{context}/source_maximum",
        )
        selected = sorted(float(numbers[index]) for index in selected_indices)
        require(
            _close(source_minimum, selected[0])
            and _close(source_maximum, selected[1])
            and source_minimum <= source_maximum,
            f"{context}: selected candidate range mismatch",
        )
        normalized_minimum = _finite(
            observation["normalized_minimum"],
            f"{context}/normalized_minimum",
        )
        normalized_maximum = _finite(
            observation["normalized_maximum"],
            f"{context}/normalized_maximum",
        )
        require(
            normalized_minimum <= normalized_maximum,
            f"{context}: inverted normalized range",
        )
        if conversion["kind"] != "reviewed_derivation":
            converted = sorted(
                (
                    source_minimum * scale + offset,
                    source_maximum * scale + offset,
                )
            )
            require(
                _close(normalized_minimum, converted[0])
                and _close(normalized_maximum, converted[1]),
                f"{context}: normalized range conversion mismatch",
            )


def validate_submission(
    value: dict[str, Any],
    *,
    path: Path,
    candidate_registry_sha256: str,
    candidate_index: dict[
        str, tuple[dict[str, Any], dict[str, Any]]
    ],
    assignment_register: dict[str, Any],
    assignments: dict[str, dict[str, Any]],
    require_canonical_file: bool = True,
) -> None:
    context = str(path)
    schema_validate(value, load_json(SUBMISSION_SCHEMA), context=context)
    validate_digest(value, context)
    require(
        value["submission_id"] == expected_submission_id(value),
        f"{context}: stable submission identity drift",
    )
    if require_canonical_file:
        require(
            path.stem == value["submission_id"],
            f"{context}: filename must equal submission_id",
        )
        require(
            path.read_text(encoding="utf-8") == canonical_json(value),
            f"{context}: submission JSON is not canonical",
        )
    _timestamp(value["submitted_at_utc"], context)
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False,
        f"{context}: submission grants authority",
    )
    subject = value["subject"]
    require(
        subject["candidate_registry_sha256"]
        == candidate_registry_sha256,
        f"{context}: candidate registry hash drift",
    )
    indexed = candidate_index.get(subject["candidate_id"])
    require(indexed is not None, f"{context}: unknown candidate")
    table, candidate = indexed
    require(
        subject["candidate_sha256"]
        == sha_bytes(canonical_bytes(candidate)),
        f"{context}: candidate hash drift",
    )
    require(
        subject["table_id"] == table["table_id"]
        and subject["model_key"] == table["model_identity"]["model_key"],
        f"{context}: candidate table/model binding drift",
    )
    _validate_assigned_actor(
        value["extractor"],
        role_id=EXTRACTOR_ROLE,
        assignments=assignments,
        register=assignment_register,
        context=context,
    )
    proposal = value["proposal"]
    disposition = proposal["requested_disposition"]
    if disposition != "accept_source_fact":
        require(
            proposal["fact"] is None,
            f"{context}: reject/defer cannot contain a fact",
        )
        return
    fact = proposal["fact"]
    require(fact is not None, f"{context}: acceptance fact missing")
    field_id, target_kind = _target_definition(
        fact["target"], context=context
    )
    mapping = candidate["mapping"]
    if fact["mapping_action"] == "accept_suggested_target":
        require(
            mapping["target_field_id"] == field_id
            and mapping["status"]
            != "not_mappable_to_current_plant_contract",
            f"{context}: suggested target does not match candidate",
        )
    else:
        require(
            bool(proposal["rationale"])
            and (
                mapping["target_field_id"] != field_id
                or mapping["status"]
                == "not_mappable_to_current_plant_contract"
            ),
            f"{context}: remap must identify and justify a changed target",
        )
    resolutions = proposal["blocker_resolutions"]
    resolution_names = [item["blocker"] for item in resolutions]
    require(
        len(resolution_names) == len(set(resolution_names)),
        f"{context}: duplicate blocker resolution",
    )
    require(
        set(mapping["blockers"]).issubset(resolution_names),
        f"{context}: every candidate mapping blocker requires resolution",
    )
    interpretation = fact["source_interpretation"]
    parse = candidate["parse"]
    require(
        parse["qualifier"] is None
        or interpretation["qualifier_resolution"] is not None,
        f"{context}: source qualifier remains unresolved",
    )
    require(
        parse["annotation"] is None
        or interpretation["annotation_resolution"] is not None,
        f"{context}: source annotation remains unresolved",
    )
    require(
        parse["kind"] != "alternatives"
        or interpretation["alternative_resolution"] is not None,
        f"{context}: source alternatives remain unresolved",
    )
    _validate_observation(
        fact["observation"],
        candidate=candidate,
        selected_indices=interpretation["selected_number_indices"],
        canonical_unit=fact["target"]["canonical_unit"],
        expected_shape=(
            "scalar" if target_kind == "parameter" else "range"
        ),
        context=context,
    )
    uncertainty = fact["uncertainty"]
    lower = _finite(uncertainty["lower"], f"{context}/uncertainty/lower")
    upper = _finite(uncertainty["upper"], f"{context}/uncertainty/upper")
    require(
        lower <= upper
        and uncertainty["unit"] == fact["target"]["canonical_unit"],
        f"{context}: uncertainty must be ordered in canonical units",
    )
    condition = fact["operating_condition"]
    for key in ("supply_voltage_v", "ambient_temperature_k"):
        if condition[key] is not None:
            _finite(condition[key], f"{context}/{key}")


def validate_event(
    value: dict[str, Any],
    *,
    path: Path,
    submissions: dict[str, dict[str, Any]],
    candidate_index: dict[
        str, tuple[dict[str, Any], dict[str, Any]]
    ],
    assignment_register: dict[str, Any],
    assignments: dict[str, dict[str, Any]],
    require_canonical_file: bool = True,
) -> None:
    context = str(path)
    schema_validate(value, load_json(EVENT_SCHEMA), context=context)
    validate_digest(value, context)
    require(
        value["event_id"] == expected_event_id(value),
        f"{context}: stable event identity drift",
    )
    if require_canonical_file:
        require(
            path.stem == value["event_id"],
            f"{context}: filename must equal event_id",
        )
        require(
            path.read_text(encoding="utf-8") == canonical_json(value),
            f"{context}: event JSON is not canonical",
        )
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False,
        f"{context}: event grants authority",
    )
    reviewed_at = _timestamp(
        value["reviewer"]["reviewed_at_utc"], context
    )
    _validate_assigned_actor(
        value["reviewer"],
        role_id=REVIEWER_ROLE,
        assignments=assignments,
        register=assignment_register,
        context=context,
    )
    require(
        value["reviewer"]["independence_attested"] is True,
        f"{context}: reviewer independence attestation required",
    )
    subject = value["subject"]
    submission = submissions.get(subject["submission_id"])
    require(submission is not None, f"{context}: unknown submission")
    require(
        subject["submission_sha256"]
        == sha_bytes(canonical_bytes(submission)),
        f"{context}: submission hash drift",
    )
    require(
        subject["candidate_id"] == submission["subject"]["candidate_id"]
        and subject["candidate_sha256"]
        == submission["subject"]["candidate_sha256"]
        and subject["candidate_id"] in candidate_index,
        f"{context}: event candidate binding drift",
    )
    require(
        reviewed_at
        > _timestamp(submission["submitted_at_utc"], context),
        f"{context}: review must occur after submission",
    )
    require(
        value["reviewer"]["actor_id"]
        != submission["extractor"]["actor_id"],
        f"{context}: reviewer must differ from extractor",
    )
    replacement_id = subject["superseding_submission_id"]
    replacement_hash = subject["superseding_submission_sha256"]
    event_type = value["event_type"]
    if event_type == "supersede":
        replacement = submissions.get(replacement_id)
        require(
            replacement is not None and replacement_hash is not None,
            f"{context}: superseding submission missing",
        )
        require(
            replacement_hash == sha_bytes(canonical_bytes(replacement)),
            f"{context}: superseding submission hash drift",
        )
        require(
            replacement["supersedes_submission_id"]
            == submission["submission_id"]
            and replacement["subject"]["candidate_id"]
            == submission["subject"]["candidate_id"],
            f"{context}: replacement lineage/candidate mismatch",
        )
        require(
            replacement["proposal"]["requested_disposition"]
            == "accept_source_fact",
            f"{context}: superseding submission must propose acceptance",
        )
        require(
            reviewed_at
            > _timestamp(replacement["submitted_at_utc"], context),
            f"{context}: review must occur after replacement submission",
        )
        require(
            value["reviewer"]["actor_id"]
            != replacement["extractor"]["actor_id"],
            f"{context}: reviewer must differ from replacement extractor",
        )
    else:
        require(
            replacement_id is None and replacement_hash is None,
            f"{context}: non-supersede event contains replacement",
        )


def _expected_transition(event_type: str) -> dict[str, Any]:
    return {
        "accept": {
            "prior_state": "submitted",
            "next_state": "accepted",
            "superseding_prior_state": None,
            "superseding_next_state": None,
        },
        "reject": {
            "prior_state": "submitted",
            "next_state": "rejected",
            "superseding_prior_state": None,
            "superseding_next_state": None,
        },
        "defer": {
            "prior_state": "submitted",
            "next_state": "deferred",
            "superseding_prior_state": None,
            "superseding_next_state": None,
        },
        "revoke": {
            "prior_state": "accepted",
            "next_state": "revoked",
            "superseding_prior_state": None,
            "superseding_next_state": None,
        },
        "supersede": {
            "prior_state": "accepted",
            "next_state": "superseded",
            "superseding_prior_state": "submitted",
            "superseding_next_state": "accepted",
        },
    }[event_type]


def replay(
    submissions: dict[str, dict[str, Any]],
    events: list[dict[str, Any]],
) -> tuple[
    dict[str, str],
    dict[str, str | None],
    dict[str, str | None],
    dict[str, str],
]:
    states = {identifier: "submitted" for identifier in submissions}
    last_events: dict[str, str | None] = {
        identifier: None for identifier in submissions
    }
    superseded_by: dict[str, str | None] = {
        identifier: None for identifier in submissions
    }
    accepting_events: dict[str, str] = {}
    expected_sequence = list(range(1, len(events) + 1))
    require(
        [event["sequence"] for event in events] == expected_sequence,
        "event sequences must be unique, ordered, and contiguous from one",
    )
    last_time: datetime | None = None
    disposition_by_event = {
        "accept": "accept_source_fact",
        "reject": "reject_candidate",
        "defer": "defer_candidate",
    }
    for event in events:
        identifier = event["subject"]["submission_id"]
        event_type = event["event_type"]
        require(
            event["transition"] == _expected_transition(event_type),
            f"{event['event_id']}: lifecycle transition drift",
        )
        event_time = _timestamp(
            event["reviewer"]["reviewed_at_utc"], event["event_id"]
        )
        require(
            last_time is None or event_time > last_time,
            f"{event['event_id']}: event timestamps must strictly increase",
        )
        last_time = event_time
        if event_type in disposition_by_event:
            require(
                states[identifier] == "submitted"
                and submissions[identifier]["proposal"][
                    "requested_disposition"
                ]
                == disposition_by_event[event_type],
                f"{event['event_id']}: disposition/state mismatch",
            )
            states[identifier] = event["transition"]["next_state"]
            if event_type == "accept":
                accepting_events[identifier] = event["event_id"]
        elif event_type == "revoke":
            require(
                states[identifier] == "accepted",
                f"{event['event_id']}: only accepted submission can revoke",
            )
            states[identifier] = "revoked"
            accepting_events.pop(identifier, None)
        else:
            replacement_id = event["subject"][
                "superseding_submission_id"
            ]
            require(
                states[identifier] == "accepted"
                and replacement_id is not None
                and states[replacement_id] == "submitted",
                f"{event['event_id']}: supersede states are not atomic",
            )
            states[identifier] = "superseded"
            states[replacement_id] = "accepted"
            superseded_by[identifier] = replacement_id
            accepting_events.pop(identifier, None)
            accepting_events[replacement_id] = event["event_id"]
            last_events[replacement_id] = event["event_id"]
        last_events[identifier] = event["event_id"]
        active_candidates: set[str] = set()
        active_targets: set[tuple[str, str]] = set()
        for active_id, state in states.items():
            if state != "accepted":
                continue
            submission = submissions[active_id]
            candidate_id = submission["subject"]["candidate_id"]
            require(
                candidate_id not in active_candidates,
                f"{event['event_id']}: multiple active facts for candidate",
            )
            active_candidates.add(candidate_id)
            fact = submission["proposal"]["fact"]
            require(fact is not None, "accepted submission has no fact")
            field_id = (
                f"{fact['target']['domain']}.{fact['target']['name']}"
            )
            target_key = (submission["subject"]["model_key"], field_id)
            require(
                target_key not in active_targets,
                f"{event['event_id']}: conflicting active model target",
            )
            active_targets.add(target_key)
    return states, last_events, superseded_by, accepting_events


def _agent_urn(actor: dict[str, Any]) -> str:
    payload = {
        "actor_id": actor["actor_id"],
        "organization_or_team": actor["organization_or_team"],
        "role_id": actor["role_id"],
    }
    return "urn:myactuator:agent:" + sha_bytes(canonical_bytes(payload))[:20]


def materialize_fact(
    *,
    submission: dict[str, Any],
    event: dict[str, Any],
    table: dict[str, Any],
    candidate: dict[str, Any],
    candidate_registry_sha256: str,
    registry_generation_sha256: str,
) -> dict[str, Any]:
    proposal = submission["proposal"]["fact"]
    require(proposal is not None, "cannot materialize null fact proposal")
    extractor = submission["extractor"]
    reviewer = event["reviewer"]
    value: dict[str, Any] = {
        "schema_version": "myactuator-plant-source-fact/2",
        "fact_id": "plantfact-" + "0" * 20,
        "model_identity": copy.deepcopy(table["model_identity"]),
        "target": copy.deepcopy(proposal["target"]),
        "observation": copy.deepcopy(proposal["observation"]),
        "provenance": {
            "candidate_registry_artifact_id": (
                "myactuator-plant-spec-candidate-registry"
            ),
            "candidate_registry_sha256": candidate_registry_sha256,
            "candidate_id": candidate["candidate_id"],
            "candidate_sha256": sha_bytes(canonical_bytes(candidate)),
            "table_id": table["table_id"],
            "document_occurrence_id": table["document_occurrence_id"],
            "file_sha256": table["file_sha256"],
            "pdf_page_index": table["pdf_page_index"],
            "page_text_sha256": table["page_text_sha256"],
            "model_header_text": table["model_header_text"],
            "source_property_id": candidate["source_property_id"],
            "source_label": candidate["source"]["label_text"],
            "source_unit": candidate["source"]["unit_text"],
            "source_value": candidate["source"]["value_text"],
            "label_bbox": candidate["source"]["label_bbox"],
            "unit_bbox": candidate["source"]["unit_bbox"],
            "value_bbox": candidate["source"]["value_bbox"],
        },
        "evidence": {
            "class": proposal["evidence_class"],
            "extraction_method": proposal["extraction_method"],
            "source_interpretation": copy.deepcopy(
                proposal["source_interpretation"]
            ),
            "extractor": {
                "role_id": extractor["role_id"],
                "actor_id": extractor["actor_id"],
                "organization_or_team": extractor[
                    "organization_or_team"
                ],
                "assignment_register_revision": extractor[
                    "assignment_register_revision"
                ],
                "competence_evidence_refs": extractor[
                    "competence_evidence_refs"
                ],
            },
            "submitted_at_utc": submission["submitted_at_utc"],
            "uncertainty": copy.deepcopy(proposal["uncertainty"]),
            "operating_condition": copy.deepcopy(
                proposal["operating_condition"]
            ),
        },
        "review": {
            "status": "accepted",
            "candidate_decision_registry_generation_sha256": (
                registry_generation_sha256
            ),
            "submission_id": submission["submission_id"],
            "submission_sha256": sha_bytes(canonical_bytes(submission)),
            "acceptance_event_id": event["event_id"],
            "acceptance_event_sha256": sha_bytes(canonical_bytes(event)),
            "reviewer": {
                "role_id": reviewer["role_id"],
                "actor_id": reviewer["actor_id"],
                "organization_or_team": reviewer[
                    "organization_or_team"
                ],
                "assignment_register_revision": reviewer[
                    "assignment_register_revision"
                ],
                "competence_evidence_refs": reviewer[
                    "competence_evidence_refs"
                ],
            },
            "reviewed_at_utc": reviewer["reviewed_at_utc"],
            "decision_assertion": reviewer["decision_assertion"],
            "signature_evidence_refs": reviewer[
                "signature_evidence_refs"
            ],
        },
        "prov": {
            "entity_urn": "pending",
            "was_derived_from_urns": [
                "urn:myactuator:plant-spec-candidate:"
                + candidate["candidate_id"],
                "urn:sha256:" + table["file_sha256"],
            ],
            "generation_activity_urn": (
                "urn:myactuator:activity:plant-fact-review:"
                + event["event_id"]
            ),
            "extractor_agent_urn": _agent_urn(extractor),
            "reviewer_agent_urn": _agent_urn(reviewer),
            "generated_at_utc": reviewer["reviewed_at_utc"],
        },
        "support_granted": False,
        "physical_motion_authority": False,
    }
    value["fact_id"] = expected_fact_id(value)
    value["prov"]["entity_urn"] = (
        "urn:myactuator:plant-fact:" + value["fact_id"]
    )
    schema_validate(value, load_json(FACT_SCHEMA), context=value["fact_id"])
    require(
        value["fact_id"] == expected_fact_id(value),
        f"{value['fact_id']}: materialized fact identity drift",
    )
    return value


def _load_records(directory: Path) -> list[tuple[Path, dict[str, Any]]]:
    if not directory.exists():
        return []
    require(directory.is_dir(), f"{directory}: expected directory")
    unexpected = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix != ".json"
    ]
    require(
        not unexpected,
        f"{directory}: only JSON decision records are permitted",
    )
    return [
        (path, load_json(path))
        for path in sorted(directory.glob("*.json"))
    ]


def build(
    *,
    candidate_registry_path: Path = CANDIDATE_REGISTRY,
    assignment_path: Path = ASSIGNMENTS,
    submission_directory: Path = SUBMISSION_DIRECTORY,
    event_directory: Path = EVENT_DIRECTORY,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    candidate_registry, candidate_index = load_candidate_registry(
        candidate_registry_path
    )
    candidate_registry_sha256 = sha_file(candidate_registry_path)
    assignment_register = load_json(assignment_path)
    assignments = _validate_assignment_register(
        assignment_register, path=assignment_path
    )
    submission_records = _load_records(submission_directory)
    submissions: dict[str, dict[str, Any]] = {}
    submission_paths: dict[str, Path] = {}
    for path, submission in submission_records:
        validate_submission(
            submission,
            path=path,
            candidate_registry_sha256=candidate_registry_sha256,
            candidate_index=candidate_index,
            assignment_register=assignment_register,
            assignments=assignments,
        )
        identifier = submission["submission_id"]
        require(
            identifier not in submissions,
            f"{path}: duplicate submission ID",
        )
        submissions[identifier] = submission
        submission_paths[identifier] = path
    for identifier, submission in submissions.items():
        parent = submission["supersedes_submission_id"]
        require(
            parent is None or parent in submissions,
            f"{identifier}: unknown superseded submission",
        )
        require(parent != identifier, f"{identifier}: self-supersession")

    event_records = _load_records(event_directory)
    events: list[dict[str, Any]] = []
    event_paths: dict[str, Path] = {}
    for path, event in event_records:
        validate_event(
            event,
            path=path,
            submissions=submissions,
            candidate_index=candidate_index,
            assignment_register=assignment_register,
            assignments=assignments,
        )
        require(
            event["event_id"] not in event_paths,
            f"{path}: duplicate event ID",
        )
        events.append(event)
        event_paths[event["event_id"]] = path
    events.sort(key=lambda item: item["sequence"])
    states, last_events, superseded_by, accepting_events = replay(
        submissions, events
    )
    event_by_id = {item["event_id"]: item for item in events}

    source_descriptor = {
        "candidate_registry_path": (
            "generated/myactuator/plant/spec_candidates/registry.json"
        ),
        "candidate_registry_sha256": candidate_registry_sha256,
        "candidate_registry_artifact_id": (
            "myactuator-plant-spec-candidate-registry"
        ),
        "reviewer_assignment_path": (
            "assets/myactuator/reviewer_assignments.json"
        ),
        "reviewer_assignment_sha256": sha_file(assignment_path),
        "reviewer_assignment_revision": assignment_register[
            "record_revision"
        ],
        "reviewer_assignment_state": assignment_register["record_state"],
        "submission_schema_sha256": sha_file(SUBMISSION_SCHEMA),
        "event_schema_sha256": sha_file(EVENT_SCHEMA),
        "source_fact_schema_sha256": sha_file(FACT_SCHEMA),
        "generator_sha256": sha_file(Path(__file__).resolve()),
    }
    submission_entries = []
    for identifier in sorted(submissions):
        submission = submissions[identifier]
        proposal = submission["proposal"]
        fact = proposal["fact"]
        submission_entries.append(
            {
                "submission_id": identifier,
                "submission_path": _relative(submission_paths[identifier]),
                "submission_sha256": sha_bytes(
                    canonical_bytes(submission)
                ),
                "candidate_id": submission["subject"]["candidate_id"],
                "candidate_sha256": submission["subject"][
                    "candidate_sha256"
                ],
                "model_key": submission["subject"]["model_key"],
                "target_field_id": (
                    None
                    if fact is None
                    else f"{fact['target']['domain']}."
                    f"{fact['target']['name']}"
                ),
                "requested_disposition": proposal[
                    "requested_disposition"
                ],
                "lifecycle_state": states[identifier],
                "superseded_by_submission_id": superseded_by[identifier],
                "last_event_id": last_events[identifier],
            }
        )
    event_entries = [
        {
            "sequence": event["sequence"],
            "event_id": event["event_id"],
            "event_path": _relative(event_paths[event["event_id"]]),
            "event_sha256": sha_bytes(canonical_bytes(event)),
            "event_type": event["event_type"],
            "submission_id": event["subject"]["submission_id"],
        }
        for event in events
    ]
    # Deliberately excludes generated fact hashes, preventing a digest cycle:
    # facts bind this immutable source/replay generation; the complete registry
    # digest separately binds the resulting fact list and hashes.
    registry_generation_sha256 = sha_bytes(
        canonical_bytes(
            {
                "sources": source_descriptor,
                "submissions": submission_entries,
                "events": event_entries,
            }
        )
    )
    facts: dict[str, dict[str, Any]] = {}
    fact_entries = []
    for identifier in sorted(accepting_events):
        submission = submissions[identifier]
        event = event_by_id[accepting_events[identifier]]
        table, candidate = candidate_index[
            submission["subject"]["candidate_id"]
        ]
        fact = materialize_fact(
            submission=submission,
            event=event,
            table=table,
            candidate=candidate,
            candidate_registry_sha256=candidate_registry_sha256,
            registry_generation_sha256=registry_generation_sha256,
        )
        require(
            fact["fact_id"] not in facts,
            f"{fact['fact_id']}: duplicate materialized fact",
        )
        facts[fact["fact_id"]] = fact
        field_id = f"{fact['target']['domain']}.{fact['target']['name']}"
        fact_entries.append(
            {
                "fact_id": fact["fact_id"],
                "fact_path": (
                    "generated/myactuator/plant/candidate_decisions/"
                    f"source_facts/{fact['fact_id']}.json"
                ),
                "fact_sha256": sha_bytes(canonical_bytes(fact)),
                "candidate_id": fact["provenance"]["candidate_id"],
                "submission_id": identifier,
                "acceptance_event_id": event["event_id"],
                "model_key": fact["model_identity"]["model_key"],
                "target_field_id": field_id,
            }
        )
    fact_entries.sort(key=lambda item: item["fact_id"])
    counts = Counter(states.values())
    assignment_complete = assignment_register["summary"][
        "assignment_complete"
    ]
    blockers = []
    if not assignment_complete:
        blockers.append("reviewer_assignments_incomplete")
    if not facts:
        blockers.append("no_accepted_candidate_decisions")
    value = {
        "schema_version": VERSION,
        "artifact_id": "myactuator-plant-candidate-decision-registry",
        "authority": (
            "independently_reviewed_candidate_fact_materialization_only"
        ),
        "sources": source_descriptor,
        "registry_generation_sha256": registry_generation_sha256,
        "submissions": submission_entries,
        "events": event_entries,
        "active_source_facts": fact_entries,
        "summary": {
            "candidate_count": candidate_registry["summary"][
                "candidate_count"
            ],
            "submission_count": len(submissions),
            "event_count": len(events),
            "submitted_count": counts["submitted"],
            "accepted_count": counts["accepted"],
            "rejected_count": counts["rejected"],
            "deferred_count": counts["deferred"],
            "revoked_count": counts["revoked"],
            "superseded_count": counts["superseded"],
            "active_source_fact_count": len(facts),
            "model_with_active_source_fact_count": len(
                {
                    fact["model_identity"]["model_key"]
                    for fact in facts.values()
                }
            ),
            "reviewer_assignment_complete": assignment_complete,
        },
        "blockers": blockers,
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(value)
    validate_registry(
        value,
        facts=facts,
        candidate_registry_sha256=candidate_registry_sha256,
    )
    return value, facts


def validate_registry(
    value: dict[str, Any],
    *,
    facts: dict[str, dict[str, Any]],
    candidate_registry_sha256: str,
) -> None:
    schema_validate(
        value, load_json(REGISTRY_SCHEMA), context="decision registry"
    )
    validate_digest(value, "decision registry")
    require(
        value["sources"]["candidate_registry_sha256"]
        == candidate_registry_sha256,
        "decision registry candidate source drift",
    )
    require(
        len(value["active_source_facts"]) == len(facts),
        "decision registry fact count drift",
    )
    for entry in value["active_source_facts"]:
        fact = facts.get(entry["fact_id"])
        require(fact is not None, "decision registry references unknown fact")
        schema_validate(
            fact, load_json(FACT_SCHEMA), context=entry["fact_id"]
        )
        require(
            entry["fact_sha256"] == sha_bytes(canonical_bytes(fact))
            and fact["fact_id"] == expected_fact_id(fact)
            and fact["review"][
                "candidate_decision_registry_generation_sha256"
            ]
            == value["registry_generation_sha256"],
            f"{entry['fact_id']}: registry/fact lineage drift",
        )


def expected_files(
    value: dict[str, Any],
    facts: dict[str, dict[str, Any]],
) -> dict[str, str]:
    result = {"registry.json": canonical_json(value)}
    result.update(
        {
            f"source_facts/{identifier}.json": canonical_json(fact)
            for identifier, fact in facts.items()
        }
    )
    return result


def check_outputs(
    value: dict[str, Any],
    facts: dict[str, dict[str, Any]],
    *,
    output_root: Path = OUTPUT_ROOT,
) -> None:
    expected = expected_files(value, facts)
    actual = {
        path.relative_to(output_root).as_posix()
        for path in output_root.rglob("*")
        if path.is_file()
    } if output_root.exists() else set()
    require(
        actual == set(expected),
        f"{output_root}: generated file set drift",
    )
    for relative, content in expected.items():
        path = output_root / relative
        require(
            path.read_text(encoding="utf-8") == content,
            f"{path}: generated content drift",
        )


def write_outputs(
    value: dict[str, Any],
    facts: dict[str, dict[str, Any]],
    *,
    output_root: Path = OUTPUT_ROOT,
) -> None:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=output_root.name + ".",
            dir=output_root.parent,
        )
    )
    backup = output_root.with_name(output_root.name + ".previous")
    try:
        for relative, content in expected_files(value, facts).items():
            path = stage / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        check_outputs(value, facts, output_root=stage)
        require(
            not backup.exists(),
            f"{backup}: stale transaction backup exists",
        )
        if output_root.exists():
            os.replace(output_root, backup)
        try:
            os.replace(stage, output_root)
        except Exception:
            if backup.exists() and not output_root.exists():
                os.replace(backup, output_root)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _validate_one_submission(path: Path) -> None:
    _, candidate_index = load_candidate_registry()
    register = load_json(ASSIGNMENTS)
    assignments = _validate_assignment_register(
        register, path=ASSIGNMENTS
    )
    validate_submission(
        load_json(path),
        path=path,
        candidate_registry_sha256=sha_file(CANDIDATE_REGISTRY),
        candidate_index=candidate_index,
        assignment_register=register,
        assignments=assignments,
    )


def _validate_one_event(path: Path) -> None:
    _, candidate_index = load_candidate_registry()
    register = load_json(ASSIGNMENTS)
    assignments = _validate_assignment_register(
        register, path=ASSIGNMENTS
    )
    submissions = {
        value["submission_id"]: value
        for _, value in _load_records(SUBMISSION_DIRECTORY)
    }
    validate_event(
        load_json(path),
        path=path,
        submissions=submissions,
        candidate_index=candidate_index,
        assignment_register=register,
        assignments=assignments,
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--validate-submission", type=Path)
    mode.add_argument("--validate-event", type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.validate_submission is not None:
            _validate_one_submission(arguments.validate_submission)
            print(f"PASS submission {arguments.validate_submission}")
            return 0
        if arguments.validate_event is not None:
            _validate_one_event(arguments.validate_event)
            print(f"PASS event {arguments.validate_event}")
            return 0
        value, facts = build()
        if arguments.generate:
            write_outputs(value, facts)
            action = "generated"
        else:
            check_outputs(value, facts)
            action = "verified"
        summary = value["summary"]
        print(
            "PASS plant candidate decisions "
            f"{action}: submissions={summary['submission_count']} "
            f"events={summary['event_count']} "
            f"active_facts={summary['active_source_fact_count']} "
            f"digest={value['integrity']['record_sha256']}"
        )
        return 0
    except PlantCandidateDecisionError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
