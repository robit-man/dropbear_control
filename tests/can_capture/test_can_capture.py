from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "host"))

from myactuator_lib.can_capture import (
    CaptureValidationError,
    validate_jsonl,
    validate_records,
)


def record(sequence: int = 1, timestamp_ns: int = 1000) -> dict:
    return {
        "schema_version": "myactuator-can-listen-capture/1",
        "capture_id": "synthetic-listen-capture-1",
        "sequence": sequence,
        "timestamp": {
            "monotonic_ns": timestamp_ns,
            "clock_id": "synthetic-monotonic-1",
            "clock_source": "synthetic_fake",
            "resolution_ns": 1000,
            "capture_started_utc": "2026-07-22T20:00:00Z",
        },
        "controller": {
            "bus_id": 1,
            "instance_id": "fake-controller-1",
            "controller_type": "synthetic-fake",
            "mode": "listen_only",
            "state": "active",
            "bitrate": 1_000_000,
            "oscillator_hz": 40_000_000,
            "transceiver_id": "synthetic-no-hardware",
        },
        "frame": {
            "direction": "rx",
            "arbitration_id": 0x141,
            "is_extended": False,
            "is_remote": False,
            "dlc": 8,
            "data_hex": "a100000019000000",
        },
        "counters": {
            "rx_frames_total": sequence,
            "rx_dropped_total": 0,
            "driver_overflow_total": 0,
        },
        "provenance": {
            "firmware_revision": "synthetic-test-revision-1",
            "firmware_binary_sha256": "11" * 32,
            "adapter_config_sha256": "22" * 32,
            "hardware_setup_id": "synthetic-no-hardware",
            "operator_id": "offline-test-runner",
        },
        "evidence_boundary": {
            "capture_class": "listen_only_observation",
            "frame_interpretation": "uninterpreted_can_frame",
            "protocol_applicability": "unverified",
            "motion_authorized": False,
            "support_granted": False,
        },
    }


class CanCaptureTests(unittest.TestCase):
    def test_valid_lossless_stream_counts_shapes_without_claiming_protocol(self) -> None:
        first = record()
        second = record(2, 2000)
        second["frame"]["arbitration_id"] = 0x241
        summary = validate_records([first, second])
        self.assertEqual(summary.records, 2)
        self.assertEqual(summary.request_shape_candidates, 1)
        self.assertEqual(summary.response_shape_candidates, 1)
        self.assertTrue(summary.lossless)
        self.assertFalse(summary.motion_authorized)
        self.assertFalse(summary.support_granted)
        self.assertEqual(summary.protocol_applicability, "unverified")

    def test_empty_sequence_and_timestamp_fail(self) -> None:
        with self.assertRaisesRegex(CaptureValidationError, "empty"):
            validate_records([])
        second = record(2, 999)
        with self.assertRaisesRegex(CaptureValidationError, "timestamp regression"):
            validate_records([record(), second])
        with self.assertRaisesRegex(CaptureValidationError, "sequence discontinuity"):
            validate_records([record(2)])

    def test_dlc_loss_and_counter_regression_fail(self) -> None:
        invalid = record()
        invalid["frame"]["data_hex"] = "00"
        with self.assertRaisesRegex(CaptureValidationError, "DLC/data"):
            validate_records([invalid])
        lost = record()
        lost["counters"]["rx_dropped_total"] = 1
        with self.assertRaisesRegex(CaptureValidationError, "not lossless"):
            validate_records([lost])
        first = record()
        first["counters"]["rx_dropped_total"] = 2
        second = record(2, 2000)
        second["counters"]["rx_dropped_total"] = 1
        with self.assertRaisesRegex(CaptureValidationError, "counter regressed"):
            validate_records([first, second])

    def test_provenance_or_controller_drift_fails(self) -> None:
        second = record(2, 2000)
        second["provenance"]["operator_id"] = "another-operator"
        with self.assertRaisesRegex(CaptureValidationError, "drift"):
            validate_records([record(), second])
        second = record(2, 2000)
        second["controller"]["oscillator_hz"] = 16_000_000
        with self.assertRaisesRegex(CaptureValidationError, "drift"):
            validate_records([record(), second])

    def test_schema_forbids_tx_extended_remote_and_support_claims(self) -> None:
        mutations = [
            ("direction", "tx"),
            ("is_extended", True),
            ("is_remote", True),
        ]
        for key, value in mutations:
            with self.subTest(key=key):
                invalid = record()
                invalid["frame"][key] = value
                with self.assertRaisesRegex(CaptureValidationError, "schema error"):
                    validate_records([invalid])
        invalid = record()
        invalid["evidence_boundary"]["support_granted"] = True
        with self.assertRaisesRegex(CaptureValidationError, "schema error"):
            validate_records([invalid])
        invalid = record()
        invalid["evidence_boundary"]["protocol_applicability"] = "verified"
        with self.assertRaisesRegex(CaptureValidationError, "schema error"):
            validate_records([invalid])

    def test_jsonl_and_cli(self) -> None:
        records = [record(), record(2, 2000)]
        records[1]["frame"]["arbitration_id"] = 0x241
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.jsonl"
            path.write_text(
                "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
                encoding="utf-8",
            )
            self.assertEqual(validate_jsonl(path).records, 2)
            completed = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "validate_can_capture.py"), str(path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("CAN_CAPTURE_VALID_LISTEN_ONLY_NO_APPLICABILITY", completed.stdout)
            path.write_text("\n", encoding="utf-8")
            with self.assertRaisesRegex(CaptureValidationError, "blank"):
                validate_jsonl(path)

    def test_input_is_not_mutated(self) -> None:
        values = [record(), record(2, 2000)]
        original = copy.deepcopy(values)
        validate_records(values)
        self.assertEqual(values, original)


if __name__ == "__main__":
    unittest.main()
