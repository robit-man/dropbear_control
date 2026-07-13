"""Device abstraction for MyActuator motors.

Each product family (RMD-X, RH, CEM, RMD-H, RMD-L, FL) gets a subclass of
``MotorDevice``. The concrete command/response encoders are implemented from the
per-product contracts in ``contracts/`` (``MOTOR_RMD_X_CONTRACT.md``, etc.).
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field

# Allow running this module directly as a script (e.g.
# `python3 host/myactuator_lib/devices.py`) by making the parent package
# importable and declaring the package name so the relative import below
# resolves. Without this, executing the file as a script raises
# "attempted relative import with no known parent package".
if __package__ in (None, ""):
    import os as _os
    import sys as _sys
    _sys.path.insert(
        0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    )
    __package__ = "myactuator_lib"

from .transport import Frame, Transport


@dataclass
class MotorState:
    """Realtime motor telemetry. Units are filled per product contract."""

    position: float = 0.0          # rad (or encoder counts per contract)
    velocity: float = 0.0          # rad/s
    torque: float = 0.0            # N·m
    temperature: float = 0.0       # °C
    error_code: int = 0
    timestamp: float = field(default_factory=time.monotonic)


class MotorDevice(abc.ABC):
    """Base class for a single MyActuator motor behind a transport."""

    def __init__(self, transport: Transport, node_id: int) -> None:
        self._transport = transport
        self._node_id = node_id
        self._state = MotorState()

    @property
    def node_id(self) -> int:
        return self._node_id

    @property
    def state(self) -> MotorState:
        return self._state

    @abc.abstractmethod
    async def enable(self) -> None:
        """Exit standby and enable the drive."""

    @abc.abstractmethod
    async def disable(self) -> None:
        """Enter standby / disable the drive."""

    @abc.abstractmethod
    async def set_torque(self, torque_nm: float) -> None:
        """Command a torque setpoint."""

    @abc.abstractmethod
    async def set_speed(self, speed_rad_s: float) -> None:
        """Command a speed setpoint."""

    @abc.abstractmethod
    async def set_position(self, position_rad: float) -> None:
        """Command a position setpoint."""

    @abc.abstractmethod
    async def read_state(self) -> MotorState:
        """Poll telemetry and update ``self.state``."""
