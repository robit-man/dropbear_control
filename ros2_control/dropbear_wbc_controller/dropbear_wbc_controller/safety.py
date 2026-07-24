"""Fail-closed 50 Hz guard for decoded Dropbear WBC references."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Tuple

from .contract import (
    AUTHORITY,
    CANONICAL_JOINT_ORDER,
    JOINT_COUNT,
    JOINT_LIMITS,
    STAND_POSE,
    ActivationRequest,
    ContractError,
    JointReferenceFrame,
    MotionTokenFrame,
    RobotStateFrame,
    SafeJointCommand,
)


class ControllerMode(str, Enum):
    INACTIVE = "inactive"
    STAND_BLEND = "stand_blend"
    ACTIVE = "active"
    WATCHDOG_STAND = "watchdog_stand"
    ESTOP = "estop"


@dataclass(frozen=True)
class SafetyConfig:
    control_hz: float = 50.0
    command_timeout_sec: float = 0.10
    state_timeout_sec: float = 0.10
    stand_blend_sec: float = 1.00
    watchdog_blend_sec: float = 0.75
    activation_max_velocity_rad_s: float = 0.15
    source_future_tolerance_sec: float = 0.025

    def __post_init__(self) -> None:
        values = (
            self.control_hz,
            self.command_timeout_sec,
            self.state_timeout_sec,
            self.stand_blend_sec,
            self.watchdog_blend_sec,
            self.activation_max_velocity_rad_s,
            self.source_future_tolerance_sec,
        )
        if not all(math.isfinite(value) and value > 0.0 for value in values):
            raise ContractError("all safety configuration values must be finite and positive")
        if self.control_hz != 50.0:
            raise ContractError("the version-1 WBC safety contract is fixed at 50 Hz")
        if self.command_timeout_sec < 2.0 / self.control_hz:
            raise ContractError("command timeout must allow at least two 50 Hz frames")


class WbcSafetyController:
    """Stateful guard around a SONIC decoder's 22-axis joint references.

    This class deliberately has no motor or CAN transport. A true hardware
    supervisor must independently authorize any use of its output.
    """

    def __init__(self, config: SafetyConfig | None = None) -> None:
        self.config = config or SafetyConfig()
        self.mode = ControllerMode.INACTIVE
        self.estop_latched = False
        self.estop_reason = ""
        self.session_id: str | None = None
        self._state: RobotStateFrame | None = None
        self._state_receipt_ns: int | None = None
        self._last_state_sequence: int | None = None
        self._reference: JointReferenceFrame | None = None
        self._reference_receipt_ns: int | None = None
        self._last_reference_sequence: int | None = None
        self._last_token_sequence: int | None = None
        self._last_activation_sequence: int | None = None
        self._last_tick_ns: int | None = None
        self._output_sequence = 0
        self._output_positions = STAND_POSE
        self._blend_start_positions = STAND_POSE
        self._blend_target_positions = STAND_POSE
        self._blend_start_ns = 0
        self._blend_duration_ns = 1
        self._pending_clamped_joints: Tuple[str, ...] = ()
        self._mode_reason = "not activated"

    @property
    def state(self) -> RobotStateFrame | None:
        return self._state

    @property
    def active_session(self) -> str | None:
        return self.session_id

    def observe_state(
        self, state: RobotStateFrame, *, receipt_steady_time_ns: int
    ) -> None:
        now_ns = self._time(receipt_steady_time_ns, "receipt_steady_time_ns")
        if (
            self._last_state_sequence is not None
            and state.sequence <= self._last_state_sequence
        ):
            raise ContractError(
                "robot-state sequence must be strictly monotonic"
            )
        if self._is_future(state.observed_steady_time_ns, now_ns):
            raise ContractError("robot state timestamp is too far in the future")
        self._state = state
        self._state_receipt_ns = now_ns
        self._last_state_sequence = state.sequence
        if self._last_tick_ns is None and self.mode == ControllerMode.INACTIVE:
            self._output_positions = self._clamp_positions(state.positions)[0]
        if state.estop:
            self.latch_estop("robot state reported estop")
        elif state.fault_codes and self.mode not in (
            ControllerMode.INACTIVE,
            ControllerMode.ESTOP,
        ):
            self.latch_estop(
                "robot state reported faults: " + ",".join(state.fault_codes)
            )

    def activate(self, request: ActivationRequest, *, now_ns: int) -> None:
        now_ns = self._time(now_ns, "now_ns")
        if self.estop_latched:
            raise ContractError("cannot activate while estop is latched")
        if self.mode != ControllerMode.INACTIVE:
            raise ContractError("controller must be inactive before activation")
        if (
            self._last_activation_sequence is not None
            and request.sequence <= self._last_activation_sequence
        ):
            raise ContractError("activation sequence must be strictly monotonic")
        self._check_frame_age(request.issued_steady_time_ns, now_ns, "activation")
        self._require_fresh_state(now_ns)
        assert self._state is not None
        if self._state.fault_codes:
            raise ContractError("cannot activate with reported robot faults")
        if any(
            abs(velocity) > self.config.activation_max_velocity_rad_s
            for velocity in self._state.velocities
        ):
            raise ContractError("robot must be stationary for guarded activation")
        self._require_state_inside_limits(self._state.positions)
        self.session_id = request.session_id
        self._last_activation_sequence = request.sequence
        self._reference = None
        self._reference_receipt_ns = None
        self._last_reference_sequence = None
        self._last_token_sequence = None
        self._output_positions = tuple(self._state.positions)
        self._begin_blend(
            ControllerMode.STAND_BLEND,
            now_ns,
            self._output_positions,
            STAND_POSE,
            self.config.stand_blend_sec,
            "guarded activation stand blend",
        )

    def deactivate(self, reason: str = "operator deactivated") -> None:
        if not reason:
            raise ContractError("deactivation reason must be non-empty")
        self.mode = ControllerMode.ESTOP if self.estop_latched else ControllerMode.INACTIVE
        self._mode_reason = self.estop_reason if self.estop_latched else reason
        self.session_id = None
        self._reference = None
        self._reference_receipt_ns = None
        self._last_reference_sequence = None
        self._last_token_sequence = None

    def latch_estop(self, reason: str) -> None:
        if not reason:
            raise ContractError("estop reason must be non-empty")
        self.estop_latched = True
        self.estop_reason = reason
        self.mode = ControllerMode.ESTOP
        self._mode_reason = reason
        self.session_id = None
        self._reference = None
        self._reference_receipt_ns = None

    def reset_estop(
        self,
        *,
        operator_confirmation: str,
        now_ns: int,
    ) -> None:
        if operator_confirmation != "DROPBEAR_WBC_RESET_ESTOP":
            raise ContractError("estop reset confirmation does not match")
        now_ns = self._time(now_ns, "now_ns")
        self._require_fresh_state(now_ns)
        assert self._state is not None
        if self._state.estop:
            raise ContractError("robot state still reports estop")
        if self._state.fault_codes:
            raise ContractError("robot state still reports faults")
        if any(
            abs(velocity) > self.config.activation_max_velocity_rad_s
            for velocity in self._state.velocities
        ):
            raise ContractError("robot must be stationary before resetting estop")
        self.estop_latched = False
        self.estop_reason = ""
        self.mode = ControllerMode.INACTIVE
        self._mode_reason = "estop reset; guarded activation required"

    def accept_token(
        self, token: MotionTokenFrame, *, receipt_steady_time_ns: int
    ) -> None:
        """Validate token freshness/order without granting command authority."""
        now_ns = self._time(receipt_steady_time_ns, "receipt_steady_time_ns")
        self._require_session(token.session_id)
        if (
            self._last_token_sequence is not None
            and token.sequence <= self._last_token_sequence
        ):
            raise ContractError("motion-token sequence must be strictly monotonic")
        self._check_frame_age(
            token.generated_steady_time_ns, now_ns, "motion token"
        )
        self._last_token_sequence = token.sequence

    def submit_reference(
        self,
        reference: JointReferenceFrame,
        *,
        receipt_steady_time_ns: int,
    ) -> Tuple[str, ...]:
        now_ns = self._time(receipt_steady_time_ns, "receipt_steady_time_ns")
        if self.mode not in (
            ControllerMode.STAND_BLEND,
            ControllerMode.ACTIVE,
        ):
            raise ContractError(
                "joint references require stand_blend or active mode"
            )
        self._require_session(reference.session_id)
        if (
            self._last_reference_sequence is not None
            and reference.sequence <= self._last_reference_sequence
        ):
            raise ContractError("reference sequence must be strictly monotonic")
        self._check_frame_age(
            reference.generated_steady_time_ns, now_ns, "reference"
        )
        positions, position_clamps = self._clamp_positions(reference.positions)
        requested_velocities = (
            reference.velocities
            if reference.velocities
            else tuple(0.0 for _ in CANONICAL_JOINT_ORDER)
        )
        velocities, velocity_clamps = self._clamp_velocities(requested_velocities)
        clamped_joints = tuple(
            name
            for name in CANONICAL_JOINT_ORDER
            if name in position_clamps or name in velocity_clamps
        )
        self._reference = JointReferenceFrame(
            session_id=reference.session_id,
            sequence=reference.sequence,
            generated_steady_time_ns=reference.generated_steady_time_ns,
            positions=positions,
            velocities=velocities,
            source_token_sequence=reference.source_token_sequence,
        )
        self._reference_receipt_ns = now_ns
        self._last_reference_sequence = reference.sequence
        self._pending_clamped_joints = clamped_joints
        return clamped_joints

    def tick(self, now_ns: int) -> SafeJointCommand:
        now_ns = self._time(now_ns, "now_ns")
        dt = self._control_dt(now_ns)
        target = self._output_positions
        command_enabled = False
        reason = self._mode_reason

        if self.estop_latched:
            self.mode = ControllerMode.ESTOP
            reason = self.estop_reason or "estop latched"
        elif self.mode == ControllerMode.INACTIVE:
            reason = self._mode_reason
        elif not self._state_is_fresh(now_ns):
            self._enter_watchdog(now_ns, "robot state watchdog expired")
            target = self._blend_value(now_ns)
            reason = self._mode_reason
        elif self.mode == ControllerMode.STAND_BLEND:
            target = self._blend_value(now_ns)
            command_enabled = True
            reason = self._mode_reason
            if self._blend_complete(now_ns):
                if self._reference_is_fresh(now_ns):
                    self.mode = ControllerMode.ACTIVE
                    self._mode_reason = "fresh decoded reference"
                    target = self._reference.positions  # type: ignore[union-attr]
                    reason = self._mode_reason
                else:
                    self._enter_watchdog(
                        now_ns, "stand blend complete without a fresh reference"
                    )
                    command_enabled = False
                    target = self._blend_value(now_ns)
                    reason = self._mode_reason
        elif self.mode == ControllerMode.ACTIVE:
            if not self._reference_is_fresh(now_ns):
                self._enter_watchdog(now_ns, "decoded reference watchdog expired")
                target = self._blend_value(now_ns)
                reason = self._mode_reason
            else:
                assert self._reference is not None
                target = self._reference.positions
                command_enabled = True
                reason = "fresh decoded reference"
        elif self.mode == ControllerMode.WATCHDOG_STAND:
            target = self._blend_value(now_ns)
            reason = self._mode_reason

        previous = self._output_positions
        positions, slew_clamps = self._slew(previous, target, dt)
        velocities = tuple(
            (current - prior) / dt for current, prior in zip(positions, previous)
        )
        velocities, velocity_clamps = self._clamp_velocities(velocities)
        positions, position_clamps = self._clamp_positions(positions)
        self._output_positions = positions
        self._last_tick_ns = now_ns
        self._output_sequence += 1
        all_clamps = set(self._pending_clamped_joints)
        all_clamps.update(slew_clamps)
        all_clamps.update(velocity_clamps)
        all_clamps.update(position_clamps)
        ordered_clamps = tuple(
            name for name in CANONICAL_JOINT_ORDER if name in all_clamps
        )
        source_sequence = (
            self._reference.sequence if self._reference is not None else None
        )
        command = SafeJointCommand(
            output_sequence=self._output_sequence,
            computed_steady_time_ns=now_ns,
            positions=positions,
            velocities=velocities,
            mode=self.mode.value,
            command_enabled=command_enabled
            and self.mode in (ControllerMode.STAND_BLEND, ControllerMode.ACTIVE),
            reason=reason,
            session_id=self.session_id,
            source_reference_sequence=source_sequence,
            clamped_joints=ordered_clamps,
        )
        self._pending_clamped_joints = ()
        return command

    def status_dict(self, now_ns: int) -> Dict[str, object]:
        now_ns = self._time(now_ns, "now_ns")
        state_age_ms = (
            None
            if self._state_receipt_ns is None
            else max(0.0, (now_ns - self._state_receipt_ns) / 1_000_000.0)
        )
        reference_age_ms = (
            None
            if self._reference_receipt_ns is None
            else max(0.0, (now_ns - self._reference_receipt_ns) / 1_000_000.0)
        )
        return {
            "schema": "dropbear-wbc-status-v1",
            "authority": AUTHORITY,
            "mode": self.mode.value,
            "reason": self._mode_reason,
            "session_id": self.session_id,
            "estop_latched": self.estop_latched,
            "state_age_ms": state_age_ms,
            "reference_age_ms": reference_age_ms,
            "last_state_sequence": self._last_state_sequence,
            "last_reference_sequence": self._last_reference_sequence,
            "last_token_sequence": self._last_token_sequence,
            "control_hz": self.config.control_hz,
        }

    def _require_session(self, session_id: str) -> None:
        if self.estop_latched:
            raise ContractError("estop is latched")
        if self.session_id is None or session_id != self.session_id:
            raise ContractError("frame session does not match active session")

    def _require_fresh_state(self, now_ns: int) -> None:
        if not self._state_is_fresh(now_ns):
            raise ContractError("fresh robot state is required")

    def _state_is_fresh(self, now_ns: int) -> bool:
        return (
            self._state is not None
            and self._state_receipt_ns is not None
            and now_ns >= self._state_receipt_ns
            and now_ns - self._state_receipt_ns
            <= int(self.config.state_timeout_sec * 1e9)
        )

    def _reference_is_fresh(self, now_ns: int) -> bool:
        return (
            self._reference is not None
            and self._reference_receipt_ns is not None
            and now_ns >= self._reference_receipt_ns
            and now_ns - self._reference_receipt_ns
            <= int(self.config.command_timeout_sec * 1e9)
        )

    def _check_frame_age(
        self, generated_ns: int, receipt_ns: int, frame_name: str
    ) -> None:
        if self._is_future(generated_ns, receipt_ns):
            raise ContractError(f"{frame_name} timestamp is too far in the future")
        if receipt_ns - generated_ns > int(self.config.command_timeout_sec * 1e9):
            raise ContractError(f"{frame_name} was stale on receipt")

    def _is_future(self, source_ns: int, now_ns: int) -> bool:
        return source_ns - now_ns > int(
            self.config.source_future_tolerance_sec * 1e9
        )

    def _require_state_inside_limits(self, positions: Tuple[float, ...]) -> None:
        violations = [
            name
            for name, position in zip(CANONICAL_JOINT_ORDER, positions)
            if position < JOINT_LIMITS[name].lower_rad
            or position > JOINT_LIMITS[name].upper_rad
        ]
        if violations:
            raise ContractError(
                "guarded activation rejected out-of-envelope state: "
                + ",".join(violations)
            )

    def _clamp_positions(
        self, positions: Iterable[float]
    ) -> Tuple[Tuple[float, ...], Tuple[str, ...]]:
        result = []
        clamped = []
        for name, value in zip(CANONICAL_JOINT_ORDER, positions):
            limit = JOINT_LIMITS[name]
            safe = min(limit.upper_rad, max(limit.lower_rad, float(value)))
            result.append(safe)
            if safe != float(value):
                clamped.append(name)
        if len(result) != JOINT_COUNT:
            raise ContractError("position vector has the wrong dimension")
        return tuple(result), tuple(clamped)

    def _clamp_velocities(
        self, velocities: Iterable[float]
    ) -> Tuple[Tuple[float, ...], Tuple[str, ...]]:
        result = []
        clamped = []
        for name, value in zip(CANONICAL_JOINT_ORDER, velocities):
            maximum = JOINT_LIMITS[name].max_velocity_rad_s
            safe = min(maximum, max(-maximum, float(value)))
            result.append(safe)
            if safe != float(value):
                clamped.append(name)
        if len(result) != JOINT_COUNT:
            raise ContractError("velocity vector has the wrong dimension")
        return tuple(result), tuple(clamped)

    def _slew(
        self,
        previous: Tuple[float, ...],
        target: Tuple[float, ...],
        dt: float,
    ) -> Tuple[Tuple[float, ...], Tuple[str, ...]]:
        result = []
        clamped = []
        for name, prior, desired in zip(CANONICAL_JOINT_ORDER, previous, target):
            maximum_delta = JOINT_LIMITS[name].max_velocity_rad_s * dt
            delta = desired - prior
            safe_delta = min(maximum_delta, max(-maximum_delta, delta))
            result.append(prior + safe_delta)
            if safe_delta != delta:
                clamped.append(name)
        return tuple(result), tuple(clamped)

    def _control_dt(self, now_ns: int) -> float:
        nominal = 1.0 / self.config.control_hz
        if self._last_tick_ns is None:
            return nominal
        if now_ns <= self._last_tick_ns:
            raise ContractError("tick time must be strictly monotonic")
        measured = (now_ns - self._last_tick_ns) / 1e9
        # A delayed executor must not turn lost cycles into one large jump.
        return min(measured, 2.0 * nominal)

    def _begin_blend(
        self,
        mode: ControllerMode,
        now_ns: int,
        start: Tuple[float, ...],
        target: Tuple[float, ...],
        duration_sec: float,
        reason: str,
    ) -> None:
        self.mode = mode
        self._blend_start_ns = now_ns
        self._blend_duration_ns = max(1, int(duration_sec * 1e9))
        self._blend_start_positions = tuple(start)
        self._blend_target_positions = tuple(target)
        self._mode_reason = reason

    def _enter_watchdog(self, now_ns: int, reason: str) -> None:
        if self.mode != ControllerMode.WATCHDOG_STAND:
            self._begin_blend(
                ControllerMode.WATCHDOG_STAND,
                now_ns,
                self._output_positions,
                STAND_POSE,
                self.config.watchdog_blend_sec,
                reason + "; guarded reactivation required",
            )
            self.session_id = None
            self._reference = None
            self._reference_receipt_ns = None

    def _blend_complete(self, now_ns: int) -> bool:
        return now_ns - self._blend_start_ns >= self._blend_duration_ns

    def _blend_value(self, now_ns: int) -> Tuple[float, ...]:
        alpha = min(
            1.0,
            max(
                0.0,
                (now_ns - self._blend_start_ns) / self._blend_duration_ns,
            ),
        )
        smooth = alpha * alpha * (3.0 - 2.0 * alpha)
        return tuple(
            start + (target - start) * smooth
            for start, target in zip(
                self._blend_start_positions, self._blend_target_positions
            )
        )

    @staticmethod
    def _time(value: int, field_name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ContractError(f"{field_name} must be a non-negative integer")
        return value
