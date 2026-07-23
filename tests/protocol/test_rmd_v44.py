from __future__ import annotations

import csv
import unittest
from decimal import Decimal
from pathlib import Path

from myactuator_lib import rmd_v44 as codec


FIXTURE_PATH = Path(__file__).with_name("golden_v44.tsv")


def load_vectors():
    with FIXTURE_PATH.open(newline="", encoding="utf-8") as stream:
        rows = csv.DictReader(stream, delimiter="\t")
        return {
            row["name"]: codec.CanFrame(
                arbitration_id=int(row["arbitration_id"], 0),
                data=bytes.fromhex(row["data_hex"]),
            )
            for row in rows
        }


VECTORS = load_vectors()


class GoldenEncodeTests(unittest.TestCase):
    def assert_frame(self, actual, vector_name):
        expected = VECTORS[vector_name]
        self.assertEqual(actual.arbitration_id, expected.arbitration_id)
        self.assertEqual(actual.data, expected.data)
        self.assertFalse(actual.is_extended)
        self.assertFalse(actual.is_remote)

    def test_zero_payload_commands(self):
        cases = {
            codec.Command.SHUTDOWN: "shutdown_request",
            codec.Command.STOP: "stop_request",
            codec.Command.READ_MULTI_TURN_ANGLE: "read_multi_turn_request",
            codec.Command.READ_SINGLE_TURN_ANGLE: "read_single_turn_request",
            codec.Command.READ_STATUS_1: "status1_request",
            codec.Command.READ_STATUS_2: "status2_request",
            codec.Command.READ_STATUS_3: "status3_request",
            codec.Command.OPERATING_MODE: "operating_mode_request",
            codec.Command.BRAKE_RELEASE: "brake_release_request",
            codec.Command.BRAKE_LOCK: "brake_lock_request",
        }
        for command, vector_name in cases.items():
            with self.subTest(command=command):
                self.assert_frame(codec.encode_request(1, command), vector_name)

    def test_control_commands(self):
        self.assert_frame(codec.encode_iq_control_raw(1, 100), "iq_positive_request")
        self.assert_frame(codec.encode_iq_control_raw(1, -100), "iq_negative_request")
        self.assert_frame(codec.encode_iq_control_amps(1, "1.00"), "iq_positive_request")

        self.assert_frame(codec.encode_speed_control_raw(1, 10_000), "speed_positive_request")
        self.assert_frame(codec.encode_speed_control_raw(1, -10_000), "speed_negative_request")
        self.assert_frame(codec.encode_speed_control_dps(1, "100"), "speed_positive_request")

        self.assert_frame(
            codec.encode_absolute_position_raw(1, 36_000, max_speed_raw=500),
            "absolute_positive_request",
        )
        self.assert_frame(
            codec.encode_absolute_position_raw(1, -36_000, max_speed_raw=500),
            "absolute_negative_request",
        )
        self.assert_frame(
            codec.encode_absolute_position_degrees(1, "360", max_speed_dps="500"),
            "absolute_positive_request",
        )

    def test_arbitration_id_boundaries(self):
        self.assertEqual(codec.request_arbitration_id(1), 0x141)
        self.assertEqual(codec.request_arbitration_id(32), 0x160)
        self.assertEqual(codec.response_arbitration_id(1), 0x241)
        self.assertEqual(codec.response_arbitration_id(32), 0x260)
        self.assert_frame(codec.encode_request(32, codec.Command.SHUTDOWN), "id32_shutdown_request")


class GoldenDecodeTests(unittest.TestCase):
    def test_all_shared_requests_decode(self):
        for name, frame in VECTORS.items():
            if name.endswith("_request"):
                with self.subTest(name=name):
                    decoded = codec.decode_request(frame)
                    self.assertIn(decoded.command, codec.Command)

    def test_all_shared_responses_decode(self):
        for name, frame in VECTORS.items():
            if name.endswith("_response"):
                with self.subTest(name=name):
                    codec.decode_response(frame)

    def test_angle_units(self):
        multi = codec.decode_response(VECTORS["read_multi_turn_360_response"])
        self.assertEqual(multi.angle_raw, 36_000)
        self.assertEqual(multi.angle_degrees, Decimal("360.00"))

        single = codec.decode_response(VECTORS["read_single_turn_75_response"])
        self.assertEqual(single.angle_raw, 7_500)
        self.assertEqual(single.angle_degrees, Decimal("75.00"))

    def test_status_units_and_faults(self):
        status1 = codec.decode_response(VECTORS["status1_response"])
        self.assertEqual(status1.motor_temperature_c, 50)
        self.assertEqual(status1.mos_temperature_raw, 0)
        self.assertTrue(status1.brake_command_released)
        self.assertEqual(status1.voltage_v, Decimal("48.5"))
        self.assertEqual(status1.error_mask, 0x0004)
        self.assertEqual(status1.active_errors, ("undervoltage",))
        self.assertEqual(status1.unknown_error_bits, 0)

        status2 = codec.decode_response(VECTORS["status2_positive_response"])
        self.assertEqual(status2.iq_a, Decimal("1.00"))
        self.assertEqual(status2.output_speed_dps, Decimal("500"))
        self.assertEqual(status2.output_angle_degrees, Decimal("45"))

        negative = codec.decode_response(VECTORS["iq_negative_response"])
        self.assertEqual(negative.iq_a, Decimal("-1.00"))
        self.assertEqual(negative.output_speed_dps, Decimal("-500"))
        self.assertEqual(negative.output_angle_degrees, Decimal("-45"))

        phases = codec.decode_response(VECTORS["status3_response"])
        self.assertEqual(phases.phase_a_a, Decimal("30.10"))
        self.assertEqual(phases.phase_b_a, Decimal("-15.20"))
        self.assertEqual(phases.phase_c_a, Decimal("-16.00"))

    def test_operating_mode_and_echo(self):
        mode = codec.decode_response(VECTORS["operating_mode_position_response"])
        self.assertEqual(mode.mode, codec.OperatingMode.POSITION)
        echo = codec.decode_response(VECTORS["shutdown_response"])
        self.assertEqual(echo.command, codec.Command.SHUTDOWN)


class BoundaryAndMalformedTests(unittest.TestCase):
    def assert_codec_error(self, callable_, *args, **kwargs):
        with self.assertRaises(codec.CodecError):
            callable_(*args, **kwargs)

    def test_numeric_boundaries_round_trip(self):
        for raw in (-(1 << 15), -1, 0, 1, (1 << 15) - 1):
            with self.subTest(iq_raw=raw):
                frame = codec.encode_iq_control_raw(1, raw)
                self.assertEqual(codec.decode_request(frame).iq_raw, raw)

        for raw in (-(1 << 31), -1, 0, 1, (1 << 31) - 1):
            with self.subTest(speed_raw=raw):
                frame = codec.encode_speed_control_raw(1, raw, max_torque_percent_raw=255)
                decoded = codec.decode_request(frame)
                self.assertEqual(decoded.speed_raw, raw)
                self.assertEqual(decoded.max_torque_percent_raw, 255)

        for max_speed in (0, 1, 65535):
            with self.subTest(max_speed=max_speed):
                frame = codec.encode_absolute_position_raw(1, -1, max_speed_raw=max_speed)
                decoded = codec.decode_request(frame)
                self.assertEqual(decoded.angle_raw, -1)
                self.assertEqual(decoded.max_speed_raw, max_speed)

    def test_rejects_invalid_ids_and_values(self):
        for invalid in (0, 33, 0x141, -1, True, 1.0):
            with self.subTest(motor_id=invalid):
                self.assert_codec_error(codec.encode_request, invalid, codec.Command.SHUTDOWN)
        self.assert_codec_error(codec.encode_iq_control_raw, 1, -(1 << 15) - 1)
        self.assert_codec_error(codec.encode_iq_control_raw, 1, 1 << 15)
        self.assert_codec_error(codec.encode_speed_control_raw, 1, 1 << 31)
        self.assert_codec_error(
            codec.encode_speed_control_raw, 1, 0, max_torque_percent_raw=256
        )
        self.assert_codec_error(
            codec.encode_absolute_position_raw, 1, 0, max_speed_raw=-1
        )
        self.assert_codec_error(codec.encode_request, 1, codec.Command.IQ_CONTROL)

    def test_physical_grid_is_exact_and_finite(self):
        self.assert_codec_error(codec.encode_iq_control_amps, 1, "0.005")
        self.assert_codec_error(codec.encode_speed_control_dps, 1, float("nan"))
        self.assert_codec_error(codec.encode_speed_control_dps, 1, float("inf"))
        self.assert_codec_error(
            codec.encode_absolute_position_degrees, 1, "1.001", max_speed_dps=1
        )
        self.assert_codec_error(
            codec.encode_absolute_position_degrees, 1, 1, max_speed_dps="0.5"
        )

    def test_wire_shape_and_direction_fail_closed(self):
        good = VECTORS["status1_response"]
        malformed = (
            codec.CanFrame(good.arbitration_id, good.data[:7]),
            codec.CanFrame(good.arbitration_id, good.data + b"\x00"),
            codec.CanFrame(good.arbitration_id, good.data, is_extended=True),
            codec.CanFrame(good.arbitration_id, good.data, is_remote=True),
            codec.CanFrame(0x1241, good.data),
            codec.CanFrame(0x141, good.data),
            codec.CanFrame(0x241, b"\xFF" + b"\x00" * 7),
        )
        for frame in malformed:
            with self.subTest(frame=frame):
                self.assert_codec_error(codec.decode_response, frame)

        self.assert_codec_error(codec.decode_request, VECTORS["status1_response"])
        self.assert_codec_error(codec.decode_response, VECTORS["status1_request"])

    def test_reserved_ranges_and_correlation(self):
        self.assert_codec_error(
            codec.decode_request,
            codec.CanFrame(0x141, bytes.fromhex("8001000000000000")),
        )
        self.assert_codec_error(
            codec.decode_request,
            codec.CanFrame(0x141, bytes.fromhex("A100010064000000")),
        )
        self.assert_codec_error(
            codec.decode_response,
            codec.CanFrame(0x241, bytes.fromhex("8000000000000001")),
        )
        self.assert_codec_error(
            codec.decode_response,
            codec.CanFrame(0x241, bytes.fromhex("9400000051460000")),  # 180.01 degrees
        )
        self.assert_codec_error(
            codec.decode_response,
            codec.CanFrame(0x241, bytes.fromhex("9A320002E5010000")),
        )
        self.assert_codec_error(
            codec.decode_response,
            VECTORS["status1_response"],
            expected_motor_id=2,
        )
        self.assert_codec_error(
            codec.decode_response,
            VECTORS["status1_response"],
            expected_command=codec.Command.READ_STATUS_2,
        )

    def test_unknown_fault_bits_are_retained(self):
        composite = codec.decode_response(
            codec.CanFrame(0x241, bytes.fromhex("9A320000E5011600"))
        )
        self.assertEqual(
            composite.active_errors,
            ("motor_stall", "undervoltage", "phase_overcurrent"),
        )
        unknown = codec.decode_response(
            codec.CanFrame(0x241, bytes.fromhex("9A320000E5010100"))
        )
        self.assertEqual(unknown.error_mask, 0x0001)
        self.assertEqual(unknown.unknown_error_bits, 0x0001)


if __name__ == "__main__":
    unittest.main()
