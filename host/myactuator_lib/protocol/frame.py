"""Unified wire-protocol frame for MyActuator controllers.

Implements the 64-byte frame from ``contracts/PROTOCOLS_CONTRACT.md``
(section 3: "Message Frame Format"). This is the lowest layer of the host
library; the transport and device layers depend on it.

Frame layout (64 bytes), faithful to the contract diagram:

    Header (8):  Sync Word 0xAA55 LE (2) | Frame Type (1) | Header Seq (1) | Reserved (4)
    Motor ID (1)
    Command Type (1)
    Sequence Number (1)
    Payload (32)
    CRC-16/CCITT (2)
    Padding (19)

NOTE on CRC: the contract names "CRC-16/CCITT" but does not pin the exact
init/reflection parameters. We use the common CRC-16/CCITT-FALSE variant
(poly=0x1021, init=0xFFFF, non-reflected). The firmware side must use the
same parameters; reconcile against ``firmware/esp32`` before cross-talk.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum

SYNC_WORD = 0xAA55
FRAME_SIZE = 64
HEADER_SIZE = 8
PAYLOAD_SIZE = 32
PADDING_SIZE = 19
RESERVED_SIZE = 4

CRC_POLY = 0x1021
CRC_INIT = 0xFFFF

# Byte offsets within the packed frame.
_BODY_OFFSET = HEADER_SIZE
_BODY_SIZE = 3 + PAYLOAD_SIZE  # motor_id + command_type + sequence + payload
_CRC_OFFSET = _BODY_OFFSET + _BODY_SIZE
_PADDING_OFFSET = _CRC_OFFSET + 2


class FrameType(IntEnum):
    """Frame type enum (contract section 3.3)."""

    STATUS_REPORT = 0x01
    POSITION_CMD = 0x02
    VELOCITY_CMD = 0x03
    TORQUE_CMD = 0x04
    PARAM_READ = 0x05
    PARAM_WRITE = 0x06
    DIAGNOSTIC = 0x07
    FIRMWARE_UPDATE = 0x08
    HEARTBEAT = 0x09


def crc16_ccitt(data: bytes, init: int = CRC_INIT, poly: int = CRC_POLY) -> int:
    """CRC-16/CCITT (non-reflected). Returns a 16-bit integer."""
    crc = init & 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


@dataclass
class Frame:
    """A single unified protocol frame."""

    frame_type: FrameType
    motor_id: int
    command_type: int
    payload: bytes = field(default=b"")
    sequence: int = 0
    header_seq: int = 0
    reserved: bytes = field(default=b"")

    def __post_init__(self) -> None:
        if not 0 <= self.motor_id <= 0xFF:
            raise ValueError("motor_id must fit in one byte")
        if not 0 <= self.command_type <= 0xFF:
            raise ValueError("command_type must fit in one byte")
        if not 0 <= self.sequence <= 0xFF:
            raise ValueError("sequence must fit in one byte")
        if not 0 <= self.header_seq <= 0xFF:
            raise ValueError("header_seq must fit in one byte")
        if len(self.payload) > PAYLOAD_SIZE:
            raise ValueError(f"payload must be <= {PAYLOAD_SIZE} bytes")
        if len(self.reserved) > RESERVED_SIZE:
            raise ValueError(f"reserved must be <= {RESERVED_SIZE} bytes")

    # --- packing -------------------------------------------------------
    def pack(self) -> bytes:
        """Serialize to the 64-byte wire format (CRC computed over header+body)."""
        payload = self.payload.ljust(PAYLOAD_SIZE, b"\x00")
        reserved = self.reserved.ljust(RESERVED_SIZE, b"\x00")
        header = struct.pack(
            "<HBB4s",
            SYNC_WORD,
            int(self.frame_type),
            self.header_seq & 0xFF,
            reserved,
        )
        body = struct.pack(
            "BBB32s",
            self.motor_id & 0xFF,
            self.command_type & 0xFF,
            self.sequence & 0xFF,
            payload,
        )
        crc = crc16_ccitt(header + body)
        return header + body + struct.pack("<H", crc) + b"\x00" * PADDING_SIZE

    # --- unpacking -----------------------------------------------------
    @classmethod
    def unpack(cls, raw: bytes) -> "Frame":
        """Parse a 64-byte frame, validating sync word and CRC."""
        if len(raw) != FRAME_SIZE:
            raise ValueError(f"frame must be {FRAME_SIZE} bytes, got {len(raw)}")
        header = raw[0:HEADER_SIZE]
        body = raw[_BODY_OFFSET:_CRC_OFFSET]
        (crc,) = struct.unpack("<H", raw[_CRC_OFFSET:_PADDING_OFFSET])
        sync, frame_type, header_seq, reserved = struct.unpack("<HBB4s", header)
        if sync != SYNC_WORD:
            raise ValueError(f"bad sync word: {sync:#06x}")
        motor_id, command_type, sequence, payload = struct.unpack("BBB32s", body)
        expected = crc16_ccitt(header + body)
        if crc != expected:
            raise ValueError(
                f"CRC mismatch: frame={crc:#06x} expected={expected:#06x}"
            )
        return cls(
            frame_type=FrameType(frame_type),
            motor_id=motor_id,
            command_type=command_type,
            payload=payload,  # fixed 32-byte field: keep full width, never strip
            sequence=sequence,
            header_seq=header_seq,
            reserved=reserved.rstrip(b"\x00"),
        )
