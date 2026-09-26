"""ESP32 observation, bounded diagnostic queries, and control admission.

The continuous observation path owns only ``O_RDONLY`` descriptors. Short-lived
``O_WRONLY`` descriptors may send an audited allowlist of version, health, and
stream-selection requests. No motion command is admitted through this class.

The control gate only proves that the browser completed a short, expiring
three-stage acknowledgement.  It does not provide a physical transport and
cannot enable actuator output.
"""

from __future__ import annotations

import hmac
import math
import os
import re
import secrets
import select
import stat
import termios
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


OBSERVATION_SCHEMA = "dropbear-hardware-observation-v2"
CONTROL_GATE_SCHEMA = "dropbear-frontend-control-gate-v1"
CONTROL_COMMAND_SCHEMA = "dropbear-hardware-command-v1"
MAX_LINE_BYTES = 256
MAX_BUFFER_BYTES = 4096
DEFAULT_MAX_SAMPLE_AGE_MS = 250.0
RAW_SERIAL_TAIL_LINES = 160
# Some legacy builds flood USB at roughly 600 lines/s despite documenting a
# 50 Hz stream. The browser polls at 10 Hz, so admitting at most 50 complete
# records/s preserves the controller's intended motion bandwidth while keeping
# legacy serial floods off the render budget.
MIN_ADMITTED_SAMPLE_INTERVAL_NS = 20_000_000
DIAGNOSTIC_COMMANDS = frozenset({
    "version", "/version", "capabilities", "health", "status", "chirality",
    "mac", "saved", "help", "observe on", "observe off", "config show",
    "can bus", "can registers", "can scan",
    "can poll on", "can poll off", "can poll status",
})
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

MOTOR_PROFILE_METADATA = {
    "calf": {
        "motorModel": "MyActuator RMD-X8 Pro 1:9",
        "motorFirmware": "V1.7",
        "motorProtocol": "rmd-x8-v1.7",
        "gearRatio": 9.0,
        "angleReference": "output_shaft",
        "anglePayload": "signed56_le_bytes_1_7",
    },
    "leg": {
        "motorModel": "MyActuator RMD-X10 1:7",
        "motorFirmware": "V4.2+",
        "motorProtocol": "rmd-x10-v4.2+",
        "gearRatio": 7.0,
        "angleReference": "output_shaft",
        "anglePayload": "signed32_le_bytes_4_7",
    },
}


def _motor_profile_metadata(canonical_name: str) -> dict[str, Any]:
    profile = MOTOR_PROFILE_METADATA[
        "calf" if canonical_name.endswith(("outer_calf", "inner_calf")) else "leg"
    ]
    return dict(profile)


def unavailable_motor_observations(
    side: str,
    status: str = "not_emitted_by_deployed_firmware",
) -> dict[str, dict[str, Any]]:
    """Describe every motor-native channel without substituting sensor data."""

    return {
        canonical_name: {
            **_motor_profile_metadata(canonical_name),
            "canonicalName": canonical_name,
            "canId": can_id,
            "positionDeg": None,
            "available": False,
            "source": "motor_native_unavailable",
            "status": status,
            "fresh": False,
            "controlPositionDeg": None,
            "controlAvailable": False,
            "controlSource": "unavailable",
            "alignmentFault": False,
        }
        for canonical_name, can_id in MOTOR_BINDINGS[side]
    }


def _motor_observations(
    side: str,
    values: list[float | None] | None = None,
    control_values: list[float | None] | None = None,
    *,
    fresh_mask: int = 0,
    control_mask: int = 0,
    alignment_fault_mask: int = 0,
) -> dict[str, dict[str, Any]]:
    """Build motor-native observations without filling gaps from AS5600 data."""

    if values is None:
        return unavailable_motor_observations(side)
    observations = unavailable_motor_observations(side)
    for slot, ((canonical_name, _), value) in enumerate(zip(MOTOR_BINDINGS[side], values)):
        control_value = control_values[slot] if control_values is not None else None
        profile = _motor_profile_metadata(canonical_name)
        profile_source = (
            "rmd_x8_v17_multi_turn_angle"
            if profile["motorProtocol"] == "rmd-x8-v1.7"
            else "rmd_x10_v42_multi_turn_angle"
        )
        observations[canonical_name] = {
            **observations[canonical_name],
            "positionDeg": value,
            "available": value is not None,
            "source": profile_source if value is not None else "motor_native_unavailable",
            "status": "measured" if value is not None else "not_fresh",
            "fresh": bool(fresh_mask & (1 << slot)) if control_values is not None else value is not None,
            "controlPositionDeg": control_value,
            "controlAvailable": bool(control_mask & (1 << slot)) and control_value is not None,
            "controlSource": f"{profile_source}_as5600_boot_aligned" if control_value is not None else "unavailable",
            "alignmentFault": bool(alignment_fault_mask & (1 << slot)),
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


def _parse_optional_motor_values(fields: list[str], schema: str) -> list[float | None]:
    values: list[float | None] = []
    for field in fields:
        if field == "NA":
            values.append(None)
            continue
        try:
            value = float(field)
        except ValueError as error:
            raise ObservationParseError(f"{schema} motor values must be numeric or NA") from error
        if not math.isfinite(value) or abs(value) > 1_000_000.0:
            raise ObservationParseError(f"{schema} motor value exceeds the telemetry sanity bound")
        values.append(value)
    return values


def parse_esp32_telemetry_line(side: str, line: str) -> dict[str, Any]:
    """Decode legacy AS5600 CSV, DB2 raw CAN, or DB3 aligned CAN telemetry.

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
    schema = fields[0]
    extended = schema in {"DB2", "DB3"}
    control_fields: list[str] | None = None
    fresh_mask = control_mask = alignment_fault_mask = 0
    if extended:
        expected_fields = 22 if schema == "DB3" else 13
        if len(fields) != expected_fields:
            raise ObservationParseError(
                f"{schema} observation line must contain exactly {expected_fields} fields"
            )
        try:
            controller_millis = int(fields[1])
        except ValueError as error:
            raise ObservationParseError(f"{schema} controller time must be an unsigned integer") from error
        if not 0 <= controller_millis <= 0xFFFFFFFF:
            raise ObservationParseError(f"{schema} controller time must fit uint32")
        external_fields = fields[2:7]
        motor_fields = fields[7:13]
        if schema == "DB3":
            control_fields = fields[13:19]
            try:
                fresh_mask, control_mask, alignment_fault_mask = map(int, fields[19:22])
            except ValueError as error:
                raise ObservationParseError("DB3 masks must be unsigned integers") from error
            if any(mask < 0 or mask > 0x3F for mask in (
                fresh_mask, control_mask, alignment_fault_mask,
            )):
                raise ObservationParseError("DB3 masks must fit six motor bits")
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
    control_values: list[float | None] | None = None
    if motor_fields is not None:
        motor_values = _parse_optional_motor_values(motor_fields, schema)
    if control_fields is not None:
        control_values = _parse_optional_motor_values(control_fields, schema)
    return {
        "format": schema if extended else "legacy5",
        "controllerMillis": controller_millis,
        "joints": joints,
        "motorJoints": _motor_observations(
            side,
            motor_values,
            control_values,
            fresh_mask=fresh_mask,
            control_mask=control_mask,
            alignment_fault_mask=alignment_fault_mask,
        ),
        "masks": {
            "motorFresh": fresh_mask,
            "motorControl": control_mask,
            "alignmentFault": alignment_fault_mask,
        },
    }


def parse_firmware_version_line(side: str, line: str) -> dict[str, Any]:
    fields = [field.strip() for field in line.strip().split(",", 5)]
    if len(fields) != 6 or fields[0] != "DBV1":
        raise ObservationParseError("firmware version line must use DBV1")
    expected_role = f"{side.upper()}LEG"
    if fields[1] != expected_role:
        raise ObservationParseError(f"DBV1 role must be {expected_role}")
    if fields[3] not in {"DB1", "LEGACY"}:
        raise ObservationParseError("unsupported command protocol")
    if fields[4] not in {"legacy5", "DB2", "DB3"}:
        raise ObservationParseError("unsupported telemetry protocol")
    capabilities = tuple(item for item in fields[5].split(";") if item)
    if not fields[2] or not capabilities:
        raise ObservationParseError("DBV1 firmware and capabilities are required")
    return {
        "schema": "DBV1",
        "role": fields[1],
        "firmware": fields[2],
        "commandProtocol": fields[3],
        "telemetryProtocol": fields[4],
        "capabilities": capabilities,
    }


def parse_firmware_health_line(side: str, line: str) -> dict[str, Any]:
    fields = [field.strip() for field in line.strip().split(",")]
    if len(fields) != 15 or fields[0] != "DBH1":
        raise ObservationParseError("firmware health line must contain fifteen DBH1 fields")
    expected_role = f"{side.upper()}LEG"
    if fields[1] != expected_role:
        raise ObservationParseError(f"DBH1 role must be {expected_role}")
    if fields[3] not in {"ok", "warn", "degraded", "fault"}:
        raise ObservationParseError("DBH1 overall state is invalid")
    try:
        numeric = [int(value) for value in fields[2:3] + fields[4:]]
    except ValueError as error:
        raise ObservationParseError("DBH1 numeric fields must be integers") from error
    if any(value < 0 for value in numeric):
        raise ObservationParseError("DBH1 numeric fields must be unsigned")
    return {
        "schema": "DBH1",
        "role": fields[1],
        "controllerMillis": numeric[0],
        "overall": fields[3],
        "runtimeReady": bool(numeric[1]),
        "canReady": bool(numeric[2]),
        "sensorFreshMask": numeric[3],
        "motorFreshMask": numeric[4],
        "motorControlMask": numeric[5],
        "alignmentFaultMask": numeric[6],
        "motorQueries": numeric[7],
        "motorResponses": numeric[8],
        "motorQueryFailures": numeric[9],
        "malformedMotorResponses": numeric[10],
        "canConsecutiveFailures": numeric[11],
    }


def parse_firmware_configuration_line(side: str, line: str) -> dict[str, Any]:
    """Decode one bounded DBCFG1 configuration record."""

    fields = [field.strip() for field in line.strip().split(",")]
    expected_role = f"{side.upper()}LEG"
    if len(fields) < 3 or fields[0] != "DBCFG1" or fields[1] != expected_role:
        raise ObservationParseError("DBCFG1 role or prefix is invalid")
    kind = fields[2]
    try:
        if kind == "end" and len(fields) == 3:
            return {"kind": kind, "value": True}
        if kind == "meta" and len(fields) == 10:
            max_torque = float(fields[5])
            if (fields[3] not in {"0", "1"} or fields[4] not in {"standalone", "hyperspawn"}
                    or fields[6] not in {"0", "1"} or fields[7] not in {"0", "1"}
                    or fields[8] not in {"0", "1"}
                    or not math.isfinite(max_torque) or not 0.0 < max_torque <= 100.0):
                raise ValueError("max torque out of range")
            return {"kind": kind, "value": {
                "configured": bool(int(fields[3])),
                "operatingMode": fields[4],
                "maxTorque": max_torque,
                "legacyUnaddressedCommands": bool(int(fields[6])),
                "rawMode": bool(int(fields[7])),
                "rebootRequired": bool(int(fields[8])),
                "firmwareVersion": fields[9],
            }}
        if kind == "hyperspawn" and len(fields) == 7:
            scale = float(fields[6])
            timeout = int(fields[3])
            if (fields[4] not in {"0", "1"} or fields[5] not in {"0", "1"}
                    or not 50 <= timeout <= 10000 or not math.isfinite(scale)
                    or not 0.0001 < scale <= 1000.0):
                raise ValueError("hyperspawn values out of range")
            return {"kind": kind, "value": {
                "timeoutMs": timeout,
                "legacyBroadcast": bool(int(fields[4])),
                "autoArm": bool(int(fields[5])),
                "positionUnitsPerDegree": scale,
            }}
        if kind in {"offsets", "directions"} and len(fields) == 8:
            names = ("outer_calf", "inner_calf", "hip_pitch", "knee", "hip_roll")
            if kind == "offsets":
                values = [int(value) for value in fields[3:]]
                if not all(-720 <= value <= 720 for value in values):
                    raise ValueError("offset out of range")
            else:
                # Firmware direction ordering follows motor command order:
                # calves, knee, hip pitch, hip roll.
                names = ("outer_calf", "inner_calf", "knee", "hip_pitch", "hip_roll")
                values = [float(value) for value in fields[3:]]
                if not all(value in {-1.0, 1.0} for value in values):
                    raise ValueError("direction is not +/-1")
            return {"kind": kind, "value": dict(zip(names, values))}
        if kind == "constraint" and len(fields) == 6:
            joint = fields[3]
            if joint not in {"outer_calf", "inner_calf", "knee", "hip_pitch", "hip_yaw", "hip_roll"}:
                raise ValueError("unknown constraint joint")
            minimum, maximum = int(fields[4]), int(fields[5])
            if minimum > maximum:
                raise ValueError("constraint minimum exceeds maximum")
            return {"kind": kind, "joint": joint, "value": {"min": minimum, "max": maximum}}
    except ValueError as error:
        raise ObservationParseError(f"invalid DBCFG1 {kind} record") from error
    raise ObservationParseError(f"unsupported DBCFG1 record kind: {kind}")


def parse_firmware_calibration_line(side: str, line: str) -> dict[str, Any]:
    fields = [field.strip() for field in line.strip().split(",")]
    expected_role = f"{side.upper()}LEG"
    if len(fields) != 9 or fields[0] != "DBCAL1" or fields[1] != expected_role:
        raise ObservationParseError("DBCAL1 record is invalid")
    if ((fields[2], fields[3]) not in {("ok", "offsets"), ("error", "valid_counts")}):
        raise ObservationParseError("DBCAL1 state is invalid")
    try:
        values = [int(value) for value in fields[4:]]
    except ValueError as error:
        raise ObservationParseError("DBCAL1 values must be integers") from error
    names = ("outer_calf", "inner_calf", "hip_pitch", "knee", "hip_roll")
    return {
        "status": fields[2],
        "kind": fields[3],
        "values": dict(zip(names, values)),
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
    raw_lines: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=RAW_SERIAL_TAIL_LINES)
    )
    firmware_family: str = "unknown"
    firmware_version: str = ""
    command_protocol: str = ""
    advertised_telemetry_protocol: str = ""
    capabilities: tuple[str, ...] = ()
    health: dict[str, Any] = field(default_factory=dict)
    configuration: dict[str, Any] = field(default_factory=lambda: {"constraints": {}})
    calibration: dict[str, Any] = field(default_factory=dict)
    observation_streaming: bool = False
    diagnostic_tx_bytes: int = 0
    last_diagnostic_command: str = ""
    last_diagnostic_error: str = ""


def _passive_firmware_identity(line: str, telemetry_format: str = "") -> tuple[str, str]:
    """Infer only what the received bytes prove; never invent a build version."""

    if telemetry_format == "legacy5":
        return "legacy-five-angle", "exact-build-unknown"
    if telemetry_format in {"DB2", "DB3"}:
        return f"dropbear-observation-{telemetry_format.lower()}", f"protocol-{telemetry_format.lower()}"
    match = re.search(
        r"(?:firmware|fw|version)[|:= ]+([A-Za-z0-9._+-]{1,64})",
        line,
        flags=re.IGNORECASE,
    )
    if match:
        return "self-reported", match.group(1)
    if "DROPBEAR UNIVERSAL" in line.upper() or "BEHEMOTH" in line.upper():
        return "dropbear-universal-behemoth", "self-identified-no-version"
    return "unknown", ""


def _looks_like_telemetry_bytes(raw: bytes) -> bool:
    cleaned = raw.rstrip(b"\r").strip()
    if cleaned.startswith((b"DB2,", b"DB3,")):
        return True
    fields = cleaned.split(b",")
    if len(fields) != 5:
        return False
    try:
        return all(math.isfinite(float(field)) for field in fields)
    except ValueError:
        return False


class _PassiveTTYReader:
    """Reconnectable O_RDONLY tty reader with no transmit method or descriptor."""

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
        while not self._stop.is_set():
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
                self.on_state(self.side, "reconnecting", str(error), None)
                self._stop.wait(0.5)
                continue

            buffer = bytearray()
            disconnected = False
            last_dispatched_ns = 0
            try:
                while not self._stop.is_set():
                    readable, _, _ = select.select([fd], [], [], 0.1)
                    if not readable:
                        continue
                    chunk = os.read(fd, 1024)
                    if not chunk:
                        raise OSError("serial device returned EOF")
                    buffer.extend(chunk)
                    if len(buffer) > MAX_BUFFER_BYTES:
                        buffer.clear()
                        self.on_state(self.side, "overflow", "serial receive buffer exceeded limit", None)
                        continue
                    if b"\n" in buffer:
                        records = buffer.split(b"\n")
                        buffer = bytearray(records[-1])
                        received_ns = time.monotonic_ns()
                        complete_records = records[:-1]
                        diagnostic_records = [
                            raw for raw in complete_records
                            if not _looks_like_telemetry_bytes(raw)
                        ]
                        # Preserve identity/health acknowledgements even when a
                        # fast DB3 stream shares the same kernel read.
                        # A complete DBCFG1 snapshot is 11 short records; keep
                        # every structured config/calibration record even when
                        # they arrive in one USB read, while other human/CAN
                        # diagnostics retain the bounded tail behavior.
                        structured_records = [
                            raw for raw in diagnostic_records
                            if raw.rstrip(b"\r").strip().startswith((b"DBCFG1,", b"DBCAL1,"))
                        ]
                        for raw in [*structured_records, *diagnostic_records[-8:]]:
                            line = raw.rstrip(b"\r").decode("ascii", errors="replace")
                            self.on_line(self.side, line, received_ns)
                        if received_ns - last_dispatched_ns >= MIN_ADMITTED_SAMPLE_INTERVAL_NS:
                            # Only the newest complete record matters for live
                            # state; coalescing a USB read avoids parsing an
                            # obsolete burst from legacy high-rate firmware.
                            newest = complete_records[-1]
                            if newest not in diagnostic_records:
                                line = newest.rstrip(b"\r").decode("ascii", errors="replace")
                                self.on_line(self.side, line, received_ns)
                            last_dispatched_ns = received_ns
                            # Let the kernel accumulate any legacy flood into
                            # the next read so obsolete lines can be coalesced
                            # without a busy Python receive loop.
                            self._stop.wait(MIN_ADMITTED_SAMPLE_INTERVAL_NS / 1_000_000_000.0)
            except (OSError, ValueError) as error:
                disconnected = True
                if not self._stop.is_set():
                    self.on_state(self.side, "reconnecting", str(error), None)
            finally:
                current = self._fd
                self._fd = None
                if current is not None:
                    try:
                        os.close(current)
                    except OSError:
                        pass
            if disconnected:
                self._stop.wait(0.5)


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
        diagnostic_writer: Callable[[str, bytes], int] | None = None,
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
        self._diagnostic_writer = diagnostic_writer or self._write_diagnostic_bytes
        self._diagnostic_tx_bytes = 0

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

    @staticmethod
    def _write_diagnostic_bytes(path: str, encoded: bytes) -> int:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK | os.O_CLOEXEC,
        )
        try:
            _PassiveTTYReader._configure_115200_8n1(fd)
            written = os.write(fd, encoded)
            termios.tcdrain(fd)
            return written
        finally:
            os.close(fd)

    @staticmethod
    def _address_for_side(side: str) -> str:
        return "LEFTLEG" if side == "left" else "RIGHTLEG"

    @staticmethod
    def _command_protocol_for_state(state: _SideState) -> str:
        if state.command_protocol:
            return state.command_protocol
        if "db1-required" in state.capabilities:
            return "DB1"
        if "behemoth" in state.firmware_version.lower():
            return "DB1"
        # Prefer the current mandatory addressed protocol when no boot/version
        # evidence has arrived. request_observation_stream performs a bounded
        # bare-version fallback for legacy images.
        return "DB1"

    @staticmethod
    def _validate_diagnostic_payload(side: str, payload: str) -> bool:
        if payload in DIAGNOSTIC_COMMANDS:
            return True
        match = re.fullmatch(r"can info (0x[0-9a-f]{3}|[0-9]{3,4})", payload)
        if not match:
            return False
        try:
            motor_id = int(match.group(1), 0)
        except ValueError:
            return False
        # Firmware discovery covers this bounded RMD range. Read-only INFO must
        # also reach a locally discovered motor whose stored ID does not match
        # the configured leg map; motion commands remain separately guarded.
        return 0x141 <= motor_id <= 0x160

    @staticmethod
    def _validate_guarded_payload(side: str, payload: str) -> bool:
        side_prefix = f"{side}_"
        if payload == "calibrate save" or payload in {
            "mode standalone", "mode hyperspawn", "raw on", "raw off",
            "hyperspawn legacy on", "hyperspawn legacy off",
            "hyperspawn autoarm on", "hyperspawn autoarm off",
        }:
            return True
        if re.fullmatch(r"config set max_torque (?:\d+(?:\.\d*)?|\.\d+)", payload):
            return True
        if re.fullmatch(
            r"config set offset (?:outer_calf|inner_calf|hip_pitch|knee|hip_roll) -?\d+",
            payload,
        ):
            return True
        if re.fullmatch(
            rf"direction {side_prefix}(?:outer_calf|inner_calf|knee|hip_pitch|hip_roll) [+-]",
            payload,
        ):
            return True
        if re.fullmatch(
            rf"constrain (?:outer_calf|inner_calf|knee|hip_pitch|hip_yaw|hip_roll)_{side} -?\d+ -?\d+",
            payload,
        ):
            return True
        if re.fullmatch(r"hyperspawn timeout \d+", payload):
            return True
        if re.fullmatch(r"hyperspawn scale (?:\d+(?:\.\d*)?|\.\d+)", payload):
            return True
        return False

    def send_diagnostic(
        self,
        side: str,
        command: str,
        *,
        protocol_override: str | None = None,
    ) -> dict[str, Any]:
        """Send one allowlisted non-motion request through an ephemeral fd."""

        if side not in self._states:
            raise ValueError("diagnostic side must be left or right")
        payload = str(command).strip().lower()
        if not self._validate_diagnostic_payload(side, payload):
            raise ValueError("serial diagnostics permit version/capabilities/health/observe and passive status queries only")
        with self._lock:
            state = self._states[side]
            if not self.enabled or not state.configured_path:
                raise ValueError(f"{side} observation serial path is not enabled")
            protocol = protocol_override or self._command_protocol_for_state(state)
            if protocol not in {"DB1", "LEGACY"}:
                raise ValueError("diagnostic protocol override must be DB1 or LEGACY")
            wire_command = (
                f"<DB1:{self._address_for_side(side)}> {payload}"
                if protocol == "DB1" else payload
            )
            path = state.configured_path
        encoded = (wire_command + "\n").encode("ascii", errors="strict")
        try:
            written = self._diagnostic_writer(path, encoded)
            if written != len(encoded):
                raise OSError(f"short serial diagnostic write: {written}/{len(encoded)} bytes")
        except (OSError, termios.error) as error:
            with self._lock:
                self._states[side].last_diagnostic_error = str(error)
            raise ValueError(f"{side} diagnostic request failed: {error}") from error
        now_ns = time.monotonic_ns()
        with self._lock:
            state = self._states[side]
            state.diagnostic_tx_bytes += written
            state.last_diagnostic_command = payload
            state.last_diagnostic_error = ""
            state.raw_lines.append({
                "receivedMonotonicNs": now_ns,
                "text": wire_command,
                "direction": "tx-diagnostic",
            })
            self._diagnostic_tx_bytes += written
        return {
            "sent": True,
            "side": side,
            "bytes": written,
            "command": payload,
            "wireCommand": wire_command,
            "commandProtocol": protocol,
            "motionCapable": False,
        }

    def send_guarded_command(self, side: str, command: str) -> dict[str, Any]:
        """Send one validated non-motion calibration/configuration command."""

        if side not in self._states:
            raise ValueError("guarded command side must be left or right")
        payload = str(command).strip().lower()
        if not self._validate_guarded_payload(side, payload):
            raise ValueError("guarded serial command is not an admitted calibration/configuration mutation")
        with self._lock:
            state = self._states[side]
            if not self.enabled or not state.configured_path:
                raise ValueError(f"{side} observation serial path is not enabled")
            wire_command = f"<DB1:{self._address_for_side(side)}> {payload}"
            path = state.configured_path
        encoded = (wire_command + "\n").encode("ascii", errors="strict")
        try:
            written = self._diagnostic_writer(path, encoded)
            if written != len(encoded):
                raise OSError(f"short serial guarded write: {written}/{len(encoded)} bytes")
        except (OSError, termios.error) as error:
            with self._lock:
                self._states[side].last_diagnostic_error = str(error)
            raise ValueError(f"{side} guarded request failed: {error}") from error
        now_ns = time.monotonic_ns()
        with self._lock:
            state = self._states[side]
            state.diagnostic_tx_bytes += written
            state.last_diagnostic_command = payload
            state.last_diagnostic_error = ""
            state.raw_lines.append({
                "receivedMonotonicNs": now_ns,
                "text": wire_command,
                "direction": "tx-guarded",
            })
            self._diagnostic_tx_bytes += written
        return {
            "sent": True,
            "side": side,
            "bytes": written,
            "command": payload,
            "wireCommand": wire_command,
            "motionCapable": False,
            "guardedMutation": True,
            "sentMonotonicNs": now_ns,
        }

    def request_observation_stream(self, enabled: bool) -> dict[str, Any]:
        """Request version, health, and passive telemetry from both leg ESPs."""

        results: dict[str, Any] = {}
        for side in self._states:
            sent = []
            errors = []
            version_requested = False
            with self._lock:
                known_protocol = self._states[side].command_protocol
            if enabled and not known_protocol:
                try:
                    sent.append(self.send_diagnostic(
                        side, "version", protocol_override="DB1",
                    ))
                    version_requested = True
                    time.sleep(0.12)
                    with self._lock:
                        known_protocol = self._states[side].command_protocol
                    if not known_protocol:
                        sent.append(self.send_diagnostic(
                            side, "version", protocol_override="LEGACY",
                        ))
                        time.sleep(0.12)
                except ValueError as error:
                    errors.append(str(error))
            commands = (
                (("health", "observe on") if version_requested
                 else ("version", "health", "observe on"))
                if enabled else ("observe off",)
            )
            for command in commands:
                try:
                    sent.append(self.send_diagnostic(side, command))
                except ValueError as error:
                    errors.append(str(error))
            results[side] = {"sent": sent, "errors": errors, "ok": not errors}
        return {
            "schema": OBSERVATION_SCHEMA,
            "requested": "on" if enabled else "off",
            "motionOutputEnabled": False,
            "sides": results,
            "ok": all(result["ok"] for result in results.values()),
        }

    def request_health(self) -> dict[str, Any]:
        """Refresh non-motion DBH1 diagnostics on both leg controllers."""

        results: dict[str, Any] = {}
        for side in self._states:
            try:
                sent = self.send_diagnostic(side, "health")
                results[side] = {"sent": sent, "errors": [], "ok": True}
            except ValueError as error:
                results[side] = {"sent": None, "errors": [str(error)], "ok": False}
        return {
            "schema": OBSERVATION_SCHEMA,
            "requested": "health",
            "motionOutputEnabled": False,
            "sides": results,
            "ok": all(result["ok"] for result in results.values()),
        }

    def ingest_line(
        self,
        side: str,
        line: str,
        received_monotonic_ns: int | None = None,
    ) -> bool:
        """Ingest a line; public to support replay and isolated tests."""

        received_ns = time.monotonic_ns() if received_monotonic_ns is None else int(received_monotonic_ns)
        cleaned_line = line.strip()
        with self._lock:
            state = self._states[side]
            state.raw_lines.append({
                "receivedMonotonicNs": received_ns,
                "text": cleaned_line,
                "direction": "rx",
            })
            family, version = _passive_firmware_identity(cleaned_line)
            if family != "unknown" and not state.command_protocol:
                state.firmware_family = family
                state.firmware_version = version
            expected_missing_header = (
                f"ERR|MISSING_TARGET_HEADER|expected=<DB1:{self._address_for_side(side)}>"
            )
            if cleaned_line.startswith(expected_missing_header):
                state.command_protocol = "DB1"
                if "db1-required" not in state.capabilities:
                    state.capabilities = (*state.capabilities, "db1-required")
                return True
            if cleaned_line.startswith("DBV1,"):
                try:
                    version_record = parse_firmware_version_line(side, cleaned_line)
                except ObservationParseError:
                    state.rejected_lines += 1
                    return False
                state.firmware_family = "dropbear-versioned"
                state.firmware_version = version_record["firmware"]
                state.command_protocol = version_record["commandProtocol"]
                state.advertised_telemetry_protocol = version_record["telemetryProtocol"]
                state.capabilities = version_record["capabilities"]
                return True
            if cleaned_line.startswith("DBH1,"):
                try:
                    state.health = parse_firmware_health_line(side, cleaned_line)
                except ObservationParseError:
                    state.rejected_lines += 1
                    return False
                return True
            if cleaned_line.startswith("DBCFG1,"):
                try:
                    record = parse_firmware_configuration_line(side, cleaned_line)
                except ObservationParseError:
                    state.rejected_lines += 1
                    return False
                if record["kind"] == "meta":
                    state.configuration = {"constraints": {}, "meta": record["value"]}
                elif record["kind"] == "constraint":
                    state.configuration.setdefault("constraints", {})[record["joint"]] = record["value"]
                elif record["kind"] == "end":
                    state.configuration["completeMonotonicNs"] = received_ns
                else:
                    state.configuration[record["kind"]] = record["value"]
                state.configuration["updatedMonotonicNs"] = received_ns
                return True
            if cleaned_line.startswith("DBCAL1,"):
                try:
                    state.calibration = parse_firmware_calibration_line(side, cleaned_line)
                except ObservationParseError:
                    state.rejected_lines += 1
                    return False
                state.calibration["updatedMonotonicNs"] = received_ns
                return True
            if cleaned_line.startswith("DBO1,"):
                fields = [field.strip() for field in cleaned_line.split(",")]
                if len(fields) not in {3, 4} or fields[1] != self._address_for_side(side):
                    state.rejected_lines += 1
                    return False
                state.observation_streaming = fields[2] == "on"
                return True
            if "," not in cleaned_line:
                # Human-readable boot/status/log output belongs in the bounded
                # raw console but is not a rejected telemetry record.
                return True
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
            family, version = _passive_firmware_identity(line, record["format"])
            if not state.command_protocol:
                if record["format"] in {"legacy5", "DB2"}:
                    state.command_protocol = "LEGACY"
                state.firmware_family = family
                state.firmware_version = version
            state.decoded_lines += 1
            state.state = "observing"
            state.error = ""
        return True

    def snapshot(self, now_ns: int | None = None) -> dict[str, Any]:
        current_ns = time.monotonic_ns() if now_ns is None else int(now_ns)
        with self._lock:
            sides: dict[str, Any] = {}
            fresh_count = 0
            unobserved_joints: list[str] = []
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
                if fresh and state.motor_joints:
                    current_motor_joints = dict(state.motor_joints)
                else:
                    profile_capable = (
                        "motor-profile-v1" in state.capabilities
                        or state.advertised_telemetry_protocol == "DB3"
                    )
                    unavailable_status = (
                        "telemetry_stale" if state.sequence
                        else "telemetry_not_started" if profile_capable
                        else "not_emitted_by_deployed_firmware"
                    )
                    current_motor_joints = unavailable_motor_observations(
                        side, unavailable_status,
                    )
                unobserved_joints.extend(
                    name for name, motor in current_motor_joints.items()
                    if not motor.get("available")
                )
                sides[side] = {
                    "state": state.state,
                    "configuredPath": state.configured_path or "",
                    "resolvedPath": state.resolved_path or "",
                    "fresh": fresh,
                    "ageMs": age_ms,
                    "sequence": state.sequence,
                    "receivedMonotonicNs": state.received_monotonic_ns,
                    "rawLine": state.raw_line,
                    "rawTail": list(state.raw_lines),
                    "telemetryFormat": state.telemetry_format,
                    "firmware": {
                        "family": state.firmware_family,
                        "version": state.firmware_version,
                        "detection": "version-record" if state.command_protocol else "passive-serial",
                        "commandProtocol": state.command_protocol,
                        "telemetryProtocol": state.advertised_telemetry_protocol,
                        "capabilities": list(state.capabilities),
                    },
                    "health": dict(state.health),
                    "configuration": {
                        **state.configuration,
                        "constraints": dict(state.configuration.get("constraints", {})),
                    },
                    "calibration": dict(state.calibration),
                    "observationStreaming": state.observation_streaming,
                    "diagnosticTxBytes": state.diagnostic_tx_bytes,
                    "lastDiagnosticCommand": state.last_diagnostic_command,
                    "lastDiagnosticError": state.last_diagnostic_error,
                    "controllerMillis": state.controller_millis,
                    "joints": dict(state.joints) if fresh else {},
                    "motorJoints": current_motor_joints,
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
                "mode": "read_only_with_diagnostic_queries",
                "state": overall,
                "enabled": self.enabled,
                "writeCapable": False,
                "motionWriteCapable": False,
                "diagnosticWriteCapable": self.enabled,
                "diagnosticCommands": sorted(DIAGNOSTIC_COMMANDS),
                "txBytes": self._diagnostic_tx_bytes,
                "baudrate": 115200,
                "maximumSampleAgeMs": self.maximum_sample_age_ms,
                "complete": fresh_count == 2,
                "unobservedJoints": unobserved_joints,
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
    "parse_esp32_telemetry_line",
    "parse_firmware_health_line",
    "parse_firmware_version_line",
]
