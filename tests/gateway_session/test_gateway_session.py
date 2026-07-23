from __future__ import annotations

import asyncio
import dataclasses
import unittest
from collections import deque
from typing import Optional

from myactuator_lib import gateway_session as gs
from myactuator_lib import hostlink_v1 as hl


CONFIG_HASH = bytes.fromhex("31" * 32)
OTHER_HASH = bytes.fromhex("42" * 32)
CONFIG = hl.ConfigIdentity("dropbear-generated", "robot-rev-2026-07", CONFIG_HASH)
OTHER_CONFIG = hl.ConfigIdentity("dropbear-generated", "robot-rev-other", OTHER_HASH)
HOST_TIME = 10_000_000
PEER_TIME = 9_000_000


class FakeClock:
    def __init__(self, now_ns: int = HOST_TIME) -> None:
        self.value = now_ns

    def now_ns(self) -> int:
        return self.value

    def advance(self, amount_ns: int) -> None:
        self.value += amount_ns


class FakeTransport:
    EOF = object()

    def __init__(self) -> None:
        self.incoming: "asyncio.Queue[object]" = asyncio.Queue()
        self.writes: list[bytes] = []
        self.connected = False
        self.closed = False
        self.connect_error: Optional[Exception] = None
        self.close_error: Optional[Exception] = None
        self.fail_write_number: Optional[int] = None
        self.read_bounds: list[int] = []

    async def connect(self) -> None:
        if self.connect_error is not None:
            raise self.connect_error
        self.connected = True

    async def read(self, maximum_bytes: int) -> bytes:
        self.read_bounds.append(maximum_bytes)
        value = await self.incoming.get()
        if value is self.EOF:
            return b""
        if isinstance(value, Exception):
            raise value
        if not isinstance(value, bytes):
            raise TypeError("bad fake input")
        return value

    async def write(self, data: bytes) -> None:
        if self.fail_write_number is not None and len(self.writes) + 1 == self.fail_write_number:
            raise OSError("injected write failure")
        self.writes.append(bytes(data))

    async def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error

    def feed(self, *chunks: bytes) -> None:
        for chunk in chunks:
            self.incoming.put_nowait(bytes(chunk))

    def feed_error(self, error: Exception) -> None:
        self.incoming.put_nowait(error)

    def feed_eof(self) -> None:
        self.incoming.put_nowait(self.EOF)


def host_hello(**changes: object) -> hl.Hello:
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


def gateway_hello(**changes: object) -> hl.Hello:
    values = {
        "endpoint_id": "dropbear-gateway",
        "role": hl.EndpointRole.GATEWAY,
    }
    values.update(changes)
    return host_hello(**values)


def encode_peer(
    body: hl.MessageBody,
    session_id: int,
    sequence: int,
    *,
    timestamp: Optional[int] = None,
    config_hash: bytes = CONFIG_HASH,
) -> bytes:
    if timestamp is None:
        timestamp = PEER_TIME + sequence
        if isinstance(body, hl.Disposition):
            timestamp = max(timestamp, body.phase_monotonic_ns)
        elif isinstance(body, hl.State):
            timestamp = body.sample_monotonic_ns + body.sample_age_ns
        elif isinstance(body, hl.Fault):
            timestamp = max(timestamp, body.occurred_monotonic_ns)
    return hl.encode_message(
        body,
        session_id=session_id,
        sequence=sequence,
        monotonic_ns=timestamp,
        config_sha256=config_hash,
        flags=hl.FrameFlag.RESPONSE,
    )


def handshake_bytes(
    session_id: int,
    *,
    peer: Optional[hl.Hello] = None,
    peer_capabilities: Optional[hl.Capabilities] = None,
    config_hash: bytes = CONFIG_HASH,
) -> tuple[bytes, bytes, hl.Capabilities]:
    peer_hello = peer or gateway_hello()
    selected = hl.negotiate(host_hello(), peer_hello)
    peer_selected = selected if peer_capabilities is None else peer_capabilities
    return (
        encode_peer(peer_hello, session_id, 1, config_hash=config_hash),
        encode_peer(peer_selected, session_id, 2, config_hash=config_hash),
        selected,
    )


def prepare_transport(
    session_id: int,
    *,
    fragments: bool = False,
    peer: Optional[hl.Hello] = None,
    peer_capabilities: Optional[hl.Capabilities] = None,
    config_hash: bytes = CONFIG_HASH,
) -> FakeTransport:
    transport = FakeTransport()
    first, second, _ = handshake_bytes(
        session_id,
        peer=peer,
        peer_capabilities=peer_capabilities,
        config_hash=config_hash,
    )
    stream = first + second
    if fragments:
        widths = (1, 2, 7, 19, 3, 31, 5, 11)
        offset = 0
        index = 0
        while offset < len(stream):
            width = widths[index % len(widths)]
            transport.feed(stream[offset : offset + width])
            offset += width
            index += 1
    else:
        transport.feed(stream)
    return transport


class TransportFactory:
    def __init__(self, transports: list[FakeTransport]) -> None:
        self.transports = deque(transports)
        self.created: list[FakeTransport] = []

    def __call__(self) -> FakeTransport:
        value = self.transports.popleft()
        self.created.append(value)
        return value


class SessionIds:
    def __init__(self, *values: int) -> None:
        self.values = deque(values)

    def __call__(self) -> int:
        return self.values.popleft()


def make_session(
    transports: list[FakeTransport],
    session_ids: tuple[int, ...],
    *,
    clock: Optional[FakeClock] = None,
    config: hl.ConfigIdentity = CONFIG,
) -> gs.GatewaySession:
    return gs.GatewaySession(
        transport_factory=TransportFactory(transports),
        active_config=config,
        local_hello=host_hello(),
        clock=clock or FakeClock(),
        session_id_factory=SessionIds(*session_ids),
        handshake_timeout_s=0.2,
    )


def intent(**changes: object) -> gs.CommandIntent:
    values = {
        "canonical_actuator_id": "left-knee-actuator",
        "mode": hl.CommandMode.POSITION,
        "enable_requested": True,
        "position_rad": 0.25,
    }
    values.update(changes)
    return gs.CommandIntent(**values)


def lease(session_id: int, **changes: object) -> gs.LeaseContext:
    values = {
        "link_session_id": session_id,
        "config": CONFIG,
        "canonical_actuator_id": "left-knee-actuator",
        "source_identity": "controller-main",
        "lease_id": "gateway-issued-lease-7",
        "lease_owner": "locomotion-controller",
        "lease_sequence": 19,
        "lease_expiry_monotonic_ns": HOST_TIME + 5_000_000,
        "allowed_mode": hl.CommandMode.POSITION,
    }
    values.update(changes)
    return gs.LeaseContext(**values)


def disposition(
    request_session: int,
    request_sequence: int,
    phase: hl.DispositionPhase,
) -> hl.Disposition:
    reason = "LIMIT_REJECTED" if phase is hl.DispositionPhase.REJECTED else "NONE"
    return hl.Disposition(
        request_session,
        request_sequence,
        "left-knee-actuator",
        phase,
        PEER_TIME + 100 + int(phase),
        reason,
    )


def state_message() -> hl.State:
    envelope_time = PEER_TIME + 300
    return hl.State(
        "left-knee-actuator",
        CONFIG,
        envelope_time - 10,
        10,
        hl.SampleValidity.VALID,
        hl.Connectivity.CONNECTED,
        hl.DriveHealth.OK,
        hl.BusHealth.OK,
        hl.NativeResponseState.VALID,
        "NONE",
        hl.SafetyState.DISABLED,
        position_rad=0.1,
        velocity_rad_s=0.0,
        native_status_code=0,
        native_fault_mask=0,
    )


async def spin_until(predicate, turns: int = 100) -> None:
    for _ in range(turns):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition did not become true")


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_negotiate_active_and_graceful_close_states(self) -> None:
        transport = prepare_transport(101)
        session = make_session([transport], (101,))
        self.assertEqual(session.state, gs.SessionState.DISCONNECTED)
        await session.connect()
        self.assertEqual(session.state, gs.SessionState.ACTIVE)
        self.assertEqual(session.session_id, 101)
        self.assertEqual(session.outbound_sequence, 2)
        self.assertTrue(session.negotiation.accepted)
        self.assertEqual(
            [record.to_state for record in session.lifecycle_records],
            [gs.SessionState.CONNECTING, gs.SessionState.NEGOTIATING, gs.SessionState.ACTIVE],
        )
        self.assertEqual(
            [hl.decode_frame(raw).message_type for raw in transport.writes],
            [hl.MessageType.HELLO, hl.MessageType.CAPABILITIES],
        )
        await session.close()
        self.assertEqual(session.state, gs.SessionState.CLOSED)
        self.assertTrue(transport.closed)
        self.assertEqual(
            [record.to_state for record in session.lifecycle_records][-2:],
            [gs.SessionState.CLOSING, gs.SessionState.CLOSED],
        )

    async def test_fragmented_handshake_uses_bounded_reads_and_same_parser(self) -> None:
        transport = prepare_transport(102, fragments=True)
        session = make_session([transport], (102,))
        await session.connect()
        self.assertEqual(session.state, gs.SessionState.ACTIVE)
        self.assertGreater(len([r for r in session.captures if r.direction is gs.CaptureDirection.INBOUND]), 8)
        self.assertTrue(all(bound == gs.READ_CHUNK_SIZE for bound in transport.read_bounds))
        self.assertEqual(session.parse_errors, ())
        await session.close()

    async def test_major_capability_and_config_negotiation_fail_closed(self) -> None:
        cases = (
            prepare_transport(103, peer=gateway_hello(supported_major=2)),
            prepare_transport(
                104,
                peer=gateway_hello(
                    required_capabilities=hl.MANDATORY_CAPABILITIES & ~hl.Capability.LEASE_BINDING,
                    offered_capabilities=hl.MANDATORY_CAPABILITIES & ~hl.Capability.LEASE_BINDING,
                ),
            ),
            prepare_transport(105, config_hash=OTHER_HASH),
        )
        for index, transport in enumerate(cases, start=103):
            with self.subTest(session=index):
                session = make_session([transport], (index,))
                with self.assertRaises(gs.GatewaySessionError):
                    await session.connect()
                self.assertEqual(session.state, gs.SessionState.FAULT)
                self.assertTrue(transport.closed)

    async def test_peer_capabilities_must_equal_deterministic_selection(self) -> None:
        selected = handshake_bytes(106)[2]
        mismatched = dataclasses.replace(selected, selected_rate_hz=400)
        transport = prepare_transport(106, peer_capabilities=mismatched)
        session = make_session([transport], (106,))
        with self.assertRaises(gs.NegotiationError):
            await session.connect()
        self.assertEqual(session.state, gs.SessionState.FAULT)

    async def test_connect_transport_failure_and_unexpected_eof_enter_fault(self) -> None:
        failed = FakeTransport()
        failed.connect_error = OSError("connect failed")
        session = make_session([failed], (107,))
        with self.assertRaises(gs.GatewaySessionError):
            await session.connect()
        self.assertEqual(session.state, gs.SessionState.FAULT)

        transport = prepare_transport(108)
        session = make_session([transport], (108,))
        await session.connect()
        transport.feed_eof()
        await spin_until(lambda: session.state is gs.SessionState.FAULT)
        self.assertIn("EOF", session.fault_reason)

    async def test_close_before_connect_and_idempotent_close(self) -> None:
        session = make_session([FakeTransport()], (109,))
        await session.close()
        await session.close()
        self.assertEqual(session.state, gs.SessionState.CLOSED)
        self.assertEqual(len(session.lifecycle_records), 1)


class CommandCorrelationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.transport = prepare_transport(201)
        self.clock = FakeClock()
        self.session = make_session([self.transport], (201,), clock=self.clock)
        await self.session.connect()

    async def asyncTearDown(self) -> None:
        if self.session.state not in (gs.SessionState.CLOSED, gs.SessionState.DISCONNECTED):
            try:
                await self.session.close()
            except gs.GatewaySessionError:
                pass

    async def send_task(
        self,
        *,
        completion: hl.DispositionPhase = hl.DispositionPhase.OBSERVED,
        timeout: float = 0.2,
    ) -> "asyncio.Task[gs.CommandResult]":
        task = asyncio.create_task(
            self.session.send_command(
                intent(), lease(201), completion_phase=completion, timeout_s=timeout
            )
        )
        await spin_until(lambda: len(self.transport.writes) == 3)
        return task

    async def test_command_requires_external_exact_lease_and_wire_body_is_typed(self) -> None:
        with self.assertRaises(hl.ValidationError):
            await self.session.send_command(intent(), object())
        task = await self.send_task(completion=hl.DispositionPhase.RECEIVED)
        command_frame = hl.decode_frame(self.transport.writes[-1])
        body = hl.decode_message(command_frame)
        self.assertIsInstance(body, hl.Command)
        self.assertEqual(body.source_identity, "controller-main")
        self.assertEqual(body.lease_id, "gateway-issued-lease-7")
        self.transport.feed(
            encode_peer(disposition(201, command_frame.sequence, hl.DispositionPhase.RECEIVED), 201, 3)
        )
        result = await task
        self.assertFalse(result.motion_authorized)
        self.assertIsNotNone(result.received)

    async def test_all_dispositions_remain_separate_until_observed(self) -> None:
        task = await self.send_task()
        request_sequence = hl.decode_frame(self.transport.writes[-1]).sequence
        phases = (
            hl.DispositionPhase.RECEIVED,
            hl.DispositionPhase.ADMITTED,
            hl.DispositionPhase.NATIVE_TX,
            hl.DispositionPhase.NATIVE_RESPONSE,
            hl.DispositionPhase.OBSERVED,
        )
        frames = b"".join(
            encode_peer(disposition(201, request_sequence, phase), 201, index)
            for index, phase in enumerate(phases, start=3)
        )
        self.transport.feed(frames)
        result = await task
        self.assertEqual(tuple(item.phase for item in result.dispositions), phases)
        self.assertIsNotNone(result.received)
        self.assertIsNotNone(result.admitted)
        self.assertIsNotNone(result.native_tx)
        self.assertIsNotNone(result.native_response)
        self.assertIsNotNone(result.observed)
        self.assertIsNone(result.rejected)
        self.assertFalse(result.motion_authorized)

    async def test_concurrent_sends_receive_one_monotonic_outbound_sequence(self) -> None:
        first = asyncio.create_task(
            self.session.send_command(
                intent(),
                lease(201, lease_id="lease-a", lease_sequence=20),
                timeout_s=0.2,
            )
        )
        second = asyncio.create_task(
            self.session.send_command(
                intent(),
                lease(201, lease_id="lease-b", lease_sequence=21),
                timeout_s=0.2,
            )
        )
        await spin_until(lambda: len(self.transport.writes) == 4)
        sequences = [hl.decode_frame(raw).sequence for raw in self.transport.writes]
        self.assertEqual(sequences, [1, 2, 3, 4])
        self.transport.feed(
            encode_peer(disposition(201, 3, hl.DispositionPhase.OBSERVED), 201, 3),
            encode_peer(disposition(201, 4, hl.DispositionPhase.OBSERVED), 201, 4),
        )
        results = await asyncio.gather(first, second)
        self.assertEqual({result.request_sequence for result in results}, {3, 4})
        self.assertTrue(all(not result.motion_authorized for result in results))

    async def test_outbound_monotonic_clock_regression_is_rejected_before_write(self) -> None:
        self.clock.value = HOST_TIME - 1
        with self.assertRaises(gs.LifecycleError):
            await self.session.send_command(intent(), lease(201))
        self.assertEqual(len(self.transport.writes), 2)

    async def test_rejected_disposition_completes_with_reason_without_promotion(self) -> None:
        task = await self.send_task()
        request_sequence = hl.decode_frame(self.transport.writes[-1]).sequence
        self.transport.feed(
            encode_peer(
                disposition(201, request_sequence, hl.DispositionPhase.REJECTED), 201, 3
            )
        )
        result = await task
        self.assertEqual(result.completed_phase, hl.DispositionPhase.REJECTED)
        self.assertEqual(result.rejection_reason, "LIMIT_REJECTED")
        self.assertFalse(result.motion_authorized)

    async def test_timeout_removes_pending_and_late_disposition_cannot_complete(self) -> None:
        task = await self.send_task(timeout=0.01)
        request_sequence = hl.decode_frame(self.transport.writes[-1]).sequence
        with self.assertRaises(gs.RequestTimeoutError):
            await task
        self.assertEqual(self.session.pending_count, 0)
        self.transport.feed(
            encode_peer(disposition(201, request_sequence, hl.DispositionPhase.OBSERVED), 201, 3)
        )
        await spin_until(lambda: len(self.session.late_dispositions) == 1)
        self.assertEqual(self.session.pending_count, 0)

    async def test_caller_cancellation_removes_pending_without_retry(self) -> None:
        task = await self.send_task()
        writes_before = len(self.transport.writes)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.session.pending_count, 0)
        await asyncio.sleep(0)
        self.assertEqual(len(self.transport.writes), writes_before)

    async def test_close_cancels_pending_request_and_sends_nothing_else(self) -> None:
        task = await self.send_task()
        writes_before = len(self.transport.writes)
        await self.session.close()
        with self.assertRaises(gs.SessionClosedError):
            await task
        self.assertEqual(self.session.pending_count, 0)
        self.assertEqual(len(self.transport.writes), writes_before)

    async def test_external_lease_session_config_actuator_mode_and_expiry_are_exact(self) -> None:
        invalid = (
            lease(999),
            lease(201, config=OTHER_CONFIG),
            lease(201, canonical_actuator_id="right-knee-actuator"),
            lease(201, allowed_mode=hl.CommandMode.VELOCITY),
            lease(201, lease_expiry_monotonic_ns=HOST_TIME),
        )
        for context in invalid:
            with self.subTest(context=context):
                with self.assertRaises(hl.ValidationError):
                    await self.session.send_command(intent(), context)
        self.assertEqual(len(self.transport.writes), 2)

    async def test_transport_write_failure_faults_session_and_exposes_no_result(self) -> None:
        self.transport.fail_write_number = 3
        with self.assertRaises(gs.TransportError):
            await self.session.send_command(intent(), lease(201))
        self.assertEqual(self.session.state, gs.SessionState.FAULT)
        self.assertEqual(self.session.pending_count, 0)

    async def test_faulted_reader_fails_pending_request(self) -> None:
        task = await self.send_task()
        self.transport.feed_error(OSError("injected read failure"))
        with self.assertRaises(gs.SessionFaultError):
            await task
        self.assertEqual(self.session.state, gs.SessionState.FAULT)
        self.assertEqual(self.session.pending_count, 0)

    async def test_previous_session_config_mismatch_and_corruption_cannot_complete_request(self) -> None:
        task = await self.send_task()
        request_sequence = hl.decode_frame(self.transport.writes[-1]).sequence
        body = disposition(201, request_sequence, hl.DispositionPhase.OBSERVED)
        prior = encode_peer(body, 200, 3)
        mismatch = encode_peer(body, 201, 3, config_hash=OTHER_HASH)
        corrupt = bytearray(encode_peer(body, 201, 3))
        corrupt[hl.HEADER_SIZE + 2] ^= 0x40
        self.transport.feed(prior + mismatch + bytes(corrupt))
        await spin_until(
            lambda: len(self.session.receive_rejections) >= 2 and len(self.session.parse_errors) >= 1
        )
        self.assertFalse(task.done())
        valid = encode_peer(body, 201, 3)
        self.transport.feed(valid)
        result = await task
        self.assertEqual(result.completed_phase, hl.DispositionPhase.OBSERVED)

    async def test_gateway_state_event_preserves_typed_body(self) -> None:
        message = state_message()
        frame = encode_peer(message, 201, 3, timestamp=PEER_TIME + 300)
        self.transport.feed(frame[:13], frame[13:79], frame[79:])
        restored = await self.session.next_event(timeout_s=0.2)
        self.assertEqual(restored.message, message)
        self.assertEqual(restored.session_id, 201)
        self.assertFalse(restored.motion_authorized)

    async def test_intent_surface_has_no_raw_or_vendor_byte_field(self) -> None:
        names = {field.name for field in dataclasses.fields(gs.CommandIntent)}
        self.assertNotIn("raw", " ".join(names))
        self.assertNotIn("payload", names)
        self.assertFalse(hasattr(self.session, "acquire_lease"))
        self.assertFalse(hasattr(self.session, "restore_lease"))

    async def test_pending_request_limit_fails_before_an_additional_write(self) -> None:
        tasks = [
            asyncio.create_task(
                self.session.send_command(
                    intent(),
                    lease(
                        201,
                        lease_id=f"bounded-lease-{index}",
                        lease_sequence=100 + index,
                    ),
                    timeout_s=1.0,
                )
            )
            for index in range(gs.MAX_PENDING_REQUESTS)
        ]
        await spin_until(
            lambda: len(self.transport.writes) == 2 + gs.MAX_PENDING_REQUESTS,
            turns=1000,
        )
        with self.assertRaises(gs.LifecycleError):
            await self.session.send_command(
                intent(),
                lease(201, lease_id="over-limit", lease_sequence=999),
                timeout_s=1.0,
            )
        self.assertEqual(len(self.transport.writes), 2 + gs.MAX_PENDING_REQUESTS)
        self.assertEqual(self.session.pending_count, gs.MAX_PENDING_REQUESTS)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.assertEqual(self.session.pending_count, 0)

    async def test_capture_and_diagnostic_retention_are_deterministically_bounded(self) -> None:
        for _ in range(gs.CAPTURE_RECORD_LIMIT + 20):
            self.transport.feed(b"bounded-noise")
        await spin_until(
            lambda: self.session.capture_dropped_records > 0,
            turns=2000,
        )
        self.assertEqual(len(self.session.captures), gs.CAPTURE_RECORD_LIMIT)
        self.assertGreater(self.session.capture_dropped_records, 0)
        self.assertLessEqual(len(self.session.parse_errors), gs.HISTORY_RECORD_LIMIT)


class ReconnectAndReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconnect_uses_fresh_session_cancels_pending_and_never_resends_command(self) -> None:
        first = prepare_transport(301)
        second = prepare_transport(302)
        session = make_session([first, second], (301, 302))
        await session.connect()
        task = asyncio.create_task(session.send_command(intent(), lease(301), timeout_s=1.0))
        await spin_until(lambda: len(first.writes) == 3)
        await session.reconnect()
        with self.assertRaises(gs.SessionClosedError):
            await task
        self.assertEqual(session.state, gs.SessionState.ACTIVE)
        self.assertEqual(session.session_id, 302)
        self.assertEqual(session.outbound_sequence, 2)
        self.assertEqual(len(second.writes), 2)
        self.assertEqual(
            [hl.decode_frame(raw).message_type for raw in second.writes],
            [hl.MessageType.HELLO, hl.MessageType.CAPABILITIES],
        )
        with self.assertRaises(hl.ValidationError):
            await session.send_command(intent(), lease(301))
        await session.close()

    async def test_previous_session_and_late_body_after_reconnect_cannot_complete_new_request(self) -> None:
        first = prepare_transport(303)
        second = prepare_transport(304)
        session = make_session([first, second], (303, 304))
        await session.connect()
        old_task = asyncio.create_task(session.send_command(intent(), lease(303), timeout_s=1.0))
        await spin_until(lambda: len(first.writes) == 3)
        old_request = hl.decode_frame(first.writes[-1]).sequence
        await session.reconnect()
        with self.assertRaises(gs.SessionClosedError):
            await old_task

        new_task = asyncio.create_task(session.send_command(intent(), lease(304), timeout_s=0.2))
        await spin_until(lambda: len(second.writes) == 3)
        new_request = hl.decode_frame(second.writes[-1]).sequence
        old_body = disposition(303, old_request, hl.DispositionPhase.OBSERVED)
        second.feed(encode_peer(old_body, 303, 3))
        second.feed(encode_peer(old_body, 304, 3))
        await spin_until(
            lambda: len(session.receive_rejections) >= 1 and len(session.late_dispositions) >= 1
        )
        self.assertFalse(new_task.done())
        second.feed(
            encode_peer(
                disposition(304, new_request, hl.DispositionPhase.OBSERVED), 304, 4
            )
        )
        result = await new_task
        self.assertEqual(result.request_session_id, 304)
        await session.close()

    async def test_session_id_reuse_fails_reconnect_closed(self) -> None:
        first = prepare_transport(305)
        second = prepare_transport(305)
        session = make_session([first, second], (305, 305))
        await session.connect()
        with self.assertRaises(gs.GatewaySessionError):
            await session.reconnect()
        self.assertEqual(session.state, gs.SessionState.FAULT)
        self.assertEqual(len(second.writes), 0)

    async def test_capture_records_are_immutable_and_replay_is_deterministic(self) -> None:
        transport = prepare_transport(306, fragments=True)
        session = make_session([transport], (306,))
        await session.connect()
        message = state_message()
        good = encode_peer(message, 306, 3, timestamp=PEER_TIME + 300)
        corrupt = bytearray(encode_peer(message, 306, 4, timestamp=PEER_TIME + 300))
        corrupt[-1] ^= 1
        transport.feed(b"noise" + bytes(corrupt) + good[:17], good[17:])
        restored = await session.next_event(timeout_s=0.2)
        self.assertEqual(restored.message, message)
        captures = session.captures
        with self.assertRaises(dataclasses.FrozenInstanceError):
            captures[0].data = b"changed"
        first = gs.replay_capture(
            captures,
            session_id=306,
            active_config=CONFIG,
            negotiation=session.negotiation,
        )
        second = gs.replay_capture(
            captures,
            session_id=306,
            active_config=CONFIG,
            negotiation=session.negotiation,
        )
        self.assertEqual(first, second)
        self.assertIn(message, first.messages)
        self.assertGreaterEqual(len(first.parse_errors), 1)
        self.assertFalse(first.motion_authorized)
        await session.close()

    async def test_replay_rejects_previous_session_and_config_mismatch(self) -> None:
        transport = prepare_transport(307)
        session = make_session([transport], (307,))
        await session.connect()
        message = state_message()
        transport.feed(
            encode_peer(message, 306, 3, timestamp=PEER_TIME + 300),
            encode_peer(
                dataclasses.replace(message, config=OTHER_CONFIG),
                307,
                3,
                timestamp=PEER_TIME + 300,
                config_hash=OTHER_HASH,
            ),
            encode_peer(message, 307, 3, timestamp=PEER_TIME + 300),
        )
        restored = await session.next_event(timeout_s=0.2)
        self.assertEqual(restored.message, message)
        replay = gs.replay_capture(
            session.captures,
            session_id=307,
            active_config=CONFIG,
            negotiation=session.negotiation,
        )
        self.assertEqual(len(replay.rejections), 2)
        self.assertEqual(
            {item.denial for item in replay.rejections},
            {
                hl.ReceiveDenial.PREVIOUS_OR_UNKNOWN_SESSION,
                hl.ReceiveDenial.CONFIG_MISMATCH,
            },
        )
        self.assertEqual(replay.messages, (message,))
        await session.close()

    async def test_reconnect_clears_old_events_and_new_events_are_session_tagged(self) -> None:
        first = prepare_transport(308)
        second = prepare_transport(309)
        session = make_session([first, second], (308, 309))
        await session.connect()
        old_message = state_message()
        first.feed(encode_peer(old_message, 308, 3, timestamp=PEER_TIME + 300))
        await spin_until(lambda: session.queued_event_count == 1)

        await session.reconnect()
        self.assertEqual(session.queued_event_count, 0)
        new_message = dataclasses.replace(old_message, position_rad=0.75)
        second.feed(encode_peer(new_message, 309, 3, timestamp=PEER_TIME + 300))
        event = await session.next_event(timeout_s=0.2)
        self.assertEqual(event.session_id, 309)
        self.assertEqual(event.frame_sequence, 3)
        self.assertEqual(event.message, new_message)
        self.assertFalse(event.motion_authorized)
        await session.close()


if __name__ == "__main__":
    unittest.main()
