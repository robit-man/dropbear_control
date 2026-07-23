#!/usr/bin/env python3
"""Generate exact per-actuator Dropbear readiness denials."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "tools"))

from generate_dropbear_views import validate_inputs  # noqa: E402
from myactuator_lib.calibration import CalibrationRegistry  # noqa: E402
from myactuator_lib.limits import LimitRegistry  # noqa: E402


CONFIG = ROOT / "schemas/examples/dropbear-observed-incomplete.json"
CONFIG_SCHEMA = ROOT / "schemas/dropbear-config.schema.json"
RECONCILIATION = ROOT / "generated/dropbear_reconciliation/reconciliation.json"
RECONCILIATION_SCHEMA = ROOT / "schemas/dropbear-reconciliation.schema.json"
CALIBRATIONS = ROOT / "assets/myactuator/calibration_registry.json"
CALIBRATION_SCHEMA = ROOT / "schemas/myactuator-calibration-registry.schema.json"
LIMITS = ROOT / "assets/myactuator/limit_registry.json"
LIMIT_SCHEMA = ROOT / "schemas/myactuator-limit-registry.schema.json"
OUTPUT = ROOT / "generated/dropbear_readiness/readiness.json"
OUTPUT_SCHEMA = ROOT / "schemas/dropbear-readiness.schema.json"


class ReadinessError(RuntimeError):
    pass


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReadinessError(f"JSON root must be an object: {path}")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def schema_validate(value: dict, schema_path: Path, label: str) -> None:
    schema = load(schema_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: (list(e.absolute_path), e.message))
    if errors:
        error = errors[0]
        raise ReadinessError(f"{label} schema failure at /{'/'.join(map(str, error.absolute_path))}: {error.message}")


def build() -> dict:
    config = validate_inputs(CONFIG, CONFIG_SCHEMA).config
    reconciliation = load(RECONCILIATION)
    schema_validate(reconciliation, RECONCILIATION_SCHEMA, "reconciliation")
    CalibrationRegistry.load(CALIBRATIONS, CALIBRATION_SCHEMA)
    LimitRegistry.load(LIMITS, LIMIT_SCHEMA)
    calibrations = load(CALIBRATIONS)
    limits = load(LIMITS)
    digest = config["configuration_integrity"]["digest"]
    for candidate in (reconciliation["generated_from"]["canonical_configuration_digest"], calibrations["configuration"]["canonical_digest"], limits["configuration"]["canonical_digest"]):
        if candidate != digest:
            raise ReadinessError("configuration digest disagreement across readiness inputs")
    by_name = {row["canonical_joint_name"]: row for row in reconciliation["actuators"]}
    if len(by_name) != 12:
        raise ReadinessError("reconciliation must expose exactly 12 unique canonical joints")

    rows = []
    for joint in config["joints"]:
        observed = by_name.get(joint["canonical_name"])
        if observed is None or observed["actuator_id"] != joint["actuator_id"]:
            raise ReadinessError(f"joint/actuator reconciliation mismatch: {joint['canonical_name']}")
        external_present = joint["feedback"]["external_sensor_id"] is not None
        blockers = [
            "installed_identity_missing",
            "native_protocol_applicability_missing",
            "exclusive_runtime_route_missing",
            "accepted_physical_calibration_missing",
            "complete_four_class_limit_set_missing",
            "native_telemetry_path_missing",
            "reviewed_feedback_reconciliation_policy_missing",
            "accepted_dropbear_cad_binding_missing",
            "reviewed_ros_actuation_mapping_missing",
            "independent_safe_power_evidence_missing",
            "hil_evidence_missing",
        ]
        if not external_present:
            blockers.insert(5, "external_joint_feedback_missing")
        dependencies = [
            {"dependency": "configuration_identity", "status": "verified_identity_only", "evidence_ids": [digest]},
            {"dependency": "installed_actuator_identity", "status": "missing", "evidence_ids": []},
            {"dependency": "native_protocol_applicability", "status": "missing", "evidence_ids": []},
            {"dependency": "exclusive_runtime_route", "status": "missing", "evidence_ids": []},
            {"dependency": "physical_calibration", "status": "missing", "evidence_ids": []},
            {"dependency": "complete_limit_set", "status": "missing", "evidence_ids": []},
            {"dependency": "external_feedback", "status": "unverified_observation" if external_present else "missing", "evidence_ids": [joint["feedback"]["external_sensor_id"]] if external_present else []},
            {"dependency": "native_telemetry", "status": "missing", "evidence_ids": []},
            {"dependency": "feedback_reconciliation_policy", "status": "missing", "evidence_ids": []},
            {"dependency": "accepted_cad_binding", "status": "missing", "evidence_ids": []},
            {"dependency": "reviewed_ros_actuation_mapping", "status": "missing", "evidence_ids": []},
            {"dependency": "independent_safe_power", "status": "missing", "evidence_ids": []},
            {"dependency": "hil_evidence", "status": "missing", "evidence_ids": []},
        ]
        rows.append({
            "actuator_id": joint["actuator_id"],
            "canonical_joint_name": joint["canonical_name"],
            "chirality": joint["chirality"],
            "semantic_joint": joint["semantic_joint"],
            "dependencies": dependencies,
            "runtime_materialization": {
                "installed_tuple": None,
                "route": None,
                "calibration_record_id": None,
                "effective_limit_record_ids": [],
                "feedback_policy_id": None,
                "cad_binding_id": None,
                "ros_actuation_mapping_id": None,
            },
            "motion_ready": False,
            "blockers": blockers,
        })

    artifact = {
        "schema_version": "dropbear-readiness/1",
        "artifact_id": "dropbear-actuator-readiness",
        "authority": "derived_denial_only",
        "configuration": {
            "configuration_id": config["configuration_id"],
            "configuration_revision": config["configuration_revision"],
            "canonical_digest": digest,
        },
        "sources": [
            {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}
            for path in (CONFIG, RECONCILIATION, CALIBRATIONS, LIMITS)
        ],
        "summary": {
            "actuator_count": 12,
            "external_feedback_observation_count": 10,
            "motion_ready_count": 0,
            "materialized_route_count": 0,
            "accepted_physical_calibration_count": calibrations["physical_admission"]["accepted_physical_record_count"],
            "accepted_measured_limit_record_count": limits["physical_admission"]["accepted_measured_record_count"],
            "reviewed_ros_actuation_mapping_count": 0,
            "motion_enable_allowed": False,
        },
        "actuators": rows,
        "global_blockers": [
            "canonical_configuration_is_incomplete_observation",
            "installed_topology_and_protocol_applicability_missing",
            "physical_calibration_and_limit_evidence_missing",
            "reviewed_robot_actuation_graph_missing",
            "independent_safe_power_and_hil_evidence_missing",
        ],
    }
    schema_validate(artifact, OUTPUT_SCHEMA, "readiness")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rendered = canonical(build())
    output = args.output.resolve()
    if args.check:
        if not output.exists() or output.read_bytes() != rendered:
            raise ReadinessError(f"generated artifact drift: {output}")
        print(f"DROPBEAR_READINESS_OK actuators=12 ready=0 routes=0 motion=false sha256={hashlib.sha256(rendered).hexdigest()}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rendered)
    print(f"wrote {output.relative_to(ROOT)} sha256={hashlib.sha256(rendered).hexdigest()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ReadinessError) as error:
        print(f"Dropbear readiness generation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
