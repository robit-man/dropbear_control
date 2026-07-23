"""Deterministic synthetic electromechanical actuator plant.

This is an offline test backend, not a MYACTUATOR model. It uses a fixed-step
semi-implicit Euler solver and explicit electrical, elastic transmission,
friction, limit, thermal, sensor quantization, and latency state. No parameter
may be substituted for a catalog model and no result is physical validation.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from . import rmd_v44
from . import rmd_v44_emulator


BACKEND_KIND = "synthetic_test_plant"
IS_PHYSICAL_PLANT = False
SUPPORT_GRANTED = False
MODEL_FIRMWARE_APPLICABILITY_VERIFIED = False
SOLVER_ID = "semi-implicit-euler-fixed-step-v1"


class PlantError(ValueError):
    """A plant identity, parameter, command, or state is invalid."""


class PlantParameterProvider(Protocol):
    """Closed parameter provider accepted by the deterministic equation core."""

    parameters: "PlantParameters"


@dataclass(frozen=True)
class PlantBackendIdentity:
    backend_id: str
    backend_kind: str
    parameter_set_id: str
    applicability_tuple: tuple[str, str, str, str, str, str, str]
    physical_fidelity: bool
    support_granted: bool


@dataclass(frozen=True)
class PlantParameters:
    time_step_s: float
    phase_resistance_ohm: float
    phase_inductance_h: float
    torque_constant_nm_per_a: float
    back_emf_v_s_per_rad: float
    rotor_inertia_kg_m2: float
    output_inertia_kg_m2: float
    gear_ratio_motor_per_output: float
    gear_efficiency: float
    transmission_stiffness_nm_per_rad: float
    transmission_damping_nm_s_per_rad: float
    backlash_rad: float
    coulomb_friction_nm: float
    viscous_friction_nm_s_per_rad: float
    supply_voltage_v: float
    maximum_qaxis_current_a: float
    maximum_motor_torque_nm: float
    maximum_output_torque_nm: float
    maximum_output_speed_rad_s: float
    position_lower_rad: float
    position_upper_rad: float
    current_controller_kp_v_per_a: float
    winding_thermal_capacity_j_per_k: float
    case_thermal_capacity_j_per_k: float
    winding_to_case_resistance_k_per_w: float
    case_to_ambient_resistance_k_per_w: float
    ambient_temperature_k: float
    derate_start_temperature_k: float
    shutdown_temperature_k: float
    position_quantum_rad: float
    velocity_quantum_rad_s: float
    current_quantum_a: float
    temperature_quantum_k: float
    sensor_latency_steps: int

    def validate(self) -> None:
        values = asdict(self)
        if set(values) != set(self.__dataclass_fields__):
            raise PlantError("parameter field closure violated")
        for name, value in values.items():
            if name == "sensor_latency_steps":
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise PlantError("sensor_latency_steps must be a nonnegative integer")
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PlantError(f"{name} must be numeric")
            if not math.isfinite(float(value)):
                raise PlantError(f"{name} must be finite")
        strictly_positive = set(values) - {
            "backlash_rad",
            "coulomb_friction_nm",
            "viscous_friction_nm_s_per_rad",
            "position_quantum_rad",
            "velocity_quantum_rad_s",
            "current_quantum_a",
            "temperature_quantum_k",
            "position_lower_rad",
            "position_upper_rad",
            "sensor_latency_steps",
        }
        for name in strictly_positive:
            if float(values[name]) <= 0.0:
                raise PlantError(f"{name} must be positive")
        for name in (
            "backlash_rad",
            "coulomb_friction_nm",
            "viscous_friction_nm_s_per_rad",
            "position_quantum_rad",
            "velocity_quantum_rad_s",
            "current_quantum_a",
            "temperature_quantum_k",
        ):
            if float(values[name]) < 0.0:
                raise PlantError(f"{name} must be nonnegative")
        if not 0.0 < self.gear_efficiency <= 1.0:
            raise PlantError("gear_efficiency must be in (0, 1]")
        if self.position_lower_rad >= self.position_upper_rad:
            raise PlantError("position limits are reversed or empty")
        if not (
            self.ambient_temperature_k
            < self.derate_start_temperature_k
            < self.shutdown_temperature_k
        ):
            raise PlantError("thermal thresholds must increase from ambient")


@dataclass(frozen=True)
class SyntheticParameterSet:
    identity: PlantBackendIdentity
    parameters: PlantParameters

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SyntheticParameterSet":
        if set(value) != {"schema_version", "identity", "parameters"}:
            raise PlantError("synthetic parameter set has unknown or missing fields")
        if value["schema_version"] != "myactuator-synthetic-plant/1":
            raise PlantError("unsupported synthetic parameter schema")
        identity_value = value["identity"]
        expected_identity = {
            "backend_id",
            "backend_kind",
            "parameter_set_id",
            "applicability_tuple",
            "physical_fidelity",
            "support_granted",
        }
        if not isinstance(identity_value, Mapping) or set(identity_value) != expected_identity:
            raise PlantError("synthetic backend identity is not closed")
        applicability = identity_value["applicability_tuple"]
        if not isinstance(applicability, list) or len(applicability) != 7:
            raise PlantError("synthetic applicability tuple must contain seven fields")
        if not all(isinstance(item, str) and item for item in applicability):
            raise PlantError("synthetic applicability tuple fields must be exact text")
        identity = PlantBackendIdentity(
            backend_id=identity_value["backend_id"],
            backend_kind=identity_value["backend_kind"],
            parameter_set_id=identity_value["parameter_set_id"],
            applicability_tuple=tuple(applicability),
            physical_fidelity=identity_value["physical_fidelity"],
            support_granted=identity_value["support_granted"],
        )
        if (
            not identity.backend_id
            or not identity.parameter_set_id
            or identity.backend_kind != BACKEND_KIND
            or identity.physical_fidelity is not False
            or identity.support_granted is not False
            or identity.applicability_tuple[0] != "SYNTHETIC"
        ):
            raise PlantError("backend identity could be confused with a physical plant")
        parameter_value = value["parameters"]
        if not isinstance(parameter_value, Mapping) or set(parameter_value) != set(
            PlantParameters.__dataclass_fields__
        ):
            raise PlantError("synthetic plant parameter fields are not closed")
        parameters = PlantParameters(**parameter_value)
        parameters.validate()
        return cls(identity, parameters)

    @classmethod
    def load(cls, path: Path | str) -> "SyntheticParameterSet":
        return cls.from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True)
class PlantState:
    step_index: int
    monotonic_s: float
    qaxis_current_a: float
    rotor_position_rad: float
    rotor_velocity_rad_s: float
    output_position_rad: float
    output_velocity_rad_s: float
    winding_temperature_k: float
    case_temperature_k: float


@dataclass(frozen=True)
class PlantCommand:
    enabled: bool
    target_qaxis_current_a: float
    output_load_torque_nm: float = 0.0


@dataclass(frozen=True)
class PlantSensorSample:
    source_step_index: int
    sample_monotonic_s: float
    output_position_rad: float
    output_velocity_rad_s: float
    qaxis_current_a: float
    winding_temperature_k: float


@dataclass(frozen=True)
class PlantDiagnostics:
    solver_id: str
    command_derate: float
    applied_voltage_v: float
    motor_torque_nm: float
    transmission_torque_nm: float
    stored_energy_j: float
    current_saturated: bool
    voltage_saturated: bool
    motor_torque_saturated: bool
    output_torque_saturated: bool
    speed_saturated: bool
    position_limited: bool
    thermal_shutdown: bool
    finite: bool


@dataclass(frozen=True)
class PlantStep:
    state: PlantState
    sample: PlantSensorSample
    diagnostics: PlantDiagnostics


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
    integral = math.floor(scaled + 0.5) if scaled >= 0.0 else math.ceil(scaled - 0.5)
    return integral * quantum


class DeterministicActuatorPlant:
    """One synthetic motor, elastic reduction and output load."""

    def __init__(self, parameter_set: PlantParameterProvider):
        self.parameter_set = parameter_set
        self.parameters = parameter_set.parameters
        self.parameters.validate()
        self._state = PlantState(
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
        initial = self._sensor(self._state)
        self._sensor_queue: deque[PlantSensorSample] = deque(
            [initial] * (self.parameters.sensor_latency_steps + 1),
            maxlen=self.parameters.sensor_latency_steps + 1,
        )
        self._last_step = PlantStep(
            self._state,
            initial,
            PlantDiagnostics(
                SOLVER_ID,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                True,
            ),
        )

    @property
    def state(self) -> PlantState:
        return self._state

    @property
    def last_step(self) -> PlantStep:
        return self._last_step

    def reset(self, state: PlantState | None = None) -> PlantStep:
        if state is None:
            state = replace(
                self._state,
                step_index=0,
                monotonic_s=0.0,
                qaxis_current_a=0.0,
                rotor_position_rad=0.0,
                rotor_velocity_rad_s=0.0,
                output_position_rad=0.0,
                output_velocity_rad_s=0.0,
                winding_temperature_k=self.parameters.ambient_temperature_k,
                case_temperature_k=self.parameters.ambient_temperature_k,
            )
        self._validate_state(state)
        self._state = state
        initial = self._sensor(state)
        self._sensor_queue = deque(
            [initial] * (self.parameters.sensor_latency_steps + 1),
            maxlen=self.parameters.sensor_latency_steps + 1,
        )
        self._last_step = PlantStep(
            state,
            initial,
            replace(
                self._last_step.diagnostics,
                applied_voltage_v=0.0,
                motor_torque_nm=0.0,
                transmission_torque_nm=0.0,
                stored_energy_j=self._stored_energy(state, 0.0),
            ),
        )
        return self._last_step

    def _validate_state(self, state: PlantState) -> None:
        if isinstance(state.step_index, bool) or state.step_index < 0:
            raise PlantError("state step_index must be nonnegative")
        for name, value in asdict(state).items():
            if name == "step_index":
                continue
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise PlantError(f"state {name} must be finite")
        if not self.parameters.position_lower_rad <= state.output_position_rad <= self.parameters.position_upper_rad:
            raise PlantError("state output position is outside limits")
        if abs(state.output_velocity_rad_s) > self.parameters.maximum_output_speed_rad_s:
            raise PlantError("state output velocity is outside limits")

    def _sensor(self, state: PlantState) -> PlantSensorSample:
        p = self.parameters
        return PlantSensorSample(
            source_step_index=state.step_index,
            sample_monotonic_s=state.monotonic_s,
            output_position_rad=_quantize(state.output_position_rad, p.position_quantum_rad),
            output_velocity_rad_s=_quantize(
                state.output_velocity_rad_s, p.velocity_quantum_rad_s
            ),
            qaxis_current_a=_quantize(state.qaxis_current_a, p.current_quantum_a),
            winding_temperature_k=_quantize(
                state.winding_temperature_k, p.temperature_quantum_k
            ),
        )

    def _transmission_deflection(self, state: PlantState) -> float:
        relative = (
            state.rotor_position_rad / self.parameters.gear_ratio_motor_per_output
            - state.output_position_rad
        )
        half_backlash = self.parameters.backlash_rad / 2.0
        if relative > half_backlash:
            return relative - half_backlash
        if relative < -half_backlash:
            return relative + half_backlash
        return 0.0

    def _stored_energy(self, state: PlantState, deflection: float) -> float:
        p = self.parameters
        return (
            0.5 * p.phase_inductance_h * state.qaxis_current_a**2
            + 0.5 * p.rotor_inertia_kg_m2 * state.rotor_velocity_rad_s**2
            + 0.5 * p.output_inertia_kg_m2 * state.output_velocity_rad_s**2
            + 0.5 * p.transmission_stiffness_nm_per_rad * deflection**2
        )

    def step(self, command: PlantCommand) -> PlantStep:
        if not isinstance(command.enabled, bool):
            raise PlantError("command enabled must be bool")
        if not math.isfinite(command.target_qaxis_current_a) or not math.isfinite(
            command.output_load_torque_nm
        ):
            raise PlantError("plant command values must be finite")
        p = self.parameters
        s = self._state
        dt = p.time_step_s

        if s.winding_temperature_k >= p.shutdown_temperature_k:
            derate = 0.0
        elif s.winding_temperature_k <= p.derate_start_temperature_k:
            derate = 1.0
        else:
            derate = (
                p.shutdown_temperature_k - s.winding_temperature_k
            ) / (p.shutdown_temperature_k - p.derate_start_temperature_k)
        requested_current = command.target_qaxis_current_a if command.enabled else 0.0
        current_limit = p.maximum_qaxis_current_a * derate
        target_current = _clamp(requested_current, -current_limit, current_limit)
        current_saturated = target_current != requested_current

        back_emf = p.back_emf_v_s_per_rad * s.rotor_velocity_rad_s
        voltage_unbounded = (
            p.phase_resistance_ohm * target_current
            + back_emf
            + p.current_controller_kp_v_per_a
            * (target_current - s.qaxis_current_a)
        )
        voltage = _clamp(
            voltage_unbounded, -p.supply_voltage_v, p.supply_voltage_v
        )
        voltage_saturated = voltage != voltage_unbounded
        current_derivative = (
            voltage
            - p.phase_resistance_ohm * s.qaxis_current_a
            - back_emf
        ) / p.phase_inductance_h
        current_unbounded = s.qaxis_current_a + current_derivative * dt
        current = _clamp(
            current_unbounded,
            -p.maximum_qaxis_current_a,
            p.maximum_qaxis_current_a,
        )
        current_saturated = current_saturated or current != current_unbounded

        motor_torque_unbounded = p.torque_constant_nm_per_a * current
        motor_torque = _clamp(
            motor_torque_unbounded,
            -p.maximum_motor_torque_nm,
            p.maximum_motor_torque_nm,
        )
        motor_torque_saturated = motor_torque != motor_torque_unbounded

        deflection = self._transmission_deflection(s)
        relative_speed = (
            s.rotor_velocity_rad_s / p.gear_ratio_motor_per_output
            - s.output_velocity_rad_s
        )
        transmission_unbounded = 0.0
        if deflection != 0.0:
            transmission_unbounded = (
                p.transmission_stiffness_nm_per_rad * deflection
                + p.transmission_damping_nm_s_per_rad * relative_speed
            )
        transmission_torque = _clamp(
            transmission_unbounded,
            -p.maximum_output_torque_nm,
            p.maximum_output_torque_nm,
        )
        output_torque_saturated = transmission_torque != transmission_unbounded

        reflected_motor_load = transmission_torque / (
            p.gear_ratio_motor_per_output * p.gear_efficiency
        )
        rotor_acceleration = (
            motor_torque - reflected_motor_load
        ) / p.rotor_inertia_kg_m2
        rotor_velocity = s.rotor_velocity_rad_s + rotor_acceleration * dt
        rotor_position = s.rotor_position_rad + rotor_velocity * dt

        external_net = transmission_torque - command.output_load_torque_nm
        if abs(s.output_velocity_rad_s) > 1.0e-12:
            friction = (
                p.coulomb_friction_nm * _sign(s.output_velocity_rad_s)
                + p.viscous_friction_nm_s_per_rad * s.output_velocity_rad_s
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
        output_velocity_unbounded = s.output_velocity_rad_s + output_acceleration * dt
        output_velocity = _clamp(
            output_velocity_unbounded,
            -p.maximum_output_speed_rad_s,
            p.maximum_output_speed_rad_s,
        )
        speed_saturated = output_velocity != output_velocity_unbounded
        output_position_unbounded = s.output_position_rad + output_velocity * dt
        output_position = _clamp(
            output_position_unbounded, p.position_lower_rad, p.position_upper_rad
        )
        position_limited = output_position != output_position_unbounded
        if position_limited and (
            (output_position == p.position_upper_rad and output_velocity > 0.0)
            or (output_position == p.position_lower_rad and output_velocity < 0.0)
        ):
            output_velocity = 0.0

        copper_loss_w = p.phase_resistance_ohm * current**2
        winding_derivative = (
            copper_loss_w
            - (s.winding_temperature_k - s.case_temperature_k)
            / p.winding_to_case_resistance_k_per_w
        ) / p.winding_thermal_capacity_j_per_k
        case_derivative = (
            (s.winding_temperature_k - s.case_temperature_k)
            / p.winding_to_case_resistance_k_per_w
            - (s.case_temperature_k - p.ambient_temperature_k)
            / p.case_to_ambient_resistance_k_per_w
        ) / p.case_thermal_capacity_j_per_k
        winding_temperature = s.winding_temperature_k + winding_derivative * dt
        case_temperature = s.case_temperature_k + case_derivative * dt

        state = PlantState(
            step_index=s.step_index + 1,
            monotonic_s=(s.step_index + 1) * dt,
            qaxis_current_a=current,
            rotor_position_rad=rotor_position,
            rotor_velocity_rad_s=rotor_velocity,
            output_position_rad=output_position,
            output_velocity_rad_s=output_velocity,
            winding_temperature_k=winding_temperature,
            case_temperature_k=case_temperature,
        )
        finite = all(
            math.isfinite(float(value))
            for name, value in asdict(state).items()
            if name != "step_index"
        )
        if not finite:
            raise PlantError("plant state became non-finite")
        current_sample = self._sensor(state)
        self._sensor_queue.append(current_sample)
        delayed_sample = self._sensor_queue[0]
        diagnostics = PlantDiagnostics(
            solver_id=SOLVER_ID,
            command_derate=derate,
            applied_voltage_v=voltage,
            motor_torque_nm=motor_torque,
            transmission_torque_nm=transmission_torque,
            stored_energy_j=self._stored_energy(state, self._transmission_deflection(state)),
            current_saturated=current_saturated,
            voltage_saturated=voltage_saturated,
            motor_torque_saturated=motor_torque_saturated,
            output_torque_saturated=output_torque_saturated,
            speed_saturated=speed_saturated,
            position_limited=position_limited,
            thermal_shutdown=derate == 0.0,
            finite=finite,
        )
        self._state = state
        self._last_step = PlantStep(state, delayed_sample, diagnostics)
        return self._last_step


class SyntheticIqPlantBridge:
    """Explicit V4.4-IQ-to-synthetic-plant test bridge."""

    def __init__(self, motor_id: int, plant: DeterministicActuatorPlant):
        self.motor_id = rmd_v44.validate_motor_id(motor_id)
        self.plant = plant
        self.enabled = False
        self.target_qaxis_current_a = 0.0

    def apply_request(self, frame: rmd_v44.CanFrame) -> rmd_v44.DecodedRequest:
        request = rmd_v44.decode_request(frame, expected_motor_id=self.motor_id)
        if request.command is rmd_v44.Command.IQ_CONTROL:
            assert request.iq_raw is not None
            self.target_qaxis_current_a = request.iq_raw * 0.01
            self.enabled = True
        elif request.command in {rmd_v44.Command.STOP, rmd_v44.Command.SHUTDOWN}:
            self.target_qaxis_current_a = 0.0
            self.enabled = False
        elif request.command not in {
            rmd_v44.Command.READ_MULTI_TURN_ANGLE,
            rmd_v44.Command.READ_SINGLE_TURN_ANGLE,
            rmd_v44.Command.READ_STATUS_1,
            rmd_v44.Command.READ_STATUS_2,
            rmd_v44.Command.READ_STATUS_3,
            rmd_v44.Command.OPERATING_MODE,
        }:
            raise PlantError(
                f"synthetic bridge does not support {request.command.name}"
            )
        return request

    def advance(self, steps: int, *, output_load_torque_nm: float = 0.0) -> PlantStep:
        if isinstance(steps, bool) or not isinstance(steps, int) or steps <= 0:
            raise PlantError("advance steps must be a positive integer")
        result = self.plant.last_step
        for _ in range(steps):
            result = self.plant.step(
                PlantCommand(
                    self.enabled,
                    self.target_qaxis_current_a,
                    output_load_torque_nm,
                )
            )
        return result

    def node_state(self) -> rmd_v44_emulator.NodeState:
        sample = self.plant.last_step.sample

        def integer(value: float, scale: float, lower: int, upper: int) -> int:
            scaled = value / scale
            rounded = (
                math.floor(scaled + 0.5)
                if scaled >= 0.0
                else math.ceil(scaled - 0.5)
            )
            return int(_clamp(float(rounded), float(lower), float(upper)))

        degrees = math.degrees(sample.output_position_rad)
        single_degrees = (degrees + 180.0) % 360.0 - 180.0
        return rmd_v44_emulator.NodeState(
            motor_id=self.motor_id,
            disabled=not self.enabled,
            stopped=abs(sample.output_velocity_rad_s) < 1.0e-9,
            mode=rmd_v44.OperatingMode.CURRENT,
            multi_turn_angle_raw=integer(degrees, 0.01, -(1 << 31), (1 << 31) - 1),
            single_turn_angle_raw=integer(single_degrees, 0.01, -18000, 18000),
            iq_raw=integer(sample.qaxis_current_a, 0.01, -(1 << 15), (1 << 15) - 1),
            output_speed_raw=integer(
                math.degrees(sample.output_velocity_rad_s),
                1.0,
                -(1 << 15),
                (1 << 15) - 1,
            ),
            output_angle_raw=integer(degrees, 1.0, -(1 << 15), (1 << 15) - 1),
            motor_temperature_c=integer(
                sample.winding_temperature_k - 273.15, 1.0, -128, 127
            ),
            voltage_raw=integer(
                self.plant.parameters.supply_voltage_v, 0.1, 0, 0xFFFF
            ),
        )


def deterministic_trace_sha256(
    parameter_set: SyntheticParameterSet,
    commands: Iterable[PlantCommand],
) -> str:
    plant = DeterministicActuatorPlant(parameter_set)
    digest = hashlib.sha256()
    for command in commands:
        result = plant.step(command)
        payload = {
            "state": asdict(result.state),
            "sample": asdict(result.sample),
            "diagnostics": asdict(result.diagnostics),
        }
        digest.update(
            json.dumps(
                payload,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
        )
        digest.update(b"\n")
    return digest.hexdigest()
