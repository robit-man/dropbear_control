"""Passive ESP32 observation and fail-closed frontend control admission.

The observation path opens each configured tty with ``O_RDONLY`` and never
owns a write-capable file descriptor.  It consumes the five-value CSV stream
already emitted by the deployed Dropbear firmware.  Opening a USB UART can
still affect modem-control lines in a driver, so hardware observation remains
explicitly opt-in through ``DROPBEAR_OBSERVATION_ENABLE=1``.

The control gate only proves that the browser completed a short, expiring
three-stage acknowledgement.  It does not provide a physical transport and
cannot enable actuator output.
"""

from __future__ import annotations

import hmac
import math
import os
import secrets
import select
import stat
import termios
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


OBSERVATION_SCHEMA = "dropbear-passive-observation-v1"
CONTROL_GATE_SCHEMA = "dropbear-frontend-control-gate-v1"
CONTROL_COMMAND_SCHEMA = "dropbear-hardware-command-v1"
MAX_LINE_BYTES = 256
MAX_BUFFER_BYTES = 4096
DEFAULT_MAX_SAMPLE_AGE_MS = 250.0

JOINT_BINDINGS = {
    "left": (
        ("left_outer_calf", "outer_calf", "0x141", "LL_Revolute81", 14),
        ("left_inner_calf", "inner_calf", "0x142", "LL_Revolute67", 27),
        ("left_hip_pitch", "hip_pitch", "0x146", "LL_hip_joint", 26),
        ("left_knee", "knee", "0x145", "LL_knee_actuator_joint", 25),
        ("left_hip_roll", "hip_roll", "0x14A", "PG_left_leg_pitch", 33),
    ),
    "right": (
        ("right_outer_calf", "outer_calf", "0x144", "RL_Revolute81", 14),
        ("right_inner_calf", "inner_calf", "0x143", "RL_Revolute67", 27),
        ("right_hip_pitch", "hip_pitch", "0x147", "RL_hip_joint", 26),
        ("right_knee", "knee", "0x148", "RL_knee_actuator_joint", 25),
        ("right_hip_roll", "hip_roll", "0x14B", "PG_right_leg_pitch", 33),
    ),
}

MOTOR_BINDINGS = {
    "left": (
        ("left_outer_calf", "0x141"),
        ("left_inner_calf", "0x142"),
        ("left_hip_pitch", "0x146"),
        ("left_knee", "0x145"),
        ("left_hip_yaw", "0x149"),
        ("left_hip_roll", "0x14A"),
    ),
    "right": (
        ("right_outer_calf", "0x144"),
        ("right_inner_calf", "0x143"),
        ("right_hip_pitch", "0x147"),
        ("right_knee", "0x148"),
        ("right_hip_yaw", "0x14C"),
        ("right_hip_roll", "0x14B"),
    ),
}


def unavailable_motor_observations(side: str) -> dict[str, dict[str, Any]]:
    """Describe every motor-native channel without substituting sensor data."""

    return {
        canonical_name: {
            "canonicalName": canonical_name,
            "canId": can_id,
            "positionDeg": None,
            "available": False,
            "source": "motor_native_unavailable",
            "status": "not_emitted_by_deployed_firmware",
        }
        for canonical_name, can_id in MOTOR_BINDINGS[side]
    }


def _motor_observations(
    side: str,
    values: list[float | None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build motor-native observations without filling gaps from AS5600 data."""

    if values is None:
        return unavailable_motor_observations(side)
    observations = unavailable_motor_observations(side)
    for (canonical_name, _), value in zip(MOTOR_BINDINGS[side], values):
        if value is None:
            continue
        observations[canonical_name] = {
            **observations[canonical_name],
            "positionDeg": value,
            "available": True,
            "source": "rmd_v44_multi_turn_angle",
            "status": "measured",
        }
    return observations

KNOWN_JOINTS = frozenset(
    binding[0]
    for bindings in JOINT_BINDINGS.values()
    for binding in bindings
) | {"left_hip_yaw", "right_hip_yaw"}

SAFETY_ACKNOWLEDGEMENTS = (
    "robot_supported",
    "area_clear",
    "estop_ready",
    "read_only_validated",
    "limits_reviewed",
)


class ObservationParseError(ValueError):
    """The ESP32 line is not an admissible joint observation."""


class ControlGateError(ValueError):
    """A frontend arming request failed closed."""


def parse_esp32_telemetry_line(side: str, line: str) -> dict[str, Any]:
    """Decode legacy AS5600 CSV or one versioned dual-angle record.

    Legacy firmware emits five external angles. ``DB2`` adds the controller
    millisecond counter and six motor-native multi-turn angles in the order
    outer calf, inner calf, hip pitch, knee, hip yaw, hip roll. ``NA`` means
    that a verified motor response was unavailable for that sample.
    """

    if side not in JOINT_BINDINGS:
        raise ObservationParseError("side must be left or right")
    if not isinstance(line, str) or not line or len(line.encode("utf-8")) > MAX_LINE_BYTES:
        raise ObservationParseError("observation line is empty or too long")
    fields = [field.strip() for field in line.strip().split(",")]
    extended = fields[0] == "DB2"
    if extended:
        if len(fields) != 13:
            raise ObservationParseError("DB2 observation line must contain exactly thirteen fields")
        try:
            controller_millis = int(fields[1])
        except ValueError as error:
            raise ObservationParseError("DB2 controller time must be an unsigned integer") from error
        if not 0 <= controller_millis <= 0xFFFFFFFF:
            raise ObservationParseError("DB2 controller time must fit uint32")
        external_fields = fields[2:7]
        motor_fields = fields[7:13]
    else:
        if len(fields) != 5:
            raise ObservationParseError("legacy observation line must contain exactly five values")
        controller_millis = None
        external_fields = fields
        motor_fields = None
    try:
        values = [float(field) for field in external_fields]
    except ValueError as error:
        raise ObservationParseError("observation values must be numeric") from error
    if not all(math.isfinite(value) for value in values):
        raise ObservationParseError("observation values must be finite")
    if not all(0.0 <= value <= 360.0 for value in values):
        raise ObservationParseError("normalized observation values must be within 0..360 degrees")

    joints = {
        canonical_name: {
            "canonicalName": canonical_name,
            "firmwareJoint": firmware_joint,
            "canId": can_id,
            "usdJoint": usd_joint,
            "sensorGpio": sensor_gpio,
            "positionDeg": value,
            "source": "external_absolute",
            "evidence": "unverified_deployed_firmware_observation",
        }
        for (canonical_name, firmware_joint, can_id, usd_joint, sensor_gpio), value
        in zip(JOINT_BINDINGS[side], values)
    }
    motor_values: list[float | None] | None = None
    if motor_fields is not None:
        motor_values = []
        for field in motor_fields:
            if field == "NA":
                motor_values.append(None)
                continue
            try:
                value = float(field)
            except ValueError as error:
                raise ObservationParseError("DB2 motor values must be numeric or NA") from error
            if not math.isfinite(value) or abs(value) > 1_000_000.0:
                raise ObservationParseError("DB2 motor value exceeds the telemetry sanity bound")
            motor_values.append(value)
    return {
        "format": "DB2" if extended else "legacy5",
        "controllerMillis": controller_millis,
        "joints": joints,
        "motorJoints": _motor_observations(side, motor_values),
    }


def parse_esp32_csv_line(side: str, line: str) -> dict[str, dict[str, Any]]:
    """Compatibility wrapper returning external sensor joints only."""

    return parse_esp32_telemetry_line(side, line)["joints"]


@dataclass
class _SideState:
    side: str
    configured_path: str | None
    resolved_path: str | None = None
    state: str = "disabled"
    sequence: int = 0
    received_monotonic_ns: int = 0
    raw_line: str = ""
    joints: dict[str, dict[str, Any]] = field(default_factory=dict)
    motor_joints: dict[str, dict[str, Any]] = field(default_factory=dict)
    telemetry_format: str = ""
    controller_millis: int | None = None
    decoded_lines: int = 0
    rejected_lines: int = 0
    overflow_events: int = 0
    read_errors: int = 0
    error: str = ""


class _PassiveTTYReader:
    """One-shot O_RDONLY tty reader with no transmit method or descriptor."""

    def __init__(
        self,
        side: str,
        path: str,
        on_line: Callable[[str, str, int], None],
        on_state: Callable[[str, str, str, str | None], None],
    ) -> None:
        self.side = side
        self.path = path
        self.on_line = on_line
        self.on_state = on_state
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fd: int | None = None

    @staticmethod
    def _configure_115200_8n1(fd: int) -> None:
        attributes = termios.tcgetattr(fd)
        attributes[0] = termios.IGNBRK
        attributes[1] = 0
        attributes[2] = (
            attributes[2]
            & ~(termios.PARENB | termios.CSTOPB | termios.CSIZE | termios.HUPCL)
        ) | termios.CS8 | termios.CREAD | termios.CLOCAL
        attributes[3] = 0
        attributes[4] = termios.B115200
        attributes[5] = termios.B115200
        attributes[6][termios.VMIN] = 0
        attributes[6][termios.VTIME] = 1
        termios.tcsetattr(fd, termios.TCSANOW, attributes)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            name=f"dropbear-passive-{self.side}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        fd = self._fd
        self._fd = None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        try:
            resolved = os.path.realpath(self.path)
            mode = os.stat(resolved).st_mode
            if not stat.S_ISCHR(mode):
                raise OSError(f"configured path is not a character device: {resolved}")
            fd = os.open(
                self.path,
                os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK | os.O_CLOEXEC,
            )
            self._fd = fd
            self._configure_115200_8n1(fd)
            self.on_state(self.side, "observing", "", resolved)
        except (OSError, termios.error) as error:
            self.on_state(self.side, "error", str(error), None)
            return

        buffer = bytearray()
        try:
            while not self._stop.is_set():
                try:
                    readable, _, _ = select.select([fd], [], [], 0.1)
                    if not readable:
                        continue
                    chunk = os.read(fd, 1024)
                except (OSError, ValueError) as error:
                    if not self._stop.is_set():
                        self.on_state(self.side, "error", str(error), None)
                    return
                if not chunk:
                    continue
                buffer.extend(chunk)
                if len(buffer) > MAX_BUFFER_BYTES:
                    buffer.clear()
                    self.on_state(self.side, "overflow", "serial receive buffer exceeded limit", None)
                    continue
                while b"\n" in buffer:
                    raw, _, remainder = buffer.partition(b"\n")
                    buffer = bytearray(remainder)
                    line = raw.rstrip(b"\r").decode("ascii", errors="replace")
                    self.on_line(self.side, line, time.monotonic_ns())
        finally:
            current = self._fd
            self._fd = None
            if current is not None:
                try:
                    os.close(current)
                except OSError:
                    pass


class HardwareObservationManager:
    """Own two passive readers and publish the freshest exact-side samples."""

    def __init__(
        self,
        left_path: str | None = None,
        right_path: str | None = None,
        *,
        enabled: bool = False,
        maximum_sample_age_ms: float = DEFAULT_MAX_SAMPLE_AGE_MS,
        reader_factory: Callable[..., _PassiveTTYReader] = _PassiveTTYReader,
    ) -> None:
        self.enabled = bool(enabled)
        self.maximum_sample_age_ms = float(maximum_sample_age_ms)
        self._lock = threading.RLock()
        self._started = False
        self._states = {
            "left": _SideState("left", left_path),
            "right": _SideState("right", right_path),
        }
        self._readers: dict[str, _PassiveTTYReader] = {}
        self._reader_factory = reader_factory

    @classmethod
    def from_environment(cls) -> "HardwareObservationManager":
        enabled = os.environ.get("DROPBEAR_OBSERVATION_ENABLE", "0") == "1"
        try:
            maximum_age = float(
                os.environ.get(
                    "DROPBEAR_OBSERVATION_MAX_AGE_MS",
                    str(DEFAULT_MAX_SAMPLE_AGE_MS),
                )
            )
        except ValueError:
            maximum_age = DEFAULT_MAX_SAMPLE_AGE_MS
        return cls(
            os.environ.get("DROPBEAR_OBSERVATION_LEFT") or None,
            os.environ.get("DROPBEAR_OBSERVATION_RIGHT") or None,
            enabled=enabled,
            maximum_sample_age_ms=maximum_age,
        )

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            if not self.enabled:
                for state in self._states.values():
                    state.state = "disabled"
                return
            if not math.isfinite(self.maximum_sample_age_ms) or self.maximum_sample_age_ms <= 0:
                for state in self._states.values():
                    state.state = "error"
                    state.error = "maximum sample age must be a positive finite value"
                return
            for side, state in self._states.items():
                if not state.configured_path:
                    state.state = "error"
                    state.error = f"DROPBEAR_OBSERVATION_{side.upper()} is required"
                    continue
                state.state = "opening"
                reader = self._reader_factory(
                    side,
                    state.configured_path,
                    self.ingest_line,
                    self._reader_state,
                )
                self._readers[side] = reader
                reader.start()

    def stop(self) -> None:
        with self._lock:
            readers = tuple(self._readers.values())
            self._readers.clear()
            self._started = False
        for reader in readers:
            reader.stop()
        with self._lock:
            for state in self._states.values():
                if state.state not in {"disabled", "error"}:
                    state.state = "stopped"

    def _reader_state(
        self,
        side: str,
        state_name: str,
        error: str,
        resolved_path: str | None,
    ) -> None:
        with self._lock:
            state = self._states[side]
            if state_name == "overflow":
                state.overflow_events += 1
                state.error = error
                return
            if state_name == "error":
                state.read_errors += 1
            state.state = state_name
            state.error = error
            if resolved_path:
                state.resolved_path = resolved_path

    def ingest_line(
        self,
        side: str,
        line: str,
        received_monotonic_ns: int | None = None,
    ) -> bool:
        """Ingest a line; public to support replay and isolated tests."""

        received_ns = time.monotonic_ns() if received_monotonic_ns is None else int(received_monotonic_ns)
        try:
            record = parse_esp32_telemetry_line(side, line)
        except ObservationParseError:
            with self._lock:
                self._states[side].rejected_lines += 1
            return False
        with self._lock:
            state = self._states[side]
            state.sequence += 1
            state.received_monotonic_ns = received_ns
            state.raw_line = line.strip()
            state.joints = record["joints"]
            state.motor_joints = record["motorJoints"]
            state.telemetry_format = record["format"]
            state.controller_millis = record["controllerMillis"]
            state.decoded_lines += 1
            state.state = "observing"
            state.error = ""
        return True

    def snapshot(self, now_ns: int | None = None) -> dict[str, Any]:
        current_ns = time.monotonic_ns() if now_ns is None else int(now_ns)
        with self._lock:
            sides: dict[str, Any] = {}
            fresh_count = 0
            for side, state in self._states.items():
                age_ms = (
                    max(0.0, (current_ns - state.received_monotonic_ns) / 1_000_000.0)
                    if state.received_monotonic_ns
                    else None
                )
                fresh = bool(
                    state.joints
                    and age_ms is not None
                    and age_ms <= self.maximum_sample_age_ms
                    and state.state == "observing"
                )
                fresh_count += int(fresh)
                sides[side] = {
                    "state": state.state,
                    "configuredPath": state.configured_path or "",
                    "resolvedPath": state.resolved_path or "",
                    "fresh": fresh,
                    "ageMs": age_ms,
                    "sequence": state.sequence,
                    "receivedMonotonicNs": state.received_monotonic_ns,
                    "rawLine": state.raw_line,
                    "telemetryFormat": state.telemetry_format,
                    "controllerMillis": state.controller_millis,
                    "joints": dict(state.joints) if fresh else {},
                    "motorJoints": dict(state.motor_joints) if fresh and state.motor_joints
                    else unavailable_motor_observations(side),
                    "decodedLines": state.decoded_lines,
                    "rejectedLines": state.rejected_lines,
                    "overflowEvents": state.overflow_events,
                    "readErrors": state.read_errors,
                    "error": state.error,
                }
            if not self.enabled:
                overall = "disabled"
            elif fresh_count == 2:
                overall = "fresh"
            elif fresh_count == 1:
                overall = "degraded"
            elif any(state["state"] == "error" for state in sides.values()):
                overall = "error"
            elif any(state["sequence"] for state in sides.values()):
                overall = "stale"
            else:
                overall = "waiting"
            return {
                "schema": OBSERVATION_SCHEMA,
                "mode": "read_only",
                "state": overall,
                "enabled": self.enabled,
                "writeCapable": False,
                "txBytes": 0,
                "baudrate": 115200,
                "maximumSampleAgeMs": self.maximum_sample_age_ms,
                "complete": fresh_count == 2,
                "unobservedJoints": ["left_hip_yaw", "right_hip_yaw"],
                "sides": sides,
            }


class HardwareControlGate:
    """Expiring three-stage browser acknowledgement with no physical backend."""

    challenge_lifetime_ns = 120_000_000_000
    lease_lifetime_ns = 60_000_000_000

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stage = 0
        self._challenge = ""
        self._challenge_expires_ns = 0
        self._lease_token = ""
        self._lease_expires_ns = 0

    def _reset_locked(self) -> None:
        self._stage = 0
        self._challenge = ""
        self._challenge_expires_ns = 0
        self._lease_token = ""
        self._lease_expires_ns = 0

    def revoke(self) -> dict[str, Any]:
        with self._lock:
            self._reset_locked()
            return self._snapshot_locked(time.monotonic_ns())

    def _expire_locked(self, now_ns: int) -> None:
        if self._stage in {1, 2} and now_ns >= self._challenge_expires_ns:
            self._reset_locked()
        elif self._stage == 3 and now_ns >= self._lease_expires_ns:
            self._reset_locked()

    def _snapshot_locked(self, now_ns: int) -> dict[str, Any]:
        self._expire_locked(now_ns)
        deadline = self._lease_expires_ns if self._stage == 3 else self._challenge_expires_ns
        return {
            "schema": CONTROL_GATE_SCHEMA,
            "state": "frontend_armed" if self._stage == 3 else "locked",
            "stage": self._stage,
            "frontendArmed": self._stage == 3,
            "hardwareOutputEnabled": False,
            "physicalTransport": "not_installed",
            "expiresInMs": max(0, (deadline - now_ns) // 1_000_000) if deadline else 0,
            "requiredAcknowledgements": list(SAFETY_ACKNOWLEDGEMENTS),
        }

    def snapshot(self, now_ns: int | None = None) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked(time.monotonic_ns() if now_ns is None else int(now_ns))

    def advance(self, payload: Mapping[str, Any], now_ns: int | None = None) -> dict[str, Any]:
        current_ns = time.monotonic_ns() if now_ns is None else int(now_ns)
        requested_stage = payload.get("stage")
        with self._lock:
            self._expire_locked(current_ns)
            if requested_stage == 1 and self._stage == 0:
                self._challenge = secrets.token_urlsafe(24)
                self._challenge_expires_ns = current_ns + self.challenge_lifetime_ns
                self._stage = 1
                return {**self._snapshot_locked(current_ns), "challenge": self._challenge}
            if requested_stage == 2 and self._stage == 1:
                if not hmac.compare_digest(str(payload.get("challenge", "")), self._challenge):
                    self._reset_locked()
                    raise ControlGateError("arming challenge did not match; sequence reset")
                acknowledgements = payload.get("acknowledgements")
                if not isinstance(acknowledgements, Mapping) or any(
                    acknowledgements.get(key) is not True for key in SAFETY_ACKNOWLEDGEMENTS
                ):
                    self._reset_locked()
                    raise ControlGateError("every safety consideration must be explicitly acknowledged; sequence reset")
                self._stage = 2
                return {**self._snapshot_locked(current_ns), "challenge": self._challenge}
            if requested_stage == 3 and self._stage == 2:
                if not hmac.compare_digest(str(payload.get("challenge", "")), self._challenge):
                    self._reset_locked()
                    raise ControlGateError("arming challenge did not match; sequence reset")
                if payload.get("confirm") is not True:
                    self._reset_locked()
                    raise ControlGateError("final control-channel confirmation is required; sequence reset")
                self._stage = 3
                self._challenge = ""
                self._challenge_expires_ns = 0
                self._lease_token = secrets.token_urlsafe(32)
                self._lease_expires_ns = current_ns + self.lease_lifetime_ns
                return {**self._snapshot_locked(current_ns), "leaseToken": self._lease_token}
            self._reset_locked()
            raise ControlGateError("arming stages must be completed once, in order; sequence reset")

    def inspect_command(self, payload: Mapping[str, Any], now_ns: int | None = None) -> dict[str, Any]:
        current_ns = time.monotonic_ns() if now_ns is None else int(now_ns)
        with self._lock:
            self._expire_locked(current_ns)
            if self._stage != 3 or not self._lease_token:
                raise ControlGateError("frontend control channel is locked")
            if not hmac.compare_digest(str(payload.get("leaseToken", "")), self._lease_token):
                self._reset_locked()
                raise ControlGateError("control lease did not match; channel relocked")
            if payload.get("schema") != CONTROL_COMMAND_SCHEMA:
                raise ControlGateError("unsupported hardware command schema")
            if payload.get("jointName") not in KNOWN_JOINTS:
                raise ControlGateError("unknown canonical joint")
            if payload.get("mode") not in {"disable", "joint_position"}:
                raise ControlGateError("unsupported hardware command mode")
            if payload.get("mode") == "joint_position":
                value = payload.get("valueSi")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ControlGateError("joint position must be a finite SI value")
            return {
                "schema": CONTROL_COMMAND_SCHEMA,
                "accepted": False,
                "frontendGate": "passed",
                "hardwareOutputEnabled": False,
                "disposition": "PHYSICAL_TRANSPORT_LOCKED",
                "detail": "frontend acknowledgement passed; no physical command transport is installed",
            }


__all__ = [
    "CONTROL_COMMAND_SCHEMA",
    "CONTROL_GATE_SCHEMA",
    "HardwareControlGate",
    "HardwareObservationManager",
    "JOINT_BINDINGS",
    "OBSERVATION_SCHEMA",
    "ObservationParseError",
    "SAFETY_ACKNOWLEDGEMENTS",
    "parse_esp32_csv_line",
]
