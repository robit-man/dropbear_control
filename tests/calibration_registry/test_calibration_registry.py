from __future__ import annotations

import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from myactuator_lib.calibration import (
    CalibrationAdmissionCode,
    CalibrationRegistry,
    CalibrationRegistryError,
    CalibrationSubject,
    ConfigurationIdentity,
    ExactDriveTuple,
    record_digest,
    registry_digest,
    validate_registry,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas/myactuator-calibration-registry.schema.json"
REGISTRY_PATH = ROOT / "assets/myactuator/calibration_registry.json"
CONFIG_PATH = ROOT / "schemas/examples/dropbear-observed-incomplete.json"
CLI = ROOT / "tools/validate_calibration_registry.py"
ALL_INVALIDATIONS = [
    "actuator_replaced",
    "sensor_replaced",
    "controller_replaced",
    "native_node_reassigned",
    "mechanical_disassembly",
    "drive_firmware_changed",
    "canonical_configuration_changed",
    "coordinate_frame_changed",
    "procedure_or_fixture_changed",
    "validity_expired",
]


def exact_configuration() -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {
        "configuration_id": config["configuration_id"],
        "configuration_revision": config["configuration_revision"],
        "canonical_digest": config["configuration_integrity"]["digest"],
    }


def record(*, evidence_class: str = "physical_bench", state: str = "accepted") -> dict:
    review = None
    if state != "draft":
        review = {
            "reviewer_id": "independent-reviewer",
            "reviewer_kind": "identified_human",
            "independent_of_operator": True,
            "reviewed_at": "2026-01-02T00:00:00Z",
            "disposition": {"accepted": "accept", "rejected": "reject", "revoked": "revoke"}[state],
            "rationale": "Fixture transform and residual evidence reviewed.",
        }
    value = {
        "record_schema_version": "myactuator-calibration-record/1",
        "record_id": "left-hip-roll-calibration-r1",
        "calibration_family_id": "left-hip-roll-calibration",
        "record_revision": 1,
        "supersedes_record_id": None,
        "state": state,
        "evidence_class": evidence_class,
        "subject": {
            "robot_id": "dropbear",
            "robot_hardware_revision": "synthetic-test-revision",
            "canonical_joint_name": "left_hip_roll",
            "actuator_id": "actuator-left-hip-roll",
            "installed_actuator_serial": "fixture-actuator-0001",
            "exact_tuple": {
                "manufacturer": "MYACTUATOR",
                "series": "RMD-X",
                "model": "RMD-X10-S2",
                "hardware_revision": "fixture-hw-1",
                "drive_firmware": "fixture-fw-4.4",
                "protocol_name": "RMD-CAN",
                "protocol_revision": "V4.4",
                "transport": "CAN_CLASSIC",
                "control_mode": "CURRENT_Q",
            },
            "bus_id": "left-leg-can",
            "native_node_id": 10,
            "sensor_id": "left-hip-roll-external",
            "sensor_kind": "external_absolute",
            "sensor_serial": "fixture-sensor-0001",
            "configuration": exact_configuration(),
        },
        "coordinates": {
            "raw_unit": "count",
            "raw_zero": 0.0,
            "joint_zero_rad": 0.0,
            "native_output_zero_rad": 0.0,
            "raw_to_joint_scale_rad_per_unit": 2.0 * math.pi / 4096.0,
            "motor_to_joint_sign": 1,
            "output_per_motor_ratio": 0.1,
            "canonical_joint_positive_definition": "Positive rotation about the synthetic fixture +Z axis.",
            "wrap": {
                "enabled": True,
                "raw_period": 4096.0,
                "canonical_period_rad": 2.0 * math.pi,
                "canonical_interval": "centered",
            },
        },
        "procedure": {
            "procedure_id": "synthetic-affine-calibration",
            "procedure_revision": 1,
            "method": "Three exact synthetic reference positions establish affine conversion.",
            "fixture_reference": "synthetic-fixture-v1",
            "operator_id": "fixture-operator",
            "recorded_at": "2026-01-01T00:00:00Z",
            "environment": {
                "temperature_c": 20.0,
                "supply_voltage_v": 0.0,
                "robot_support_state": "synthetic fixture; no physical hardware",
            },
            "tools": [
                {
                    "tool_id": "synthetic-reference",
                    "tool_type": "deterministic numeric fixture",
                    "serial": "fixture-tool-0001",
                    "version": "1.0.0",
                    "calibration_due_at": "2027-01-01T00:00:00Z",
                }
            ],
            "source_artifacts": [
                {
                    "artifact_id": "synthetic-measurements",
                    "path_or_uri": "tests/calibration_registry/synthetic-fixture-v1",
                    "sha256": "1" * 64,
                    "authority": "measurement",
                }
            ],
        },
        "measurements": {
            "samples": [
                {"sample_index": 0, "raw_value": 0.0, "reference_joint_rad": 0.0, "residual_rad": 0.0},
                {"sample_index": 1, "raw_value": 1024.0, "reference_joint_rad": math.pi / 2.0, "residual_rad": 0.0},
                {"sample_index": 2, "raw_value": 2048.0, "reference_joint_rad": math.pi, "residual_rad": 0.0},
            ],
            "uncertainty_rad": 0.001,
            "max_absolute_residual_rad": 0.0,
            "repeatability_rad": 0.0,
            "acceptance_max_residual_rad": 0.01,
            "acceptance_max_uncertainty_rad": 0.01,
            "acceptance_passed": True,
        },
        "review": review,
        "validity": {
            "valid_from": "2026-01-02T00:00:00Z",
            "valid_until": "2028-01-02T00:00:00Z",
            "invalidation_conditions": list(ALL_INVALIDATIONS),
        },
        "integrity": {
            "algorithm": "SHA-256",
            "canonicalization": "UTF-8 sorted-key compact JSON excluding integrity.digest",
            "digest": "0" * 64,
        },
    }
    value["integrity"]["digest"] = record_digest(value)
    return value


def registry(records: list[dict]) -> dict:
    superseded = {row["supersedes_record_id"] for row in records if row["supersedes_record_id"] is not None}
    count = sum(
        row["state"] == "accepted"
        and row["evidence_class"] == "physical_bench"
        and row["record_id"] not in superseded
        for row in records
    )
    value = {
        "schema_version": "myactuator-calibration-registry/1",
        "registry_id": "dropbear-physical-calibrations",
        "registry_revision": 1,
        "authority": "reviewed_records_only",
        "configuration": exact_configuration(),
        "records": records,
        "physical_admission": {
            "accepted_physical_record_count": count,
            "motion_enable_allowed": False,
            "blockers": ["fixture_registry_does_not_authorize_motion"],
        },
        "integrity": {
            "algorithm": "SHA-256",
            "canonicalization": "UTF-8 sorted-key compact JSON excluding integrity.digest",
            "digest": "0" * 64,
        },
    }
    value["integrity"]["digest"] = registry_digest(value)
    return value


def reseal(value: dict) -> None:
    for row in value["records"]:
        row["integrity"]["digest"] = record_digest(row)
    value["integrity"]["digest"] = registry_digest(value)


def subject_from(row: dict) -> CalibrationSubject:
    value = row["subject"]
    return CalibrationSubject(
        robot_id=value["robot_id"],
        robot_hardware_revision=value["robot_hardware_revision"],
        canonical_joint_name=value["canonical_joint_name"],
        actuator_id=value["actuator_id"],
        installed_actuator_serial=value["installed_actuator_serial"],
        exact_tuple=ExactDriveTuple(**value["exact_tuple"]),
        bus_id=value["bus_id"],
        native_node_id=value["native_node_id"],
        sensor_id=value["sensor_id"],
        sensor_kind=value["sensor_kind"],
        sensor_serial=value["sensor_serial"],
        configuration=ConfigurationIdentity(**value["configuration"]),
    )


class CalibrationRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def assert_invalid(self, value: dict, contains: str | None = None) -> None:
        with self.assertRaises(CalibrationRegistryError) as caught:
            validate_registry(value, self.schema)
        if contains:
            self.assertIn(contains, str(caught.exception))

    def test_tracked_registry_is_empty_bound_and_motion_denied(self) -> None:
        tracked = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        validate_registry(tracked, self.schema)
        self.assertEqual(exact_configuration(), tracked["configuration"])
        self.assertEqual([], tracked["records"])
        loaded = CalibrationRegistry.load(REGISTRY_PATH, SCHEMA_PATH)
        self.assertEqual(0, loaded.accepted_physical_record_count)
        self.assertFalse(loaded.motion_enable_allowed)

    def test_synthetic_accepted_record_is_valid_but_never_physical(self) -> None:
        row = record(evidence_class="synthetic_fixture")
        loaded = CalibrationRegistry(registry([row]), self.schema)
        decision = loaded.admit_physical(
            row["record_id"], subject_from(row), datetime(2027, 1, 1, tzinfo=timezone.utc)
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(CalibrationAdmissionCode.NONPHYSICAL_EVIDENCE, decision.code)
        self.assertEqual(0, loaded.accepted_physical_record_count)

    def test_exact_physical_record_admits_only_inside_validity(self) -> None:
        row = record()
        loaded = CalibrationRegistry(registry([row]), self.schema)
        selected = subject_from(row)
        at_start = loaded.admit_physical(
            row["record_id"], selected, datetime(2026, 1, 2, tzinfo=timezone.utc)
        )
        at_end = loaded.admit_physical(
            row["record_id"], selected, datetime(2028, 1, 2, tzinfo=timezone.utc)
        )
        self.assertTrue(at_start.allowed)
        self.assertTrue(at_end.allowed)
        self.assertEqual(CalibrationAdmissionCode.ADMITTED, at_start.code)
        self.assertEqual(1, loaded.accepted_physical_record_count)

        before = loaded.admit_physical(
            row["record_id"], selected, datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        after = loaded.admit_physical(
            row["record_id"], selected, datetime(2028, 1, 2, 0, 0, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(CalibrationAdmissionCode.NOT_YET_VALID, before.code)
        self.assertEqual(CalibrationAdmissionCode.EXPIRED, after.code)

    def test_every_subject_field_participates_in_exact_admission(self) -> None:
        row = record()
        loaded = CalibrationRegistry(registry([row]), self.schema)
        selected = subject_from(row)
        mutations = {
            "robot_id": "another-robot",
            "robot_hardware_revision": "another-revision",
            "canonical_joint_name": "right_hip_roll",
            "actuator_id": "actuator-right-hip-roll",
            "installed_actuator_serial": "another-actuator",
            "bus_id": "right-leg-can",
            "native_node_id": 11,
            "sensor_id": "another-sensor",
            "sensor_kind": "native_output",
            "sensor_serial": "another-serial",
            "configuration": ConfigurationIdentity("another-config", 1, "2" * 64),
            "exact_tuple": ExactDriveTuple(
                **{**selected.exact_tuple.__dict__, "drive_firmware": "different-firmware"}
            ),
        }
        for field, replacement in mutations.items():
            with self.subTest(field=field):
                changed = CalibrationSubject(**{**selected.__dict__, field: replacement})
                decision = loaded.admit_physical(
                    row["record_id"], changed, datetime(2027, 1, 1, tzinfo=timezone.utc)
                )
                self.assertEqual(CalibrationAdmissionCode.SUBJECT_MISMATCH, decision.code)

    def test_explicit_record_selection_has_no_latest_or_family_fallback(self) -> None:
        row = record()
        loaded = CalibrationRegistry(registry([row]), self.schema)
        decision = loaded.admit_physical(
            "left-hip-roll-calibration",
            subject_from(row),
            datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(CalibrationAdmissionCode.RECORD_NOT_FOUND, decision.code)

    def test_draft_and_rejected_records_never_admit(self) -> None:
        for state in ("draft", "rejected"):
            with self.subTest(state=state):
                row = record(state=state)
                loaded = CalibrationRegistry(registry([row]), self.schema)
                decision = loaded.admit_physical(
                    row["record_id"], subject_from(row), datetime(2027, 1, 1, tzinfo=timezone.utc)
                )
                self.assertEqual(CalibrationAdmissionCode.RECORD_NOT_ACCEPTED, decision.code)

    def test_supersession_is_linear_and_old_record_is_denied(self) -> None:
        first = record()
        second = copy.deepcopy(first)
        second["record_id"] = "left-hip-roll-calibration-r2"
        second["record_revision"] = 2
        second["supersedes_record_id"] = first["record_id"]
        second["integrity"]["digest"] = record_digest(second)
        loaded = CalibrationRegistry(registry([first, second]), self.schema)
        at = datetime(2027, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(
            CalibrationAdmissionCode.RECORD_SUPERSEDED,
            loaded.admit_physical(first["record_id"], subject_from(first), at).code,
        )
        self.assertTrue(loaded.admit_physical(second["record_id"], subject_from(second), at).allowed)
        self.assertEqual(1, loaded.accepted_physical_record_count)

    def test_digest_tamper_and_nonfinite_values_fail(self) -> None:
        value = registry([record()])
        value["records"][0]["coordinates"]["raw_zero"] = 1.0
        self.assert_invalid(value, "digest mismatch")

        value = registry([record()])
        value["records"][0]["coordinates"]["raw_zero"] = math.nan
        self.assert_invalid(value, "non-finite")

    def test_measurement_procedure_review_and_wrap_semantics_fail_closed(self) -> None:
        mutations = [
            (lambda row: row["measurements"]["samples"][1].__setitem__("sample_index", 2), "sample indexes"),
            (lambda row: row["measurements"].__setitem__("max_absolute_residual_rad", 0.1), "maximum residual"),
            (lambda row: row["measurements"].__setitem__("acceptance_passed", False), "acceptance_passed"),
            (lambda row: row["review"].__setitem__("reviewer_id", "fixture-operator"), "reviewer and operator"),
            (lambda row: row["procedure"]["tools"][0].__setitem__("calibration_due_at", "2025-01-01T00:00:00Z"), "past its calibration"),
            (lambda row: row["coordinates"]["wrap"].__setitem__("canonical_period_rad", 7.0), "wrap periods"),
            (lambda row: row["validity"].__setitem__("valid_until", "2025-01-01T00:00:00Z"), "validity interval"),
            (lambda row: row["validity"]["invalidation_conditions"].pop(), "every required invalidation"),
            (lambda row: row["subject"]["exact_tuple"].__setitem__("model", "UNKNOWN"), "unknown or wildcard"),
        ]
        for mutation, expected in mutations:
            with self.subTest(expected=expected):
                row = record()
                mutation(row)
                value = registry([row])
                reseal(value)
                self.assert_invalid(value, expected)

    def test_configuration_drift_count_lie_and_supersession_fork_fail(self) -> None:
        value = registry([record()])
        value["records"][0]["subject"]["configuration"]["configuration_revision"] = 2
        reseal(value)
        self.assert_invalid(value, "configuration does not equal")

        value = registry([record()])
        value["physical_admission"]["accepted_physical_record_count"] = 0
        value["integrity"]["digest"] = registry_digest(value)
        self.assert_invalid(value, "count does not match")

        first = record()
        second = copy.deepcopy(first)
        second.update(record_id="left-hip-roll-calibration-r2", record_revision=2, supersedes_record_id=first["record_id"])
        second["integrity"]["digest"] = record_digest(second)
        third = copy.deepcopy(first)
        third.update(record_id="left-hip-roll-calibration-r3", record_revision=3, supersedes_record_id=first["record_id"])
        third["integrity"]["digest"] = record_digest(third)
        self.assert_invalid(registry([first, second, third]), "superseded more than once")

    def test_cli_validates_and_never_rewrites(self) -> None:
        before = REGISTRY_PATH.read_bytes()
        result = subprocess.run(
            [sys.executable, str(CLI), str(REGISTRY_PATH)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("records=0 accepted_physical=0 motion=false", result.stdout)
        self.assertEqual(before, REGISTRY_PATH.read_bytes())

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            bad = json.loads(before)
            bad["physical_admission"]["motion_enable_allowed"] = True
            path.write_text(json.dumps(bad), encoding="utf-8")
            denied = subprocess.run(
                [sys.executable, str(CLI), str(path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(0, denied.returncode)


if __name__ == "__main__":
    unittest.main()
