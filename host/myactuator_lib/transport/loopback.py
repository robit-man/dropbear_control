"""In-memory loopback transport for tests and offline development.

Frames sent via :meth:`send` are queued and returned, in FIFO order, by the
next :meth:`receive` call. No hardware required. This is the transport used
by the host-library self-tests so the protocol/device layers can be exercised
without a CAN adapter.
"""

from __future__ import annotations

import threading
import time

from .base import ProtocolType, Transport, TransportError
from ..protocol import Frame


class LoopbackTransport(Transport):
    """FIFO in-memory transport."""

    def __init__(self, maxlen: int = 1024) -> None:
        super().__init__()
        self._queue: "list[Frame]" = []
        self._cond = threading.Condition()
        self._maxlen = maxlen

    # --- connection management ----------------------------------------
    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False
        with self._cond:
            self._queue.clear()

    # --- data transfer -------------------------------------------------
    def send(self, frame: Frame) -> bool:
        if not self._connected:
            self._last_error = 1
            raise TransportError("not connected")
        with self._cond:
            if len(self._queue) >= self._maxlen:
                self._last_error = 2
                raise TransportError("loopback queue full")
            # Simulate the wire: serialize then re-parse so the queued frame
            # carries the canonical 32-byte payload (matching a real transport).
            self._queue.append(Frame.unpack(frame.pack()))
            self._cond.notify_all()
        return True

    def receive(self, timeout_ms: int = 100) -> Frame | None:
        if not self._connected:
            self._last_error = 1
            raise TransportError("not connected")
        deadline = time.monotonic() + timeout_ms / 1000.0
        with self._cond:
            while not self._queue:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)
            return self._queue.pop(0)

    # --- status --------------------------------------------------------
    def get_type(self) -> ProtocolType:
        return ProtocolType.CAN  # loopback stands in for the CAN bus in tests
