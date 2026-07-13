"""Per-product protocol layer for MyActuator motors (host side).

This module is the host-side counterpart to the ESP32 per-product drivers
(``firmware/esp32/src/drivers/{cem,fl}_driver.*`` and the RMD/RH/H/L command
builders in ``firmware/esp32/src/protocols/``). It maps high-level control
intents to the unified 64-byte :class:`~framing.Frame` and decodes
:class:`~framing.StatusReport` into physical units.

Scaling constants are sourced from the per-product contracts in
``contracts/MOTOR_*_CONTRACT.md``. Values marked ``# UNVERIFIED`` could not be
confirmed against the contract at authoring time and must be validated before
field deployment.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, Tuple

try:
    from .framing import (
        Frame, FrameType, StatusReport,
        build_command_frame, build_status_frame,
    )
except ImportError:  # script / flat import
    from framing import (
        Frame, FrameType, StatusReport,
        build_command_frame, build_status_frame,
    )

PAYLOAD_SIZE = 32


class ControlMode(IntEnum):
    POSITION = 0x01
    VELOCITY = 0x02
    TORQUE = 0x03
    STOP = 0x04
    ZERO = 0x05


@dataclass
class ProductSpec:
    """Physical/electrical characteristics of a motor family."""

    family: str
    bus: str                       # "can" | "ethercat" | "both"
    position_scale: float          # physical_deg = raw * scale
    velocity_scale: float          # physical_dps = raw * scale
    torque_scale: float            # physical_nm  = raw * scale
    encoder_resolution: int = 0    # counts per revolution (0 = unknown)
    rated_torque_nm: float = 0.0
    control_modes: Tuple[str, ...] = ("position", "velocity", "torque")
    notes: str = ""


# Scaling constants. MyActuator's public RMD protocol uses 0.01 deg/unit for
# multi-turn angle, 1 deg/s/unit for speed, and 0.01 Nm/unit for torque.
# Per-family overrides below are taken from the contracts where available.
_SPECS: Dict[str, ProductSpec] = {
    "RMD-X": ProductSpec(
        family="RMD-X", bus="can",
        position_scale=0.01, velocity_scale=1.0, torque_scale=0.01,
        encoder_resolution=16384, rated_torque_nm=0.0,
        notes="Planetary integrated actuator. CAN 500k/1M.",
    ),
    "RH": ProductSpec(
        family="RH", bus="can",
        position_scale=0.01, velocity_scale=1.0, torque_scale=0.01,
        encoder_resolution=131072, rated_torque_nm=0.0,
        notes="Hollow harmonic integrated actuator.",
    ),
    "CEM": ProductSpec(
        family="CEM", bus="can",
        position_scale=0.01, velocity_scale=1.0, torque_scale=0.01,
        encoder_resolution=16384, rated_torque_nm=0.0,
        notes="Cycloid integrated actuator. See contracts/MOTOR_CEM_CONTRACT.md.",
    ),
    "RMD-H": ProductSpec(
        family="RMD-H", bus="both",
        position_scale=0.01, velocity_scale=1.0, torque_scale=0.01,
        encoder_resolution=16384, rated_torque_nm=0.0,
        notes="Direct-drive (DD) motor. CAN and EtherCAT.",
    ),
    "RMD-L": ProductSpec(
        family="RMD-L", bus="both",
        position_scale=0.01, velocity_scale=1.0, torque_scale=0.01,
        encoder_resolution=16384, rated_torque_nm=0.0,
        notes="Low-profile direct-drive (DD) motor. CAN and EtherCAT.",
    ),
    "FL": ProductSpec(
        family="FL", bus="can",
        position_scale=0.01, velocity_scale=1.0, torque_scale=0.01,
        encoder_resolution=0, rated_torque_nm=0.0,
        notes="Frameless torque motor. See contracts for FL/FLO if present.",
    ),
}


def get_spec(family: str) -> ProductSpec:
    if family not in _SPECS:
        raise KeyError(f"unknown product family: {family!r}")
    return _SPECS[family]


def list_families() -> Tuple[str, ...]:
    return tuple(_SPECS.keys())


# Command payload layouts (32-byte unified payload) -------------------------
# Position: int32 target(raw) | int16 max_speed(raw) | int16 accel(raw) |
#           uint8 mode | 23x uint8 reserved  -> 9 + 23 = 32
_POS_FMT = "<i h h B 23s"
# Velocity: int32 target(raw) | int16 accel(raw) | uint8 mode | 25s pad
_VEL_FMT = "<i h B 25s"
# Torque:   int16 target(raw) | uint8 mode | 29s pad
_TRQ_FMT = "<h B 29s"
# Stop/Zero: uint8 mode | 31s pad
_GEN_FMT = "<B 31s"

for _f in (_POS_FMT, _VEL_FMT, _TRQ_FMT, _GEN_FMT):
    assert struct.calcsize(_f) == PAYLOAD_SIZE, struct.calcsize(_f)


class ProductProtocol:
    """Encodes/decodes commands and state for one motor instance."""

    def __init__(self, family: str, motor_id: int, seq: int = 0) -> None:
        self.spec = get_spec(family)
        self.family = family
        self.motor_id = motor_id
        self._seq = seq

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    # -- command builders -------------------------------------------------
    def position_cmd(self, target_deg: float, max_speed_dps: float = 0.0,
                     accel_dps2: float = 0.0) -> Frame:
        raw_target = int(round(target_deg / self.spec.position_scale))
        raw_speed = int(round(max_speed_dps / self.spec.velocity_scale))
        raw_accel = int(round(accel_dps2 / self.spec.velocity_scale))
        payload = struct.pack(_POS_FMT, raw_target, raw_speed, raw_accel,
                              int(ControlMode.POSITION), b"\x00" * 23)
        return build_command_frame(FrameType.POSITION_CMD, self.motor_id,
                                   payload, seq=self._next_seq())

    def velocity_cmd(self, target_dps: float, accel_dps2: float = 0.0) -> Frame:
        raw_target = int(round(target_dps / self.spec.velocity_scale))
        raw_accel = int(round(accel_dps2 / self.spec.velocity_scale))
        payload = struct.pack(_VEL_FMT, raw_target, raw_accel,
                              int(ControlMode.VELOCITY), b"\x00" * 25)
        return build_command_frame(FrameType.VELOCITY_CMD, self.motor_id,
                                   payload, seq=self._next_seq())

    def torque_cmd(self, target_nm: float) -> Frame:
        raw_target = int(round(target_nm / self.spec.torque_scale))
        payload = struct.pack(_TRQ_FMT, raw_target, int(ControlMode.TORQUE),
                              b"\x00" * 29)
        return build_command_frame(FrameType.TORQUE_CMD, self.motor_id,
                                   payload, seq=self._next_seq())

    def stop_cmd(self) -> Frame:
        payload = struct.pack(_GEN_FMT, int(ControlMode.STOP), b"\x00" * 31)
        return build_command_frame(FrameType.POSITION_CMD, self.motor_id,
                                   payload, seq=self._next_seq())

    def zero_cmd(self) -> Frame:
        payload = struct.pack(_GEN_FMT, int(ControlMode.ZERO), b"\x00" * 31)
        return build_command_frame(FrameType.PARAM_WRITE, self.motor_id,
                                   payload, seq=self._next_seq())

    # -- state decoding ---------------------------------------------------
    def decode_status(self, frame: Frame) -> dict:
        if frame.frame_type != FrameType.STATUS_REPORT:
            raise ValueError("frame is not a status report")
        r = StatusReport.unpack(frame.payload)
        return {
            "motor_id": frame.motor_id,
            "seq": frame.seq,
            "family": self.family,
            "position_deg": r.position * self.spec.position_scale,
            "velocity_dps": r.velocity * self.spec.velocity_scale,
            "torque_nm": r.torque * self.spec.torque_scale,
            "temperature_c": r.temperature,
            "status_word": r.status_word,
            "fault_code": r.fault_code,
        }


if __name__ == "__main__":
    p = ProductProtocol("RMD-X", motor_id=0x01)
    f_pos = p.position_cmd(90.0, max_speed_dps=30.0)
    assert f_pos.frame_type == FrameType.POSITION_CMD
    raw_target = struct.unpack("<i", f_pos.payload[0:4])[0]
    assert raw_target == 9000, raw_target  # 90 / 0.01

    f_vel = p.velocity_cmd(120.0)
    raw_vel = struct.unpack("<i", f_vel.payload[0:4])[0]
    assert raw_vel == 120, raw_vel

    f_trq = p.torque_cmd(0.5)
    raw_trq = struct.unpack("<h", f_trq.payload[0:2])[0]
    assert raw_trq == 50, raw_trq  # 0.5 / 0.01

    rep = StatusReport(position=9000, velocity=120, torque=50, temperature=35,
                       status_word=0x0035, fault_code=0)
    sf = build_status_frame(0x01, rep, seq=2)
    state = p.decode_status(sf)
    assert abs(state["position_deg"] - 90.0) < 1e-6
    assert abs(state["velocity_dps"] - 120.0) < 1e-6
    assert abs(state["torque_nm"] - 0.5) < 1e-6
    assert state["temperature_c"] == 35

    # every family constructs and builds commands without error
    for fam in list_families():
        pp = ProductProtocol(fam, motor_id=0x02)
        pp.position_cmd(10.0)
        pp.velocity_cmd(5.0)
        pp.torque_cmd(0.1)
        pp.stop_cmd()
        pp.zero_cmd()

    print("protocols self-test OK; families =", len(_SPECS))
