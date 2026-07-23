"""Canonical, backend-neutral simulation trace interchange.

This module serializes deterministic offline simulation evidence.  It grants
neither product fidelity nor hardware authority.  Session traces retain their
original rolling hash chain; normalized commands, states and dispositions are
derived projections which an independent consumer can recompute.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

from .simulation_session import SimulationSession, TraceEvent


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "schemas/simulation-trace-interchange.schema.json"
ZERO_SHA256 = "0" * 64


class TraceInterchangeError(ValueError):
    """A trace is malformed, inconsistent, promoted, or not reproducible."""


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _plain(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                _plain(value),
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise TraceInterchangeError("trace contains a noncanonical value") from error


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str:
    return sha256(canonical_json(value))


def _schema(path: Path = DEFAULT_SCHEMA) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TraceInterchangeError(f"cannot load trace schema: {error}") from error
    if not isinstance(value, dict):
        raise TraceInterchangeError("trace schema root is not an object")
    Draft202012Validator.check_schema(value)
    return value


def chain_events(
    records: Sequence[tuple[int, str, Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Build a dense rolling-hash event chain from tick/kind/payload records."""

    result: list[dict[str, Any]] = []
    previous = ZERO_SHA256
    previous_tick = 0
    for sequence, (tick, kind, payload) in enumerate(records, 1):
        if (
            not isinstance(tick, int)
            or isinstance(tick, bool)
            or tick < previous_tick
        ):
            raise TraceInterchangeError("event ticks must be monotonic uint64")
        if not isinstance(kind, str) or not kind:
            raise TraceInterchangeError("event kind is empty")
        body = {
            "sequence": sequence,
            "tick": tick,
            "kind": kind,
            "payload": _plain(dict(payload)),
            "previous_sha256": previous,
        }
        digest = _digest(body)
        result.append({**body, "record_sha256": digest})
        previous = digest
        previous_tick = tick
    if not result:
        raise TraceInterchangeError("trace must contain at least one event")
    return result


def _event_dict(event: TraceEvent | Mapping[str, Any]) -> dict[str, Any]:
    value = _plain(event)
    if not isinstance(value, dict):
        raise TraceInterchangeError("trace event is not an object")
    return value


def _normalize(events: Sequence[Mapping[str, Any]]) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    commands: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []
    for event in events:
        kind = event["kind"]
        payload = event["payload"]
        if kind == "command-accepted":
            command = payload["command"]
            commands.append(
                {
                    "event_sequence": event["sequence"],
                    "sequence": command["sequence"],
                    "tick": command["issued_tick"],
                    "deadline_tick": command["deadline_tick"],
                    "actuator_id": command["actuator_id"],
                    "mode": command["mode"],
                    "target_si": command["target_si"],
                    "target_unit": command["target_unit"],
                    "maximum_absolute_target_si": command[
                        "maximum_absolute_target_si"
                    ],
                }
            )
            dispositions.append(
                {
                    "event_sequence": event["sequence"],
                    "tick": event["tick"],
                    "command_sequence": command["sequence"],
                    "result": "accepted",
                    "reason": "command-accepted",
                }
            )
        elif kind == "command-denied":
            dispositions.append(
                {
                    "event_sequence": event["sequence"],
                    "tick": event["tick"],
                    "command_sequence": payload["sequence"],
                    "result": "denied",
                    "reason": payload.get("reason", "scheduled-fault"),
                }
            )
        elif kind == "state-read":
            state = payload["state"]
            engine = state["engine_state"]
            states.append(
                {
                    "event_sequence": event["sequence"],
                    "tick": state["tick"],
                    "sample_tick": engine["sample_tick"],
                    "actuator_id": engine["actuator_id"],
                    "position_rad": engine["position_rad"],
                    "velocity_rad_s": engine["velocity_rad_s"],
                    "effort_nm": None,
                    "qaxis_current_a": engine["qaxis_current_a"],
                    "temperature_k": engine["temperature_k"],
                    "validity": engine["validity"],
                    "source": engine["source"],
                    "fault_code": engine["fault_code"],
                    "provenance_refs": engine["provenance_refs"],
                }
            )
        elif kind == "joint-state-read":
            states.append(
                {
                    "event_sequence": event["sequence"],
                    "tick": event["tick"],
                    **copy.deepcopy(payload["state"]),
                }
            )
    return commands, states, dispositions


def build_trace(
    *,
    producer: Mapping[str, Any],
    subject: Mapping[str, Any],
    backend: Mapping[str, Any],
    source_generations: Mapping[str, Any],
    tick_period_ns: int,
    seed: int,
    reset_generation: int,
    initial_state_sha256: str,
    events: Sequence[TraceEvent | Mapping[str, Any]],
) -> dict[str, Any]:
    """Create and independently validate one complete interchange document."""

    event_values = [_event_dict(event) for event in events]
    commands, states, dispositions = _normalize(event_values)
    accepted = sum(item["result"] == "accepted" for item in dispositions)
    denied = sum(item["result"] == "denied" for item in dispositions)
    body: dict[str, Any] = {
        "schema_version": "simulation-trace-interchange/1",
        "trace_id": "simtrace-" + "0" * 24,
        "authority": "offline_backend_interchange_only",
        "producer": _plain(producer),
        "subject": _plain(subject),
        "backend": _plain(backend),
        "source_generations": _plain(source_generations),
        "clock": {
            "timebase": "integer_virtual_tick",
            "tick_period_ns": tick_period_ns,
            "initial_tick": 0,
            "final_tick": event_values[-1]["tick"],
        },
        "reset": {
            "seed": seed,
            "reset_generation": reset_generation,
            "initial_state_sha256": initial_state_sha256,
        },
        "commands": commands,
        "states": states,
        "dispositions": dispositions,
        "events": event_values,
        "summary": {
            "command_count": len(commands),
            "state_count": len(states),
            "disposition_count": len(dispositions),
            "event_count": len(event_values),
            "accepted_command_count": accepted,
            "denied_command_count": denied,
        },
        "claims": {
            "generic_fixture_only": subject["kind"]
            == "generic_rigid_body_fixture",
            "canonical_dropbear": subject["kind"]
            == "canonical_dropbear_scene",
            "exact_model_fidelity": bool(backend["exact_model_fidelity"]),
            "physically_validated": bool(backend["physically_validated"]),
            "support_granted": False,
            "physical_motion_authority": False,
            "physical_io": False,
        },
        "integrity": {
            "event_chain_sha256": event_values[-1]["record_sha256"],
            "record_sha256": ZERO_SHA256,
        },
    }
    trace_id_payload = copy.deepcopy(body)
    trace_id_payload["trace_id"] = "simtrace-" + "0" * 24
    trace_id_payload["integrity"]["record_sha256"] = ZERO_SHA256
    body["trace_id"] = "simtrace-" + _digest(trace_id_payload)[:24]
    digest_payload = copy.deepcopy(body)
    digest_payload["integrity"]["record_sha256"] = ZERO_SHA256
    body["integrity"]["record_sha256"] = _digest(digest_payload)
    validate_trace(body)
    return body


def build_session_trace(
    session: SimulationSession,
    *,
    fixture_id: str,
    tick_period_ns: int,
    producer_source_sha256: str,
    producer_version: str = "1",
) -> dict[str, Any]:
    """Export a common SimulationSession without widening its evidence claims."""

    events = [_event_dict(event) for event in session.trace()]
    if not events or events[0]["kind"] != "configured":
        raise TraceInterchangeError("session trace does not begin with configured")
    configured = events[0]["payload"]
    selection = configured["selection"]
    engine = configured["engine"]
    context = session.trace_context()
    return build_trace(
        producer={
            "name": "myactuator-trace-exporter",
            "version": producer_version,
            "source_sha256": producer_source_sha256,
        },
        subject={
            "kind": "catalog_model_selection",
            "subject_id": "subject-" + selection["model_key"].removeprefix("model-"),
            "fixture_id": fixture_id,
            "model_key": selection["model_key"],
            "series": selection["series"],
            "model": selection["model"],
            "configuration_id": selection["configuration_id"],
            "evidence_class": engine["evidence_class"],
        },
        backend={
            "backend_id": engine["backend_id"],
            "backend_kind": engine["backend_kind"],
            "engine_name": engine["backend_id"],
            "engine_version": producer_version,
            "engine_binary_sha256": None,
            "use_case": engine["use_case"],
            "deterministic_virtual_time": engine[
                "deterministic_virtual_time"
            ],
            "command_capable": engine["command_capable"],
            "exact_model_fidelity": engine["exact_model_fidelity"],
            "physically_validated": engine["physically_validated"],
            "physical_io": False,
        },
        source_generations={
            "catalog_sha256": context["catalog_generation_sha256"],
            "source_registry_sha256": context[
                "source_registry_generation_sha256"
            ],
            "graph_registry_sha256": context[
                "graph_registry_generation_sha256"
            ],
        },
        tick_period_ns=tick_period_ns,
        seed=configured["seed"],
        reset_generation=configured["reset_generation"],
        initial_state_sha256=configured["initial_state_sha256"],
        events=events,
    )


def validate_trace(
    value: Mapping[str, Any],
    *,
    schema_path: Path = DEFAULT_SCHEMA,
) -> None:
    """Validate schema, event chain, projections, identity, counts and claims."""

    document = _plain(value)
    if not isinstance(document, dict):
        raise TraceInterchangeError("trace root is not an object")
    errors = sorted(
        Draft202012Validator(_schema(schema_path)).iter_errors(document),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise TraceInterchangeError(
            "trace schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    events = document["events"]
    previous = ZERO_SHA256
    previous_tick = 0
    for expected_sequence, event in enumerate(events, 1):
        if event["sequence"] != expected_sequence:
            raise TraceInterchangeError("event sequence is not dense")
        if event["tick"] < previous_tick:
            raise TraceInterchangeError("event ticks are not monotonic")
        if event["previous_sha256"] != previous:
            raise TraceInterchangeError("event predecessor hash mismatch")
        body = {key: value for key, value in event.items() if key != "record_sha256"}
        if event["record_sha256"] != _digest(body):
            raise TraceInterchangeError("event record hash mismatch")
        previous = event["record_sha256"]
        previous_tick = event["tick"]
    if document["integrity"]["event_chain_sha256"] != previous:
        raise TraceInterchangeError("terminal event-chain hash mismatch")
    if document["clock"]["final_tick"] != events[-1]["tick"]:
        raise TraceInterchangeError("final tick does not match event stream")

    commands, states, dispositions = _normalize(events)
    if document["commands"] != commands:
        raise TraceInterchangeError("normalized command projection mismatch")
    if document["states"] != states:
        raise TraceInterchangeError("normalized state projection mismatch")
    if document["dispositions"] != dispositions:
        raise TraceInterchangeError("normalized disposition projection mismatch")
    summary = document["summary"]
    expected_summary = {
        "command_count": len(commands),
        "state_count": len(states),
        "disposition_count": len(dispositions),
        "event_count": len(events),
        "accepted_command_count": sum(
            item["result"] == "accepted" for item in dispositions
        ),
        "denied_command_count": sum(
            item["result"] == "denied" for item in dispositions
        ),
    }
    if summary != expected_summary:
        raise TraceInterchangeError("trace summary mismatch")
    for item in states:
        for key in (
            "position_rad",
            "velocity_rad_s",
            "effort_nm",
            "qaxis_current_a",
            "temperature_k",
        ):
            number = item[key]
            if number is not None and not math.isfinite(number):
                raise TraceInterchangeError("state contains nonfinite value")
        if item["sample_tick"] > item["tick"]:
            raise TraceInterchangeError("state sample is from the future")
        if item["validity"] in {"missing", "faulted"} and any(
            item[key] is not None
            for key in (
                "position_rad",
                "velocity_rad_s",
                "effort_nm",
                "qaxis_current_a",
                "temperature_k",
            )
        ):
            raise TraceInterchangeError("invalid state carries numeric values")

    trace_id_payload = copy.deepcopy(document)
    trace_id_payload["trace_id"] = "simtrace-" + "0" * 24
    trace_id_payload["integrity"]["record_sha256"] = ZERO_SHA256
    if document["trace_id"] != "simtrace-" + _digest(trace_id_payload)[:24]:
        raise TraceInterchangeError("trace ID mismatch")
    digest_payload = copy.deepcopy(document)
    digest_payload["integrity"]["record_sha256"] = ZERO_SHA256
    if document["integrity"]["record_sha256"] != _digest(digest_payload):
        raise TraceInterchangeError("trace record hash mismatch")
    subject_kind = document["subject"]["kind"]
    generic = subject_kind == "generic_rigid_body_fixture"
    canonical_dropbear = subject_kind == "canonical_dropbear_scene"
    if document["claims"]["generic_fixture_only"] is not generic:
        raise TraceInterchangeError("generic-fixture claim disagrees with subject")
    if document["claims"]["canonical_dropbear"] is not canonical_dropbear:
        raise TraceInterchangeError("canonical-scene claim disagrees with subject")
    if (
        document["claims"]["exact_model_fidelity"]
        is not document["backend"]["exact_model_fidelity"]
        or document["claims"]["physically_validated"]
        is not document["backend"]["physically_validated"]
    ):
        raise TraceInterchangeError("trace/backend fidelity claims disagree")
    if document["claims"]["physically_validated"] and not document["claims"][
        "exact_model_fidelity"
    ]:
        raise TraceInterchangeError("physical validation requires exact fidelity")
    if generic and (
        document["claims"]["canonical_dropbear"]
        or document["claims"]["exact_model_fidelity"]
        or document["claims"]["physically_validated"]
    ):
        raise TraceInterchangeError("generic fixture contains a fidelity promotion")
    if canonical_dropbear:
        if not document["claims"]["exact_model_fidelity"]:
            raise TraceInterchangeError(
                "canonical Dropbear trace requires exact-model fidelity"
            )
        if any(
            document["source_generations"][key] is None
            for key in (
                "catalog_sha256",
                "source_registry_sha256",
                "graph_registry_sha256",
            )
        ):
            raise TraceInterchangeError(
                "canonical Dropbear trace lacks admitted source generations"
            )


def compare_inputs_and_dispositions(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> None:
    """Require exact canonical input and disposition equality across backends."""

    validate_trace(first)
    validate_trace(second)
    first_projection = {
        "clock": first["clock"],
        "reset": first["reset"],
        "commands": first["commands"],
        "dispositions": first["dispositions"],
    }
    second_projection = {
        "clock": second["clock"],
        "reset": second["reset"],
        "commands": second["commands"],
        "dispositions": second["dispositions"],
    }
    if canonical_json(first_projection) != canonical_json(second_projection):
        raise TraceInterchangeError(
            "backend command/reset/disposition projections differ"
        )


def write_trace(path: Path, value: Mapping[str, Any]) -> None:
    validate_trace(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{path.name}.",
        dir=path.parent,
        delete=False,
    ) as temporary:
        temporary.write(canonical_json(value))
        temporary.flush()
        os.fsync(temporary.fileno())
        staged = Path(temporary.name)
    staged.replace(path)


def load_trace(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TraceInterchangeError(f"cannot load trace: {error}") from error
    validate_trace(value)
    return value
