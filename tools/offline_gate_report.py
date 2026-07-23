#!/usr/bin/env python3
"""Maintain an atomic, schema-validated machine report for the offline gate."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/offline-gate-report.schema.json"
DEFAULT_OUTPUT = ROOT / "generated/verification/offline_gate_report.json"
SOURCE_ROOTS = (
    ".aiwg",
    "contracts",
    "docs",
    "firmware",
    "host",
    "ros2_control",
    "schemas",
    "tests",
    "tools",
    "web",
)
EXCLUDED_PARTS = {
    ".git",
    ".pio",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
}


class GateReportError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def canonical(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GateReportError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise GateReportError(f"JSON root must be an object: {path}")
    return value


def validator() -> Draft202012Validator:
    schema = read_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(value: dict[str, Any]) -> None:
    errors = sorted(
        validator().iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise GateReportError(
            f"schema failure at /{'/'.join(map(str, error.absolute_path))}: "
            f"{error.message}"
        )
    stages = value["stages"]
    sequences = [stage["sequence"] for stage in stages]
    if sequences != list(range(1, len(stages) + 1)):
        raise GateReportError("stage sequence must be contiguous and ordered")
    ids = [stage["stage_id"] for stage in stages]
    if len(ids) != len(set(ids)):
        raise GateReportError("stage IDs must be unique")
    running = [stage for stage in stages if stage["result"] == "RUNNING"]
    if value["result"] == "RUNNING" and len(running) > 1:
        raise GateReportError("at most one stage may be running")
    if value["result"] != "RUNNING" and running:
        raise GateReportError("final report cannot contain a running stage")
    if value["result"] == "PASS":
        if any(stage["result"] != "PASS" for stage in stages):
            raise GateReportError("passing report requires every executed stage to pass")
        if value["failure_stage"] is not None or value["exit_code"] != 0:
            raise GateReportError("passing report cannot contain failure metadata")
    if value["result"] == "FAIL":
        if value["failure_stage"] is None or value["exit_code"] in (None, 0):
            raise GateReportError("failed report requires failure stage and nonzero exit")


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    validate(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{path.name}.", dir=path.parent, delete=False
    ) as temporary:
        temporary.write(canonical(value))
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def command(*args: str, check: bool = True) -> bytes:
    result = subprocess.run(
        list(args),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and result.returncode:
        raise GateReportError(
            f"command failed ({' '.join(args)}): "
            f"{result.stdout.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout


def tool_version(executable: str) -> str:
    try:
        output = command(executable, "--version", check=False).decode(
            "utf-8", "replace"
        )
    except OSError:
        return "unavailable"
    first = next((line.strip() for line in output.splitlines() if line.strip()), "")
    return first or "unavailable"


def source_manifest() -> tuple[int, str]:
    records: list[bytes] = []
    for root_name in SOURCE_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
                continue
            relative = path.relative_to(ROOT).as_posix()
            if relative == DEFAULT_OUTPUT.relative_to(ROOT).as_posix():
                continue
            records.append(
                relative.encode("utf-8")
                + b"\0"
                + hashlib.sha256(path.read_bytes()).digest()
            )
    return len(records), sha256(b"\0".join(records))


def asserted_claims() -> tuple[dict[str, Any], list[dict[str, str]]]:
    named_paths = {
        "download_index": (
            ROOT / "assets/myactuator/download_index_snapshot.json"
        ),
        "reviewer_assignments": (
            ROOT / "assets/myactuator/reviewer_assignments.json"
        ),
        "evidence_review_queue": (
            ROOT / "generated/myactuator/evidence_review/queue.json"
        ),
        "evidence_intake": (
            ROOT / "generated/myactuator/evidence_intake/manifest.json"
        ),
        "coverage_dashboard": (
            ROOT / "generated/myactuator/coverage_dashboard/dashboard.json"
        ),
        "claim_surface": (
            ROOT / "generated/myactuator/claim_surface/report.json"
        ),
        "cad": ROOT / "generated/myactuator/cad/support_report.json",
        "cad_review_campaign": (
            ROOT / "generated/myactuator/cad/campaign/campaign.json"
        ),
        "protocol_applicability": (
            ROOT
            / "generated/myactuator/protocol_applicability/registry.json"
        ),
        "plant": ROOT / "generated/myactuator/plant/runtime_registry.json",
        "plant_evidence_ledger": (
            ROOT
            / "generated/myactuator/plant/evidence_ledger/ledger.json"
        ),
        "plant_spec_candidates": (
            ROOT
            / "generated/myactuator/plant/spec_candidates/registry.json"
        ),
        "plant_candidate_decisions": (
            ROOT
            / "generated/myactuator/plant/candidate_decisions/registry.json"
        ),
        "plant_parameter_sets": (
            ROOT
            / "generated/myactuator/plant/parameter_sets/registry.json"
        ),
        "plant_runtime_adapters": (
            ROOT
            / "generated/myactuator/plant/runtime_adapters/registry.json"
        ),
        "plant_runtime_adapters_v2": (
            ROOT
            / "generated/myactuator/plant/runtime_adapters_v2/registry.json"
        ),
        "simulator_runtime": (
            ROOT / "generated/myactuator/simulator/runtime_catalog.json"
        ),
        "rigid_body_benchmark": (
            ROOT / "generated/myactuator/rigid_body_benchmark/report.json"
        ),
        "rigid_body_trace": (
            ROOT / "generated/myactuator/rigid_body_benchmark/trace.json"
        ),
        "rigid_body_engine_lock": (
            ROOT / "tools/rigid-body-engine-lock.json"
        ),
        "ros2_cpp_handoff": (
            ROOT
            / "generated/myactuator/ros2_control_cpp_handoff/report.json"
        ),
        "ros2_cpp_environment_lock": (
            ROOT / "tools/ros2-cpp-environment-lock.json"
        ),
        "readiness": ROOT / "generated/dropbear_readiness/readiness.json",
        "description": ROOT / "generated/dropbear_description/inventory.json",
        "calibration": ROOT / "assets/myactuator/calibration_registry.json",
        "limits": ROOT / "assets/myactuator/limit_registry.json",
        "config": ROOT / "schemas/examples/dropbear-observed-incomplete.json",
        "source_authority": (
            ROOT / "generated/dropbear_source_authority/status.json"
        ),
        "source_registry_v2": (
            ROOT / "generated/dropbear_source_registry_v2/registry.json"
        ),
        "graph_status": ROOT / "generated/dropbear_graph_review/status.json",
        "graph_v2_status": ROOT / "generated/dropbear_graph_v2/status.json",
        "graph_registry_v2": (
            ROOT / "generated/dropbear_graph_registry_v2/registry.json"
        ),
        "graph_host": ROOT / "generated/dropbear_graph_projection/host.json",
        "graph_ros": ROOT / "generated/dropbear_graph_projection/ros.json",
        "graph_simulator": (
            ROOT / "generated/dropbear_graph_projection/simulator.json"
        ),
        "graph_ui": ROOT / "generated/dropbear_graph_projection/ui.json",
        "graph_lifecycle_host": (
            ROOT / "generated/dropbear_graph_lifecycle_projection_v2/host.json"
        ),
        "graph_lifecycle_ros": (
            ROOT / "generated/dropbear_graph_lifecycle_projection_v2/ros.json"
        ),
        "graph_lifecycle_simulator": (
            ROOT / "generated/dropbear_graph_lifecycle_projection_v2/simulator.json"
        ),
        "graph_lifecycle_ui": (
            ROOT / "generated/dropbear_graph_lifecycle_projection_v2/ui.json"
        ),
        "can_adapter_intake": (
            ROOT / "generated/can_adapter_intake/status.json"
        ),
        "security_platform_intake": (
            ROOT / "generated/security_platform_intake/status.json"
        ),
        "discovery": (
            ROOT / "generated/dropbear_unpowered_discovery/status.json"
        ),
        "installed_inventory": (
            ROOT / "assets/dropbear/installed_inventory_template.json"
        ),
    }
    values = {name: read_json(path) for name, path in named_paths.items()}
    download_index = values["download_index"]
    reviewer_assignments = values["reviewer_assignments"]
    evidence_review_queue = values["evidence_review_queue"]
    evidence_intake = values["evidence_intake"]
    coverage_dashboard = values["coverage_dashboard"]
    claim_surface = values["claim_surface"]
    cad = values["cad"]["summary"]
    cad_review_campaign = values["cad_review_campaign"]["summary"]
    protocol_applicability = values["protocol_applicability"]["summary"]
    plant = values["plant"]["summary"]
    plant_evidence = values["plant_evidence_ledger"]["summary"]
    plant_spec_candidates = values["plant_spec_candidates"]["summary"]
    plant_candidate_decisions = values["plant_candidate_decisions"][
        "summary"
    ]
    plant_parameter_sets = values["plant_parameter_sets"]["summary"]
    plant_runtime_adapters = values["plant_runtime_adapters"]["summary"]
    plant_runtime_adapters_v2 = values["plant_runtime_adapters_v2"][
        "summary"
    ]
    simulator_runtime = values["simulator_runtime"]["summary"]
    rigid_body_benchmark = values["rigid_body_benchmark"]
    rigid_body_trace = values["rigid_body_trace"]
    rigid_body_engine_lock = values["rigid_body_engine_lock"]
    ros2_cpp_handoff = values["ros2_cpp_handoff"]
    ros2_cpp_environment_lock = values["ros2_cpp_environment_lock"]
    readiness = values["readiness"]["summary"]
    description = values["description"]["summary"]
    calibration = values["calibration"]["physical_admission"]
    limits = values["limits"]["physical_admission"]
    config = values["config"]
    source_authority = values["source_authority"]["summary"]
    source_registry_v2 = values["source_registry_v2"]
    graph_status = values["graph_status"]["summary"]
    graph_v2_status = values["graph_v2_status"]
    graph_registry_v2 = values["graph_registry_v2"]
    graph_host = values["graph_host"]
    graph_ros = values["graph_ros"]
    graph_simulator = values["graph_simulator"]
    graph_ui = values["graph_ui"]
    graph_lifecycle = tuple(
        values[f"graph_lifecycle_{kind}"]
        for kind in ("host", "ros", "simulator", "ui")
    )
    can_adapter_intake = values["can_adapter_intake"]
    security_platform_intake = values["security_platform_intake"]
    discovery = values["discovery"]["summary"]
    installed_inventory = values["installed_inventory"]
    claims = {
        "physical_work_performed": False,
        "hardware_can_capture_performed": False,
        "bench_or_hil_performed": False,
        "robot_motion_performed": False,
        "download_index_page_count": download_index["summary"][
            "page_count"
        ],
        "download_index_archive_url_count": download_index["summary"][
            "archive_url_count"
        ],
        "download_index_tracked_exact_match": download_index["summary"][
            "tracked_exact_match"
        ],
        "reviewer_role_count": reviewer_assignments["summary"]["role_count"],
        "reviewer_assigned_role_count": reviewer_assignments["summary"][
            "assigned_role_count"
        ],
        "evidence_review_queue_item_count": evidence_review_queue["summary"][
            "item_count"
        ],
        "evidence_review_queue_workstream_count": evidence_review_queue[
            "summary"
        ]["workstream_count"],
        "evidence_review_queue_accepted_item_count": evidence_review_queue[
            "summary"
        ]["accepted_item_count"],
        "evidence_review_queue_assigned_item_count": evidence_review_queue[
            "summary"
        ]["assigned_item_count"],
        "evidence_review_queue_physical_action_count": evidence_review_queue[
            "summary"
        ]["physical_action_permitted_count"],
        "evidence_intake_packet_count": evidence_intake["summary"][
            "packet_count"
        ],
        "evidence_intake_cad_packet_count": evidence_intake["summary"][
            "cad_packet_count"
        ],
        "evidence_intake_plant_packet_count": evidence_intake["summary"][
            "plant_packet_count"
        ],
        "evidence_intake_ready_packet_count": evidence_intake["summary"][
            "ready_packet_count"
        ],
        "evidence_intake_blocked_packet_count": evidence_intake["summary"][
            "blocked_packet_count"
        ],
        "evidence_intake_task_count": evidence_intake["summary"]["task_count"],
        "evidence_intake_cad_task_count": evidence_intake["summary"][
            "cad_task_count"
        ],
        "evidence_intake_plant_task_count": evidence_intake["summary"][
            "plant_task_count"
        ],
        "evidence_intake_assigned_packet_count": evidence_intake["summary"][
            "assigned_packet_count"
        ],
        "evidence_intake_accepted_packet_count": evidence_intake["summary"][
            "accepted_packet_count"
        ],
        "evidence_intake_physical_action_count": evidence_intake["summary"][
            "physical_action_permitted_count"
        ],
        "coverage_requirement_count": coverage_dashboard["summary"][
            "requirement_count"
        ],
        "coverage_structurally_traced_requirement_count": coverage_dashboard[
            "summary"
        ]["structurally_traced_requirement_count"],
        "coverage_catalog_test_count": coverage_dashboard["summary"][
            "catalog_test_count"
        ],
        "coverage_exists_offline_test_count": coverage_dashboard["summary"][
            "test_exists_offline_count"
        ],
        "coverage_planned_test_count": coverage_dashboard["summary"][
            "test_planned_count"
        ],
        "coverage_physical_hold_test_count": coverage_dashboard["summary"][
            "test_physical_hold_count"
        ],
        "coverage_work_package_count": coverage_dashboard["summary"][
            "work_package_count"
        ],
        "coverage_phase_gate_count": coverage_dashboard["summary"][
            "phase_gate_count"
        ],
        "coverage_objective_criterion_count": coverage_dashboard["summary"][
            "objective_criterion_count"
        ],
        "coverage_objective_criterion_met_count": coverage_dashboard["summary"][
            "objective_criterion_met_count"
        ],
        "coverage_model_count": coverage_dashboard["summary"]["model_count"],
        "coverage_cad_configuration_count": coverage_dashboard["summary"][
            "cad_configuration_count"
        ],
        "coverage_objective_evidence_complete": coverage_dashboard["summary"][
            "objective_evidence_complete"
        ],
        "coverage_release_authorized": coverage_dashboard[
            "release_authorized"
        ],
        "claim_surface_lexical_rule_count": claim_surface["summary"][
            "lexical_rule_count"
        ],
        "claim_surface_structured_rule_count": claim_surface["summary"][
            "structured_rule_count"
        ],
        "claim_surface_finding_count": claim_surface["summary"][
            "finding_count"
        ],
        "claim_surface_exception_count": claim_surface["summary"][
            "exception_count"
        ],
        "claim_surface_passed": claim_surface["summary"]["passed"],
        "catalog_model_count": cad["models"],
        "supported_catalog_model_count": cad["supported_models"],
        "protocol_applicability_model_count": protocol_applicability[
            "model_count"
        ],
        "protocol_document_package_count": protocol_applicability[
            "document_package_count"
        ],
        "protocol_document_file_occurrence_count": protocol_applicability[
            "document_file_occurrence_count"
        ],
        "accepted_protocol_applicability_count": protocol_applicability[
            "accepted_applicability_count"
        ],
        "cad_configuration_count": cad["geometry_configurations"],
        "accepted_cad_configuration_count": (
            cad["geometry_configurations"]
            - cad["configuration_statuses"].get("unsupported", 0)
        ),
        "cad_campaign_configuration_count": cad_review_campaign[
            "configuration_count"
        ],
        "cad_campaign_unanswered_question_count": cad_review_campaign[
            "unanswered_question_count"
        ],
        "cad_campaign_packet_reviewable_count": cad_review_campaign[
            "currently_packet_reviewable_count"
        ],
        "cad_campaign_blocked_configuration_count": cad_review_campaign[
            "blocked_re_source_or_specialized_partition_count"
        ],
        "real_plant_parameter_set_count": plant["sourced_parameter_sets"],
        "physically_validated_plant_parameter_set_count": plant[
            "physically_validated_parameter_sets"
        ],
        "plant_evidence_model_count": plant_evidence["model_count"],
        "plant_required_parameter_field_count": plant_evidence[
            "required_parameter_field_count"
        ],
        "plant_model_parameter_requirement_count": plant_evidence[
            "model_parameter_requirement_count"
        ],
        "plant_required_operating_envelope_field_count": plant_evidence[
            "required_operating_envelope_field_count"
        ],
        "plant_model_operating_envelope_requirement_count": plant_evidence[
            "model_operating_envelope_requirement_count"
        ],
        "plant_candidate_model_manual_relationship_count": plant_evidence[
            "candidate_model_manual_relationship_count"
        ],
        "plant_spec_manual_occurrence_count": plant_spec_candidates[
            "manual_occurrence_count"
        ],
        "plant_spec_page_count": plant_spec_candidates["page_count"],
        "plant_spec_model_count": plant_spec_candidates["model_count"],
        "plant_spec_candidate_count": plant_spec_candidates["candidate_count"],
        "plant_spec_direct_mapping_candidate_count": plant_spec_candidates[
            "direct_label_unit_mapping_candidate_count"
        ],
        "plant_spec_semantic_review_candidate_count": plant_spec_candidates[
            "semantic_review_mapping_candidate_count"
        ],
        "plant_spec_unmapped_candidate_count": plant_spec_candidates[
            "unmapped_candidate_count"
        ],
        "plant_spec_accepted_candidate_count": plant_spec_candidates[
            "accepted_candidate_count"
        ],
        "plant_spec_runtime_admissible_candidate_count": plant_spec_candidates[
            "runtime_admissible_candidate_count"
        ],
        "plant_candidate_submission_count": plant_candidate_decisions[
            "submission_count"
        ],
        "plant_candidate_event_count": plant_candidate_decisions[
            "event_count"
        ],
        "plant_candidate_accepted_count": plant_candidate_decisions[
            "accepted_count"
        ],
        "plant_candidate_rejected_count": plant_candidate_decisions[
            "rejected_count"
        ],
        "plant_candidate_deferred_count": plant_candidate_decisions[
            "deferred_count"
        ],
        "plant_candidate_revoked_count": plant_candidate_decisions[
            "revoked_count"
        ],
        "plant_candidate_superseded_count": plant_candidate_decisions[
            "superseded_count"
        ],
        "plant_candidate_active_source_fact_count": (
            plant_candidate_decisions["active_source_fact_count"]
        ),
        "plant_candidate_model_with_active_source_fact_count": (
            plant_candidate_decisions[
                "model_with_active_source_fact_count"
            ]
        ),
        "plant_candidate_reviewer_assignment_complete": (
            plant_candidate_decisions["reviewer_assignment_complete"]
        ),
        "plant_parameter_set_active_source_fact_count": (
            plant_parameter_sets["active_source_fact_count"]
        ),
        "plant_parameter_set_source_complete_model_count": (
            plant_parameter_sets["source_fact_complete_model_count"]
        ),
        "plant_parameter_set_accepted_applicability_count": (
            plant_parameter_sets["accepted_protocol_applicability_count"]
        ),
        "plant_parameter_set_accepted_applicability_model_count": (
            plant_parameter_sets[
                "accepted_protocol_applicability_model_count"
            ]
        ),
        "plant_parameter_set_assembled_count": (
            plant_parameter_sets["assembled_parameter_set_count"]
        ),
        "plant_parameter_set_assembled_model_count": (
            plant_parameter_sets["assembled_model_count"]
        ),
        "plant_parameter_set_runtime_loadable_count": (
            plant_parameter_sets["runtime_loadable_parameter_set_count"]
        ),
        "plant_parameter_set_physically_correlated_count": (
            plant_parameter_sets[
                "physically_correlated_parameter_set_count"
            ]
        ),
        "plant_runtime_profile_submission_count": (
            plant_runtime_adapters["profile_submission_count"]
        ),
        "plant_runtime_contract_count": (
            plant_runtime_adapters["runtime_contract_count"]
        ),
        "plant_runtime_loadable_parameter_set_count": (
            plant_runtime_adapters[
                "runtime_loadable_parameter_set_count"
            ]
        ),
        "plant_runtime_loadable_model_count": (
            plant_runtime_adapters["runtime_loadable_model_count"]
        ),
        "plant_runtime_physically_validated_contract_count": (
            plant_runtime_adapters[
                "physically_validated_contract_count"
            ]
        ),
        "plant_runtime_source_semantic_count": values[
            "plant_runtime_adapters"
        ]["adapter"]["source_semantic_count"],
        "plant_runtime_v2_profile_submission_count": (
            plant_runtime_adapters_v2["profile_submission_count"]
        ),
        "plant_runtime_v2_contract_count": (
            plant_runtime_adapters_v2["runtime_contract_count"]
        ),
        "plant_runtime_v2_loadable_parameter_set_count": (
            plant_runtime_adapters_v2[
                "runtime_loadable_parameter_set_count"
            ]
        ),
        "plant_runtime_v2_loadable_model_count": (
            plant_runtime_adapters_v2["runtime_loadable_model_count"]
        ),
        "plant_runtime_v2_physically_validated_contract_count": (
            plant_runtime_adapters_v2[
                "physically_validated_contract_count"
            ]
        ),
        "plant_runtime_v2_source_semantic_count": values[
            "plant_runtime_adapters_v2"
        ]["adapter"]["source_semantic_count"],
        "plant_runtime_v2_solver_id": values[
            "plant_runtime_adapters_v2"
        ]["adapter"]["solver_id"],
        "plant_runtime_v2_noise_algorithm": values[
            "plant_runtime_adapters_v2"
        ]["adapter"]["noise_algorithm"],
        "plant_runtime_v2_jitter_algorithm": values[
            "plant_runtime_adapters_v2"
        ]["adapter"]["jitter_algorithm"],
        "plant_source_fact_count": plant_evidence["source_fact_count"],
        "plant_accepted_source_fact_count": plant_evidence[
            "accepted_source_fact_count"
        ],
        "plant_missing_parameter_requirement_count": plant_evidence[
            "missing_parameter_requirement_count"
        ],
        "plant_missing_operating_envelope_requirement_count": (
            plant_evidence[
                "missing_operating_envelope_requirement_count"
            ]
        ),
        "plant_source_fact_complete_model_count": plant_evidence[
            "source_fact_complete_model_count"
        ],
        "simulator_runtime_model_count": simulator_runtime["model_count"],
        "simulator_runtime_configuration_count": simulator_runtime[
            "geometry_configuration_count"
        ],
        "exact_model_simulation_ready_count": simulator_runtime[
            "exact_model_simulation_ready_count"
        ],
        "browser_articulated_asset_ready_count": simulator_runtime[
            "browser_articulated_asset_ready_count"
        ],
        "dropbear_whole_robot_simulation_ready_count": simulator_runtime[
            "dropbear_whole_robot_ready_count"
        ],
        "rigid_body_benchmark_case_count": rigid_body_benchmark["summary"][
            "case_count"
        ],
        "rigid_body_benchmark_passed_case_count": rigid_body_benchmark[
            "summary"
        ]["passed_case_count"],
        "rigid_body_benchmark_executed_candidate_count": rigid_body_benchmark[
            "engine_lock"
        ]["executed_candidate_count"],
        "rigid_body_trace_event_count": rigid_body_trace["summary"][
            "event_count"
        ],
        "rigid_body_trace_command_count": rigid_body_trace["summary"][
            "command_count"
        ],
        "rigid_body_trace_state_count": rigid_body_trace["summary"][
            "state_count"
        ],
        "generic_rigid_body_fixture_passed": rigid_body_benchmark["claims"][
            "generic_fixture_passed"
        ],
        "dropbear_production_rigid_body_engine_selected": (
            rigid_body_benchmark["claims"]["production_engine_selected"]
            or rigid_body_engine_lock["claims"]["production_engine_selected"]
        ),
        "ros2_cpp_handoff_case_count": ros2_cpp_handoff["counts"][
            "case_count"
        ],
        "ros2_cpp_handoff_passed_case_count": ros2_cpp_handoff["counts"][
            "pass_count"
        ],
        "ros2_cpp_native_ctest_count": ros2_cpp_handoff["counts"][
            "native_ctest_count"
        ],
        "ros2_cpp_python_test_count": ros2_cpp_handoff["counts"][
            "python_test_count"
        ],
        "ros2_cpp_parity_line_count": ros2_cpp_handoff["counts"][
            "parity_line_count"
        ],
        "ros2_cpp_handoff_compiles": ros2_cpp_handoff["claims"][
            "cpp_handoff_compiles_in_exact_environment"
        ],
        "ros2_cpp_semantic_parity": ros2_cpp_handoff["claims"][
            "python_cpp_semantic_parity"
        ],
        "ros2_cpp_plugin_loads": ros2_cpp_handoff["claims"]["plugin_loads"],
        "ros2_cpp_fail_closed": ros2_cpp_handoff["claims"][
            "fail_closed_without_authority_and_adapter"
        ],
        "ros2_cpp_physical_adapter_present": (
            ros2_cpp_handoff["claims"]["physical_adapter_present"]
            or ros2_cpp_environment_lock["claims"]["physical_adapter_present"]
        ),
        "dropbear_actuator_count": readiness["actuator_count"],
        "dropbear_motion_ready_count": readiness["motion_ready_count"],
        "dropbear_runtime_route_count": readiness["materialized_route_count"],
        "dropbear_ros_actuator_mapping_count": readiness[
            "reviewed_ros_actuation_mapping_count"
        ],
        "accepted_physical_calibration_count": calibration[
            "accepted_physical_record_count"
        ],
        "accepted_measured_limit_record_count": limits[
            "accepted_measured_record_count"
        ],
        "description_runtime_mapping_count": description[
            "runtime_ros_actuator_mapping_count"
        ],
        "dropbear_source_authority_accepted_count": source_authority[
            "accepted_decision_count"
        ],
        "dropbear_source_registry_submission_count": source_registry_v2[
            "summary"
        ]["submission_count"],
        "dropbear_source_registry_active_count": source_registry_v2[
            "summary"
        ]["accepted_count"],
        "dropbear_source_registry_revoked_count": source_registry_v2[
            "summary"
        ]["revoked_count"],
        "dropbear_source_registry_superseded_count": source_registry_v2[
            "summary"
        ]["superseded_count"],
        "dropbear_graph_question_count": graph_status["question_count"],
        "dropbear_graph_unanswered_question_count": graph_status[
            "unanswered_question_count"
        ],
        "dropbear_graph_submitted_count": graph_status[
            "submitted_decision_count"
        ],
        "dropbear_graph_accepted_count": graph_status["accepted_graph_count"],
        "dropbear_canonical_graph_count": graph_status[
            "canonical_graph_count"
        ],
        "dropbear_graph_v2_unresolved_question_count": graph_v2_status[
            "summary"
        ]["v1_unresolved_question_count"],
        "dropbear_graph_registry_submission_count": graph_registry_v2[
            "summary"
        ]["submission_count"],
        "dropbear_graph_registry_active_count": graph_registry_v2[
            "summary"
        ]["accepted_count"],
        "dropbear_graph_registry_revoked_count": graph_registry_v2[
            "summary"
        ]["revoked_count"],
        "dropbear_graph_registry_superseded_count": graph_registry_v2[
            "summary"
        ]["superseded_count"],
        "dropbear_consumer_projection_count": len(
            (graph_host, graph_ros, graph_simulator, graph_ui)
        ),
        "dropbear_graph_transform_count": graph_host["outputs"][
            "transform_count"
        ],
        "dropbear_ros_urdf_fragment_count": graph_ros["outputs"][
            "urdf_fragment_count"
        ],
        "dropbear_simulator_authoritative_graph_count": graph_simulator[
            "outputs"
        ]["authoritative_graph_count"],
        "dropbear_ui_exposed_path_count": graph_ui["outputs"][
            "exposed_local_path_count"
        ],
        "dropbear_command_handle_count": graph_host["outputs"][
            "command_handle_count"
        ],
        "dropbear_lifecycle_projection_count": len(graph_lifecycle),
        "dropbear_lifecycle_frame_count": graph_lifecycle[0][
            "graph_summary"
        ]["frame_count"],
        "dropbear_lifecycle_actuator_mapping_count": graph_lifecycle[0][
            "graph_summary"
        ]["actuator_mapping_count"],
        "dropbear_lifecycle_ros_mapping_count": graph_lifecycle[0][
            "graph_summary"
        ]["ros_mapping_count"],
        "reviewed_can_adapter_manifest_count": can_adapter_intake["summary"][
            "reviewed_manifest_count"
        ],
        "selected_can_adapter_manifest_count": (
            can_adapter_intake["summary"]["selected_listen_only_count"]
            + can_adapter_intake["summary"]["selected_runtime_count"]
        ),
        "physical_can_adapter_factory_enabled": can_adapter_intake[
            "physical_factory_enabled"
        ],
        "security_platform_profile_count": security_platform_intake[
            "summary"
        ]["profile_count"],
        "security_platform_reviewed_target_profile_count": (
            security_platform_intake["summary"][
                "reviewed_target_profile_count"
            ]
        ),
        "security_platform_selected_profile_count": security_platform_intake[
            "summary"
        ]["selected_profile_count"],
        "security_trust_anchor_count": security_platform_intake["summary"][
            "trust_anchor_count"
        ],
        "security_key_assignment_count": security_platform_intake["summary"][
            "key_assignment_count"
        ],
        "security_private_key_material_count": security_platform_intake[
            "summary"
        ]["private_key_material_count"],
        "security_observed_secure_boot_enabled": security_platform_intake[
            "observed_capabilities"
        ]["secure_boot_enabled"],
        "security_observed_flash_encryption_enabled": security_platform_intake[
            "observed_capabilities"
        ]["flash_encryption_enabled"],
        "security_observed_bootloader_anti_rollback_enabled": (
            security_platform_intake["observed_capabilities"][
                "bootloader_anti_rollback_enabled"
            ]
        ),
        "security_observed_nvs_encryption_enabled": security_platform_intake[
            "observed_capabilities"
        ]["nvs_encryption_enabled"],
        "security_observed_legacy_tls_enabled": security_platform_intake[
            "observed_capabilities"
        ]["legacy_tls_enabled"],
        "security_authenticated_transport_adapter_present": (
            security_platform_intake["observed_capabilities"][
                "authenticated_transport_adapter_present"
            ]
        ),
        "security_signed_artifact_verifier_adapter_present": (
            security_platform_intake["observed_capabilities"][
                "signed_artifact_verifier_adapter_present"
            ]
        ),
        "security_persistent_replay_adapter_present": (
            security_platform_intake["observed_capabilities"][
                "persistent_replay_adapter_present"
            ]
        ),
        "security_durable_audit_adapter_present": security_platform_intake[
            "observed_capabilities"
        ]["durable_audit_adapter_present"],
        "security_ota_installer_adapter_present": security_platform_intake[
            "observed_capabilities"
        ]["ota_installer_adapter_present"],
        "security_physical_io_enabled": security_platform_intake[
            "physical_io_enabled"
        ],
        "installed_inventory_submission_count": discovery[
            "submitted_inventory_count"
        ],
        "selected_can_controller_count": discovery[
            "selected_can_controller_count"
        ],
        "authorized_physical_action_count": discovery[
            "authorized_action_count"
        ],
        "unpowered_discovery_ready_for_execution": discovery[
            "ready_for_execution"
        ],
        "motion_enable_allowed": bool(
            readiness["motion_enable_allowed"]
            or calibration["motion_enable_allowed"]
            or limits["motion_enable_allowed"]
            or description["motion_enable_allowed"]
            or config["safety_admission"]["motion_enable_allowed"]
            or graph_status["canonical_graph_admissible"]
            or source_registry_v2["physical_motion_authority"]
            or graph_v2_status["physical_motion_authority"]
            or graph_registry_v2["physical_motion_authority"]
            or any(row["physical_motion_authority"] for row in graph_lifecycle)
            or can_adapter_intake["physical_motion_authority"]
            or can_adapter_intake["physical_factory_enabled"]
            or security_platform_intake["physical_motion_authority"]
            or security_platform_intake["physical_io_enabled"]
            or installed_inventory["physical_motion_authority"]
            or values["protocol_applicability"]["physical_motion_authority"]
            or values["plant_evidence_ledger"]["physical_motion_authority"]
            or values["plant_candidate_decisions"][
                "physical_motion_authority"
            ]
            or values["plant_parameter_sets"]["physical_motion_authority"]
            or values["plant_runtime_adapters"]["physical_motion_authority"]
            or values["rigid_body_benchmark"]["claims"][
                "physical_motion_authority"
            ]
            or values["rigid_body_trace"]["claims"][
                "physical_motion_authority"
            ]
            or values["rigid_body_engine_lock"]["claims"][
                "physical_motion_authority"
            ]
            or values["ros2_cpp_handoff"]["claims"][
                "physical_motion_authority"
            ]
            or values["ros2_cpp_environment_lock"]["claims"][
                "physical_motion_authority"
            ]
            or download_index["physical_motion_authority"]
            or reviewer_assignments["physical_motion_authority"]
            or evidence_review_queue["physical_motion_authority"]
            or evidence_review_queue["summary"][
                "physical_action_permitted_count"
            ]
            or evidence_intake["physical_motion_authority"]
            or evidence_intake["physical_action_permitted"]
            or evidence_intake["summary"][
                "physical_action_permitted_count"
            ]
            or coverage_dashboard["physical_motion_authority"]
            or coverage_dashboard["physical_action_permitted"]
            or coverage_dashboard["release_authorized"]
            or claim_surface["physical_motion_authority"]
            or claim_surface["physical_action_permitted"]
            or claim_surface["support_granted"]
        ),
    }
    expected = {
        "download_index_page_count": 6,
        "download_index_archive_url_count": 53,
        "download_index_tracked_exact_match": True,
        "reviewer_role_count": 17,
        "reviewer_assigned_role_count": 0,
        "evidence_review_queue_item_count": 145,
        "evidence_review_queue_workstream_count": 7,
        "evidence_review_queue_accepted_item_count": 0,
        "evidence_review_queue_assigned_item_count": 0,
        "evidence_review_queue_physical_action_count": 0,
        "evidence_intake_packet_count": 97,
        "evidence_intake_cad_packet_count": 53,
        "evidence_intake_plant_packet_count": 44,
        "evidence_intake_ready_packet_count": 85,
        "evidence_intake_blocked_packet_count": 12,
        "evidence_intake_task_count": 2361,
        "evidence_intake_cad_task_count": 689,
        "evidence_intake_plant_task_count": 1672,
        "evidence_intake_assigned_packet_count": 0,
        "evidence_intake_accepted_packet_count": 0,
        "evidence_intake_physical_action_count": 0,
        "coverage_requirement_count": 77,
        "coverage_structurally_traced_requirement_count": 77,
        "coverage_catalog_test_count": 140,
        "coverage_exists_offline_test_count": 105,
        "coverage_planned_test_count": 28,
        "coverage_physical_hold_test_count": 7,
        "coverage_work_package_count": 20,
        "coverage_phase_gate_count": 8,
        "coverage_objective_criterion_count": 15,
        "coverage_objective_criterion_met_count": 3,
        "coverage_model_count": 44,
        "coverage_cad_configuration_count": 53,
        "coverage_objective_evidence_complete": False,
        "coverage_release_authorized": False,
        "claim_surface_lexical_rule_count": 9,
        "claim_surface_structured_rule_count": 3,
        "claim_surface_finding_count": 0,
        "claim_surface_exception_count": 0,
        "claim_surface_passed": True,
        "catalog_model_count": 44,
        "supported_catalog_model_count": 0,
        "protocol_applicability_model_count": 44,
        "protocol_document_package_count": 9,
        "protocol_document_file_occurrence_count": 32,
        "accepted_protocol_applicability_count": 0,
        "cad_configuration_count": 53,
        "accepted_cad_configuration_count": 0,
        "cad_campaign_configuration_count": 53,
        "cad_campaign_unanswered_question_count": 689,
        "cad_campaign_packet_reviewable_count": 41,
        "cad_campaign_blocked_configuration_count": 12,
        "real_plant_parameter_set_count": 0,
        "physically_validated_plant_parameter_set_count": 0,
        "plant_evidence_model_count": 44,
        "plant_required_parameter_field_count": 34,
        "plant_model_parameter_requirement_count": 1496,
        "plant_required_operating_envelope_field_count": 4,
        "plant_model_operating_envelope_requirement_count": 176,
        "plant_candidate_model_manual_relationship_count": 106,
        "plant_spec_manual_occurrence_count": 15,
        "plant_spec_page_count": 215,
        "plant_spec_model_count": 44,
        "plant_spec_candidate_count": 531,
        "plant_spec_direct_mapping_candidate_count": 89,
        "plant_spec_semantic_review_candidate_count": 317,
        "plant_spec_unmapped_candidate_count": 125,
        "plant_spec_accepted_candidate_count": 0,
        "plant_spec_runtime_admissible_candidate_count": 0,
        "plant_candidate_submission_count": 0,
        "plant_candidate_event_count": 0,
        "plant_candidate_accepted_count": 0,
        "plant_candidate_rejected_count": 0,
        "plant_candidate_deferred_count": 0,
        "plant_candidate_revoked_count": 0,
        "plant_candidate_superseded_count": 0,
        "plant_candidate_active_source_fact_count": 0,
        "plant_candidate_model_with_active_source_fact_count": 0,
        "plant_candidate_reviewer_assignment_complete": False,
        "plant_parameter_set_active_source_fact_count": 0,
        "plant_parameter_set_source_complete_model_count": 0,
        "plant_parameter_set_accepted_applicability_count": 0,
        "plant_parameter_set_accepted_applicability_model_count": 0,
        "plant_parameter_set_assembled_count": 0,
        "plant_parameter_set_assembled_model_count": 0,
        "plant_parameter_set_runtime_loadable_count": 0,
        "plant_parameter_set_physically_correlated_count": 0,
        "plant_runtime_profile_submission_count": 0,
        "plant_runtime_contract_count": 0,
        "plant_runtime_loadable_parameter_set_count": 0,
        "plant_runtime_loadable_model_count": 0,
        "plant_runtime_physically_validated_contract_count": 0,
        "plant_runtime_source_semantic_count": 38,
        "plant_runtime_v2_profile_submission_count": 0,
        "plant_runtime_v2_contract_count": 0,
        "plant_runtime_v2_loadable_parameter_set_count": 0,
        "plant_runtime_v2_loadable_model_count": 0,
        "plant_runtime_v2_physically_validated_contract_count": 0,
        "plant_runtime_v2_source_semantic_count": 38,
        "plant_runtime_v2_solver_id": (
            "semi-implicit-euler-event-scheduled-v2"
        ),
        "plant_runtime_v2_noise_algorithm": (
            "sha256-box-muller-counter-v1"
        ),
        "plant_runtime_v2_jitter_algorithm": (
            "sha256-bounded-uniform-counter-v1"
        ),
        "plant_source_fact_count": 0,
        "plant_accepted_source_fact_count": 0,
        "plant_missing_parameter_requirement_count": 1496,
        "plant_missing_operating_envelope_requirement_count": 176,
        "plant_source_fact_complete_model_count": 0,
        "simulator_runtime_model_count": 44,
        "simulator_runtime_configuration_count": 53,
        "exact_model_simulation_ready_count": 0,
        "browser_articulated_asset_ready_count": 0,
        "dropbear_whole_robot_simulation_ready_count": 0,
        "rigid_body_benchmark_case_count": 10,
        "rigid_body_benchmark_passed_case_count": 10,
        "rigid_body_benchmark_executed_candidate_count": 1,
        "rigid_body_trace_event_count": 764,
        "rigid_body_trace_command_count": 9,
        "rigid_body_trace_state_count": 753,
        "generic_rigid_body_fixture_passed": True,
        "dropbear_production_rigid_body_engine_selected": False,
        "ros2_cpp_handoff_case_count": 10,
        "ros2_cpp_handoff_passed_case_count": 10,
        "ros2_cpp_native_ctest_count": 2,
        "ros2_cpp_python_test_count": 6,
        "ros2_cpp_parity_line_count": 6,
        "ros2_cpp_handoff_compiles": True,
        "ros2_cpp_semantic_parity": True,
        "ros2_cpp_plugin_loads": True,
        "ros2_cpp_fail_closed": True,
        "ros2_cpp_physical_adapter_present": False,
        "dropbear_actuator_count": 12,
        "dropbear_motion_ready_count": 0,
        "dropbear_runtime_route_count": 0,
        "dropbear_ros_actuator_mapping_count": 0,
        "accepted_physical_calibration_count": 0,
        "accepted_measured_limit_record_count": 0,
        "description_runtime_mapping_count": 0,
        "dropbear_source_authority_accepted_count": 0,
        "dropbear_source_registry_submission_count": 0,
        "dropbear_source_registry_active_count": 0,
        "dropbear_source_registry_revoked_count": 0,
        "dropbear_source_registry_superseded_count": 0,
        "dropbear_graph_question_count": 161,
        "dropbear_graph_unanswered_question_count": 161,
        "dropbear_graph_submitted_count": 0,
        "dropbear_graph_accepted_count": 0,
        "dropbear_canonical_graph_count": 0,
        "dropbear_graph_v2_unresolved_question_count": 161,
        "dropbear_graph_registry_submission_count": 0,
        "dropbear_graph_registry_active_count": 0,
        "dropbear_graph_registry_revoked_count": 0,
        "dropbear_graph_registry_superseded_count": 0,
        "dropbear_consumer_projection_count": 4,
        "dropbear_graph_transform_count": 0,
        "dropbear_ros_urdf_fragment_count": 0,
        "dropbear_simulator_authoritative_graph_count": 0,
        "dropbear_ui_exposed_path_count": 0,
        "dropbear_command_handle_count": 0,
        "dropbear_lifecycle_projection_count": 4,
        "dropbear_lifecycle_frame_count": 0,
        "dropbear_lifecycle_actuator_mapping_count": 0,
        "dropbear_lifecycle_ros_mapping_count": 0,
        "reviewed_can_adapter_manifest_count": 0,
        "selected_can_adapter_manifest_count": 0,
        "physical_can_adapter_factory_enabled": False,
        "security_platform_profile_count": 1,
        "security_platform_reviewed_target_profile_count": 0,
        "security_platform_selected_profile_count": 0,
        "security_trust_anchor_count": 0,
        "security_key_assignment_count": 0,
        "security_private_key_material_count": 0,
        "security_observed_secure_boot_enabled": False,
        "security_observed_flash_encryption_enabled": False,
        "security_observed_bootloader_anti_rollback_enabled": False,
        "security_observed_nvs_encryption_enabled": False,
        "security_observed_legacy_tls_enabled": True,
        "security_authenticated_transport_adapter_present": False,
        "security_signed_artifact_verifier_adapter_present": False,
        "security_persistent_replay_adapter_present": False,
        "security_durable_audit_adapter_present": False,
        "security_ota_installer_adapter_present": False,
        "security_physical_io_enabled": False,
        "installed_inventory_submission_count": 0,
        "selected_can_controller_count": 0,
        "authorized_physical_action_count": 0,
        "unpowered_discovery_ready_for_execution": False,
        "motion_enable_allowed": False,
    }
    for key, expected_value in expected.items():
        if claims[key] != expected_value:
            raise GateReportError(
                f"claim invariant drift: {key}={claims[key]!r}, "
                f"expected {expected_value!r}"
            )
    hashes = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256(path.read_bytes()),
        }
        for path in named_paths.values()
    ]
    parity_path = (
        ROOT / "generated/myactuator/ros2_control_cpp_handoff/parity.txt"
    )
    hashes.append(
        {
            "path": parity_path.relative_to(ROOT).as_posix(),
            "sha256": sha256(parity_path.read_bytes()),
        }
    )
    return claims, hashes


def initial_report() -> dict[str, Any]:
    started = now()
    file_count, manifest_sha = source_manifest()
    claims, artifact_hashes = asserted_claims()
    git_head = command("git", "rev-parse", "HEAD").decode("ascii").strip()
    tracked_diff = command("git", "diff", "--binary", "--no-ext-diff", "HEAD")
    dirty = bool(command("git", "status", "--porcelain=v1"))
    config = read_json(ROOT / "schemas/examples/dropbear-observed-incomplete.json")
    run_id = sha256(
        f"{started}\0{git_head}\0{manifest_sha}".encode("utf-8")
    )[:24]
    return {
        "schema_version": "offline-gate-report/1",
        "gate_id": "p0-p1-offline",
        "run_id": run_id,
        "result": "RUNNING",
        "started_at": started,
        "completed_at": None,
        "failure_stage": None,
        "exit_code": None,
        "evidence_class": {
            "classes": [
                "specification",
                "offline_static",
                "offline_unit",
                "offline_build",
                "synthetic_sil",
            ],
            "physical_evidence_present": False,
        },
        "workspace_identity": {
            "git_head": git_head,
            "working_tree_dirty": dirty,
            "tracked_diff_sha256": sha256(tracked_diff),
            "source_manifest_file_count": file_count,
            "source_manifest_sha256": manifest_sha,
            "canonical_configuration_id": config["configuration_id"],
            "canonical_configuration_revision": config["configuration_revision"],
            "canonical_configuration_digest": config["configuration_integrity"][
                "digest"
            ],
        },
        "environment": {
            "platform": platform.platform(),
            "python": tool_version("python3"),
            "node": tool_version("node"),
            "npm": tool_version("npm"),
            "gxx": tool_version("g++"),
            "platformio": tool_version("pio"),
            "git": tool_version("git"),
        },
        "artifact_hashes": artifact_hashes,
        "claim_invariants": claims,
        "stages": [],
    }


def load_report(path: Path) -> dict[str, Any]:
    value = read_json(path)
    validate(value)
    return value


def stage_start(path: Path, stage_id: str, command_text: str) -> None:
    value = load_report(path)
    if value["result"] != "RUNNING":
        raise GateReportError("cannot start stage on a finalized report")
    if any(stage["result"] == "RUNNING" for stage in value["stages"]):
        raise GateReportError("another stage is already running")
    if any(stage["stage_id"] == stage_id for stage in value["stages"]):
        raise GateReportError(f"duplicate stage ID: {stage_id}")
    value["stages"].append(
        {
            "sequence": len(value["stages"]) + 1,
            "stage_id": stage_id,
            "command": command_text,
            "started_at": now(),
            "completed_at": None,
            "result": "RUNNING",
            "exit_code": None,
        }
    )
    atomic_write(path, value)


def stage_end(path: Path, stage_id: str, result: str, exit_code: int) -> None:
    value = load_report(path)
    if value["result"] != "RUNNING" or not value["stages"]:
        raise GateReportError("no active report stage")
    stage = value["stages"][-1]
    if stage["stage_id"] != stage_id or stage["result"] != "RUNNING":
        raise GateReportError(f"stage completion mismatch: {stage_id}")
    if (result == "PASS") != (exit_code == 0):
        raise GateReportError("stage result and exit code disagree")
    stage["result"] = result
    stage["exit_code"] = exit_code
    stage["completed_at"] = now()
    atomic_write(path, value)


def finalize(
    path: Path, result: str, exit_code: int, failure_stage: str | None
) -> None:
    value = load_report(path)
    if value["result"] != "RUNNING":
        raise GateReportError("report is already finalized")
    if any(stage["result"] == "RUNNING" for stage in value["stages"]):
        raise GateReportError("cannot finalize while a stage is running")
    if result == "PASS":
        if exit_code != 0 or failure_stage is not None:
            raise GateReportError("passing finalization metadata disagrees")
        if any(stage["result"] != "PASS" for stage in value["stages"]):
            raise GateReportError("cannot pass after a failed stage")
    else:
        if exit_code == 0 or not failure_stage:
            raise GateReportError("failed finalization needs stage and nonzero exit")
    value["result"] = result
    value["exit_code"] = exit_code
    value["failure_stage"] = failure_stage
    value["completed_at"] = now()
    atomic_write(path, value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, help="report JSON path"
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("init")
    start = subparsers.add_parser("stage-start")
    start.add_argument("--stage", required=True)
    start.add_argument("--command", required=True)
    end = subparsers.add_parser("stage-end")
    end.add_argument("--stage", required=True)
    end.add_argument("--result", choices=("PASS", "FAIL"), required=True)
    end.add_argument("--exit-code", type=int, required=True)
    finish = subparsers.add_parser("finalize")
    finish.add_argument("--result", choices=("PASS", "FAIL"), required=True)
    finish.add_argument("--exit-code", type=int, required=True)
    finish.add_argument("--failure-stage")
    subparsers.add_parser("validate")
    subparsers.add_parser("print")
    args = parser.parse_args()
    path = args.output.resolve()
    if args.operation == "init":
        atomic_write(path, initial_report())
    elif args.operation == "stage-start":
        stage_start(path, args.stage, args.command)
    elif args.operation == "stage-end":
        stage_end(path, args.stage, args.result, args.exit_code)
    elif args.operation == "finalize":
        finalize(
            path,
            args.result,
            args.exit_code,
            args.failure_stage,
        )
    elif args.operation == "validate":
        load_report(path)
    elif args.operation == "print":
        value = load_report(path)
        sys.stdout.buffer.write(canonical(value))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GateReportError, OSError, ValueError) as error:
        print(f"Offline gate report failed: {error}", file=sys.stderr)
        raise SystemExit(1)
