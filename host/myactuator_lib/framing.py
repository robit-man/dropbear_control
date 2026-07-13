"""MyActuator unified protocol framing (host side).

Implements the 64-byte unified frame defined in
``contracts/PROTOCOLS_CONTRACT.md`` section 3. This is the host-side (Python)
counterpart to the ESP32 Protocol Abstraction Layer (PAL) so the high-level
compute stack and the ROS bridge can encode/decode motor frames without
depending on the embedded build.

Frame layout (64 bytes, little-endian)::

    Header (8)      : sync(2)=0xAA55, frame_type(1), seq(1), reserved(4)
    Motor ID (1)
    Command Type (1)
    Sequence (1)        # body copy of seq
    Payload (32)
    CRC-16/CCITT (2)    # over bytes [0:43]
    Padding (19)

NOTE on CRC: "CRC-16/CCITT" is implemented as CCITT-FALSE
(poly=0x1021, init=0xFFFF, no reflection), the variant most embedded docs
label "CRC-16/CCITT". If your firmware uses XMODEM (init=0x0000) or TRUE
(reflected), pass the matching ``init``/reflection to :func:`crc16_ccitt`.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

SYNC_WORD = 0xAA55
FRAME_SIZE = 64
HEADER_SIZE = 8
PAYLOAD_SIZE = 32
PADDING_SIZE = 19

# Byte offset of the CRC field inside the frame.
CRC_OFFSET = HEADER_SIZE + 1 + 1 + 1 + PAYLOAD_SIZE  # 8+1+1+1+32 = 43


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


def crc16_ccitt(data: bytes, init: int = 0xFFFF, poly: int = 0x1021,
                reflect: bool = False) -> int:
    """CRC-16/CCITT. Default is CCITT-FALSE (init=0xFFFF, no reflection)."""

    def _reflect(x: int, n: int) -> int:
        out = 0
        for i in range(n):
            if x & (1 << i):
                out |= 1 << (n - 1 - i)
        return out

    crc = init & 0xFFFF
    for b in data:
        if reflect:
            b = _reflect(b, 8)
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    if reflect:
        crc = _reflect(crc, 16)
    return crc & 0xFFFF


# < H B B 4s | B B B | 32s | H | 19s  -> 64 bytes
_FRAME_FMT = "<HBB4sBBB32sH19s"
assert struct.calcsize(_FRAME_FMT) == FRAME_SIZE, struct.calcsize(_FRAME_FMT)


@dataclass
class Frame:
    frame_type: FrameType
    motor_id: int
    payload: bytes
    seq: int = 0
    command_type: int = 0
    reserved: bytes = b"\x00" * 4

    def pack(self) -> bytes:
        if len(self.payload) != PAYLOAD_SIZE:
            raise ValueError(f"payload must be {PAYLOAD_SIZE} bytes, got {len(self.payload)}")
        if not (0 <= self.seq <= 0xFF):
            raise ValueError("seq out of range")
        if not (0 <= self.motor_id <= 0xFF):
            raise ValueError("motor_id out of range")
        body = struct.pack(
            _FRAME_FMT,
            SYNC_WORD,
            int(self.frame_type),
            self.seq & 0xFF,
            self.reserved[:4].ljust(4, b"\x00"),
            self.motor_id & 0xFF,
            self.command_type & 0xFF,
            self.seq & 0xFF,
            self.payload,
            0,  # crc placeholder
            b"\x00" * PADDING_SIZE,
        )
        crc = crc16_ccitt(body[:CRC_OFFSET])
        return body[:CRC_OFFSET] + struct.pack("<H", crc) + body[CRC_OFFSET + 2:]

    @classmethod
    def unpack(cls, raw: bytes) -> "Frame":
        if len(raw) != FRAME_SIZE:
            raise ValueError(f"frame must be {FRAME_SIZE} bytes, got {len(raw)}")
        (sync, ft, seq, reserved, motor_id, cmd, _seq2,
         payload, crc, _padding) = struct.unpack(_FRAME_FMT, raw)
        if sync != SYNC_WORD:
            raise ValueError(f"bad sync word: {sync:#06x}")
        expected = crc16_ccitt(raw[:CRC_OFFSET])
        if expected != crc:
            raise ValueError(f"CRC mismatch: expected {expected:#06x}, got {crc:#06x}")
        return cls(
            frame_type=FrameType(ft),
            motor_id=motor_id,
            payload=payload,
            seq=seq,
            command_type=cmd,
            reserved=reserved,
        )


# Status report payload (contract section 3.4.1): 32 bytes
_STATUS_FMT = "<iihBHB18s"
assert struct.calcsize(_STATUS_FMT) == PAYLOAD_SIZE


@dataclass
class StatusReport:
    position: int       # int32, encoder counts or scaled units
    velocity: int       # int32
    torque: int         # int16, mNm or raw
    temperature: int    # uint8, deg C
    status_word: int    # uint16
    fault_code: int     # uint8

    def pack(self) -> bytes:
        return struct.pack(
            _STATUS_FMT,
            self.position,
            self.velocity,
            self.torque,
            self.temperature & 0xFF,
            self.status_word & 0xFFFF,
            self.fault_code & 0xFF,
            b"\x00" * 18,
        )

    @classmethod
    def unpack(cls, payload: bytes) -> "StatusReport":
        (pos, vel, tq, temp, sw, fc, _res) = struct.unpack(_STATUS_FMT, payload)
        return cls(pos, vel, tq, temp, sw, fc)


def build_status_frame(motor_id: int, report: StatusReport, seq: int = 0) -> Frame:
    return Frame(
        frame_type=FrameType.STATUS_REPORT,
        motor_id=motor_id,
        payload=report.pack(),
        seq=seq,
        command_type=int(FrameType.STATUS_REPORT),
    )


def build_command_frame(frame_type: FrameType, motor_id: int,
                        payload: bytes, seq: int = 0) -> Frame:
    if len(payload) > PAYLOAD_SIZE:
        raise ValueError("payload too large")
    return Frame(
        frame_type=frame_type,
        motor_id=motor_id,
        payload=payload.ljust(PAYLOAD_SIZE, b"\x00"),
        seq=seq,
        command_type=int(frame_type),
    )


if __name__ == "__main__":
    r = StatusReport(position=1000, velocity=50, torque=200,
                     temperature=35, status_word=0x1234, fault_code=0)
    f = build_status_frame(0x01, r, seq=7)
    raw = f.pack()
    assert len(raw) == 64, len(raw)
    f2 = Frame.unpack(raw)
    r2 = StatusReport.unpack(f2.payload)
    assert r2.position == 1000 and r2.temperature == 35, (r2.position, r2.temperature)
    # round-trip a command frame too
    cf = build_command_frame(FrameType.POSITION_CMD, 0x02, b"\x01\x02\x03\x04", seq=3)
    cf2 = Frame.unpack(cf.pack())
    assert cf2.frame_type == FrameType.POSITION_CMD and cf2.motor_id == 0x02
    print("framing self-test OK; frame bytes =", len(raw))
