"""Transport base classes for myactuator_lib.

Faithful Python port of the contract's ``IProtocol`` interface
(``contracts/PROTOCOLS_CONTRACT.md`` section 2.1). Every concrete transport
(CAN / Modbus / EtherCAT / loopback) subclasses :class:`Transport`.
"""

from __future__ import annotations

import abc
import time
from enum import Enum

from ..protocol import Frame
from ..protocol.frame import FrameType  # noqa: F401  (re-exported for convenience)


class ProtocolType(Enum):
    """Identifies the underlying bus technology."""

    CAN = "can"
    MODBUS = "modbus"
    ETHERCAT = "ethercat"


class TransportError(Exception):
    """Raised when a transport-level operation fails."""


class Transport(abc.ABC):
    """Abstract bus transport, mirroring the contract ``IProtocol`` surface."""

    def __init__(self) -> None:
        self._connected = False
        self._last_error: int = 0
        self._retry_count: int = 0

    # --- connection management ----------------------------------------
    @abc.abstractmethod
    def connect(self) -> bool:
        """Open the bus. Returns True on success."""

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Close the bus."""

    def is_connected(self) -> bool:
        return self._connected

    # --- data transfer -------------------------------------------------
    @abc.abstractmethod
    def send(self, frame: Frame) -> bool:
        """Transmit a single frame. Returns True on success."""

    @abc.abstractmethod
    def receive(self, timeout_ms: int = 100) -> Frame | None:
        """Receive a single frame, blocking up to ``timeout_ms``.

        Returns ``None`` on timeout.
        """

    # --- status --------------------------------------------------------
    @abc.abstractmethod
    def get_type(self) -> ProtocolType:
        """Return the bus technology for this transport."""

    def get_last_error(self) -> int:
        return self._last_error

    def get_retry_count(self) -> int:
        return self._retry_count

    # --- context manager ----------------------------------------------
    def __enter__(self) -> "Transport":
        if not self.connect():
            raise TransportError("connect() failed")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()
