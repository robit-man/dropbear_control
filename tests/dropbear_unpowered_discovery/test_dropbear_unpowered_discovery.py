from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/prepare_dropbear_unpowered_discovery.py"
TEMPLATE_PATH = ROOT / "assets/dropbear/installed_inventory_template.json"
STATUS_PATH = ROOT / "generated/dropbear_unpowered_discovery/status.json"
INVENTORY_SCHEMA = json.loads(
    (ROOT / "schemas/dropbear-installed-inventory.schema.json").read_text()
)
STATUS_SCHEMA = json.loads(
    (
        ROOT
        / "schemas/dropbear-unpowered-discovery-status.schema.json"
    ).read_text()
)

spec = importlib.util.spec_from_file_location(
    "dropbear_unpowered_discovery_test_module", TOOL
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class DropbearUnpoweredDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = manager.template()
        cls.status = json.loads(STATUS_PATH.read_text())

    def submitted_fixture(self, *, complete: bool = False):
        record = copy.deepcopy(self.template)
        record["record_state"] = "submitted"
        record["subject"].update(
            robot_revision="synthetic-revision",
            physical_asset_tag="synthetic-asset",
            captured_at="2026-07-23T10:00:00Z",
        )
        record["authorization"] = {
            "granted": True,
            "authorization_id": "synthetic-unpowered-authorization",
            "allowed_actions": [
                "visual_label_inspection",
                "label_photography",
                "documentation_transcription",
            ],
            "valid_from": "2026-07-23T09:00:00Z",
            "valid_until": "2026-07-23T11:00:00Z",
            "evidence_refs": ["synthetic-evidence"],
        }
        record["personnel"] = {
            "operator_id": "synthetic-operator",
            "hardware_owner_id": "synthetic-owner",
            "safety_reviewer_id": "synthetic-safety-reviewer",
        }
        record["evidence"] = [
            {
                "evidence_id": "synthetic-evidence",
                "capture_method": "manual_transcription",
                "captured_at": "2026-07-23T10:00:00Z",
                "operator_id": "synthetic-operator",
                "relative_path": (
                    "assets/dropbear/installed_inventory_evidence/"
                    "synthetic-evidence.txt"
                ),
                "sha256": "ab" * 32,
            }
        ]
        record["controller_path"].update(
            observation_status="observed_partial",
            board_model="synthetic-board-observation",
            evidence_refs=["synthetic-evidence"],
        )
        record["motors"][0].update(
            observation_status="observed_partial",
            model="synthetic-model-observation",
            evidence_refs=["synthetic-evidence"],
        )
        if complete:
            record["controller_path"] = {
                "observation_status": "observed_complete",
                "board_manufacturer": "synthetic-board-vendor",
                "board_model": "synthetic-board",
                "board_revision": "synthetic-revision",
                "board_serial": "synthetic-board-serial",
                "controller_kind": "esp32_twai",
                "controller_part": "synthetic-controller",
                "controller_oscillator_hz": 80_000_000,
                "transceiver_part": "synthetic-transceiver",
                "transceiver_isolation": "isolated",
                "transceiver_silent_or_standby_control": "synthetic-silent",
                "physically_enforced_tx_disable": "synthetic-disable",
                "termination_ohm": 120.0,
                "connector_id": "synthetic-connector",
                "ground_reference": "synthetic-isolated-reference",
                "pin_observations": [
                    {
                        "signal": "synthetic-can-rx",
                        "pin": "synthetic-pin",
                        "evidence_refs": ["synthetic-evidence"],
                    }
                ],
                "evidence_refs": ["synthetic-evidence"],
            }
            for index, motor in enumerate(record["motors"], start=1):
                motor.update(
                    observation_status="observed_complete",
                    manufacturer="synthetic-manufacturer",
                    series="synthetic-series",
                    model="synthetic-model",
                    hardware_revision="synthetic-hardware",
                    drive_firmware="synthetic-firmware",
                    serial_number=f"synthetic-serial-{index:02d}",
                    protocol_name="synthetic-protocol",
                    protocol_revision="synthetic-protocol-revision",
                    native_node_id=index,
                    brake_observation="synthetic-brake-observation",
                    bus_connector_observation="synthetic-bus-connector",
                    evidence_refs=["synthetic-evidence"],
                )
            record["record_complete"] = True
        manager.set_digest(record)
        return record

    def denied(self, record, mutation):
        mutation(record)
        manager.set_digest(record)
        with self.assertRaises(manager.DiscoveryPreparationError):
            manager.validate_inventory(record, verify_evidence_files=False)

    def test_template_is_exact_unobserved_unauthorized_and_digest_bound(self):
        manager.validate_inventory(copy.deepcopy(self.template))
        self.assertEqual(self.template, json.loads(TEMPLATE_PATH.read_text()))
        self.assertEqual(12, len(self.template["motors"]))
        self.assertTrue(
            all(
                row["observation_status"] == "unobserved"
                and row["manufacturer"] is None
                and row["native_node_id"] is None
                and not row["evidence_refs"]
                for row in self.template["motors"]
            )
        )
        self.assertFalse(self.template["authorization"]["granted"])
        self.assertEqual([], self.template["authorization"]["allowed_actions"])
        self.assertEqual("unknown", self.template["controller_path"]["controller_kind"])
        self.assertFalse(self.template["record_complete"])
        self.assertFalse(self.template["support_granted"])
        self.assertFalse(self.template["physical_motion_authority"])

    def test_exact_twelve_actuator_slots_follow_reconciliation_without_aliases(self):
        reconciliation = manager.reconciliation()
        expected = [row["actuator_id"] for row in reconciliation["actuators"]]
        actual = [
            row["canonical_actuator_id"] for row in self.template["motors"]
        ]
        self.assertEqual(expected, actual)
        for mutation in (
            lambda value: value["motors"].pop(),
            lambda value: value["motors"].reverse(),
            lambda value: value["motors"][0].__setitem__(
                "canonical_actuator_id", "actuator-left-knee"
            ),
        ):
            record = self.submitted_fixture()
            self.denied(record, mutation)

    def test_partial_synthetic_unpowered_submission_validates_but_is_not_evidence(self):
        record = self.submitted_fixture()
        manager.validate_inventory(record, verify_evidence_files=False)
        self.assertFalse(record["record_complete"])
        self.assertFalse(record["support_granted"])
        self.assertFalse(record["physical_motion_authority"])
        self.assertEqual(0, self.status["summary"]["submitted_inventory_count"])

    def test_complete_synthetic_inventory_validates_without_selecting_controller(self):
        record = self.submitted_fixture(complete=True)
        manager.validate_inventory(record, verify_evidence_files=False)
        self.assertTrue(record["record_complete"])
        self.assertEqual(0, self.status["summary"]["selected_can_controller_count"])
        self.assertFalse(self.status["summary"]["ready_for_execution"])

    def test_duplicate_node_and_serial_require_explicit_conflict_records(self):
        node = self.submitted_fixture(complete=True)
        node["motors"][1]["native_node_id"] = node["motors"][0]["native_node_id"]
        node["record_complete"] = True
        manager.set_digest(node)
        with self.assertRaises(manager.DiscoveryPreparationError):
            manager.validate_inventory(node, verify_evidence_files=False)
        node["conflicts"].append(
            {
                "conflict_id": "synthetic-node-conflict",
                "kind": "duplicate_native_node",
                "subject_ids": [
                    node["motors"][0]["canonical_actuator_id"],
                    node["motors"][1]["canonical_actuator_id"],
                ],
                "disposition": "repair_before_later_capture",
                "rationale": "Synthetic conflict fixture.",
                "evidence_refs": ["synthetic-evidence"],
            }
        )
        manager.set_digest(node)
        manager.validate_inventory(node, verify_evidence_files=False)

        serial = self.submitted_fixture(complete=True)
        serial["motors"][1]["serial_number"] = serial["motors"][0]["serial_number"]
        manager.set_digest(serial)
        with self.assertRaises(manager.DiscoveryPreparationError):
            manager.validate_inventory(serial, verify_evidence_files=False)

    def test_authorization_personnel_time_and_scope_fail_closed(self):
        base = self.submitted_fixture()
        mutations = [
            lambda value: value["authorization"].__setitem__("granted", False),
            lambda value: value["authorization"].__setitem__("allowed_actions", []),
            lambda value: value["authorization"].__setitem__(
                "valid_from", "2026-07-23T09:00:00-07:00"
            ),
            lambda value: value["authorization"].__setitem__(
                "valid_until", "2026-07-23T08:00:00Z"
            ),
            lambda value: value["subject"].__setitem__(
                "captured_at", "2026-07-23T12:00:00Z"
            ),
            lambda value: value["personnel"].__setitem__(
                "safety_reviewer_id", value["personnel"]["operator_id"]
            ),
            lambda value: value.__setitem__("scope", "powered_capture"),
        ]
        for mutation in mutations:
            self.denied(copy.deepcopy(base), mutation)

    def test_unknown_evidence_missing_file_and_digest_drift_deny(self):
        base = self.submitted_fixture()
        self.denied(
            copy.deepcopy(base),
            lambda value: value["motors"][0]["evidence_refs"].append(
                "unknown-evidence"
            ),
        )
        with self.assertRaises(manager.DiscoveryPreparationError):
            manager.validate_inventory(base, verify_evidence_files=True)
        digest = copy.deepcopy(base)
        digest["integrity"]["record_sha256"] = "0" * 64
        with self.assertRaises(manager.DiscoveryPreparationError):
            manager.validate_inventory(digest, verify_evidence_files=False)

    def test_schema_has_no_power_command_frame_or_device_read_capture_method(self):
        validator = Draft202012Validator(INVENTORY_SCHEMA)
        for field in (
            "can_frames",
            "commands",
            "powered",
            "motion_enabled",
            "firmware_write",
        ):
            value = self.submitted_fixture()
            value[field] = []
            self.assertTrue(list(validator.iter_errors(value)), field)
        value = self.submitted_fixture()
        value["evidence"][0]["capture_method"] = "read_from_device"
        manager.set_digest(value)
        self.assertTrue(list(validator.iter_errors(value)))

    def test_schema_rejects_support_motion_or_execution_promotions(self):
        inventory_validator = Draft202012Validator(INVENTORY_SCHEMA)
        for field in ("support_granted", "physical_motion_authority"):
            value = self.submitted_fixture()
            value[field] = True
            manager.set_digest(value)
            self.assertTrue(list(inventory_validator.iter_errors(value)))
        status_validator = Draft202012Validator(STATUS_SCHEMA)
        mutations = [
            lambda value: value["summary"].__setitem__(
                "submitted_inventory_count", 1
            ),
            lambda value: value["summary"].__setitem__(
                "selected_can_controller_count", 1
            ),
            lambda value: value["summary"].__setitem__(
                "authorized_action_count", 1
            ),
            lambda value: value["summary"].__setitem__(
                "ready_for_execution", True
            ),
            lambda value: value.__setitem__("support_granted", True),
            lambda value: value.__setitem__(
                "physical_motion_authority", True
            ),
        ]
        for mutation in mutations:
            value = copy.deepcopy(self.status)
            mutation(value)
            self.assertTrue(list(status_validator.iter_errors(value)))

    def test_status_hashes_all_thirteen_review_sources_and_preserves_zero_authority(self):
        self.assertEqual(13, len(self.status["sources"]))
        for source in self.status["sources"]:
            path = ROOT / source["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                source["sha256"],
            )
        summary = self.status["summary"]
        self.assertEqual(12, summary["planned_workstream_count"])
        self.assertEqual(12, summary["installed_actuator_slot_count"])
        self.assertTrue(summary["ready_for_human_review"])
        self.assertFalse(summary["ready_for_execution"])
        self.assertEqual(0, summary["authorized_action_count"])

    def test_runbooks_name_roles_preconditions_aborts_evidence_and_no_authority(self):
        texts = {
            path.name: path.read_text()
            for path in manager.PACKAGE_DOCS
        }
        combined = "\n".join(texts.values()).casefold()
        for term in (
            "owner",
            "reviewer",
            "precondition",
            "abort",
            "evidence",
            "no-controller-selected",
            "tx disable",
            "power-removal",
            "calibration",
            "limit",
            "hil",
            "cad",
            "plant",
            "unauthorized",
        ):
            self.assertIn(term, combined, term)

    def test_v1_status_refuses_any_inventory_submission(self):
        original = manager.SUBMISSIONS
        try:
            with tempfile.TemporaryDirectory() as temporary:
                manager.SUBMISSIONS = Path(temporary)
                (manager.SUBMISSIONS / "submission.json").write_text("{}")
                with self.assertRaises(manager.DiscoveryPreparationError):
                    manager.package_status(self.template)
        finally:
            manager.SUBMISSIONS = original

    def test_cli_check_is_read_only_and_canonical(self):
        before_template = TEMPLATE_PATH.read_bytes()
        before_status = STATUS_PATH.read_bytes()
        result = subprocess.run(
            ["python3", str(TOOL), "--check"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertIn("workstreams=12 slots=12 submitted=0", result.stdout)
        self.assertIn("execution=false support=false motion=false", result.stdout)
        self.assertEqual(before_template, TEMPLATE_PATH.read_bytes())
        self.assertEqual(before_status, STATUS_PATH.read_bytes())
        self.assertEqual(
            before_status,
            manager.canonical_bytes(json.loads(before_status)),
        )


if __name__ == "__main__":
    unittest.main()
