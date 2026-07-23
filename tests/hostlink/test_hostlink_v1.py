from __future__ import annotations

import dataclasses
import math
import random
import struct
import unittest

from myactuator_lib import hostlink_v1 as hl


CONFIG_HASH = bytes.fromhex("11" * 32)
OTHER_HASH = bytes.fromhex("22" * 32)
CONFIG = hl.ConfigIdentity("dropbear-main", "robot-rev-2026-07", CONFIG_HASH)
SESSION = 0x1020304050607080
BASE_TIME = 9_000_000_000


def hello(**changes: object) -> hl.Hello:
    values = {
        "endpoint_id": "dropbear-host",
        "role": hl.EndpointRole.HOST,
        "supported_major": 1,
        "minimum_minor": 0,
        "maximum_minor": 0,
        "required_capabilities": hl.MANDATORY_CAPABILITIES,
        "offered_capabilities": hl.MANDATORY_CAPABILITIES,
        "minimum_rate_hz": 50,
        "maximum_rate_hz": 1000,
        "preferred_rate_hz": 500,
        "maximum_payload_size": hl.MAX_PAYLOAD_SIZE,
    }
    values.update(changes)
    return hl.Hello(**values)


def negotiation() -> hl.Capabilities:
    result = hl.negotiate(hello(), hello(endpoint_id="dropbear-gateway", role=hl.EndpointRole.GATEWAY))
    if not result.accepted:
        raise AssertionError("test fixture negotiation failed")
    return result


def command(mode: hl.CommandMode = hl.CommandMode.POSITION, **changes: object) -> hl.Command:
    mode_values = {
        hl.CommandMode.DISABLE: {},
        hl.CommandMode.POSITION: {"position_rad": 0.25},
        hl.CommandMode.VELOCITY: {"velocity_rad_s": -1.5},
        hl.CommandMode.EFFORT: {"effort_nm": 2.75},
        hl.CommandMode.CURRENT_Q: {"current_q_a": -0.4},
        hl.CommandMode.IMPEDANCE: {
            "position_rad": 0.2,
            "velocity_rad_s": -0.1,
            "stiffness_nm_per_rad": 22.0,
            "damping_nm_s_per_rad": 0.8,
        },
    }
    values = {
        "canonical_actuator_id": "left-knee-actuator",
        "config": CONFIG,
        "source_identity": "controller-main",
        "lease_id": "locomotion-lease-7",
        "lease_owner": "controller-main",
        "lease_sequence": 41,
        "lease_expiry_monotonic_ns": BASE_TIME + 2_000_000_000,
        "mode": mode,
        "enable_requested": mode is not hl.CommandMode.DISABLE,
    }
    values.update(mode_values[mode])
    values.update(changes)
    return hl.Command(**values)


def state(**changes: object) -> hl.State:
    values = {
        "canonical_actuator_id": "left-knee-actuator",
        "config": CONFIG,
        "sample_monotonic_ns": BASE_TIME - 2_000_000,
        "sample_age_ns": 2_000_000,
        "validity": hl.SampleValidity.VALID,
        "connectivity": hl.Connectivity.CONNECTED,
        "drive_health": hl.DriveHealth.OK,
        "bus_health": hl.BusHealth.OK,
        "native_response": hl.NativeResponseState.VALID,
        "fault_code": "NONE",
        "safety_state": hl.SafetyState.DISABLED,
        "position_rad": 0.4,
        "velocity_rad_s": -0.2,
        "effort_nm": 1.2,
        "current_q_a": 0.3,
        "temperature_c": 38.5,
        "voltage_v": 47.8,
        "native_status_code": 0x1234,
        "native_fault_mask": 0,
    }
    values.update(changes)
    return hl.State(**values)


def encode_body(body: hl.MessageBody, sequence: int = 1, **changes: object) -> bytes:
    values = {
        "session_id": SESSION,
        "sequence": sequence,
        "monotonic_ns": BASE_TIME,
        "config_sha256": CONFIG_HASH,
    }
    values.update(changes)
    return hl.encode_message(body, **values)


def decoded_body(body: hl.MessageBody, sequence: int = 1, **changes: object) -> hl.MessageBody:
    return hl.decode_message(hl.decode_frame(encode_body(body, sequence, **changes)))


def replace_crc(frame: bytes) -> bytes:
    return frame[:-hl.CRC_SIZE] + struct.pack(">I", hl.crc32c(frame[:-hl.CRC_SIZE]))


def frame_for(body: hl.MessageBody, sequence: int = 1, **changes: object) -> hl.Frame:
    return hl.decode_frame(encode_body(body, sequence, **changes))


class CrcAndEnvelopeTests(unittest.TestCase):
    def test_crc32c_standard_check_value(self) -> None:
        self.assertEqual(hl.crc32c(b"123456789"), 0xE3069283)
        self.assertEqual(hl.crc32c(b""), 0)

    def test_fixed_layout_and_round_trip_preserve_every_header_field(self) -> None:
        raw = encode_body(
            hl.Heartbeat(
                "gateway-main",
                hl.EndpointRole.GATEWAY,
                hl.LinkHealth.ACTIVE,
                hl.SafetyState.DISABLED,
                123456,
                88,
            ),
            sequence=99,
            flags=hl.FrameFlag.RESPONSE | hl.FrameFlag.URGENT_SAFETY,
        )
        self.assertEqual(hl.HEADER_SIZE, 72)
        self.assertEqual(len(raw), hl.HEADER_SIZE + len(hl.decode_frame(raw).payload) + 4)
        frame = hl.decode_frame(raw)
        self.assertEqual(frame.message_type, hl.MessageType.HEARTBEAT)
        self.assertEqual(frame.flags, hl.FrameFlag.RESPONSE | hl.FrameFlag.URGENT_SAFETY)
        self.assertEqual(frame.session_id, SESSION)
        self.assertEqual(frame.sequence, 99)
        self.assertEqual(frame.monotonic_ns, BASE_TIME)
        self.assertEqual(frame.config_sha256, CONFIG_HASH)

    def test_encoding_is_byte_deterministic(self) -> None:
        body = command(hl.CommandMode.IMPEDANCE, effort_nm=0.15)
        first = encode_body(body, sequence=7)
        self.assertEqual(first, encode_body(body, sequence=7))
        self.assertEqual(hl.encode_frame(hl.decode_frame(first)), first)

    def test_payload_frame_and_feed_limits_are_published_and_enforced(self) -> None:
        self.assertEqual(hl.MAX_FRAME_SIZE, hl.HEADER_SIZE + hl.MAX_PAYLOAD_SIZE + 4)
        self.assertEqual(hl.MAX_BUFFER_SIZE, 2 * hl.MAX_FRAME_SIZE)
        maximum = hl.Frame(
            hl.MessageType.HEARTBEAT,
            hl.FrameFlag.NONE,
            SESSION,
            1,
            BASE_TIME,
            CONFIG_HASH,
            b"x" * hl.MAX_PAYLOAD_SIZE,
        )
        self.assertEqual(len(hl.encode_frame(maximum)), hl.MAX_FRAME_SIZE)
        with self.assertRaises(hl.ValidationError):
            dataclasses.replace(maximum, payload=b"x" * (hl.MAX_PAYLOAD_SIZE + 1))
        parser = hl.StreamParser()
        with self.assertRaises(hl.BufferLimitError):
            parser.feed(b"x" * (hl.MAX_FEED_SIZE + 1))
        self.assertEqual(parser.buffered_bytes, 0)

    def test_complete_frame_rejects_bad_magic_version_lengths_type_flags_reserved_and_crc(self) -> None:
        base = bytearray(encode_body(hl.Heartbeat("host", hl.EndpointRole.HOST, hl.LinkHealth.ACTIVE, hl.SafetyState.DISABLED, 1, 0)))
        cases = []
        changed = bytearray(base)
        changed[0] ^= 1
        cases.append(bytes(changed))
        changed = bytearray(base)
        changed[4] = 2
        cases.append(replace_crc(bytes(changed)))
        changed = bytearray(base)
        changed[6:8] = struct.pack(">H", hl.HEADER_SIZE + 1)
        cases.append(replace_crc(bytes(changed)))
        changed = bytearray(base)
        changed[8:12] = struct.pack(">I", hl.MAX_PAYLOAD_SIZE + 1)
        cases.append(replace_crc(bytes(changed)))
        changed = bytearray(base)
        changed[12] = 0xFF
        cases.append(replace_crc(bytes(changed)))
        changed = bytearray(base)
        changed[13] = 0x80
        cases.append(replace_crc(bytes(changed)))
        changed = bytearray(base)
        changed[14] = 1
        cases.append(replace_crc(bytes(changed)))
        changed = bytearray(base)
        changed[-1] ^= 1
        cases.append(bytes(changed))
        cases.extend((bytes(base[:-1]), bytes(base) + b"x"))
        for index, case in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(hl.FrameError):
                    hl.decode_frame(case)

    def test_zero_session_and_sequence_are_rejected(self) -> None:
        with self.assertRaises(hl.ValidationError):
            hl.Frame(hl.MessageType.HELLO, hl.FrameFlag.NONE, 0, 1, 0, hl.ZERO_SHA256, b"")
        with self.assertRaises(hl.ValidationError):
            hl.Frame(hl.MessageType.HELLO, hl.FrameFlag.NONE, 1, 0, 0, hl.ZERO_SHA256, b"")


class TypedBodyTests(unittest.TestCase):
    def test_hello_capabilities_fault_and_heartbeat_round_trip(self) -> None:
        messages = (
            hello(),
            negotiation(),
            hl.Fault(
                "BUS_OFF",
                hl.FaultSeverity.LATCHED,
                hl.SafetyState.FAULT,
                BASE_TIME - 1,
                17,
                "left-knee-actuator",
                "CAN controller entered bus-off; no hardware claim",
            ),
            hl.Heartbeat(
                "gateway-main",
                hl.EndpointRole.GATEWAY,
                hl.LinkHealth.DEGRADED,
                hl.SafetyState.SHUTDOWN,
                99_000,
                42,
            ),
        )
        for message in messages:
            with self.subTest(message=type(message).__name__):
                self.assertEqual(decoded_body(message), message)

    def test_every_command_mode_round_trips_with_exact_si_fields(self) -> None:
        messages = (
            command(hl.CommandMode.DISABLE),
            command(hl.CommandMode.POSITION, velocity_rad_s=0.1, effort_nm=0.2),
            command(hl.CommandMode.VELOCITY, effort_nm=-0.2),
            command(hl.CommandMode.EFFORT),
            command(hl.CommandMode.CURRENT_Q),
            command(hl.CommandMode.IMPEDANCE, effort_nm=0.3),
        )
        for message in messages:
            with self.subTest(mode=message.mode):
                self.assertEqual(decoded_body(message), message)

    def test_command_modes_reject_missing_and_forbidden_fields(self) -> None:
        invalid = (
            lambda: command(hl.CommandMode.POSITION, position_rad=None),
            lambda: command(hl.CommandMode.VELOCITY, velocity_rad_s=None),
            lambda: command(hl.CommandMode.EFFORT, effort_nm=None),
            lambda: command(hl.CommandMode.CURRENT_Q, current_q_a=None),
            lambda: command(hl.CommandMode.IMPEDANCE, damping_nm_s_per_rad=None),
            lambda: command(hl.CommandMode.DISABLE, effort_nm=0.0),
            lambda: command(hl.CommandMode.EFFORT, position_rad=0.0),
            lambda: command(hl.CommandMode.CURRENT_Q, velocity_rad_s=0.0),
        )
        for index, constructor in enumerate(invalid):
            with self.subTest(index=index):
                with self.assertRaises(hl.ValidationError):
                    constructor()

    def test_command_enable_state_is_mode_specific(self) -> None:
        with self.assertRaises(hl.ValidationError):
            command(hl.CommandMode.DISABLE, enable_requested=True)
        with self.assertRaises(hl.ValidationError):
            command(hl.CommandMode.POSITION, enable_requested=False)

    def test_all_command_numeric_fields_reject_nan_and_infinity(self) -> None:
        field_modes = {
            "position_rad": hl.CommandMode.POSITION,
            "velocity_rad_s": hl.CommandMode.VELOCITY,
            "effort_nm": hl.CommandMode.EFFORT,
            "current_q_a": hl.CommandMode.CURRENT_Q,
            "stiffness_nm_per_rad": hl.CommandMode.IMPEDANCE,
            "damping_nm_s_per_rad": hl.CommandMode.IMPEDANCE,
        }
        for field_name, mode in field_modes.items():
            for value in (math.nan, math.inf, -math.inf):
                with self.subTest(field=field_name, value=value):
                    with self.assertRaises(hl.ValidationError):
                        command(mode, **{field_name: value})

    def test_command_requires_exact_actuator_config_and_lease_identity(self) -> None:
        changes = (
            {"canonical_actuator_id": "unknown"},
            {"canonical_actuator_id": "left-*-actuator"},
            {"source_identity": "any"},
            {"lease_id": "lease-unknown"},
            {"lease_owner": "any"},
            {"lease_sequence": 0},
            {"lease_expiry_monotonic_ns": 0},
        )
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaises(hl.ValidationError):
                    command(**change)
        with self.assertRaises(hl.ValidationError):
            hl.ConfigIdentity("dropbear", "unknown", CONFIG_HASH)
        with self.assertRaises(hl.ValidationError):
            hl.ConfigIdentity("dropbear", "rev-1", hl.ZERO_SHA256)

    def test_command_config_hash_must_equal_envelope_and_lease_must_be_live(self) -> None:
        with self.assertRaises(hl.ValidationError):
            encode_body(command(), config_sha256=OTHER_HASH)
        with self.assertRaises(hl.ValidationError):
            encode_body(command(lease_expiry_monotonic_ns=BASE_TIME), monotonic_ns=BASE_TIME)

    def test_state_round_trip_preserves_times_age_health_fault_safety_and_native_status(self) -> None:
        message = state()
        restored = decoded_body(message)
        self.assertEqual(restored, message)
        self.assertEqual(restored.sample_monotonic_ns, BASE_TIME - 2_000_000)
        self.assertEqual(restored.sample_age_ns, 2_000_000)
        self.assertEqual(restored.validity, hl.SampleValidity.VALID)
        self.assertEqual(restored.connectivity, hl.Connectivity.CONNECTED)
        self.assertEqual(restored.drive_health, hl.DriveHealth.OK)
        self.assertEqual(restored.bus_health, hl.BusHealth.OK)
        self.assertEqual(restored.native_response, hl.NativeResponseState.VALID)
        self.assertEqual(restored.native_status_code, 0x1234)
        self.assertEqual(restored.native_fault_mask, 0)

    def test_state_optional_fields_are_presence_preserving(self) -> None:
        message = state(
            validity=hl.SampleValidity.INVALID,
            connectivity=hl.Connectivity.DISCONNECTED,
            drive_health=hl.DriveHealth.UNKNOWN,
            bus_health=hl.BusHealth.BUS_OFF,
            native_response=hl.NativeResponseState.TIMED_OUT,
            fault_code="NO_RESPONSE",
            position_rad=None,
            velocity_rad_s=None,
            effort_nm=None,
            current_q_a=None,
            temperature_c=None,
            voltage_v=None,
            native_status_code=None,
            native_fault_mask=None,
        )
        self.assertEqual(decoded_body(message), message)

    def test_state_age_and_sample_time_are_bound_to_envelope(self) -> None:
        with self.assertRaises(hl.ValidationError):
            encode_body(state(sample_age_ns=1))
        with self.assertRaises(hl.ValidationError):
            encode_body(state(sample_monotonic_ns=BASE_TIME + 1, sample_age_ns=0))

    def test_state_numeric_fields_reject_nonfinite_values(self) -> None:
        for field_name in (
            "position_rad",
            "velocity_rad_s",
            "effort_nm",
            "current_q_a",
            "temperature_c",
            "voltage_v",
        ):
            with self.subTest(field=field_name):
                with self.assertRaises(hl.ValidationError):
                    state(**{field_name: math.nan})

    def test_all_disposition_phases_are_distinct_and_round_trip(self) -> None:
        expected = {
            hl.DispositionPhase.RECEIVED,
            hl.DispositionPhase.ADMITTED,
            hl.DispositionPhase.NATIVE_TX,
            hl.DispositionPhase.NATIVE_RESPONSE,
            hl.DispositionPhase.OBSERVED,
            hl.DispositionPhase.REJECTED,
        }
        observed = set()
        for index, phase in enumerate(hl.DispositionPhase, start=1):
            reason = "LIMIT_REJECTED" if phase is hl.DispositionPhase.REJECTED else "NONE"
            message = hl.Disposition(SESSION, 10, "left-knee-actuator", phase, BASE_TIME, reason)
            self.assertEqual(decoded_body(message, sequence=index), message)
            observed.add(phase)
        self.assertEqual(observed, expected)

    def test_disposition_does_not_equate_tx_or_native_response_with_observed(self) -> None:
        self.assertNotEqual(hl.DispositionPhase.NATIVE_TX, hl.DispositionPhase.NATIVE_RESPONSE)
        self.assertNotEqual(hl.DispositionPhase.NATIVE_RESPONSE, hl.DispositionPhase.OBSERVED)
        with self.assertRaises(hl.ValidationError):
            hl.Disposition(SESSION, 1, "actuator-1", hl.DispositionPhase.REJECTED, 1, "NONE")
        with self.assertRaises(hl.ValidationError):
            hl.Disposition(SESSION, 1, "actuator-1", hl.DispositionPhase.ADMITTED, 1, "BAD")

    def test_truncated_trailing_and_nonfinite_typed_payloads_are_rejected(self) -> None:
        valid = frame_for(command())
        for payload in (valid.payload[:-1], valid.payload + b"x"):
            with self.subTest(length=len(payload)):
                with self.assertRaises(hl.BodyError):
                    hl.decode_message(dataclasses.replace(valid, payload=payload))
        corrupted = bytearray(valid.payload)
        # The last value is the required POSITION float64.
        corrupted[-8:] = struct.pack(">d", math.nan)
        with self.assertRaises(hl.BodyError):
            hl.decode_message(dataclasses.replace(valid, payload=bytes(corrupted)))

    def test_no_typed_command_field_or_message_type_is_a_vendor_raw_escape(self) -> None:
        self.assertNotIn("payload", {field.name for field in dataclasses.fields(hl.Command)})
        self.assertNotIn("raw", " ".join(field.name for field in dataclasses.fields(hl.Command)))
        self.assertEqual(
            set(hl.MessageType),
            {
                hl.MessageType.HELLO,
                hl.MessageType.CAPABILITIES,
                hl.MessageType.COMMAND,
                hl.MessageType.STATE,
                hl.MessageType.DISPOSITION,
                hl.MessageType.FAULT,
                hl.MessageType.HEARTBEAT,
            },
        )
        with self.assertRaises(hl.ValidationError):
            encode_body(b"vendor bytes")


class NegotiationTests(unittest.TestCase):
    def test_compatible_minor_capability_rate_and_payload_select_deterministically(self) -> None:
        local = hello(minimum_minor=0, maximum_minor=2, minimum_rate_hz=100, maximum_rate_hz=800, preferred_rate_hz=600)
        peer = hello(
            endpoint_id="gateway",
            role=hl.EndpointRole.GATEWAY,
            minimum_minor=0,
            maximum_minor=1,
            minimum_rate_hz=200,
            maximum_rate_hz=500,
            preferred_rate_hz=400,
            maximum_payload_size=2048,
        )
        result = hl.negotiate(local, peer)
        self.assertTrue(result.accepted)
        self.assertEqual(result.selected_major, 1)
        self.assertEqual(result.selected_minor, 0)
        self.assertEqual(result.selected_capabilities, hl.MANDATORY_CAPABILITIES)
        self.assertEqual(result.selected_rate_hz, 400)
        self.assertEqual(result.selected_payload_size, 2048)

    def test_major_mismatch_fails_closed(self) -> None:
        result = hl.negotiate(hello(), hello(supported_major=2))
        self.assertFalse(result.accepted)
        self.assertEqual(result.rejection, hl.NegotiationRejection.MAJOR_VERSION_MISMATCH)

    def test_minor_mismatch_fails_closed(self) -> None:
        result = hl.negotiate(hello(), hello(minimum_minor=1, maximum_minor=2))
        self.assertFalse(result.accepted)
        self.assertEqual(result.rejection, hl.NegotiationRejection.MINOR_VERSION_MISMATCH)

    def test_missing_required_capability_fails_closed(self) -> None:
        reduced = hl.MANDATORY_CAPABILITIES & ~hl.Capability.LEASE_BINDING
        peer = hello(required_capabilities=reduced, offered_capabilities=reduced)
        result = hl.negotiate(hello(), peer)
        self.assertFalse(result.accepted)
        self.assertEqual(result.rejection, hl.NegotiationRejection.CAPABILITY_MISMATCH)

    def test_disjoint_rate_ranges_fail_closed(self) -> None:
        result = hl.negotiate(
            hello(minimum_rate_hz=10, maximum_rate_hz=100, preferred_rate_hz=50),
            hello(minimum_rate_hz=200, maximum_rate_hz=400, preferred_rate_hz=300),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.rejection, hl.NegotiationRejection.RATE_MISMATCH)

    def test_too_small_payload_limit_fails_closed(self) -> None:
        result = hl.negotiate(hello(), hello(maximum_payload_size=128))
        self.assertFalse(result.accepted)
        self.assertEqual(result.rejection, hl.NegotiationRejection.PAYLOAD_LIMIT_MISMATCH)

    def test_rejected_capability_body_cannot_claim_selected_parameters(self) -> None:
        with self.assertRaises(hl.ValidationError):
            hl.Capabilities(
                False,
                1,
                0,
                hl.MANDATORY_CAPABILITIES,
                500,
                1024,
                hl.NegotiationRejection.CAPABILITY_MISMATCH,
            )


class StreamParserTests(unittest.TestCase):
    def test_every_single_split_point_reassembles_one_frame(self) -> None:
        raw = encode_body(command())
        for split in range(len(raw) + 1):
            with self.subTest(split=split):
                parser = hl.StreamParser()
                first = parser.feed(raw[:split])
                second = parser.feed(raw[split:])
                self.assertEqual(first.frames + second.frames, (hl.decode_frame(raw),))
                self.assertEqual(parser.buffered_bytes, 0)

    def test_one_byte_fragments_and_concatenated_frames_preserve_order(self) -> None:
        frames = [encode_body(command(), sequence=index) for index in range(1, 8)]
        parser = hl.StreamParser()
        recovered = []
        for byte in b"".join(frames):
            recovered.extend(parser.feed(bytes((byte,))).frames)
        self.assertEqual([frame.sequence for frame in recovered], list(range(1, 8)))
        parser = hl.StreamParser()
        batch = parser.feed(b"".join(frames))
        self.assertEqual([frame.sequence for frame in batch.frames], list(range(1, 8)))

    def test_noise_partial_magic_invalid_header_and_crc_corruption_resynchronize(self) -> None:
        good = encode_body(command(), sequence=12)
        bad = bytearray(encode_body(command(), sequence=11))
        bad[hl.HEADER_SIZE + 3] ^= 0x80
        fake_header = bytearray(good[:hl.HEADER_SIZE])
        fake_header[4] = 9
        stream = b"noiseDB" + b"xx" + bytes(fake_header) + bytes(bad) + b"junk" + good
        parser = hl.StreamParser()
        batch = parser.feed(stream)
        self.assertEqual([frame.sequence for frame in batch.frames], [12])
        self.assertGreater(batch.discarded_bytes, 0)
        self.assertIn(hl.ParseErrorCode.INVALID_HEADER, {event.code for event in batch.errors})
        self.assertIn(hl.ParseErrorCode.CRC_MISMATCH, {event.code for event in batch.errors})
        self.assertEqual(parser.buffered_bytes, 0)

    def test_magic_prefix_is_retained_across_noise_boundary(self) -> None:
        raw = encode_body(command())
        parser = hl.StreamParser()
        first = parser.feed(b"noise" + hl.MAGIC[:3])
        self.assertEqual(first.frames, ())
        self.assertEqual(parser.buffered_bytes, 3)
        second = parser.feed(raw[3:])
        self.assertEqual(second.frames, (hl.decode_frame(raw),))

    def test_buffer_overflow_is_reported_and_memory_remains_bounded(self) -> None:
        header = bytearray(encode_body(command())[:hl.HEADER_SIZE])
        header[8:12] = struct.pack(">I", hl.MAX_PAYLOAD_SIZE)
        parser = hl.StreamParser()
        parser.feed(bytes(header))
        batch = parser.feed(b"z" * hl.MAX_FEED_SIZE)
        self.assertLessEqual(parser.buffered_bytes, hl.MAX_BUFFER_SIZE)
        self.assertIn(hl.ParseErrorCode.BUFFER_OVERFLOW, {event.code for event in batch.errors})

    def test_seeded_fragmentation_property_for_mixed_typed_frames(self) -> None:
        rng = random.Random(0xDBA11)
        bodies = [
            command(),
            state(),
            hl.Heartbeat("gateway", hl.EndpointRole.GATEWAY, hl.LinkHealth.ACTIVE, hl.SafetyState.DISABLED, 1, 0),
            hl.Disposition(SESSION, 1, "left-knee-actuator", hl.DispositionPhase.RECEIVED, BASE_TIME, "NONE"),
        ]
        raw = b"".join(encode_body(body, sequence=index + 1) for index, body in enumerate(bodies))
        for trial in range(100):
            parser = hl.StreamParser()
            output = []
            offset = 0
            while offset < len(raw):
                width = rng.randint(1, 37)
                output.extend(parser.feed(raw[offset : offset + width]).frames)
                offset += width
            self.assertEqual([frame.sequence for frame in output], [1, 2, 3, 4], trial)
            self.assertEqual(parser.buffered_bytes, 0)

    def test_seeded_single_bit_corruption_never_exposes_corrupt_frame_and_recovers_sentinel(self) -> None:
        rng = random.Random(0xC32C)
        original = encode_body(command(), sequence=1)
        sentinel = encode_body(command(), sequence=2)
        for trial in range(250):
            corrupt = bytearray(original)
            index = rng.randrange(len(corrupt) - hl.CRC_SIZE)
            corrupt[index] ^= 1 << rng.randrange(8)
            parser = hl.StreamParser()
            batch = parser.feed(bytes(corrupt) + sentinel)
            self.assertEqual([frame.sequence for frame in batch.frames], [2], trial)
            self.assertEqual(parser.buffered_bytes, 0)

    def test_seeded_noise_fuzz_never_exceeds_buffer_or_synthesizes_frames(self) -> None:
        rng = random.Random(0xF022)
        parser = hl.StreamParser()
        for _ in range(500):
            chunk = bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 256)))
            batch = parser.feed(chunk)
            self.assertEqual(batch.frames, ())
            self.assertLessEqual(parser.buffered_bytes, len(hl.MAGIC) - 1)


class SessionReceiverTests(unittest.TestCase):
    def receiver(self, **changes: object) -> hl.SessionReceiver:
        values = {
            "active_session_id": SESSION,
            "active_config_sha256": CONFIG_HASH,
            "negotiation": negotiation(),
        }
        values.update(changes)
        return hl.SessionReceiver(**values)

    def test_valid_command_is_only_link_accepted_and_never_motion_authorized(self) -> None:
        receiver = self.receiver()
        result = receiver.receive(frame_for(command()), now_monotonic_ns=BASE_TIME)
        self.assertTrue(result.link_accepted)
        self.assertIsInstance(result.message, hl.Command)
        self.assertFalse(result.motion_authorized)
        self.assertIn("admission", result.detail)

    def test_duplicate_and_reordered_messages_are_rejected_without_exposure(self) -> None:
        receiver = self.receiver()
        accepted = frame_for(command(), sequence=5)
        self.assertTrue(receiver.receive(accepted).link_accepted)
        duplicate = receiver.receive(accepted)
        reordered = receiver.receive(frame_for(command(), sequence=4))
        self.assertEqual(duplicate.denial, hl.ReceiveDenial.DUPLICATE_SEQUENCE)
        self.assertEqual(reordered.denial, hl.ReceiveDenial.REORDERED_SEQUENCE)
        self.assertIsNone(duplicate.message)
        self.assertIsNone(reordered.message)
        self.assertEqual(receiver.last_sequence, 5)

    def test_previous_session_is_rejected_before_body_exposure(self) -> None:
        receiver = self.receiver()
        frame = dataclasses.replace(
            frame_for(command()), session_id=SESSION - 1, payload=b"malformed"
        )
        result = receiver.receive(frame)
        self.assertFalse(result.link_accepted)
        self.assertEqual(result.denial, hl.ReceiveDenial.PREVIOUS_OR_UNKNOWN_SESSION)
        self.assertIsNone(result.message)

    def test_config_mismatch_nonmonotonic_time_and_unsupported_version_fail_closed(self) -> None:
        mismatch = self.receiver().receive(
            dataclasses.replace(frame_for(command()), config_sha256=OTHER_HASH)
        )
        self.assertEqual(mismatch.denial, hl.ReceiveDenial.CONFIG_MISMATCH)
        receiver = self.receiver(initial_sequence=4, initial_monotonic_ns=BASE_TIME + 1)
        backwards = receiver.receive(frame_for(command(), sequence=5))
        self.assertEqual(backwards.denial, hl.ReceiveDenial.NONMONOTONIC_TIMESTAMP)
        unsupported = self.receiver().receive(dataclasses.replace(frame_for(command()), major=2))
        self.assertEqual(unsupported.denial, hl.ReceiveDenial.UNSUPPORTED_ENVELOPE)
        self.assertTrue(all(result.message is None for result in (mismatch, backwards, unsupported)))

    def test_malformed_typed_body_is_rejected_without_advancing_window(self) -> None:
        receiver = self.receiver()
        malformed = dataclasses.replace(frame_for(command(), sequence=10), payload=b"bad")
        result = receiver.receive(malformed)
        self.assertEqual(result.denial, hl.ReceiveDenial.MALFORMED_BODY)
        self.assertIsNone(result.message)
        self.assertEqual(receiver.last_sequence, 0)
        self.assertTrue(receiver.receive(frame_for(command(), sequence=1)).link_accepted)

    def test_command_expired_at_receiver_time_is_not_exposed(self) -> None:
        receiver = self.receiver()
        candidate = command(lease_expiry_monotonic_ns=BASE_TIME + 1)
        result = receiver.receive(
            frame_for(candidate), now_monotonic_ns=BASE_TIME + 1
        )
        self.assertEqual(result.denial, hl.ReceiveDenial.EXPIRED_COMMAND)
        self.assertIsNone(result.message)
        self.assertEqual(receiver.last_sequence, 0)

    def test_receiver_requires_accepted_complete_negotiation_and_nonzero_config(self) -> None:
        rejected = hl.negotiate(hello(), hello(supported_major=2))
        with self.assertRaises(hl.ValidationError):
            self.receiver(negotiation=rejected)
        reduced = hl.MANDATORY_CAPABILITIES & ~hl.Capability.STATE_VALIDITY
        incomplete = hl.Capabilities(
            True,
            1,
            0,
            reduced,
            500,
            1024,
            hl.NegotiationRejection.NONE,
        )
        with self.assertRaises(hl.ValidationError):
            self.receiver(negotiation=incomplete)
        with self.assertRaises(hl.ValidationError):
            self.receiver(active_config_sha256=hl.ZERO_SHA256)

    def test_duplicate_is_rejected_before_a_replaced_malformed_body_can_be_decoded(self) -> None:
        receiver = self.receiver()
        accepted = frame_for(command(), sequence=1)
        self.assertTrue(receiver.receive(accepted).link_accepted)
        replay = receiver.receive(dataclasses.replace(accepted, payload=b"bad"))
        self.assertEqual(replay.denial, hl.ReceiveDenial.DUPLICATE_SEQUENCE)
        self.assertIsNone(replay.message)


if __name__ == "__main__":
    unittest.main()
