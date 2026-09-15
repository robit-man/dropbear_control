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

    def test_snapshot_requires_both_fresh_sides_and_never_claims_tx(self):
        manager = HardwareObservationManager(enabled=False, maximum_sample_age_ms=250)
        manager.ingest_line("left", "180,181,182,183,184", 1_000_000_000)
        partial = manager.snapshot(1_100_000_000)
        self.assertFalse(partial["complete"])
        self.assertEqual(partial["txBytes"], 0)
        self.assertFalse(partial["writeCapable"])
        self.assertEqual(partial["unobservedJoints"], ["left_hip_yaw", "right_hip_yaw"])

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
