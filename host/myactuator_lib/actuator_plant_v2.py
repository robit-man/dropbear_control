"""Deterministic extended actuator plant dynamics.

This offline SIL equation core represents source semantics that the V1 plant
deliberately rejects: directional efficiency, peak-duration torque, separate
motor speed and case temperature limits, deterministic sensor noise, command
delay/jitter, multi-rate sampling, and arbitrary feedback delay.  It grants
no support, physical validation, physical I/O, or motion authority.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from fractions import Fraction
from typing import Any, Iterable, Mapping

from .actuator_plant import PlantError, PlantState


SOLVER_ID = "semi-implicit-euler-event-scheduled-v2"
NOISE_ALGORITHM = "sha256-box-muller-counter-v1"
JITTER_ALGORITHM = "sha256-bounded-uniform-counter-v1"
SUPPORT_GRANTED = False
PHYSICAL_VALIDATION = False
PHYSICAL_IO = False
MOTION_AUTHORITY = False
_U64_MAX = (1 << 64) - 1


class PlantV2Error(PlantError):
    """A V2 parameter, command, state, schedule, or snapshot is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PlantV2Error(message)


def _finite(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{label} must be finite",
    )
    return float(value)


def _nonnegative_integer(value: Any, label: str) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0,
        f"{label} must be a nonnegative integer",
    )
    return value


def _positive_integer(value: Any, label: str) -> int:
    result = _nonnegative_integer(value, label)
    _require(result > 0, f"{label} must be positive")
    return result


def _fraction(value: float) -> Fraction:
    return Fraction(str(value))


def _fraction_record(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _load_fraction(value: Any, label: str) -> Fraction:
    _require(
        isinstance(value, Mapping)
        and set(value) == {"numerator", "denominator"},
        f"{label} rational record is not closed",
    )
    numerator = value["numerator"]
    denominator = value["denominator"]
    _require(
        isinstance(numerator, int)
        and not isinstance(numerator, bool)
        and isinstance(denominator, int)
        and not isinstance(denominator, bool)
        and denominator > 0,
        f"{label} rational record is invalid",
    )
    return Fraction(numerator, denominator)


def _period_boundary_at_or_after(
    value: Fraction,
    period: Fraction,
) -> Fraction:
    _require(value >= 0 and period > 0, "period boundary input is invalid")
    quotient, remainder = divmod(value, period)
    return quotient * period if remainder == 0 else (quotient + 1) * period


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _sign(value: float) -> float:
    if value > 0.0:
        return 1.0
    if value < 0.0:
        return -1.0
    return 0.0


def _quantize(value: float, quantum: float) -> float:
    if quantum == 0.0:
        return value
    scaled = value / quantum
    integral = (
        math.floor(scaled + 0.5)
        if scaled >= 0.0
        else math.ceil(scaled - 0.5)
    )
    return integral * quantum


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _counter_digest(
    seed: int,
    stream: str,
    sequence: int,
    lane: int,
) -> bytes:
    _nonnegative_integer(seed, "reset seed")
    _nonnegative_integer(sequence, "counter sequence")
    _nonnegative_integer(lane, "counter lane")
    _require(
        isinstance(stream, str) and stream and "\0" not in stream,
        "counter stream is invalid",
    )
    return hashlib.sha256(
        f"{seed}\0{stream}\0{sequence}\0{lane}".encode("ascii")
    ).digest()


def _uniform_fraction(
    seed: int,
    stream: str,
    sequence: int,
    lane: int = 0,
) -> Fraction:
    raw = int.from_bytes(
        _counter_digest(seed, stream, sequence, lane)[:8],
        "big",
    )
    return Fraction(raw + 1, _U64_MAX + 2)


def _centered_uniform_fraction(
    seed: int,
    stream: str,
    sequence: int,
) -> Fraction:
    raw = int.from_bytes(
        _counter_digest(seed, stream, sequence, 0)[:8],
        "big",
    )
    return Fraction(2 * raw - _U64_MAX, _U64_MAX)


def _normal(seed: int, stream: str, sequence: int) -> float:
    u1 = float(_uniform_fraction(seed, stream, sequence, 0))
    u2 = float(_uniform_fraction(seed, stream, sequence, 1))
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


@dataclass(frozen=True)
class PlantV2Parameters:
    current_loop_period_s: float
    phase_resistance_ohm: float
    phase_inductance_h: float
    torque_constant_nm_per_a: float
    back_emf_v_s_per_rad: float
    maximum_qaxis_current_a: float
    rotor_inertia_kg_m2: float
    output_inertia_kg_m2: float
    coulomb_friction_nm: float
    viscous_friction_nm_s_per_rad: float
    gear_ratio_motor_per_output: float
    forward_efficiency_ratio: float
    reverse_efficiency_ratio: float
    transmission_stiffness_nm_per_rad: float
    transmission_damping_nm_s_per_rad: float
    backlash_rad: float
    maximum_motor_speed_rad_s: float
    maximum_output_speed_rad_s: float
    maximum_continuous_output_torque_nm: float
    maximum_peak_output_torque_nm: float
    peak_duration_s: float
    winding_to_case_resistance_k_per_w: float
    case_to_ambient_resistance_k_per_w: float
    winding_thermal_capacity_j_per_k: float
    case_thermal_capacity_j_per_k: float
    maximum_winding_temperature_k: float
    maximum_case_temperature_k: float
    position_quantum_rad: float
    position_noise_stddev_rad: float
    velocity_noise_stddev_rad_s: float
    current_noise_stddev_a: float
    command_delay_s: float
    state_sample_period_s: float
    feedback_delay_s: float
    delay_jitter_s: float
    supply_voltage_v: float
    ambient_temperature_k: float
    position_lower_rad: float
    position_upper_rad: float
    output_load_torque_bound_nm: float
    current_controller_kp_v_per_a: float
    winding_derate_start_temperature_k: float
    case_derate_start_temperature_k: float

    def validate(self) -> None:
        values = asdict(self)
        _require(
            set(values) == set(self.__dataclass_fields__),
            "V2 parameter field closure violated",
        )
        for name, value in values.items():
            _finite(value, f"parameter {name}")
        nonnegative = {
            "coulomb_friction_nm",
            "viscous_friction_nm_s_per_rad",
            "backlash_rad",
            "position_quantum_rad",
            "position_noise_stddev_rad",
            "velocity_noise_stddev_rad_s",
            "current_noise_stddev_a",
            "command_delay_s",
            "feedback_delay_s",
            "delay_jitter_s",
        }
        for name in nonnegative:
            _require(values[name] >= 0.0, f"{name} must be nonnegative")
        for name in set(values) - nonnegative - {
            "position_lower_rad",
            "position_upper_rad",
        }:
            _require(values[name] > 0.0, f"{name} must be positive")
        for name in (
            "forward_efficiency_ratio",
            "reverse_efficiency_ratio",
        ):
            _require(
                0.0 < values[name] <= 1.0,
                f"{name} must be in (0, 1]",
            )
        _require(
            self.position_lower_rad < 0.0 < self.position_upper_rad,
            "position interval must contain reset position zero",
        )
        _require(
            self.maximum_peak_output_torque_nm
            >= self.maximum_continuous_output_torque_nm,
            "peak torque must not be below continuous torque",
        )
        _require(
            self.state_sample_period_s >= self.current_loop_period_s,
            "state sample period must not be faster than the solver",
        )
        _require(
            self.ambient_temperature_k
            < self.winding_derate_start_temperature_k
            < self.maximum_winding_temperature_k,
            "winding thermal thresholds must increase from ambient",
        )
        _require(
            self.ambient_temperature_k
            < self.case_derate_start_temperature_k
            < self.maximum_case_temperature_k,
            "case thermal thresholds must increase from ambient",
        )
        _require(
            self.output_load_torque_bound_nm
            <= self.maximum_peak_output_torque_nm,
            "load bound exceeds sourced peak torque",
        )


@dataclass(frozen=True)
class PlantV2Semantics:
    torque_regime: str
    rotation_direction: str
    jitter_application: str
    efficiency_direction_basis: str = "transmission_torque_sign"
    peak_recovery_policy: str = "one_shot_per_reset_no_recovery"
    command_activation_policy: str = "first_solver_boundary_at_or_after"
    sensor_capture_policy: str = "linear_interpolation_at_exact_period"
    feedback_delivery_policy: str = "first_solver_boundary_at_or_after"
    noise_algorithm: str = NOISE_ALGORITHM
    jitter_algorithm: str = JITTER_ALGORITHM

    def validate(self, parameters: PlantV2Parameters) -> None:
        _require(
            set(asdict(self)) == set(self.__dataclass_fields__),
            "V2 semantics field closure violated",
        )
        _require(
            self.torque_regime
            in {"continuous_only", "peak_one_shot_per_reset"},
            "unknown V2 torque regime",
        )
        _require(
            self.rotation_direction
            in {"positive", "negative", "bidirectional"},
            "unknown V2 rotation direction",
        )
        _require(
            self.jitter_application
            in {"command_only", "feedback_only", "command_and_feedback"},
            "unknown V2 jitter application",
        )
        _require(
            self.efficiency_direction_basis == "transmission_torque_sign",
            "unsupported directional-efficiency basis",
        )
        _require(
            self.peak_recovery_policy == "one_shot_per_reset_no_recovery",
            "unsupported peak recovery policy",
        )
        _require(
            self.command_activation_policy
            == "first_solver_boundary_at_or_after",
            "unsupported command activation policy",
        )
        _require(
            self.sensor_capture_policy
            == "linear_interpolation_at_exact_period",
            "unsupported sensor capture policy",
        )
        _require(
            self.feedback_delivery_policy
            == "first_solver_boundary_at_or_after",
            "unsupported feedback delivery policy",
        )
        _require(
            self.noise_algorithm == NOISE_ALGORITHM
            and self.jitter_algorithm == JITTER_ALGORITHM,
            "noise/jitter algorithm identity mismatch",
        )
        if parameters.delay_jitter_s > 0.0:
            _require(
                self.jitter_application
                in {"command_only", "feedback_only", "command_and_feedback"},
                "nonzero jitter is not assigned",
            )


@dataclass(frozen=True)
class PlantV2Configuration:
    parameter_set_id: str
    parameters: PlantV2Parameters
    semantics: PlantV2Semantics

    def validate(self) -> None:
        _require(
            isinstance(self.parameter_set_id, str)
            and self.parameter_set_id
            and "\0" not in self.parameter_set_id,
            "V2 parameter_set_id is invalid",
        )
        _require(
            isinstance(self.parameters, PlantV2Parameters)
            and isinstance(self.semantics, PlantV2Semantics),
            "typed V2 parameters and semantics are required",
        )
        self.parameters.validate()
        self.semantics.validate(self.parameters)

    @property
    def configuration_sha256(self) -> str:
        self.validate()
        return _digest(
            {
                "parameter_set_id": self.parameter_set_id,
                "parameters": {
                    name: float(value)
                    for name, value in asdict(self.parameters).items()
                },
                "semantics": asdict(self.semantics),
                "solver_id": SOLVER_ID,
            }
        )


@dataclass(frozen=True)
class PlantV2Command:
    sequence: int
    issued_step_index: int
    enabled: bool
    target_qaxis_current_a: float
    deadline_step_index: int | None = None


@dataclass(frozen=True)
class PlantV2Time:
    """Canonical rational simulation time suitable for JSON snapshots."""

    numerator: int
    denominator: int

    @classmethod
    def from_fraction(cls, value: Fraction) -> "PlantV2Time":
        return cls(value.numerator, value.denominator)

    def as_fraction(self) -> Fraction:
        _require(
            isinstance(self.numerator, int)
            and not isinstance(self.numerator, bool)
            and isinstance(self.denominator, int)
            and not isinstance(self.denominator, bool)
            and self.numerator >= 0
            and self.denominator > 0,
            "V2 rational time is invalid",
        )
        return Fraction(self.numerator, self.denominator)

    @property
    def seconds(self) -> float:
        return float(self.as_fraction())


def _load_plant_time(value: Any, label: str) -> PlantV2Time:
    _require(
        isinstance(value, Mapping)
        and set(value) == {"numerator", "denominator"},
        f"{label} rational time record is not closed",
    )
    result = PlantV2Time(
        numerator=value["numerator"],
        denominator=value["denominator"],
    )
    result.as_fraction()
    return result


@dataclass(frozen=True)
class _ScheduledCommand:
    command: PlantV2Command
    jitter_s: float
    eligible_time: Fraction


@dataclass(frozen=True)
class _ActiveCommand:
    command: PlantV2Command
    jitter_s: float
    eligible_time: Fraction
    activation_step_index: int
    activation_time: Fraction


@dataclass(frozen=True)
class PlantV2SensorSample:
    sample_sequence: int
    source_lower_step_index: int
    source_upper_step_index: int
    capture_time: PlantV2Time
    eligible_delivery_time: PlantV2Time
    delivered_step_index: int | None
    delivery_time: PlantV2Time | None
    output_position_rad: float
    output_velocity_rad_s: float
    qaxis_current_a: float
    winding_temperature_k: float
    position_noise_rad: float
    velocity_noise_rad_s: float
    current_noise_a: float
    feedback_jitter_s: float


@dataclass(frozen=True)
class _ScheduledSample:
    sample: PlantV2SensorSample
    eligible_time: Fraction


@dataclass(frozen=True)
class PlantV2Diagnostics:
    solver_id: str
    noise_algorithm: str
    jitter_algorithm: str
    active_command_sequence: int
    active_command_issued_step_index: int | None
    active_command_eligible_time: PlantV2Time | None
    active_command_activation_step_index: int | None
    active_command_activation_time: PlantV2Time | None
    active_command_jitter_s: float | None
    command_activated_this_step: bool
    stale_command_count: int
    expired_command_count: int
    command_derate: float
    applied_voltage_v: float
    motor_torque_nm: float
    transmission_torque_nm: float
    active_efficiency_ratio: float
    active_output_torque_limit_nm: float
    peak_time_used_s: float
    peak_budget_exhausted: bool
    captured_sample_count: int
    delivered_sample_count: int
    stale_sample_count: int
    current_saturated: bool
    voltage_saturated: bool
    motor_torque_saturated: bool
    output_torque_saturated: bool
    motor_speed_saturated: bool
    output_speed_saturated: bool
    position_limited: bool
    thermal_shutdown: bool
    finite: bool


@dataclass(frozen=True)
class PlantV2Step:
    state: PlantState
    sample: PlantV2SensorSample | None
    diagnostics: PlantV2Diagnostics


def _interpolate_state(
    lower: PlantState,
    upper: PlantState,
    alpha: float,
    capture_time: Fraction,
) -> PlantState:
    _require(0.0 <= alpha <= 1.0, "sensor interpolation escaped interval")

    def interpolate(name: str) -> float:
        return float(getattr(lower, name)) + alpha * (
            float(getattr(upper, name)) - float(getattr(lower, name))
        )

    return PlantState(
        step_index=upper.step_index,
        monotonic_s=float(capture_time),
        qaxis_current_a=interpolate("qaxis_current_a"),
        rotor_position_rad=interpolate("rotor_position_rad"),
        rotor_velocity_rad_s=interpolate("rotor_velocity_rad_s"),
        output_position_rad=interpolate("output_position_rad"),
        output_velocity_rad_s=interpolate("output_velocity_rad_s"),
        winding_temperature_k=interpolate("winding_temperature_k"),
        case_temperature_k=interpolate("case_temperature_k"),
    )


class DeterministicActuatorPlantV2:
    """Extended deterministic single-actuator SIL plant."""

    def __init__(
        self,
        configuration: PlantV2Configuration,
        *,
        seed: int = 0,
    ) -> None:
        _require(
            isinstance(configuration, PlantV2Configuration),
            "typed V2 configuration is required",
        )
        configuration.validate()
        self.configuration = configuration
        self.parameters = configuration.parameters
        self.semantics = configuration.semantics
        self._dt = _fraction(self.parameters.current_loop_period_s)
        self._sample_period = _fraction(
            self.parameters.state_sample_period_s
        )
        self._seed = 0
        self._state = self._zero_state()
        self._active_command: _ActiveCommand | None = None
        self._pending_commands: list[_ScheduledCommand] = []
        self._next_command_sequence = 1
        self._command_watermark = 0
        self._peak_time_used = Fraction(0)
        self._capture_sequence = 0
        self._next_capture_time = Fraction(0)
        self._pending_samples: list[_ScheduledSample] = []
        self._latest_sample: PlantV2SensorSample | None = None
        self._last_step = self._empty_step()
        self.reset(seed=seed)

    def _zero_state(self) -> PlantState:
        return PlantState(
            0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            self.parameters.ambient_temperature_k,
            self.parameters.ambient_temperature_k,
        )

    def _empty_diagnostics(self) -> PlantV2Diagnostics:
        return PlantV2Diagnostics(
            SOLVER_ID,
            NOISE_ALGORITHM,
            JITTER_ALGORITHM,
            0,
            None,
            None,
            None,
            None,
            None,
            False,
            0,
            0,
            1.0,
            0.0,
            0.0,
            0.0,
            1.0,
            self.parameters.maximum_continuous_output_torque_nm,
            0.0,
            False,
            0,
            0,
            0,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            True,
        )

    def _empty_step(self) -> PlantV2Step:
        return PlantV2Step(
            self._state,
            self._latest_sample,
            self._empty_diagnostics(),
        )

    @property
    def state(self) -> PlantState:
        return self._state

    @property
    def last_step(self) -> PlantV2Step:
        return self._last_step

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def next_command_sequence(self) -> int:
        return self._next_command_sequence

    def _validate_state(self, state: PlantState) -> None:
        _require(
            isinstance(state, PlantState),
            "typed plant state is required",
        )
        _nonnegative_integer(state.step_index, "state step_index")
        expected_time = state.step_index * self._dt
        _require(
            math.isclose(
                state.monotonic_s,
                float(expected_time),
                rel_tol=0.0,
                abs_tol=1.0e-12,
            ),
            "state time is not on the solver grid",
        )
        for name, value in asdict(state).items():
            if name != "step_index":
                _finite(value, f"state {name}")
        p = self.parameters
        _require(
            p.position_lower_rad
            <= state.output_position_rad
            <= p.position_upper_rad,
            "state output position is outside limits",
        )
        _require(
            abs(state.output_velocity_rad_s)
            <= p.maximum_output_speed_rad_s,
            "state output velocity is outside limits",
        )
        _require(
            abs(state.rotor_velocity_rad_s)
            <= p.maximum_motor_speed_rad_s,
            "state motor velocity is outside limits",
        )

    def reset(
        self,
        *,
        seed: int = 0,
        state: PlantState | None = None,
    ) -> PlantV2Step:
        _nonnegative_integer(seed, "reset seed")
        _require(seed <= _U64_MAX, "reset seed exceeds u64")
        candidate = state if state is not None else self._zero_state()
        self._validate_state(candidate)
        self._seed = seed
        self._state = candidate
        self._active_command = None
        self._pending_commands = []
        self._next_command_sequence = 1
        self._command_watermark = 0
        self._peak_time_used = Fraction(0)
        self._capture_sequence = 0
        now = Fraction(candidate.step_index) * self._dt
        self._next_capture_time = _period_boundary_at_or_after(
            now,
            self._sample_period,
        )
        self._pending_samples = []
        self._latest_sample = None
        self._capture_due(
            candidate,
            candidate,
            now,
            now,
        )
        delivered, _ = self._deliver_due(now, candidate.step_index)
        self._last_step = PlantV2Step(
            candidate,
            self._latest_sample,
            replace(
                self._empty_diagnostics(),
                captured_sample_count=self._capture_sequence,
                delivered_sample_count=delivered,
            ),
        )
        return self._last_step

    def _jitter_applies(self, kind: str) -> bool:
        selected = self.semantics.jitter_application
        return selected == "command_and_feedback" or selected == f"{kind}_only"

    def _delay_with_jitter(
        self,
        *,
        base_s: float,
        kind: str,
        sequence: int,
        seed: int | None = None,
    ) -> tuple[Fraction, float]:
        selected_seed = self._seed if seed is None else seed
        jitter = Fraction(0)
        if self.parameters.delay_jitter_s > 0.0 and self._jitter_applies(kind):
            jitter = (
                _fraction(self.parameters.delay_jitter_s)
                * _centered_uniform_fraction(
                    selected_seed,
                    f"{kind}-delay-jitter",
                    sequence,
                )
            )
        delay = max(Fraction(0), _fraction(base_s) + jitter)
        return delay, float(jitter)

    def _validate_command_values(
        self,
        command: PlantV2Command,
        *,
        label: str,
    ) -> None:
        _require(
            isinstance(command, PlantV2Command),
            f"typed {label} is required",
        )
        _positive_integer(command.sequence, f"{label} sequence")
        _nonnegative_integer(
            command.issued_step_index,
            f"{label} issued_step_index",
        )
        if command.deadline_step_index is not None:
            _positive_integer(
                command.deadline_step_index,
                f"{label} deadline_step_index",
            )
            _require(
                command.deadline_step_index
                > command.issued_step_index,
                f"{label} deadline must follow issue step",
            )
        _require(
            isinstance(command.enabled, bool),
            f"{label} enabled must be bool",
        )
        target = _finite(
            command.target_qaxis_current_a,
            f"{label} target current",
        )
        _require(
            abs(target) <= self.parameters.maximum_qaxis_current_a,
            f"{label} current exceeds source limit",
        )
        if not command.enabled:
            _require(
                target == 0.0,
                f"disabled {label} target must be zero",
            )
        direction = self.semantics.rotation_direction
        _require(
            not (
                (direction == "positive" and target < 0.0)
                or (direction == "negative" and target > 0.0)
            ),
            f"{label} direction exceeds execution semantics",
        )

    def submit(self, command: PlantV2Command) -> None:
        self._validate_command_values(command, label="command")
        _require(
            command.sequence == self._next_command_sequence,
            "command sequence is not exact",
        )
        _require(
            command.issued_step_index == self._state.step_index,
            "command issue step is stale or future",
        )
        delay, jitter = self._delay_with_jitter(
            base_s=self.parameters.command_delay_s,
            kind="command",
            sequence=command.sequence,
        )
        issued_time = self._state.step_index * self._dt
        self._pending_commands.append(
            _ScheduledCommand(
                command,
                jitter,
                issued_time + delay,
            )
        )
        self._pending_commands.sort(
            key=lambda item: (
                item.eligible_time,
                item.command.sequence,
            )
        )
        self._next_command_sequence += 1

    def _activate_due_commands(
        self,
        now: Fraction,
        step_index: int,
    ) -> tuple[bool, int, int]:
        due = [
            item
            for item in self._pending_commands
            if item.eligible_time <= now
        ]
        expired = [
            item
            for item in self._pending_commands
            if item.command.deadline_step_index is not None
            and item.command.deadline_step_index <= step_index
        ]
        expired_ids = {item.command.sequence for item in expired}
        active_expired = (
            self._active_command is not None
            and self._active_command.command.deadline_step_index is not None
            and self._active_command.command.deadline_step_index <= step_index
        )
        if active_expired:
            self._command_watermark = max(
                self._command_watermark,
                self._active_command.command.sequence,
            )
            self._active_command = None
        if expired:
            newest_expired = max(expired_ids)
            self._command_watermark = max(
                self._command_watermark,
                newest_expired,
            )
            if (
                self._active_command is not None
                and self._active_command.command.sequence < newest_expired
            ):
                self._active_command = None
        if expired_ids:
            self._pending_commands = [
                item
                for item in self._pending_commands
                if item.command.sequence not in expired_ids
            ]
        due = [
            item
            for item in self._pending_commands
            if item.eligible_time <= now
        ]
        if not due:
            return False, 0, len(expired) + int(active_expired)
        due.sort(key=lambda item: item.command.sequence)
        admissible = [
            item
            for item in due
            if item.command.sequence > self._command_watermark
        ]
        selected = admissible[-1] if admissible else None
        stale_count = len(due) - (1 if selected is not None else 0)
        if selected is not None:
            self._active_command = _ActiveCommand(
                command=selected.command,
                jitter_s=selected.jitter_s,
                eligible_time=selected.eligible_time,
                activation_step_index=step_index,
                activation_time=now,
            )
            self._command_watermark = selected.command.sequence
        due_ids = {item.command.sequence for item in due}
        self._pending_commands = [
            item
            for item in self._pending_commands
            if item.command.sequence not in due_ids
        ]
        return (
            selected is not None,
            stale_count,
            len(expired) + int(active_expired),
        )

    def _derate(self, value: float, start: float, stop: float) -> float:
        if value >= stop:
            return 0.0
        if value <= start:
            return 1.0
        return (stop - value) / (stop - start)

    def _transmission_deflection(self, state: PlantState) -> float:
        p = self.parameters
        relative = (
            state.rotor_position_rad / p.gear_ratio_motor_per_output
            - state.output_position_rad
        )
        half_backlash = p.backlash_rad / 2.0
        if relative > half_backlash:
            return relative - half_backlash
        if relative < -half_backlash:
            return relative + half_backlash
        return 0.0

    def _capture_sample(
        self,
        state: PlantState,
        capture_time: Fraction,
        lower_step: int,
        upper_step: int,
    ) -> None:
        p = self.parameters
        sequence = self._capture_sequence + 1
        position_noise = (
            p.position_noise_stddev_rad
            * _normal(self._seed, "position-noise", sequence)
            if p.position_noise_stddev_rad
            else 0.0
        )
        velocity_noise = (
            p.velocity_noise_stddev_rad_s
            * _normal(self._seed, "velocity-noise", sequence)
            if p.velocity_noise_stddev_rad_s
            else 0.0
        )
        current_noise = (
            p.current_noise_stddev_a
            * _normal(self._seed, "current-noise", sequence)
            if p.current_noise_stddev_a
            else 0.0
        )
        delay, feedback_jitter = self._delay_with_jitter(
            base_s=p.feedback_delay_s,
            kind="feedback",
            sequence=sequence,
        )
        eligible_time = capture_time + delay
        sample = PlantV2SensorSample(
            sample_sequence=sequence,
            source_lower_step_index=lower_step,
            source_upper_step_index=upper_step,
            capture_time=PlantV2Time.from_fraction(capture_time),
            eligible_delivery_time=PlantV2Time.from_fraction(
                eligible_time
            ),
            delivered_step_index=None,
            delivery_time=None,
            output_position_rad=_quantize(
                state.output_position_rad + position_noise,
                p.position_quantum_rad,
            ),
            output_velocity_rad_s=(
                state.output_velocity_rad_s + velocity_noise
            ),
            qaxis_current_a=state.qaxis_current_a + current_noise,
            winding_temperature_k=state.winding_temperature_k,
            position_noise_rad=position_noise,
            velocity_noise_rad_s=velocity_noise,
            current_noise_a=current_noise,
            feedback_jitter_s=feedback_jitter,
        )
        self._pending_samples.append(
            _ScheduledSample(sample, eligible_time)
        )
        self._pending_samples.sort(
            key=lambda item: (
                item.eligible_time,
                item.sample.sample_sequence,
            )
        )
        self._capture_sequence = sequence

    def _capture_due(
        self,
        lower: PlantState,
        upper: PlantState,
        start: Fraction,
        end: Fraction,
    ) -> int:
        count = 0
        while self._next_capture_time <= end:
            capture_time = self._next_capture_time
            if capture_time < start:
                self._next_capture_time += self._sample_period
                continue
            if end == start:
                alpha = 0.0
            else:
                alpha = float((capture_time - start) / (end - start))
            sampled_state = _interpolate_state(
                lower,
                upper,
                alpha,
                capture_time,
            )
            self._capture_sample(
                sampled_state,
                capture_time,
                lower.step_index,
                upper.step_index,
            )
            self._next_capture_time += self._sample_period
            count += 1
        return count

    def _deliver_due(
        self,
        now: Fraction,
        step_index: int,
    ) -> tuple[int, int]:
        due = [
            item
            for item in self._pending_samples
            if item.eligible_time <= now
        ]
        if not due:
            return 0, 0
        due.sort(key=lambda item: item.sample.sample_sequence)
        watermark = (
            self._latest_sample.sample_sequence
            if self._latest_sample is not None
            else 0
        )
        admissible = [
            item for item in due if item.sample.sample_sequence > watermark
        ]
        for item in admissible:
            self._latest_sample = replace(
                item.sample,
                delivered_step_index=step_index,
                delivery_time=PlantV2Time.from_fraction(now),
            )
        due_ids = {item.sample.sample_sequence for item in due}
        self._pending_samples = [
            item
            for item in self._pending_samples
            if item.sample.sample_sequence not in due_ids
        ]
        return len(admissible), len(due) - len(admissible)

    def _validate_sample(
        self,
        sample: PlantV2SensorSample,
        *,
        label: str,
        now: Fraction,
        seed: int,
    ) -> None:
        _positive_integer(sample.sample_sequence, f"{label} sequence")
        lower_step = _nonnegative_integer(
            sample.source_lower_step_index,
            f"{label} lower source step",
        )
        upper_step = _nonnegative_integer(
            sample.source_upper_step_index,
            f"{label} upper source step",
        )
        _require(
            lower_step <= upper_step <= int(now / self._dt),
            f"{label} source steps are inconsistent",
        )
        for name in (
            "output_position_rad",
            "output_velocity_rad_s",
            "qaxis_current_a",
            "winding_temperature_k",
            "position_noise_rad",
            "velocity_noise_rad_s",
            "current_noise_a",
            "feedback_jitter_s",
        ):
            _finite(getattr(sample, name), f"{label} {name}")
        _require(
            isinstance(sample.capture_time, PlantV2Time)
            and isinstance(
                sample.eligible_delivery_time,
                PlantV2Time,
            ),
            f"{label} rational times are not typed",
        )
        capture_time = sample.capture_time.as_fraction()
        eligible_time = sample.eligible_delivery_time.as_fraction()
        _require(
            capture_time >= 0
            and capture_time % self._sample_period == 0
            and eligible_time >= capture_time,
            f"{label} capture/eligibility timing is inconsistent",
        )
        expected_delay, expected_jitter = self._delay_with_jitter(
            base_s=self.parameters.feedback_delay_s,
            kind="feedback",
            sequence=sample.sample_sequence,
            seed=seed,
        )
        _require(
            math.isclose(
                sample.feedback_jitter_s,
                expected_jitter,
                rel_tol=0.0,
                abs_tol=1.0e-15,
            )
            and math.isclose(
                float(eligible_time),
                float(capture_time + expected_delay),
                rel_tol=0.0,
                abs_tol=0.0,
            )
            and eligible_time == capture_time + expected_delay,
            f"{label} deterministic feedback timing drift",
        )
        p = self.parameters
        expected_noises = (
            (
                "position_noise_rad",
                p.position_noise_stddev_rad,
                "position-noise",
            ),
            (
                "velocity_noise_rad_s",
                p.velocity_noise_stddev_rad_s,
                "velocity-noise",
            ),
            (
                "current_noise_a",
                p.current_noise_stddev_a,
                "current-noise",
            ),
        )
        for field_name, deviation, stream in expected_noises:
            expected = (
                deviation
                * _normal(seed, stream, sample.sample_sequence)
                if deviation
                else 0.0
            )
            _require(
                getattr(sample, field_name) == expected,
                f"{label} deterministic noise drift",
            )
        delivered_step = sample.delivered_step_index
        delivered_time = sample.delivery_time
        _require(
            (delivered_step is None) == (delivered_time is None),
            f"{label} delivery fields are not paired",
        )
        if delivered_step is not None and delivered_time is not None:
            delivered_step = _nonnegative_integer(
                delivered_step,
                f"{label} delivered step",
            )
            _require(
                isinstance(delivered_time, PlantV2Time),
                f"{label} delivery rational time is not typed",
            )
            delivered_fraction = delivered_time.as_fraction()
            _require(
                delivered_step <= int(now / self._dt)
                and delivered_fraction == delivered_step * self._dt
                and delivered_fraction >= eligible_time,
                f"{label} delivery timing is inconsistent",
            )

    def step(
        self,
        *,
        output_load_torque_nm: float = 0.0,
    ) -> PlantV2Step:
        p = self.parameters
        load = _finite(output_load_torque_nm, "output load torque")
        _require(
            abs(load) <= p.output_load_torque_bound_nm,
            "output load exceeds reviewed bound",
        )
        lower = self._state
        start = lower.step_index * self._dt
        end = start + self._dt
        activated, stale_commands, expired_commands = (
            self._activate_due_commands(
            start,
            lower.step_index,
            )
        )
        active = self._active_command
        command = active.command if active is not None else None
        enabled = command.enabled if command is not None else False
        requested_current = (
            command.target_qaxis_current_a
            if command is not None and enabled
            else 0.0
        )

        winding_derate = self._derate(
            lower.winding_temperature_k,
            p.winding_derate_start_temperature_k,
            p.maximum_winding_temperature_k,
        )
        case_derate = self._derate(
            lower.case_temperature_k,
            p.case_derate_start_temperature_k,
            p.maximum_case_temperature_k,
        )
        derate = min(winding_derate, case_derate)
        target_limit = p.maximum_qaxis_current_a * derate
        target_current = _clamp(
            requested_current,
            -target_limit,
            target_limit,
        )
        current_saturated = target_current != requested_current

        back_emf = (
            p.back_emf_v_s_per_rad * lower.rotor_velocity_rad_s
        )
        voltage_unbounded = (
            p.phase_resistance_ohm * target_current
            + back_emf
            + p.current_controller_kp_v_per_a
            * (target_current - lower.qaxis_current_a)
        )
        voltage = _clamp(
            voltage_unbounded,
            -p.supply_voltage_v,
            p.supply_voltage_v,
        )
        voltage_saturated = voltage != voltage_unbounded
        current_derivative = (
            voltage
            - p.phase_resistance_ohm * lower.qaxis_current_a
            - back_emf
        ) / p.phase_inductance_h
        current_unbounded = (
            lower.qaxis_current_a
            + current_derivative * p.current_loop_period_s
        )
        current = _clamp(
            current_unbounded,
            -p.maximum_qaxis_current_a,
            p.maximum_qaxis_current_a,
        )
        current_saturated = (
            current_saturated or current != current_unbounded
        )

        maximum_motor_torque = (
            p.torque_constant_nm_per_a * p.maximum_qaxis_current_a
        )
        motor_torque_unbounded = p.torque_constant_nm_per_a * current
        motor_torque = _clamp(
            motor_torque_unbounded,
            -maximum_motor_torque,
            maximum_motor_torque,
        )
        motor_torque_saturated = (
            motor_torque != motor_torque_unbounded
        )

        deflection = self._transmission_deflection(lower)
        relative_speed = (
            lower.rotor_velocity_rad_s / p.gear_ratio_motor_per_output
            - lower.output_velocity_rad_s
        )
        transmission_unbounded = 0.0
        if deflection != 0.0:
            transmission_unbounded = (
                p.transmission_stiffness_nm_per_rad * deflection
                + p.transmission_damping_nm_s_per_rad * relative_speed
            )

        peak_available = (
            self.semantics.torque_regime
            == "peak_one_shot_per_reset"
            and self._peak_time_used + self._dt
            <= _fraction(p.peak_duration_s)
        )
        output_torque_limit = (
            p.maximum_peak_output_torque_nm
            if peak_available
            else p.maximum_continuous_output_torque_nm
        )
        transmission_torque = _clamp(
            transmission_unbounded,
            -output_torque_limit,
            output_torque_limit,
        )
        output_torque_saturated = (
            transmission_torque != transmission_unbounded
        )
        if (
            abs(transmission_torque)
            > p.maximum_continuous_output_torque_nm
        ):
            self._peak_time_used += self._dt

        efficiency = (
            p.forward_efficiency_ratio
            if transmission_torque >= 0.0
            else p.reverse_efficiency_ratio
        )
        reflected_motor_load = transmission_torque / (
            p.gear_ratio_motor_per_output * efficiency
        )
        rotor_acceleration = (
            motor_torque - reflected_motor_load
        ) / p.rotor_inertia_kg_m2
        rotor_velocity_unbounded = (
            lower.rotor_velocity_rad_s
            + rotor_acceleration * p.current_loop_period_s
        )
        rotor_velocity = _clamp(
            rotor_velocity_unbounded,
            -p.maximum_motor_speed_rad_s,
            p.maximum_motor_speed_rad_s,
        )
        motor_speed_saturated = (
            rotor_velocity != rotor_velocity_unbounded
        )
        rotor_position = (
            lower.rotor_position_rad
            + rotor_velocity * p.current_loop_period_s
        )

        external_net = transmission_torque - load
        if abs(lower.output_velocity_rad_s) > 1.0e-12:
            friction = (
                p.coulomb_friction_nm
                * _sign(lower.output_velocity_rad_s)
                + p.viscous_friction_nm_s_per_rad
                * lower.output_velocity_rad_s
            )
            output_acceleration = (
                external_net - friction
            ) / p.output_inertia_kg_m2
        elif abs(external_net) <= p.coulomb_friction_nm:
            output_acceleration = 0.0
        else:
            friction = p.coulomb_friction_nm * _sign(external_net)
            output_acceleration = (
                external_net - friction
            ) / p.output_inertia_kg_m2
        output_velocity_unbounded = (
            lower.output_velocity_rad_s
            + output_acceleration * p.current_loop_period_s
        )
        output_velocity = _clamp(
            output_velocity_unbounded,
            -p.maximum_output_speed_rad_s,
            p.maximum_output_speed_rad_s,
        )
        output_speed_saturated = (
            output_velocity != output_velocity_unbounded
        )
        output_position_unbounded = (
            lower.output_position_rad
            + output_velocity * p.current_loop_period_s
        )
        output_position = _clamp(
            output_position_unbounded,
            p.position_lower_rad,
            p.position_upper_rad,
        )
        position_limited = output_position != output_position_unbounded
        if position_limited and (
            (
                output_position == p.position_upper_rad
                and output_velocity > 0.0
            )
            or (
                output_position == p.position_lower_rad
                and output_velocity < 0.0
            )
        ):
            output_velocity = 0.0

        copper_loss_w = p.phase_resistance_ohm * current**2
        winding_derivative = (
            copper_loss_w
            - (
                lower.winding_temperature_k
                - lower.case_temperature_k
            )
            / p.winding_to_case_resistance_k_per_w
        ) / p.winding_thermal_capacity_j_per_k
        case_derivative = (
            (
                lower.winding_temperature_k
                - lower.case_temperature_k
            )
            / p.winding_to_case_resistance_k_per_w
            - (
                lower.case_temperature_k
                - p.ambient_temperature_k
            )
            / p.case_to_ambient_resistance_k_per_w
        ) / p.case_thermal_capacity_j_per_k
        winding_temperature = (
            lower.winding_temperature_k
            + winding_derivative * p.current_loop_period_s
        )
        case_temperature = (
            lower.case_temperature_k
            + case_derivative * p.current_loop_period_s
        )

        state = PlantState(
            lower.step_index + 1,
            float(end),
            current,
            rotor_position,
            rotor_velocity,
            output_position,
            output_velocity,
            winding_temperature,
            case_temperature,
        )
        finite = all(
            math.isfinite(float(value))
            for name, value in asdict(state).items()
            if name != "step_index"
        )
        _require(finite, "V2 plant state became non-finite")
        captured = self._capture_due(lower, state, start, end)
        delivered, stale_samples = self._deliver_due(
            end,
            state.step_index,
        )
        thermal_shutdown = (
            state.winding_temperature_k
            >= p.maximum_winding_temperature_k
            or state.case_temperature_k
            >= p.maximum_case_temperature_k
        )
        peak_exhausted = (
            self.semantics.torque_regime
            == "peak_one_shot_per_reset"
            and self._peak_time_used + self._dt
            > _fraction(p.peak_duration_s)
        )
        diagnostics = PlantV2Diagnostics(
            SOLVER_ID,
            NOISE_ALGORITHM,
            JITTER_ALGORITHM,
            command.sequence if command is not None else 0,
            (
                command.issued_step_index
                if command is not None
                else None
            ),
            (
                PlantV2Time.from_fraction(active.eligible_time)
                if active is not None
                else None
            ),
            (
                active.activation_step_index
                if active is not None
                else None
            ),
            (
                PlantV2Time.from_fraction(active.activation_time)
                if active is not None
                else None
            ),
            active.jitter_s if active is not None else None,
            activated,
            stale_commands,
            expired_commands,
            derate,
            voltage,
            motor_torque,
            transmission_torque,
            efficiency,
            output_torque_limit,
            float(self._peak_time_used),
            peak_exhausted,
            captured,
            delivered,
            stale_samples,
            current_saturated,
            voltage_saturated,
            motor_torque_saturated,
            output_torque_saturated,
            motor_speed_saturated,
            output_speed_saturated,
            position_limited,
            thermal_shutdown,
            finite,
        )
        self._state = state
        self._last_step = PlantV2Step(
            state,
            self._latest_sample,
            diagnostics,
        )
        return self._last_step

    def clear_commands(self) -> None:
        """Remove queued and active commands without creating a command."""

        self._pending_commands = []
        self._active_command = None
        self._command_watermark = self._next_command_sequence - 1

    @staticmethod
    def _scheduled_command_record(
        item: _ScheduledCommand,
    ) -> dict[str, Any]:
        return {
            "command": asdict(item.command),
            "jitter_s": item.jitter_s,
            "eligible_time": _fraction_record(item.eligible_time),
        }

    @staticmethod
    def _active_command_record(
        item: _ActiveCommand,
    ) -> dict[str, Any]:
        return {
            "command": asdict(item.command),
            "jitter_s": item.jitter_s,
            "eligible_time": _fraction_record(item.eligible_time),
            "activation_step_index": item.activation_step_index,
            "activation_time": _fraction_record(item.activation_time),
        }

    @staticmethod
    def _scheduled_sample_record(
        item: _ScheduledSample,
    ) -> dict[str, Any]:
        return {
            "sample": asdict(item.sample),
            "eligible_time": _fraction_record(item.eligible_time),
        }

    def snapshot(self) -> dict[str, Any]:
        payload = {
            "schema_version": "myactuator-plant-v2-snapshot/1",
            "configuration_sha256": (
                self.configuration.configuration_sha256
            ),
            "seed": self._seed,
            "state": asdict(self._state),
            "active_command": (
                self._active_command_record(self._active_command)
                if self._active_command is not None
                else None
            ),
            "pending_commands": [
                self._scheduled_command_record(item)
                for item in self._pending_commands
            ],
            "next_command_sequence": self._next_command_sequence,
            "command_watermark": self._command_watermark,
            "peak_time_used": _fraction_record(self._peak_time_used),
            "capture_sequence": self._capture_sequence,
            "next_capture_time": _fraction_record(
                self._next_capture_time
            ),
            "pending_samples": [
                self._scheduled_sample_record(item)
                for item in self._pending_samples
            ],
            "latest_sample": (
                asdict(self._latest_sample)
                if self._latest_sample is not None
                else None
            ),
            "last_diagnostics": asdict(self._last_step.diagnostics),
        }
        return {
            **payload,
            "snapshot_sha256": _digest(payload),
        }

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        expected = {
            "schema_version",
            "configuration_sha256",
            "seed",
            "state",
            "active_command",
            "pending_commands",
            "next_command_sequence",
            "command_watermark",
            "peak_time_used",
            "capture_sequence",
            "next_capture_time",
            "pending_samples",
            "latest_sample",
            "last_diagnostics",
            "snapshot_sha256",
        }
        _require(
            isinstance(snapshot, Mapping) and set(snapshot) == expected,
            "V2 snapshot field closure drift",
        )
        snapshot_payload = {
            key: value
            for key, value in snapshot.items()
            if key != "snapshot_sha256"
        }
        _require(
            isinstance(snapshot["snapshot_sha256"], str)
            and snapshot["snapshot_sha256"] == _digest(snapshot_payload),
            "V2 snapshot integrity mismatch",
        )
        _require(
            snapshot["schema_version"]
            == "myactuator-plant-v2-snapshot/1"
            and snapshot["configuration_sha256"]
            == self.configuration.configuration_sha256,
            "V2 snapshot identity/configuration mismatch",
        )
        seed = _nonnegative_integer(snapshot["seed"], "snapshot seed")
        _require(seed <= _U64_MAX, "snapshot seed exceeds u64")
        _require(
            isinstance(snapshot["state"], Mapping),
            "snapshot state is invalid",
        )
        state = PlantState(**snapshot["state"])
        self._validate_state(state)
        next_command_sequence = _positive_integer(
            snapshot["next_command_sequence"],
            "snapshot next command sequence",
        )
        command_watermark = _nonnegative_integer(
            snapshot["command_watermark"],
            "snapshot command watermark",
        )
        _require(
            command_watermark < next_command_sequence,
            "snapshot command watermark is not prior to next",
        )
        active_value = snapshot["active_command"]
        active: _ActiveCommand | None = None
        if active_value is not None:
            _require(
                isinstance(active_value, Mapping)
                and set(active_value)
                == {
                    "command",
                    "jitter_s",
                    "eligible_time",
                    "activation_step_index",
                    "activation_time",
                },
                "active command snapshot row is not closed",
            )
            _require(
                isinstance(active_value["command"], Mapping)
                and set(active_value["command"])
                == set(PlantV2Command.__dataclass_fields__),
                "active command record is not closed",
            )
            try:
                active_command = PlantV2Command(
                    **active_value["command"]
                )
            except (TypeError, ValueError) as exc:
                raise PlantV2Error(
                    "active command record is invalid"
                ) from exc
            self._validate_command_values(
                active_command,
                label="active command",
            )
            _require(
                active_command.sequence == command_watermark,
                "active command sequence/watermark drift",
            )
            activation_step = _nonnegative_integer(
                active_value["activation_step_index"],
                "active command activation step",
            )
            activation_time = _load_fraction(
                active_value["activation_time"],
                "active command activation time",
            )
            eligible_time = _load_fraction(
                active_value["eligible_time"],
                "active command eligible time",
            )
            _require(
                activation_time == activation_step * self._dt
                and eligible_time <= activation_time
                and activation_step <= state.step_index,
                "active command timing is inconsistent",
            )
            active = _ActiveCommand(
                command=active_command,
                jitter_s=_finite(
                    active_value["jitter_s"],
                    "active command jitter",
                ),
                eligible_time=eligible_time,
                activation_step_index=activation_step,
                activation_time=activation_time,
            )
            expected_delay, expected_jitter = self._delay_with_jitter(
                base_s=self.parameters.command_delay_s,
                kind="command",
                sequence=active_command.sequence,
                seed=seed,
            )
            _require(
                active_command.issued_step_index <= activation_step
                and math.isclose(
                    active.jitter_s,
                    expected_jitter,
                    rel_tol=0.0,
                    abs_tol=1.0e-15,
                )
                and active.eligible_time
                == (
                    active_command.issued_step_index * self._dt
                    + expected_delay
                ),
                "active command issue/jitter metadata is inconsistent",
            )
        _require(
            isinstance(snapshot["pending_commands"], list),
            "pending command snapshot is invalid",
        )
        pending_commands: list[_ScheduledCommand] = []
        for row in snapshot["pending_commands"]:
            _require(
                isinstance(row, Mapping)
                and set(row) == {
                    "command",
                    "jitter_s",
                    "eligible_time",
                },
                "pending command snapshot row is not closed",
            )
            _require(
                isinstance(row["command"], Mapping)
                and set(row["command"])
                == set(PlantV2Command.__dataclass_fields__),
                "pending command record is not closed",
            )
            try:
                command = PlantV2Command(**row["command"])
            except (TypeError, ValueError) as exc:
                raise PlantV2Error(
                    "pending command record is invalid"
                ) from exc
            self._validate_command_values(
                command,
                label="pending command",
            )
            _require(
                command.issued_step_index <= state.step_index,
                "pending command issue step is future",
            )
            pending_jitter = _finite(
                row["jitter_s"],
                "pending command jitter",
            )
            pending_eligible = _load_fraction(
                row["eligible_time"],
                "pending command eligible time",
            )
            expected_delay, expected_jitter = self._delay_with_jitter(
                base_s=self.parameters.command_delay_s,
                kind="command",
                sequence=command.sequence,
                seed=seed,
            )
            _require(
                math.isclose(
                    pending_jitter,
                    expected_jitter,
                    rel_tol=0.0,
                    abs_tol=1.0e-15,
                )
                and pending_eligible
                == command.issued_step_index * self._dt + expected_delay,
                "pending command timing metadata is inconsistent",
            )
            pending_commands.append(
                _ScheduledCommand(
                    command,
                    pending_jitter,
                    pending_eligible,
                )
            )
        pending_sequences = [
            item.command.sequence for item in pending_commands
        ]
        _require(
            len(pending_sequences) == len(set(pending_sequences)),
            "pending command sequence duplication",
        )
        _require(
            active is None
            or active.command.sequence not in set(pending_sequences),
            "active command is duplicated in pending commands",
        )
        _require(
            all(
                sequence < next_command_sequence
                for sequence in pending_sequences
            ),
            "pending command sequence is not prior to next",
        )
        peak_time_used = _load_fraction(
            snapshot["peak_time_used"],
            "snapshot peak time",
        )
        _require(
            peak_time_used >= 0
            and (
                self.semantics.torque_regime
                == "peak_one_shot_per_reset"
                or peak_time_used == 0
            )
            and peak_time_used <= _fraction(self.parameters.peak_duration_s),
            "snapshot peak time is invalid",
        )
        capture_sequence = _nonnegative_integer(
            snapshot["capture_sequence"],
            "snapshot capture sequence",
        )
        next_capture_time = _load_fraction(
            snapshot["next_capture_time"],
            "snapshot next capture time",
        )
        now = state.step_index * self._dt
        _require(
            next_capture_time > now,
            "snapshot next capture time is stale",
        )
        _require(
            next_capture_time % self._sample_period == 0,
            "snapshot next capture time is off schedule",
        )
        _require(
            isinstance(snapshot["pending_samples"], list),
            "pending sample snapshot is invalid",
        )
        pending_samples: list[_ScheduledSample] = []
        for row in snapshot["pending_samples"]:
            _require(
                isinstance(row, Mapping)
                and set(row) == {"sample", "eligible_time"},
                "pending sample snapshot row is not closed",
            )
            _require(
                isinstance(row["sample"], Mapping)
                and set(row["sample"])
                == set(PlantV2SensorSample.__dataclass_fields__),
                "pending sample record is not closed",
            )
            try:
                sample_value = dict(row["sample"])
                sample_value["capture_time"] = _load_plant_time(
                    sample_value["capture_time"],
                    "pending sample capture time",
                )
                sample_value[
                    "eligible_delivery_time"
                ] = _load_plant_time(
                    sample_value["eligible_delivery_time"],
                    "pending sample eligible delivery time",
                )
                sample_value["delivery_time"] = (
                    None
                    if sample_value["delivery_time"] is None
                    else _load_plant_time(
                        sample_value["delivery_time"],
                        "pending sample delivery time",
                    )
                )
                sample = PlantV2SensorSample(**sample_value)
            except (TypeError, ValueError) as exc:
                raise PlantV2Error(
                    "pending sample record is invalid"
                ) from exc
            _positive_integer(
                sample.sample_sequence,
                "pending sample sequence",
            )
            _require(
                sample.delivered_step_index is None
                and sample.delivery_time is None,
                "pending sample is already delivered",
            )
            self._validate_sample(
                sample,
                label="pending sample",
                now=now,
                seed=seed,
            )
            sample_eligible = _load_fraction(
                row["eligible_time"],
                "pending sample eligible time",
            )
            _require(
                sample_eligible
                == sample.eligible_delivery_time.as_fraction(),
                "pending sample eligible time drift",
            )
            pending_samples.append(
                _ScheduledSample(
                    sample,
                    sample_eligible,
                )
            )
        sample_sequences = [
            item.sample.sample_sequence for item in pending_samples
        ]
        _require(
            len(sample_sequences) == len(set(sample_sequences))
            and all(
                sequence <= capture_sequence
                for sequence in sample_sequences
            ),
            "pending sample sequence partition is invalid",
        )
        latest_value = snapshot["latest_sample"]
        latest: PlantV2SensorSample | None = None
        if latest_value is not None:
            _require(
                isinstance(latest_value, Mapping)
                and set(latest_value)
                == set(PlantV2SensorSample.__dataclass_fields__),
                "latest sample record is not closed",
            )
            try:
                latest_record = dict(latest_value)
                latest_record["capture_time"] = _load_plant_time(
                    latest_record["capture_time"],
                    "latest sample capture time",
                )
                latest_record[
                    "eligible_delivery_time"
                ] = _load_plant_time(
                    latest_record["eligible_delivery_time"],
                    "latest sample eligible delivery time",
                )
                latest_record["delivery_time"] = (
                    None
                    if latest_record["delivery_time"] is None
                    else _load_plant_time(
                        latest_record["delivery_time"],
                        "latest sample delivery time",
                    )
                )
                latest = PlantV2SensorSample(**latest_record)
            except (TypeError, ValueError) as exc:
                raise PlantV2Error(
                    "latest sample record is invalid"
                ) from exc
        if latest is not None:
            self._validate_sample(
                latest,
                label="latest sample",
                now=now,
                seed=seed,
            )
            _require(
                latest.delivered_step_index is not None
                and latest.delivery_time is not None
                and latest.sample_sequence <= capture_sequence,
                "latest delivered sample is invalid",
            )
        _require(
            isinstance(snapshot["last_diagnostics"], Mapping)
            and set(snapshot["last_diagnostics"])
            == set(PlantV2Diagnostics.__dataclass_fields__),
            "snapshot diagnostics record is not closed",
        )
        try:
            diagnostics_value = dict(snapshot["last_diagnostics"])
            diagnostics_value["active_command_eligible_time"] = (
                None
                if diagnostics_value[
                    "active_command_eligible_time"
                ]
                is None
                else _load_plant_time(
                    diagnostics_value[
                        "active_command_eligible_time"
                    ],
                    "diagnostics active command eligible time",
                )
            )
            diagnostics_value["active_command_activation_time"] = (
                None
                if diagnostics_value[
                    "active_command_activation_time"
                ]
                is None
                else _load_plant_time(
                    diagnostics_value[
                        "active_command_activation_time"
                    ],
                    "diagnostics active command activation time",
                )
            )
            diagnostics = PlantV2Diagnostics(**diagnostics_value)
        except (TypeError, ValueError) as exc:
            raise PlantV2Error(
                "snapshot diagnostics record is invalid"
            ) from exc
        _require(
            diagnostics.solver_id == SOLVER_ID
            and diagnostics.noise_algorithm == NOISE_ALGORITHM
            and diagnostics.jitter_algorithm == JITTER_ALGORITHM,
            "snapshot algorithm identity drift",
        )
        _nonnegative_integer(
            diagnostics.active_command_sequence,
            "diagnostics active command sequence",
        )
        for name in (
            "active_command_issued_step_index",
            "active_command_activation_step_index",
        ):
            value = getattr(diagnostics, name)
            if value is not None:
                _nonnegative_integer(value, f"diagnostics {name}")
        active_metadata = (
            diagnostics.active_command_issued_step_index,
            diagnostics.active_command_eligible_time,
            diagnostics.active_command_activation_step_index,
            diagnostics.active_command_activation_time,
            diagnostics.active_command_jitter_s,
        )
        _require(
            (
                all(value is None for value in active_metadata)
                if diagnostics.active_command_sequence == 0
                else all(value is not None for value in active_metadata)
            ),
            "diagnostics active command timing partition is invalid",
        )
        if diagnostics.active_command_sequence > 0:
            _require(
                isinstance(
                    diagnostics.active_command_eligible_time,
                    PlantV2Time,
                )
                and isinstance(
                    diagnostics.active_command_activation_time,
                    PlantV2Time,
                )
                and (
                    diagnostics.active_command_activation_time.as_fraction()
                    == diagnostics.active_command_activation_step_index
                    * self._dt
                )
                and (
                    diagnostics.active_command_eligible_time.as_fraction()
                    <= diagnostics.active_command_activation_time.as_fraction()
                ),
                "diagnostics active command times are invalid",
            )
        for name in (
            "command_activated_this_step",
            "peak_budget_exhausted",
            "current_saturated",
            "voltage_saturated",
            "motor_torque_saturated",
            "output_torque_saturated",
            "motor_speed_saturated",
            "output_speed_saturated",
            "position_limited",
            "thermal_shutdown",
            "finite",
        ):
            _require(
                isinstance(getattr(diagnostics, name), bool),
                f"diagnostics {name} must be bool",
            )
        for name in (
            "stale_command_count",
            "expired_command_count",
            "captured_sample_count",
            "delivered_sample_count",
            "stale_sample_count",
        ):
            _nonnegative_integer(
                getattr(diagnostics, name),
                f"diagnostics {name}",
            )
        for name in (
            "command_derate",
            "applied_voltage_v",
            "motor_torque_nm",
            "transmission_torque_nm",
            "active_efficiency_ratio",
            "active_output_torque_limit_nm",
            "peak_time_used_s",
        ):
            _finite(getattr(diagnostics, name), f"diagnostics {name}")
        _require(
            0.0 <= diagnostics.command_derate <= 1.0
            and diagnostics.active_efficiency_ratio
            in {
                self.parameters.forward_efficiency_ratio,
                self.parameters.reverse_efficiency_ratio,
                1.0,
            }
            and diagnostics.active_output_torque_limit_nm
            in {
                self.parameters.maximum_continuous_output_torque_nm,
                self.parameters.maximum_peak_output_torque_nm,
            }
            and math.isclose(
                diagnostics.peak_time_used_s,
                float(peak_time_used),
                rel_tol=0.0,
                abs_tol=1.0e-15,
            )
            and diagnostics.finite,
            "snapshot diagnostics numeric domain is invalid",
        )
        self._seed = seed
        self._state = state
        self._active_command = active
        self._pending_commands = sorted(
            pending_commands,
            key=lambda item: (
                item.eligible_time,
                item.command.sequence,
            ),
        )
        self._next_command_sequence = next_command_sequence
        self._command_watermark = command_watermark
        self._peak_time_used = peak_time_used
        self._capture_sequence = capture_sequence
        self._next_capture_time = next_capture_time
        self._pending_samples = sorted(
            pending_samples,
            key=lambda item: (
                item.eligible_time,
                item.sample.sample_sequence,
            ),
        )
        self._latest_sample = latest
        self._last_step = PlantV2Step(state, latest, diagnostics)


def deterministic_trace_sha256(
    configuration: PlantV2Configuration,
    events: Iterable[tuple[PlantV2Command | None, float]],
    *,
    seed: int,
) -> str:
    plant = DeterministicActuatorPlantV2(configuration, seed=seed)
    digest = hashlib.sha256()
    for command, load in events:
        if command is not None:
            plant.submit(command)
        result = plant.step(output_load_torque_nm=load)
        digest.update(
            _canonical_bytes(
                {
                    "state": asdict(result.state),
                    "sample": (
                        asdict(result.sample)
                        if result.sample is not None
                        else None
                    ),
                    "diagnostics": asdict(result.diagnostics),
                }
            )
        )
    return digest.hexdigest()


def clone_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-compatible deep copy for callers and tests."""

    return copy.deepcopy(dict(snapshot))


__all__ = [
    "JITTER_ALGORITHM",
    "MOTION_AUTHORITY",
    "NOISE_ALGORITHM",
    "PHYSICAL_IO",
    "PHYSICAL_VALIDATION",
    "PlantV2Command",
    "PlantV2Configuration",
    "PlantV2Diagnostics",
    "PlantV2Error",
    "PlantV2Parameters",
    "PlantV2Semantics",
    "PlantV2SensorSample",
    "PlantV2Step",
    "PlantV2Time",
    "SOLVER_ID",
    "SUPPORT_GRANTED",
    "DeterministicActuatorPlantV2",
    "clone_snapshot",
    "deterministic_trace_sha256",
]
