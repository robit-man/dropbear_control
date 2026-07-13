"""myactuator_lib — host-side library for MyActuator motor controllers.

Layered API to talk to MyActuator servo drives (RMD-X, RH, CEM, RMD-H, RMD-L)
over CAN (MCP2515), RS485 or EtherCAT, and to bridge them into ROS.

Package layout (built incrementally):
    myactuator_lib.transport   — bus abstractions (CAN / RS485 / EtherCAT)
    myactuator_lib.device      — per-product motor device drivers
    myactuator_lib.protocol    — wire protocols (PAL, RS485 framing)
    myactuator_lib.ros         — ROS 2 bridge nodes

The firmware counterpart lives in ``firmware/esp32`` and is built with
PlatformIO (targets: esp32, esp32s3, esp32c3, esp32s3dev). The wire-protocol
details are specified in ``contracts/`` (``PROTOCOLS_CONTRACT.md`` and the
per-product ``MOTOR_*_CONTRACT.md`` files). Those contracts are the source of
truth for command/response framing and must be consulted before implementing
concrete command encoders/decoders.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "MyActuatorError",
    "TransportError",
    "ProtocolError",
    "DeviceError",
    "__version__",
]


class MyActuatorError(Exception):
    """Base exception for all myactuator_lib errors."""


class TransportError(MyActuatorError):
    """Raised when a transport (CAN/RS485/EtherCAT) operation fails."""


class ProtocolError(MyActuatorError):
    """Raised when a wire-protocol encode/decode or CRC check fails."""


class DeviceError(MyActuatorError):
    """Raised when a device-level command is rejected or times out."""
