from __future__ import annotations

import csv
import unittest
from pathlib import Path

from myactuator_lib import rmd_v44 as codec
from myactuator_lib import rmd_v44_emulator as emulator


ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "tests" / "protocol" / "golden_v44.tsv"


def load_golden():
    with GOLDEN_PATH.open(newline="", encoding="utf-8") as stream:
        return {
            row["name"]: codec.CanFrame(
                int(row["arbitration_id"], 0), bytes.fromhex(row["data_hex"])
            )
            for row in csv.DictReader(stream, delimiter="\t")
        }


GOLDEN = load_golden()
ALL_POLICY = emulator.CapabilityPolicy.allow_explicit(
    motion=emulator.MOTION_COMMANDS,
    brake=emulator.BRAKE_COMMANDS,
)


def admitted(_context):
    return True


def make_emulator(state=None, **kwargs):
    if state is None:
        state = emulator.NodeState(1, disabled=False)
    kwargs.setdefault("capability_policy", ALL_POLICY)
    kwargs.setdefault("admission_callback", admitted)
    return emulator.RmdV44Emulator([state], **kwargs)


class ApplicabilityAndConfigurationTests(unittest.TestCase):
    def test_scope_markers_are_explicitly_false(self):
        self.assertFalse(emulator.APPLICABILITY_VERIFIED)
        self.assertFalse(emulator.MODEL_FIRMWARE_APPLICABILITY_VERIFIED)
        self.assertFalse(emulator.IS_PHYSICAL_PLANT)
        self.assertEqual(emulator.PROTOCOL_EDITION, codec.SOURCE_EDITION)
        self.assertEqual(emulator.PROTOCOL_SOURCE_SHA256, codec.SOURCE_SHA256)
        instance = emulator.RmdV44Emulator([1])
        self.assertFalse(instance.model_firmware_applicability_verified)
        self.assertFalse(instance.is_physical_plant)

    def test_one_or_multiple_validated_unique_node_ids(self):
        instance = emulator.RmdV44Emulator([32, 1, 7])
        self.assertEqual(instance.node_ids(), (1, 7, 32))
        with self.assertRaises(ValueError):
            emulator.RmdV44Emulator([])
        with self.assertRaises(ValueError):
            emulator.RmdV44Emulator([1, 1])
        for invalid in (0, 33, True, "1"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                emulator.RmdV44Emulator([invalid])

    def test_raw_node_state_validates_every_wire_range(self):
        valid = emulator.NodeState(
            1,
            multi_turn_angle_raw=-(1 << 31),
            single_turn_angle_raw=18_000,
            iq_raw=-(1 << 15),
            output_speed_raw=(1 << 15) - 1,
            output_angle_raw=-(1 << 15),
            motor_temperature_c=-128,
            mos_temperature_raw=255,
            voltage_raw=0xFFFF,
            error_mask=0xFFFF,
            phase_a_raw=-(1 << 15),
            phase_b_raw=0,
            phase_c_raw=(1 << 15) - 1,
        )
        self.assertEqual(valid.single_turn_angle_raw, 18_000)
        invalid_fields = {
            "multi_turn_angle_raw": 1 << 31,
            "single_turn_angle_raw": 18_001,
            "iq_raw": 1 << 15,
            "output_speed_raw": -(1 << 15) - 1,
            "output_angle_raw": 1 << 15,
            "motor_temperature_c": 128,
            "mos_temperature_raw": 256,
            "voltage_raw": -1,
            "error_mask": 0x10000,
            "phase_a_raw": 1 << 15,
        }
        for name, value in invalid_fields.items():
            with self.subTest(field=name), self.assertRaises(ValueError):
                emulator.NodeState(1, **{name: value})

    def test_policy_accepts_only_the_correct_actuating_families(self):
        with self.assertRaises(emulator.EmulatorError):
            emulator.CapabilityPolicy.allow_explicit(motion=[codec.Command.STOP])
        with self.assertRaises(emulator.EmulatorError):
            emulator.CapabilityPolicy.allow_explicit(brake=[codec.Command.IQ_CONTROL])


class GoldenCompatibilityTests(unittest.TestCase):
    def assert_exchange(self, request_name, response_name, state, motor_id=1):
        instance = make_emulator(state)
        submission = instance.submit(GOLDEN[request_name])
        self.assertTrue(submission.accepted, submission.reason)
        deliveries = instance.poll()
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].frame, GOLDEN[response_name])
        decoded = codec.decode_response(
            deliveries[0].frame,
            expected_motor_id=motor_id,
            expected_command=GOLDEN[request_name].data[0],
        )
        self.assertEqual(decoded.motor_id, motor_id)

    def test_all_shared_golden_request_response_pairs(self):
        positive = dict(
            disabled=False,
            motor_temperature_c=50,
            iq_raw=100,
            output_speed_raw=500,
            output_angle_raw=45,
        )
        cases = (
            (
                "shutdown_request",
                "shutdown_response",
                emulator.NodeState(1, disabled=False),
            ),
            ("stop_request", "stop_response", emulator.NodeState(1, disabled=False)),
            (
                "read_multi_turn_request",
                "read_multi_turn_360_response",
                emulator.NodeState(1, multi_turn_angle_raw=36_000),
            ),
            (
                "read_single_turn_request",
                "read_single_turn_75_response",
                emulator.NodeState(1, single_turn_angle_raw=7_500),
            ),
            (
                "status1_request",
                "status1_response",
                emulator.NodeState(
                    1,
                    motor_temperature_c=50,
                    brake_released=True,
                    voltage_raw=485,
                    error_mask=0x0004,
                ),
            ),
            (
                "status2_request",
                "status2_positive_response",
                emulator.NodeState(1, **positive),
            ),
            (
                "status3_request",
                "status3_response",
                emulator.NodeState(
                    1,
                    motor_temperature_c=50,
                    phase_a_raw=3010,
                    phase_b_raw=-1520,
                    phase_c_raw=-1600,
                ),
            ),
            (
                "iq_positive_request",
                "iq_positive_response",
                emulator.NodeState(1, **positive),
            ),
            (
                "speed_positive_request",
                "speed_positive_response",
                emulator.NodeState(1, **positive),
            ),
            (
                "absolute_positive_request",
                "absolute_positive_response",
                emulator.NodeState(1, **positive),
            ),
            (
                "iq_negative_request",
                "iq_negative_response",
                emulator.NodeState(
                    1,
                    disabled=False,
                    motor_temperature_c=50,
                    iq_raw=-100,
                    output_speed_raw=-500,
                    output_angle_raw=-45,
                ),
            ),
            (
                "speed_negative_request",
                "speed_negative_response",
                emulator.NodeState(
                    1,
                    disabled=False,
                    motor_temperature_c=50,
                    iq_raw=-100,
                    output_speed_raw=-500,
                    output_angle_raw=-45,
                ),
            ),
            (
                "absolute_negative_request",
                "absolute_negative_response",
                emulator.NodeState(
                    1,
                    disabled=False,
                    motor_temperature_c=50,
                    iq_raw=-100,
                    output_speed_raw=-500,
                    output_angle_raw=-45,
                ),
            ),
            (
                "operating_mode_request",
                "operating_mode_position_response",
                emulator.NodeState(1, mode=codec.OperatingMode.POSITION),
            ),
            (
                "brake_release_request",
                "brake_release_response",
                emulator.NodeState(1, disabled=False),
            ),
            (
                "brake_lock_request",
                "brake_lock_response",
                emulator.NodeState(1, disabled=False),
            ),
        )
        for request_name, response_name, state in cases:
            with self.subTest(request=request_name):
                self.assert_exchange(request_name, response_name, state)

        state32 = emulator.NodeState(32, disabled=False)
        instance32 = emulator.RmdV44Emulator([state32])
        submission = instance32.submit(GOLDEN["id32_shutdown_request"])
        self.assertTrue(submission.accepted)
        self.assertEqual(instance32.poll()[0].frame, GOLDEN["id32_shutdown_response"])

    def test_every_codec_evidenced_opcode_generates_a_decodable_response(self):
        state = emulator.NodeState(1, disabled=False)
        instance = make_emulator(state)
        requests = [
            codec.encode_request(1, command) for command in codec.ZERO_PAYLOAD_COMMANDS
        ] + [
            codec.encode_iq_control_raw(1, 0),
            codec.encode_speed_control_raw(1, 0),
            codec.encode_absolute_position_raw(1, 0, max_speed_raw=0),
        ]
        for request in requests:
            with self.subTest(command=request.data[0]):
                if instance.state(1).disabled:
                    instance.set_enabled(1, True)
                result = instance.submit(request)
                self.assertTrue(result.accepted, result.reason)
                response = instance.poll()[0].frame
                self.assertEqual(response.arbitration_id, 0x241)
                codec.decode_response(
                    response,
                    expected_motor_id=1,
                    expected_command=request.data[0],
                )


class FailClosedAndStateTests(unittest.TestCase):
    def test_malformed_reserved_wrong_direction_and_wrong_id_do_not_mutate_state(self):
        instance = make_emulator(
            emulator.NodeState(1, disabled=False, stopped=True, iq_raw=55)
        )
        original = instance.state(1)
        malformed = (
            codec.CanFrame(0x141, bytes.fromhex("8001000000000000")),
            codec.CanFrame(0x141, bytes.fromhex("A100010064000000")),
            codec.CanFrame(0x141, bytes.fromhex("A200010000000000")),
            codec.CanFrame(0x141, b"\x80" * 7),
            codec.CanFrame(0x141, b"\x80" * 8, is_extended=True),
            codec.CanFrame(0x241, bytes.fromhex("8000000000000000")),
            codec.CanFrame(0x141, b"\xff" + b"\x00" * 7),
            codec.encode_request(2, codec.Command.STOP),
        )
        for frame in malformed:
            with self.subTest(frame=frame):
                result = instance.submit(frame)
                self.assertFalse(result.accepted)
                self.assertEqual(instance.state(1), original)
                self.assertEqual(instance.pending_count(), 0)

    def test_motion_is_default_deny_at_each_independent_gate(self):
        request = codec.encode_iq_control_raw(1, 123)

        default = emulator.RmdV44Emulator([emulator.NodeState(1, disabled=False)])
        self.assertEqual(default.submit(request).reason, "capability_policy_denied")

        no_callback = emulator.RmdV44Emulator(
            [emulator.NodeState(1, disabled=False)],
            capability_policy=ALL_POLICY,
        )
        self.assertEqual(
            no_callback.submit(request).reason, "admission_callback_missing"
        )

        callback_denied = emulator.RmdV44Emulator(
            [emulator.NodeState(1, disabled=False)],
            capability_policy=ALL_POLICY,
            admission_callback=lambda _context: False,
        )
        self.assertEqual(
            callback_denied.submit(request).reason, "admission_callback_denied"
        )

        non_boolean = emulator.RmdV44Emulator(
            [emulator.NodeState(1, disabled=False)],
            capability_policy=ALL_POLICY,
            admission_callback=lambda _context: 1,
        )
        self.assertEqual(
            non_boolean.submit(request).reason, "admission_callback_denied"
        )

        disabled = make_emulator(emulator.NodeState(1, disabled=True))
        self.assertEqual(disabled.submit(request).reason, "node_disabled")

    def test_admission_callback_error_fails_closed_without_state_change(self):
        def raises(_context):
            raise RuntimeError("lease service unavailable")

        instance = emulator.RmdV44Emulator(
            [emulator.NodeState(1, disabled=False)],
            capability_policy=ALL_POLICY,
            admission_callback=raises,
        )
        original = instance.state(1)
        result = instance.submit(codec.encode_speed_control_raw(1, 10))
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "admission_callback_error")
        self.assertEqual(instance.state(1), original)
        self.assertIn(
            "admission_callback_error", [event.kind for event in instance.events()]
        )

    def test_brake_lock_and_release_require_policy_enable_and_admission(self):
        release = codec.encode_request(1, codec.Command.BRAKE_RELEASE)
        lock = codec.encode_request(1, codec.Command.BRAKE_LOCK)
        denied = emulator.RmdV44Emulator([emulator.NodeState(1, disabled=False)])
        self.assertFalse(denied.submit(release).accepted)
        self.assertFalse(denied.state(1).brake_released)

        instance = make_emulator(emulator.NodeState(1, disabled=False))
        self.assertTrue(instance.submit(release).accepted)
        self.assertTrue(instance.state(1).brake_released)
        instance.poll()
        self.assertTrue(instance.submit(lock).accepted)
        self.assertFalse(instance.state(1).brake_released)

    def test_shutdown_and_stop_are_distinct_protocol_states(self):
        stop_instance = make_emulator(
            emulator.NodeState(1, disabled=False, stopped=False)
        )
        stop_instance.submit(codec.encode_request(1, codec.Command.STOP))
        self.assertFalse(stop_instance.state(1).disabled)
        self.assertTrue(stop_instance.state(1).stopped)

        shutdown_instance = make_emulator(
            emulator.NodeState(1, disabled=False, stopped=False)
        )
        shutdown_instance.submit(codec.encode_request(1, codec.Command.SHUTDOWN))
        self.assertTrue(shutdown_instance.state(1).disabled)
        self.assertFalse(shutdown_instance.state(1).stopped)
        denied = shutdown_instance.submit(codec.encode_iq_control_raw(1, 10))
        self.assertEqual(denied.reason, "node_disabled")

    def test_motion_records_raw_command_but_never_synthesizes_telemetry(self):
        original = emulator.NodeState(
            1,
            disabled=False,
            stopped=True,
            iq_raw=-17,
            output_speed_raw=23,
            output_angle_raw=-41,
            multi_turn_angle_raw=999,
        )
        instance = make_emulator(original)
        result = instance.submit(
            codec.encode_speed_control_raw(1, 1_234_567, max_torque_percent_raw=37)
        )
        self.assertTrue(result.accepted)
        state = instance.state(1)
        self.assertFalse(state.stopped)
        self.assertEqual(state.last_speed_command_raw, 1_234_567)
        self.assertEqual(state.last_speed_max_torque_percent_raw, 37)
        self.assertEqual(state.iq_raw, original.iq_raw)
        self.assertEqual(state.output_speed_raw, original.output_speed_raw)
        self.assertEqual(state.output_angle_raw, original.output_angle_raw)
        self.assertEqual(state.multi_turn_angle_raw, original.multi_turn_angle_raw)
        response = codec.decode_response(instance.poll()[0].frame)
        self.assertEqual(response.iq_raw, -17)
        self.assertEqual(response.output_speed_raw, 23)
        self.assertEqual(response.output_angle_raw, -41)

    def test_admission_context_carries_raw_request_state_time_and_sequence(self):
        contexts = []
        instance = emulator.RmdV44Emulator(
            [emulator.NodeState(1, disabled=False)],
            capability_policy=ALL_POLICY,
            admission_callback=lambda context: contexts.append(context) is None,
        )
        instance.advance_to(17)
        request = codec.encode_absolute_position_raw(1, -36000, max_speed_raw=500)
        self.assertTrue(instance.submit(request).accepted)
        context = contexts[0]
        self.assertEqual(context.now_us, 17)
        self.assertEqual(context.request_sequence, 1)
        self.assertEqual(context.request.angle_raw, -36000)
        self.assertEqual(context.request.max_speed_raw, 500)
        self.assertFalse(context.state.disabled)


class VirtualTimeAndInjectionTests(unittest.TestCase):
    def test_monotonic_virtual_time_latency_and_request_order(self):
        instance = emulator.RmdV44Emulator(
            [1, 2], response_latency_us=5, response_deadline_us=20
        )
        first = instance.submit(codec.encode_request(2, codec.Command.READ_STATUS_1))
        second = instance.submit(codec.encode_request(1, codec.Command.READ_STATUS_1))
        self.assertEqual(first.response_due_us, 5)
        self.assertEqual(second.response_due_us, 5)
        self.assertEqual(instance.advance_to(4), ())
        deliveries = instance.advance_to(5)
        self.assertEqual(
            [delivery.frame.arbitration_id for delivery in deliveries],
            [0x242, 0x241],
        )
        with self.assertRaises(emulator.EmulatorError):
            instance.advance_to(4)

    def test_configurable_and_per_request_deadline(self):
        instance = emulator.RmdV44Emulator(
            [1], response_latency_us=6, response_deadline_us=10
        )
        missed = instance.submit(
            codec.encode_request(1, codec.Command.READ_STATUS_1),
            response_deadline_us=5,
        )
        self.assertEqual(missed.reason, "accepted_response_will_miss_deadline")
        self.assertEqual(instance.advance_to(4), ())
        self.assertEqual(instance.advance_to(5), ())
        self.assertIn(
            "response_deadline_missed", [event.kind for event in instance.events()]
        )
        self.assertEqual(instance.pending_count(), 0)

    def test_drop_and_delay_are_one_shot_and_match_specific_requests(self):
        instance = emulator.RmdV44Emulator(
            [1], response_latency_us=5, response_deadline_us=30
        )
        instance.queue_scenario(
            emulator.ResponseScenario(
                motor_id=1,
                command=codec.Command.READ_STATUS_1,
                drop_response=True,
            )
        )
        dropped = instance.submit(codec.encode_request(1, codec.Command.READ_STATUS_1))
        self.assertEqual(dropped.reason, "accepted_response_dropped")
        self.assertEqual(instance.pending_count(), 0)

        instance.queue_scenario(
            emulator.ResponseScenario(
                motor_id=1,
                command=codec.Command.READ_STATUS_1,
                extra_delay_us=10,
            )
        )
        delayed = instance.submit(codec.encode_request(1, codec.Command.READ_STATUS_1))
        ordinary = instance.submit(codec.encode_request(1, codec.Command.READ_STATUS_1))
        self.assertEqual(delayed.response_due_us, 15)
        self.assertEqual(ordinary.response_due_us, 5)
        self.assertEqual(
            [delivery.request_sequence for delivery in instance.advance_to(5)], [3]
        )
        self.assertEqual(
            [delivery.request_sequence for delivery in instance.advance_to(15)], [2]
        )

    def test_unexpected_response_is_codec_valid_but_intentionally_uncorrelated(self):
        unexpected = codec.CanFrame(0x242, bytes.fromhex("8100000000000000"))
        instance = emulator.RmdV44Emulator([1, 2])
        instance.queue_scenario(
            emulator.ResponseScenario(
                motor_id=1,
                command=codec.Command.READ_STATUS_1,
                unexpected_response=unexpected,
            )
        )
        result = instance.submit(codec.encode_request(1, codec.Command.READ_STATUS_1))
        self.assertTrue(result.accepted)
        delivered = instance.poll()[0].frame
        self.assertEqual(delivered, unexpected)
        codec.decode_response(delivered)
        with self.assertRaises(codec.CodecError):
            codec.decode_response(
                delivered,
                expected_motor_id=1,
                expected_command=codec.Command.READ_STATUS_1,
            )

    def test_drive_fault_updates_raw_fault_state_and_can_fail_disabled(self):
        state = emulator.NodeState(1, disabled=False, error_mask=0)
        instance = make_emulator(state)
        instance.queue_scenario(
            emulator.ResponseScenario(
                motor_id=1,
                command=codec.Command.READ_STATUS_1,
                drive_error_mask=0x1004,
                drive_disables=True,
            )
        )
        self.assertTrue(
            instance.submit(
                codec.encode_request(1, codec.Command.READ_STATUS_1)
            ).accepted
        )
        self.assertTrue(instance.state(1).disabled)
        self.assertEqual(instance.state(1).error_mask, 0x1004)
        status = codec.decode_response(instance.poll()[0].frame)
        self.assertEqual(status.error_mask, 0x1004)
        self.assertIn("undervoltage", status.active_errors)
        self.assertIn("motor_overtemperature", status.active_errors)

    def test_delayed_response_past_deadline_is_not_delivered(self):
        instance = emulator.RmdV44Emulator(
            [1], response_latency_us=2, response_deadline_us=10
        )
        instance.queue_scenario(emulator.ResponseScenario(extra_delay_us=9))
        result = instance.submit(codec.encode_request(1, codec.Command.READ_STATUS_2))
        self.assertEqual(result.response_due_us, 11)
        self.assertEqual(result.response_deadline_us, 10)
        self.assertEqual(instance.run_until_idle(), ())
        self.assertEqual(instance.now_us, 10)


class ReplayAndEventLogTests(unittest.TestCase):
    def test_event_log_and_replay_are_deterministic(self):
        def configured():
            instance = emulator.RmdV44Emulator(
                [emulator.NodeState(1, disabled=False, voltage_raw=485)],
                response_latency_us=5,
                response_deadline_us=30,
                capability_policy=ALL_POLICY,
                admission_callback=admitted,
            )
            instance.queue_scenario(
                emulator.ResponseScenario(
                    command=codec.Command.READ_STATUS_1,
                    extra_delay_us=2,
                )
            )
            return instance

        original = configured()
        original.submit(codec.encode_request(1, codec.Command.READ_STATUS_1))
        original.advance_to(3)
        original.submit(codec.encode_request(1, codec.Command.STOP))
        original_deliveries = original.run_until_idle()
        records = original.replay_records()

        replayed = configured()
        replay_deliveries = replayed.replay(records)
        self.assertEqual(replay_deliveries, original_deliveries)
        self.assertEqual(replayed.events(), original.events())
        self.assertEqual(replayed.state(1), original.state(1))
        self.assertEqual(replayed.replay_records(), records)

    def test_event_sequences_are_dense_and_frames_are_preserved(self):
        instance = emulator.RmdV44Emulator([1])
        request = codec.encode_request(1, codec.Command.READ_STATUS_1)
        instance.submit(request)
        instance.poll()
        events = instance.events()
        self.assertEqual(
            [event.event_sequence for event in events],
            list(range(1, len(events) + 1)),
        )
        self.assertEqual(events[0].kind, "request_received")
        self.assertEqual(events[0].frame, request)
        self.assertEqual(events[-1].kind, "response_delivered")
        self.assertEqual(events[-1].frame.arbitration_id, 0x241)

    def test_replay_rejects_out_of_order_time(self):
        instance = emulator.RmdV44Emulator([1])
        records = (
            emulator.ReplayRecord(
                2, codec.encode_request(1, codec.Command.READ_STATUS_1)
            ),
            emulator.ReplayRecord(
                1, codec.encode_request(1, codec.Command.READ_STATUS_1)
            ),
        )
        with self.assertRaises(emulator.EmulatorError):
            instance.replay(records)


if __name__ == "__main__":
    unittest.main()
