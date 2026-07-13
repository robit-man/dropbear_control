"""Device abstraction for myactuator motors.

A :class:`Device` binds a :class:`~myactuator_lib.transport.Transport` to a
single motor (by ``motor_id``) and exposes typed command helpers that build
and parse the contract frame types. The ROS node layer is built on top of
this.
"""

from __future__ import annotations

import struct
from typing import Optional

from ..protocol import Frame, FrameType
from ..transport import Transport, TransportError


class Device:
    """Single-motor controller bound to a transport."""

    def __init__(self, transport: Transport, motor_id: int, *, sequence: int = 0) -> None:
        if not (0 <= motor_id <= 0xFF):
            raise ValueError("motor_id must fit in a byte")
        self._transport = transport
        self._motor_id = motor_id
        self._sequence = sequence & 0xFF

    # -- low level -----------------------------------------------------
    def request(
        self,
        frame_type: FrameType,
        command_type: int,
        payload: bytes,
        timeout_ms: int = 100,
    ) -> Optional[Frame]:
        """Send a command frame and await one response frame.

        Returns the received :class:`Frame`, or ``None`` on timeout.
        """
        if not self._transport.is_connected():
            raise TransportError("transport not connected")
        frame = Frame(
            frame_type=frame_type,
            motor_id=self._motor_id,
            command_type=command_type & 0xFF,
            payload=payload,
            sequence=self._sequence,
        )
        self._sequence = (self._sequence + 1) & 0xFF
        if not self._transport.send(frame):
            raise TransportError("send() returned False")
        return self._transport.receive(timeout_ms=timeout_ms)

    # -- typed helpers -------------------------------------------------
    def set_position(self, position: int, timeout_ms: int = 100) -> Optional[Frame]:
        """Issue a POSITION_CMD. ``position`` is a signed 32-bit counts value."""
        payload = struct.pack("<i", int(position))
        return self.request(FrameType.POSITION_CMD, 0x00, payload, timeout_ms)

    def get_status(self, timeout_ms: int = 100) -> Optional[Frame]:
        """Request a STATUS_REPORT (position/velocity/torque feedback)."""
        return self.request(FrameType.STATUS_REPORT, 0x00, b"", timeout_ms)
