#!/usr/bin/env python3
"""Prepare and validate the no-authority Dropbear unpowered-discovery package."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
RECONCILIATION = ROOT / "generated/dropbear_reconciliation/reconciliation.json"
INVENTORY_SCHEMA = ROOT / "schemas/dropbear-installed-inventory.schema.json"
STATUS_SCHEMA = ROOT / "schemas/dropbear-unpowered-discovery-status.schema.json"
TEMPLATE = ROOT / "assets/dropbear/installed_inventory_template.json"
SUBMISSIONS = ROOT / "assets/dropbear/installed_inventories"
STATUS = ROOT / "generated/dropbear_unpowered_discovery/status.json"
DISCOVERY = ROOT / ".aiwg/iterations/iteration-10/discovery"
ITERATION_12_DISCOVERY = ROOT / ".aiwg/iterations/iteration-11/discovery"
PACKAGE_DOCS = (
    DISCOVERY / "installed-inventory-capture-runbook.md",
    DISCOVERY / "can-controller-decision-matrix.md",
    DISCOVERY / "listen-only-capture-runbook.md",
    DISCOVERY / "independent-power-survey-plan.md",
    DISCOVERY / "calibration-limit-hil-campaigns.md",
    DISCOVERY / "cad-plant-intake-plan.md",
    DISCOVERY / "authorization-register.md",
    ITERATION_12_DISCOVERY / "discovery-plan.md",
    ITERATION_12_DISCOVERY / "u0-authorization-request.md",
    ITERATION_12_DISCOVERY / "reviewer-assignment-register.md",
    ITERATION_12_DISCOVERY / "iteration-12-readiness-status.md",
)


class DiscoveryPreparationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DiscoveryPreparationError(message)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DiscoveryPreparationError(f"cannot read {path}: {error}") from error
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


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
        raise DiscoveryPreparationError(
            f"{label} schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def utc(value: str, label: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(
        parsed.tzinfo is not None
        and parsed.utcoffset() == dt.timedelta(0),
        f"{label} must be UTC",
    )
    return parsed


def digest_payload(record: dict[str, Any]) -> bytes:
    value = copy.deepcopy(record)
    value["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(value)


def set_digest(record: dict[str, Any]) -> None:
    record["integrity"]["record_sha256"] = sha_bytes(digest_payload(record))


def reconciliation() -> dict[str, Any]:
    value = load(RECONCILIATION)
    require(
        value["schema_version"] == "dropbear-reconciliation/1"
        and value["summary"]["canonical_actuator_count"] == 12
        and value["summary"]["installed_identity_count"] == 0
        and value["summary"]["motion_enable_allowed"] is False,
        "installed-inventory reconciliation baseline drift",
    )
    return value


def template() -> dict[str, Any]:
    source = reconciliation()
    configuration_digest = source["generated_from"][
        "canonical_configuration_digest"
    ]
    capture_subject = {
        "canonical_configuration_digest": configuration_digest,
        "inventory_schema_sha256": sha_file(INVENTORY_SCHEMA),
    }
    record = {
        "schema_version": "dropbear-installed-inventory/1",
        "record_state": "template",
        "capture_id": (
            "installed-inventory-" + sha_bytes(canonical_bytes(capture_subject))[:20]
        ),
        "scope": "unpowered_identification_only",
        "subject": {
            "canonical_configuration_digest": configuration_digest,
            "robot_revision": None,
            "physical_asset_tag": None,
            "captured_at": None,
        },
        "authorization": {
            "granted": False,
            "authorization_id": None,
            "allowed_actions": [],
            "valid_from": None,
            "valid_until": None,
            "evidence_refs": [],
        },
        "personnel": {
            "operator_id": None,
            "hardware_owner_id": None,
            "safety_reviewer_id": None,
        },
        "controller_path": {
            "observation_status": "unobserved",
            "board_manufacturer": None,
            "board_model": None,
            "board_revision": None,
            "board_serial": None,
            "controller_kind": "unknown",
            "controller_part": None,
            "controller_oscillator_hz": None,
            "transceiver_part": None,
            "transceiver_isolation": "unknown",
            "transceiver_silent_or_standby_control": None,
            "physically_enforced_tx_disable": None,
            "termination_ohm": None,
            "connector_id": None,
            "ground_reference": None,
            "pin_observations": [],
            "evidence_refs": [],
        },
        "motors": [
            {
                "canonical_actuator_id": row["actuator_id"],
                "observation_status": "unobserved",
                "manufacturer": None,
                "series": None,
                "model": None,
                "hardware_revision": None,
                "drive_firmware": None,
                "serial_number": None,
                "protocol_name": None,
                "protocol_revision": None,
                "native_node_id": None,
                "brake_observation": None,
                "bus_connector_observation": None,
                "evidence_refs": [],
            }
            for row in source["actuators"]
        ],
        "conflicts": [],
        "evidence": [],
        "record_complete": False,
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(record)
    validate_inventory(record)
    return record


def evidence_refs(record: dict[str, Any]) -> list[str]:
    refs = list(record["authorization"]["evidence_refs"])
    refs.extend(record["controller_path"]["evidence_refs"])
    for pin in record["controller_path"]["pin_observations"]:
        refs.extend(pin["evidence_refs"])
    for motor in record["motors"]:
        refs.extend(motor["evidence_refs"])
    for conflict in record["conflicts"]:
        refs.extend(conflict["evidence_refs"])
    return refs


def validate_inventory(
    record: dict[str, Any], *, verify_evidence_files: bool = True
) -> None:
    schema_validate(record, INVENTORY_SCHEMA, "installed inventory")
    source = reconciliation()
    require(
        record["subject"]["canonical_configuration_digest"]
        == source["generated_from"]["canonical_configuration_digest"],
        "installed inventory configuration drift",
    )
    require(
        record["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(record)),
        "installed inventory record digest mismatch",
    )
    require(
        record["support_granted"] is False
        and record["physical_motion_authority"] is False,
        "installed inventory grants support/motion",
    )
    expected_ids = [row["actuator_id"] for row in source["actuators"]]
    observed_ids = [row["canonical_actuator_id"] for row in record["motors"]]
    require(observed_ids == expected_ids, "installed actuator coverage/order drift")

    evidence = {row["evidence_id"]: row for row in record["evidence"]}
    require(
        len(evidence) == len(record["evidence"]),
        "duplicate installed-inventory evidence ID",
    )
    for reference in evidence_refs(record):
        require(reference in evidence, f"unknown inventory evidence ref: {reference}")
    if verify_evidence_files:
        for row in evidence.values():
            path = (ROOT / row["relative_path"]).resolve()
            try:
                path.relative_to(ROOT.resolve())
            except ValueError as error:
                raise DiscoveryPreparationError(
                    "installed inventory evidence path escapes repository"
                ) from error
            require(
                path.is_file() and sha_file(path) == row["sha256"],
                f"installed inventory evidence missing/changed: {row['evidence_id']}",
            )

    if record["record_state"] == "template":
        require(
            record == template_without_validation(record),
            "installed-inventory template contains observations/authority",
        )
        return

    authorization = record["authorization"]
    require(
        authorization["granted"] is True
        and authorization["authorization_id"]
        and authorization["allowed_actions"]
        and authorization["valid_from"]
        and authorization["valid_until"]
        and authorization["evidence_refs"],
        "submitted inventory lacks exact unpowered authorization",
    )
    valid_from = utc(authorization["valid_from"], "authorization valid_from")
    valid_until = utc(authorization["valid_until"], "authorization valid_until")
    require(valid_until > valid_from, "authorization interval is empty/reversed")
    require(record["subject"]["captured_at"] is not None, "capture time is missing")
    captured_at = utc(record["subject"]["captured_at"], "capture time")
    require(
        valid_from <= captured_at <= valid_until,
        "capture time falls outside authorization",
    )
    personnel = record["personnel"]
    require(
        all(personnel.values())
        and personnel["operator_id"] != personnel["safety_reviewer_id"],
        "submitted inventory lacks independent named personnel",
    )

    serials: dict[str, list[str]] = defaultdict(list)
    nodes: dict[int, list[str]] = defaultdict(list)
    for motor in record["motors"]:
        if motor["serial_number"] is not None:
            serials[motor["serial_number"]].append(
                motor["canonical_actuator_id"]
            )
        if motor["native_node_id"] is not None:
            nodes[motor["native_node_id"]].append(
                motor["canonical_actuator_id"]
            )
    conflicts_by_kind = defaultdict(list)
    for conflict in record["conflicts"]:
        require(
            conflict["rationale"] and conflict["evidence_refs"],
            f"inventory conflict lacks evidence: {conflict['conflict_id']}",
        )
        conflicts_by_kind[conflict["kind"]].append(
            set(conflict["subject_ids"])
        )
    for values, kind in (
        (serials, "duplicate_serial"),
        (nodes, "duplicate_native_node"),
    ):
        for duplicate_ids in values.values():
            if len(duplicate_ids) > 1:
                require(
                    any(
                        set(duplicate_ids) <= subjects
                        for subjects in conflicts_by_kind[kind]
                    ),
                    f"{kind} lacks explicit conflict record",
                )

    controller_required = (
        "board_manufacturer",
        "board_model",
        "board_revision",
        "board_serial",
        "controller_part",
        "controller_oscillator_hz",
        "transceiver_part",
        "transceiver_silent_or_standby_control",
        "physically_enforced_tx_disable",
        "termination_ohm",
        "connector_id",
        "ground_reference",
    )
    controller = record["controller_path"]
    controller_complete = (
        controller["observation_status"] == "observed_complete"
        and controller["controller_kind"] != "unknown"
        and controller["transceiver_isolation"] != "unknown"
        and all(controller[field] is not None for field in controller_required)
        and bool(controller["pin_observations"])
        and bool(controller["evidence_refs"])
    )
    motor_required = (
        "manufacturer",
        "series",
        "model",
        "hardware_revision",
        "drive_firmware",
        "serial_number",
        "protocol_name",
        "protocol_revision",
        "native_node_id",
        "brake_observation",
        "bus_connector_observation",
    )
    motors_complete = all(
        motor["observation_status"] == "observed_complete"
        and all(motor[field] is not None for field in motor_required)
        and bool(motor["evidence_refs"])
        for motor in record["motors"]
    )
    complete = controller_complete and motors_complete
    require(
        record["record_complete"] is complete,
        "installed inventory completeness claim disagrees",
    )


def template_without_validation(record: dict[str, Any]) -> dict[str, Any]:
    expected = copy.deepcopy(record)
    expected["subject"].update(
        robot_revision=None,
        physical_asset_tag=None,
        captured_at=None,
    )
    expected["authorization"] = {
        "granted": False,
        "authorization_id": None,
        "allowed_actions": [],
        "valid_from": None,
        "valid_until": None,
        "evidence_refs": [],
    }
    expected["personnel"] = {
        "operator_id": None,
        "hardware_owner_id": None,
        "safety_reviewer_id": None,
    }
    expected["controller_path"] = template_controller()
    for motor in expected["motors"]:
        motor.update(
            observation_status="unobserved",
            manufacturer=None,
            series=None,
            model=None,
            hardware_revision=None,
            drive_firmware=None,
            serial_number=None,
            protocol_name=None,
            protocol_revision=None,
            native_node_id=None,
            brake_observation=None,
            bus_connector_observation=None,
            evidence_refs=[],
        )
    expected["conflicts"] = []
    expected["evidence"] = []
    expected["record_complete"] = False
    expected["support_granted"] = False
    expected["physical_motion_authority"] = False
    set_digest(expected)
    return expected


def template_controller() -> dict[str, Any]:
    return {
        "observation_status": "unobserved",
        "board_manufacturer": None,
        "board_model": None,
        "board_revision": None,
        "board_serial": None,
        "controller_kind": "unknown",
        "controller_part": None,
        "controller_oscillator_hz": None,
        "transceiver_part": None,
        "transceiver_isolation": "unknown",
        "transceiver_silent_or_standby_control": None,
        "physically_enforced_tx_disable": None,
        "termination_ohm": None,
        "connector_id": None,
        "ground_reference": None,
        "pin_observations": [],
        "evidence_refs": [],
    }


def package_status(template_value: dict[str, Any]) -> dict[str, Any]:
    submissions = sorted(SUBMISSIONS.glob("*.json")) if SUBMISSIONS.is_dir() else []
    require(
        not submissions,
        "installed-inventory submissions require reviewed discovery status V2",
    )
    sources = [INVENTORY_SCHEMA, TEMPLATE, *PACKAGE_DOCS]
    require(
        len(sources) == 13 and all(path.is_file() for path in sources),
        "discovery package incomplete",
    )
    status = {
        "schema_version": "dropbear-unpowered-discovery-status/1",
        "artifact_id": "dropbear-unpowered-discovery-status",
        "authority": "planning_only_no_execution_authority",
        "sources": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha_file(path),
            }
            for path in sources
        ],
        "summary": {
            "planned_workstream_count": 12,
            "installed_actuator_slot_count": len(template_value["motors"]),
            "submitted_inventory_count": 0,
            "selected_can_controller_count": 0,
            "authorized_action_count": 0,
            "ready_for_human_review": True,
            "ready_for_execution": False,
        },
        "blockers": [
            "hardware_owner_authorization_missing",
            "safety_reviewer_authorization_missing",
            "physical_asset_and_workspace_not_verified",
            "installed_controller_and_transceiver_unknown",
            "physically_enforced_tx_disable_unverified",
            "independent_safe_power_evidence_missing",
        ],
        "support_granted": False,
        "physical_motion_authority": False,
    }
    schema_validate(status, STATUS_SCHEMA, "unpowered discovery status")
    return status


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


def generate() -> tuple[dict[str, Any], dict[str, Any]]:
    value = template()
    atomic_write(TEMPLATE, value)
    status = package_status(value)
    atomic_write(STATUS, status)
    return value, status


def check() -> tuple[dict[str, Any], dict[str, Any]]:
    value = template()
    require(
        TEMPLATE.is_file() and TEMPLATE.read_bytes() == canonical_bytes(value),
        "installed-inventory template drift",
    )
    status = package_status(value)
    require(
        STATUS.is_file() and STATUS.read_bytes() == canonical_bytes(status),
        "unpowered-discovery status drift",
    )
    return value, status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--generate", action="store_true")
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--validate", type=Path)
    args = parser.parse_args()
    if args.validate:
        validate_inventory(load(args.validate.resolve()))
        print(
            "DROPBEAR_INSTALLED_INVENTORY_OK "
            "scope=unpowered support=false motion=false"
        )
        return 0
    value, status = generate() if args.generate else check()
    print(
        "DROPBEAR_UNPOWERED_DISCOVERY_OK "
        f"workstreams=12 slots={len(value['motors'])} "
        f"submitted={status['summary']['submitted_inventory_count']} "
        "selected_controller=0 authorized_actions=0 review=true "
        "execution=false support=false motion=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, DiscoveryPreparationError, ValueError) as error:
        print(f"Dropbear discovery preparation failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
