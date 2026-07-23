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

from myactuator_lib.calibration import ConfigurationIdentity, ExactDriveTuple
from myactuator_lib.limits import (
    LimitQuery,
    LimitRegistry,
    LimitRegistryError,
    LimitSelectionCode,
    LimitSubject,
    OperatingPoint,
    PROVENANCE_CLASSES,
    record_digest,
    registry_digest,
    validate_registry,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas/myactuator-limit-registry.schema.json"
REGISTRY_PATH = ROOT / "assets/myactuator/limit_registry.json"
CONFIG_PATH = ROOT / "schemas/examples/dropbear-observed-incomplete.json"
CLI = ROOT / "tools/validate_limit_registry.py"

EVIDENCE = {
    "vendor_rating": ("vendor_manual", "identified_human"),
    "software_command_limit": ("software_configuration", "identified_human"),
    "measured_safe_robot_limit": ("physical_measurement", "identified_human"),
    "runtime_derate": ("runtime_derate_policy", "runtime_controller"),
}


def configuration() -> dict:
    value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {
        "configuration_id": value["configuration_id"],
        "configuration_revision": value["configuration_revision"],
        "canonical_digest": value["configuration_integrity"]["digest"],
    }


def subject_dict() -> dict:
    return {
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
        "configuration": configuration(),
    }


def subject() -> LimitSubject:
    value = subject_dict()
    return LimitSubject(
        robot_id=value["robot_id"],
        robot_hardware_revision=value["robot_hardware_revision"],
        canonical_joint_name=value["canonical_joint_name"],
        actuator_id=value["actuator_id"],
        installed_actuator_serial=value["installed_actuator_serial"],
        exact_tuple=ExactDriveTuple(**value["exact_tuple"]),
        bus_id=value["bus_id"],
        native_node_id=value["native_node_id"],
        configuration=ConfigurationIdentity(**value["configuration"]),
    )


def limit_record(
    provenance: str,
    direction: str,
    bound: float,
    *,
    quantity: str = "qaxis_current",
    coordinate: str = "electrical",
    unit: str = "A",
    state: str = "accepted",
) -> dict:
    authority, reviewer_kind = EVIDENCE[provenance]
    value = {
        "record_schema_version": "myactuator-limit-record/1",
        "record_id": f"{provenance.replace('_', '-')}-{quantity.replace('_', '-')}-{direction}",
        "record_revision": 1,
        "state": state,
        "provenance_class": provenance,
        "subject": subject_dict(),
        "quantity": quantity,
        "coordinate": coordinate,
        "direction": direction,
        "si_unit": unit,
        "bound_value": bound,
        "control_modes": ["CURRENT_Q" if quantity == "qaxis_current" else "POSITION"],
        "operating_envelope": {
            "supply_voltage_min_v": 40.0,
            "supply_voltage_max_v": 60.0,
            "temperature_min_c": -10.0,
            "temperature_max_c": 80.0,
            "speed_abs_max_rad_s": 5.0,
        },
        "valid_from": "2026-01-02T00:00:00Z",
        "valid_until": "2028-01-02T00:00:00Z",
        "evidence": {
            "artifact_id": f"{provenance.replace('_', '-')}-evidence",
            "path_or_uri": f"tests/limit_registry/{provenance}.json",
            "sha256": {name: str(index + 1) * 64 for index, name in enumerate(PROVENANCE_CLASSES)}[provenance],
            "authority": authority,
            "reviewer_id": "runtime-controller" if reviewer_kind == "runtime_controller" else "identified-limit-reviewer",
            "reviewer_kind": reviewer_kind,
            "reviewed_at": "2026-01-01T00:00:00Z",
        },
        "runtime_snapshot": (
            {
                "generation": 9,
                "sample_time_ns": 100,
                "valid_until_ns": 200,
                "reason_code": "synthetic-temperature-derate",
                "policy_id": "synthetic-derate-policy",
                "policy_sha256": "9" * 64,
            }
            if provenance == "runtime_derate"
            else None
        ),
        "integrity": {
            "algorithm": "SHA-256",
            "canonicalization": "UTF-8 sorted-key compact JSON excluding integrity.digest",
            "digest": "0" * 64,
        },
    }
    value["integrity"]["digest"] = record_digest(value)
    return value


def registry(records: list[dict]) -> dict:
    value = {
        "schema_version": "myactuator-limit-registry/1",
        "registry_id": "dropbear-exact-limits",
        "registry_revision": 1,
        "authority": "reviewed_exact_records_only",
        "configuration": configuration(),
        "records": records,
        "physical_admission": {
            "accepted_measured_record_count": sum(
                row["state"] == "accepted" and row["provenance_class"] == "measured_safe_robot_limit"
                for row in records
            ),
            "motion_enable_allowed": False,
            "blockers": ["fixture_limits_do_not_authorize_motion"],
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


def query(
    *,
    quantity: str = "qaxis_current",
    coordinate: str = "electrical",
    mode: str = "CURRENT_Q",
    classes: tuple[str, ...] = PROVENANCE_CLASSES,
    directions: tuple[str, ...] = ("magnitude",),
    generation: int | None = 9,
    now_ns: int = 150,
    voltage: float | None = 50.0,
    temperature: float | None = 25.0,
    speed: float | None = 1.0,
    at: datetime = datetime(2027, 1, 1, tzinfo=timezone.utc),
) -> LimitQuery:
    return LimitQuery(
        subject=subject(),
        quantity=quantity,
        coordinate=coordinate,
        control_mode=mode,
        required_provenance_classes=classes,
        required_directions=directions,
        runtime_generation=generation,
        operating_point=OperatingPoint(at, now_ns, voltage, temperature, speed),
    )


class LimitRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def assert_invalid(self, value: dict, contains: str) -> None:
        with self.assertRaises(LimitRegistryError) as caught:
            validate_registry(value, self.schema)
        self.assertIn(contains, str(caught.exception))

    def magnitude_records(self) -> list[dict]:
        values = dict(zip(PROVENANCE_CLASSES, (30.0, 10.0, 8.0, 5.0)))
        return [limit_record(name, "magnitude", values[name]) for name in PROVENANCE_CLASSES]

    def test_tracked_registry_is_empty_config_bound_and_motion_denied(self) -> None:
        tracked = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        validate_registry(tracked, self.schema)
        self.assertEqual(configuration(), tracked["configuration"])
        self.assertEqual([], tracked["records"])
        loaded = LimitRegistry.load(REGISTRY_PATH, SCHEMA_PATH)
        self.assertEqual(0, loaded.accepted_measured_record_count)
        self.assertFalse(loaded.motion_enable_allowed)

    def test_four_classes_intersect_to_most_restrictive_magnitude(self) -> None:
        rows = self.magnitude_records()
        selected = LimitRegistry(registry(rows), self.schema).select(
            [row["record_id"] for row in rows], query()
        )
        self.assertTrue(selected.allowed)
        self.assertEqual(LimitSelectionCode.SELECTED, selected.code)
        self.assertEqual(5.0, selected.effective.magnitude)
        self.assertEqual(-5.0, selected.effective.lower)
        self.assertEqual(5.0, selected.effective.upper)
        self.assertEqual("A", selected.effective.si_unit)

    def test_lower_is_maximum_and_upper_is_minimum(self) -> None:
        lower_values = dict(zip(PROVENANCE_CLASSES, (-3.0, -2.5, -2.0, -1.5)))
        upper_values = dict(zip(PROVENANCE_CLASSES, (3.0, 2.5, 2.0, 1.5)))
        rows = []
        for name in PROVENANCE_CLASSES:
            rows.append(limit_record(name, "lower", lower_values[name], quantity="position", coordinate="joint", unit="rad"))
            rows.append(limit_record(name, "upper", upper_values[name], quantity="position", coordinate="joint", unit="rad"))
        selected = LimitRegistry(registry(rows), self.schema).select(
            [row["record_id"] for row in rows],
            query(quantity="position", coordinate="joint", mode="POSITION", directions=("lower", "upper")),
        )
        self.assertTrue(selected.allowed)
        self.assertEqual(-1.5, selected.effective.lower)
        self.assertEqual(1.5, selected.effective.upper)

    def test_missing_class_and_direction_are_distinct_denials(self) -> None:
        rows = self.magnitude_records()[:-1]
        result = LimitRegistry(registry(rows), self.schema).select(
            [row["record_id"] for row in rows], query()
        )
        self.assertEqual(LimitSelectionCode.MISSING_PROVENANCE_CLASS, result.code)
        self.assertEqual("runtime_derate", result.missing_provenance_class)

        rows = self.magnitude_records()
        result = LimitRegistry(registry(rows), self.schema).select(
            [row["record_id"] for row in rows], query(directions=("lower", "upper"))
        )
        self.assertEqual(LimitSelectionCode.MISSING_DIRECTION, result.code)
        self.assertEqual("lower", result.missing_direction)

    def test_explicit_ids_state_subject_and_scope_do_not_fallback(self) -> None:
        rows = self.magnitude_records()
        loaded = LimitRegistry(registry(rows), self.schema)
        ids = [row["record_id"] for row in rows]
        self.assertEqual(LimitSelectionCode.RECORD_NOT_FOUND, loaded.select([*ids[:-1], "runtime-derate"], query()).code)

        rows[0]["state"] = "draft"
        reseal_value = registry(rows)
        reseal(reseal_value)
        loaded = LimitRegistry(reseal_value, self.schema)
        self.assertEqual(LimitSelectionCode.RECORD_NOT_ACCEPTED, loaded.select(ids, query()).code)

        rows = self.magnitude_records()
        loaded = LimitRegistry(registry(rows), self.schema)
        changed_subject = copy.deepcopy(query())
        object.__setattr__(changed_subject, "subject", LimitSubject(**{**subject().__dict__, "native_node_id": 11}))
        self.assertEqual(LimitSelectionCode.SUBJECT_MISMATCH, loaded.select(ids, changed_subject).code)
        self.assertEqual(LimitSelectionCode.SCOPE_MISMATCH, loaded.select(ids, query(mode="POSITION")).code)

    def test_operating_point_missing_and_outside_fail(self) -> None:
        rows = self.magnitude_records()
        loaded = LimitRegistry(registry(rows), self.schema)
        ids = [row["record_id"] for row in rows]
        self.assertEqual(LimitSelectionCode.OPERATING_POINT_MISSING, loaded.select(ids, query(voltage=None)).code)
        self.assertEqual(LimitSelectionCode.OPERATING_ENVELOPE_MISMATCH, loaded.select(ids, query(temperature=81.0)).code)
        self.assertEqual(LimitSelectionCode.OPERATING_ENVELOPE_MISMATCH, loaded.select(ids, query(speed=5.1)).code)

    def test_runtime_generation_and_validity_are_exact_and_inclusive(self) -> None:
        rows = self.magnitude_records()
        loaded = LimitRegistry(registry(rows), self.schema)
        ids = [row["record_id"] for row in rows]
        self.assertEqual(LimitSelectionCode.RUNTIME_GENERATION_MISMATCH, loaded.select(ids, query(generation=8)).code)
        self.assertTrue(loaded.select(ids, query(now_ns=100)).allowed)
        self.assertTrue(loaded.select(ids, query(now_ns=200)).allowed)
        self.assertEqual(LimitSelectionCode.RUNTIME_SNAPSHOT_STALE, loaded.select(ids, query(now_ns=201)).code)
        self.assertEqual(
            LimitSelectionCode.NOT_YET_VALID,
            loaded.select(ids, query(at=datetime(2026, 1, 1, tzinfo=timezone.utc))).code,
        )
        self.assertEqual(
            LimitSelectionCode.EXPIRED,
            loaded.select(ids, query(at=datetime(2028, 1, 2, 0, 0, 1, tzinfo=timezone.utc))).code,
        )

    def test_contradictory_interval_is_denied(self) -> None:
        rows = []
        for name in PROVENANCE_CLASSES:
            rows.append(limit_record(name, "lower", 2.0, quantity="position", coordinate="joint", unit="rad"))
            rows.append(limit_record(name, "upper", 1.0, quantity="position", coordinate="joint", unit="rad"))
        result = LimitRegistry(registry(rows), self.schema).select(
            [row["record_id"] for row in rows],
            query(quantity="position", coordinate="joint", mode="POSITION", directions=("lower", "upper")),
        )
        self.assertEqual(LimitSelectionCode.CONTRADICTORY_BOUNDS, result.code)

    def test_semantic_units_coordinates_authority_envelope_and_snapshot_fail(self) -> None:
        mutations = [
            (lambda row: row.__setitem__("si_unit", "V"), "unit does not match"),
            (lambda row: row.__setitem__("coordinate", "joint"), "coordinate does not match"),
            (lambda row: row["evidence"].__setitem__("authority", "vendor_manual"), "authority/reviewer"),
            (lambda row: row["operating_envelope"].__setitem__("temperature_min_c", 90.0), "reversed"),
            (lambda row: row["runtime_snapshot"].__setitem__("valid_until_ns", 100), "snapshot interval"),
            (lambda row: row["subject"]["exact_tuple"].__setitem__("model", "UNKNOWN"), "unknown or wildcard"),
        ]
        for mutation, expected in mutations:
            with self.subTest(expected=expected):
                row = limit_record("runtime_derate", "magnitude", 5.0)
                mutation(row)
                value = registry([row])
                reseal(value)
                self.assert_invalid(value, expected)

        row = limit_record("vendor_rating", "magnitude", -1.0)
        value = registry([row])
        reseal(value)
        self.assert_invalid(value, "magnitude must be nonnegative")

    def test_integrity_nonfinite_config_count_and_duplicate_fail(self) -> None:
        value = registry(self.magnitude_records())
        value["records"][0]["bound_value"] = 99.0
        self.assert_invalid(value, "digest mismatch")

        value = registry(self.magnitude_records())
        value["records"][0]["bound_value"] = math.inf
        self.assert_invalid(value, "non-finite")

        value = registry(self.magnitude_records())
        value["records"][0]["subject"]["configuration"]["configuration_revision"] = 2
        reseal(value)
        self.assert_invalid(value, "configuration does not equal")

        value = registry(self.magnitude_records())
        value["physical_admission"]["accepted_measured_record_count"] = 0
        value["integrity"]["digest"] = registry_digest(value)
        self.assert_invalid(value, "count does not match")

        row = limit_record("vendor_rating", "magnitude", 30.0)
        value = registry([row, copy.deepcopy(row)])
        self.assert_invalid(value, "duplicate record_id")

    def test_cli_is_read_only_and_rejects_motion_promotion(self) -> None:
        before = REGISTRY_PATH.read_bytes()
        result = subprocess.run([sys.executable, str(CLI)], cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("records=0 accepted_measured=0 motion=false", result.stdout)
        self.assertEqual(before, REGISTRY_PATH.read_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            bad = json.loads(before)
            bad["physical_admission"]["motion_enable_allowed"] = True
            path = Path(temporary) / "bad.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            denied = subprocess.run([sys.executable, str(CLI), str(path)], cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertNotEqual(0, denied.returncode)


if __name__ == "__main__":
    unittest.main()
