"""Deterministic protocol-state emulator for classic-CAN RMD V4.4.

This emulator is deliberately narrower than a motor simulator.  It exercises
the byte-exact request/response contract implemented by :mod:`rmd_v44` and a
small, explicit protocol state model.  It does not model torque, inertia,
friction, gearing, electrical behavior, or motion dynamics.  Commanded values
are recorded, but they never synthesize feedback telemetry.

Protocol layout evidence is not model/firmware applicability evidence.  In
particular, neither this module nor a passing test against it proves that a
specific MYACTUATOR product implements V4.4.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field, replace
from typing import Callable, FrozenSet, Iterable, List, Optional, Tuple, Union

from . import rmd_v44 as codec


APPLICABILITY_VERIFIED = False
MODEL_FIRMWARE_APPLICABILITY_VERIFIED = False
IS_PHYSICAL_PLANT = False
PROTOCOL_EDITION = codec.SOURCE_EDITION
PROTOCOL_SOURCE_SHA256 = codec.SOURCE_SHA256

MOTION_COMMANDS = frozenset(
    {
        codec.Command.IQ_CONTROL,
        codec.Command.SPEED_CONTROL,
        codec.Command.ABSOLUTE_POSITION,
    }
)
BRAKE_COMMANDS = frozenset({codec.Command.BRAKE_RELEASE, codec.Command.BRAKE_LOCK})
ACTUATING_COMMANDS = MOTION_COMMANDS | BRAKE_COMMANDS


class EmulatorError(ValueError):
    """The emulator configuration or virtual-time operation is invalid."""


def _integer(value: int, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EmulatorError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise EmulatorError(f"{label} must be in [{minimum}, {maximum}], got {value}")
    return value


def _command(value: Union[int, codec.Command]) -> codec.Command:
    if isinstance(value, bool):
        raise EmulatorError("command must be an evidenced V4.4 command")
    try:
        return codec.Command(value)
    except (TypeError, ValueError) as exc:
        raise EmulatorError(
            f"command must be an evidenced V4.4 command, got {value!r}"
        ) from exc


def _mode(value: Union[int, codec.OperatingMode]) -> codec.OperatingMode:
    if isinstance(value, bool):
        raise EmulatorError("mode must be an evidenced V4.4 operating mode")
    try:
        return codec.OperatingMode(value)
    except (TypeError, ValueError) as exc:
        raise EmulatorError(
            f"mode must be an evidenced V4.4 operating mode, got {value!r}"
        ) from exc


@dataclass(frozen=True)
class NodeState:
    """Raw protocol state for one emulated node.

    Feedback fields are independent inputs to the emulator.  Accepted motion
    commands update only the ``last_*_command_raw`` fields; there is no plant
    model that turns a command into measured feedback.
    """

    motor_id: int
    disabled: bool = True
    stopped: bool = False
    mode: codec.OperatingMode = codec.OperatingMode.CURRENT
    brake_released: bool = False
    multi_turn_angle_raw: int = 0
    single_turn_angle_raw: int = 0
    iq_raw: int = 0
    output_speed_raw: int = 0
    output_angle_raw: int = 0
    motor_temperature_c: int = 0
    mos_temperature_raw: int = 0
    voltage_raw: int = 0
    error_mask: int = 0
    phase_a_raw: int = 0
    phase_b_raw: int = 0
    phase_c_raw: int = 0
    last_iq_command_raw: Optional[int] = None
    last_speed_command_raw: Optional[int] = None
    last_speed_max_torque_percent_raw: Optional[int] = None
    last_position_command_raw: Optional[int] = None
    last_position_max_speed_raw: Optional[int] = None

    def __post_init__(self) -> None:
        codec.validate_motor_id(self.motor_id)
        if not isinstance(self.disabled, bool):
            raise EmulatorError("disabled must be bool")
        if not isinstance(self.stopped, bool):
            raise EmulatorError("stopped must be bool")
        if not isinstance(self.brake_released, bool):
            raise EmulatorError("brake_released must be bool")
        object.__setattr__(self, "mode", _mode(self.mode))
        _integer(
            self.multi_turn_angle_raw,
            -(1 << 31),
            (1 << 31) - 1,
            "multi_turn_angle_raw",
        )
        _integer(self.single_turn_angle_raw, -18_000, 18_000, "single_turn_angle_raw")
        _integer(self.iq_raw, -(1 << 15), (1 << 15) - 1, "iq_raw")
        _integer(
            self.output_speed_raw,
            -(1 << 15),
            (1 << 15) - 1,
            "output_speed_raw",
        )
        _integer(
            self.output_angle_raw,
            -(1 << 15),
            (1 << 15) - 1,
            "output_angle_raw",
        )
        _integer(self.motor_temperature_c, -128, 127, "motor_temperature_c")
        _integer(self.mos_temperature_raw, 0, 255, "mos_temperature_raw")
        _integer(self.voltage_raw, 0, 0xFFFF, "voltage_raw")
        _integer(self.error_mask, 0, 0xFFFF, "error_mask")
        for name in ("phase_a_raw", "phase_b_raw", "phase_c_raw"):
            _integer(getattr(self, name), -(1 << 15), (1 << 15) - 1, name)
        optional_ranges = (
            ("last_iq_command_raw", -(1 << 15), (1 << 15) - 1),
            ("last_speed_command_raw", -(1 << 31), (1 << 31) - 1),
            ("last_speed_max_torque_percent_raw", 0, 255),
            ("last_position_command_raw", -(1 << 31), (1 << 31) - 1),
            ("last_position_max_speed_raw", 0, 0xFFFF),
        )
        for name, minimum, maximum in optional_ranges:
            value = getattr(self, name)
            if value is not None:
                _integer(value, minimum, maximum, name)


@dataclass(frozen=True)
class CapabilityPolicy:
    """Explicit allow-list for commands that can alter actuation state."""

    motion: FrozenSet[codec.Command] = frozenset()
    brake: FrozenSet[codec.Command] = frozenset()

    def __post_init__(self) -> None:
        motion = frozenset(_command(command) for command in self.motion)
        brake = frozenset(_command(command) for command in self.brake)
        if not motion <= MOTION_COMMANDS:
            raise EmulatorError("motion policy contains a non-motion command")
        if not brake <= BRAKE_COMMANDS:
            raise EmulatorError("brake policy contains a non-brake command")
        object.__setattr__(self, "motion", motion)
        object.__setattr__(self, "brake", brake)

    @classmethod
    def deny_all(cls) -> "CapabilityPolicy":
        return cls()

    @classmethod
    def allow_explicit(
        cls,
        *,
        motion: Iterable[Union[int, codec.Command]] = (),
        brake: Iterable[Union[int, codec.Command]] = (),
    ) -> "CapabilityPolicy":
        return cls(
            frozenset(_command(command) for command in motion),
            frozenset(_command(command) for command in brake),
        )

    def allows(self, command: codec.Command) -> bool:
        return command in self.motion or command in self.brake


@dataclass(frozen=True)
class AdmissionContext:
    motor_id: int
    command: codec.Command
    now_us: int
    request_sequence: int
    request: codec.DecodedRequest
    state: NodeState


AdmissionCallback = Callable[[AdmissionContext], bool]


@dataclass(frozen=True)
class ResponseScenario:
    """One deterministic, one-shot response/fault injection.

    The first accepted request matching ``motor_id`` and ``command`` consumes
    the scenario.  Fields may be combined, e.g. a drive fault plus a delayed
    status response.  ``unexpected_response`` must itself be a codec-valid
    V4.4 response; malformed response generation is intentionally outside this
    protocol emulator.
    """

    motor_id: Optional[int] = None
    command: Optional[codec.Command] = None
    drop_response: bool = False
    extra_delay_us: int = 0
    unexpected_response: Optional[codec.CanFrame] = None
    drive_error_mask: Optional[int] = None
    drive_disables: bool = False

    def __post_init__(self) -> None:
        if self.motor_id is not None:
            codec.validate_motor_id(self.motor_id)
        if self.command is not None:
            object.__setattr__(self, "command", _command(self.command))
        if not isinstance(self.drop_response, bool):
            raise EmulatorError("drop_response must be bool")
        _integer(self.extra_delay_us, 0, (1 << 63) - 1, "extra_delay_us")
        if self.unexpected_response is not None:
            try:
                codec.decode_response(self.unexpected_response)
            except codec.CodecError as exc:
                raise EmulatorError(
                    "unexpected_response must be a codec-valid V4.4 response"
                ) from exc
        if self.drive_error_mask is not None:
            _integer(self.drive_error_mask, 0, 0xFFFF, "drive_error_mask")
        if not isinstance(self.drive_disables, bool):
            raise EmulatorError("drive_disables must be bool")
        if self.drive_disables and self.drive_error_mask is None:
            raise EmulatorError("drive_disables requires drive_error_mask")

    def matches(self, request: codec.DecodedRequest) -> bool:
        return (self.motor_id is None or self.motor_id == request.motor_id) and (
            self.command is None or self.command == request.command
        )


@dataclass(frozen=True)
class Submission:
    request_sequence: int
    accepted: bool
    reason: str
    motor_id: Optional[int] = None
    command: Optional[codec.Command] = None
    response_due_us: Optional[int] = None
    response_deadline_us: Optional[int] = None


@dataclass(frozen=True)
class Delivery:
    request_sequence: int
    delivered_at_us: int
    frame: codec.CanFrame


@dataclass(frozen=True)
class ReplayRecord:
    submitted_at_us: int
    frame: codec.CanFrame
    response_deadline_us: Optional[int] = None

    def __post_init__(self) -> None:
        _integer(self.submitted_at_us, 0, (1 << 63) - 1, "submitted_at_us")
        if self.response_deadline_us is not None:
            _integer(
                self.response_deadline_us,
                0,
                (1 << 63) - 1,
                "response_deadline_us",
            )


@dataclass(frozen=True)
class Event:
    event_sequence: int
    at_us: int
    kind: str
    request_sequence: Optional[int] = None
    motor_id: Optional[int] = None
    command: Optional[codec.Command] = None
    reason: str = ""
    frame: Optional[codec.CanFrame] = None


@dataclass(order=True)
class _Scheduled:
    at_us: int
    order: int
    request_sequence: int = field(compare=False)
    frame: Optional[codec.CanFrame] = field(compare=False, default=None)
    deadline_miss: bool = field(compare=False, default=False)
    motor_id: int = field(compare=False, default=0)
    command: codec.Command = field(compare=False, default=codec.Command.STOP)


class RmdV44Emulator:
    """Virtual-time RMD V4.4 request/response protocol emulator."""

    def __init__(
        self,
        nodes: Iterable[Union[int, NodeState]],
        *,
        response_latency_us: int = 0,
        response_deadline_us: int = 1_000,
        capability_policy: Optional[CapabilityPolicy] = None,
        admission_callback: Optional[AdmissionCallback] = None,
    ) -> None:
        _integer(response_latency_us, 0, (1 << 63) - 1, "response_latency_us")
        _integer(response_deadline_us, 0, (1 << 63) - 1, "response_deadline_us")
        if admission_callback is not None and not callable(admission_callback):
            raise EmulatorError("admission_callback must be callable")
        states = {}
        for configured in nodes:
            state = (
                configured
                if isinstance(configured, NodeState)
                else NodeState(configured)
            )
            if state.motor_id in states:
                raise EmulatorError(f"duplicate motor_id: {state.motor_id}")
            states[state.motor_id] = state
        if not states:
            raise EmulatorError("at least one node is required")

        self._states = states
        self._latency_us = response_latency_us
        self._deadline_us = response_deadline_us
        self._policy = capability_policy or CapabilityPolicy.deny_all()
        self._admission = admission_callback
        self._now_us = 0
        self._request_sequence = 0
        self._event_sequence = 0
        self._schedule_order = 0
        self._pending: List[_Scheduled] = []
        self._events: List[Event] = []
        self._replay: List[ReplayRecord] = []
        self._scenarios: List[ResponseScenario] = []

    @property
    def now_us(self) -> int:
        return self._now_us

    @property
    def protocol_edition(self) -> str:
        return PROTOCOL_EDITION

    @property
    def model_firmware_applicability_verified(self) -> bool:
        return False

    @property
    def is_physical_plant(self) -> bool:
        return False

    def node_ids(self) -> Tuple[int, ...]:
        return tuple(sorted(self._states))

    def state(self, motor_id: int) -> NodeState:
        motor_id = codec.validate_motor_id(motor_id)
        try:
            return self._states[motor_id]
        except KeyError as exc:
            raise EmulatorError(f"motor_id {motor_id} is not configured") from exc

    def set_state(self, state: NodeState) -> None:
        if not isinstance(state, NodeState):
            raise EmulatorError("state must be NodeState")
        if state.motor_id not in self._states:
            raise EmulatorError(f"motor_id {state.motor_id} is not configured")
        self._states[state.motor_id] = state
        self._log("state_configured", motor_id=state.motor_id)

    def set_enabled(self, motor_id: int, enabled: bool) -> None:
        if not isinstance(enabled, bool):
            raise EmulatorError("enabled must be bool")
        state = self.state(motor_id)
        self._states[motor_id] = replace(state, disabled=not enabled)
        self._log(
            "enabled_configured",
            motor_id=motor_id,
            reason="enabled" if enabled else "disabled",
        )

    def queue_scenario(self, scenario: ResponseScenario) -> None:
        if not isinstance(scenario, ResponseScenario):
            raise EmulatorError("scenario must be ResponseScenario")
        self._scenarios.append(scenario)
        self._log(
            "scenario_queued",
            motor_id=scenario.motor_id,
            command=scenario.command,
        )

    def events(self) -> Tuple[Event, ...]:
        return tuple(self._events)

    def replay_records(self) -> Tuple[ReplayRecord, ...]:
        return tuple(self._replay)

    def pending_count(self) -> int:
        return len(self._pending)

    def submit(
        self,
        frame: codec.CanFrame,
        *,
        response_deadline_us: Optional[int] = None,
    ) -> Submission:
        """Process a request now and schedule its deterministic response.

        ``response_deadline_us`` is a duration measured from submission.  A
        request whose response is injected beyond that duration still applies
        its protocol-state transition, but records a missed response deadline.
        This mirrors the fact that absence of a CAN response cannot prove the
        drive ignored a transmitted command.
        """

        deadline_duration = (
            self._deadline_us
            if response_deadline_us is None
            else _integer(
                response_deadline_us,
                0,
                (1 << 63) - 1,
                "response_deadline_us",
            )
        )
        self._request_sequence += 1
        request_sequence = self._request_sequence
        self._replay.append(ReplayRecord(self._now_us, frame, response_deadline_us))
        self._log("request_received", request_sequence=request_sequence, frame=frame)

        try:
            request = codec.decode_request(frame)
        except codec.CodecError as exc:
            reason = f"codec_rejected:{exc}"
            self._log(
                "request_rejected",
                request_sequence=request_sequence,
                reason=reason,
                frame=frame,
            )
            return Submission(request_sequence, False, reason)

        if request.motor_id not in self._states:
            reason = "unconfigured_motor_id"
            self._log(
                "request_rejected",
                request_sequence=request_sequence,
                motor_id=request.motor_id,
                command=request.command,
                reason=reason,
                frame=frame,
            )
            return Submission(
                request_sequence,
                False,
                reason,
                request.motor_id,
                request.command,
            )

        rejection = self._actuation_rejection(request, request_sequence)
        if rejection is not None:
            self._log(
                "request_rejected",
                request_sequence=request_sequence,
                motor_id=request.motor_id,
                command=request.command,
                reason=rejection,
                frame=frame,
            )
            return Submission(
                request_sequence,
                False,
                rejection,
                request.motor_id,
                request.command,
            )

        self._apply_request(request)
        scenario = self._take_scenario(request)
        if scenario is not None and scenario.drive_error_mask is not None:
            state = self._states[request.motor_id]
            self._states[request.motor_id] = replace(
                state,
                error_mask=scenario.drive_error_mask,
                disabled=state.disabled or scenario.drive_disables,
            )
            self._log(
                "drive_fault_injected",
                request_sequence=request_sequence,
                motor_id=request.motor_id,
                command=request.command,
                reason=f"error_mask={scenario.drive_error_mask:#06x}",
            )

        response = self._make_response(request)
        delay_us = self._latency_us
        if scenario is not None:
            delay_us += scenario.extra_delay_us
            if scenario.unexpected_response is not None:
                response = scenario.unexpected_response
                self._log(
                    "unexpected_response_injected",
                    request_sequence=request_sequence,
                    motor_id=request.motor_id,
                    command=request.command,
                    frame=response,
                )

        deadline_at = self._now_us + deadline_duration
        if scenario is not None and scenario.drop_response:
            self._log(
                "response_dropped",
                request_sequence=request_sequence,
                motor_id=request.motor_id,
                command=request.command,
            )
            self._log(
                "request_accepted",
                request_sequence=request_sequence,
                motor_id=request.motor_id,
                command=request.command,
                frame=frame,
            )
            return Submission(
                request_sequence,
                True,
                "accepted_response_dropped",
                request.motor_id,
                request.command,
                None,
                deadline_at,
            )

        due_at = self._now_us + delay_us
        if due_at > deadline_at:
            self._schedule(
                deadline_at,
                request_sequence,
                None,
                True,
                request.motor_id,
                request.command,
            )
            reason = "accepted_response_will_miss_deadline"
        else:
            self._schedule(
                due_at,
                request_sequence,
                response,
                False,
                request.motor_id,
                request.command,
            )
            reason = "accepted"
        self._log(
            "request_accepted",
            request_sequence=request_sequence,
            motor_id=request.motor_id,
            command=request.command,
            frame=frame,
        )
        return Submission(
            request_sequence,
            True,
            reason,
            request.motor_id,
            request.command,
            due_at,
            deadline_at,
        )

    def poll(self) -> Tuple[Delivery, ...]:
        return self.advance_to(self._now_us)

    def advance_by(self, delta_us: int) -> Tuple[Delivery, ...]:
        delta_us = _integer(delta_us, 0, (1 << 63) - 1, "delta_us")
        return self.advance_to(self._now_us + delta_us)

    def advance_to(self, target_us: int) -> Tuple[Delivery, ...]:
        target_us = _integer(target_us, 0, (1 << 63) - 1, "target_us")
        if target_us < self._now_us:
            raise EmulatorError(
                f"virtual time cannot move backward ({self._now_us} -> {target_us})"
            )
        delivered = []
        while self._pending and self._pending[0].at_us <= target_us:
            scheduled = heapq.heappop(self._pending)
            self._now_us = scheduled.at_us
            if scheduled.deadline_miss:
                self._log(
                    "response_deadline_missed",
                    request_sequence=scheduled.request_sequence,
                    motor_id=scheduled.motor_id,
                    command=scheduled.command,
                )
                continue
            assert scheduled.frame is not None
            item = Delivery(
                scheduled.request_sequence, scheduled.at_us, scheduled.frame
            )
            delivered.append(item)
            self._log(
                "response_delivered",
                request_sequence=scheduled.request_sequence,
                motor_id=scheduled.motor_id,
                command=scheduled.command,
                frame=scheduled.frame,
            )
        self._now_us = target_us
        return tuple(delivered)

    def run_until_idle(self) -> Tuple[Delivery, ...]:
        delivered = []
        while self._pending:
            delivered.extend(self.advance_to(self._pending[0].at_us))
        return tuple(delivered)

    def replay(
        self,
        records: Iterable[ReplayRecord],
        *,
        finish: bool = True,
    ) -> Tuple[Delivery, ...]:
        """Replay an ordered request trace into a fresh or reset-equivalent emulator."""

        delivered = []
        for record in records:
            if not isinstance(record, ReplayRecord):
                raise EmulatorError("records must contain ReplayRecord values")
            delivered.extend(self.advance_to(record.submitted_at_us))
            self.submit(
                record.frame,
                response_deadline_us=record.response_deadline_us,
            )
            delivered.extend(self.poll())
        if finish:
            delivered.extend(self.run_until_idle())
        return tuple(delivered)

    def _actuation_rejection(
        self, request: codec.DecodedRequest, request_sequence: int
    ) -> Optional[str]:
        if request.command not in ACTUATING_COMMANDS:
            return None
        if not self._policy.allows(request.command):
            return "capability_policy_denied"
        state = self._states[request.motor_id]
        if state.disabled:
            return "node_disabled"
        if self._admission is None:
            return "admission_callback_missing"
        context = AdmissionContext(
            request.motor_id,
            request.command,
            self._now_us,
            request_sequence,
            request,
            state,
        )
        try:
            admitted = self._admission(context)
        except Exception as exc:  # callback is an explicit safety boundary
            self._log(
                "admission_callback_error",
                request_sequence=request_sequence,
                motor_id=request.motor_id,
                command=request.command,
                reason=type(exc).__name__,
            )
            return "admission_callback_error"
        if admitted is not True:
            return "admission_callback_denied"
        return None

    def _apply_request(self, request: codec.DecodedRequest) -> None:
        state = self._states[request.motor_id]
        command = request.command
        if command == codec.Command.SHUTDOWN:
            # Shutdown changes the disabled state only.  It is intentionally
            # not aliased to STOP in this protocol-state model.
            state = replace(state, disabled=True)
        elif command == codec.Command.STOP:
            # Stop does not claim a shutdown or loss of enable state.
            state = replace(state, stopped=True)
        elif command == codec.Command.BRAKE_RELEASE:
            state = replace(state, brake_released=True)
        elif command == codec.Command.BRAKE_LOCK:
            state = replace(state, brake_released=False)
        elif command == codec.Command.IQ_CONTROL:
            state = replace(state, stopped=False, last_iq_command_raw=request.iq_raw)
        elif command == codec.Command.SPEED_CONTROL:
            state = replace(
                state,
                stopped=False,
                last_speed_command_raw=request.speed_raw,
                last_speed_max_torque_percent_raw=request.max_torque_percent_raw,
            )
        elif command == codec.Command.ABSOLUTE_POSITION:
            state = replace(
                state,
                stopped=False,
                last_position_command_raw=request.angle_raw,
                last_position_max_speed_raw=request.max_speed_raw,
            )
        # All other evidenced commands are read-only.
        self._states[request.motor_id] = state

    def _take_scenario(
        self, request: codec.DecodedRequest
    ) -> Optional[ResponseScenario]:
        for index, scenario in enumerate(self._scenarios):
            if scenario.matches(request):
                return self._scenarios.pop(index)
        return None

    def _make_response(self, request: codec.DecodedRequest) -> codec.CanFrame:
        state = self._states[request.motor_id]
        command = request.command
        if command in codec.ECHO_COMMANDS:
            payload = bytes((int(command), 0, 0, 0, 0, 0, 0, 0))
        elif command == codec.Command.READ_MULTI_TURN_ANGLE:
            payload = bytes(
                (int(command), 0, 0, 0)
            ) + state.multi_turn_angle_raw.to_bytes(4, "little", signed=True)
        elif command == codec.Command.READ_SINGLE_TURN_ANGLE:
            payload = bytes(
                (int(command), 0, 0, 0)
            ) + state.single_turn_angle_raw.to_bytes(4, "little", signed=True)
        elif command == codec.Command.READ_STATUS_1:
            payload = (
                bytes(
                    (
                        int(command),
                        state.motor_temperature_c & 0xFF,
                        state.mos_temperature_raw,
                        int(state.brake_released),
                    )
                )
                + state.voltage_raw.to_bytes(2, "little")
                + state.error_mask.to_bytes(2, "little")
            )
        elif command in codec.MOTION_STATUS_COMMANDS:
            payload = bytes(
                (int(command), state.motor_temperature_c & 0xFF)
            ) + b"".join(
                value.to_bytes(2, "little", signed=True)
                for value in (
                    state.iq_raw,
                    state.output_speed_raw,
                    state.output_angle_raw,
                )
            )
        elif command == codec.Command.READ_STATUS_3:
            payload = bytes(
                (int(command), state.motor_temperature_c & 0xFF)
            ) + b"".join(
                value.to_bytes(2, "little", signed=True)
                for value in (
                    state.phase_a_raw,
                    state.phase_b_raw,
                    state.phase_c_raw,
                )
            )
        elif command == codec.Command.OPERATING_MODE:
            payload = bytes((int(command), 0, 0, 0, 0, 0, 0, int(state.mode)))
        else:  # decode_request and the Command enum are the closed surface.
            raise AssertionError(f"unhandled evidenced command: {command!r}")
        response = codec.CanFrame(
            codec.response_arbitration_id(request.motor_id), payload
        )
        # Internal assertion: every generated response must satisfy the shared
        # revision-exact decoder and request correlation.
        codec.decode_response(
            response,
            expected_motor_id=request.motor_id,
            expected_command=command,
        )
        return response

    def _schedule(
        self,
        at_us: int,
        request_sequence: int,
        frame: Optional[codec.CanFrame],
        deadline_miss: bool,
        motor_id: int,
        command: codec.Command,
    ) -> None:
        self._schedule_order += 1
        heapq.heappush(
            self._pending,
            _Scheduled(
                at_us,
                self._schedule_order,
                request_sequence,
                frame,
                deadline_miss,
                motor_id,
                command,
            ),
        )

    def _log(
        self,
        kind: str,
        *,
        request_sequence: Optional[int] = None,
        motor_id: Optional[int] = None,
        command: Optional[codec.Command] = None,
        reason: str = "",
        frame: Optional[codec.CanFrame] = None,
    ) -> None:
        self._event_sequence += 1
        self._events.append(
            Event(
                self._event_sequence,
                self._now_us,
                kind,
                request_sequence,
                motor_id,
                command,
                reason,
                frame,
            )
        )


__all__ = [
    "ACTUATING_COMMANDS",
    "APPLICABILITY_VERIFIED",
    "AdmissionCallback",
    "AdmissionContext",
    "BRAKE_COMMANDS",
    "CapabilityPolicy",
    "Delivery",
    "EmulatorError",
    "Event",
    "IS_PHYSICAL_PLANT",
    "MODEL_FIRMWARE_APPLICABILITY_VERIFIED",
    "MOTION_COMMANDS",
    "NodeState",
    "PROTOCOL_EDITION",
    "PROTOCOL_SOURCE_SHA256",
    "ReplayRecord",
    "ResponseScenario",
    "RmdV44Emulator",
    "Submission",
]
