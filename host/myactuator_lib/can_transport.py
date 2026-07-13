"""CAN / MCP2515 transport layer (host side).

This module is the host-side counterpart to the ESP32 CAN/MCP2515 driver. It
lets the high-level compute stack (custom control stack or the ROS bridge)
move the 64-byte *unified* :class:`~framing.Frame` over a CAN bus.

Two physical topologies are supported:

1. **Direct CAN** -- the host has its own CAN adapter (e.g. a USB-CAN dongle or
   a SocketCAN interface). :class:`SocketCanTransport` talks raw SocketCAN on
   Linux and needs no extra dependency.
2. **ESP32 serial bridge** -- the host connects to the ESP32 over USB/serial and
   the ESP32 owns the MCP2515. :class:`Mcp2515SerialBridge` ships the 64-byte
   unified frame to the ESP32 using a COBS-encoded link; the ESP32 firmware
   mirrors this link (see ``firmware/esp32/src/drivers/mcp2515_can.*``).

Because the MCP2515 is a *classic* CAN controller (8-byte max payload), the
64-byte unified frame is fragmented. CAN-FD adapters (64-byte payload) carry it
in a single frame. :class:`UnifiedFrameCodec` handles both directions.

Wire format (classic CAN, 8-byte frames)::

    CAN ID (29-bit extended):  [motor_id:8][frame_type:8][seq:8][rsvd:5]
    DATA[0] = fragment index (0-based)
    DATA[1] = fragment total
    DATA[2:8] = 6 bytes of unified-frame payload

Wire format (CAN-FD, 64-byte frame)::

    CAN ID (29-bit extended):  same as above, fragment_total == 1
    DATA[0:64] = the full 64-byte unified frame

The module is hardware-optional: :class:`LoopbackTransport` and
:class:`MockMcp2515` let the unit tests run with no bus attached.
"""

from __future__ import annotations

import binascii
import struct
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:  # package import
    from .framing import FRAME_SIZE, Frame, FrameType
except ImportError:  # script / flat import
    from framing import FRAME_SIZE, Frame, FrameType

# ---------------------------------------------------------------------------
# CAN frame model
# ---------------------------------------------------------------------------

# 29-bit extended CAN ID layout for the unified-frame transport.
#   motor_id : 8   (low)
#   frame_type : 8
#   seq : 8
#   reserved : 5   (high)
CAN_ID_MOTOR_SHIFT = 0
CAN_ID_FTYPE_SHIFT = 8
CAN_ID_SEQ_SHIFT = 16
CAN_ID_RSVD_SHIFT = 24
CAN_ID_MASK = 0x1FFFFFFF  # 29 bits

CLASSIC_MTU = 8
FD_MTU = 64
# bytes of unified-frame payload carried per classic CAN frame
CLASSIC_PAYLOAD_PER_FRAME = CLASSIC_MTU - 2  # 6


@dataclass
class CanFrame:
    """A single CAN frame (classic or FD)."""

    can_id: int
    data: bytes
    is_extended: bool = True
    is_fd: bool = False
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if not (0 <= self.can_id <= CAN_ID_MASK):
            raise ValueError(f"can_id out of 29-bit range: {self.can_id}")
        if self.is_fd:
            if len(self.data) > FD_MTU:
                raise ValueError("FD data exceeds 64 bytes")
        else:
            if len(self.data) > CLASSIC_MTU:
                raise ValueError("classic data exceeds 8 bytes")


def encode_can_id(motor_id: int, frame_type: int, seq: int) -> int:
    cid = ((motor_id & 0xFF) << CAN_ID_MOTOR_SHIFT
           | ((int(frame_type) & 0xFF) << CAN_ID_FTYPE_SHIFT)
           | ((seq & 0xFF) << CAN_ID_SEQ_SHIFT))
    return cid & CAN_ID_MASK


def decode_can_id(can_id: int) -> Tuple[int, int, int]:
    motor_id = (can_id >> CAN_ID_MOTOR_SHIFT) & 0xFF
    frame_type = (can_id >> CAN_ID_FTYPE_SHIFT) & 0xFF
    seq = (can_id >> CAN_ID_SEQ_SHIFT) & 0xFF
    return motor_id, frame_type, seq


# ---------------------------------------------------------------------------
# Fragmentation codec (64-byte unified frame <-> CAN frames)
# ---------------------------------------------------------------------------

class UnifiedFrameCodec:
    """Fragment a 64-byte :class:`Frame` into CAN frames and reassemble them."""

    def __init__(self, use_fd: bool = False) -> None:
        self.use_fd = use_fd

    def fragment(self, frame: Frame) -> List[CanFrame]:
        raw = frame.pack()
        cid = encode_can_id(frame.motor_id, int(frame.frame_type), frame.seq)
        if self.use_fd:
            return [CanFrame(can_id=cid, data=raw, is_extended=True, is_fd=True)]
        # classic: 6 payload bytes per frame
        chunks = [raw[i:i + CLASSIC_PAYLOAD_PER_FRAME]
                  for i in range(0, len(raw), CLASSIC_PAYLOAD_PER_FRAME)]
        total = len(chunks)
        out: List[CanFrame] = []
        for idx, chunk in enumerate(chunks):
            data = bytes([idx, total]) + chunk
            # pad to 8 bytes (MCP2515 requires full DLC)
            data = data.ljust(CLASSIC_MTU, b"\x00")
            out.append(CanFrame(can_id=cid, data=data, is_extended=True,
                                is_fd=False))
        return out

    def reassemble(self, can_frames: List[CanFrame]) -> Frame:
        if not can_frames:
            raise ValueError("no CAN frames to reassemble")
        first = can_frames[0]
        if first.is_fd and len(first.data) == FRAME_SIZE:
            return Frame.unpack(first.data)
        # classic fragmentation
        by_key: Dict[Tuple[int, int, int], Dict[int, bytes]] = {}
        totals: Dict[Tuple[int, int, int], int] = {}
        for cf in can_frames:
            motor_id, frame_type, seq = decode_can_id(cf.can_id)
            key = (motor_id, frame_type, seq)
            frag_idx = cf.data[0]
            frag_total = cf.data[1]
            payload = cf.data[2:2 + CLASSIC_PAYLOAD_PER_FRAME]
            by_key.setdefault(key, {})[frag_idx] = payload
            totals[key] = frag_total
        # reassemble the first complete group
        for key, frags in by_key.items():
            total = totals[key]
            if len(frags) == total and all(i in frags for i in range(total)):
                raw = b"".join(frags[i] for i in range(total))
                if len(raw) < FRAME_SIZE:
                    raw = raw.ljust(FRAME_SIZE, b"\x00")
                return Frame.unpack(raw[:FRAME_SIZE])
        raise ValueError("incomplete fragment set; cannot reassemble")


# ---------------------------------------------------------------------------
# Transport abstraction
# ---------------------------------------------------------------------------

class CanTransport(ABC):
    """Abstract CAN transport. Subclasses move :class:`Frame` on/off a bus."""

    def __init__(self, use_fd: bool = False) -> None:
        self.codec = UnifiedFrameCodec(use_fd=use_fd)
        self._recv_thread: Optional[threading.Thread] = None
        self._running = False
        self._listeners: List[callable] = []

    # -- lifecycle --------------------------------------------------------
    @abstractmethod
    def open(self) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    # -- raw CAN (optional override) -------------------------------------
    def send_can(self, frame: CanFrame) -> None:  # pragma: no cover - default
        raise NotImplementedError

    def recv_can(self) -> Optional[CanFrame]:  # pragma: no cover - default
        raise NotImplementedError

    # -- unified frame API ----------------------------------------------
    def send(self, frame: Frame) -> None:
        for cf in self.codec.fragment(frame):
            self.send_can(cf)

    def recv(self) -> Optional[Frame]:
        cf = self.recv_can()
        if cf is None:
            return None
        # buffer fragments until a full frame is available
        return self._buffer_can(cf)

    def _buffer_can(self, cf: CanFrame) -> Optional[Frame]:
        # simple single-group buffering; sufficient for point-to-point links
        if not hasattr(self, "_frag_buf"):
            self._frag_buf: List[CanFrame] = []  # type: ignore[attr-defined]
        self._frag_buf.append(cf)  # type: ignore[attr-defined]
        try:
            return self.codec.reassemble(self._frag_buf)  # type: ignore[attr-defined]
        except ValueError:
            return None

    def add_listener(self, cb: callable) -> None:
        self._listeners.append(cb)

    def _dispatch(self, frame: Frame) -> None:
        for cb in self._listeners:
            try:
                cb(frame)
            except Exception:  # listeners must not break the rx loop
                pass

    def _rx_loop(self) -> None:
        while self._running:
            cf = self.recv_can()
            if cf is None:
                time.sleep(0.001)
                continue
            try:
                frame = self.codec.reassemble([cf])
            except ValueError:
                frame = None
            if frame is not None:
                self._dispatch(frame)


# ---------------------------------------------------------------------------
# SocketCAN backend (Linux, no external dependency)
# ---------------------------------------------------------------------------

class SocketCanTransport(CanTransport):
    """Raw SocketCAN transport for Linux hosts with a CAN adapter.

    Uses the ``AF_CAN`` raw socket directly (no python-can dependency). Works
    for both classic CAN and CAN-FD interfaces (``can_fd=True`` selects the
    FD MTU).
    """

    def __init__(self, interface: str = "can0", can_fd: bool = False) -> None:
        super().__init__(use_fd=can_fd)
        self.interface = interface
        self.can_fd = can_fd
        self._sock = None

    def open(self) -> None:
        import socket
        self._sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW,
                                   socket.CAN_RAW)
        self._sock.bind((self.interface,))
        self._running = True

    def close(self) -> None:
        self._running = False
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def send_can(self, frame: CanFrame) -> None:
        if self._sock is None:
            raise RuntimeError("transport not open")
        if frame.is_fd:
            # <I B 3x 64s
            pkt = struct.pack("<IB3x64s", frame.can_id, len(frame.data),
                              frame.data.ljust(64, b"\x00"))
        else:
            pkt = struct.pack("<IB3x8s", frame.can_id, len(frame.data),
                              frame.data.ljust(8, b"\x00"))
        self._sock.send(pkt)

    def recv_can(self) -> Optional[CanFrame]:
        if self._sock is None:
            return None
        self._sock.settimeout(0.05)
        try:
            pkt = self._sock.recv(72)
        except Exception:
            return None
        if len(pkt) >= 16:  # classic: <I B 3x 8s = 16
            can_id, dlc, data = struct.unpack("<IB3x8s", pkt[:16])
            return CanFrame(can_id=can_id, data=data[:dlc], is_extended=True,
                            is_fd=False)
        return None


# ---------------------------------------------------------------------------
# ESP32 / MCP2515 serial bridge
# ---------------------------------------------------------------------------

# COBS-encoded serial link carrying the 64-byte unified frame.
# Wire format: [0x00][cobs(payload)][0x00]  where payload = 64-byte frame.
# The ESP32 firmware implements the identical link (see mcp2515_can.cpp).

def _cobs_encode(data: bytes) -> bytes:
    """Consistent Overhead Byte Stuffing (RFC 1055)."""
    out = bytearray()
    code_idx = 0
    code = 1
    out.append(0)  # placeholder for the first code byte
    for b in data:
        if b == 0:
            out[code_idx] = code
            code_idx = len(out)
            out.append(0)  # placeholder for next code byte
            code = 1
        else:
            code += 1
            out.append(b)
            if code == 0xFF:
                out[code_idx] = code
                code_idx = len(out)
                out.append(0)  # placeholder
                code = 1
    out[code_idx] = code
    return bytes(out)


def _cobs_decode(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        code = data[i]
        if code == 0:
            raise ValueError("zero code in COBS stream")
        i += 1
        end = i + code - 1
        if end > n:
            raise ValueError("COBS overrun")
        out.extend(data[i:end])
        if code < 0xFF and end < n:
            out.append(0)
        i = end
    return bytes(out)


class Mcp2515SerialBridge(CanTransport):
    """Host <-> ESP32 (MCP2515 owner) bridge over a serial port.

    The host sends the 64-byte unified frame to the ESP32 using a COBS-encoded
    link; the ESP32 translates to/from the MCP2515 CAN bus. Received CAN frames
    are relayed back the same way.
    """

    def __init__(self, port: str = "/dev/ttyUSB0", baud: int = 921600) -> None:
        super().__init__(use_fd=False)
        self.port = port
        self.baud = baud
        self._ser = None
        self._buf = bytearray()

    def open(self) -> None:
        import serial  # pyserial
        self._ser = serial.Serial(self.port, self.baud, timeout=0.05)
        self._running = True
        self._recv_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._recv_thread.start()

    def close(self) -> None:
        self._running = False
        if self._recv_thread is not None:
            self._recv_thread.join(timeout=1.0)
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def send(self, frame: Frame) -> None:  # type: ignore[override]
        if self._ser is None:
            raise RuntimeError("bridge not open")
        raw = frame.pack()
        packet = b"\x00" + _cobs_encode(raw) + b"\x00"
        self._ser.write(packet)

    def _rx_loop(self) -> None:
        while self._running and self._ser is not None:
            chunk = self._ser.read(64)
            if not chunk:
                continue
            self._buf.extend(chunk)
            # split on 0x00 delimiters
            while b"\x00" in self._buf:
                idx = self._buf.index(b"\x00")
                if idx == 0:
                    self._buf.pop(0)
                    continue
                packet = bytes(self._buf[:idx])
                del self._buf[:idx + 1]
                try:
                    raw = _cobs_decode(packet)
                except ValueError:
                    continue
                if len(raw) == FRAME_SIZE:
                    try:
                        frame = Frame.unpack(raw)
                    except ValueError:
                        continue
                    self._dispatch(frame)


# ---------------------------------------------------------------------------
# Test / simulation backends (no hardware)
# ---------------------------------------------------------------------------

class LoopbackTransport(CanTransport):
    """In-memory loopback: every sent frame is immediately received."""

    def __init__(self, use_fd: bool = False) -> None:
        super().__init__(use_fd=use_fd)
        self._queue: List[Frame] = []
        self._lock = threading.Lock()

    def open(self) -> None:
        self._running = True

    def close(self) -> None:
        self._running = False

    def send(self, frame: Frame) -> None:  # type: ignore[override]
        with self._lock:
            self._queue.append(frame)

    def recv(self) -> Optional[Frame]:  # type: ignore[override]
        with self._lock:
            if self._queue:
                return self._queue.pop(0)
        return None


class MockMcp2515(CanTransport):
    """Simulates a motor hanging off the MCP2515.

    Echoes a STATUS_REPORT for every command frame it receives, so the device
    layer can be exercised end-to-end without a real bus or motor.
    """

    def __init__(self, motor_id: int = 0x01, use_fd: bool = False) -> None:
        super().__init__(use_fd=use_fd)
        self.motor_id = motor_id
        self._in: List[Frame] = []
        self._out: List[Frame] = []
        self._lock = threading.Lock()

    def open(self) -> None:
        self._running = True

    def close(self) -> None:
        self._running = False

    def send(self, frame: Frame) -> None:  # type: ignore[override]
        with self._lock:
            self._in.append(frame)
            # synthesize a status report echo
            from .framing import StatusReport, build_status_frame
            report = StatusReport(position=frame.seq * 100, velocity=10,
                                  torque=5, temperature=30, status_word=0x0035,
                                  fault_code=0)
            echo = build_status_frame(self.motor_id, report, seq=frame.seq)
            self._out.append(echo)

    def recv(self) -> Optional[Frame]:  # type: ignore[override]
        with self._lock:
            if self._out:
                return self._out.pop(0)
        return None


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 1) classic fragmentation round-trip
    from framing import StatusReport, build_status_frame
    rep = StatusReport(position=1234, velocity=-50, torque=300, temperature=42,
                       status_word=0x1234, fault_code=0)
    f = build_status_frame(0x07, rep, seq=9)
    codec = UnifiedFrameCodec(use_fd=False)
    frags = codec.fragment(f)
    assert len(frags) == 11, len(frags)  # 64 / 6 -> 11 frames
    reassembled = codec.reassemble(frags)
    assert reassembled.motor_id == 0x07 and reassembled.seq == 9
    r2 = StatusReport.unpack(reassembled.payload)
    assert r2.position == 1234 and r2.temperature == 42

    # 2) FD single-frame round-trip
    codec_fd = UnifiedFrameCodec(use_fd=True)
    fd_frags = codec_fd.fragment(f)
    assert len(fd_frags) == 1 and fd_frags[0].is_fd
    assert codec_fd.reassemble(fd_frags).motor_id == 0x07

    # 3) loopback transport end-to-end
    lb = LoopbackTransport(use_fd=False)
    lb.open()
    lb.send(f)
    got = lb.recv()
    assert got is not None and got.motor_id == 0x07
    lb.close()

    # 4) COBS encode/decode symmetry
    sample = bytes(range(256))
    assert _cobs_decode(_cobs_encode(sample)) == sample

    # 5) CAN ID encode/decode
    cid = encode_can_id(0x0A, int(FrameType.VELOCITY_CMD), 0x05)
    assert decode_can_id(cid) == (0x0A, int(FrameType.VELOCITY_CMD), 0x05)

    print("can_transport self-test OK; classic fragments =", len(frags))
