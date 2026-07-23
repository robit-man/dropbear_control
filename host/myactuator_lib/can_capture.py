"""Strict validation for append-only listen-only CAN evidence captures.

Capture shape can identify traffic worth later protocol review. It cannot by
itself establish motor model, firmware, protocol applicability, physical
execution, or support.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "myactuator-can-listen-capture-record.schema.json"
)


class CaptureValidationError(ValueError):
    """The capture cannot serve as lossless listen-only evidence."""


@dataclass(frozen=True)
class CaptureSummary:
    capture_id: str
    records: int
    first_monotonic_ns: int
    last_monotonic_ns: int
    request_shape_candidates: int
    response_shape_candidates: int
    lossless: bool
    motion_authorized: bool = False
    support_granted: bool = False
    protocol_applicability: str = "unverified"

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_id": self.capture_id,
            "records": self.records,
            "first_monotonic_ns": self.first_monotonic_ns,
            "last_monotonic_ns": self.last_monotonic_ns,
            "request_shape_candidates": self.request_shape_candidates,
            "response_shape_candidates": self.response_shape_candidates,
            "lossless": self.lossless,
            "motion_authorized": self.motion_authorized,
            "support_granted": self.support_granted,
            "protocol_applicability": self.protocol_applicability,
        }


def _schema_validator(schema_path: Path = SCHEMA_PATH) -> Draft202012Validator:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _stable_projection(record: dict[str, Any]) -> dict[str, Any]:
    timestamp = record["timestamp"]
    controller = record["controller"]
    return {
        "capture_id": record["capture_id"],
        "clock_id": timestamp["clock_id"],
        "clock_source": timestamp["clock_source"],
        "clock_resolution_ns": timestamp["resolution_ns"],
        "capture_started_utc": timestamp["capture_started_utc"],
        "bus_id": controller["bus_id"],
        "instance_id": controller["instance_id"],
        "controller_type": controller["controller_type"],
        "mode": controller["mode"],
        "bitrate": controller["bitrate"],
        "oscillator_hz": controller["oscillator_hz"],
        "transceiver_id": controller["transceiver_id"],
        "provenance": record["provenance"],
        "evidence_boundary": record["evidence_boundary"],
    }


def _path(error: Any) -> str:
    return ".".join(str(part) for part in error.absolute_path) or "<record>"


def validate_records(
    records: Iterable[dict[str, Any]],
    *,
    schema_path: Path = SCHEMA_PATH,
) -> CaptureSummary:
    validator = _schema_validator(schema_path)
    materialized = list(records)
    if not materialized:
        raise CaptureValidationError("capture is empty")

    baseline: dict[str, Any] | None = None
    last_sequence = 0
    last_timestamp = -1
    last_rx_frames = 0
    last_dropped = 0
    last_overflow = 0
    request_candidates = 0
    response_candidates = 0

    for line_number, record in enumerate(materialized, start=1):
        errors = sorted(validator.iter_errors(record), key=lambda item: list(item.path))
        if errors:
            first = errors[0]
            raise CaptureValidationError(
                f"record {line_number} schema error at {_path(first)}: {first.message}"
            )
        sequence = record["sequence"]
        if sequence != last_sequence + 1:
            raise CaptureValidationError(
                f"record {line_number} sequence discontinuity: "
                f"expected {last_sequence + 1}, found {sequence}"
            )
        last_sequence = sequence

        stable = _stable_projection(record)
        if baseline is None:
            baseline = stable
        elif stable != baseline:
            raise CaptureValidationError(
                f"record {line_number} capture/controller/provenance drift"
            )

        timestamp = record["timestamp"]["monotonic_ns"]
        if timestamp < last_timestamp:
            raise CaptureValidationError(
                f"record {line_number} monotonic timestamp regression"
            )
        last_timestamp = timestamp

        frame = record["frame"]
        if len(frame["data_hex"]) != frame["dlc"] * 2:
            raise CaptureValidationError(
                f"record {line_number} DLC/data length mismatch"
            )
        counters = record["counters"]
        if counters["rx_frames_total"] <= last_rx_frames:
            raise CaptureValidationError(
                f"record {line_number} receive counter did not increase"
            )
        if counters["rx_dropped_total"] < last_dropped:
            raise CaptureValidationError(
                f"record {line_number} dropped counter regressed"
            )
        if counters["driver_overflow_total"] < last_overflow:
            raise CaptureValidationError(
                f"record {line_number} overflow counter regressed"
            )
        last_rx_frames = counters["rx_frames_total"]
        last_dropped = counters["rx_dropped_total"]
        last_overflow = counters["driver_overflow_total"]

        arbitration_id = frame["arbitration_id"]
        if frame["dlc"] == 8 and 0x141 <= arbitration_id <= 0x160:
            request_candidates += 1
        if frame["dlc"] == 8 and 0x241 <= arbitration_id <= 0x260:
            response_candidates += 1

    if last_dropped != 0 or last_overflow != 0:
        raise CaptureValidationError(
            "capture is not lossless: dropped/overflow counter is nonzero"
        )
    assert baseline is not None
    return CaptureSummary(
        capture_id=baseline["capture_id"],
        records=len(materialized),
        first_monotonic_ns=materialized[0]["timestamp"]["monotonic_ns"],
        last_monotonic_ns=materialized[-1]["timestamp"]["monotonic_ns"],
        request_shape_candidates=request_candidates,
        response_shape_candidates=response_candidates,
        lossless=True,
    )


def validate_jsonl(
    path: Path | str,
    *,
    schema_path: Path = SCHEMA_PATH,
) -> CaptureSummary:
    capture_path = Path(path)
    records: list[dict[str, Any]] = []
    with capture_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                raise CaptureValidationError(f"record {line_number} is blank")
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise CaptureValidationError(
                    f"record {line_number} is invalid JSON: {error.msg}"
                ) from error
            if not isinstance(value, dict):
                raise CaptureValidationError(f"record {line_number} is not an object")
            records.append(value)
    return validate_records(records, schema_path=schema_path)
