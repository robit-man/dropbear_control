#!/usr/bin/env python3
"""Generate the source-bound MYACTUATOR/Dropbear coverage dashboard."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "generated/myactuator/coverage_dashboard"
GENERATOR = Path(__file__).resolve()
SCHEMA = ROOT / "schemas/myactuator-coverage-dashboard.schema.json"
REQUIREMENTS = ROOT / ".aiwg/requirements/system-requirements.md"
TRACEABILITY = ROOT / ".aiwg/requirements/traceability-matrix.md"
TEST_CATALOG = ROOT / ".aiwg/testing/test-catalog.md"
MASTER_PLAN = ROOT / ".aiwg/planning/master-program-plan.md"
PHASE_GATES = ROOT / ".aiwg/gates/phase-gates.md"
TEST_ENTRY = ROOT / "tools/test_all.sh"
SIMULATOR = ROOT / "generated/myactuator/simulator/runtime_catalog.json"
CAD_CAMPAIGN = ROOT / "generated/myactuator/cad/campaign/campaign.json"
PLANT_LEDGER = (
    ROOT / "generated/myactuator/plant/evidence_ledger/ledger.json"
)
PLANT_CANDIDATE_DECISIONS = (
    ROOT / "generated/myactuator/plant/candidate_decisions/registry.json"
)
PLANT_PARAMETER_SETS = (
    ROOT / "generated/myactuator/plant/parameter_sets/registry.json"
)
PLANT_RUNTIME_ADAPTERS = (
    ROOT / "generated/myactuator/plant/runtime_adapters/registry.json"
)
PLANT_RUNTIME_ADAPTERS_V2 = (
    ROOT / "generated/myactuator/plant/runtime_adapters_v2/registry.json"
)
PROTOCOL = (
    ROOT / "generated/myactuator/protocol_applicability/registry.json"
)
REVIEW_QUEUE = (
    ROOT / "generated/myactuator/evidence_review/queue.json"
)
EVIDENCE_INTAKE = (
    ROOT / "generated/myactuator/evidence_intake/manifest.json"
)
ASSIGNMENTS = ROOT / "assets/myactuator/reviewer_assignments.json"
SOURCE_REGISTRY = (
    ROOT / "generated/dropbear_source_registry_v2/registry.json"
)
GRAPH_REGISTRY = (
    ROOT / "generated/dropbear_graph_registry_v2/registry.json"
)
READINESS = ROOT / "generated/dropbear_readiness/readiness.json"
ADAPTER_STATUS = ROOT / "generated/can_adapter_intake/status.json"
INSTALLED_INVENTORY = (
    ROOT / "assets/dropbear/installed_inventory_template.json"
)

VERSION = "myactuator-coverage-dashboard/1"
REQUIREMENT_RE = re.compile(r"^[A-Z]{2,3}-\d{3}$")
TEST_RE = re.compile(r"^TST-[A-Z]+-\d{3}$")
WP_RE = re.compile(r"^WP-\d{3}$")
GATE_RE = re.compile(r"^G[0-7]$")
TEST_STATUSES = (
    "PLANNED",
    "EXISTS-OFFLINE",
    "EXISTS-BASELINE",
    "PHYSICAL-HOLD",
)


class CoverageDashboardError(ValueError):
    """A dashboard input, projection, or output is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CoverageDashboardError(message)


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


def sha_file(path: Path) -> str:
    try:
        return sha_bytes(path.read_bytes())
    except OSError as error:
        raise CoverageDashboardError(f"cannot hash {path}: {error}") from error


def stable_id(prefix: str, value: Any) -> str:
    return prefix + sha_bytes(canonical_bytes(value))[:20]


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CoverageDashboardError(f"cannot load {path}: {error}") from error
    require(isinstance(value, dict), f"{path}: root must be an object")
    return value


def verify_embedded_digest(path: Path, value: dict[str, Any]) -> None:
    integrity = value.get("integrity")
    if integrity is None:
        return
    require(
        isinstance(integrity, dict)
        and isinstance(integrity.get("record_sha256"), str),
        f"{path}: malformed integrity block",
    )
    require(
        integrity["record_sha256"] == sha_bytes(digest_payload(value)),
        f"{path}: embedded digest drift",
    )


def input_paths() -> tuple[Path, ...]:
    return (
        GENERATOR,
        SCHEMA,
        REQUIREMENTS,
        TRACEABILITY,
        TEST_CATALOG,
        MASTER_PLAN,
        PHASE_GATES,
        TEST_ENTRY,
        SIMULATOR,
        CAD_CAMPAIGN,
        PLANT_LEDGER,
        PLANT_CANDIDATE_DECISIONS,
        PLANT_PARAMETER_SETS,
        PLANT_RUNTIME_ADAPTERS,
        PLANT_RUNTIME_ADAPTERS_V2,
        PROTOCOL,
        REVIEW_QUEUE,
        EVIDENCE_INTAKE,
        ASSIGNMENTS,
        SOURCE_REGISTRY,
        GRAPH_REGISTRY,
        READINESS,
        ADAPTER_STATUS,
        INSTALLED_INVENTORY,
    )


def source_records() -> list[dict[str, str]]:
    records = []
    for path in input_paths():
        require(path.is_file(), f"dashboard source missing: {path}")
        records.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha_file(path),
            }
        )
    return records


def markdown_rows(path: Path) -> list[list[str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise CoverageDashboardError(f"cannot read {path}: {error}") from error
    rows: list[list[str]] = []
    for line in lines:
        if not line.startswith("| ") or line.startswith("|---"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    return rows


def unique_ordered(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def expand_prefixed_refs(cell: str, prefix_pattern: str) -> list[str]:
    pattern = re.compile(
        rf"({prefix_pattern})(\d{{3}})(?:\.\.(\d{{3}}))?"
    )
    values: list[str] = []
    for match in pattern.finditer(cell):
        prefix, start_text, end_text = match.groups()
        start = int(start_text)
        end = int(end_text or start_text)
        require(end >= start, f"descending reference range: {match.group(0)}")
        values.extend(f"{prefix}{number:03d}" for number in range(start, end + 1))
    return unique_ordered(values)


def expand_wp_refs(cell: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"(?<![A-Z0-9])(\d{3})(?:\.\.(\d{3}))?", cell):
        start = int(match.group(1))
        end = int(match.group(2) or match.group(1))
        require(end >= start, f"descending WP range: {match.group(0)}")
        require(
            start % 10 == 0 and end % 10 == 0,
            f"non-work-package numeric reference: {match.group(0)}",
        )
        values.extend(f"WP-{number:03d}" for number in range(start, end + 1, 10))
    return unique_ordered(values)


def parse_requirements() -> list[dict[str, Any]]:
    records = []
    for cells in markdown_rows(REQUIREMENTS):
        if not cells or not REQUIREMENT_RE.fullmatch(cells[0]):
            continue
        require(len(cells) == 4, f"{cells[0]}: malformed requirement row")
        records.append(
            {
                "requirement_id": cells[0],
                "priority": cells[1],
                "statement": cells[2],
                "basis": cells[3],
            }
        )
    require(len(records) == 77, f"expected 77 requirements; found {len(records)}")
    identifiers = [record["requirement_id"] for record in records]
    require(len(set(identifiers)) == 77, "duplicate requirement ID")
    require(
        Counter(record["priority"] for record in records)
        == {"P0": 39, "P1": 37, "P2": 1},
        "requirement priority partition drift",
    )
    return records


def parse_traceability() -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    for cells in markdown_rows(TRACEABILITY):
        if not cells or not REQUIREMENT_RE.fullmatch(cells[0]):
            continue
        require(len(cells) == 6, f"{cells[0]}: malformed trace row")
        require(cells[0] not in records, f"duplicate trace row: {cells[0]}")
        records[cells[0]] = {
            "design": cells[1],
            "work_packages": cells[2],
            "planned_verification": cells[3],
            "gates": cells[4],
            "evidence_now": cells[5],
        }
    return records


def parse_tests(
    requirement_ids: set[str],
    wp_ids: set[str],
) -> list[dict[str, Any]]:
    records = []
    for cells in markdown_rows(TEST_CATALOG):
        if not cells or not TEST_RE.fullmatch(cells[0]):
            continue
        require(len(cells) == 6, f"{cells[0]}: malformed test row")
        requirement_refs = expand_prefixed_refs(
            cells[3],
            r"[A-Z]{2,3}-",
        )
        work_package_refs = expand_wp_refs(cells[4])
        require(
            set(requirement_refs) <= requirement_ids,
            f"{cells[0]}: unknown requirement reference",
        )
        require(
            set(work_package_refs) <= wp_ids,
            f"{cells[0]}: unknown work-package reference",
        )
        require(cells[5] in TEST_STATUSES, f"{cells[0]}: unknown test status")
        records.append(
            {
                "test_id": cells[0],
                "level": cells[1],
                "purpose": cells[2],
                "requirement_ids": requirement_refs,
                "work_package_ids": work_package_refs,
                "status": cells[5],
            }
        )
    require(len(records) == 140, f"expected 140 tests; found {len(records)}")
    identifiers = [record["test_id"] for record in records]
    require(len(set(identifiers)) == 140, "duplicate test ID")
    return records


def parse_work_packages(
    requirement_ids: set[str],
) -> list[dict[str, Any]]:
    records = []
    for cells in markdown_rows(MASTER_PLAN):
        if not cells or not WP_RE.fullmatch(cells[0]):
            continue
        require(len(cells) == 6, f"{cells[0]}: malformed work-package row")
        requirement_refs = expand_prefixed_refs(
            cells[3],
            r"[A-Z]{2,3}-",
        )
        require(
            set(requirement_refs) <= requirement_ids,
            f"{cells[0]}: unknown requirement reference",
        )
        if cells[5].startswith("DONE-OFFLINE"):
            lifecycle_state = "DONE-OFFLINE"
        elif cells[5].startswith("PHYSICAL-HOLD"):
            lifecycle_state = "PHYSICAL-HOLD"
        elif cells[5].startswith("OPEN"):
            lifecycle_state = "OPEN"
        elif cells[5].startswith("ACTIVE"):
            lifecycle_state = "ACTIVE"
        else:
            raise CoverageDashboardError(
                f"{cells[0]}: unknown lifecycle status {cells[5]}"
            )
        records.append(
            {
                "work_package_id": cells[0],
                "outcome": cells[1],
                "depends_on": cells[2],
                "dependency_work_package_ids": expand_wp_refs(cells[2]),
                "requirement_ids": requirement_refs,
                "exit_evidence": cells[4],
                "status": cells[5],
                "lifecycle_state": lifecycle_state,
            }
        )
    require(len(records) == 20, f"expected 20 work packages; found {len(records)}")
    identifiers = [record["work_package_id"] for record in records]
    expected = [f"WP-{number:03d}" for number in range(0, 200, 10)]
    require(identifiers == expected, "work-package coverage/order drift")
    known = set(identifiers)
    for record in records:
        require(
            set(record["dependency_work_package_ids"]) <= known,
            f"{record['work_package_id']}: unknown dependency",
        )
    return records


def parse_gates() -> list[dict[str, str]]:
    records = []
    for cells in markdown_rows(PHASE_GATES):
        if not cells:
            continue
        gate_id = cells[0].split(" ", 1)[0]
        if not GATE_RE.fullmatch(gate_id):
            continue
        require(len(cells) == 4, f"{gate_id}: malformed phase-gate row")
        name = cells[0][len(gate_id) :].lstrip(" —-")
        records.append(
            {
                "gate_id": gate_id,
                "name": name,
                "authorized_scope": cells[1],
                "required_evidence": cells[2],
                "hard_hold": cells[3],
                "pass_asserted": False,
            }
        )
    require(
        [record["gate_id"] for record in records]
        == [f"G{number}" for number in range(8)],
        "phase-gate coverage/order drift",
    )
    return records


def status_counts(tests: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(test["status"] for test in tests)
    return {status: counts[status] for status in TEST_STATUSES}


def model_projection(
    simulator: dict[str, Any],
) -> list[dict[str, Any]]:
    records = []
    for model in simulator["models"]:
        records.append(
            {
                "model_key": model["model_key"],
                "series": model["series"],
                "model": model["model"],
                "source_variant_ids": model["source_variant_ids"],
                "configuration_ids": model["configuration_ids"],
                "protocol_applicability_accepted": model[
                    "protocol_model_firmware_applicability_verified"
                ],
                "cad_accepted_configuration_count": model["cad"][
                    "accepted_configuration_count"
                ],
                "plant_status": model["plant"]["status"],
                "exact_model_geometry_ready": model["fidelity"][
                    "exact_model_geometry_ready"
                ],
                "exact_model_plant_ready": model["fidelity"][
                    "exact_model_plant_ready"
                ],
                "exact_model_simulation_ready": model["fidelity"][
                    "exact_model_simulation_ready"
                ],
                "physically_correlated_plant_ready": model["fidelity"][
                    "physically_correlated_plant_ready"
                ],
                "blockers": model["blockers"],
            }
        )
    return records


def cad_projection(campaign: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for configuration in campaign["configurations"]:
        records.append(
            {
                "configuration_id": configuration["configuration_id"],
                "variant_id": configuration["variant_id"],
                "model_key": configuration["model_key"],
                "series": configuration["series"],
                "model": configuration["model"],
                "source_structure": configuration["source_structure"],
                "selector_status": configuration["selector_status"],
                "review_status": configuration["review_status"],
                "review_lane": configuration["candidate_state"]["review_lane"],
                "packet_reviewable_now": configuration["candidate_state"][
                    "packet_reviewable_now"
                ],
                "current_action": configuration["candidate_state"][
                    "current_action"
                ],
                "unanswered_question_count": sum(
                    response["response"] is None
                    for response in configuration["question_responses"]
                ),
                "accepted_asset": configuration["accepted_asset"],
                "browser_releasable": configuration["browser_releasable"],
                "support_granted": configuration["support_granted"],
            }
        )
    return records


def criterion(
    criterion_id: str,
    label: str,
    required_count: int,
    observed_count: int,
    evidence_ref: str,
    blocker: str | None,
) -> dict[str, Any]:
    met = observed_count >= required_count
    return {
        "criterion_id": criterion_id,
        "label": label,
        "required_count": required_count,
        "observed_count": observed_count,
        "met": met,
        "evidence_ref": evidence_ref,
        "blocker": None if met else blocker,
    }


def assemble() -> dict[str, Any]:
    requirements = parse_requirements()
    requirement_ids = {record["requirement_id"] for record in requirements}
    work_packages = parse_work_packages(requirement_ids)
    wp_ids = {record["work_package_id"] for record in work_packages}
    tests = parse_tests(requirement_ids, wp_ids)
    tests_by_id = {record["test_id"]: record for record in tests}
    trace = parse_traceability()
    require(
        set(trace) == requirement_ids,
        "requirement/traceability coverage mismatch",
    )
    gates = parse_gates()
    gate_ids = {record["gate_id"] for record in gates}

    requirement_rows = []
    for requirement in requirements:
        identifier = requirement["requirement_id"]
        traced = trace[identifier]
        planned_tests = expand_prefixed_refs(
            traced["planned_verification"],
            r"TST-[A-Z]+-",
        )
        traced_wps = expand_wp_refs(traced["work_packages"])
        traced_gates = (
            [record["gate_id"] for record in gates]
            if traced["gates"] == "all"
            else unique_ordered(re.findall(r"G[0-7]", traced["gates"]))
        )
        require(planned_tests, f"{identifier}: no planned test")
        require(traced_wps, f"{identifier}: no work package")
        require(traced_gates, f"{identifier}: no gate")
        require(
            set(planned_tests) <= set(tests_by_id),
            f"{identifier}: unknown planned test",
        )
        require(
            set(traced_wps) <= wp_ids,
            f"{identifier}: unknown work package",
        )
        require(
            set(traced_gates) <= gate_ids,
            f"{identifier}: unknown phase gate",
        )
        mapped_tests = [tests_by_id[test_id] for test_id in planned_tests]
        requirement_rows.append(
            {
                **requirement,
                "design_refs": traced["design"],
                "work_package_ids": traced_wps,
                "planned_test_ids": planned_tests,
                "gate_ids": traced_gates,
                "evidence_now": traced["evidence_now"],
                "test_status_counts": status_counts(mapped_tests),
                "structurally_traced": True,
                "completion_asserted": False,
            }
        )

    json_paths = (
        SIMULATOR,
        CAD_CAMPAIGN,
        PLANT_LEDGER,
        PLANT_PARAMETER_SETS,
        PLANT_RUNTIME_ADAPTERS,
        PLANT_RUNTIME_ADAPTERS_V2,
        PROTOCOL,
        REVIEW_QUEUE,
        EVIDENCE_INTAKE,
        ASSIGNMENTS,
        SOURCE_REGISTRY,
        GRAPH_REGISTRY,
        READINESS,
        ADAPTER_STATUS,
        INSTALLED_INVENTORY,
    )
    values = {path: load_json(path) for path in json_paths}
    for path, value in values.items():
        verify_embedded_digest(path, value)

    simulator = values[SIMULATOR]
    cad = values[CAD_CAMPAIGN]
    plant = values[PLANT_LEDGER]
    parameter_sets = values[PLANT_PARAMETER_SETS]
    runtime_adapters = values[PLANT_RUNTIME_ADAPTERS]
    runtime_adapters_v2 = values[PLANT_RUNTIME_ADAPTERS_V2]
    protocol = values[PROTOCOL]
    queue = values[REVIEW_QUEUE]
    intake = values[EVIDENCE_INTAKE]
    assignments = values[ASSIGNMENTS]
    source_registry = values[SOURCE_REGISTRY]
    graph_registry = values[GRAPH_REGISTRY]
    readiness = values[READINESS]
    adapter = values[ADAPTER_STATUS]
    inventory = values[INSTALLED_INVENTORY]

    require(simulator["summary"]["model_count"] == 44, "simulator model drift")
    require(
        simulator["summary"]["geometry_configuration_count"] == 53,
        "simulator configuration drift",
    )
    require(cad["summary"]["configuration_count"] == 53, "CAD campaign drift")
    require(plant["summary"]["model_count"] == 44, "plant model drift")
    require(
        parameter_sets["summary"]["model_count"] == 44
        and parameter_sets["summary"]["assembled_parameter_set_count"] == 0
        and parameter_sets["support_granted"] is False
        and parameter_sets["physical_motion_authority"] is False,
        "plant parameter-set assembly drift",
    )
    for label, registry, version in (
        ("V1", runtime_adapters, "myactuator-plant-runtime-adapter-registry/1"),
        (
            "V2",
            runtime_adapters_v2,
            "myactuator-plant-runtime-adapter-registry/2",
        ),
    ):
        summary = registry["summary"]
        require(
            registry["schema_version"] == version
            and summary["model_count"] == 44
            and summary["profile_submission_count"] == 0
            and summary["runtime_contract_count"] == 0
            and summary["runtime_loadable_parameter_set_count"] == 0
            and summary["runtime_loadable_model_count"] == 0
            and summary["physically_validated_contract_count"] == 0
            and registry["support_granted"] is False
            and registry["physical_motion_authority"] is False,
            f"plant runtime-adapter {label} baseline drift",
        )
    require(protocol["summary"]["model_count"] == 44, "protocol model drift")
    require(queue["summary"]["item_count"] == 145, "review queue drift")
    require(intake["summary"]["packet_count"] == 97, "evidence intake drift")
    require(assignments["summary"]["role_count"] == 17, "role count drift")

    models = model_projection(simulator)
    configurations = cad_projection(cad)
    model_keys = {model["model_key"] for model in models}
    require(
        model_keys
        == {model["model_key"] for model in protocol["models"]}
        == {model["model_key"] for model in plant["models"]},
        "protocol/plant/simulator model join drift",
    )
    require(
        {item["configuration_id"] for item in configurations}
        == {
            configuration_id
            for model in models
            for configuration_id in model["configuration_ids"]
        },
        "CAD/simulator configuration join drift",
    )
    require(
        all(
            not model["protocol_applicability_accepted"]
            and not model["exact_model_geometry_ready"]
            and not model["exact_model_plant_ready"]
            and not model["exact_model_simulation_ready"]
            and not model["physically_correlated_plant_ready"]
            for model in models
        ),
        "current model projection unexpectedly promoted readiness",
    )
    require(
        all(
            not item["accepted_asset"]
            and not item["browser_releasable"]
            and not item["support_granted"]
            for item in configurations
        ),
        "current CAD projection unexpectedly promoted authority",
    )

    catalog_status = status_counts(tests)
    implemented_count = (
        catalog_status["EXISTS-OFFLINE"]
        + catalog_status["EXISTS-BASELINE"]
    )
    observed_inventory_count = sum(
        motor["observation_status"] != "unobserved"
        for motor in inventory["motors"]
    )
    physical_completed_count = sum(
        test["level"] in {"BENCH", "HIL", "ROBOT"}
        and test["status"] not in {"PLANNED", "PHYSICAL-HOLD"}
        for test in tests
    )
    criteria = [
        criterion(
            "requirements_trace_coverage",
            "All requirements have design, WP, test and gate trace rows",
            77,
            len(requirement_rows),
            ".aiwg/requirements/traceability-matrix.md",
            "missing_structural_trace",
        ),
        criterion(
            "catalog_tests_implemented",
            "All cataloged verification items have implemented evidence",
            len(tests),
            implemented_count + physical_completed_count,
            ".aiwg/testing/test-catalog.md",
            "planned_or_physical_hold_tests_remain",
        ),
        criterion(
            "vendor_models_catalogued",
            "All MYACTUATOR model identities are catalogued",
            44,
            simulator["summary"]["model_count"],
            "generated/myactuator/simulator/runtime_catalog.json",
            "catalog_models_missing",
        ),
        criterion(
            "step_configurations_acquired",
            "All source STEP configurations are acquired and joined",
            53,
            simulator["summary"]["geometry_configuration_count"],
            "generated/myactuator/simulator/runtime_catalog.json",
            "source_step_configurations_missing",
        ),
        criterion(
            "protocol_models_accepted",
            "Every model has reviewed exact protocol applicability",
            44,
            protocol["summary"]["accepted_model_count"],
            "generated/myactuator/protocol_applicability/registry.json",
            "reviewed_exact_protocol_applicability_missing",
        ),
        criterion(
            "cad_configurations_accepted",
            "Every exact CAD configuration has reviewed output semantics",
            53,
            cad["summary"]["accepted_configuration_count"],
            "generated/myactuator/cad/campaign/campaign.json",
            "housing_output_axis_reviews_missing",
        ),
        criterion(
            "plant_models_source_complete",
            "Every model has a complete sourced plant parameter set",
            44,
            plant["summary"]["source_fact_complete_model_count"],
            "generated/myactuator/plant/evidence_ledger/ledger.json",
            "reviewed_plant_source_facts_missing",
        ),
        criterion(
            "exact_model_simulation_ready",
            "Exact-model simulation readiness coverage",
            44,
            simulator["summary"]["exact_model_simulation_ready_count"],
            "generated/myactuator/simulator/runtime_catalog.json",
            "exact_protocol_cad_or_plant_evidence_missing",
        ),
        criterion(
            "dropbear_source_authority_active",
            "One reviewed Dropbear source generation is active",
            1,
            source_registry["summary"]["active_runtime_complete_count"],
            "generated/dropbear_source_registry_v2/registry.json",
            "dropbear_source_authority_absent",
        ),
        criterion(
            "dropbear_canonical_graph_active",
            "One reviewed canonical Dropbear graph is active",
            1,
            graph_registry["summary"]["canonical_graph_count"],
            "generated/dropbear_graph_registry_v2/registry.json",
            "dropbear_canonical_graph_absent",
        ),
        criterion(
            "dropbear_motion_ready_actuators",
            "All twelve Dropbear actuators meet motion-readiness dependencies",
            12,
            readiness["summary"]["motion_ready_count"],
            "generated/dropbear_readiness/readiness.json",
            "dropbear_actuator_dependencies_incomplete",
        ),
        criterion(
            "reviewer_roles_assigned",
            "All controlled evidence-review roles are assigned",
            17,
            assignments["summary"]["assigned_role_count"],
            "assets/myactuator/reviewer_assignments.json",
            "human_reviewers_unassigned",
        ),
        criterion(
            "installed_motors_observed",
            "All twelve installed motor slots have reviewed observations",
            12,
            observed_inventory_count,
            "assets/dropbear/installed_inventory_template.json",
            "unpowered_installed_inventory_absent",
        ),
        criterion(
            "runtime_can_adapter_selected",
            "One reviewed runtime CAN adapter is selected",
            1,
            adapter["summary"]["selected_runtime_count"],
            "generated/can_adapter_intake/status.json",
            "reviewed_runtime_can_adapter_absent",
        ),
        criterion(
            "physical_evidence_tests_completed",
            "Every bench/HIL/robot hold has exact physical evidence",
            catalog_status["PHYSICAL-HOLD"],
            physical_completed_count,
            ".aiwg/testing/test-catalog.md",
            "authorized_bench_hil_robot_evidence_absent",
        ),
    ]
    objective_evidence_complete = all(item["met"] for item in criteria)
    require(not objective_evidence_complete, "current objective unexpectedly complete")

    lifecycle_counts = Counter(
        item["lifecycle_state"] for item in work_packages
    )
    summary = {
        "requirement_count": len(requirement_rows),
        "p0_requirement_count": sum(
            item["priority"] == "P0" for item in requirement_rows
        ),
        "p1_requirement_count": sum(
            item["priority"] == "P1" for item in requirement_rows
        ),
        "p2_requirement_count": sum(
            item["priority"] == "P2" for item in requirement_rows
        ),
        "structurally_traced_requirement_count": sum(
            item["structurally_traced"] for item in requirement_rows
        ),
        "completion_asserted_requirement_count": sum(
            item["completion_asserted"] for item in requirement_rows
        ),
        "catalog_test_count": len(tests),
        "test_exists_offline_count": catalog_status["EXISTS-OFFLINE"],
        "test_exists_baseline_count": catalog_status["EXISTS-BASELINE"],
        "test_planned_count": catalog_status["PLANNED"],
        "test_physical_hold_count": catalog_status["PHYSICAL-HOLD"],
        "work_package_count": len(work_packages),
        "active_work_package_count": lifecycle_counts["ACTIVE"],
        "done_offline_work_package_count": lifecycle_counts["DONE-OFFLINE"],
        "open_work_package_count": lifecycle_counts["OPEN"],
        "physical_hold_work_package_count": lifecycle_counts["PHYSICAL-HOLD"],
        "phase_gate_count": len(gates),
        "phase_gate_pass_asserted_count": sum(
            item["pass_asserted"] for item in gates
        ),
        "model_count": len(models),
        "cad_configuration_count": len(configurations),
        "review_queue_item_count": queue["summary"]["item_count"],
        "evidence_intake_packet_count": intake["summary"]["packet_count"],
        "objective_criterion_count": len(criteria),
        "objective_criterion_met_count": sum(
            item["met"] for item in criteria
        ),
        "objective_evidence_complete": objective_evidence_complete,
    }

    sources = source_records()
    value = {
        "schema_version": VERSION,
        "dashboard_id": stable_id(
            "coverage-",
            {
                "sources": sources,
                "summary": summary,
                "criteria": criteria,
            },
        ),
        "authority": "coverage_and_gap_observation_only",
        "sources": sources,
        "verification_entry_point": "tools/test_all.sh",
        "latest_machine_report_path": (
            "generated/verification/offline_gate_report.json"
        ),
        "policy": {
            "structural_trace_is_not_verification": True,
            "catalog_status_is_not_current_run_result": True,
            "planned_test_is_not_passed": True,
            "source_acquisition_is_not_support": True,
            "generated_dashboard_is_not_review_or_approval": True,
            "source_drift_invalidates_dashboard": True,
            "physical_actions_require_separate_authorization": True,
            "dashboard_never_grants_support_or_motion": True,
        },
        "summary": summary,
        "objective_criteria": criteria,
        "requirements": requirement_rows,
        "tests": tests,
        "work_packages": work_packages,
        "phase_gates": gates,
        "models": models,
        "cad_configurations": configurations,
        "release_authorized": False,
        "support_granted": False,
        "physical_motion_authority": False,
        "physical_action_permitted": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(value)
    return value


def validate(value: dict[str, Any], *, verify_projection: bool = True) -> None:
    schema = load_json(SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise CoverageDashboardError(
            "dashboard schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "dashboard digest drift",
    )
    summary = value["summary"]
    require(
        summary["requirement_count"]
        == summary["p0_requirement_count"]
        + summary["p1_requirement_count"]
        + summary["p2_requirement_count"],
        "requirement summary partition drift",
    )
    require(
        summary["catalog_test_count"]
        == summary["test_exists_offline_count"]
        + summary["test_exists_baseline_count"]
        + summary["test_planned_count"]
        + summary["test_physical_hold_count"],
        "test summary partition drift",
    )
    require(
        summary["work_package_count"]
        == summary["active_work_package_count"]
        + summary["done_offline_work_package_count"]
        + summary["open_work_package_count"]
        + summary["physical_hold_work_package_count"],
        "work-package summary partition drift",
    )
    require(
        summary["objective_criterion_met_count"]
        == sum(item["met"] for item in value["objective_criteria"])
        and summary["objective_evidence_complete"]
        == all(item["met"] for item in value["objective_criteria"]),
        "objective criterion summary drift",
    )
    require(
        not value["release_authorized"]
        and not value["support_granted"]
        and not value["physical_motion_authority"]
        and not value["physical_action_permitted"],
        "dashboard authority promotion",
    )
    require(
        all(
            item["structurally_traced"] and not item["completion_asserted"]
            for item in value["requirements"]
        ),
        "dashboard promoted structural trace to requirement completion",
    )
    if verify_projection:
        expected = assemble()
        require(value == expected, "dashboard source projection drift")


def render_index(value: dict[str, Any]) -> str:
    summary = value["summary"]
    criteria_rows = []
    for item in value["objective_criteria"]:
        criteria_rows.append(
            "<tr>"
            f"<td>{html.escape(item['label'])}</td>"
            f"<td>{item['observed_count']} / {item['required_count']}</td>"
            f"<td class=\"{'met' if item['met'] else 'gap'}\">"
            f"{'MET' if item['met'] else 'GAP'}</td>"
            f"<td>{html.escape(item['blocker'] or '—')}</td>"
            f"<td><code>{html.escape(item['evidence_ref'])}</code></td>"
            "</tr>"
        )
    requirement_rows = []
    for item in value["requirements"]:
        counts = item["test_status_counts"]
        requirement_rows.append(
            "<tr>"
            f"<td><code>{html.escape(item['requirement_id'])}</code></td>"
            f"<td>{html.escape(item['priority'])}</td>"
            f"<td>{html.escape(item['statement'])}</td>"
            f"<td>{len(item['planned_test_ids'])}</td>"
            f"<td>{counts['EXISTS-OFFLINE'] + counts['EXISTS-BASELINE']}</td>"
            f"<td>{counts['PLANNED']}</td>"
            f"<td>{counts['PHYSICAL-HOLD']}</td>"
            f"<td>{html.escape(', '.join(item['gate_ids']))}</td>"
            f"<td>{html.escape(item['evidence_now'])}</td>"
            "</tr>"
        )
    work_package_rows = [
        "<tr>"
        f"<td><code>{html.escape(item['work_package_id'])}</code></td>"
        f"<td>{html.escape(item['outcome'])}</td>"
        f"<td>{html.escape(item['lifecycle_state'])}</td>"
        f"<td>{html.escape(item['status'])}</td>"
        "</tr>"
        for item in value["work_packages"]
    ]
    gate_rows = [
        "<tr>"
        f"<td><code>{html.escape(item['gate_id'])}</code></td>"
        f"<td>{html.escape(item['name'])}</td>"
        f"<td>{html.escape(item['required_evidence'])}</td>"
        f"<td>{html.escape(item['hard_hold'])}</td>"
        "<td>not asserted by this dashboard</td>"
        "</tr>"
        for item in value["phase_gates"]
    ]
    model_rows = [
        "<tr>"
        f"<td>{html.escape(item['series'])}</td>"
        f"<td>{html.escape(item['model'])}</td>"
        f"<td>{len(item['source_variant_ids'])}</td>"
        f"<td>{len(item['configuration_ids'])}</td>"
        f"<td>{'yes' if item['protocol_applicability_accepted'] else 'no'}</td>"
        f"<td>{item['cad_accepted_configuration_count']}</td>"
        f"<td>{html.escape(item['plant_status'])}</td>"
        f"<td>{'yes' if item['exact_model_simulation_ready'] else 'no'}</td>"
        f"<td>{html.escape(', '.join(item['blockers']))}</td>"
        "</tr>"
        for item in value["models"]
    ]
    cad_rows = [
        "<tr>"
        f"<td><code>{html.escape(item['configuration_id'])}</code></td>"
        f"<td>{html.escape(item['series'])}</td>"
        f"<td>{html.escape(item['model'])}</td>"
        f"<td>{html.escape(item['source_structure'])}</td>"
        f"<td>{html.escape(item['selector_status'])}</td>"
        f"<td>{html.escape(item['review_lane'])}</td>"
        f"<td>{item['unanswered_question_count']}</td>"
        f"<td>{'yes' if item['accepted_asset'] else 'no'}</td>"
        "</tr>"
        for item in value["cad_configurations"]
    ]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MYACTUATOR and Dropbear coverage</title>
<style>
:root{{--ok:#176b36;--gap:#9a3d24;--hold:#fff1cc;--line:#ccd1d6}}
body{{font-family:system-ui,sans-serif;margin:2rem;line-height:1.4;color:#20242a}}
h1,h2{{line-height:1.15}}
.hold{{border:2px solid #9a5b00;background:var(--hold);padding:1rem}}
.cards{{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}}
.card{{border:1px solid var(--line);padding:.7rem;min-width:10rem}}
.met{{color:var(--ok);font-weight:700}}
.gap{{color:var(--gap);font-weight:700}}
.scroll{{overflow:auto;max-height:70vh;border:1px solid var(--line)}}
table{{border-collapse:collapse;width:100%;font-size:.9rem}}
th,td{{border:1px solid var(--line);padding:.4rem;text-align:left;vertical-align:top}}
th{{background:#eef1f4;position:sticky;top:0}}
code{{overflow-wrap:anywhere}}
</style>
</head>
<body>
<h1>MYACTUATOR / Dropbear coverage and gap dashboard</h1>
<div class="hold"><strong>Observation only.</strong> Structural trace coverage,
catalog status and generated summaries are not current test results, human
review, product support, release approval, physical-action authorization or
motion authority. Consult the separately generated
<a href="../../../verification/offline_gate_report.json">machine gate report</a>
for the exact latest repository run.</div>
<div class="cards">
<div class="card"><strong>{summary['requirement_count']}</strong><br>requirements traced</div>
<div class="card"><strong>{summary['test_exists_offline_count']}</strong><br>offline tests implemented</div>
<div class="card"><strong>{summary['test_planned_count']}</strong><br>tests planned</div>
<div class="card"><strong>{summary['test_physical_hold_count']}</strong><br>physical test holds</div>
<div class="card"><strong>{summary['objective_criterion_met_count']} / {summary['objective_criterion_count']}</strong><br>objective criteria met</div>
<div class="card"><strong>0</strong><br>exact models simulation-ready</div>
</div>
<p>Canonical JSON: <a href="dashboard.json"><code>{html.escape(value['dashboard_id'])}</code></a></p>

<h2>Objective completion criteria</h2>
<div class="scroll"><table>
<thead><tr><th>Criterion</th><th>Observed / required</th><th>State</th>
<th>Blocker</th><th>Evidence</th></tr></thead>
<tbody>{''.join(criteria_rows)}</tbody>
</table></div>

<h2>Work packages</h2>
<div class="scroll"><table>
<thead><tr><th>WP</th><th>Outcome</th><th>State</th><th>Exact status</th></tr></thead>
<tbody>{''.join(work_package_rows)}</tbody>
</table></div>

<h2>Requirement trace and planned evidence</h2>
<p>No row below asserts requirement completion. Counts describe catalog
implementation/hold state, not the latest run result.</p>
<div class="scroll"><table>
<thead><tr><th>ID</th><th>Pri</th><th>Requirement</th><th>Mapped tests</th>
<th>Implemented</th><th>Planned</th><th>Physical hold</th><th>Gates</th>
<th>Evidence now</th></tr></thead>
<tbody>{''.join(requirement_rows)}</tbody>
</table></div>

<h2>MYACTUATOR model readiness</h2>
<div class="scroll"><table>
<thead><tr><th>Series</th><th>Model</th><th>STEP variants</th><th>Configurations</th>
<th>Protocol accepted</th><th>CAD accepted</th><th>Plant</th>
<th>Exact simulation</th><th>Blockers</th></tr></thead>
<tbody>{''.join(model_rows)}</tbody>
</table></div>

<h2>Exact CAD configurations</h2>
<div class="scroll"><table>
<thead><tr><th>Configuration</th><th>Series</th><th>Model</th><th>Source</th>
<th>Selector</th><th>Review lane</th><th>Questions</th><th>Accepted</th></tr></thead>
<tbody>{''.join(cad_rows)}</tbody>
</table></div>

<h2>Phase gates</h2>
<div class="scroll"><table>
<thead><tr><th>Gate</th><th>Name</th><th>Required evidence</th><th>Hard hold</th>
<th>Dashboard decision</th></tr></thead>
<tbody>{''.join(gate_rows)}</tbody>
</table></div>
</body>
</html>
"""


def expected_files(value: dict[str, Any]) -> dict[str, bytes]:
    return {
        "dashboard.json": canonical_bytes(value),
        "index.html": render_index(value).encode("utf-8"),
    }


def check_outputs(files: dict[str, bytes]) -> None:
    require(OUTPUT_DIR.is_dir(), "coverage dashboard output directory missing")
    actual = {
        path.relative_to(OUTPUT_DIR).as_posix()
        for path in OUTPUT_DIR.rglob("*")
        if path.is_file()
    }
    require(actual == set(files), "coverage dashboard output file-set drift")
    for relative, expected in files.items():
        path = OUTPUT_DIR / relative
        require(path.read_bytes() == expected, f"{relative}: output drift")


def write_outputs(files: dict[str, bytes]) -> None:
    OUTPUT_DIR.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{OUTPUT_DIR.name}.staging.",
            dir=OUTPUT_DIR.parent,
        )
    )
    backup = OUTPUT_DIR.with_name(f".{OUTPUT_DIR.name}.backup")
    try:
        for relative, content in files.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                with path.open("rb") as handle:
                    os.fsync(handle.fileno())
        if backup.exists():
            shutil.rmtree(backup)
        if OUTPUT_DIR.exists():
            OUTPUT_DIR.replace(backup)
        try:
            staging.replace(OUTPUT_DIR)
        except Exception:
            if backup.exists() and not OUTPUT_DIR.exists():
                backup.replace(OUTPUT_DIR)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def build() -> dict[str, Any]:
    value = assemble()
    validate(value, verify_projection=False)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        value = build()
        files = expected_files(value)
        if args.write:
            write_outputs(files)
            action = "WRITE"
        else:
            check_outputs(files)
            action = "CHECK"
        summary = value["summary"]
        print(
            f"COVERAGE_DASHBOARD_{action} PASS "
            f"requirements={summary['requirement_count']} "
            f"tests={summary['catalog_test_count']} "
            f"implemented={summary['test_exists_offline_count']} "
            f"planned={summary['test_planned_count']} "
            f"physical_hold={summary['test_physical_hold_count']} "
            f"criteria={summary['objective_criterion_met_count']}/"
            f"{summary['objective_criterion_count']} "
            f"release={str(value['release_authorized']).lower()} "
            f"motion={str(value['physical_motion_authority']).lower()}"
        )
        return 0
    except (CoverageDashboardError, OSError) as error:
        print(f"coverage dashboard failed: {error}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
