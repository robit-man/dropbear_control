from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB_ROOT))

from hardware_service import (  # noqa: E402
    CONTROL_COMMAND_SCHEMA,
    ControlGateError,
    HardwareControlGate,
    HardwareObservationManager,
    ObservationParseError,
    SAFETY_ACKNOWLEDGEMENTS,
    parse_esp32_csv_line,
    parse_esp32_telemetry_line,
)


class PassiveObservationTests(unittest.TestCase):
    def test_exact_five_axis_side_mapping(self):
        result = parse_esp32_csv_line("left", "181.5,179,200,220,170")
        self.assertEqual(
            list(result),
            [
                "left_outer_calf",
                "left_inner_calf",
                "left_hip_pitch",
                "left_knee",
                "left_hip_roll",
            ],
        )
        self.assertEqual(result["left_outer_calf"]["canId"], "0x141")
        self.assertEqual(result["left_knee"]["usdJoint"], "LL_knee_actuator_joint")
        self.assertEqual(result["left_hip_roll"]["sensorGpio"], 33)

        result = parse_esp32_csv_line("right", "180,181,182,183,184")
        self.assertEqual(result["right_outer_calf"]["canId"], "0x144")
        self.assertEqual(result["right_hip_pitch"]["canId"], "0x147")
        self.assertEqual(result["right_knee"]["canId"], "0x148")

    def test_malformed_nonfinite_and_out_of_range_lines_deny(self):
        for line in (
            "1,2,3,4",
            "1,2,3,4,5,6",
            "1,2,three,4,5",
            f"1,2,{math.nan},4,5",
            "1,2,361,4,5",
            "1,2,-1,4,5",
        ):
            with self.subTest(line=line), self.assertRaises(ObservationParseError):
                parse_esp32_csv_line("left", line)

    def test_db2_keeps_motor_and_external_angles_separate(self):
        record = parse_esp32_telemetry_line(
            "left",
            "DB2,123456,194,72,10,213,146,10.25,NA,-3.5,44,1.25,88.125",
        )
        self.assertEqual(record["format"], "DB2")
        self.assertEqual(record["controllerMillis"], 123456)
        self.assertEqual(record["joints"]["left_outer_calf"]["positionDeg"], 194)
        self.assertEqual(record["motorJoints"]["left_outer_calf"]["positionDeg"], 10.25)
        self.assertFalse(record["motorJoints"]["left_inner_calf"]["available"])
        self.assertEqual(record["motorJoints"]["left_hip_pitch"]["positionDeg"], -3.5)
        self.assertEqual(record["motorJoints"]["left_hip_yaw"]["canId"], "0x149")

        for line in (
            "DB2,123,1,2,3,4,5,1,2,3,4,5",
            "DB2,-1,1,2,3,4,5,1,2,3,4,5,6",
            "DB2,123,1,2,3,4,5,1,2,BAD,4,5,6",
            "DB2,123,1,2,3,4,5,1,2,nan,4,5,6",
        ):
            with self.subTest(line=line), self.assertRaises(ObservationParseError):
                parse_esp32_telemetry_line("left", line)

    def test_manager_exposes_db2_motor_values_only_when_emitted(self):
        manager = HardwareObservationManager(enabled=False, maximum_sample_age_ms=250)
        manager.ingest_line(
            "right",
            "DB2,42,125,188,89,28,169,1,2,3,4,5,6",
            1_000_000_000,
        )
        snapshot = manager.snapshot(1_100_000_000)
        side = snapshot["sides"]["right"]
        self.assertEqual(side["telemetryFormat"], "DB2")
        self.assertEqual(side["controllerMillis"], 42)
        self.assertEqual(side["motorJoints"]["right_hip_yaw"]["positionDeg"], 5)
        self.assertTrue(side["motorJoints"]["right_hip_yaw"]["available"])

    def test_raw_tail_and_legacy_identity_are_passively_detected(self):
        manager = HardwareObservationManager(enabled=False, maximum_sample_age_ms=250)
        manager.ingest_line("left", "180,181,182,183,184", 1_000_000_000)
        side = manager.snapshot(1_100_000_000)["sides"]["left"]
        self.assertEqual(side["rawTail"][-1]["text"], "180,181,182,183,184")
        self.assertEqual(side["rawTail"][-1]["direction"], "rx")
        self.assertEqual(side["firmware"]["family"], "legacy-five-angle")
        self.assertEqual(side["firmware"]["version"], "exact-build-unknown")

    def test_snapshot_requires_both_fresh_sides_and_never_claims_tx(self):
        manager = HardwareObservationManager(enabled=False, maximum_sample_age_ms=250)
        manager.ingest_line("left", "180,181,182,183,184", 1_000_000_000)
        partial = manager.snapshot(1_100_000_000)
        self.assertFalse(partial["complete"])
        self.assertEqual(partial["txBytes"], 0)
        self.assertFalse(partial["writeCapable"])
        self.assertEqual(partial["unobservedJoints"], ["left_hip_yaw", "right_hip_yaw"])
        self.assertFalse(partial["sides"]["left"]["motorJoints"]["left_knee"]["available"])
        self.assertIsNone(partial["sides"]["left"]["motorJoints"]["left_knee"]["positionDeg"])
        self.assertEqual(
            partial["sides"]["left"]["motorJoints"]["left_hip_yaw"]["canId"],
            "0x149",
        )

        manager.ingest_line("right", "185,186,187,188,189", 1_050_000_000)
        complete = manager.snapshot(1_150_000_000)
        self.assertTrue(complete["complete"])
        self.assertTrue(complete["sides"]["left"]["fresh"])
        self.assertTrue(complete["sides"]["right"]["fresh"])

        stale = manager.snapshot(1_400_000_001)
        self.assertFalse(stale["complete"])
        self.assertEqual(stale["sides"]["left"]["joints"], {})


class FrontendControlGateTests(unittest.TestCase):
    def setUp(self):
        self.gate = HardwareControlGate()
        self.now = 5_000_000_000

    def _acknowledgements(self):
        return {key: True for key in SAFETY_ACKNOWLEDGEMENTS}

    def test_three_stages_are_ordered_and_command_transport_stays_locked(self):
        first = self.gate.advance({"stage": 1}, self.now)
        self.assertEqual(first["stage"], 1)
        challenge = first["challenge"]
        second = self.gate.advance(
            {
                "stage": 2,
                "challenge": challenge,
                "acknowledgements": self._acknowledgements(),
            },
            self.now + 1,
        )
        self.assertEqual(second["stage"], 2)
        third = self.gate.advance(
            {"stage": 3, "challenge": challenge, "confirm": True},
            self.now + 2,
        )
        self.assertTrue(third["frontendArmed"])
        self.assertFalse(third["hardwareOutputEnabled"])
        disposition = self.gate.inspect_command(
            {
                "schema": CONTROL_COMMAND_SCHEMA,
                "leaseToken": third["leaseToken"],
                "jointName": "left_knee",
                "mode": "joint_position",
                "valueSi": 0.25,
            },
            self.now + 3,
        )
        self.assertFalse(disposition["accepted"])
        self.assertEqual(disposition["disposition"], "PHYSICAL_TRANSPORT_LOCKED")

    def test_missing_acknowledgement_and_out_of_order_stage_reset(self):
        first = self.gate.advance({"stage": 1}, self.now)
        acknowledgements = self._acknowledgements()
        acknowledgements[SAFETY_ACKNOWLEDGEMENTS[0]] = False
        with self.assertRaises(ControlGateError):
            self.gate.advance(
                {
                    "stage": 2,
                    "challenge": first["challenge"],
                    "acknowledgements": acknowledgements,
                },
                self.now + 1,
            )
        self.assertEqual(self.gate.snapshot(self.now + 2)["stage"], 0)
        with self.assertRaises(ControlGateError):
            self.gate.advance({"stage": 3, "confirm": True}, self.now + 3)
        self.assertEqual(self.gate.snapshot(self.now + 4)["stage"], 0)

    def test_challenge_and_lease_expire(self):
        self.gate.advance({"stage": 1}, self.now)
        expired = self.gate.snapshot(self.now + self.gate.challenge_lifetime_ns)
        self.assertEqual(expired["stage"], 0)


if __name__ == "__main__":
    unittest.main()
