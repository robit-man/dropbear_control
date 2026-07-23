#!/usr/bin/env python3
"""Generate the exact-model plant source-fact and missing-evidence ledger."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import html
import json
import math
import os
import tempfile
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "assets/myactuator/catalog.tsv"
APPLICABILITY = (
    ROOT / "generated/myactuator/protocol_applicability/registry.json"
)
PLANT_REGISTRY = ROOT / "generated/myactuator/plant/runtime_registry.json"
CANDIDATE_REGISTRY = (
    ROOT / "generated/myactuator/plant/spec_candidates/registry.json"
)
DECISION_REGISTRY = (
    ROOT / "generated/myactuator/plant/candidate_decisions/registry.json"
)
DECISION_REGISTRY_SCHEMA = (
    ROOT
    / "schemas/myactuator-plant-candidate-decision-registry.schema.json"
)
FACT_DIRECTORY = (
    ROOT
    / "generated/myactuator/plant/candidate_decisions/source_facts"
)
FACT_SCHEMA = ROOT / "schemas/myactuator-plant-source-fact.schema.json"
LEDGER_SCHEMA = (
    ROOT / "schemas/myactuator-plant-evidence-ledger.schema.json"
)
OUTPUT = (
    ROOT / "generated/myactuator/plant/evidence_ledger/ledger.json"
)
HTML_OUTPUT = (
    ROOT / "generated/myactuator/plant/evidence_ledger/index.html"
)
VERSION = "myactuator-plant-evidence-ledger/1"

PARAMETER_FIELDS = {
    "electrical": {
        "phase_resistance_ohm": ("ohm", "dq-lumped-v1"),
        "phase_inductance_h": ("H", "dq-lumped-v1"),
        "torque_constant_nm_per_a": ("N*m/A", "dq-lumped-v1"),
        "back_emf_v_s_per_rad": ("V*s/rad", "dq-lumped-v1"),
        "max_qaxis_current_a": ("A", "dq-lumped-v1"),
    },
    "mechanical": {
        "rotor_inertia_kg_m2": ("kg*m^2", "two-inertia-output-v1"),
        "output_inertia_kg_m2": ("kg*m^2", "two-inertia-output-v1"),
        "coulomb_friction_nm": (
            "N*m",
            "coulomb-viscous-deadzone-v1",
        ),
        "viscous_friction_nm_s_per_rad": (
            "N*m*s/rad",
            "coulomb-viscous-deadzone-v1",
        ),
    },
    "transmission": {
        "ratio_motor_per_output": ("1", "ratio-efficiency-compliance-v1"),
        "forward_efficiency_ratio": (
            "1",
            "ratio-efficiency-compliance-v1",
        ),
        "reverse_efficiency_ratio": (
            "1",
            "ratio-efficiency-compliance-v1",
        ),
        "torsional_stiffness_nm_per_rad": (
            "N*m/rad",
            "ratio-efficiency-compliance-v1",
        ),
        "backlash_rad": ("rad", "coulomb-viscous-deadzone-v1"),
    },
    "saturation": {
        "max_motor_speed_rad_s": (
            "rad/s",
            "current-speed-torque-duration-v1",
        ),
        "max_output_speed_rad_s": (
            "rad/s",
            "current-speed-torque-duration-v1",
        ),
        "max_continuous_output_torque_nm": (
            "N*m",
            "current-speed-torque-duration-v1",
        ),
        "max_peak_output_torque_nm": (
            "N*m",
            "current-speed-torque-duration-v1",
        ),
        "peak_duration_s": ("s", "current-speed-torque-duration-v1"),
    },
    "thermal": {
        "winding_resistance_k_per_w": ("K/W", "two-node-rc-v1"),
        "case_resistance_k_per_w": ("K/W", "two-node-rc-v1"),
        "winding_heat_capacity_j_per_k": ("J/K", "two-node-rc-v1"),
        "case_heat_capacity_j_per_k": ("J/K", "two-node-rc-v1"),
        "max_winding_temperature_k": ("K", "two-node-rc-v1"),
        "max_case_temperature_k": ("K", "two-node-rc-v1"),
    },
    "sensor": {
        "position_quantization_rad": (
            "rad",
            "quantized-biased-noisy-v1",
        ),
        "position_noise_stddev_rad": (
            "rad",
            "quantized-biased-noisy-v1",
        ),
        "velocity_noise_stddev_rad_s": (
            "rad/s",
            "quantized-biased-noisy-v1",
        ),
        "current_noise_stddev_a": (
            "A",
            "quantized-biased-noisy-v1",
        ),
    },
    "latency": {
        "command_delay_s": ("s", "bounded-delay-jitter-v1"),
        "current_loop_period_s": ("s", "bounded-delay-jitter-v1"),
        "state_sample_period_s": ("s", "bounded-delay-jitter-v1"),
        "feedback_delay_s": ("s", "bounded-delay-jitter-v1"),
        "delay_jitter_s": ("s", "bounded-delay-jitter-v1"),
    },
}
ENVELOPE_FIELDS = {
    "supply_voltage_v": ("V", "bounded-operating-envelope-v1"),
    "ambient_temperature_k": ("K", "bounded-operating-envelope-v1"),
    "output_speed_rad_s": ("rad/s", "bounded-operating-envelope-v1"),
    "output_torque_nm": ("N*m", "bounded-operating-envelope-v1"),
}
MANUAL_EVIDENCE_CLASSES = {
    "official_stated",
    "source_derived",
    "digitized_curve",
}


class PlantEvidenceLedgerError(ValueError):
    """A source fact, model/source join, or ledger invariant is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PlantEvidenceLedgerError(message)


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
        raise PlantEvidenceLedgerError(
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
        raise PlantEvidenceLedgerError(
            f"cannot load catalog: {error}"
        ) from error
    require(len(rows) == 44, "catalog must contain exactly 44 models")
    require(
        len({(row["series"], row["model"]) for row in rows}) == 44,
        "catalog model identity is not unique",
    )
    return rows


def requirement_catalog() -> list[dict[str, str]]:
    return [
        {
            "requirement_kind": "parameter",
            "field_id": f"{domain}.{name}",
            "domain": domain,
            "name": name,
            "canonical_unit": unit,
            "model_form": model_form,
        }
        for domain, fields in PARAMETER_FIELDS.items()
        for name, (unit, model_form) in fields.items()
    ]


def envelope_catalog() -> list[dict[str, str]]:
    return [
        {
            "requirement_kind": "operating_envelope",
            "field_id": f"operating_envelope.{name}",
            "domain": "operating_envelope",
            "name": name,
            "canonical_unit": unit,
            "model_form": model_form,
        }
        for name, (unit, model_form) in ENVELOPE_FIELDS.items()
    ]


def fact_identity_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {
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


def expected_fact_id(value: dict[str, Any]) -> str:
    return "plantfact-" + sha_bytes(
        canonical_bytes(fact_identity_payload(value))
    )[:20]


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


def validate_source_fact(
    fact: dict[str, Any],
    *,
    fact_schema: dict[str, Any],
    models: dict[str, dict[str, Any]],
    occurrences: dict[str, dict[str, Any]],
    candidate_manuals_by_model: dict[str, set[str]],
    candidate_index: dict[
        str, tuple[dict[str, Any], dict[str, Any]]
    ],
    candidate_registry_sha256: str,
) -> None:
    errors = sorted(
        Draft202012Validator(
            fact_schema,
            format_checker=FormatChecker(),
        ).iter_errors(fact),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise PlantEvidenceLedgerError(
            "source fact schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    identifier = fact["fact_id"]
    require(
        identifier == expected_fact_id(fact),
        f"{identifier}: stable fact identity drift",
    )
    identity = fact["model_identity"]
    model = models.get(identity["model_key"])
    require(model is not None, f"{identifier}: unknown model key")
    require(
        (
            identity["series"],
            identity["model"],
            identity["package_revision"],
        )
        == (
            model["series"],
            model["model"],
            model["package_revision"],
        ),
        f"{identifier}: exact catalog identity mismatch",
    )
    provenance = fact["provenance"]
    indexed = candidate_index.get(provenance["candidate_id"])
    require(indexed is not None, f"{identifier}: unknown source candidate")
    table, candidate = indexed
    require(
        provenance["candidate_registry_sha256"]
        == candidate_registry_sha256
        and provenance["candidate_sha256"]
        == sha_bytes(canonical_bytes(candidate)),
        f"{identifier}: candidate registry/fact hash drift",
    )
    require(
        provenance["table_id"] == table["table_id"]
        and identity == table["model_identity"],
        f"{identifier}: candidate table/model binding mismatch",
    )
    occurrence_id = provenance["document_occurrence_id"]
    occurrence = occurrences.get(occurrence_id)
    require(
        occurrence is not None,
        f"{identifier}: unknown document occurrence",
    )
    require(
        occurrence_id in candidate_manuals_by_model[identity["model_key"]],
        f"{identifier}: document is not a candidate product manual for model",
    )
    require(
        provenance["file_sha256"] == occurrence["file_sha256"],
        f"{identifier}: document SHA-256 mismatch",
    )
    expected_provenance = {
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
    }
    require(
        provenance == expected_provenance,
        f"{identifier}: exact candidate provenance drift",
    )
    target = fact["target"]
    field_id = f"{target['domain']}.{target['name']}"
    definitions = {
        item["field_id"]: item
        for item in requirement_catalog() + envelope_catalog()
    }
    definition = definitions.get(field_id)
    require(definition is not None, f"{identifier}: unknown target {field_id}")
    require(
        target["requirement_kind"] == definition["requirement_kind"]
        and target["canonical_unit"] == definition["canonical_unit"],
        f"{identifier}: target kind/unit drift",
    )
    observation = fact["observation"]
    expected_shape = (
        "scalar"
        if target["requirement_kind"] == "parameter"
        else "range"
    )
    require(
        observation["shape"] == expected_shape,
        f"{identifier}: {target['requirement_kind']} requires "
        f"{expected_shape} observation",
    )
    require(
        observation["normalized_unit"] == definition["canonical_unit"],
        f"{identifier}: normalized unit is not canonical",
    )
    conversion = observation["conversion"]
    scale = _finite(conversion["scale"], f"{identifier}/conversion/scale")
    offset = _finite(conversion["offset"], f"{identifier}/conversion/offset")
    require(scale != 0.0, f"{identifier}: zero conversion scale")
    if conversion["kind"] == "identity":
        require(
            scale == 1.0
            and offset == 0.0
            and conversion["expression"] is None
            and observation["source_unit"] == observation["normalized_unit"],
            f"{identifier}: invalid identity conversion",
        )
    elif conversion["kind"] == "exact_linear_si":
        require(
            conversion["expression"] is not None,
            f"{identifier}: SI conversion expression missing",
        )
    else:
        require(
            conversion["expression"] is not None,
            f"{identifier}: derivation expression missing",
        )
    if observation["shape"] == "scalar":
        source = _finite(
            observation["source_value"],
            f"{identifier}/source_value",
        )
        normalized = _finite(
            observation["normalized_value"],
            f"{identifier}/normalized_value",
        )
        if conversion["kind"] != "reviewed_derivation":
            require(
                _close(normalized, source * scale + offset),
                f"{identifier}: normalized scalar conversion mismatch",
            )
    else:
        source_minimum = _finite(
            observation["source_minimum"],
            f"{identifier}/source_minimum",
        )
        source_maximum = _finite(
            observation["source_maximum"],
            f"{identifier}/source_maximum",
        )
        normalized_minimum = _finite(
            observation["normalized_minimum"],
            f"{identifier}/normalized_minimum",
        )
        normalized_maximum = _finite(
            observation["normalized_maximum"],
            f"{identifier}/normalized_maximum",
        )
        require(
            source_minimum <= source_maximum
            and normalized_minimum <= normalized_maximum,
            f"{identifier}: inverted range",
        )
        if conversion["kind"] != "reviewed_derivation":
            converted = sorted(
                [
                    source_minimum * scale + offset,
                    source_maximum * scale + offset,
                ]
            )
            require(
                _close(normalized_minimum, converted[0])
                and _close(normalized_maximum, converted[1]),
                f"{identifier}: normalized range conversion mismatch",
            )

    evidence = fact["evidence"]
    require(
        evidence["class"] in MANUAL_EVIDENCE_CLASSES,
        f"{identifier}: fitted/bench evidence is not a manual source fact",
    )
    uncertainty = evidence["uncertainty"]
    bounds = (
        uncertainty["lower"],
        uncertainty["upper"],
        uncertainty["unit"],
        uncertainty["coverage_probability"],
    )
    review = fact["review"]
    require(
        review["status"] == "accepted",
        f"{identifier}: lifecycle output must be accepted",
    )
    require(
        evidence["extractor"]["role_id"] == "plant_source_extractor"
        and review["reviewer"]["role_id"] == "plant_fact_reviewer"
        and evidence["extractor"]["actor_id"]
        != review["reviewer"]["actor_id"],
        f"{identifier}: source fact review is not independent",
    )
    require(
        all(value is not None for value in bounds),
        f"{identifier}: accepted fact requires bounded uncertainty",
    )
    lower = _finite(bounds[0], f"{identifier}/uncertainty/lower")
    upper = _finite(bounds[1], f"{identifier}/uncertainty/upper")
    require(lower <= upper, f"{identifier}: inverted uncertainty")
    require(
        bounds[2] == definition["canonical_unit"],
        f"{identifier}: uncertainty unit is not canonical",
    )
    require(
        not fact["support_granted"]
        and not fact["physical_motion_authority"],
        f"{identifier}: authority promotion",
    )


def load_source_facts(
    *,
    fact_schema: dict[str, Any],
    models: dict[str, dict[str, Any]],
    occurrences: dict[str, dict[str, Any]],
    candidate_manuals_by_model: dict[str, set[str]],
    candidate_index: dict[
        str, tuple[dict[str, Any], dict[str, Any]]
    ],
    candidate_registry_sha256: str,
    decision_registry: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    facts: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    expected_entries = {
        item["fact_id"]: item
        for item in decision_registry["active_source_facts"]
    }
    actual_files = {
        path.stem: path for path in sorted(FACT_DIRECTORY.glob("*.json"))
    }
    require(
        set(actual_files) == set(expected_entries),
        "candidate decision registry/source-fact file set drift",
    )
    for identifier, path in sorted(actual_files.items()):
        fact = load_json(path)
        validate_source_fact(
            fact,
            fact_schema=fact_schema,
            models=models,
            occurrences=occurrences,
            candidate_manuals_by_model=candidate_manuals_by_model,
            candidate_index=candidate_index,
            candidate_registry_sha256=candidate_registry_sha256,
        )
        require(
            path.stem == fact["fact_id"],
            f"{path}: filename must equal fact_id",
        )
        require(
            path.read_text(encoding="utf-8") == canonical_json(fact),
            f"{path}: source fact JSON is not canonical",
        )
        require(
            fact["fact_id"] not in hashes,
            f"{path}: duplicate source fact ID",
        )
        entry = expected_entries[identifier]
        require(
            entry["fact_sha256"] == sha_file(path)
            and entry["candidate_id"]
            == fact["provenance"]["candidate_id"]
            and entry["submission_id"] == fact["review"]["submission_id"]
            and entry["acceptance_event_id"]
            == fact["review"]["acceptance_event_id"]
            and entry["model_key"] == fact["model_identity"]["model_key"]
            and entry["target_field_id"]
            == f"{fact['target']['domain']}.{fact['target']['name']}",
            f"{path}: decision registry/fact entry drift",
        )
        require(
            fact["review"][
                "candidate_decision_registry_generation_sha256"
            ]
            == decision_registry["registry_generation_sha256"],
            f"{path}: decision registry generation drift",
        )
        facts.append(fact)
        hashes[fact["fact_id"]] = sha_file(path)
    return facts, hashes


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def _html_text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def render_html(value: dict[str, Any]) -> str:
    summary = value["summary"]
    manuals = {
        item["document_occurrence_id"]: item
        for item in value["candidate_product_manuals"]
    }
    model_rows: list[str] = []
    detail_rows: list[str] = []
    for model in value["models"]:
        states = (
            model["parameter_evidence"]
            + model["operating_envelope_evidence"]
        )
        counts = Counter(item["status"] for item in states)
        model_rows.append(
            "<tr>"
            f"<td><a href=\"#{_html_text(model['model_key'])}\">"
            f"{_html_text(model['model'])}</a></td>"
            f"<td>{_html_text(model['series'])}</td>"
            f"<td>{_html_text(model['package_revision'])}</td>"
            f"<td>{len(model['candidate_product_manual_occurrence_ids'])}</td>"
            f"<td>{counts['accepted_source_fact']}</td>"
            f"<td>{counts['candidate_unreviewed']}</td>"
            f"<td>{counts['missing']}</td>"
            f"<td>{_html_text(model['plant_status'])}</td>"
            "</tr>"
        )
        manual_links = []
        for identifier in model["candidate_product_manual_occurrence_ids"]:
            manual = manuals[identifier]
            relative = (
                "../../../../assets/vendor/myactuator/docs/"
                + urllib.parse.quote(
                    manual["vendor_relative_path"],
                    safe="/()",
                )
            )
            manual_links.append(
                f"<li><a href=\"{_html_text(relative)}\">"
                f"{_html_text(manual['file_name'])}</a>"
                f"<br><code>{_html_text(identifier)}</code> · "
                f"<code>{_html_text(manual['file_sha256'])}</code></li>"
            )
        field_rows = []
        for state in states:
            candidate_ids = ", ".join(state["candidate_fact_ids"]) or "—"
            blocker = ", ".join(state["blockers"]) or "—"
            field_rows.append(
                "<tr>"
                f"<td><code>{_html_text(state['field_id'])}</code></td>"
                f"<td>{_html_text(state['expected_unit'])}</td>"
                f"<td class=\"status-{_html_text(state['status'])}\">"
                f"{_html_text(state['status'])}</td>"
                f"<td><code>{_html_text(candidate_ids)}</code></td>"
                f"<td><code>{_html_text(blocker)}</code></td>"
                "</tr>"
            )
        detail_rows.append(
            f"<details id=\"{_html_text(model['model_key'])}\">"
            f"<summary>{_html_text(model['series'])} / "
            f"{_html_text(model['model'])} · "
            f"{counts['accepted_source_fact']} accepted · "
            f"{counts['candidate_unreviewed']} pending · "
            f"{counts['missing']} missing</summary>"
            "<h3>Candidate pinned manuals</h3>"
            f"<ul>{''.join(manual_links)}</ul>"
            "<h3>Required evidence matrix</h3>"
            "<table><thead><tr><th>Field</th><th>SI unit</th>"
            "<th>Status</th><th>Candidate facts</th><th>Blocker</th>"
            f"</tr></thead><tbody>{''.join(field_rows)}</tbody></table>"
            "</details>"
        )
    return (
        "<!doctype html>\n"
        "<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>MYACTUATOR plant evidence ledger</title>"
        "<style>"
        ":root{color-scheme:light dark;font-family:system-ui,sans-serif}"
        "body{max-width:1500px;margin:auto;padding:1.5rem;line-height:1.4}"
        "code{font-size:.78rem;overflow-wrap:anywhere}"
        "table{width:100%;border-collapse:collapse;margin:.8rem 0 1.4rem}"
        "th,td{border:1px solid #7776;padding:.45rem;text-align:left;"
        "vertical-align:top}"
        "th{position:sticky;top:0;background:Canvas}"
        "details{border:1px solid #7776;border-radius:.45rem;"
        "padding:.7rem;margin:.7rem 0}"
        "summary{cursor:pointer;font-weight:650}"
        ".cards{display:grid;grid-template-columns:repeat(auto-fit,"
        "minmax(12rem,1fr));gap:.7rem;margin:1rem 0}"
        ".card{border:1px solid #7776;border-radius:.45rem;padding:.8rem}"
        ".number{font-size:1.6rem;font-weight:750;display:block}"
        ".status-missing{color:#c33}.status-candidate_unreviewed{color:#b70}"
        ".status-accepted_source_fact{color:#187b2e}"
        "</style></head><body>"
        "<h1>MYACTUATOR plant evidence ledger</h1>"
        "<p>This static local view is a navigation and denial artifact. "
        "Candidate documents and unreviewed facts do not fill values, create "
        "a real plant, enable hardware, or grant motor support.</p>"
        "<div class=\"cards\">"
        f"<div class=\"card\"><span class=\"number\">{summary['model_count']}"
        "</span>catalog models</div>"
        f"<div class=\"card\"><span class=\"number\">"
        f"{summary['model_parameter_requirement_count']}</span>"
        "parameter requirements</div>"
        f"<div class=\"card\"><span class=\"number\">"
        f"{summary['model_operating_envelope_requirement_count']}</span>"
        "envelope requirements</div>"
        f"<div class=\"card\"><span class=\"number\">"
        f"{summary['accepted_source_fact_count']}</span>"
        "accepted source facts</div>"
        f"<div class=\"card\"><span class=\"number\">"
        f"{summary['runtime_plant_count']}</span>runtime plants</div>"
        "</div>"
        "<h2>Model coverage</h2>"
        "<table><thead><tr><th>Model</th><th>Series</th><th>Package</th>"
        "<th>Manuals</th><th>Accepted</th><th>Pending</th><th>Missing</th>"
        f"<th>Plant</th></tr></thead><tbody>{''.join(model_rows)}</tbody>"
        "</table><h2>Per-model evidence</h2>"
        f"{''.join(detail_rows)}"
        "<footer><p>Ledger record SHA-256: <code>"
        f"{_html_text(value['integrity']['record_sha256'])}</code></p></footer>"
        "</body></html>\n"
    )


def _requirement_state(
    definition: dict[str, str],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    require(
        len(candidates) <= 1,
        f"{definition['field_id']}: multiple accepted source facts",
    )
    if candidates:
        selected = candidates[0]
        observation = selected["observation"]
        value: float | dict[str, float] = (
            observation["normalized_value"]
            if observation["shape"] == "scalar"
            else {
                "minimum": observation["normalized_minimum"],
                "maximum": observation["normalized_maximum"],
            }
        )
        return {
            "field_id": definition["field_id"],
            "expected_unit": definition["canonical_unit"],
            "status": "accepted_source_fact",
            "candidate_fact_ids": [
                fact["fact_id"] for fact in candidates
            ],
            "selected_fact_id": selected["fact_id"],
            "value": value,
            "uncertainty": selected["evidence"]["uncertainty"],
            "blockers": [],
        }
    return {
        "field_id": definition["field_id"],
        "expected_unit": definition["canonical_unit"],
        "status": "missing",
        "candidate_fact_ids": [],
        "selected_fact_id": None,
        "value": None,
        "uncertainty": None,
        "blockers": ["exact_model_source_fact_missing"],
    }


def build() -> dict[str, Any]:
    catalog = load_catalog()
    applicability = load_json(APPLICABILITY)
    plant_registry = load_json(PLANT_REGISTRY)
    candidate_registry = load_json(CANDIDATE_REGISTRY)
    decision_registry = load_json(DECISION_REGISTRY)
    fact_schema = load_json(FACT_SCHEMA)
    Draft202012Validator.check_schema(fact_schema)
    decision_schema = load_json(DECISION_REGISTRY_SCHEMA)
    decision_errors = sorted(
        Draft202012Validator(decision_schema).iter_errors(
            decision_registry
        ),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if decision_errors:
        error = decision_errors[0]
        raise PlantEvidenceLedgerError(
            "candidate decision registry schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        decision_registry["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(decision_registry)),
        "candidate decision registry digest drift",
    )
    candidate_registry_sha256 = sha_file(CANDIDATE_REGISTRY)
    require(
        candidate_registry["artifact_id"]
        == "myactuator-plant-spec-candidate-registry"
        and candidate_registry["summary"]["candidate_count"] == 531
        and decision_registry["sources"]["candidate_registry_sha256"]
        == candidate_registry_sha256,
        "candidate/decision registry source drift",
    )
    candidate_index: dict[
        str, tuple[dict[str, Any], dict[str, Any]]
    ] = {}
    for table in candidate_registry["model_tables"]:
        for candidate in table["candidates"]:
            require(
                candidate["candidate_id"] not in candidate_index,
                "duplicate source candidate",
            )
            candidate_index[candidate["candidate_id"]] = (
                table,
                candidate,
            )
    require(len(candidate_index) == 531, "source candidate index drift")
    require(
        applicability["summary"]["model_count"] == 44,
        "applicability registry is not model-complete",
    )
    require(
        plant_registry["summary"]["models"] == 44,
        "plant registry is not model-complete",
    )
    applicability_models = {
        item["model_key"]: item for item in applicability["models"]
    }
    catalog_identities = [
        (row["series"], row["model"], row["package_revision"])
        for row in catalog
    ]
    require(
        [
            (item["series"], item["model"], item["package_revision"])
            for item in applicability["models"]
        ]
        == catalog_identities,
        "catalog/applicability model order or revision differs",
    )
    packages = {
        item["package_id"]: item
        for item in applicability["document_packages"]
    }
    occurrences = {
        item["occurrence_id"]: item
        for item in applicability["document_file_occurrences"]
    }
    product_manuals = [
        item
        for item in applicability["document_file_occurrences"]
        if item["source_claim"]["document_scope"] == "product_manual"
    ]
    require(
        len(product_manuals) == 15,
        "expected exactly 15 candidate product manual occurrences",
    )
    product_manual_ids = {
        item["occurrence_id"] for item in product_manuals
    }
    candidate_manuals_by_model: dict[str, set[str]] = {}
    for model_key, model in applicability_models.items():
        candidate_manuals_by_model[model_key] = {
            occurrence_id
            for package_id in model["candidate_package_ids"]
            for occurrence_id in packages[package_id]["file_occurrence_ids"]
            if occurrence_id in product_manual_ids
        }
        require(
            candidate_manuals_by_model[model_key],
            f"{model_key}: candidate product manual missing",
        )
    facts, fact_hashes = load_source_facts(
        fact_schema=fact_schema,
        models=applicability_models,
        occurrences=occurrences,
        candidate_manuals_by_model=candidate_manuals_by_model,
        candidate_index=candidate_index,
        candidate_registry_sha256=candidate_registry_sha256,
        decision_registry=decision_registry,
    )
    facts_by_model_and_field: dict[
        tuple[str, str], list[dict[str, Any]]
    ] = {}
    for fact in facts:
        target = fact["target"]
        key = (
            fact["model_identity"]["model_key"],
            f"{target['domain']}.{target['name']}",
        )
        facts_by_model_and_field.setdefault(key, []).append(fact)

    parameter_definitions = requirement_catalog()
    envelope_definitions = envelope_catalog()
    coverage_by_identity = {
        (item["series"], item["model"]): item
        for item in plant_registry["model_coverage"]
    }
    models: list[dict[str, Any]] = []
    for row in catalog:
        applicability_model = next(
            item
            for item in applicability["models"]
            if (
                item["series"],
                item["model"],
                item["package_revision"],
            )
            == (
                row["series"],
                row["model"],
                row["package_revision"],
            )
        )
        model_key = applicability_model["model_key"]
        parameters = [
            _requirement_state(
                definition,
                facts_by_model_and_field.get(
                    (model_key, definition["field_id"]),
                    [],
                ),
            )
            for definition in parameter_definitions
        ]
        envelopes = [
            _requirement_state(
                definition,
                facts_by_model_and_field.get(
                    (model_key, definition["field_id"]),
                    [],
                ),
            )
            for definition in envelope_definitions
        ]
        complete = all(
            item["status"] == "accepted_source_fact"
            for item in parameters + envelopes
        )
        coverage = coverage_by_identity[(row["series"], row["model"])]
        correlated = coverage["status"] in {
            "partially_validated",
            "validated",
        }
        blockers: list[str] = []
        if not complete:
            blockers.append("source_fact_matrix_incomplete")
        if not coverage["plant_ids"]:
            blockers.append("qualified_runtime_plant_parameter_set_missing")
        if not correlated:
            blockers.append("physical_correlation_evidence_missing")
        model_facts = [
            fact
            for fact in facts
            if fact["model_identity"]["model_key"] == model_key
        ]
        models.append(
            {
                "model_key": model_key,
                "series": row["series"],
                "model": row["model"],
                "package_revision": row["package_revision"],
                "candidate_product_manual_occurrence_ids": sorted(
                    candidate_manuals_by_model[model_key]
                ),
                "source_fact_ids": [
                    fact["fact_id"] for fact in model_facts
                ],
                "parameter_evidence": parameters,
                "operating_envelope_evidence": envelopes,
                "source_fact_complete": complete,
                "correlation_complete": correlated,
                "runtime_plant_ids": coverage["plant_ids"],
                "plant_status": coverage["status"],
                "blockers": blockers,
                "support_granted": False,
            }
        )

    candidate_manual_rows = [
        {
            "document_occurrence_id": item["occurrence_id"],
            "package_id": item["package_id"],
            "series": item["series"],
            "document_set": item["document_set"],
            "file_name": item["file_name"],
            "vendor_relative_path": item["vendor_relative_path"],
            "file_sha256": item["file_sha256"],
            "bytes": item["bytes"],
            "candidate_only": True,
        }
        for item in product_manuals
    ]
    parameter_states = [
        state for model in models for state in model["parameter_evidence"]
    ]
    envelope_states = [
        state
        for model in models
        for state in model["operating_envelope_evidence"]
    ]
    reviews = Counter(fact["review"]["status"] for fact in facts)
    value = {
        "schema_version": VERSION,
        "artifact_id": "myactuator-plant-evidence-ledger",
        "authority": (
            "source_navigation_missing_evidence_and_admission_denial_only"
        ),
        "sources": {
            "catalog_sha256": sha_file(CATALOG),
            "protocol_applicability_registry_sha256": sha_file(
                APPLICABILITY
            ),
            "plant_runtime_registry_sha256": sha_file(PLANT_REGISTRY),
            "plant_spec_candidate_registry_sha256": (
                candidate_registry_sha256
            ),
            "plant_candidate_decision_registry_sha256": sha_file(
                DECISION_REGISTRY
            ),
            "source_fact_schema_sha256": sha_file(FACT_SCHEMA),
            "source_fact_file_sha256": dict(sorted(fact_hashes.items())),
        },
        "policy": {
            "all_catalog_models_required": True,
            "missing_is_null_and_blocking": True,
            "family_default_forbidden": True,
            "silent_unit_conversion_forbidden": True,
            "source_hash_page_and_locator_required": True,
            "generated_extraction_cannot_accept": True,
            "candidate_lifecycle_materialization_required": True,
            "independent_review_required": True,
            "uncertainty_classes_non_substitutable": True,
            "source_fit_correlation_states_separate": True,
            "operating_envelope_required": True,
            "synthetic_evidence_never_fills_real_model": True,
            "runtime_plant_requires_qualified_parameter_set": True,
            "ledger_never_grants_motor_support": True,
        },
        "parameter_catalog": parameter_definitions,
        "operating_envelope_catalog": envelope_definitions,
        "candidate_product_manuals": candidate_manual_rows,
        "source_facts": facts,
        "models": models,
        "summary": {
            "model_count": len(models),
            "parameter_domain_count": len(PARAMETER_FIELDS),
            "required_parameter_field_count": len(parameter_definitions),
            "model_parameter_requirement_count": len(parameter_states),
            "required_operating_envelope_field_count": len(
                envelope_definitions
            ),
            "model_operating_envelope_requirement_count": len(
                envelope_states
            ),
            "candidate_product_manual_occurrence_count": len(
                candidate_manual_rows
            ),
            "candidate_model_manual_relationship_count": sum(
                len(model["candidate_product_manual_occurrence_ids"])
                for model in models
            ),
            "source_fact_count": len(facts),
            "unreviewed_source_fact_count": reviews["unreviewed"],
            "accepted_source_fact_count": reviews["accepted"],
            "missing_parameter_requirement_count": sum(
                state["status"] != "accepted_source_fact"
                for state in parameter_states
            ),
            "missing_operating_envelope_requirement_count": sum(
                state["status"] != "accepted_source_fact"
                for state in envelope_states
            ),
            "source_fact_complete_model_count": sum(
                model["source_fact_complete"] for model in models
            ),
            "correlated_model_count": sum(
                model["correlation_complete"] for model in models
            ),
            "runtime_plant_count": len(plant_registry["parameter_sets"]),
            "supported_model_count": 0,
        },
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(value)
    return value


def validate(
    value: dict[str, Any],
    *,
    verify_sources: bool = True,
) -> None:
    schema = load_json(LEDGER_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise PlantEvidenceLedgerError(
            "ledger schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "ledger record digest drift",
    )
    require(
        value["parameter_catalog"] == requirement_catalog(),
        "parameter requirement catalog drift",
    )
    require(
        value["operating_envelope_catalog"] == envelope_catalog(),
        "operating-envelope requirement catalog drift",
    )
    catalog = load_catalog()
    require(
        [
            (model["series"], model["model"], model["package_revision"])
            for model in value["models"]
        ]
        == [
            (row["series"], row["model"], row["package_revision"])
            for row in catalog
        ],
        "ledger model identity/order differs from catalog",
    )
    manual_ids = {
        item["document_occurrence_id"]
        for item in value["candidate_product_manuals"]
    }
    require(
        len(manual_ids) == 15,
        "candidate product manual identity is not unique",
    )
    fact_ids = [fact["fact_id"] for fact in value["source_facts"]]
    require(
        len(fact_ids) == len(set(fact_ids)),
        "source fact identity is not unique",
    )
    expected_parameters = [
        item["field_id"] for item in requirement_catalog()
    ]
    expected_envelopes = [
        item["field_id"] for item in envelope_catalog()
    ]
    for model in value["models"]:
        require(
            set(model["candidate_product_manual_occurrence_ids"])
            <= manual_ids,
            f"{model['model_key']}: unknown candidate product manual",
        )
        require(
            [item["field_id"] for item in model["parameter_evidence"]]
            == expected_parameters,
            f"{model['model_key']}: parameter matrix drift",
        )
        require(
            [
                item["field_id"]
                for item in model["operating_envelope_evidence"]
            ]
            == expected_envelopes,
            f"{model['model_key']}: operating-envelope matrix drift",
        )
        for state in (
            model["parameter_evidence"]
            + model["operating_envelope_evidence"]
        ):
            if state["status"] == "accepted_source_fact":
                require(
                    state["selected_fact_id"] is not None
                    and state["value"] is not None
                    and state["uncertainty"] is not None
                    and not state["blockers"],
                    f"{model['model_key']}/{state['field_id']}: "
                    "partial accepted state",
                )
            else:
                require(
                    state["selected_fact_id"] is None
                    and state["value"] is None
                    and state["uncertainty"] is None
                    and state["blockers"],
                    f"{model['model_key']}/{state['field_id']}: "
                    "missing/candidate value leakage",
                )
        require(
            model["source_fact_complete"]
            == all(
                state["status"] == "accepted_source_fact"
                for state in (
                    model["parameter_evidence"]
                    + model["operating_envelope_evidence"]
                )
            ),
            f"{model['model_key']}: source completeness drift",
        )
        require(
            not model["support_granted"],
            f"{model['model_key']}: ledger support promotion",
        )
    parameter_states = [
        state
        for model in value["models"]
        for state in model["parameter_evidence"]
    ]
    envelope_states = [
        state
        for model in value["models"]
        for state in model["operating_envelope_evidence"]
    ]
    reviews = Counter(
        fact["review"]["status"] for fact in value["source_facts"]
    )
    expected_summary = {
        "model_count": 44,
        "parameter_domain_count": 7,
        "required_parameter_field_count": 34,
        "model_parameter_requirement_count": 1496,
        "required_operating_envelope_field_count": 4,
        "model_operating_envelope_requirement_count": 176,
        "candidate_product_manual_occurrence_count": 15,
        "candidate_model_manual_relationship_count": sum(
            len(model["candidate_product_manual_occurrence_ids"])
            for model in value["models"]
        ),
        "source_fact_count": len(value["source_facts"]),
        "unreviewed_source_fact_count": reviews["unreviewed"],
        "accepted_source_fact_count": reviews["accepted"],
        "missing_parameter_requirement_count": sum(
            state["status"] != "accepted_source_fact"
            for state in parameter_states
        ),
        "missing_operating_envelope_requirement_count": sum(
            state["status"] != "accepted_source_fact"
            for state in envelope_states
        ),
        "source_fact_complete_model_count": sum(
            model["source_fact_complete"] for model in value["models"]
        ),
        "correlated_model_count": sum(
            model["correlation_complete"] for model in value["models"]
        ),
        "runtime_plant_count": sum(
            bool(model["runtime_plant_ids"]) for model in value["models"]
        ),
        "supported_model_count": 0,
    }
    require(
        value["summary"] == expected_summary,
        "plant evidence ledger summary drift",
    )
    require(
        not value["support_granted"]
        and not value["physical_motion_authority"],
        "plant evidence ledger authority promotion",
    )
    if verify_sources:
        expected_sources = {
            "catalog_sha256": sha_file(CATALOG),
            "protocol_applicability_registry_sha256": sha_file(
                APPLICABILITY
            ),
            "plant_runtime_registry_sha256": sha_file(PLANT_REGISTRY),
            "plant_spec_candidate_registry_sha256": sha_file(
                CANDIDATE_REGISTRY
            ),
            "plant_candidate_decision_registry_sha256": sha_file(
                DECISION_REGISTRY
            ),
            "source_fact_schema_sha256": sha_file(FACT_SCHEMA),
            "source_fact_file_sha256": {
                path.stem: sha_file(path)
                for path in sorted(FACT_DIRECTORY.glob("*.json"))
            },
        }
        require(
            value["sources"] == expected_sources,
            "plant evidence ledger source drift",
        )


def check_or_write(*, check: bool) -> None:
    value = build()
    validate(value)
    content = canonical_json(value)
    html_content = render_html(value)
    if check:
        require(OUTPUT.is_file(), f"generated ledger missing: {OUTPUT}")
        require(
            HTML_OUTPUT.is_file(),
            f"generated ledger view missing: {HTML_OUTPUT}",
        )
        require(
            OUTPUT.read_text(encoding="utf-8") == content,
            "tracked plant evidence ledger differs from inputs",
        )
        require(
            HTML_OUTPUT.read_text(encoding="utf-8") == html_content,
            "tracked plant evidence ledger view differs from inputs",
        )
        return
    atomic_write(OUTPUT, content)
    atomic_write(HTML_OUTPUT, html_content)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the tracked ledger instead of writing it",
    )
    arguments = parser.parse_args(argv)
    try:
        check_or_write(check=arguments.check)
    except PlantEvidenceLedgerError as error:
        parser.error(str(error))
    mode = "verified" if arguments.check else "generated"
    print(f"Plant evidence ledger {mode}: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
