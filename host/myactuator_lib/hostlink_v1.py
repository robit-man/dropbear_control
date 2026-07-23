"""Canonical Dropbear host-link V1 reference implementation.

The module is deliberately hardware-free and standard-library-only.  It
defines a bounded binary envelope, deterministic typed message bodies,
capability/rate negotiation, stream recovery, and an established-session
anti-replay receiver.  A link-accepted :class:`Command` is only a candidate
for the independent gateway admission and safety state machines; this module
never authorizes motion or reports mechanical execution.

All integers use network byte order.  Floating-point values are finite IEEE
754 binary64 values with units carried in field names.  Vendor-native frames
or arbitrary command bytes are not part of this protocol.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass
from enum import Enum, IntEnum, IntFlag
from typing import Dict, List, Optional, Tuple, Type, Union


MAGIC = b"DBHL"
VERSION_MAJOR = 1
VERSION_MINOR = 0

# magic, major, minor, header length, payload length, type, flags, reserved,
# session, sequence, monotonic ns, active configuration SHA-256
HEADER_STRUCT = struct.Struct(">4sBBHIBBHQQQ32s")
HEADER_SIZE = HEADER_STRUCT.size
CRC_SIZE = 4
MAX_PAYLOAD_SIZE = 4096
MAX_FRAME_SIZE = HEADER_SIZE + MAX_PAYLOAD_SIZE + CRC_SIZE
MAX_BUFFER_SIZE = MAX_FRAME_SIZE * 2
MAX_FEED_SIZE = MAX_BUFFER_SIZE
MAX_TEXT_BYTES = 255
MAX_DETAIL_BYTES = 512
MIN_NEGOTIATED_PAYLOAD_SIZE = 256
MAX_CONTROL_RATE_HZ = 5000
ZERO_SHA256 = b"\x00" * 32


class HostLinkError(ValueError):
    """Base class for host-link contract violations."""


class ValidationError(HostLinkError):
    """A typed value violates the V1 contract."""


class FrameError(HostLinkError):
    """A complete envelope is malformed or corrupt."""


class BodyError(HostLinkError):
    """A typed body is malformed or inconsistent with its envelope."""


class BufferLimitError(HostLinkError):
    """One parser feed exceeded the published memory bound."""


class MessageType(IntEnum):
    HELLO = 1
    CAPABILITIES = 2
    COMMAND = 3
    STATE = 4
    DISPOSITION = 5
    FAULT = 6
    HEARTBEAT = 7


class FrameFlag(IntFlag):
    NONE = 0
    RESPONSE = 1 << 0
    URGENT_SAFETY = 1 << 1


KNOWN_FRAME_FLAGS = FrameFlag.RESPONSE | FrameFlag.URGENT_SAFETY


class EndpointRole(IntEnum):
    HOST = 1
    GATEWAY = 2
    SIMULATOR = 3
    REPLAY = 4


class Capability(IntFlag):
    NONE = 0
    TYPED_SI_COMMANDS = 1 << 0
    CONFIG_BINDING = 1 << 1
    LEASE_BINDING = 1 << 2
    STATE_VALIDITY = 1 << 3
    SEMANTIC_DISPOSITIONS = 1 << 4
    CRC32C_RESYNC = 1 << 5
    SESSION_ANTI_REPLAY = 1 << 6


MANDATORY_CAPABILITIES = (
    Capability.TYPED_SI_COMMANDS
    | Capability.CONFIG_BINDING
    | Capability.LEASE_BINDING
    | Capability.STATE_VALIDITY
    | Capability.SEMANTIC_DISPOSITIONS
    | Capability.CRC32C_RESYNC
    | Capability.SESSION_ANTI_REPLAY
)
KNOWN_CAPABILITIES = MANDATORY_CAPABILITIES


class NegotiationRejection(IntEnum):
    NONE = 0
    MAJOR_VERSION_MISMATCH = 1
    MINOR_VERSION_MISMATCH = 2
    CAPABILITY_MISMATCH = 3
    RATE_MISMATCH = 4
    PAYLOAD_LIMIT_MISMATCH = 5


class CommandMode(IntEnum):
    DISABLE = 0
    POSITION = 1
    VELOCITY = 2
    EFFORT = 3
    CURRENT_Q = 4
    IMPEDANCE = 5


class SampleValidity(IntEnum):
    INVALID = 0
    VALID = 1
    STALE = 2


class Connectivity(IntEnum):
    DISCONNECTED = 0
    DEGRADED = 1
    CONNECTED = 2


class DriveHealth(IntEnum):
    UNKNOWN = 0
    OK = 1
    WARNING = 2
    FAULT = 3


class BusHealth(IntEnum):
    UNKNOWN = 0
    OK = 1
    DEGRADED = 2
    BUS_OFF = 3
    RECOVERING = 4


class NativeResponseState(IntEnum):
    NOT_EXPECTED = 0
    PENDING = 1
    VALID = 2
    TIMED_OUT = 3
    MALFORMED = 4
    DRIVE_FAULT = 5


class SafetyState(IntEnum):
    BOOT = 0
    DISCOVERY = 1
    DISABLED = 2
    ARMED = 3
    ENABLED = 4
    SHUTDOWN = 5
    FAULT = 6


class DispositionPhase(IntEnum):
    RECEIVED = 1
    ADMITTED = 2
    NATIVE_TX = 3
    NATIVE_RESPONSE = 4
    OBSERVED = 5
    REJECTED = 6


class FaultSeverity(IntEnum):
    INFO = 0
    WARNING = 1
    RECOVERABLE = 2
    LATCHED = 3
    EMERGENCY = 4


class LinkHealth(IntEnum):
    STARTING = 0
    NEGOTIATING = 1
    ACTIVE = 2
    DEGRADED = 3
    FAULTED = 4


class ParseErrorCode(str, Enum):
    NOISE_DISCARDED = "noise_discarded"
    INVALID_HEADER = "invalid_header"
    CRC_MISMATCH = "crc_mismatch"
    BUFFER_OVERFLOW = "buffer_overflow"


class ReceiveDenial(str, Enum):
    UNSUPPORTED_ENVELOPE = "unsupported_envelope"
    PREVIOUS_OR_UNKNOWN_SESSION = "previous_or_unknown_session"
    DUPLICATE_SEQUENCE = "duplicate_sequence"
    REORDERED_SEQUENCE = "reordered_sequence"
    NONMONOTONIC_TIMESTAMP = "nonmonotonic_timestamp"
    CONFIG_MISMATCH = "config_mismatch"
    MALFORMED_BODY = "malformed_body"
    EXPIRED_COMMAND = "expired_command"


def _int(value: object, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise ValidationError(f"{label} must be in [{minimum}, {maximum}]")
    return value


def _enum(value: object, enum_type: Type[IntEnum], label: str) -> IntEnum:
    if not isinstance(value, enum_type):
        raise ValidationError(f"{label} must be {enum_type.__name__}")
    return value


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{label} must be boolean")
    return value


def _text(
    value: object,
    label: str,
    *,
    allow_empty: bool = False,
    maximum: int = MAX_TEXT_BYTES,
) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a string")
    if not value and not allow_empty:
        raise ValidationError(f"{label} must not be empty")
    encoded = value.encode("utf-8")
    if len(encoded) > maximum:
        raise ValidationError(f"{label} exceeds {maximum} UTF-8 bytes")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValidationError(f"{label} must not contain control characters")
    return value


_NONEXACT = frozenset(
    {"*", "any", "all", "default", "latest", "n/a", "none", "tbd", "unknown"}
)
_NONEXACT_SEGMENT = re.compile(
    r"(?:^|[.\-_/])(?:all|any|default|latest|none|tbd|unknown)(?:$|[.\-_/])",
    re.IGNORECASE,
)


def _exact_text(value: object, label: str) -> str:
    text = _text(value, label)
    if text != text.strip():
        raise ValidationError(f"{label} must not have surrounding whitespace")
    if (
        text.casefold() in _NONEXACT
        or any(character in text for character in "*?[]{}")
        or _NONEXACT_SEGMENT.search(text)
    ):
        raise ValidationError(f"{label} must be a concrete exact identifier")
    return text


def _status_code(value: object, label: str, *, allow_none: bool) -> str:
    """Validate a concrete status code, with an explicit uppercase NONE sentinel."""

    if allow_none and value == "NONE":
        return "NONE"
    return _exact_text(value, label)


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValidationError(f"{label} must be finite")
    return result


def _optional_finite(value: object, label: str) -> Optional[float]:
    if value is None:
        return None
    return _finite(value, label)


def _sha256(value: object, label: str, *, allow_zero: bool) -> bytes:
    if not isinstance(value, bytes) or len(value) != 32:
        raise ValidationError(f"{label} must be exactly 32 bytes")
    if not allow_zero and value == ZERO_SHA256:
        raise ValidationError(f"{label} must not be the all-zero sentinel")
    return value


def sha256_from_hex(value: str, *, allow_zero: bool = False) -> bytes:
    """Convert a canonical lowercase hexadecimal digest to wire bytes."""

    if not isinstance(value, str) or len(value) != 64 or value != value.lower():
        raise ValidationError("SHA-256 hex must be 64 canonical lowercase characters")
    try:
        result = bytes.fromhex(value)
    except ValueError as exc:
        raise ValidationError("SHA-256 hex contains a non-hexadecimal character") from exc
    return _sha256(result, "SHA-256", allow_zero=allow_zero)


def sha256_to_hex(value: bytes) -> str:
    return _sha256(value, "SHA-256", allow_zero=True).hex()


def _capability(value: object, label: str) -> Capability:
    if not isinstance(value, Capability):
        raise ValidationError(f"{label} must be Capability")
    if int(value) & ~int(KNOWN_CAPABILITIES):
        raise ValidationError(f"{label} contains unknown capability bits")
    return value


def _decode_capability(value: int, label: str) -> Capability:
    if value & ~int(KNOWN_CAPABILITIES):
        raise BodyError(f"{label} contains unknown capability bits")
    return Capability(value)


def _crc32c_table() -> Tuple[int, ...]:
    polynomial = 0x82F63B78
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            crc = (crc >> 1) ^ polynomial if crc & 1 else crc >> 1
        table.append(crc & 0xFFFFFFFF)
    return tuple(table)


_CRC32C_TABLE = _crc32c_table()


def crc32c(data: bytes) -> int:
    """Return Castagnoli CRC-32C using initial/final XOR of all ones."""

    if not isinstance(data, bytes):
        raise ValidationError("CRC input must be bytes")
    crc = 0xFFFFFFFF
    for byte in data:
        crc = _CRC32C_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


class _Writer:
    def __init__(self) -> None:
        self.data = bytearray()

    def u8(self, value: int) -> None:
        self.data.extend(struct.pack(">B", _int(value, 0, 0xFF, "uint8")))

    def u16(self, value: int) -> None:
        self.data.extend(struct.pack(">H", _int(value, 0, 0xFFFF, "uint16")))

    def u32(self, value: int) -> None:
        self.data.extend(struct.pack(">I", _int(value, 0, 0xFFFFFFFF, "uint32")))

    def u64(self, value: int) -> None:
        self.data.extend(struct.pack(">Q", _int(value, 0, 0xFFFFFFFFFFFFFFFF, "uint64")))

    def boolean(self, value: bool) -> None:
        self.u8(1 if _bool(value, "boolean") else 0)

    def f64(self, value: float) -> None:
        self.data.extend(struct.pack(">d", _finite(value, "float64")))

    def fixed(self, value: bytes, size: int) -> None:
        if not isinstance(value, bytes) or len(value) != size:
            raise ValidationError(f"fixed field must be exactly {size} bytes")
        self.data.extend(value)

    def text(self, value: str, *, allow_empty: bool = False, maximum: int = MAX_TEXT_BYTES) -> None:
        checked = _text(value, "text field", allow_empty=allow_empty, maximum=maximum)
        encoded = checked.encode("utf-8")
        self.u16(len(encoded))
        self.data.extend(encoded)

    def finish(self) -> bytes:
        if len(self.data) > MAX_PAYLOAD_SIZE:
            raise ValidationError("typed payload exceeds MAX_PAYLOAD_SIZE")
        return bytes(self.data)


class _Reader:
    def __init__(self, data: bytes) -> None:
        if not isinstance(data, bytes):
            raise BodyError("payload must be bytes")
        self.data = data
        self.offset = 0

    def take(self, size: int) -> bytes:
        if size < 0 or self.offset + size > len(self.data):
            raise BodyError("typed body is truncated")
        result = self.data[self.offset : self.offset + size]
        self.offset += size
        return result

    def u8(self) -> int:
        return struct.unpack(">B", self.take(1))[0]

    def u16(self) -> int:
        return struct.unpack(">H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack(">I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack(">Q", self.take(8))[0]

    def boolean(self) -> bool:
        value = self.u8()
        if value not in (0, 1):
            raise BodyError("boolean field must be encoded as 0 or 1")
        return bool(value)

    def f64(self) -> float:
        value = struct.unpack(">d", self.take(8))[0]
        if not math.isfinite(value):
            raise BodyError("float64 field must be finite")
        return value

    def text(self, *, allow_empty: bool = False, maximum: int = MAX_TEXT_BYTES) -> str:
        length = self.u16()
        if length > maximum:
            raise BodyError(f"text field exceeds {maximum} bytes")
        raw = self.take(length)
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BodyError("text field is not valid UTF-8") from exc
        try:
            return _text(value, "text field", allow_empty=allow_empty, maximum=maximum)
        except ValidationError as exc:
            raise BodyError(str(exc)) from exc

    def finish(self) -> None:
        if self.offset != len(self.data):
            raise BodyError("typed body contains trailing bytes")


@dataclass(frozen=True)
class ConfigIdentity:
    identity: str
    revision: str
    sha256: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "identity", _exact_text(self.identity, "config identity"))
        object.__setattr__(self, "revision", _exact_text(self.revision, "config revision"))
        object.__setattr__(
            self, "sha256", _sha256(self.sha256, "config SHA-256", allow_zero=False)
        )


@dataclass(frozen=True)
class Hello:
    endpoint_id: str
    role: EndpointRole
    supported_major: int
    minimum_minor: int
    maximum_minor: int
    required_capabilities: Capability
    offered_capabilities: Capability
    minimum_rate_hz: int
    maximum_rate_hz: int
    preferred_rate_hz: int
    maximum_payload_size: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint_id", _exact_text(self.endpoint_id, "endpoint_id"))
        _enum(self.role, EndpointRole, "role")
        _int(self.supported_major, 1, 0xFF, "supported_major")
        _int(self.minimum_minor, 0, 0xFF, "minimum_minor")
        _int(self.maximum_minor, 0, 0xFF, "maximum_minor")
        if self.minimum_minor > self.maximum_minor:
            raise ValidationError("minimum_minor must not exceed maximum_minor")
        required = _capability(self.required_capabilities, "required_capabilities")
        offered = _capability(self.offered_capabilities, "offered_capabilities")
        if required & ~offered:
            raise ValidationError("required capabilities must also be offered")
        _int(self.minimum_rate_hz, 1, MAX_CONTROL_RATE_HZ, "minimum_rate_hz")
        _int(self.maximum_rate_hz, 1, MAX_CONTROL_RATE_HZ, "maximum_rate_hz")
        _int(self.preferred_rate_hz, 1, MAX_CONTROL_RATE_HZ, "preferred_rate_hz")
        if not self.minimum_rate_hz <= self.preferred_rate_hz <= self.maximum_rate_hz:
            raise ValidationError("preferred_rate_hz must be within the advertised range")
        if self.minimum_rate_hz > self.maximum_rate_hz:
            raise ValidationError("minimum_rate_hz must not exceed maximum_rate_hz")
        _int(self.maximum_payload_size, 1, MAX_PAYLOAD_SIZE, "maximum_payload_size")


@dataclass(frozen=True)
class Capabilities:
    accepted: bool
    selected_major: int
    selected_minor: int
    selected_capabilities: Capability
    selected_rate_hz: int
    selected_payload_size: int
    rejection: NegotiationRejection

    def __post_init__(self) -> None:
        _bool(self.accepted, "accepted")
        _int(self.selected_major, 0, 0xFF, "selected_major")
        _int(self.selected_minor, 0, 0xFF, "selected_minor")
        selected = _capability(self.selected_capabilities, "selected_capabilities")
        _int(self.selected_rate_hz, 0, MAX_CONTROL_RATE_HZ, "selected_rate_hz")
        _int(self.selected_payload_size, 0, MAX_PAYLOAD_SIZE, "selected_payload_size")
        _enum(self.rejection, NegotiationRejection, "rejection")
        if self.accepted:
            if self.rejection is not NegotiationRejection.NONE:
                raise ValidationError("accepted negotiation must have rejection NONE")
            if self.selected_major != VERSION_MAJOR:
                raise ValidationError("accepted negotiation must select V1 major")
            if self.selected_minor > VERSION_MINOR:
                raise ValidationError("accepted negotiation selected an unsupported minor")
            if selected == Capability.NONE or self.selected_rate_hz == 0:
                raise ValidationError("accepted negotiation must select capabilities and rate")
            if self.selected_payload_size < MIN_NEGOTIATED_PAYLOAD_SIZE:
                raise ValidationError("accepted negotiation payload is too small")
        else:
            if self.rejection is NegotiationRejection.NONE:
                raise ValidationError("rejected negotiation must state a reason")
            if any(
                (
                    self.selected_major,
                    self.selected_minor,
                    int(selected),
                    self.selected_rate_hz,
                    self.selected_payload_size,
                )
            ):
                raise ValidationError("rejected negotiation must not select parameters")


def _rejected_negotiation(reason: NegotiationRejection) -> Capabilities:
    return Capabilities(False, 0, 0, Capability.NONE, 0, 0, reason)


def negotiate(local: Hello, peer: Hello) -> Capabilities:
    """Select a symmetric V1 contract, or return an explicit fail-closed result."""

    if not isinstance(local, Hello) or not isinstance(peer, Hello):
        raise ValidationError("negotiate requires two Hello bodies")
    if local.supported_major != peer.supported_major or local.supported_major != VERSION_MAJOR:
        return _rejected_negotiation(NegotiationRejection.MAJOR_VERSION_MISMATCH)
    minor_low = max(local.minimum_minor, peer.minimum_minor)
    minor_high = min(local.maximum_minor, peer.maximum_minor, VERSION_MINOR)
    if minor_low > minor_high:
        return _rejected_negotiation(NegotiationRejection.MINOR_VERSION_MISMATCH)
    if (
        local.required_capabilities & ~peer.offered_capabilities
        or peer.required_capabilities & ~local.offered_capabilities
    ):
        return _rejected_negotiation(NegotiationRejection.CAPABILITY_MISMATCH)
    selected_capabilities = local.offered_capabilities & peer.offered_capabilities
    rate_low = max(local.minimum_rate_hz, peer.minimum_rate_hz)
    rate_high = min(local.maximum_rate_hz, peer.maximum_rate_hz)
    if rate_low > rate_high:
        return _rejected_negotiation(NegotiationRejection.RATE_MISMATCH)
    selected_payload = min(local.maximum_payload_size, peer.maximum_payload_size)
    if selected_payload < MIN_NEGOTIATED_PAYLOAD_SIZE:
        return _rejected_negotiation(NegotiationRejection.PAYLOAD_LIMIT_MISMATCH)
    selected_rate = max(
        rate_low,
        min(local.preferred_rate_hz, peer.preferred_rate_hz, rate_high),
    )
    return Capabilities(
        True,
        VERSION_MAJOR,
        minor_high,
        selected_capabilities,
        selected_rate,
        selected_payload,
        NegotiationRejection.NONE,
    )


_COMMAND_VALUE_NAMES = (
    "position_rad",
    "velocity_rad_s",
    "effort_nm",
    "current_q_a",
    "stiffness_nm_per_rad",
    "damping_nm_s_per_rad",
)
_COMMAND_VALUE_BITS = {name: 1 << index for index, name in enumerate(_COMMAND_VALUE_NAMES)}
_COMMAND_REQUIRED = {
    CommandMode.DISABLE: frozenset(),
    CommandMode.POSITION: frozenset({"position_rad"}),
    CommandMode.VELOCITY: frozenset({"velocity_rad_s"}),
    CommandMode.EFFORT: frozenset({"effort_nm"}),
    CommandMode.CURRENT_Q: frozenset({"current_q_a"}),
    CommandMode.IMPEDANCE: frozenset(
        {
            "position_rad",
            "velocity_rad_s",
            "stiffness_nm_per_rad",
            "damping_nm_s_per_rad",
        }
    ),
}
_COMMAND_ALLOWED = {
    CommandMode.DISABLE: frozenset(),
    CommandMode.POSITION: frozenset({"position_rad", "velocity_rad_s", "effort_nm"}),
    CommandMode.VELOCITY: frozenset({"velocity_rad_s", "effort_nm"}),
    CommandMode.EFFORT: frozenset({"effort_nm"}),
    CommandMode.CURRENT_Q: frozenset({"current_q_a"}),
    CommandMode.IMPEDANCE: frozenset(
        {
            "position_rad",
            "velocity_rad_s",
            "effort_nm",
            "stiffness_nm_per_rad",
            "damping_nm_s_per_rad",
        }
    ),
}


@dataclass(frozen=True)
class Command:
    canonical_actuator_id: str
    config: ConfigIdentity
    source_identity: str
    lease_id: str
    lease_owner: str
    lease_sequence: int
    lease_expiry_monotonic_ns: int
    mode: CommandMode
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
            _exact_text(self.canonical_actuator_id, "canonical_actuator_id"),
        )
        if not isinstance(self.config, ConfigIdentity):
            raise ValidationError("config must be ConfigIdentity")
        object.__setattr__(
            self,
            "source_identity",
            _exact_text(self.source_identity, "source_identity"),
        )
        object.__setattr__(self, "lease_id", _exact_text(self.lease_id, "lease_id"))
        object.__setattr__(self, "lease_owner", _exact_text(self.lease_owner, "lease_owner"))
        _int(self.lease_sequence, 1, 0xFFFFFFFFFFFFFFFF, "lease_sequence")
        _int(
            self.lease_expiry_monotonic_ns,
            1,
            0xFFFFFFFFFFFFFFFF,
            "lease_expiry_monotonic_ns",
        )
        _enum(self.mode, CommandMode, "mode")
        _bool(self.enable_requested, "enable_requested")
        present = set()
        for name in _COMMAND_VALUE_NAMES:
            value = _optional_finite(getattr(self, name), name)
            object.__setattr__(self, name, value)
            if value is not None:
                present.add(name)
        missing = _COMMAND_REQUIRED[self.mode] - present
        unexpected = present - _COMMAND_ALLOWED[self.mode]
        if missing:
            raise ValidationError(f"{self.mode.name} command is missing {sorted(missing)!r}")
        if unexpected:
            raise ValidationError(
                f"{self.mode.name} command has forbidden values {sorted(unexpected)!r}"
            )
        if self.mode is CommandMode.DISABLE and self.enable_requested:
            raise ValidationError("DISABLE command cannot request enable")
        if self.mode is not CommandMode.DISABLE and not self.enable_requested:
            raise ValidationError("active command modes must request enable")


_STATE_VALUE_NAMES = (
    "position_rad",
    "velocity_rad_s",
    "effort_nm",
    "current_q_a",
    "temperature_c",
    "voltage_v",
)
_STATE_VALUE_BITS = {name: 1 << index for index, name in enumerate(_STATE_VALUE_NAMES)}
_STATE_NATIVE_STATUS_BIT = 1 << 6
_STATE_NATIVE_FAULT_BIT = 1 << 7


@dataclass(frozen=True)
class State:
    canonical_actuator_id: str
    config: ConfigIdentity
    sample_monotonic_ns: int
    sample_age_ns: int
    validity: SampleValidity
    connectivity: Connectivity
    drive_health: DriveHealth
    bus_health: BusHealth
    native_response: NativeResponseState
    fault_code: str
    safety_state: SafetyState
    position_rad: Optional[float] = None
    velocity_rad_s: Optional[float] = None
    effort_nm: Optional[float] = None
    current_q_a: Optional[float] = None
    temperature_c: Optional[float] = None
    voltage_v: Optional[float] = None
    native_status_code: Optional[int] = None
    native_fault_mask: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "canonical_actuator_id",
            _exact_text(self.canonical_actuator_id, "canonical_actuator_id"),
        )
        if not isinstance(self.config, ConfigIdentity):
            raise ValidationError("config must be ConfigIdentity")
        _int(self.sample_monotonic_ns, 0, 0xFFFFFFFFFFFFFFFF, "sample_monotonic_ns")
        _int(self.sample_age_ns, 0, 0xFFFFFFFFFFFFFFFF, "sample_age_ns")
        _enum(self.validity, SampleValidity, "validity")
        _enum(self.connectivity, Connectivity, "connectivity")
        _enum(self.drive_health, DriveHealth, "drive_health")
        _enum(self.bus_health, BusHealth, "bus_health")
        _enum(self.native_response, NativeResponseState, "native_response")
        object.__setattr__(
            self,
            "fault_code",
            _status_code(self.fault_code, "fault_code", allow_none=True),
        )
        _enum(self.safety_state, SafetyState, "safety_state")
        for name in _STATE_VALUE_NAMES:
            object.__setattr__(self, name, _optional_finite(getattr(self, name), name))
        if self.native_status_code is not None:
            _int(self.native_status_code, 0, 0xFFFFFFFF, "native_status_code")
        if self.native_fault_mask is not None:
            _int(self.native_fault_mask, 0, 0xFFFFFFFF, "native_fault_mask")


@dataclass(frozen=True)
class Disposition:
    request_session_id: int
    request_sequence: int
    canonical_actuator_id: str
    phase: DispositionPhase
    phase_monotonic_ns: int
    reason_code: str

    def __post_init__(self) -> None:
        _int(self.request_session_id, 1, 0xFFFFFFFFFFFFFFFF, "request_session_id")
        _int(self.request_sequence, 1, 0xFFFFFFFFFFFFFFFF, "request_sequence")
        object.__setattr__(
            self,
            "canonical_actuator_id",
            _exact_text(self.canonical_actuator_id, "canonical_actuator_id"),
        )
        _enum(self.phase, DispositionPhase, "phase")
        _int(self.phase_monotonic_ns, 0, 0xFFFFFFFFFFFFFFFF, "phase_monotonic_ns")
        object.__setattr__(
            self,
            "reason_code",
            _status_code(self.reason_code, "reason_code", allow_none=True),
        )
        if self.phase is DispositionPhase.REJECTED and self.reason_code == "NONE":
            raise ValidationError("REJECTED disposition must carry a reason")
        if self.phase is not DispositionPhase.REJECTED and self.reason_code != "NONE":
            raise ValidationError("non-rejected disposition reason must be NONE")


@dataclass(frozen=True)
class Fault:
    fault_code: str
    severity: FaultSeverity
    safety_state: SafetyState
    occurred_monotonic_ns: int
    related_sequence: int
    canonical_actuator_id: str
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "fault_code", _exact_text(self.fault_code, "fault_code"))
        _enum(self.severity, FaultSeverity, "severity")
        _enum(self.safety_state, SafetyState, "safety_state")
        _int(self.occurred_monotonic_ns, 0, 0xFFFFFFFFFFFFFFFF, "occurred_monotonic_ns")
        _int(self.related_sequence, 0, 0xFFFFFFFFFFFFFFFF, "related_sequence")
        if self.canonical_actuator_id:
            object.__setattr__(
                self,
                "canonical_actuator_id",
                _exact_text(self.canonical_actuator_id, "canonical_actuator_id"),
            )
        else:
            _text(self.canonical_actuator_id, "canonical_actuator_id", allow_empty=True)
        object.__setattr__(
            self,
            "description",
            _text(self.description, "description", allow_empty=True, maximum=MAX_DETAIL_BYTES),
        )


@dataclass(frozen=True)
class Heartbeat:
    endpoint_id: str
    role: EndpointRole
    link_health: LinkHealth
    safety_state: SafetyState
    uptime_ns: int
    last_received_sequence: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint_id", _exact_text(self.endpoint_id, "endpoint_id"))
        _enum(self.role, EndpointRole, "role")
        _enum(self.link_health, LinkHealth, "link_health")
        _enum(self.safety_state, SafetyState, "safety_state")
        _int(self.uptime_ns, 0, 0xFFFFFFFFFFFFFFFF, "uptime_ns")
        _int(self.last_received_sequence, 0, 0xFFFFFFFFFFFFFFFF, "last_received_sequence")


MessageBody = Union[Hello, Capabilities, Command, State, Disposition, Fault, Heartbeat]


@dataclass(frozen=True)
class Frame:
    message_type: MessageType
    flags: FrameFlag
    session_id: int
    sequence: int
    monotonic_ns: int
    config_sha256: bytes
    payload: bytes
    major: int = VERSION_MAJOR
    minor: int = VERSION_MINOR

    def __post_init__(self) -> None:
        _enum(self.message_type, MessageType, "message_type")
        if not isinstance(self.flags, FrameFlag) or int(self.flags) & ~int(KNOWN_FRAME_FLAGS):
            raise ValidationError("flags contain unknown bits")
        _int(self.session_id, 1, 0xFFFFFFFFFFFFFFFF, "session_id")
        _int(self.sequence, 1, 0xFFFFFFFFFFFFFFFF, "sequence")
        _int(self.monotonic_ns, 0, 0xFFFFFFFFFFFFFFFF, "monotonic_ns")
        object.__setattr__(
            self,
            "config_sha256",
            _sha256(self.config_sha256, "envelope config SHA-256", allow_zero=True),
        )
        if not isinstance(self.payload, bytes) or len(self.payload) > MAX_PAYLOAD_SIZE:
            raise ValidationError("payload must be bounded bytes")
        _int(self.major, 0, 0xFF, "major")
        _int(self.minor, 0, 0xFF, "minor")


def encode_frame(frame: Frame) -> bytes:
    if not isinstance(frame, Frame):
        raise ValidationError("encode_frame requires Frame")
    if frame.major != VERSION_MAJOR or frame.minor != VERSION_MINOR:
        raise FrameError("unsupported envelope version")
    header = HEADER_STRUCT.pack(
        MAGIC,
        frame.major,
        frame.minor,
        HEADER_SIZE,
        len(frame.payload),
        int(frame.message_type),
        int(frame.flags),
        0,
        frame.session_id,
        frame.sequence,
        frame.monotonic_ns,
        frame.config_sha256,
    )
    protected = header + frame.payload
    return protected + struct.pack(">I", crc32c(protected))


def decode_frame(data: bytes) -> Frame:
    if not isinstance(data, bytes):
        raise FrameError("frame must be bytes")
    if len(data) < HEADER_SIZE + CRC_SIZE:
        raise FrameError("frame is shorter than the fixed envelope")
    if len(data) > MAX_FRAME_SIZE:
        raise FrameError("frame exceeds MAX_FRAME_SIZE")
    (
        magic,
        major,
        minor,
        header_length,
        payload_length,
        message_type,
        flags,
        reserved,
        session_id,
        sequence,
        monotonic_ns,
        config_sha256,
    ) = HEADER_STRUCT.unpack_from(data)
    if magic != MAGIC:
        raise FrameError("bad magic")
    if major != VERSION_MAJOR or minor != VERSION_MINOR:
        raise FrameError("unsupported envelope version")
    if header_length != HEADER_SIZE:
        raise FrameError("unsupported header length")
    if payload_length > MAX_PAYLOAD_SIZE:
        raise FrameError("payload length exceeds MAX_PAYLOAD_SIZE")
    expected_length = HEADER_SIZE + payload_length + CRC_SIZE
    if len(data) != expected_length:
        raise FrameError("frame length does not match header payload length")
    if reserved != 0:
        raise FrameError("reserved header bits must be zero")
    if flags & ~int(KNOWN_FRAME_FLAGS):
        raise FrameError("unknown frame flags")
    try:
        typed_message = MessageType(message_type)
    except ValueError as exc:
        raise FrameError("unknown message type") from exc
    protected = data[:-CRC_SIZE]
    expected_crc = struct.unpack(">I", data[-CRC_SIZE:])[0]
    if crc32c(protected) != expected_crc:
        raise FrameError("CRC-32C mismatch")
    try:
        return Frame(
            typed_message,
            FrameFlag(flags),
            session_id,
            sequence,
            monotonic_ns,
            config_sha256,
            data[HEADER_SIZE:-CRC_SIZE],
            major,
            minor,
        )
    except ValidationError as exc:
        raise FrameError(str(exc)) from exc


def _write_config(writer: _Writer, config: ConfigIdentity) -> None:
    writer.text(config.identity)
    writer.text(config.revision)
    writer.fixed(config.sha256, 32)


def _read_config(reader: _Reader) -> ConfigIdentity:
    try:
        return ConfigIdentity(reader.text(), reader.text(), reader.take(32))
    except ValidationError as exc:
        raise BodyError(str(exc)) from exc


def _encode_hello(body: Hello) -> bytes:
    writer = _Writer()
    writer.text(body.endpoint_id)
    writer.u8(int(body.role))
    writer.u8(body.supported_major)
    writer.u8(body.minimum_minor)
    writer.u8(body.maximum_minor)
    writer.u64(int(body.required_capabilities))
    writer.u64(int(body.offered_capabilities))
    writer.u16(body.minimum_rate_hz)
    writer.u16(body.maximum_rate_hz)
    writer.u16(body.preferred_rate_hz)
    writer.u32(body.maximum_payload_size)
    return writer.finish()


def _decode_hello(reader: _Reader) -> Hello:
    try:
        body = Hello(
            reader.text(),
            EndpointRole(reader.u8()),
            reader.u8(),
            reader.u8(),
            reader.u8(),
            _decode_capability(reader.u64(), "required_capabilities"),
            _decode_capability(reader.u64(), "offered_capabilities"),
            reader.u16(),
            reader.u16(),
            reader.u16(),
            reader.u32(),
        )
    except (ValueError, ValidationError) as exc:
        raise BodyError(str(exc)) from exc
    reader.finish()
    return body


def _encode_capabilities(body: Capabilities) -> bytes:
    writer = _Writer()
    writer.boolean(body.accepted)
    writer.u8(body.selected_major)
    writer.u8(body.selected_minor)
    writer.u64(int(body.selected_capabilities))
    writer.u16(body.selected_rate_hz)
    writer.u32(body.selected_payload_size)
    writer.u8(int(body.rejection))
    return writer.finish()


def _decode_capabilities(reader: _Reader) -> Capabilities:
    try:
        body = Capabilities(
            reader.boolean(),
            reader.u8(),
            reader.u8(),
            _decode_capability(reader.u64(), "selected_capabilities"),
            reader.u16(),
            reader.u32(),
            NegotiationRejection(reader.u8()),
        )
    except (ValueError, ValidationError) as exc:
        raise BodyError(str(exc)) from exc
    reader.finish()
    return body


def _encode_command(body: Command) -> bytes:
    writer = _Writer()
    writer.text(body.canonical_actuator_id)
    _write_config(writer, body.config)
    writer.text(body.source_identity)
    writer.text(body.lease_id)
    writer.text(body.lease_owner)
    writer.u64(body.lease_sequence)
    writer.u64(body.lease_expiry_monotonic_ns)
    writer.u8(int(body.mode))
    writer.boolean(body.enable_requested)
    mask = sum(
        _COMMAND_VALUE_BITS[name]
        for name in _COMMAND_VALUE_NAMES
        if getattr(body, name) is not None
    )
    writer.u16(mask)
    for name in _COMMAND_VALUE_NAMES:
        value = getattr(body, name)
        if value is not None:
            writer.f64(value)
    return writer.finish()


def _decode_command(reader: _Reader) -> Command:
    actuator_id = reader.text()
    config = _read_config(reader)
    source_identity = reader.text()
    lease_id = reader.text()
    lease_owner = reader.text()
    lease_sequence = reader.u64()
    lease_expiry = reader.u64()
    try:
        mode = CommandMode(reader.u8())
    except ValueError as exc:
        raise BodyError("unknown command mode") from exc
    enable = reader.boolean()
    mask = reader.u16()
    known_mask = sum(_COMMAND_VALUE_BITS.values())
    if mask & ~known_mask:
        raise BodyError("command value mask contains unknown bits")
    values: Dict[str, Optional[float]] = {}
    for name in _COMMAND_VALUE_NAMES:
        values[name] = reader.f64() if mask & _COMMAND_VALUE_BITS[name] else None
    reader.finish()
    try:
        return Command(
            actuator_id,
            config,
            source_identity,
            lease_id,
            lease_owner,
            lease_sequence,
            lease_expiry,
            mode,
            enable,
            **values,
        )
    except ValidationError as exc:
        raise BodyError(str(exc)) from exc


def _encode_state(body: State) -> bytes:
    writer = _Writer()
    writer.text(body.canonical_actuator_id)
    _write_config(writer, body.config)
    writer.u64(body.sample_monotonic_ns)
    writer.u64(body.sample_age_ns)
    writer.u8(int(body.validity))
    writer.u8(int(body.connectivity))
    writer.u8(int(body.drive_health))
    writer.u8(int(body.bus_health))
    writer.u8(int(body.native_response))
    writer.text(body.fault_code)
    writer.u8(int(body.safety_state))
    mask = sum(
        _STATE_VALUE_BITS[name]
        for name in _STATE_VALUE_NAMES
        if getattr(body, name) is not None
    )
    if body.native_status_code is not None:
        mask |= _STATE_NATIVE_STATUS_BIT
    if body.native_fault_mask is not None:
        mask |= _STATE_NATIVE_FAULT_BIT
    writer.u16(mask)
    for name in _STATE_VALUE_NAMES:
        value = getattr(body, name)
        if value is not None:
            writer.f64(value)
    if body.native_status_code is not None:
        writer.u32(body.native_status_code)
    if body.native_fault_mask is not None:
        writer.u32(body.native_fault_mask)
    return writer.finish()


def _decode_state(reader: _Reader) -> State:
    actuator_id = reader.text()
    config = _read_config(reader)
    sample_time = reader.u64()
    sample_age = reader.u64()
    try:
        validity = SampleValidity(reader.u8())
        connectivity = Connectivity(reader.u8())
        drive_health = DriveHealth(reader.u8())
        bus_health = BusHealth(reader.u8())
        native_response = NativeResponseState(reader.u8())
    except ValueError as exc:
        raise BodyError("unknown state enumeration") from exc
    fault_code = reader.text()
    try:
        safety_state = SafetyState(reader.u8())
    except ValueError as exc:
        raise BodyError("unknown safety state") from exc
    mask = reader.u16()
    known_mask = sum(_STATE_VALUE_BITS.values()) | _STATE_NATIVE_STATUS_BIT | _STATE_NATIVE_FAULT_BIT
    if mask & ~known_mask:
        raise BodyError("state field mask contains unknown bits")
    values: Dict[str, Optional[float]] = {}
    for name in _STATE_VALUE_NAMES:
        values[name] = reader.f64() if mask & _STATE_VALUE_BITS[name] else None
    native_status = reader.u32() if mask & _STATE_NATIVE_STATUS_BIT else None
    native_fault = reader.u32() if mask & _STATE_NATIVE_FAULT_BIT else None
    reader.finish()
    try:
        return State(
            actuator_id,
            config,
            sample_time,
            sample_age,
            validity,
            connectivity,
            drive_health,
            bus_health,
            native_response,
            fault_code,
            safety_state,
            native_status_code=native_status,
            native_fault_mask=native_fault,
            **values,
        )
    except ValidationError as exc:
        raise BodyError(str(exc)) from exc


def _encode_disposition(body: Disposition) -> bytes:
    writer = _Writer()
    writer.u64(body.request_session_id)
    writer.u64(body.request_sequence)
    writer.text(body.canonical_actuator_id)
    writer.u8(int(body.phase))
    writer.u64(body.phase_monotonic_ns)
    writer.text(body.reason_code)
    return writer.finish()


def _decode_disposition(reader: _Reader) -> Disposition:
    try:
        body = Disposition(
            reader.u64(),
            reader.u64(),
            reader.text(),
            DispositionPhase(reader.u8()),
            reader.u64(),
            reader.text(),
        )
    except (ValueError, ValidationError) as exc:
        raise BodyError(str(exc)) from exc
    reader.finish()
    return body


def _encode_fault(body: Fault) -> bytes:
    writer = _Writer()
    writer.text(body.fault_code)
    writer.u8(int(body.severity))
    writer.u8(int(body.safety_state))
    writer.u64(body.occurred_monotonic_ns)
    writer.u64(body.related_sequence)
    writer.text(body.canonical_actuator_id, allow_empty=True)
    writer.text(body.description, allow_empty=True, maximum=MAX_DETAIL_BYTES)
    return writer.finish()


def _decode_fault(reader: _Reader) -> Fault:
    try:
        body = Fault(
            reader.text(),
            FaultSeverity(reader.u8()),
            SafetyState(reader.u8()),
            reader.u64(),
            reader.u64(),
            reader.text(allow_empty=True),
            reader.text(allow_empty=True, maximum=MAX_DETAIL_BYTES),
        )
    except (ValueError, ValidationError) as exc:
        raise BodyError(str(exc)) from exc
    reader.finish()
    return body


def _encode_heartbeat(body: Heartbeat) -> bytes:
    writer = _Writer()
    writer.text(body.endpoint_id)
    writer.u8(int(body.role))
    writer.u8(int(body.link_health))
    writer.u8(int(body.safety_state))
    writer.u64(body.uptime_ns)
    writer.u64(body.last_received_sequence)
    return writer.finish()


def _decode_heartbeat(reader: _Reader) -> Heartbeat:
    try:
        body = Heartbeat(
            reader.text(),
            EndpointRole(reader.u8()),
            LinkHealth(reader.u8()),
            SafetyState(reader.u8()),
            reader.u64(),
            reader.u64(),
        )
    except (ValueError, ValidationError) as exc:
        raise BodyError(str(exc)) from exc
    reader.finish()
    return body


_BODY_ENCODERS = {
    Hello: (MessageType.HELLO, _encode_hello),
    Capabilities: (MessageType.CAPABILITIES, _encode_capabilities),
    Command: (MessageType.COMMAND, _encode_command),
    State: (MessageType.STATE, _encode_state),
    Disposition: (MessageType.DISPOSITION, _encode_disposition),
    Fault: (MessageType.FAULT, _encode_fault),
    Heartbeat: (MessageType.HEARTBEAT, _encode_heartbeat),
}
_BODY_DECODERS = {
    MessageType.HELLO: _decode_hello,
    MessageType.CAPABILITIES: _decode_capabilities,
    MessageType.COMMAND: _decode_command,
    MessageType.STATE: _decode_state,
    MessageType.DISPOSITION: _decode_disposition,
    MessageType.FAULT: _decode_fault,
    MessageType.HEARTBEAT: _decode_heartbeat,
}


def encode_message(
    body: MessageBody,
    *,
    session_id: int,
    sequence: int,
    monotonic_ns: int,
    config_sha256: bytes,
    flags: FrameFlag = FrameFlag.NONE,
) -> bytes:
    """Encode one typed body into a deterministic V1 frame."""

    entry = _BODY_ENCODERS.get(type(body))
    if entry is None:
        raise ValidationError("body is not a V1 typed message")
    message_type, encoder = entry
    checked_hash = _sha256(config_sha256, "envelope config SHA-256", allow_zero=True)
    if isinstance(body, (Command, State)) and body.config.sha256 != checked_hash:
        raise ValidationError("body config SHA-256 does not match envelope")
    if isinstance(body, Command) and body.lease_expiry_monotonic_ns <= monotonic_ns:
        raise ValidationError("command lease is expired at its envelope timestamp")
    if isinstance(body, State):
        if body.sample_monotonic_ns > monotonic_ns:
            raise ValidationError("state sample time is after its envelope timestamp")
        if monotonic_ns - body.sample_monotonic_ns != body.sample_age_ns:
            raise ValidationError("state sample_age_ns does not match envelope minus sample time")
    if isinstance(body, Disposition) and body.phase_monotonic_ns > monotonic_ns:
        raise ValidationError("disposition phase time is after its envelope timestamp")
    if isinstance(body, Fault) and body.occurred_monotonic_ns > monotonic_ns:
        raise ValidationError("fault occurrence is after its envelope timestamp")
    return encode_frame(
        Frame(
            message_type,
            flags,
            session_id,
            sequence,
            monotonic_ns,
            checked_hash,
            encoder(body),
        )
    )


def decode_message(frame: Frame) -> MessageBody:
    """Decode a known body and enforce its cross-envelope invariants."""

    if not isinstance(frame, Frame):
        raise BodyError("decode_message requires Frame")
    if frame.major != VERSION_MAJOR or frame.minor != VERSION_MINOR:
        raise BodyError("unsupported envelope version")
    decoder = _BODY_DECODERS[frame.message_type]
    body = decoder(_Reader(frame.payload))
    if isinstance(body, (Command, State)) and body.config.sha256 != frame.config_sha256:
        raise BodyError("body config SHA-256 does not match envelope")
    if isinstance(body, Command) and body.lease_expiry_monotonic_ns <= frame.monotonic_ns:
        raise BodyError("command lease is expired at its envelope timestamp")
    if isinstance(body, State):
        if body.sample_monotonic_ns > frame.monotonic_ns:
            raise BodyError("state sample time is after its envelope timestamp")
        if frame.monotonic_ns - body.sample_monotonic_ns != body.sample_age_ns:
            raise BodyError("state sample age is inconsistent with envelope time")
    if isinstance(body, Disposition) and body.phase_monotonic_ns > frame.monotonic_ns:
        raise BodyError("disposition phase time is after its envelope timestamp")
    if isinstance(body, Fault) and body.occurred_monotonic_ns > frame.monotonic_ns:
        raise BodyError("fault occurrence is after its envelope timestamp")
    return body


@dataclass(frozen=True)
class ParseErrorEvent:
    code: ParseErrorCode
    discarded_bytes: int
    detail: str


@dataclass(frozen=True)
class ParseBatch:
    frames: Tuple[Frame, ...]
    errors: Tuple[ParseErrorEvent, ...]
    discarded_bytes: int


class StreamParser:
    """Bounded incremental parser with magic/CRC resynchronization."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def reset(self) -> None:
        self._buffer.clear()

    def feed(self, data: bytes) -> ParseBatch:
        if not isinstance(data, bytes):
            raise ValidationError("parser feed must be bytes")
        if len(data) > MAX_FEED_SIZE:
            self.reset()
            raise BufferLimitError("one feed exceeds MAX_FEED_SIZE; parser reset")
        errors: List[ParseErrorEvent] = []
        discarded = 0
        overflow = len(self._buffer) + len(data) - MAX_BUFFER_SIZE
        if overflow > 0:
            del self._buffer[:overflow]
            discarded += overflow
            errors.append(
                ParseErrorEvent(
                    ParseErrorCode.BUFFER_OVERFLOW,
                    overflow,
                    "oldest buffered bytes discarded to preserve the hard memory bound",
                )
            )
        self._buffer.extend(data)
        frames_out: List[Frame] = []

        while self._buffer:
            magic_offset = self._buffer.find(MAGIC)
            if magic_offset < 0:
                keep = 0
                maximum_prefix = min(len(MAGIC) - 1, len(self._buffer))
                for candidate in range(maximum_prefix, 0, -1):
                    if self._buffer[-candidate:] == MAGIC[:candidate]:
                        keep = candidate
                        break
                count = len(self._buffer) - keep
                if count:
                    del self._buffer[:count]
                    discarded += count
                    errors.append(
                        ParseErrorEvent(
                            ParseErrorCode.NOISE_DISCARDED,
                            count,
                            "bytes before a possible magic prefix were discarded",
                        )
                    )
                break
            if magic_offset:
                del self._buffer[:magic_offset]
                discarded += magic_offset
                errors.append(
                    ParseErrorEvent(
                        ParseErrorCode.NOISE_DISCARDED,
                        magic_offset,
                        "noise before magic was discarded",
                    )
                )
            if len(self._buffer) < HEADER_SIZE:
                break

            unpacked = HEADER_STRUCT.unpack_from(self._buffer)
            header_length = unpacked[3]
            payload_length = unpacked[4]
            message_type = unpacked[5]
            flags = unpacked[6]
            reserved = unpacked[7]
            structurally_valid = (
                unpacked[0] == MAGIC
                and unpacked[1] == VERSION_MAJOR
                and unpacked[2] == VERSION_MINOR
                and header_length == HEADER_SIZE
                and payload_length <= MAX_PAYLOAD_SIZE
                and message_type in MessageType._value2member_map_
                and not flags & ~int(KNOWN_FRAME_FLAGS)
                and reserved == 0
                and unpacked[8] != 0
                and unpacked[9] != 0
            )
            if not structurally_valid:
                del self._buffer[0]
                discarded += 1
                errors.append(
                    ParseErrorEvent(
                        ParseErrorCode.INVALID_HEADER,
                        1,
                        "candidate magic had an invalid bounded header",
                    )
                )
                continue
            total_length = HEADER_SIZE + payload_length + CRC_SIZE
            if len(self._buffer) < total_length:
                break
            candidate = bytes(self._buffer[:total_length])
            try:
                frame = decode_frame(candidate)
            except FrameError as exc:
                del self._buffer[0]
                discarded += 1
                errors.append(
                    ParseErrorEvent(
                        ParseErrorCode.CRC_MISMATCH,
                        1,
                        str(exc),
                    )
                )
                continue
            del self._buffer[:total_length]
            frames_out.append(frame)

        return ParseBatch(tuple(frames_out), tuple(errors), discarded)


@dataclass(frozen=True)
class ReceiveResult:
    link_accepted: bool
    message: Optional[MessageBody]
    denial: Optional[ReceiveDenial]
    detail: str
    motion_authorized: bool = False

    def __post_init__(self) -> None:
        if self.motion_authorized:
            raise ValidationError("host-link receipt can never authorize motion")


class SessionReceiver:
    """Established-session ordering/config gate placed before command exposure."""

    def __init__(
        self,
        *,
        active_session_id: int,
        active_config_sha256: bytes,
        negotiation: Capabilities,
        initial_sequence: int = 0,
        initial_monotonic_ns: int = 0,
    ) -> None:
        self._session_id = _int(
            active_session_id, 1, 0xFFFFFFFFFFFFFFFF, "active_session_id"
        )
        self._config_sha256 = _sha256(
            active_config_sha256, "active_config_sha256", allow_zero=False
        )
        if not isinstance(negotiation, Capabilities) or not negotiation.accepted:
            raise ValidationError("SessionReceiver requires accepted negotiation")
        if negotiation.selected_major != VERSION_MAJOR:
            raise ValidationError("negotiated major is not V1")
        if negotiation.selected_capabilities & MANDATORY_CAPABILITIES != MANDATORY_CAPABILITIES:
            raise ValidationError("negotiation lacks mandatory V1 capabilities")
        self._last_sequence = _int(
            initial_sequence, 0, 0xFFFFFFFFFFFFFFFF, "initial_sequence"
        )
        self._last_monotonic_ns = _int(
            initial_monotonic_ns,
            0,
            0xFFFFFFFFFFFFFFFF,
            "initial_monotonic_ns",
        )

    @property
    def active_session_id(self) -> int:
        return self._session_id

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    def receive(self, frame: Frame, *, now_monotonic_ns: Optional[int] = None) -> ReceiveResult:
        if not isinstance(frame, Frame):
            raise ValidationError("receive requires Frame")
        if frame.major != VERSION_MAJOR or frame.minor != VERSION_MINOR:
            return ReceiveResult(
                False,
                None,
                ReceiveDenial.UNSUPPORTED_ENVELOPE,
                "frame envelope version is not the negotiated V1 version",
            )
        if frame.session_id != self._session_id:
            return ReceiveResult(
                False,
                None,
                ReceiveDenial.PREVIOUS_OR_UNKNOWN_SESSION,
                "frame session is not the explicitly active negotiated session",
            )
        if frame.sequence == self._last_sequence:
            return ReceiveResult(
                False, None, ReceiveDenial.DUPLICATE_SEQUENCE, "sequence was already accepted"
            )
        if frame.sequence < self._last_sequence:
            return ReceiveResult(
                False, None, ReceiveDenial.REORDERED_SEQUENCE, "sequence precedes replay window"
            )
        if frame.monotonic_ns < self._last_monotonic_ns:
            return ReceiveResult(
                False,
                None,
                ReceiveDenial.NONMONOTONIC_TIMESTAMP,
                "frame monotonic timestamp moved backward",
            )
        if frame.config_sha256 != self._config_sha256:
            return ReceiveResult(
                False,
                None,
                ReceiveDenial.CONFIG_MISMATCH,
                "envelope configuration hash is not active",
            )
        try:
            body = decode_message(frame)
        except BodyError as exc:
            return ReceiveResult(False, None, ReceiveDenial.MALFORMED_BODY, str(exc))
        evaluation_time = frame.monotonic_ns
        if now_monotonic_ns is not None:
            evaluation_time = _int(
                now_monotonic_ns, 0, 0xFFFFFFFFFFFFFFFF, "now_monotonic_ns"
            )
            if evaluation_time < frame.monotonic_ns:
                raise ValidationError("now_monotonic_ns precedes the frame timestamp")
        if isinstance(body, Command) and body.lease_expiry_monotonic_ns <= evaluation_time:
            return ReceiveResult(
                False,
                None,
                ReceiveDenial.EXPIRED_COMMAND,
                "command lease is expired at receiver evaluation time",
            )
        self._last_sequence = frame.sequence
        self._last_monotonic_ns = frame.monotonic_ns
        return ReceiveResult(
            True,
            body,
            None,
            "link integrity/order/config checks passed; gateway admission is still required",
        )


__all__ = [
    "BodyError",
    "BufferLimitError",
    "CRC_SIZE",
    "Capability",
    "Capabilities",
    "Command",
    "CommandMode",
    "ConfigIdentity",
    "Connectivity",
    "BusHealth",
    "Disposition",
    "DispositionPhase",
    "DriveHealth",
    "EndpointRole",
    "Fault",
    "FaultSeverity",
    "Frame",
    "FrameError",
    "FrameFlag",
    "HEADER_SIZE",
    "Heartbeat",
    "Hello",
    "HostLinkError",
    "LinkHealth",
    "MAGIC",
    "MANDATORY_CAPABILITIES",
    "MAX_BUFFER_SIZE",
    "MAX_FEED_SIZE",
    "MAX_FRAME_SIZE",
    "MAX_PAYLOAD_SIZE",
    "MessageBody",
    "MessageType",
    "NativeResponseState",
    "NegotiationRejection",
    "ParseBatch",
    "ParseErrorCode",
    "ParseErrorEvent",
    "ReceiveDenial",
    "ReceiveResult",
    "SafetyState",
    "SampleValidity",
    "SessionReceiver",
    "State",
    "StreamParser",
    "ValidationError",
    "VERSION_MAJOR",
    "VERSION_MINOR",
    "ZERO_SHA256",
    "crc32c",
    "decode_frame",
    "decode_message",
    "encode_frame",
    "encode_message",
    "negotiate",
    "sha256_from_hex",
    "sha256_to_hex",
]
