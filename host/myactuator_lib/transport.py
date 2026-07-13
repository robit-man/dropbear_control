"""Transport abstraction for talking to the ESP32 motor gateway.

The ESP32 firmware (``firmware/esp32/src/drivers/``) exposes motors over several
physical transports. This module defines a small async-agnostic ABC so the device
layer and the ROS bridge can be written once and bound to any transport.

Concrete transports are filled in once the protocol framing from
``contracts/PROTOCOLS_CONTRACT.md`` is ported.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional


@dataclass
class Frame:
    """A single transport frame (e.g. a CAN frame or serial packet)."""

    arbitration_id: int
    data: bytes
    is_extended: bool = False


class Transport(abc.ABC):
    """Abstract transport between the host and the ESP32 motor gateway."""

    @abc.abstractmethod
    async def open(self) -> None:
        """Establish the connection."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Tear down the connection."""

    @abc.abstractmethod
    async def send(self, frame: Frame) -> None:
        """Transmit a single frame."""

    @abc.abstractmethod
    async def recv(self, timeout: Optional[float] = None) -> Frame:
        """Receive the next frame, or raise ``asyncio.TimeoutError``."""


class CanTransport(Transport):
    """CAN / MCP2515 transport (matches ``drivers/mcp2515_can.*``)."""

    def __init__(self, channel: str, bitrate: int = 1_000_000) -> None:
        self._channel = channel
        self._bitrate = bitrate

    async def open(self) -> None:  # pragma: no cover - hardware
        raise NotImplementedError("Bind to python-can / MCP2515 backend")

    async def close(self) -> None:  # pragma: no cover
        raise NotImplementedError

    async def send(self, frame: Frame) -> None:  # pragma: no cover
        raise NotImplementedError

    async def recv(self, timeout: Optional[float] = None) -> Frame:  # pragma: no cover
        raise NotImplementedError


class SerialTransport(Transport):
    """RS485 / UART transport (matches ``drivers/rs485.*``)."""

    def __init__(self, port: str, baudrate: int = 115_200) -> None:
        self._port = port
        self._baudrate = baudrate

    async def open(self) -> None:  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover
        raise NotImplementedError

    async def send(self, frame: Frame) -> None:  # pragma: no cover
        raise NotImplementedError

    async def recv(self, timeout: Optional[float] = None) -> Frame:  # pragma: no cover
        raise NotImplementedError


class EthercatTransport(Transport):
    """EtherCAT transport (matches ``drivers/ethercat.*``)."""

    def __init__(self, ifname: str) -> None:
        self._ifname = ifname

    async def open(self) -> None:  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover
        raise NotImplementedError

    async def send(self, frame: Frame) -> None:  # pragma: no cover
        raise NotImplementedError

    async def recv(self, timeout: Optional[float] = None) -> Frame:  # pragma: no cover
        raise NotImplementedError
