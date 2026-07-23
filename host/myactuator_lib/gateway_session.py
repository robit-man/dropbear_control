"""Async, hardware-free lifecycle for one canonical host-link V1 gateway.

Connection state, link sessions, safety leases and motion admission are
deliberately separate.  This layer negotiates a typed byte stream, correlates
semantic dispositions, and records/replays bounded host-link input.  It never
acquires or restores a lease, never retries a command automatically, never
accepts vendor-native bytes, and never reports motion authorization.
"""

from __future__ import annotations

import asyncio
import math
import secrets
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Deque, Dict, Optional, Protocol, Tuple, Union

from . import hostlink_v1 as link


READ_CHUNK_SIZE = 4096
EVENT_QUEUE_LIMIT = 128
MAX_PENDING_REQUESTS = 64
CAPTURE_RECORD_LIMIT = 512
HISTORY_RECORD_LIMIT = 512
SESSION_ID_HISTORY_LIMIT = 1024
DEFAULT_HANDSHAKE_TIMEOUT_S = 1.0
DEFAULT_REQUEST_TIMEOUT_S = 1.0


class GatewaySessionError(RuntimeError):
    """Base error for session lifecycle and request failures."""


class LifecycleError(GatewaySessionError):
    """An operation is not valid in the current lifecycle state."""


class NegotiationError(GatewaySessionError):
    """The peer did not complete the exact V1 negotiation."""


class TransportError(GatewaySessionError):
    """The injected byte transport failed or closed unexpectedly."""


class RequestTimeoutError(GatewaySessionError):
    """A pending command did not reach its requested disposition in time."""


class SessionClosedError(GatewaySessionError):
    """Pending work was invalidated by close or reconnect."""


class SessionFaultError(GatewaySessionError):
    """Pending work was invalidated by a session fault."""


class SessionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    NEGOTIATING = "negotiating"
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"
    FAULT = "fault"


class CaptureDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class AsyncByteTransport(Protocol):
    """Minimal injected transport; implementations must honor read bounds."""

    async def connect(self) -> None:
        ...

    async def read(self, maximum_bytes: int) -> bytes:
        ...

    async def write(self, data: bytes) -> None:
        ...

    async def close(self) -> None:
        ...


class MonotonicClock(Protocol):
    def now_ns(self) -> int:
        ...


class SystemMonotonicClock:
    def now_ns(self) -> int:
        return time.monotonic_ns()


def _positive_u64(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise link.ValidationError(f"{label} must be an integer")
    if not 1 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise link.ValidationError(f"{label} must be in [1, 2^64-1]")
    return value


def _nonnegative_u64(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise link.ValidationError(f"{label} must be an integer")
    if not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise link.ValidationError(f"{label} must be in [0, 2^64-1]")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise link.ValidationError(f"{label} must be a non-empty exact string")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise link.ValidationError(f"{label} contains control characters")
    if len(value.encode("utf-8")) > link.MAX_TEXT_BYTES:
        raise link.ValidationError(f"{label} exceeds host-link text bounds")
    folded = value.casefold()
    if folded in {"*", "any", "all", "default", "latest", "none", "tbd", "unknown"}:
        raise link.ValidationError(f"{label} must be concrete")
    if any(character in value for character in "*?[]{}"):
        raise link.ValidationError(f"{label} must not contain wildcard syntax")
    return value


def _timeout(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise link.ValidationError(f"{label} must be numeric seconds")
    checked = float(value)
    if not math.isfinite(checked) or checked <= 0:
        raise link.ValidationError(f"{label} must be finite and positive")
    return checked


def _clock_now(clock: MonotonicClock) -> int:
    return _nonnegative_u64(clock.now_ns(), "clock.now_ns()")


@dataclass(frozen=True)
class LeaseContext:
    """Externally issued lease facts; the session cannot construct or renew one."""

    link_session_id: int
    config: link.ConfigIdentity
    canonical_actuator_id: str
    source_identity: str
    lease_id: str
    lease_owner: str
    lease_sequence: int
    lease_expiry_monotonic_ns: int
    allowed_mode: link.CommandMode

    def __post_init__(self) -> None:
        _positive_u64(self.link_session_id, "link_session_id")
        if not isinstance(self.config, link.ConfigIdentity):
            raise link.ValidationError("lease config must be ConfigIdentity")
        object.__setattr__(
            self,
            "canonical_actuator_id",
            _identifier(self.canonical_actuator_id, "canonical_actuator_id"),
        )
        object.__setattr__(
            self, "source_identity", _identifier(self.source_identity, "source_identity")
        )
        object.__setattr__(self, "lease_id", _identifier(self.lease_id, "lease_id"))
        object.__setattr__(
            self, "lease_owner", _identifier(self.lease_owner, "lease_owner")
        )
        _positive_u64(self.lease_sequence, "lease_sequence")
        _positive_u64(self.lease_expiry_monotonic_ns, "lease_expiry_monotonic_ns")
        if not isinstance(self.allowed_mode, link.CommandMode):
            raise link.ValidationError("allowed_mode must be CommandMode")


_INTENT_FIELDS = (
    "position_rad",
    "velocity_rad_s",
    "effort_nm",
    "current_q_a",
    "stiffness_nm_per_rad",
    "damping_nm_s_per_rad",
)


@dataclass(frozen=True)
class CommandIntent:
    """Canonical SI intent with no lease authority and no native byte surface."""

    canonical_actuator_id: str
    mode: link.CommandMode
    enable_requested: bool
    position_rad: Optional[float] = None
    velocity_rad_s: Optional[float] = None
    effort_nm: Optional[float] = None
    current_q_a: Optional[float] = None
    stiffness_nm_per_rad: Optional[float] = None
    damping_nm_s_per_rad: Optional[float] = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "canonical_actuator_id",
            _identifier(self.canonical_actuator_id, "canonical_actuator_id"),
        )
        if not isinstance(self.mode, link.CommandMode):
            raise link.ValidationError("mode must be CommandMode")
        if not isinstance(self.enable_requested, bool):
            raise link.ValidationError("enable_requested must be boolean")
        for name in _INTENT_FIELDS:
            value = getattr(self, name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise link.ValidationError(f"{name} must be numeric")
                value = float(value)
                if not math.isfinite(value):
                    raise link.ValidationError(f"{name} must be finite")
                object.__setattr__(self, name, value)

    def bind(self, lease: LeaseContext) -> link.Command:
        if not isinstance(lease, LeaseContext):
            raise link.ValidationError("command requires an external LeaseContext")
        return link.Command(
            canonical_actuator_id=self.canonical_actuator_id,
            config=lease.config,
            source_identity=lease.source_identity,
            lease_id=lease.lease_id,
            lease_owner=lease.lease_owner,
            lease_sequence=lease.lease_sequence,
            lease_expiry_monotonic_ns=lease.lease_expiry_monotonic_ns,
            mode=self.mode,
            enable_requested=self.enable_requested,
            position_rad=self.position_rad,
            velocity_rad_s=self.velocity_rad_s,
            effort_nm=self.effort_nm,
            current_q_a=self.current_q_a,
            stiffness_nm_per_rad=self.stiffness_nm_per_rad,
            damping_nm_s_per_rad=self.damping_nm_s_per_rad,
        )


@dataclass(frozen=True)
class LifecycleRecord:
    index: int
    from_state: SessionState
    to_state: SessionState
    monotonic_ns: int
    reason: str


@dataclass(frozen=True)
class CaptureRecord:
    index: int
    direction: CaptureDirection
    session_id: int
    lifecycle_state: SessionState
    monotonic_ns: int
    data: bytes

    def __post_init__(self) -> None:
        _nonnegative_u64(self.index, "capture index")
        if not isinstance(self.direction, CaptureDirection):
            raise link.ValidationError("capture direction is invalid")
        _positive_u64(self.session_id, "capture session_id")
        if not isinstance(self.lifecycle_state, SessionState):
            raise link.ValidationError("capture lifecycle state is invalid")
        _nonnegative_u64(self.monotonic_ns, "capture monotonic_ns")
        if not isinstance(self.data, bytes) or len(self.data) > link.MAX_FEED_SIZE:
            raise link.ValidationError("capture data must be bounded bytes")


@dataclass(frozen=True)
class ReceiveRejectionRecord:
    session_id: int
    frame_sequence: int
    denial: link.ReceiveDenial
    detail: str


@dataclass(frozen=True)
class LateDispositionRecord:
    disposition: link.Disposition
    reason: str


@dataclass(frozen=True)
class CommandResult:
    request_session_id: int
    request_sequence: int
    canonical_actuator_id: str
    dispositions: Tuple[link.Disposition, ...]
    completed_phase: link.DispositionPhase
    rejection_reason: Optional[str]
    motion_authorized: bool = False

    def __post_init__(self) -> None:
        if self.motion_authorized:
            raise link.ValidationError("a host session result cannot authorize motion")

    def disposition(self, phase: link.DispositionPhase) -> Optional[link.Disposition]:
        for item in self.dispositions:
            if item.phase is phase:
                return item
        return None

    @property
    def received(self) -> Optional[link.Disposition]:
        return self.disposition(link.DispositionPhase.RECEIVED)

    @property
    def admitted(self) -> Optional[link.Disposition]:
        return self.disposition(link.DispositionPhase.ADMITTED)

    @property
    def native_tx(self) -> Optional[link.Disposition]:
        return self.disposition(link.DispositionPhase.NATIVE_TX)

    @property
    def native_response(self) -> Optional[link.Disposition]:
        return self.disposition(link.DispositionPhase.NATIVE_RESPONSE)

    @property
    def observed(self) -> Optional[link.Disposition]:
        return self.disposition(link.DispositionPhase.OBSERVED)

    @property
    def rejected(self) -> Optional[link.Disposition]:
        return self.disposition(link.DispositionPhase.REJECTED)


@dataclass(frozen=True)
class GatewayEvent:
    session_id: int
    frame_sequence: int
    received_monotonic_ns: int
    message: Union[link.State, link.Fault, link.Heartbeat]
    motion_authorized: bool = False

    def __post_init__(self) -> None:
        _positive_u64(self.session_id, "event session_id")
        _positive_u64(self.frame_sequence, "event frame_sequence")
        _nonnegative_u64(self.received_monotonic_ns, "event received_monotonic_ns")
        if not isinstance(self.message, (link.State, link.Fault, link.Heartbeat)):
            raise link.ValidationError("GatewayEvent message must be state/fault/heartbeat")
        if self.motion_authorized:
            raise link.ValidationError("a gateway event cannot authorize motion")


@dataclass(frozen=True)
class ReplayResult:
    messages: Tuple[link.MessageBody, ...]
    rejections: Tuple[ReceiveRejectionRecord, ...]
    parse_errors: Tuple[link.ParseErrorEvent, ...]
    consumed_records: int
    motion_authorized: bool = False

    def __post_init__(self) -> None:
        if self.motion_authorized:
            raise link.ValidationError("capture replay cannot authorize motion")


@dataclass
class _PendingRequest:
    session_id: int
    sequence: int
    actuator_id: str
    completion_phase: link.DispositionPhase
    future: "asyncio.Future[CommandResult]"
    dispositions: list[link.Disposition]


_NONTERMINAL_PHASE_ORDER = {
    link.DispositionPhase.RECEIVED: 1,
    link.DispositionPhase.ADMITTED: 2,
    link.DispositionPhase.NATIVE_TX: 3,
    link.DispositionPhase.NATIVE_RESPONSE: 4,
    link.DispositionPhase.OBSERVED: 5,
}


class GatewaySession:
    """One async host lifecycle over injected bounded byte transports."""

    def __init__(
        self,
        *,
        transport_factory: Callable[[], AsyncByteTransport],
        active_config: link.ConfigIdentity,
        local_hello: link.Hello,
        clock: Optional[MonotonicClock] = None,
        session_id_factory: Optional[Callable[[], int]] = None,
        handshake_timeout_s: float = DEFAULT_HANDSHAKE_TIMEOUT_S,
    ) -> None:
        if not callable(transport_factory):
            raise link.ValidationError("transport_factory must be callable")
        if not isinstance(active_config, link.ConfigIdentity):
            raise link.ValidationError("active_config must be exact ConfigIdentity")
        if not isinstance(local_hello, link.Hello) or local_hello.role is not link.EndpointRole.HOST:
            raise link.ValidationError("local_hello must be a HOST Hello")
        if local_hello.required_capabilities & link.MANDATORY_CAPABILITIES != link.MANDATORY_CAPABILITIES:
            raise link.ValidationError("local Hello must require all mandatory capabilities")
        if local_hello.offered_capabilities & link.MANDATORY_CAPABILITIES != link.MANDATORY_CAPABILITIES:
            raise link.ValidationError("local Hello must offer all mandatory capabilities")
        self._transport_factory = transport_factory
        self._active_config = active_config
        self._local_hello = local_hello
        self._clock = clock or SystemMonotonicClock()
        self._session_id_factory = session_id_factory or self._random_session_id
        self._handshake_timeout_s = _timeout(handshake_timeout_s, "handshake_timeout_s")

        self._state = SessionState.DISCONNECTED
        self._transport: Optional[AsyncByteTransport] = None
        self._parser = link.StreamParser()
        self._receiver: Optional[link.SessionReceiver] = None
        self._negotiation: Optional[link.Capabilities] = None
        self._session_id: Optional[int] = None
        self._used_session_ids: set[int] = set()
        self._outbound_sequence = 0
        self._last_outbound_monotonic_ns = 0
        self._peer_handshake_sequence = 0
        self._peer_handshake_monotonic_ns = 0
        self._queued_handshake_frames: Deque[link.Frame] = deque()
        self._pending: Dict[Tuple[int, int], _PendingRequest] = {}
        self._reader_task: Optional["asyncio.Task[None]"] = None
        self._send_lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._events: "asyncio.Queue[GatewayEvent]" = asyncio.Queue(EVENT_QUEUE_LIMIT)
        self._captures: Deque[CaptureRecord] = deque(maxlen=CAPTURE_RECORD_LIMIT)
        self._capture_index = 0
        self._capture_dropped_records = 0
        self._lifecycle: Deque[LifecycleRecord] = deque(maxlen=HISTORY_RECORD_LIMIT)
        self._lifecycle_index = 0
        self._parse_errors: Deque[link.ParseErrorEvent] = deque(
            maxlen=HISTORY_RECORD_LIMIT
        )
        self._receive_rejections: Deque[ReceiveRejectionRecord] = deque(
            maxlen=HISTORY_RECORD_LIMIT
        )
        self._late_dispositions: Deque[LateDispositionRecord] = deque(
            maxlen=HISTORY_RECORD_LIMIT
        )
        self._fault_reason: Optional[str] = None

    @staticmethod
    def _random_session_id() -> int:
        value = 0
        while value == 0:
            value = secrets.randbits(64)
        return value

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def active_config(self) -> link.ConfigIdentity:
        return self._active_config

    @property
    def session_id(self) -> Optional[int]:
        return self._session_id

    @property
    def outbound_sequence(self) -> int:
        return self._outbound_sequence

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def queued_event_count(self) -> int:
        return self._events.qsize()

    @property
    def negotiation(self) -> Optional[link.Capabilities]:
        return self._negotiation

    @property
    def captures(self) -> Tuple[CaptureRecord, ...]:
        return tuple(self._captures)

    @property
    def capture_dropped_records(self) -> int:
        return self._capture_dropped_records

    @property
    def lifecycle_records(self) -> Tuple[LifecycleRecord, ...]:
        return tuple(self._lifecycle)

    @property
    def parse_errors(self) -> Tuple[link.ParseErrorEvent, ...]:
        return tuple(self._parse_errors)

    @property
    def receive_rejections(self) -> Tuple[ReceiveRejectionRecord, ...]:
        return tuple(self._receive_rejections)

    @property
    def late_dispositions(self) -> Tuple[LateDispositionRecord, ...]:
        return tuple(self._late_dispositions)

    @property
    def fault_reason(self) -> Optional[str]:
        return self._fault_reason

    def _transition(self, target: SessionState, reason: str) -> None:
        if target is self._state:
            return
        previous = self._state
        self._state = target
        self._lifecycle.append(
            LifecycleRecord(
                self._lifecycle_index,
                previous,
                target,
                _clock_now(self._clock),
                reason,
            )
        )
        self._lifecycle_index += 1

    def _capture(self, direction: CaptureDirection, data: bytes) -> None:
        if self._session_id is None:
            raise LifecycleError("cannot capture bytes without a session")
        if len(self._captures) == CAPTURE_RECORD_LIMIT:
            self._capture_dropped_records += 1
        self._captures.append(
            CaptureRecord(
                self._capture_index,
                direction,
                self._session_id,
                self._state,
                _clock_now(self._clock),
                bytes(data),
            )
        )
        self._capture_index += 1

    def _new_session_id(self) -> int:
        if len(self._used_session_ids) >= SESSION_ID_HISTORY_LIMIT:
            raise LifecycleError(
                "session ID history limit reached; create a new GatewaySession"
            )
        session_id = _positive_u64(self._session_id_factory(), "generated session_id")
        if session_id in self._used_session_ids:
            raise LifecycleError("session_id_factory reused a prior session ID")
        self._used_session_ids.add(session_id)
        return session_id

    async def connect(self) -> None:
        async with self._lifecycle_lock:
            if self._state not in (
                SessionState.DISCONNECTED,
                SessionState.CLOSED,
                SessionState.FAULT,
            ):
                raise LifecycleError(f"connect is invalid while {self._state.value}")
            self._fault_reason = None
            while not self._events.empty():
                self._events.get_nowait()
            self._transition(SessionState.CONNECTING, "connect requested")
            try:
                transport = self._transport_factory()
                for method in ("connect", "read", "write", "close"):
                    if not callable(getattr(transport, method, None)):
                        raise TransportError(f"transport lacks async {method}()")
                self._transport = transport
                await asyncio.wait_for(transport.connect(), self._handshake_timeout_s)
                self._session_id = self._new_session_id()
                self._outbound_sequence = 0
                self._last_outbound_monotonic_ns = 0
                self._peer_handshake_sequence = 0
                self._peer_handshake_monotonic_ns = 0
                self._parser = link.StreamParser()
                self._receiver = None
                self._negotiation = None
                self._queued_handshake_frames.clear()
                self._transition(SessionState.NEGOTIATING, "transport connected")
                await self._negotiate()
                self._receiver = link.SessionReceiver(
                    active_session_id=self._session_id,
                    active_config_sha256=self._active_config.sha256,
                    negotiation=self._negotiation,
                    initial_sequence=self._peer_handshake_sequence,
                    initial_monotonic_ns=self._peer_handshake_monotonic_ns,
                )
                self._transition(SessionState.ACTIVE, "V1 capabilities accepted")
                self._reader_task = asyncio.create_task(
                    self._reader_loop(), name=f"gateway-session-{self._session_id}"
                )
            except asyncio.CancelledError:
                await self._connect_failed("connect cancelled")
                raise
            except Exception as exc:
                await self._connect_failed(str(exc))
                if isinstance(exc, GatewaySessionError):
                    raise
                raise GatewaySessionError(str(exc)) from exc

    async def _connect_failed(self, reason: str) -> None:
        self._fault_reason = reason
        self._transition(SessionState.FAULT, reason)
        self._fail_pending(lambda: SessionFaultError(reason))
        if self._transport is not None:
            try:
                await self._transport.close()
            except Exception:
                pass

    async def _negotiate(self) -> None:
        await self._write_body(self._local_hello, flags=link.FrameFlag.NONE)
        peer_hello_frame = await self._next_handshake_frame()
        peer_hello = self._validate_handshake_frame(
            peer_hello_frame, link.MessageType.HELLO, expected_sequence=1
        )
        if not isinstance(peer_hello, link.Hello) or peer_hello.role is not link.EndpointRole.GATEWAY:
            raise NegotiationError("peer HELLO is not a gateway")
        selected = link.negotiate(self._local_hello, peer_hello)
        self._negotiation = selected
        await self._write_body(selected, flags=link.FrameFlag.RESPONSE)
        if not selected.accepted:
            raise NegotiationError(f"peer compatibility rejected: {selected.rejection.name}")
        peer_capabilities_frame = await self._next_handshake_frame()
        peer_capabilities = self._validate_handshake_frame(
            peer_capabilities_frame,
            link.MessageType.CAPABILITIES,
            expected_sequence=2,
        )
        if not isinstance(peer_capabilities, link.Capabilities):
            raise NegotiationError("peer did not send typed capabilities")
        if peer_capabilities != selected or not peer_capabilities.accepted:
            raise NegotiationError("peer selected capabilities differ from deterministic result")

    def _validate_handshake_frame(
        self,
        frame: link.Frame,
        expected_type: link.MessageType,
        *,
        expected_sequence: int,
    ) -> link.MessageBody:
        if frame.session_id != self._session_id:
            raise NegotiationError("handshake frame uses another session")
        if frame.config_sha256 != self._active_config.sha256:
            raise NegotiationError("handshake frame configuration does not match active config")
        if frame.message_type is not expected_type:
            raise NegotiationError(
                f"expected {expected_type.name}, received {frame.message_type.name}"
            )
        if frame.sequence != expected_sequence:
            raise NegotiationError("handshake sequence is duplicate, reordered or skipped")
        if frame.monotonic_ns < self._peer_handshake_monotonic_ns:
            raise NegotiationError("handshake monotonic timestamp moved backward")
        try:
            body = link.decode_message(frame)
        except link.HostLinkError as exc:
            raise NegotiationError(f"malformed handshake body: {exc}") from exc
        self._peer_handshake_sequence = frame.sequence
        self._peer_handshake_monotonic_ns = frame.monotonic_ns
        return body

    async def _next_handshake_frame(self) -> link.Frame:
        if self._queued_handshake_frames:
            return self._queued_handshake_frames.popleft()
        while True:
            data = await self._read_transport(self._handshake_timeout_s)
            batch = self._parser.feed(data)
            self._parse_errors.extend(batch.errors)
            if batch.frames:
                self._queued_handshake_frames.extend(batch.frames[1:])
                return batch.frames[0]

    async def _read_transport(self, timeout_s: Optional[float] = None) -> bytes:
        if self._transport is None:
            raise TransportError("transport is unavailable")
        read = self._transport.read(READ_CHUNK_SIZE)
        data = await asyncio.wait_for(read, timeout_s) if timeout_s is not None else await read
        if not isinstance(data, bytes):
            raise TransportError("transport read must return bytes")
        if not data:
            raise TransportError("transport reached EOF")
        if len(data) > READ_CHUNK_SIZE or len(data) > link.MAX_FEED_SIZE:
            raise TransportError("transport violated the negotiated read bound")
        self._capture(CaptureDirection.INBOUND, data)
        return data

    async def _write_body(
        self, body: link.MessageBody, *, flags: link.FrameFlag = link.FrameFlag.NONE
    ) -> int:
        if self._transport is None or self._session_id is None:
            raise TransportError("transport/session unavailable")
        async with self._send_lock:
            if self._outbound_sequence == 0xFFFFFFFFFFFFFFFF:
                raise LifecycleError("outbound sequence exhausted; reconnect required")
            sequence = self._outbound_sequence + 1
            timestamp = _clock_now(self._clock)
            if timestamp < self._last_outbound_monotonic_ns:
                raise LifecycleError("outbound monotonic clock moved backward")
            raw = link.encode_message(
                body,
                session_id=self._session_id,
                sequence=sequence,
                monotonic_ns=timestamp,
                config_sha256=self._active_config.sha256,
                flags=flags,
            )
            await self._transport.write(raw)
            self._outbound_sequence = sequence
            self._last_outbound_monotonic_ns = timestamp
            self._capture(CaptureDirection.OUTBOUND, raw)
            return sequence

    async def send_command(
        self,
        intent: CommandIntent,
        lease: LeaseContext,
        *,
        completion_phase: link.DispositionPhase = link.DispositionPhase.OBSERVED,
        timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
    ) -> CommandResult:
        if self._state is not SessionState.ACTIVE or self._session_id is None:
            raise LifecycleError("commands require an ACTIVE session")
        if not isinstance(intent, CommandIntent):
            raise link.ValidationError("intent must be CommandIntent")
        if not isinstance(lease, LeaseContext):
            raise link.ValidationError("an external exact LeaseContext is required")
        if completion_phase not in _NONTERMINAL_PHASE_ORDER:
            raise link.ValidationError("completion_phase must be a non-rejected disposition phase")
        checked_timeout = _timeout(timeout_s, "timeout_s")
        if lease.link_session_id != self._session_id:
            raise link.ValidationError("lease context belongs to another link session")
        if lease.config != self._active_config:
            raise link.ValidationError("lease context configuration is not active")
        if lease.canonical_actuator_id != intent.canonical_actuator_id:
            raise link.ValidationError("lease context actuator does not match intent")
        if lease.allowed_mode is not intent.mode:
            raise link.ValidationError("lease context mode does not match intent")
        now = _clock_now(self._clock)
        if now < self._last_outbound_monotonic_ns:
            raise LifecycleError("outbound monotonic clock moved backward")
        if lease.lease_expiry_monotonic_ns <= now:
            raise link.ValidationError("external lease context is expired")
        body = intent.bind(lease)
        loop = asyncio.get_running_loop()
        future: "asyncio.Future[CommandResult]" = loop.create_future()

        # Reserve the exact outbound sequence while holding the same send lock
        # used by all link writes, so correlation exists before bytes can be
        # observed by a zero-latency fake gateway.
        async with self._send_lock:
            if self._state is not SessionState.ACTIVE or self._transport is None:
                raise LifecycleError("session left ACTIVE before command write")
            if self._outbound_sequence == 0xFFFFFFFFFFFFFFFF:
                raise LifecycleError("outbound sequence exhausted; reconnect required")
            sequence = self._outbound_sequence + 1
            key = (self._session_id, sequence)
            pending = _PendingRequest(
                self._session_id,
                sequence,
                intent.canonical_actuator_id,
                completion_phase,
                future,
                [],
            )
            self._pending[key] = pending
            if len(self._pending) > MAX_PENDING_REQUESTS:
                self._pending.pop(key, None)
                future.cancel()
                raise LifecycleError("pending request limit reached before write")
            try:
                raw = link.encode_message(
                    body,
                    session_id=self._session_id,
                    sequence=sequence,
                    monotonic_ns=now,
                    config_sha256=self._active_config.sha256,
                )
                await self._transport.write(raw)
            except asyncio.CancelledError:
                self._pending.pop(key, None)
                future.cancel()
                raise
            except Exception as exc:
                self._pending.pop(key, None)
                future.cancel()
                await self._enter_fault(f"command transport write failed: {exc}")
                raise TransportError(str(exc)) from exc
            self._outbound_sequence = sequence
            self._last_outbound_monotonic_ns = now
            self._capture(CaptureDirection.OUTBOUND, raw)

        try:
            return await asyncio.wait_for(asyncio.shield(future), checked_timeout)
        except asyncio.TimeoutError as exc:
            if self._pending.pop(key, None) is not None:
                future.cancel()
            raise RequestTimeoutError(
                f"request {self._session_id}:{sequence} timed out awaiting "
                f"{completion_phase.name}"
            ) from exc
        except asyncio.CancelledError:
            if self._pending.pop(key, None) is not None:
                future.cancel()
            raise

    async def next_event(self, timeout_s: Optional[float] = None) -> GatewayEvent:
        if timeout_s is None:
            return await self._events.get()
        return await asyncio.wait_for(self._events.get(), _timeout(timeout_s, "timeout_s"))

    async def _reader_loop(self) -> None:
        try:
            while self._state is SessionState.ACTIVE:
                while self._queued_handshake_frames:
                    await self._process_frame(self._queued_handshake_frames.popleft())
                data = await self._read_transport()
                batch = self._parser.feed(data)
                self._parse_errors.extend(batch.errors)
                for frame in batch.frames:
                    await self._process_frame(frame)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if self._state is SessionState.ACTIVE:
                await self._enter_fault(str(exc))

    async def _process_frame(self, frame: link.Frame) -> None:
        if self._receiver is None or self._session_id is None:
            raise LifecycleError("active receiver is unavailable")
        result = self._receiver.receive(frame)
        if not result.link_accepted:
            self._receive_rejections.append(
                ReceiveRejectionRecord(
                    self._session_id,
                    frame.sequence,
                    result.denial,
                    result.detail,
                )
            )
            return
        message = result.message
        if isinstance(message, link.Disposition):
            self._route_disposition(message)
            return
        if isinstance(message, (link.State, link.Fault, link.Heartbeat)):
            try:
                self._events.put_nowait(
                    GatewayEvent(
                        frame.session_id,
                        frame.sequence,
                        _clock_now(self._clock),
                        message,
                    )
                )
            except asyncio.QueueFull as exc:
                raise SessionFaultError("bounded host event queue overflow") from exc
            return
        raise SessionFaultError(
            f"unexpected active-session message from gateway: {type(message).__name__}"
        )

    def _route_disposition(self, disposition: link.Disposition) -> None:
        key = (disposition.request_session_id, disposition.request_sequence)
        pending = self._pending.get(key)
        if pending is None:
            self._late_dispositions.append(
                LateDispositionRecord(disposition, "no current pending request for exact key")
            )
            return
        if disposition.request_session_id != self._session_id:
            self._late_dispositions.append(
                LateDispositionRecord(disposition, "disposition names a previous session")
            )
            return
        if disposition.canonical_actuator_id != pending.actuator_id:
            self._late_dispositions.append(
                LateDispositionRecord(disposition, "actuator does not match pending request")
            )
            return
        if any(item.phase is disposition.phase for item in pending.dispositions):
            self._late_dispositions.append(
                LateDispositionRecord(disposition, "duplicate disposition phase")
            )
            return
        if disposition.phase is not link.DispositionPhase.REJECTED:
            rank = _NONTERMINAL_PHASE_ORDER[disposition.phase]
            prior_ranks = [
                _NONTERMINAL_PHASE_ORDER[item.phase]
                for item in pending.dispositions
                if item.phase is not link.DispositionPhase.REJECTED
            ]
            if prior_ranks and rank < max(prior_ranks):
                self._late_dispositions.append(
                    LateDispositionRecord(disposition, "disposition phase regressed")
                )
                return
        pending.dispositions.append(disposition)
        complete = (
            disposition.phase is link.DispositionPhase.REJECTED
            or disposition.phase is pending.completion_phase
        )
        if not complete:
            return
        self._pending.pop(key, None)
        rejection = (
            disposition.reason_code
            if disposition.phase is link.DispositionPhase.REJECTED
            else None
        )
        result = CommandResult(
            pending.session_id,
            pending.sequence,
            pending.actuator_id,
            tuple(pending.dispositions),
            disposition.phase,
            rejection,
        )
        if not pending.future.done():
            pending.future.set_result(result)

    def _fail_pending(self, exception_factory: Callable[[], Exception]) -> None:
        pending = tuple(self._pending.values())
        self._pending.clear()
        for request in pending:
            if not request.future.done():
                request.future.set_exception(exception_factory())

    async def _enter_fault(self, reason: str) -> None:
        self._fault_reason = reason
        self._transition(SessionState.FAULT, reason)
        self._fail_pending(lambda: SessionFaultError(reason))
        reader = self._reader_task
        if reader is not None and reader is not asyncio.current_task():
            reader.cancel()
            try:
                await reader
            except asyncio.CancelledError:
                pass
        if self._transport is not None:
            try:
                await self._transport.close()
            except Exception:
                pass

    async def close(self) -> None:
        async with self._lifecycle_lock:
            if self._state is SessionState.CLOSED:
                return
            if self._state is SessionState.DISCONNECTED:
                self._transition(SessionState.CLOSED, "closed before connect")
                return
            self._transition(SessionState.CLOSING, "close requested")
            self._fail_pending(lambda: SessionClosedError("session closed"))
            reader = self._reader_task
            self._reader_task = None
            if reader is not None and reader is not asyncio.current_task():
                reader.cancel()
                try:
                    await reader
                except asyncio.CancelledError:
                    pass
            if self._transport is not None:
                try:
                    await self._transport.close()
                except Exception as exc:
                    self._fault_reason = str(exc)
                    self._transition(SessionState.FAULT, f"close failed: {exc}")
                    raise TransportError(str(exc)) from exc
            self._transport = None
            self._receiver = None
            self._negotiation = None
            while not self._events.empty():
                self._events.get_nowait()
            self._queued_handshake_frames.clear()
            self._parser.reset()
            self._transition(SessionState.CLOSED, "transport closed")

    async def reconnect(self) -> None:
        if self._state in (
            SessionState.CONNECTING,
            SessionState.NEGOTIATING,
            SessionState.CLOSING,
        ):
            raise LifecycleError(f"reconnect is invalid while {self._state.value}")
        await self.close()
        await self.connect()


def replay_capture(
    records: Tuple[CaptureRecord, ...],
    *,
    session_id: int,
    active_config: link.ConfigIdentity,
    negotiation: link.Capabilities,
) -> ReplayResult:
    """Replay inbound capture chunks through a new V1 parser and receiver.

    Handshake HELLO/CAPABILITIES frames are validated and used only to seed the
    receiver replay window.  All later frames pass through the same
    :class:`link.StreamParser` and :class:`link.SessionReceiver` used live.
    No replayed command or disposition can create authority.
    """

    if not isinstance(records, tuple) or any(not isinstance(item, CaptureRecord) for item in records):
        raise link.ValidationError("records must be a tuple of CaptureRecord")
    if len(records) > CAPTURE_RECORD_LIMIT:
        raise link.ValidationError("replay input exceeds CAPTURE_RECORD_LIMIT")
    _positive_u64(session_id, "session_id")
    if not isinstance(active_config, link.ConfigIdentity):
        raise link.ValidationError("active_config must be ConfigIdentity")
    if not isinstance(negotiation, link.Capabilities) or not negotiation.accepted:
        raise link.ValidationError("replay requires accepted capabilities")
    indices = [item.index for item in records]
    if indices != sorted(indices) or len(indices) != len(set(indices)):
        raise link.ValidationError("capture record indices must be unique and ordered")

    parser = link.StreamParser()
    receiver: Optional[link.SessionReceiver] = None
    handshake_sequence = 0
    handshake_time = 0
    messages: list[link.MessageBody] = []
    rejections: list[ReceiveRejectionRecord] = []
    parse_errors: list[link.ParseErrorEvent] = []
    consumed = 0

    for record in records:
        if record.direction is not CaptureDirection.INBOUND:
            continue
        consumed += 1
        batch = parser.feed(record.data)
        parse_errors.extend(batch.errors)
        for frame in batch.frames:
            is_handshake = (
                frame.session_id == session_id
                and frame.config_sha256 == active_config.sha256
                and (
                    (frame.sequence == 1 and frame.message_type is link.MessageType.HELLO)
                    or (
                        frame.sequence == 2
                        and frame.message_type is link.MessageType.CAPABILITIES
                    )
                )
            )
            if is_handshake:
                try:
                    body = link.decode_message(frame)
                except link.HostLinkError:
                    is_handshake = False
                else:
                    valid_body = (
                        frame.sequence == 1
                        and isinstance(body, link.Hello)
                        and body.role is link.EndpointRole.GATEWAY
                    ) or (
                        frame.sequence == 2
                        and isinstance(body, link.Capabilities)
                        and body == negotiation
                    )
                    if valid_body and frame.sequence > handshake_sequence:
                        handshake_sequence = frame.sequence
                        handshake_time = frame.monotonic_ns
                        if handshake_sequence == 2:
                            receiver = link.SessionReceiver(
                                active_session_id=session_id,
                                active_config_sha256=active_config.sha256,
                                negotiation=negotiation,
                                initial_sequence=2,
                                initial_monotonic_ns=handshake_time,
                            )
                        continue
                    is_handshake = False
            if receiver is None:
                receiver = link.SessionReceiver(
                    active_session_id=session_id,
                    active_config_sha256=active_config.sha256,
                    negotiation=negotiation,
                    initial_sequence=handshake_sequence,
                    initial_monotonic_ns=handshake_time,
                )
            result = receiver.receive(frame)
            if result.link_accepted:
                messages.append(result.message)
            else:
                rejections.append(
                    ReceiveRejectionRecord(
                        session_id, frame.sequence, result.denial, result.detail
                    )
                )
    return ReplayResult(tuple(messages), tuple(rejections), tuple(parse_errors), consumed)


__all__ = [
    "AsyncByteTransport",
    "CaptureDirection",
    "CaptureRecord",
    "CAPTURE_RECORD_LIMIT",
    "CommandIntent",
    "CommandResult",
    "DEFAULT_HANDSHAKE_TIMEOUT_S",
    "DEFAULT_REQUEST_TIMEOUT_S",
    "EVENT_QUEUE_LIMIT",
    "GatewayEvent",
    "GatewaySession",
    "GatewaySessionError",
    "LateDispositionRecord",
    "LeaseContext",
    "LifecycleError",
    "LifecycleRecord",
    "HISTORY_RECORD_LIMIT",
    "MAX_PENDING_REQUESTS",
    "MonotonicClock",
    "NegotiationError",
    "READ_CHUNK_SIZE",
    "ReceiveRejectionRecord",
    "ReplayResult",
    "RequestTimeoutError",
    "SessionClosedError",
    "SessionFaultError",
    "SessionState",
    "SESSION_ID_HISTORY_LIMIT",
    "SystemMonotonicClock",
    "TransportError",
    "replay_capture",
]
