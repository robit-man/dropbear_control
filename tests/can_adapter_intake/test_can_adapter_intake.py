from __future__ import annotations

import copy
import importlib.util
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from myactuator_lib.can_adapter_intake import (
    AdapterAdmissionError,
    AdapterPurpose,
    CanAdapterIntakeRegistry,
    ControllerKind,
    PhysicalAdapterFactoryDisabled,
)


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/manage_can_adapter_intake.py"
STATUS = ROOT / "generated/can_adapter_intake/status.json"

spec = importlib.util.spec_from_file_location(
    "can_adapter_intake_test_module", TOOL
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class CanAdapterIntakeTests(unittest.TestCase):
    def manifest(
        self,
        controller_kind="esp32_twai",
        purpose="listen_only_capture",
        marker="one",
    ):
        twai = controller_kind == "esp32_twai"
        clock = 80_000_000 if twai else 16_000_000
        divider = 4 if twai else 1
        segment_1 = 15 if twai else 13
        segment_2 = 4 if twai else 2
        total = 1 + segment_1 + segment_2
        sample = 100.0 * (1 + segment_1) / total
        listen_only = purpose == "listen_only_capture"
        pins = (
            {
                "can_tx_gpio": 21,
                "can_rx_gpio": 22,
                "spi_sck_gpio": None,
                "spi_mosi_gpio": None,
                "spi_miso_gpio": None,
                "spi_chip_select_gpio": None,
                "interrupt_gpio": None,
                "transceiver_standby_gpio": 23,
            }
            if twai
            else {
                "can_tx_gpio": None,
                "can_rx_gpio": None,
                "spi_sck_gpio": 18,
                "spi_mosi_gpio": 23,
                "spi_miso_gpio": 19,
                "spi_chip_select_gpio": 5,
                "interrupt_gpio": 4,
                "transceiver_standby_gpio": 27,
            }
        )
        value = {
            "schema_version": "can-adapter-manifest/1",
            "manifest_id": "canadapter-" + "0" * 20,
            "record_state": "reviewed",
            "purpose": purpose,
            "subject": {
                "canonical_configuration_digest": manager.configuration_digest(),
                "installed_inventory_submission_id": (
                    "inventorysubmission-" + "a1" * 10
                ),
                "robot_asset_id": "dropbear-synthetic-fixture",
                "controller_location": f"synthetic-{marker}-controller",
            },
            "hardware": {
                "controller_kind": controller_kind,
                "controller_part_number": (
                    "ESP32-TWAI-INTEGRATED" if twai else "MCP2515"
                ),
                "controller_silicon_revision": f"synthetic-rev-{marker}",
                "connection_kind": "integrated_peripheral" if twai else "spi",
                "board_model": f"synthetic-board-{marker}",
                "board_revision": "fixture-rev-a",
                "transceiver_part_number": "SN65HVD230",
                "transceiver_revision": "fixture-rev-a",
                "controller_clock_hz": clock,
                "clock_source": "synthetic-reviewed-clock",
                "logic_voltage_v": 3.3,
                "bus_voltage_v": 5.0,
                "termination_ohm": 120.0,
                "pins": pins,
            },
            "firmware": {
                "build_system": "platformio",
                "environment": "esp32",
                "framework": "arduino",
                "driver_id": "esp-idf-twai" if twai else "autowp-mcp2515",
                "driver_version": f"synthetic-{marker}",
                "driver_source_sha256": "11" * 32,
                "binary_sha256": "22" * 32,
                "configuration_sha256": "33" * 32,
                "compile_flag_evidence_refs": [
                    f"tests/can_adapter_intake/compile-{marker}"
                ],
            },
            "timing": {
                "target_bitrate_hz": 1_000_000,
                "controller_clock_hz": clock,
                "clock_divider": divider,
                "sync_segment_tq": 1,
                "time_segment_1_tq": segment_1,
                "time_segment_2_tq": segment_2,
                "sjw_tq": min(2, segment_2),
                "total_time_quanta": total,
                "calculated_bitrate_hz": 1_000_000.0,
                "sample_point_percent": sample,
                "bitrate_error_ppm": 0.0,
                "triple_sampling": False,
                "calculation_evidence_refs": [
                    f"tests/can_adapter_intake/timing-{marker}"
                ],
            },
            "tx_disable": {
                "controller_operating_mode": (
                    "listen_only" if listen_only else "normal"
                ),
                "controller_enforced_listen_only": listen_only,
                "independent_disable_mechanism": "transceiver_standby",
                "independent_disable_default_state": "tx_disabled",
                "independent_disable_control_gpio": pins[
                    "transceiver_standby_gpio"
                ],
                "independent_disable_observed": True,
                "measurement_method": "synthetic no-I/O semantic fixture",
                "measurement_evidence_refs": [
                    f"tests/can_adapter_intake/tx-disable-{marker}"
                ],
            },
            "queues_and_time": {
                "rx_queue_depth": 64,
                "tx_queue_depth": 0 if listen_only else 32,
                "overflow_policy": "reject_new_and_count",
                "rx_loss_counter_bits": 64,
                "tx_loss_counter_bits": 64,
                "timestamp_clock": "synthetic-monotonic-clock",
                "timestamp_resolution_ns": 1000,
                "timestamp_counter_bits": 64,
                "timestamp_wrap_policy": "u64_no_expected_wrap",
                "monotonic_timestamp_confirmed": True,
                "evidence_refs": [
                    f"tests/can_adapter_intake/queues-{marker}"
                ],
            },
            "error_state_policy": {
                "warning_threshold": 96,
                "passive_threshold": 128,
                "bus_off_threshold": 256,
                "warning_action": "report",
                "passive_action": "fault_and_tx_disable",
                "bus_off_action": "latch_fault_cancel_pending",
                "recovery_mode": "manual_reviewed_reinitialize",
                "recovery_requires_fresh_session": True,
                "max_recovery_attempts": 1,
                "evidence_refs": [
                    f"tests/can_adapter_intake/errors-{marker}"
                ],
            },
            "review": {
                "reviewer_id": f"independent-hardware-reviewer-{marker}",
                "organization_or_team": "external-hardware-review-team",
                "hardware_competence_attested": True,
                "independence_attested": True,
                "reviewed_at": "2026-07-23T18:00:00Z",
                "review_assertion": (
                    "Synthetic no-I/O manifest semantics fixture."
                ),
                "signature_evidence_refs": [
                    f"tests/can_adapter_intake/reviewer-{marker}"
                ],
            },
            "evidence_refs": [
                f"tests/can_adapter_intake/manifest-{marker}"
            ],
            "support_granted": False,
            "physical_motion_authority": False,
            "physical_io_enabled": False,
            "integrity": {"record_sha256": "0" * 64},
        }
        value["manifest_id"] = manager.expected_manifest_id(value)
        manager.set_digest(value)
        manager.validate_manifest(value)
        return value

    def write_case(self, root, manifests):
        root.mkdir(exist_ok=True)
        for manifest in manifests:
            (root / f"{manifest['manifest_id']}.json").write_bytes(
                manager.canonical_bytes(manifest)
            )

    def build_case(self, manifests):
        with tempfile.TemporaryDirectory() as temporary:
            submissions = Path(temporary) / "submissions"
            self.write_case(submissions, manifests)
            return manager.build(submissions)

    def consumer(self, status, manifests):
        by_id = {manifest["manifest_id"]: manifest for manifest in manifests}
        return CanAdapterIntakeRegistry(
            status,
            json.loads(manager.STATUS_SCHEMA.read_text()),
            json.loads(manager.MANIFEST_SCHEMA.read_text()),
            {
                entry["path"]: manager.canonical_bytes(by_id[entry["manifest_id"]])
                for entry in status["manifests"]
            },
            manager.MANIFEST_SCHEMA.read_bytes(),
        )

    def test_tracked_status_is_zero_neutral_and_physical_factory_disabled(self):
        value = manager.build()
        self.assertEqual(value, json.loads(STATUS.read_text()))
        self.assertEqual([], value["manifests"])
        self.assertEqual(0, value["summary"]["reviewed_manifest_count"])
        self.assertIsNone(value["selected_listen_only_manifest_id"])
        self.assertIsNone(value["selected_runtime_manifest_id"])
        self.assertFalse(value["physical_factory_enabled"])
        registry = CanAdapterIntakeRegistry.load()
        self.assertEqual(0, registry.reviewed_manifest_count)
        with self.assertRaises(AdapterAdmissionError):
            registry.describe_no_io(
                "canadapter-" + "0" * 20,
                AdapterPurpose.LISTEN_ONLY_CAPTURE,
            )

    def test_twai_and_mcp2515_purposes_validate_without_selection_or_io(self):
        manifests = [
            self.manifest("esp32_twai", "listen_only_capture", "twai-listen"),
            self.manifest("esp32_twai", "runtime_gateway", "twai-runtime"),
            self.manifest("mcp2515", "listen_only_capture", "mcp-listen"),
            self.manifest("mcp2515", "runtime_gateway", "mcp-runtime"),
        ]
        status = self.build_case(manifests)
        self.assertEqual(4, status["summary"]["reviewed_manifest_count"])
        self.assertEqual(2, status["summary"]["twai_manifest_count"])
        self.assertEqual(2, status["summary"]["mcp2515_manifest_count"])
        self.assertEqual(0, status["summary"]["selected_runtime_count"])
        registry = self.consumer(status, manifests)
        for manifest in manifests:
            purpose = AdapterPurpose(manifest["purpose"])
            descriptor = registry.describe_no_io(
                manifest["manifest_id"], purpose
            )
            self.assertEqual(
                ControllerKind(manifest["hardware"]["controller_kind"]),
                descriptor.controller_kind,
            )
            self.assertEqual(1_000_000, descriptor.target_bitrate_hz)
            self.assertFalse(descriptor.physical_io)
            self.assertFalse(descriptor.support_granted)
            self.assertFalse(descriptor.physical_motion_authority)
            with self.assertRaises(PhysicalAdapterFactoryDisabled):
                registry.create_physical(manifest["manifest_id"], purpose)

    def test_listen_only_and_runtime_purposes_cannot_substitute(self):
        listen = self.manifest(
            "esp32_twai", "listen_only_capture", "purpose"
        )
        status = self.build_case([listen])
        registry = self.consumer(status, [listen])
        with self.assertRaises(AdapterAdmissionError):
            registry.describe_no_io(
                listen["manifest_id"], AdapterPurpose.RUNTIME_GATEWAY
            )
        changed = copy.deepcopy(listen)
        changed["purpose"] = "runtime_gateway"
        changed["manifest_id"] = manager.expected_manifest_id(changed)
        manager.set_digest(changed)
        with self.assertRaises(manager.AdapterIntakeError):
            manager.validate_manifest(changed)

    def test_controller_connection_driver_pin_and_disable_tuple_deny(self):
        mutations = [
            lambda value: value["hardware"].update(connection_kind="spi"),
            lambda value: value["firmware"].update(driver_id="autowp-mcp2515"),
            lambda value: value["hardware"]["pins"].update(can_rx_gpio=None),
            lambda value: value["hardware"]["pins"].update(can_rx_gpio=21),
            lambda value: value["tx_disable"].update(
                independent_disable_control_gpio=24
            ),
            lambda value: value["tx_disable"].update(
                controller_enforced_listen_only=False
            ),
        ]
        for mutation in mutations:
            value = self.manifest(marker="tuple")
            mutation(value)
            value["manifest_id"] = manager.expected_manifest_id(value)
            manager.set_digest(value)
            with self.assertRaises(manager.AdapterIntakeError):
                manager.validate_manifest(value)

    def test_timing_formula_sample_sjw_and_clock_deny(self):
        mutations = [
            lambda value: value["timing"].update(total_time_quanta=19),
            lambda value: value["timing"].update(
                calculated_bitrate_hz=999_999.0
            ),
            lambda value: value["timing"].update(sample_point_percent=81.0),
            lambda value: value["timing"].update(bitrate_error_ppm=1.0),
            lambda value: value["timing"].update(sjw_tq=5),
            lambda value: value["timing"].update(controller_clock_hz=40_000_000),
        ]
        for mutation in mutations:
            value = self.manifest(marker="timing")
            mutation(value)
            value["manifest_id"] = manager.expected_manifest_id(value)
            manager.set_digest(value)
            with self.assertRaises(manager.AdapterIntakeError):
                manager.validate_manifest(value)

    def test_queue_timestamp_loss_error_review_identity_and_integrity_deny(self):
        mutations = [
            lambda value: value["queues_and_time"].update(tx_queue_depth=1),
            lambda value: value["error_state_policy"].update(
                warning_threshold=129
            ),
            lambda value: value["review"].update(
                reviewer_id="codex-automated-reviewer"
            ),
            lambda value: value["subject"].update(
                canonical_configuration_digest="0" * 64
            ),
            lambda value: value.update(manifest_id="canadapter-" + "0" * 20),
            lambda value: value["integrity"].update(record_sha256="0" * 64),
        ]
        for mutation in mutations:
            value = self.manifest(marker="integrity")
            mutation(value)
            if value["manifest_id"] != "canadapter-" + "0" * 20:
                value["manifest_id"] = manager.expected_manifest_id(value)
            if value["integrity"]["record_sha256"] != "0" * 64:
                manager.set_digest(value)
            with self.assertRaises(manager.AdapterIntakeError):
                manager.validate_manifest(value)

    def test_status_tamper_foreign_file_and_cli_check_deny(self):
        manifest = self.manifest(marker="status")
        with tempfile.TemporaryDirectory() as temporary:
            submissions = Path(temporary) / "submissions"
            self.write_case(submissions, [manifest])
            (submissions / "notes.txt").write_text("foreign")
            with self.assertRaises(manager.AdapterIntakeError):
                manager.build(submissions)
        status = self.build_case([manifest])
        changed = copy.deepcopy(status)
        changed["summary"]["selected_runtime_count"] = 1
        self.assertTrue(
            list(
                Draft202012Validator(
                    json.loads(manager.STATUS_SCHEMA.read_text())
                ).iter_errors(changed)
            )
        )
        changed = copy.deepcopy(status)
        changed["manifests"][0]["selected"] = True
        changed["integrity"]["record_sha256"] = manager.status_digest(changed)
        with self.assertRaises(manager.AdapterIntakeError):
            manager.validate_status(changed)

        result = subprocess.run(
            [sys.executable, str(TOOL), "--check"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("twai=0 mcp2515=0", result.stdout)
        self.assertIn("physical_factory=false", result.stdout)

    def test_host_consumer_independently_rechecks_manifest_semantics(self):
        manifest = self.manifest(marker="host-semantic")
        status = self.build_case([manifest])
        changed_manifest = copy.deepcopy(manifest)
        changed_manifest["timing"]["sample_point_percent"] = 81.0
        changed_manifest["manifest_id"] = manager.expected_manifest_id(
            changed_manifest
        )
        manager.set_digest(changed_manifest)
        changed_status = copy.deepcopy(status)
        changed_status["manifests"][0].update(
            manifest_id=changed_manifest["manifest_id"],
            sha256=manager.sha_bytes(
                manager.canonical_bytes(changed_manifest)
            ),
        )
        changed_status["integrity"]["record_sha256"] = manager.status_digest(
            changed_status
        )
        with self.assertRaises(AdapterAdmissionError):
            self.consumer(changed_status, [changed_manifest])


if __name__ == "__main__":
    unittest.main()
