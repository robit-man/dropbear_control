"""ROS 2 bridge layer for MyActuator motors.

This module is the integration surface for ROS 2 control stacks. It exposes
each :class:`~myactuator_lib.devices.MotorDevice` as a *joint* so the motors
correlate 1:1 with joints in a URDF / MJCF model on the high-level compute
side.

Design
------
* :class:`RosBridge` holds a mapping ``joint_name -> MotorDevice``. Joint
  names can be supplied explicitly or discovered from a URDF / MJCF string
  via :meth:`RosBridge.from_urdf` (lightweight regex extraction, no external
  XML dependency).
* :meth:`RosBridge.joint_state_dict` aggregates every device's
  :class:`MotorState` into the four standard ``sensor_msgs/JointState``
  vectors (``name``, ``position``, ``velocity``, ``effort``).
* :meth:`RosBridge.to_joint_state_msg` converts that dict into a real
  ``sensor_msgs.msg.JointState`` (requires an ``rclpy`` runtime).
* :meth:`RosBridge.command` routes a high-level command (position / velocity
  / effort) for a named joint to the underlying device's async setter.

The module imports cleanly *without* ROS 2 installed (``rclpy`` /
``sensor_msgs`` are imported lazily inside the methods that need them), so the
headless self-test at the bottom runs on a plain Python interpreter.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from .devices import MotorDevice, MotorState


class RosBridge:
    """Bridges a set of :class:`MotorDevice` instances to ROS 2 topics.

    The bridge is intentionally transport-agnostic: it only talks to the
    device objects, never to CAN directly. That keeps it unit-testable with a
    mock transport and a mock device.
    """

    def __init__(
        self,
        devices: Sequence[MotorDevice],
        joint_names: Optional[Sequence[str]] = None,
    ) -> None:
        if joint_names is None:
            joint_names = [f"joint_{i}" for i in range(len(devices))]
        if len(joint_names) != len(devices):
            raise ValueError(
                f"joint_names ({len(joint_names)}) must match devices ({len(devices)})"
            )
        # Python dicts preserve insertion order -> stable joint ordering.
        self._joints: Dict[str, MotorDevice] = dict(zip(joint_names, devices))

    # -- introspection ----------------------------------------------------
    @property
    def joint_names(self) -> List[str]:
        return list(self._joints.keys())

    def device_for(self, joint_name: str) -> MotorDevice:
        try:
            return self._joints[joint_name]
        except KeyError as exc:
            raise KeyError(f"unknown joint: {joint_name!r}") from exc

    # -- state aggregation ------------------------------------------------
    def joint_state_dict(self) -> Dict[str, List[float]]:
        """Return ``{name, position, velocity, effort}`` vectors.

        Position / velocity / effort are read off each device's
        :class:`MotorState` with graceful fallbacks (0.0 when a field is
        missing). This is the dependency-free core that
        :meth:`to_joint_state_msg` wraps when ROS 2 is present.
        """
        names: List[str] = []
        positions: List[float] = []
        velocities: List[float] = []
        efforts: List[float] = []
        for name, dev in self._joints.items():
            state = dev.state
            names.append(name)
            positions.append(float(getattr(state, "position", 0.0) or 0.0))
            velocities.append(float(getattr(state, "velocity", 0.0) or 0.0))
            # Effort may be reported as torque; fall back to torque then 0.0.
            eff = getattr(state, "effort", None)
            if eff is None:
                eff = getattr(state, "torque", 0.0)
            efforts.append(float(eff or 0.0))
        return {
            "name": names,
            "position": positions,
            "velocity": velocities,
            "effort": efforts,
        }

    def to_joint_state_msg(self):
        """Build a ``sensor_msgs.msg.JointState`` from aggregated state.

        Requires ``rclpy`` / ``sensor_msgs`` to be importable.
        """
        from sensor_msgs.msg import JointState  # lazy: ROS 2 only

        vec = self.joint_state_dict()
        msg = JointState()
        msg.name = vec["name"]
        msg.position = vec["position"]
        msg.velocity = vec["velocity"]
        msg.effort = vec["effort"]
        return msg

    # -- command routing --------------------------------------------------
    async def command(self, joint_name: str, kind: str, value: float) -> None:
        """Route a high-level command to the device behind ``joint_name``.

        ``kind`` is one of ``"position"``, ``"velocity"`` or ``"effort"``
        (effort maps to torque).
        """
        dev = self.device_for(joint_name)
        if kind == "position":
            await dev.set_position(float(value))
        elif kind == "velocity":
            await dev.set_speed(float(value))
        elif kind in ("effort", "torque"):
            await dev.set_torque(float(value))
        else:
            raise ValueError(f"unknown command kind: {kind!r}")

    # -- URDF / MJCF correlation -----------------------------------------
    @classmethod
    def from_urdf(
        cls,
        urdf_text: str,
        devices: Sequence[MotorDevice],
        joint_names: Optional[Sequence[str]] = None,
    ) -> "RosBridge":
        """Create a bridge, optionally discovering joint names from a URDF/MJCF.

        If ``joint_names`` is not given, joint names are extracted from the
        ``<joint name="...">`` (URDF) or ``<joint name="..."/>`` (MJCF)
        elements, in document order, and paired 1:1 with ``devices``.
        """
        if joint_names is None:
            joint_names = cls._extract_joint_names(urdf_text)
        return cls(devices, joint_names=joint_names)

    @staticmethod
    def _extract_joint_names(urdf_text: str) -> List[str]:
        # Matches both URDF (<joint name="x">) and MJCF (<joint name="x"/>).
        return re.findall(r"<joint\b[^>]*\bname\s*=\s*[\"']([^\"']+)[\"']", urdf_text)

    # -- runtime (requires ROS 2) ----------------------------------------
    def spin(self) -> None:  # pragma: no cover - requires ROS 2 runtime
        """Create the ROS 2 node, publisher and subscribers and spin.

        Implemented on the device layer once ``rclpy`` is available in the
        deployment image.
        """
        raise NotImplementedError("Requires rclpy; implement after device layer lands")


def _self_test() -> None:
    """Headless self-test: runs without ROS 2 installed."""

    class _DummyTransport:
        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

        def send(self, frame):  # pragma: no cover - not exercised here
            pass

        def recv(self):  # pragma: no cover - not exercised here
            return None

        def add_listener(self, cb) -> None:  # pragma: no cover
            pass

    class _TestDevice(MotorDevice):
        def __init__(self, node_id: int) -> None:
            super().__init__(_DummyTransport(), node_id)
            self.last: Optional[Tuple[str, float]] = None

        async def enable(self) -> None:
            pass

        async def disable(self) -> None:
            pass

        async def set_torque(self, torque_nm: float) -> None:
            self.last = ("torque", torque_nm)

        async def set_speed(self, speed_rad_s: float) -> None:
            self.last = ("speed", speed_rad_s)

        async def set_position(self, position_rad: float) -> None:
            self.last = ("position", position_rad)

        async def read_state(self) -> MotorState:
            return self._state

    import asyncio

    d1 = _TestDevice(node_id=1)
    d2 = _TestDevice(node_id=2)
    bridge = RosBridge([d1, d2], joint_names=["joint_a", "joint_b"])

    # 1) joint-name correlation
    assert bridge.joint_names == ["joint_a", "joint_b"], bridge.joint_names

    # 2) state aggregation structure
    vec = bridge.joint_state_dict()
    assert vec["name"] == ["joint_a", "joint_b"], vec
    assert len(vec["position"]) == 2 and len(vec["velocity"]) == 2, vec

    # 3) command routing
    asyncio.run(bridge.command("joint_a", "position", 1.25))
    assert d1.last == ("position", 1.25), d1.last
    asyncio.run(bridge.command("joint_b", "effort", 3.0))
    assert d2.last == ("torque", 3.0), d2.last

    # 4) URDF joint discovery + 1:1 correlation
    urdf = """
    <robot name="arm">
      <joint name="shoulder" type="revolute"/>
      <joint name="elbow" type="revolute"/>
    </robot>"""
    bridge2 = RosBridge.from_urdf(urdf, [d1, d2])
    assert bridge2.joint_names == ["shoulder", "elbow"], bridge2.joint_names

    # 5) unknown joint rejected
    try:
        bridge.device_for("nope")
        raise AssertionError("expected KeyError for unknown joint")
    except KeyError:
        pass

    print("ros self-test OK")


if __name__ == "__main__":
    _self_test()
