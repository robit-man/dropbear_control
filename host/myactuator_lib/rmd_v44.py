"""Official-source MYACTUATOR classic-CAN V4.4 codec (offline core).

This module implements only the command surface whose byte layout is directly
evidenced by ``CAN BUS Motor Motion Protocol V4.4 260520.pdf``.  The source PDF
has SHA-256 ``15731a29c60771f0066fa0b2c7a7609de76edc53fbc8757035d2389d7a5dc3d2``.

Important: protocol layout evidence is not evidence that a particular motor or
firmware revision implements it.  Applicability remains unverified and an
independent capability/safety policy must authorize all actuation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import IntEnum
from typing import Optional, Tuple, Union


APPLICABILITY_VERIFIED = False
SOURCE_EDITION = "V4.4-260520"
SOURCE_SHA256 = "15731a29c60771f0066fa0b2c7a7609de76edc53fbc8757035d2389d7a5dc3d2"

CAN_BITRATE = 1_000_000
REQUEST_BASE_ID = 0x140
RESPONSE_BASE_ID = 0x240
MIN_MOTOR_ID = 1
MAX_MOTOR_ID = 32
FRAME_DLC = 8

KNOWN_ERROR_MASK = (
    0x0002 | 0x0004 | 0x0008 | 0x0010 | 0x0040 | 0x0080
    | 0x0100 | 0x0800 | 0x1000 | 0x2000 | 0x4000
)

ERROR_FLAGS = {
    0x0002: "motor_stall",
    0x0004: "undervoltage",
    0x0008: "overvoltage",
    0x0010: "phase_overcurrent",
    0x0040: "power_overrun",
    0x0080: "calibration_parameter_error",
    0x0100: "overspeed",
    0x0800: "component_overtemperature",
    0x1000: "motor_overtemperature",
    0x2000: "encoder_calibration_error",
    0x4000: "encoder_data_error",
}


class CodecError(ValueError):
    """A frame or typed value violates the evidenced protocol contract."""


class Command(IntEnum):
    OPERATING_MODE = 0x70
    BRAKE_RELEASE = 0x77
    BRAKE_LOCK = 0x78
    SHUTDOWN = 0x80
    STOP = 0x81
    READ_MULTI_TURN_ANGLE = 0x92
    READ_SINGLE_TURN_ANGLE = 0x94
    READ_STATUS_1 = 0x9A
    READ_STATUS_2 = 0x9C
    READ_STATUS_3 = 0x9D
    IQ_CONTROL = 0xA1
    SPEED_CONTROL = 0xA2
    ABSOLUTE_POSITION = 0xA4


class OperatingMode(IntEnum):
    CURRENT = 0x01
    SPEED = 0x02
    POSITION = 0x03


ZERO_PAYLOAD_COMMANDS = frozenset(
    {
        Command.OPERATING_MODE,
        Command.BRAKE_RELEASE,
        Command.BRAKE_LOCK,
        Command.SHUTDOWN,
        Command.STOP,
        Command.READ_MULTI_TURN_ANGLE,
        Command.READ_SINGLE_TURN_ANGLE,
        Command.READ_STATUS_1,
        Command.READ_STATUS_2,
        Command.READ_STATUS_3,
    }
)

ECHO_COMMANDS = frozenset(
    {Command.BRAKE_RELEASE, Command.BRAKE_LOCK, Command.SHUTDOWN, Command.STOP}
)

MOTION_STATUS_COMMANDS = frozenset(
    {Command.READ_STATUS_2, Command.IQ_CONTROL, Command.SPEED_CONTROL, Command.ABSOLUTE_POSITION}
)


@dataclass(frozen=True)
class CanFrame:
    arbitration_id: int
    data: bytes
    is_extended: bool = False
    is_remote: bool = False

    @property
    def dlc(self) -> int:
        return len(self.data)


@dataclass(frozen=True)
class DecodedRequest:
    motor_id: int
    command: Command
    iq_raw: Optional[int] = None
    max_torque_percent_raw: Optional[int] = None
    speed_raw: Optional[int] = None
    max_speed_raw: Optional[int] = None
    angle_raw: Optional[int] = None


@dataclass(frozen=True)
class EchoResponse:
    motor_id: int
    command: Command


@dataclass(frozen=True)
class AngleResponse:
    motor_id: int
    command: Command
    angle_raw: int
    angle_degrees: Decimal


@dataclass(frozen=True)
class Status1Response:
    motor_id: int
    motor_temperature_c: int
    mos_temperature_raw: int
    brake_command_released: bool
    voltage_raw: int
    voltage_v: Decimal
    error_mask: int
    active_errors: Tuple[str, ...]
    unknown_error_bits: int


@dataclass(frozen=True)
class MotionStatusResponse:
    motor_id: int
    command: Command
    motor_temperature_c: int
    iq_raw: int
    iq_a: Decimal
    output_speed_raw: int
    output_speed_dps: Decimal
    output_angle_raw: int
    output_angle_degrees: Decimal


@dataclass(frozen=True)
class PhaseStatusResponse:
    motor_id: int
    motor_temperature_c: int
    phase_a_raw: int
    phase_b_raw: int
    phase_c_raw: int
    phase_a_a: Decimal
    phase_b_a: Decimal
    phase_c_a: Decimal


@dataclass(frozen=True)
class OperatingModeResponse:
    motor_id: int
    mode: OperatingMode


DecodedResponse = Union[
    EchoResponse,
    AngleResponse,
    Status1Response,
    MotionStatusResponse,
    PhaseStatusResponse,
    OperatingModeResponse,
]


def _require_int(value: int, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CodecError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise CodecError(f"{label} must be in [{minimum}, {maximum}], got {value}")
    return value


def validate_motor_id(motor_id: int) -> int:
    return _require_int(motor_id, MIN_MOTOR_ID, MAX_MOTOR_ID, "motor_id")


def request_arbitration_id(motor_id: int) -> int:
    return REQUEST_BASE_ID + validate_motor_id(motor_id)


def response_arbitration_id(motor_id: int) -> int:
    return RESPONSE_BASE_ID + validate_motor_id(motor_id)


def _command(value: Union[int, Command]) -> Command:
    if isinstance(value, bool):
        raise CodecError("command must be a supported command byte")
    try:
        return Command(value)
    except (TypeError, ValueError) as exc:
        raise CodecError(f"unsupported command: {value!r}") from exc


def _le_i16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little", signed=True)


def _le_u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little", signed=False)


def _le_i32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little", signed=True)


def _i8(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def _put_i16(value: int) -> bytes:
    return _require_int(value, -(1 << 15), (1 << 15) - 1, "int16 value").to_bytes(
        2, "little", signed=True
    )


def _put_i32(value: int) -> bytes:
    return _require_int(value, -(1 << 31), (1 << 31) - 1, "int32 value").to_bytes(
        4, "little", signed=True
    )


def _put_u16(value: int) -> bytes:
    return _require_int(value, 0, (1 << 16) - 1, "uint16 value").to_bytes(
        2, "little", signed=False
    )


def _scaled_raw(value: object, scale: str, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool):
        raise CodecError(f"{label} must be a finite numeric value")
    try:
        physical = Decimal(str(value))
        raw_decimal = physical / Decimal(scale)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CodecError(f"{label} must be a finite numeric value") from exc
    if not physical.is_finite() or not raw_decimal.is_finite():
        raise CodecError(f"{label} must be finite")
    integral = raw_decimal.to_integral_value()
    if raw_decimal != integral:
        raise CodecError(f"{label} must lie exactly on the {scale} unit wire grid")
    return _require_int(int(integral), minimum, maximum, f"{label} raw value")


def _make_request(motor_id: int, payload: bytes) -> CanFrame:
    if len(payload) != FRAME_DLC:
        raise CodecError("internal request payload must be exactly 8 bytes")
    return CanFrame(request_arbitration_id(motor_id), bytes(payload))


def encode_request(motor_id: int, command: Union[int, Command]) -> CanFrame:
    """Encode an evidenced request whose seven argument bytes are all zero."""
    cmd = _command(command)
    if cmd not in ZERO_PAYLOAD_COMMANDS:
        raise CodecError(f"{cmd.name} requires a command-specific encoder")
    return _make_request(motor_id, bytes((int(cmd), 0, 0, 0, 0, 0, 0, 0)))


def encode_iq_control_raw(motor_id: int, iq_raw: int) -> CanFrame:
    """Encode 0xA1 raw iq current; operational current authorization is external."""
    return _make_request(motor_id, b"\xA1\x00\x00\x00" + _put_i16(iq_raw) + b"\x00\x00")


def encode_iq_control_amps(motor_id: int, iq_a: object) -> CanFrame:
    raw = _scaled_raw(iq_a, "0.01", -(1 << 15), (1 << 15) - 1, "iq_a")
    return encode_iq_control_raw(motor_id, raw)


def encode_speed_control_raw(
    motor_id: int, speed_raw: int, *, max_torque_percent_raw: int = 0
) -> CanFrame:
    max_torque = _require_int(max_torque_percent_raw, 0, 255, "max_torque_percent_raw")
    return _make_request(
        motor_id,
        bytes((Command.SPEED_CONTROL, max_torque, 0, 0)) + _put_i32(speed_raw),
    )


def encode_speed_control_dps(
    motor_id: int, speed_dps: object, *, max_torque_percent_raw: int = 0
) -> CanFrame:
    raw = _scaled_raw(speed_dps, "0.01", -(1 << 31), (1 << 31) - 1, "speed_dps")
    return encode_speed_control_raw(
        motor_id, raw, max_torque_percent_raw=max_torque_percent_raw
    )


def encode_absolute_position_raw(
    motor_id: int, angle_raw: int, *, max_speed_raw: int
) -> CanFrame:
    return _make_request(
        motor_id,
        b"\xA4\x00" + _put_u16(max_speed_raw) + _put_i32(angle_raw),
    )


def encode_absolute_position_degrees(
    motor_id: int, angle_degrees: object, *, max_speed_dps: object
) -> CanFrame:
    angle_raw = _scaled_raw(
        angle_degrees, "0.01", -(1 << 31), (1 << 31) - 1, "angle_degrees"
    )
    max_speed_raw = _scaled_raw(max_speed_dps, "1", 0, (1 << 16) - 1, "max_speed_dps")
    return encode_absolute_position_raw(
        motor_id, angle_raw, max_speed_raw=max_speed_raw
    )


def _validate_wire(frame: CanFrame) -> bytes:
    if not isinstance(frame, CanFrame):
        raise CodecError("frame must be a CanFrame")
    if frame.is_extended:
        raise CodecError("V4.4 native frames must use standard 11-bit identifiers")
    if frame.is_remote:
        raise CodecError("V4.4 native frames must be data frames, not RTR")
    if isinstance(frame.arbitration_id, bool) or not isinstance(frame.arbitration_id, int):
        raise CodecError("arbitration_id must be an integer")
    if not 0 <= frame.arbitration_id <= 0x7FF:
        raise CodecError("arbitration_id must be an 11-bit standard identifier")
    if not isinstance(frame.data, bytes):
        raise CodecError("data must be immutable bytes")
    if len(frame.data) != FRAME_DLC:
        raise CodecError(f"DLC must be exactly {FRAME_DLC}, got {len(frame.data)}")
    return frame.data


def _decode_address(
    arbitration_id: int, base: int, expected_motor_id: Optional[int]
) -> int:
    motor_id = arbitration_id - base
    if not MIN_MOTOR_ID <= motor_id <= MAX_MOTOR_ID:
        direction = "request" if base == REQUEST_BASE_ID else "response"
        raise CodecError(f"invalid {direction} arbitration ID: {arbitration_id:#x}")
    if expected_motor_id is not None and motor_id != validate_motor_id(expected_motor_id):
        raise CodecError(
            f"unexpected motor response: expected {expected_motor_id}, got {motor_id}"
        )
    return motor_id


def _check_expected_command(command: Command, expected: Optional[Union[int, Command]]) -> None:
    if expected is not None:
        expected_command = _command(expected)
        if command != expected_command:
            raise CodecError(
                f"unexpected command response: expected {expected_command:#04x}, got {command:#04x}"
            )


def _all_zero(data: bytes, start: int, stop: int) -> bool:
    return all(value == 0 for value in data[start:stop])


def decode_request(
    frame: CanFrame,
    *,
    expected_motor_id: Optional[int] = None,
    expected_command: Optional[Union[int, Command]] = None,
) -> DecodedRequest:
    data = _validate_wire(frame)
    motor_id = _decode_address(frame.arbitration_id, REQUEST_BASE_ID, expected_motor_id)
    command = _command(data[0])
    _check_expected_command(command, expected_command)

    if command in ZERO_PAYLOAD_COMMANDS:
        if not _all_zero(data, 1, 8):
            raise CodecError("reserved request bytes must be zero")
        return DecodedRequest(motor_id, command)
    if command == Command.IQ_CONTROL:
        if not (_all_zero(data, 1, 4) and _all_zero(data, 6, 8)):
            raise CodecError("0xA1 reserved request bytes must be zero")
        return DecodedRequest(motor_id, command, iq_raw=_le_i16(data, 4))
    if command == Command.SPEED_CONTROL:
        if not _all_zero(data, 2, 4):
            raise CodecError("0xA2 reserved request bytes must be zero")
        return DecodedRequest(
            motor_id,
            command,
            max_torque_percent_raw=data[1],
            speed_raw=_le_i32(data, 4),
        )
    if command == Command.ABSOLUTE_POSITION:
        if data[1] != 0:
            raise CodecError("0xA4 reserved request byte must be zero")
        return DecodedRequest(
            motor_id,
            command,
            max_speed_raw=_le_u16(data, 2),
            angle_raw=_le_i32(data, 4),
        )
    raise CodecError(f"unsupported request command: {command:#04x}")


def decode_response(
    frame: CanFrame,
    *,
    expected_motor_id: Optional[int] = None,
    expected_command: Optional[Union[int, Command]] = None,
) -> DecodedResponse:
    data = _validate_wire(frame)
    motor_id = _decode_address(frame.arbitration_id, RESPONSE_BASE_ID, expected_motor_id)
    command = _command(data[0])
    _check_expected_command(command, expected_command)

    if command in ECHO_COMMANDS:
        if not _all_zero(data, 1, 8):
            raise CodecError("echo response contains nonzero reserved bytes")
        return EchoResponse(motor_id, command)

    if command in (Command.READ_MULTI_TURN_ANGLE, Command.READ_SINGLE_TURN_ANGLE):
        if not _all_zero(data, 1, 4):
            raise CodecError("angle response contains nonzero reserved bytes")
        angle_raw = _le_i32(data, 4)
        if command == Command.READ_SINGLE_TURN_ANGLE and not -18_000 <= angle_raw <= 18_000:
            raise CodecError("single-turn angle is outside the documented +/-180 degree range")
        return AngleResponse(motor_id, command, angle_raw, Decimal(angle_raw) * Decimal("0.01"))

    if command == Command.READ_STATUS_1:
        if data[3] not in (0, 1):
            raise CodecError("brake command state must be 0 or 1")
        error_mask = _le_u16(data, 6)
        return Status1Response(
            motor_id=motor_id,
            motor_temperature_c=_i8(data[1]),
            mos_temperature_raw=data[2],
            brake_command_released=bool(data[3]),
            voltage_raw=_le_u16(data, 4),
            voltage_v=Decimal(_le_u16(data, 4)) * Decimal("0.1"),
            error_mask=error_mask,
            active_errors=tuple(
                name for mask, name in ERROR_FLAGS.items() if error_mask & mask
            ),
            unknown_error_bits=error_mask & ~KNOWN_ERROR_MASK & 0xFFFF,
        )

    if command in MOTION_STATUS_COMMANDS:
        iq_raw = _le_i16(data, 2)
        speed_raw = _le_i16(data, 4)
        angle_raw = _le_i16(data, 6)
        return MotionStatusResponse(
            motor_id=motor_id,
            command=command,
            motor_temperature_c=_i8(data[1]),
            iq_raw=iq_raw,
            iq_a=Decimal(iq_raw) * Decimal("0.01"),
            output_speed_raw=speed_raw,
            output_speed_dps=Decimal(speed_raw),
            output_angle_raw=angle_raw,
            output_angle_degrees=Decimal(angle_raw),
        )

    if command == Command.READ_STATUS_3:
        phase_a = _le_i16(data, 2)
        phase_b = _le_i16(data, 4)
        phase_c = _le_i16(data, 6)
        return PhaseStatusResponse(
            motor_id,
            _i8(data[1]),
            phase_a,
            phase_b,
            phase_c,
            Decimal(phase_a) * Decimal("0.01"),
            Decimal(phase_b) * Decimal("0.01"),
            Decimal(phase_c) * Decimal("0.01"),
        )

    if command == Command.OPERATING_MODE:
        if not _all_zero(data, 1, 7):
            raise CodecError("operating-mode response contains nonzero reserved bytes")
        try:
            mode = OperatingMode(data[7])
        except ValueError as exc:
            raise CodecError(f"undocumented operating mode: {data[7]:#04x}") from exc
        return OperatingModeResponse(motor_id, mode)

    raise CodecError(f"unsupported response command: {command:#04x}")


__all__ = [
    "APPLICABILITY_VERIFIED",
    "CAN_BITRATE",
    "CanFrame",
    "CodecError",
    "Command",
    "DecodedRequest",
    "OperatingMode",
    "SOURCE_EDITION",
    "SOURCE_SHA256",
    "decode_request",
    "decode_response",
    "encode_absolute_position_degrees",
    "encode_absolute_position_raw",
    "encode_iq_control_amps",
    "encode_iq_control_raw",
    "encode_request",
    "encode_speed_control_dps",
    "encode_speed_control_raw",
    "request_arbitration_id",
    "response_arbitration_id",
    "validate_motor_id",
]
