"""Transport layer for myactuator_lib.

Bus abstractions matching the contract's ``IProtocol`` interface
(``contracts/PROTOCOLS_CONTRACT.md`` section 2.1). Concrete transports:

    CanTransport      — CAN bus (MCP2515 on the ESP32 side; socketcan/hardware on host)
    ModbusTransport   — RS485 / Modbus RTU
    EthercatTransport — EtherCAT
    LoopbackTransport — in-memory FIFO, for tests and offline development

The device and ROS layers depend on this package, not the other way around.
"""

from ..protocol import Frame
from .base import ProtocolType, Transport, TransportError
from .loopback import LoopbackTransport

__all__ = ["Frame", "ProtocolType", "Transport", "TransportError", "LoopbackTransport"]
