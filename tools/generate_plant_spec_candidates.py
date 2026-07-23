#!/usr/bin/env python3
"""Extract page-bound, non-authoritative plant-spec candidates from local PDFs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "assets/myactuator/catalog.tsv"
DOCUMENT_FILES = ROOT / "assets/myactuator/document_files.tsv"
PROTOCOL_APPLICABILITY = (
    ROOT / "generated/myactuator/protocol_applicability/registry.json"
)
EXTRACTION_PLAN = (
    ROOT / "assets/myactuator/plant_spec_extraction_plan.json"
)
EXTRACTION_PLAN_SCHEMA = (
    ROOT
    / "schemas/myactuator-plant-spec-extraction-plan.schema.json"
)
ENVIRONMENT_LOCK = ROOT / "tools/poppler-text-environment-lock.json"
SCHEMA = (
    ROOT
    / "schemas/myactuator-plant-spec-candidate-registry.schema.json"
)
OUTPUT = (
    ROOT / "generated/myactuator/plant/spec_candidates/registry.json"
)
HTML_OUTPUT = (
    ROOT / "generated/myactuator/plant/spec_candidates/index.html"
)
DOCUMENT_ROOT = (ROOT / "assets/vendor/myactuator/docs").resolve()
VERSION = "myactuator-plant-spec-candidate-registry/1"
XHTML = "{http://www.w3.org/1999/xhtml}"
TARGET_FIELDS = {
    "electrical.phase_resistance_ohm",
    "electrical.phase_inductance_h",
    "electrical.torque_constant_nm_per_a",
    "electrical.back_emf_v_s_per_rad",
    "electrical.max_qaxis_current_a",
    "mechanical.rotor_inertia_kg_m2",
    "mechanical.output_inertia_kg_m2",
    "mechanical.coulomb_friction_nm",
    "mechanical.viscous_friction_nm_s_per_rad",
    "transmission.ratio_motor_per_output",
    "transmission.forward_efficiency_ratio",
    "transmission.reverse_efficiency_ratio",
    "transmission.torsional_stiffness_nm_per_rad",
    "transmission.backlash_rad",
    "saturation.max_motor_speed_rad_s",
    "saturation.max_output_speed_rad_s",
    "saturation.max_continuous_output_torque_nm",
    "saturation.max_peak_output_torque_nm",
    "saturation.peak_duration_s",
    "thermal.winding_resistance_k_per_w",
    "thermal.case_resistance_k_per_w",
    "thermal.winding_heat_capacity_j_per_k",
    "thermal.case_heat_capacity_j_per_k",
    "thermal.max_winding_temperature_k",
    "thermal.max_case_temperature_k",
    "sensor.position_quantization_rad",
    "sensor.position_noise_stddev_rad",
    "sensor.velocity_noise_stddev_rad_s",
    "sensor.current_noise_stddev_a",
    "latency.command_delay_s",
    "latency.current_loop_period_s",
    "latency.state_sample_period_s",
    "latency.feedback_delay_s",
    "latency.delay_jitter_s",
    "operating_envelope.supply_voltage_v",
    "operating_envelope.ambient_temperature_k",
    "operating_envelope.output_speed_rad_s",
    "operating_envelope.output_torque_nm",
}

# Ordered longest/specific-first.  Matching retains the complete source label.
LABEL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("phase_to_phase_inductance", "Phase to Phase Inductance"),
    ("motor_back_emf_constant", "Motor Back-EMF Constant"),
    ("module_torque_constant", "Module Torque Constant"),
    ("motor_phase_resistance", "Motor Phase Resistance"),
    ("motor_phase_inductance", "Motor Phase Inductance"),
    ("rated_phase_current", "Rated Phase Current"),
    ("peak_phase_current", "Peak Phase Current"),
    ("no_load_input_current", "No-Load Input Current"),
    ("max_instant_torque", "Max Instant Torque"),
    ("max_instant_current", "Max Instant Current"),
    ("working_temperature", "Working Temperature"),
    ("line_resistance", "Line Resistance"),
    ("no_load_current", "No Load Current"),
    ("no_load_speed", "No-Load speed"),
    ("no_load_speed", "No Load Speed"),
    ("nominal_voltage", "Nominal Voltage"),
    ("nominal_current", "Nominal Current"),
    ("nominal_torque", "Nominal Torque"),
    ("nominal_speed", "Nominal Speed"),
    ("max_speed", "Max Speed"),
    ("gear_ratio", "Gear Ratio"),
    ("gear_ratio", "Gear ratio"),
    ("input_voltage", "Input Voltage"),
    ("rated_speed", "Rated Speed"),
    ("rated_torque", "Rated Torque"),
    ("rated_current", "Rated Current"),
    ("peak_torque", "Peak Torque"),
    ("peak_current", "Peak Current"),
    ("efficiency", "Efficiency"),
    ("torque_constant", "Torque Constant"),
    ("rotor_inertia", "Rotor Inertia"),
    ("phase_resistance", "Phase Resistance"),
    ("phase_inductance", "Phase Inductance"),
)

MODEL_HEADER = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+$")
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"


class PlantSpecCandidateError(ValueError):
    """A source, extraction, mapping or registry invariant is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PlantSpecCandidateError(message)


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


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".",
        dir=path.parent,
    )
    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PlantSpecCandidateError(
            f"{path}: cannot load JSON: {error}"
        ) from error
    require(isinstance(value, dict), f"{path}: JSON root must be an object")
    return value


def load_catalog() -> list[dict[str, str]]:
    try:
        with CATALOG.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            require(
                reader.fieldnames
                == [
                    "series",
                    "model",
                    "package_revision",
                    "archive_url",
                ],
                "catalog columns drift",
            )
            rows = list(reader)
    except OSError as error:
        raise PlantSpecCandidateError(
            f"cannot load catalog: {error}"
        ) from error
    require(len(rows) == 44, "catalog must contain exactly 44 models")
    require(
        len({row["model"] for row in rows}) == 44,
        "catalog model names must be globally unique",
    )
    return rows


def poppler_version() -> str:
    try:
        process = subprocess.run(
            ["pdftotext", "-v"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise PlantSpecCandidateError(
            f"cannot execute pdftotext: {error}"
        ) from error
    rendered = (process.stdout + "\n" + process.stderr).strip()
    match = re.search(r"pdftotext version ([0-9.]+)", rendered)
    require(
        process.returncode == 0 and match is not None,
        "cannot identify pdftotext version",
    )
    return match.group(1)


def check_environment() -> dict[str, Any]:
    lock = load_json(ENVIRONMENT_LOCK)
    require(
        set(lock)
        == {
            "artifact_id",
            "command",
            "command_arguments",
            "expected_version",
            "physical_io",
            "purpose",
            "schema_version",
            "support_granted",
        },
        "Poppler environment lock keys drift",
    )
    require(
        lock["schema_version"]
        == "myactuator-poppler-text-environment-lock/1"
        and lock["artifact_id"]
        == "myactuator-poppler-text-environment-lock"
        and lock["command"] == "pdftotext"
        and lock["command_arguments"]
        == ["-bbox-layout", "-enc", "UTF-8"]
        and lock["physical_io"] is False
        and lock["support_granted"] is False,
        "Poppler environment lock authority or command drift",
    )
    actual = poppler_version()
    require(
        actual == lock["expected_version"],
        f"pdftotext version {actual} != locked {lock['expected_version']}",
    )
    return {
        "command": lock["command"],
        "version": actual,
        "arguments": lock["command_arguments"],
    }


def _line_bbox(line: dict[str, Any]) -> list[float]:
    return [
        round(line["x0"], 6),
        round(line["y0"], 6),
        round(line["x1"], 6),
        round(line["y1"], 6),
    ]


def _merge_bbox(lines: Iterable[dict[str, Any]]) -> list[float]:
    items = list(lines)
    require(bool(items), "cannot merge an empty coordinate selection")
    return [
        round(min(line["x0"] for line in items), 6),
        round(min(line["y0"] for line in items), 6),
        round(max(line["x1"] for line in items), 6),
        round(max(line["y1"] for line in items), 6),
    ]


def _center_x(line: dict[str, Any]) -> float:
    return (line["x0"] + line["x1"]) / 2.0


def _center_y(line: dict[str, Any]) -> float:
    return (line["y0"] + line["y1"]) / 2.0


def _page_text_payload(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "bbox": _line_bbox(line),
            "text": line["text"],
            "word_count": line["word_count"],
        }
        for line in sorted(
            lines,
            key=lambda item: (
                round(item["y0"], 6),
                round(item["x0"], 6),
                item["text"],
            ),
        )
    ]


def extract_pdf(path: Path) -> list[dict[str, Any]]:
    try:
        process = subprocess.run(
            [
                "pdftotext",
                "-bbox-layout",
                "-enc",
                "UTF-8",
                str(path),
                "-",
            ],
            check=False,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise PlantSpecCandidateError(
            f"{path}: pdftotext failed: {error}"
        ) from error
    require(
        process.returncode == 0,
        f"{path}: pdftotext exit {process.returncode}: "
        + process.stderr.decode("utf-8", errors="replace")[:512],
    )
    try:
        root = ET.fromstring(process.stdout)
    except ET.ParseError as error:
        raise PlantSpecCandidateError(
            f"{path}: bbox XHTML is invalid: {error}"
        ) from error
    pages: list[dict[str, Any]] = []
    for page_index, page in enumerate(
        root.iter(XHTML + "page"),
        start=1,
    ):
        lines: list[dict[str, Any]] = []
        for line in page.iter(XHTML + "line"):
            words = list(line.findall(XHTML + "word"))
            if not words:
                continue
            text = " ".join(
                "".join(word.itertext()).strip() for word in words
            ).strip()
            if not text:
                continue
            lines.append(
                {
                    "text": text,
                    "word_count": len(words),
                    "x0": float(line.attrib["xMin"]),
                    "y0": float(line.attrib["yMin"]),
                    "x1": float(line.attrib["xMax"]),
                    "y1": float(line.attrib["yMax"]),
                }
            )
        payload = _page_text_payload(lines)
        pages.append(
            {
                "width": float(page.attrib["width"]),
                "height": float(page.attrib["height"]),
                "lines": lines,
                "record": {
                    "pdf_page_index": page_index,
                    "text_sha256": sha_bytes(canonical_bytes(payload)),
                    "text_status": (
                        "text_extracted"
                        if lines
                        else "no_extractable_text"
                    ),
                    "line_count": len(lines),
                    "word_count": sum(
                        line["word_count"] for line in lines
                    ),
                    "non_whitespace_character_count": sum(
                        len(re.sub(r"\s", "", line["text"]))
                        for line in lines
                    ),
                },
            }
        )
    require(pages, f"{path}: no PDF pages extracted")
    return pages


def match_property(text: str) -> str | None:
    folded = text.casefold()
    for property_id, phrase in LABEL_PATTERNS:
        if phrase.casefold() in folded:
            return property_id
    return None


def _normalize_for_parse(value: str) -> str:
    return (
        value.replace("％", "%")
        .replace("｜", "|")
        .replace("（", "(")
        .replace("）", ")")
        .replace("～", "~")
        .replace("−", "-")
        .replace("–", "-")
        .strip()
    )


def parse_value(value: str) -> dict[str, Any]:
    normalized = _normalize_for_parse(value)
    numbers = [
        float(item)
        for item in re.findall(NUMBER, normalized.replace(",", ""))
    ]
    qualifier: str | None = None
    annotation: str | None = None
    kind = "unparsed"
    qualified = re.fullmatch(
        rf"\s*(<=|>=|<|>)\s*({NUMBER})\s*%?\s*",
        normalized,
    )
    exact = re.fullmatch(
        rf"\s*({NUMBER})\s*(?:%|℃|°C)?\s*",
        normalized,
    )
    annotated = re.fullmatch(
        rf"\s*({NUMBER})\s*\(([^)]+)\)\s*",
        normalized,
    )
    range_match = re.search(
        rf"({NUMBER})\s*~\s*({NUMBER})",
        normalized,
    )
    if "|" in normalized and len(numbers) >= 2:
        kind = "alternatives"
        annotation = "source_presents_multiple_alternatives"
    elif range_match is not None and len(numbers) >= 2:
        kind = "range"
    elif qualified is not None:
        kind = "qualified_scalar"
        qualifier = qualified.group(1)
    elif exact is not None and len(numbers) == 1:
        kind = "scalar"
    elif annotated is not None and len(numbers) == 1:
        kind = "annotated_scalar"
        annotation = annotated.group(2).strip()
    elif len(numbers) == 1:
        kind = "annotated_scalar"
        annotation = normalized
    elif len(numbers) > 1:
        kind = "alternatives"
        annotation = "multiple_numbers_without_single_scalar_semantics"
    return {
        "kind": kind,
        "numbers": numbers,
        "qualifier": qualifier,
        "annotation": annotation,
    }


def _conversion(
    kind: str,
    *,
    scale: float | None,
    offset: float | None = 0.0,
    expression: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "scale": scale,
        "offset": offset,
        "expression": expression,
    }


def mapping_for(
    property_id: str,
    parsed: dict[str, Any],
) -> dict[str, Any]:
    identity = _conversion("identity", scale=1.0)
    not_applicable = _conversion(
        "not_applicable",
        scale=None,
        offset=None,
        expression=None,
    )
    direct: dict[str, tuple[str, str, dict[str, Any]]] = {
        "gear_ratio": (
            "transmission.ratio_motor_per_output",
            "1",
            identity,
        ),
        "motor_phase_resistance": (
            "electrical.phase_resistance_ohm",
            "ohm",
            identity,
        ),
        "motor_phase_inductance": (
            "electrical.phase_inductance_h",
            "H",
            _conversion("exact_linear_si", scale=0.001),
        ),
        "torque_constant": (
            "electrical.torque_constant_nm_per_a",
            "N*m/A",
            identity,
        ),
        "rotor_inertia": (
            "mechanical.rotor_inertia_kg_m2",
            "kg*m^2",
            _conversion("exact_linear_si", scale=1e-7),
        ),
    }
    semantic: dict[
        str,
        tuple[str, str, dict[str, Any], tuple[str, ...]],
    ] = {
        "phase_resistance": (
            "electrical.phase_resistance_ohm",
            "ohm",
            identity,
            ("line_or_phase_basis_not_explicit",),
        ),
        "line_resistance": (
            "electrical.phase_resistance_ohm",
            "ohm",
            _conversion(
                "reviewed_derivation_required",
                scale=None,
                offset=None,
                expression="derive phase resistance from stated line basis",
            ),
            ("line_to_phase_conversion_not_defined",),
        ),
        "phase_inductance": (
            "electrical.phase_inductance_h",
            "H",
            _conversion("exact_linear_si", scale=0.001),
            ("line_or_phase_basis_not_explicit",),
        ),
        "phase_to_phase_inductance": (
            "electrical.phase_inductance_h",
            "H",
            _conversion(
                "reviewed_derivation_required",
                scale=None,
                offset=None,
                expression="derive phase inductance from phase-to-phase basis",
            ),
            ("phase_to_phase_conversion_not_defined",),
        ),
        "module_torque_constant": (
            "electrical.torque_constant_nm_per_a",
            "N*m/A",
            _conversion(
                "reviewed_derivation_required",
                scale=None,
                offset=None,
                expression="resolve module/output-side versus motor-side basis",
            ),
            ("module_vs_motor_shaft_definition_unresolved",),
        ),
        "motor_back_emf_constant": (
            "electrical.back_emf_v_s_per_rad",
            "V*s/rad",
            _conversion(
                "reviewed_derivation_required",
                scale=60.0 / (1000.0 * 2.0 * math.pi),
                expression="Vdc/Krpm * 60 / (1000 * 2*pi)",
            ),
            ("voltage_and_phase_basis_unresolved",),
        ),
        "rated_torque": (
            "saturation.max_continuous_output_torque_nm",
            "N*m",
            identity,
            ("rated_duty_to_continuous_limit_review_required",),
        ),
        "nominal_torque": (
            "saturation.max_continuous_output_torque_nm",
            "N*m",
            identity,
            ("nominal_duty_to_continuous_limit_review_required",),
        ),
        "peak_torque": (
            "saturation.max_peak_output_torque_nm",
            "N*m",
            identity,
            ("peak_duration_not_stated",),
        ),
        "max_instant_torque": (
            "saturation.max_peak_output_torque_nm",
            "N*m",
            identity,
            ("instant_duration_not_stated",),
        ),
        "max_speed": (
            "saturation.max_motor_speed_rad_s",
            "rad/s",
            _conversion(
                "exact_linear_si",
                scale=2.0 * math.pi / 60.0,
                expression="RPM * 2*pi / 60",
            ),
            ("motor_vs_output_speed_basis_review_required",),
        ),
        "no_load_speed": (
            "saturation.max_output_speed_rad_s",
            "rad/s",
            _conversion(
                "exact_linear_si",
                scale=2.0 * math.pi / 60.0,
                expression="RPM * 2*pi / 60",
            ),
            ("no_load_speed_is_not_declared_maximum",),
        ),
        "rated_current": (
            "electrical.max_qaxis_current_a",
            "A",
            identity,
            ("rated_current_is_not_qaxis_maximum",),
        ),
        "rated_phase_current": (
            "electrical.max_qaxis_current_a",
            "A",
            identity,
            ("rms_phase_current_is_not_qaxis_maximum",),
        ),
        "peak_current": (
            "electrical.max_qaxis_current_a",
            "A",
            identity,
            ("peak_input_or_phase_current_is_not_qaxis_limit",),
        ),
        "peak_phase_current": (
            "electrical.max_qaxis_current_a",
            "A",
            identity,
            ("peak_rms_phase_current_is_not_qaxis_limit",),
        ),
        "max_instant_current": (
            "electrical.max_qaxis_current_a",
            "A",
            identity,
            ("instant_current_is_not_qaxis_limit",),
        ),
        "efficiency": (
            "transmission.forward_efficiency_ratio",
            "1",
            _conversion("exact_linear_si", scale=0.01),
            ("operating_point_and_direction_unresolved",),
        ),
        "working_temperature": (
            "operating_envelope.ambient_temperature_k",
            "K",
            _conversion(
                "exact_linear_si",
                scale=1.0,
                offset=273.15,
                expression="degrees Celsius + 273.15",
            ),
            ("motor_working_vs_ambient_definition_unresolved",),
        ),
    }
    unmapped_blockers: dict[str, tuple[str, ...]] = {
        "input_voltage": ("scalar_voltage_cannot_fill_required_range",),
        "nominal_voltage": (
            "nominal_voltage_cannot_fill_required_range",
        ),
        "nominal_current": (
            "nominal_current_is_not_qaxis_limit",
        ),
        "no_load_current": ("no_current_plant_target_with_same_semantics",),
        "no_load_input_current": (
            "no_current_plant_target_with_same_semantics",
        ),
        "rated_speed": (
            "rated_speed_is_not_a_current_plant_limit_field",
        ),
        "nominal_speed": (
            "nominal_speed_is_not_a_current_plant_limit_field",
        ),
    }
    if property_id in direct:
        target, unit, conversion = direct[property_id]
        blockers: list[str] = []
        if parsed["kind"] != "scalar":
            blockers.append("source_value_not_single_scalar")
        return {
            "status": (
                "candidate_direct_label_unit_match"
                if not blockers
                else "candidate_semantic_review_required"
            ),
            "target_field_id": target,
            "normalized_unit": unit,
            "conversion": conversion,
            "blockers": blockers,
        }
    if property_id in semantic:
        target, unit, conversion, configured = semantic[property_id]
        blockers = list(configured)
        expected_shape = (
            "range"
            if target.startswith("operating_envelope.")
            else "scalar"
        )
        if parsed["kind"] != expected_shape:
            blockers.append(
                "source_value_not_" + expected_shape
            )
        return {
            "status": "candidate_semantic_review_required",
            "target_field_id": target,
            "normalized_unit": unit,
            "conversion": conversion,
            "blockers": sorted(set(blockers)),
        }
    blockers = list(
        unmapped_blockers.get(
            property_id,
            ("no_current_plant_target_with_same_semantics",),
        )
    )
    if parsed["kind"] == "unparsed":
        blockers.append("source_value_not_machine_parsed")
    return {
        "status": "not_mappable_to_current_plant_contract",
        "target_field_id": None,
        "normalized_unit": None,
        "conversion": not_applicable,
        "blockers": sorted(set(blockers)),
    }


def _candidate_identity_payload(
    *,
    model_key: str,
    occurrence_id: str,
    page_index: int,
    property_id: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    return {
        "model_key": model_key,
        "document_occurrence_id": occurrence_id,
        "pdf_page_index": page_index,
        "source_property_id": property_id,
        "source": source,
    }


def _table_identity_payload(
    *,
    model_key: str,
    occurrence_id: str,
    page_index: int,
    page_text_sha256: str,
) -> dict[str, Any]:
    return {
        "model_key": model_key,
        "document_occurrence_id": occurrence_id,
        "pdf_page_index": page_index,
        "page_text_sha256": page_text_sha256,
    }


def _table_label_cluster(
    lines: list[dict[str, Any]],
    header: dict[str, Any],
) -> list[tuple[dict[str, Any], str]]:
    candidates = sorted(
        (
            (line, property_id)
            for line in lines
            if line["x0"] > 600.0
            and (property_id := match_property(line["text"])) is not None
            and 0.0 < _center_y(line) - _center_y(header) < 400.0
        ),
        key=lambda item: (_center_y(item[0]), item[0]["x0"]),
    )
    require(candidates, f"{header['text']}: no recognized table labels")
    first_index = next(
        (
            index
            for index, (line, _) in enumerate(candidates)
            if 0.0 < _center_y(line) - _center_y(header) < 40.0
        ),
        None,
    )
    require(
        first_index is not None,
        f"{header['text']}: no table label follows exact header",
    )
    result = [candidates[first_index]]
    previous_y = _center_y(candidates[first_index][0])
    for item in candidates[first_index + 1 :]:
        current_y = _center_y(item[0])
        if current_y - previous_y > 55.0:
            break
        result.append(item)
        previous_y = current_y
    require(
        len(result) >= 8,
        f"{header['text']}: fewer than eight contiguous parameter rows",
    )
    return result


def _exact_header(
    lines: list[dict[str, Any]],
    model: str,
) -> tuple[dict[str, Any], list[tuple[dict[str, Any], str]]]:
    possible: list[
        tuple[
            float,
            dict[str, Any],
            list[tuple[dict[str, Any], str]],
        ]
    ] = []
    for line in lines:
        if line["text"].strip() != model or line["x0"] <= 600.0:
            continue
        try:
            labels = _table_label_cluster(lines, line)
        except PlantSpecCandidateError:
            continue
        possible.append(
            (
                _center_y(labels[0][0]) - _center_y(line),
                line,
                labels,
            )
        )
    require(
        possible,
        f"{model}: exact table header not found on selected page",
    )
    _, header, labels = min(possible, key=lambda item: item[0])
    return header, labels


def extract_model_table(
    *,
    model: dict[str, Any],
    occurrence: dict[str, Any],
    page: dict[str, Any],
    page_index: int,
) -> dict[str, Any]:
    lines = page["lines"]
    header, label_cluster = _exact_header(lines, model["model"])
    header_y = _center_y(header)
    table_headers = sorted(
        (
            line
            for line in lines
            if line["x0"] > 600.0
            and abs(_center_y(line) - header_y) < 4.0
            and MODEL_HEADER.fullmatch(line["text"].strip())
        ),
        key=_center_x,
    )
    centers = [_center_x(line) for line in table_headers]
    target_index = next(
        (
            index
            for index, line in enumerate(table_headers)
            if line["text"].strip() == model["model"]
        ),
        None,
    )
    require(
        target_index is not None,
        f"{model['model']}: selected header is not in table columns",
    )
    center = centers[target_index]
    if target_index > 0:
        lower = (centers[target_index - 1] + center) / 2.0
    elif len(centers) > 1:
        lower = center - (centers[1] - center) / 2.0
    else:
        lower = center - 110.0
    if target_index + 1 < len(centers):
        upper = (center + centers[target_index + 1]) / 2.0
    elif target_index > 0:
        upper = center + (center - centers[target_index - 1]) / 2.0
    else:
        upper = center + 110.0
    first_value_lower = min(centers) - (
        (centers[1] - centers[0]) / 2.0
        if len(centers) > 1
        else 110.0
    )
    candidates: list[dict[str, Any]] = []
    for label, property_id in label_cluster:
        label_y = _center_y(label)
        same_row = [
            line
            for line in lines
            if abs(_center_y(line) - label_y) < 3.2
        ]
        value_lines = sorted(
            (
                line
                for line in same_row
                if lower <= _center_x(line) < upper
            ),
            key=lambda line: line["x0"],
        )
        require(
            value_lines,
            f"{model['model']}/{property_id}: value cell missing",
        )
        unit_lines = sorted(
            (
                line
                for line in same_row
                if label["x1"] < _center_x(line) < first_value_lower
            ),
            key=lambda line: line["x0"],
        )
        source = {
            "label_text": label["text"],
            "unit_text": " ".join(
                line["text"] for line in unit_lines
            ),
            "value_text": " ".join(
                line["text"] for line in value_lines
            ),
            "label_bbox": _line_bbox(label),
            "unit_bbox": (
                _merge_bbox(unit_lines) if unit_lines else None
            ),
            "value_bbox": _merge_bbox(value_lines),
        }
        parsed = parse_value(source["value_text"])
        identity = _candidate_identity_payload(
            model_key=model["model_key"],
            occurrence_id=occurrence["document_occurrence_id"],
            page_index=page_index,
            property_id=property_id,
            source=source,
        )
        candidates.append(
            {
                "candidate_id": "plantspeccandidate-"
                + sha_bytes(canonical_bytes(identity))[:20],
                "source_property_id": property_id,
                "source": source,
                "parse": parsed,
                "mapping": mapping_for(property_id, parsed),
                "review": {
                    "status": "unreviewed",
                    "reviewer_id": None,
                    "reviewed_at_utc": None,
                    "decision_note": None,
                },
            }
        )
    table_identity = _table_identity_payload(
        model_key=model["model_key"],
        occurrence_id=occurrence["document_occurrence_id"],
        page_index=page_index,
        page_text_sha256=page["record"]["text_sha256"],
    )
    return {
        "table_id": "plantspectable-"
        + sha_bytes(canonical_bytes(table_identity))[:20],
        "model_identity": {
            "model_key": model["model_key"],
            "series": model["series"],
            "model": model["model"],
            "package_revision": model["package_revision"],
        },
        "document_occurrence_id": occurrence["document_occurrence_id"],
        "file_sha256": occurrence["file_sha256"],
        "pdf_page_index": page_index,
        "page_text_sha256": page["record"]["text_sha256"],
        "model_header_text": header["text"],
        "model_header_bbox": _line_bbox(header),
        "applicability_blockers": [
            "exact_installed_hardware_firmware_tuple_unknown",
            "independent_manual_applicability_review_missing",
        ],
        "candidates": candidates,
        "accepted_candidate_count": 0,
        "runtime_admissible": False,
    }


def _model_key_by_name(
    registry: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result = {
        item["model"]: {
            "model_key": item["model_key"],
            "series": item["series"],
            "model": item["model"],
            "package_revision": item["package_revision"],
        }
        for item in registry["models"]
    }
    require(len(result) == 44, "applicability model identity drift")
    return result


def load_and_validate_plan(
    *,
    registry: dict[str, Any],
) -> tuple[
    dict[str, tuple[str, int]],
    dict[str, dict[str, Any]],
]:
    plan = load_json(EXTRACTION_PLAN)
    plan_schema = load_json(EXTRACTION_PLAN_SCHEMA)
    Draft202012Validator.check_schema(plan_schema)
    plan_errors = sorted(
        Draft202012Validator(plan_schema).iter_errors(plan),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if plan_errors:
        error = plan_errors[0]
        raise PlantSpecCandidateError(
            "extraction plan schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        set(plan)
        == {
            "artifact_id",
            "authority",
            "policy",
            "schema_version",
            "sources",
            "support_granted",
        },
        "extraction plan keys drift",
    )
    require(
        plan["schema_version"]
        == "myactuator-plant-spec-extraction-plan/1"
        and plan["artifact_id"]
        == "myactuator-plant-spec-extraction-plan"
        and plan["authority"] == "machine_extraction_navigation_only"
        and plan["support_granted"] is False,
        "extraction plan authority drift",
    )
    expected_policy = {
        "all_catalog_models_exactly_once": True,
        "exact_model_header_required": True,
        "independent_review_required": True,
        "machine_selection_cannot_accept_fact": True,
        "page_and_source_hash_required": True,
        "raw_label_unit_and_value_preserved": True,
    }
    require(plan["policy"] == expected_policy, "extraction plan policy drift")
    occurrences = {
        item["occurrence_id"]: item
        for item in registry["document_file_occurrences"]
        if item["source_claim"]["document_scope"] == "product_manual"
    }
    selections: dict[str, tuple[str, int]] = {}
    source_rows: dict[str, dict[str, Any]] = {}
    require(len(plan["sources"]) == 9, "plan must select nine spec manuals")
    for source in plan["sources"]:
        require(
            set(source)
            == {"document_occurrence_id", "file_sha256", "tables"},
            "extraction plan source keys drift",
        )
        occurrence_id = source["document_occurrence_id"]
        occurrence = occurrences.get(occurrence_id)
        require(
            occurrence is not None,
            f"{occurrence_id}: plan source is not a candidate manual",
        )
        require(
            source["file_sha256"] == occurrence["file_sha256"],
            f"{occurrence_id}: extraction-plan source hash drift",
        )
        require(
            occurrence_id not in source_rows,
            f"{occurrence_id}: duplicate extraction-plan source",
        )
        source_rows[occurrence_id] = source
        for table in source["tables"]:
            require(
                set(table) == {"model", "pdf_page_index"},
                f"{occurrence_id}: table selection keys drift",
            )
            model = table["model"]
            require(
                model not in selections,
                f"{model}: duplicate table selection",
            )
            require(
                isinstance(table["pdf_page_index"], int)
                and not isinstance(table["pdf_page_index"], bool)
                and table["pdf_page_index"] >= 1,
                f"{model}: invalid PDF page index",
            )
            selections[model] = (
                occurrence_id,
                table["pdf_page_index"],
            )
    catalog_models = {item["model"] for item in registry["models"]}
    require(
        set(selections) == catalog_models and len(selections) == 44,
        "extraction plan must select every catalog model exactly once",
    )
    return selections, source_rows


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = json.loads(json.dumps(value))
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(
        digest_payload(value)
    )


def build() -> dict[str, Any]:
    environment = check_environment()
    applicability = load_json(PROTOCOL_APPLICABILITY)
    catalog = load_catalog()
    require(
        [
            (
                item["series"],
                item["model"],
                item["package_revision"],
            )
            for item in applicability["models"]
        ]
        == [
            (
                item["series"],
                item["model"],
                item["package_revision"],
            )
            for item in catalog
        ],
        "applicability registry and catalog identity/order drift",
    )
    selections, selected_sources = load_and_validate_plan(
        registry=applicability
    )
    occurrences = {
        item["occurrence_id"]: {
            **item,
            "document_occurrence_id": item["occurrence_id"],
        }
        for item in applicability["document_file_occurrences"]
        if item["source_claim"]["document_scope"] == "product_manual"
    }
    require(len(occurrences) == 15, "candidate manual occurrence drift")
    extracted_by_occurrence: dict[str, list[dict[str, Any]]] = {}
    manuals: list[dict[str, Any]] = []
    for occurrence in occurrences.values():
        relative = occurrence["vendor_relative_path"]
        source = (DOCUMENT_ROOT / relative).resolve()
        require(
            source.is_relative_to(DOCUMENT_ROOT),
            f"{relative}: source escapes local document root",
        )
        require(source.is_file(), f"{relative}: source PDF is missing")
        require(
            source.stat().st_size == occurrence["bytes"],
            f"{relative}: source PDF byte count drift",
        )
        require(
            sha_file(source) == occurrence["file_sha256"],
            f"{relative}: source PDF SHA-256 drift",
        )
        pages = extract_pdf(source)
        extracted_by_occurrence[
            occurrence["document_occurrence_id"]
        ] = pages
        manuals.append(
            {
                "document_occurrence_id": occurrence[
                    "document_occurrence_id"
                ],
                "file_name": occurrence["file_name"],
                "vendor_relative_path": relative,
                "file_sha256": occurrence["file_sha256"],
                "bytes": occurrence["bytes"],
                "page_count": len(pages),
                "pages": [page["record"] for page in pages],
                "text_extraction_status": "all_pages_processed",
                "selected_product_spec_table": occurrence[
                    "document_occurrence_id"
                ]
                in selected_sources,
            }
        )
    models_by_name = _model_key_by_name(applicability)
    model_tables: list[dict[str, Any]] = []
    for catalog_row in catalog:
        model = models_by_name[catalog_row["model"]]
        occurrence_id, page_index = selections[model["model"]]
        occurrence = occurrences[occurrence_id]
        pages = extracted_by_occurrence[occurrence_id]
        require(
            page_index <= len(pages),
            f"{model['model']}: selected page exceeds PDF page count",
        )
        model_tables.append(
            extract_model_table(
                model=model,
                occurrence=occurrence,
                page=pages[page_index - 1],
                page_index=page_index,
            )
        )
    candidates = [
        candidate
        for table in model_tables
        for candidate in table["candidates"]
    ]
    mapping_counts = {
        status: sum(
            candidate["mapping"]["status"] == status
            for candidate in candidates
        )
        for status in (
            "candidate_direct_label_unit_match",
            "candidate_semantic_review_required",
            "not_mappable_to_current_plant_contract",
        )
    }
    value = {
        "schema_version": VERSION,
        "artifact_id": "myactuator-plant-spec-candidate-registry",
        "authority": (
            "page_bound_machine_extraction_and_review_navigation_only"
        ),
        "sources": {
            "catalog_sha256": sha_file(CATALOG),
            "document_files_sha256": sha_file(DOCUMENT_FILES),
            "protocol_applicability_registry_sha256": sha_file(
                PROTOCOL_APPLICABILITY
            ),
            "extraction_plan_sha256": sha_file(EXTRACTION_PLAN),
            "extraction_plan_schema_sha256": sha_file(
                EXTRACTION_PLAN_SCHEMA
            ),
            "poppler_environment_lock_sha256": sha_file(
                ENVIRONMENT_LOCK
            ),
            "generator_sha256": sha_file(Path(__file__).resolve()),
        },
        "extraction_environment": environment,
        "policy": {
            "all_catalog_models_required": True,
            "full_manual_page_digest_required": True,
            "source_hash_page_and_coordinates_required": True,
            "raw_label_unit_and_value_preserved": True,
            "machine_extraction_cannot_accept_fact": True,
            "all_candidate_values_remain_unreviewed": True,
            "conflicts_and_alternatives_remain_unresolved": True,
            "independent_review_required": True,
        },
        "manuals": manuals,
        "model_tables": model_tables,
        "summary": {
            "manual_occurrence_count": len(manuals),
            "product_spec_manual_count": len(selected_sources),
            "page_count": sum(manual["page_count"] for manual in manuals),
            "model_count": len(model_tables),
            "model_with_candidate_count": sum(
                bool(table["candidates"]) for table in model_tables
            ),
            "candidate_count": len(candidates),
            "direct_label_unit_mapping_candidate_count": mapping_counts[
                "candidate_direct_label_unit_match"
            ],
            "semantic_review_mapping_candidate_count": mapping_counts[
                "candidate_semantic_review_required"
            ],
            "unmapped_candidate_count": mapping_counts[
                "not_mappable_to_current_plant_contract"
            ],
            "unreviewed_candidate_count": len(candidates),
            "accepted_candidate_count": 0,
            "runtime_admissible_candidate_count": 0,
        },
        "runtime_plant_admission": False,
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(value)
    validate(value)
    return value


def _expected_candidate_id(
    table: dict[str, Any],
    candidate: dict[str, Any],
) -> str:
    payload = _candidate_identity_payload(
        model_key=table["model_identity"]["model_key"],
        occurrence_id=table["document_occurrence_id"],
        page_index=table["pdf_page_index"],
        property_id=candidate["source_property_id"],
        source=candidate["source"],
    )
    return "plantspeccandidate-" + sha_bytes(
        canonical_bytes(payload)
    )[:20]


def validate(
    value: dict[str, Any],
    *,
    verify_sources: bool = True,
) -> None:
    schema = load_json(SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise PlantSpecCandidateError(
            "registry schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "registry digest drift",
    )
    catalog = load_catalog()
    require(
        [
            (
                table["model_identity"]["series"],
                table["model_identity"]["model"],
                table["model_identity"]["package_revision"],
            )
            for table in value["model_tables"]
        ]
        == [
            (
                row["series"],
                row["model"],
                row["package_revision"],
            )
            for row in catalog
        ],
        "registry model identity/order differs from catalog",
    )
    manual_ids = [
        item["document_occurrence_id"] for item in value["manuals"]
    ]
    require(
        len(manual_ids) == len(set(manual_ids)) == 15,
        "manual occurrence identity is not unique",
    )
    manuals = {
        item["document_occurrence_id"]: item
        for item in value["manuals"]
    }
    table_ids: set[str] = set()
    candidate_ids: set[str] = set()
    target_fields = TARGET_FIELDS
    for table in value["model_tables"]:
        require(
            table["table_id"] not in table_ids,
            f"{table['table_id']}: duplicate table identity",
        )
        table_ids.add(table["table_id"])
        manual = manuals.get(table["document_occurrence_id"])
        require(manual is not None, "table references unknown manual")
        require(
            table["file_sha256"] == manual["file_sha256"],
            f"{table['table_id']}: source hash differs from manual",
        )
        page_index = table["pdf_page_index"]
        require(
            page_index <= manual["page_count"],
            f"{table['table_id']}: source page is outside manual",
        )
        require(
            table["page_text_sha256"]
            == manual["pages"][page_index - 1]["text_sha256"],
            f"{table['table_id']}: page text digest drift",
        )
        expected_table_id = "plantspectable-" + sha_bytes(
            canonical_bytes(
                _table_identity_payload(
                    model_key=table["model_identity"]["model_key"],
                    occurrence_id=table["document_occurrence_id"],
                    page_index=page_index,
                    page_text_sha256=table["page_text_sha256"],
                )
            )
        )[:20]
        require(
            table["table_id"] == expected_table_id,
            f"{table['table_id']}: stable table identity drift",
        )
        for candidate in table["candidates"]:
            identifier = candidate["candidate_id"]
            require(
                identifier not in candidate_ids,
                f"{identifier}: duplicate candidate identity",
            )
            candidate_ids.add(identifier)
            require(
                identifier == _expected_candidate_id(table, candidate),
                f"{identifier}: stable candidate identity drift",
            )
            mapping = candidate["mapping"]
            target = mapping["target_field_id"]
            require(
                target is None or target in target_fields,
                f"{identifier}: unknown runtime target field",
            )
            for key in ("label_bbox", "value_bbox"):
                x0, y0, x1, y1 = candidate["source"][key]
                require(
                    x0 >= 0
                    and y0 >= 0
                    and x1 > x0
                    and y1 > y0,
                    f"{identifier}: invalid {key}",
                )
    summary = value["summary"]
    candidates = [
        candidate
        for table in value["model_tables"]
        for candidate in table["candidates"]
    ]
    expected_counts = {
        "manual_occurrence_count": len(value["manuals"]),
        "product_spec_manual_count": sum(
            manual["selected_product_spec_table"]
            for manual in value["manuals"]
        ),
        "page_count": sum(
            manual["page_count"] for manual in value["manuals"]
        ),
        "model_count": len(value["model_tables"]),
        "model_with_candidate_count": sum(
            bool(table["candidates"]) for table in value["model_tables"]
        ),
        "candidate_count": len(candidates),
        "direct_label_unit_mapping_candidate_count": sum(
            candidate["mapping"]["status"]
            == "candidate_direct_label_unit_match"
            for candidate in candidates
        ),
        "semantic_review_mapping_candidate_count": sum(
            candidate["mapping"]["status"]
            == "candidate_semantic_review_required"
            for candidate in candidates
        ),
        "unmapped_candidate_count": sum(
            candidate["mapping"]["status"]
            == "not_mappable_to_current_plant_contract"
            for candidate in candidates
        ),
        "unreviewed_candidate_count": len(candidates),
        "accepted_candidate_count": 0,
        "runtime_admissible_candidate_count": 0,
    }
    require(summary == expected_counts, "registry summary drift")
    if verify_sources:
        require(
            value["sources"]
            == {
                "catalog_sha256": sha_file(CATALOG),
                "document_files_sha256": sha_file(DOCUMENT_FILES),
                "protocol_applicability_registry_sha256": sha_file(
                    PROTOCOL_APPLICABILITY
                ),
                "extraction_plan_sha256": sha_file(EXTRACTION_PLAN),
                "extraction_plan_schema_sha256": sha_file(
                    EXTRACTION_PLAN_SCHEMA
                ),
                "poppler_environment_lock_sha256": sha_file(
                    ENVIRONMENT_LOCK
                ),
                "generator_sha256": sha_file(Path(__file__).resolve()),
            },
            "registry source digests drift",
        )
        check_environment()
        for manual in value["manuals"]:
            source = (
                DOCUMENT_ROOT / manual["vendor_relative_path"]
            ).resolve()
            require(
                source.is_relative_to(DOCUMENT_ROOT)
                and source.is_file(),
                f"{manual['vendor_relative_path']}: source missing",
            )
            require(
                source.stat().st_size == manual["bytes"]
                and sha_file(source) == manual["file_sha256"],
                f"{manual['vendor_relative_path']}: source bytes drift",
            )


def render_html(value: dict[str, Any]) -> str:
    summary = value["summary"]
    rows: list[str] = []
    for table in value["model_tables"]:
        identity = table["model_identity"]
        for candidate in table["candidates"]:
            source = candidate["source"]
            mapping = candidate["mapping"]
            rows.append(
                "<tr>"
                f"<td>{html.escape(identity['series'])}</td>"
                f"<td>{html.escape(identity['model'])}</td>"
                f"<td>{table['pdf_page_index']}</td>"
                f"<td>{html.escape(source['label_text'])}</td>"
                f"<td>{html.escape(source['unit_text'])}</td>"
                f"<td>{html.escape(source['value_text'])}</td>"
                f"<td>{html.escape(mapping['target_field_id'] or '—')}</td>"
                f"<td>{html.escape(mapping['status'])}</td>"
                f"<td>{html.escape(', '.join(mapping['blockers']) or '—')}</td>"
                "</tr>"
            )
    return (
        "<!doctype html>\n"
        "<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>MYACTUATOR plant specification candidates</title>"
        "<style>"
        "body{font:14px/1.4 system-ui,sans-serif;margin:2rem;color:#17202a}"
        "h1{margin-bottom:.25rem}.warning{padding:1rem;background:#fff3cd;"
        "border:1px solid #e1b12c;font-weight:650}table{border-collapse:collapse;"
        "width:100%;margin-top:1rem}th,td{border:1px solid #ccd1d1;"
        "padding:.35rem;text-align:left;vertical-align:top}th{background:#edf2f7;"
        "position:sticky;top:0}code{overflow-wrap:anywhere}"
        "</style></head><body>"
        "<h1>MYACTUATOR plant specification candidates</h1>"
        "<p class=\"warning\">MACHINE-EXTRACTED, UNREVIEWED NAVIGATION ONLY. "
        "No row is an accepted source fact, runtime plant, support claim, "
        "physical-I/O permission or motion authority.</p>"
        f"<p>Manuals: {summary['manual_occurrence_count']} "
        f"({summary['product_spec_manual_count']} selected product sheets); "
        f"pages digested: {summary['page_count']}; models: "
        f"{summary['model_with_candidate_count']}/"
        f"{summary['model_count']}; candidates: "
        f"{summary['candidate_count']}; accepted: 0.</p>"
        f"<p>Registry digest: <code>{html.escape(value['integrity']['record_sha256'])}</code></p>"
        "<table><thead><tr><th>Series</th><th>Model</th><th>PDF page</th>"
        "<th>Raw label</th><th>Raw unit</th><th>Raw value</th>"
        "<th>Suggested target</th><th>Mapping state</th><th>Blockers</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></body></html>\n"
    )


def check_output(
    *,
    output: Path,
    html_output: Path,
    value: dict[str, Any],
) -> None:
    expected_json = canonical_json(value)
    expected_html = render_html(value)
    require(output.is_file(), f"{output}: generated registry is missing")
    require(
        output.read_text(encoding="utf-8") == expected_json,
        f"{output}: generated registry is stale",
    )
    require(
        html_output.is_file(),
        f"{html_output}: generated review index is missing",
    )
    require(
        html_output.read_text(encoding="utf-8") == expected_html,
        f"{html_output}: generated review index is stale",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--html-output", type=Path, default=HTML_OUTPUT)
    arguments = parser.parse_args()
    try:
        value = build()
        if arguments.check:
            check_output(
                output=arguments.output,
                html_output=arguments.html_output,
                value=value,
            )
            action = "CHECK"
        else:
            atomic_write(arguments.output, canonical_json(value))
            atomic_write(arguments.html_output, render_html(value))
            action = "WRITE"
    except PlantSpecCandidateError as error:
        print(f"PLANT_SPEC_CANDIDATES_ERROR {error}")
        return 1
    summary = value["summary"]
    print(
        f"PLANT_SPEC_CANDIDATES_{action} PASS "
        f"manuals={summary['manual_occurrence_count']} "
        f"pages={summary['page_count']} "
        f"models={summary['model_with_candidate_count']}/"
        f"{summary['model_count']} "
        f"candidates={summary['candidate_count']} "
        "accepted=0 runtime=0 support=false motion=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
