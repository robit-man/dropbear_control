"""ROS-independent semantic core for a future ros2_control SystemInterface.

There is intentionally no ROS import, native CAN surface or implicit joint
mapping here.  The core consumes the graph-gated hardware API, preserving its
lease, generation, lifecycle, signal-validity and fault semantics.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from . import dropbear_hardware_api as hardware
from .simulation_runtime import SimulationRuntimeCatalog


SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{2,127}$")


class RosControlError(ValueError):
    """A descriptor, command batch or control-core operation is invalid."""


class RosControlAdmissionDenied(RosControlError):
    """Tracked graph/mapping evidence cannot construct a control descriptor."""


class ControlLifecycle(str, Enum):
    UNCONFIGURED = "unconfigured"
    INACTIVE = "inactive"
    ACTIVE = "active"
    FAULTED = "faulted"
    FINALIZED = "finalized"


class ReturnDisposition(str, Enum):
    SUCCESS = "success"
    NOT_READY = "not_ready"
    INVALID = "invalid"
    STALE = "stale"
    TIMEOUT = "timeout"
    FAULT = "fault"


class CommandInterface(str, Enum):
    POSITION = "position"
    VELOCITY = "velocity"
    EFFORT = "effort"


class StateInterface(str, Enum):
    POSITION = "position"
    VELOCITY = "velocity"
    EFFORT = "effort"
    QAXIS_CURRENT = "qaxis_current"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RosControlError(message)


def _sha(value: str, label: str) -> None:
    _require(isinstance(value, str) and bool(SHA256.fullmatch(value)), f"{label} must be sha256")


def _identifier(value: str, label: str) -> None:
    _require(
        isinstance(value, str) and bool(IDENTIFIER.fullmatch(value)),
        f"{label} must be an exact identifier",
    )


def _positive(value: float, label: str) -> None:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and value > 0.0,
        f"{label} must be finite and positive",
    )


@dataclass(frozen=True)
class JointInterfaceDescriptor:
    joint_name: str
    canonical_actuator_id: str
    command_interfaces: tuple[CommandInterface, ...]
    state_interfaces: tuple[StateInterface, ...]
    position_lower_rad: float
    position_upper_rad: float
    maximum_velocity_rad_s: float
    maximum_output_effort_nm: float
    maximum_current_a: float

    def __post_init__(self) -> None:
        _identifier(self.joint_name, "joint_name")
        _require(
            self.canonical_actuator_id in hardware.CANONICAL_ACTUATOR_IDS,
            "canonical actuator ID is not exact",
        )
        _require(
            bool(self.command_interfaces)
            and len(self.command_interfaces) == len(set(self.command_interfaces))
            and all(isinstance(item, CommandInterface) for item in self.command_interfaces),
            "command interfaces must be unique typed values",
        )
        _require(
            bool(self.state_interfaces)
            and len(self.state_interfaces) == len(set(self.state_interfaces))
            and all(isinstance(item, StateInterface) for item in self.state_interfaces),
            "state interfaces must be unique typed values",
        )
        for value, label in (
            (self.position_lower_rad, "position lower"),
            (self.position_upper_rad, "position upper"),
        ):
            _require(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value)),
                f"{label} must be finite",
            )
        _require(self.position_lower_rad < self.position_upper_rad, "position limits are reversed")
        _positive(self.maximum_velocity_rad_s, "maximum velocity")
        _positive(self.maximum_output_effort_nm, "maximum output effort")
        _positive(self.maximum_current_a, "maximum current")


@dataclass(frozen=True)
class SystemInterfaceDescriptor:
    hardware_name: str
    canonical_configuration_digest: str
    accepted_graph_decision_id: str
    accepted_graph_sha256: str
    source_registry_generation_sha256: str
    graph_registry_generation_sha256: str
    simulator_catalog_generation_sha256: str
    joints: tuple[JointInterfaceDescriptor, ...]

    def __post_init__(self) -> None:
        _identifier(self.hardware_name, "hardware_name")
        for value, label in (
            (self.canonical_configuration_digest, "configuration digest"),
            (self.accepted_graph_sha256, "graph digest"),
            (self.source_registry_generation_sha256, "source generation"),
            (self.graph_registry_generation_sha256, "graph generation"),
            (self.simulator_catalog_generation_sha256, "simulator catalog generation"),
        ):
            _sha(value, label)
        _require(
            isinstance(self.accepted_graph_decision_id, str)
            and bool(hardware.GRAPH_DECISION_ID.fullmatch(self.accepted_graph_decision_id)),
            "accepted graph decision is invalid",
        )
        _require(bool(self.joints), "system descriptor requires exact joints")
        names = [joint.joint_name for joint in self.joints]
        actuators = [joint.canonical_actuator_id for joint in self.joints]
        _require(len(names) == len(set(names)), "joint names are duplicated")
        _require(len(actuators) == len(set(actuators)), "actuator mappings are duplicated")

    @classmethod
    def load_tracked_denial(
        cls,
        catalog: SimulationRuntimeCatalog | None = None,
    ) -> "SystemInterfaceDescriptor":
        catalog = catalog or SimulationRuntimeCatalog.load()
        dropbear = catalog.dropbear_readiness()
        if not dropbear["whole_robot_graph_ready"] or not dropbear["ros_mapping_count"]:
            raise RosControlAdmissionDenied(
                "tracked Dropbear graph/ROS mapping is unavailable: "
                + ",".join(dropbear["blockers"])
            )
        raise RosControlAdmissionDenied(
            "positive tracked descriptor construction requires an accepted mapping artifact"
        )


@dataclass(frozen=True)
class OperationResult:
    disposition: ReturnDisposition
    detail: str

    @property
    def succeeded(self) -> bool:
        return self.disposition is ReturnDisposition.SUCCESS


@dataclass(frozen=True)
class JointCommandValue:
    joint_name: str
    interface: CommandInterface
    value: float

    def __post_init__(self) -> None:
        _identifier(self.joint_name, "command joint_name")
        _require(isinstance(self.interface, CommandInterface), "command interface is invalid")
        _require(
            isinstance(self.value, (int, float))
            and not isinstance(self.value, bool)
            and math.isfinite(float(self.value)),
            "command value must be finite",
        )


@dataclass(frozen=True)
class CommandBatch:
    simulator_catalog_generation_sha256: str
    source_registry_generation_sha256: str
    graph_registry_generation_sha256: str
    configuration_generation: int
    sequence: int
    issued_monotonic_ns: int
    deadline_monotonic_ns: int
    commands: tuple[JointCommandValue, ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.simulator_catalog_generation_sha256, "batch catalog generation"),
            (self.source_registry_generation_sha256, "batch source generation"),
            (self.graph_registry_generation_sha256, "batch graph generation"),
        ):
            _sha(value, label)
        for value, label in (
            (self.configuration_generation, "configuration generation"),
            (self.sequence, "batch sequence"),
            (self.deadline_monotonic_ns, "batch deadline"),
        ):
            _require(
                isinstance(value, int) and not isinstance(value, bool) and value > 0,
                f"{label} must be a positive integer",
            )
        _require(
            isinstance(self.issued_monotonic_ns, int)
            and not isinstance(self.issued_monotonic_ns, bool)
            and self.issued_monotonic_ns >= 0,
            "batch issue time must be a nonnegative integer",
        )
        _require(self.deadline_monotonic_ns > self.issued_monotonic_ns, "batch deadline must follow issue")
        _require(bool(self.commands), "command batch is empty")
        keys = [(item.joint_name, item.interface) for item in self.commands]
        _require(len(keys) == len(set(keys)), "command batch contains duplicate interfaces")


@dataclass(frozen=True)
class InterfaceValue:
    value: float | None
    validity: hardware.SignalValidity
    source: hardware.SignalSource
    source_age_ns: int
    provenance_refs: tuple[str, ...]


@dataclass(frozen=True)
class JointReadState:
    joint_name: str
    canonical_actuator_id: str
    sampled_monotonic_ns: int
    received_monotonic_ns: int
    fault_code: str
    interfaces: tuple[tuple[StateInterface, InterfaceValue], ...]


@dataclass(frozen=True)
class ReadResult:
    disposition: ReturnDisposition
    detail: str
    states: tuple[JointReadState, ...]


GenerationProvider = Callable[[], tuple[str, str, str]]


class Ros2ControlCore:
    """Lifecycle and read/write core consumed by a future thin ROS plugin."""

    def __init__(
        self,
        *,
        descriptor: SystemInterfaceDescriptor,
        session: hardware.DropbearHardwareSession,
        monotonic_ns: Callable[[], int],
        generation_provider: GenerationProvider,
    ) -> None:
        _require(callable(monotonic_ns), "monotonic clock must be callable")
        _require(callable(generation_provider), "generation provider must be callable")
        self._descriptor = descriptor
        self._session = session
        self._clock = monotonic_ns
        self._generation_provider = generation_provider
        self._state = ControlLifecycle.UNCONFIGURED
        self._configuration_generation = 0
        self._session_id: str | None = None
        self._lease: hardware.CommandLease | None = None
        self._handles: dict[str, hardware.JointHandle] = {}
        self._next_batch_sequence = 1

    @property
    def state(self) -> ControlLifecycle:
        return self._state

    @property
    def descriptor(self) -> SystemInterfaceDescriptor:
        return self._descriptor

    def _expected_generations(self) -> tuple[str, str, str]:
        return (
            self._descriptor.simulator_catalog_generation_sha256,
            self._descriptor.source_registry_generation_sha256,
            self._descriptor.graph_registry_generation_sha256,
        )

    def _check_generations(self) -> OperationResult | None:
        try:
            current = self._generation_provider()
        except Exception as error:
            self.error("generation-provider-unavailable")
            return OperationResult(ReturnDisposition.STALE, type(error).__name__)
        if current != self._expected_generations():
            self.error("authority-generation-changed")
            return OperationResult(ReturnDisposition.STALE, "catalog/source/graph generation changed")
        return None

    def configure(
        self,
        *,
        configuration_generation: int,
        session_id: str,
        session_owner: str,
    ) -> OperationResult:
        if self._state is not ControlLifecycle.UNCONFIGURED:
            return OperationResult(ReturnDisposition.INVALID, "configure requires unconfigured state")
        stale = self._check_generations()
        if stale is not None:
            return stale
        try:
            context = hardware.SessionContext(
                self._descriptor.canonical_configuration_digest,
                self._descriptor.accepted_graph_decision_id,
                self._descriptor.accepted_graph_sha256,
                self._descriptor.source_registry_generation_sha256,
                self._descriptor.graph_registry_generation_sha256,
                configuration_generation,
                session_id,
                session_owner,
            )
            self._session.configure(context)
        except hardware.AdmissionDenied as error:
            return OperationResult(ReturnDisposition.NOT_READY, str(error))
        except hardware.HardwareApiError as error:
            return OperationResult(ReturnDisposition.INVALID, str(error))
        self._configuration_generation = configuration_generation
        self._session_id = session_id
        self._state = ControlLifecycle.INACTIVE
        self._next_batch_sequence = 1
        return OperationResult(ReturnDisposition.SUCCESS, "configured")

    def activate(self, lease: hardware.CommandLease) -> OperationResult:
        if self._state is not ControlLifecycle.INACTIVE:
            return OperationResult(ReturnDisposition.INVALID, "activate requires inactive state")
        stale = self._check_generations()
        if stale is not None:
            return stale
        try:
            self._session.activate()
            self._handles = {
                joint.joint_name: self._session.open_handle(
                    joint.canonical_actuator_id, lease
                )
                for joint in self._descriptor.joints
            }
        except hardware.AdmissionDenied as error:
            self.error("activate-admission-denied")
            return OperationResult(ReturnDisposition.STALE, str(error))
        except hardware.HardwareApiError as error:
            self.error("activate-not-ready")
            return OperationResult(ReturnDisposition.NOT_READY, str(error))
        self._lease = lease
        self._state = ControlLifecycle.ACTIVE
        return OperationResult(ReturnDisposition.SUCCESS, "activated")

    def _joint(self, name: str) -> JointInterfaceDescriptor:
        for joint in self._descriptor.joints:
            if joint.joint_name == name:
                return joint
        raise RosControlError("command joint is not mapped")

    def _intent(self, item: JointCommandValue, batch: CommandBatch) -> hardware.JointCommandIntent:
        joint = self._joint(item.joint_name)
        _require(item.interface in joint.command_interfaces, "command interface is not admitted")
        assert self._session_id is not None and self._lease is not None
        common = dict(
            canonical_actuator_id=joint.canonical_actuator_id,
            canonical_configuration_digest=self._descriptor.canonical_configuration_digest,
            accepted_graph_decision_id=self._descriptor.accepted_graph_decision_id,
            session_id=self._session_id,
            lease_id=self._lease.lease_id,
            lease_sequence=self._lease.lease_sequence,
            issued_monotonic_ns=batch.issued_monotonic_ns,
            deadline_monotonic_ns=batch.deadline_monotonic_ns,
        )
        if item.interface is CommandInterface.POSITION:
            _require(
                joint.position_lower_rad <= item.value <= joint.position_upper_rad,
                "position command exceeds admitted limits",
            )
            return hardware.JointCommandIntent(
                **common,
                mode=hardware.CommandMode.JOINT_POSITION,
                target_position_rad=item.value,
                maximum_velocity_rad_s=joint.maximum_velocity_rad_s,
                maximum_current_a=joint.maximum_current_a,
            )
        if item.interface is CommandInterface.VELOCITY:
            _require(abs(item.value) <= joint.maximum_velocity_rad_s, "velocity command exceeds admitted limit")
            return hardware.JointCommandIntent(
                **common,
                mode=hardware.CommandMode.JOINT_VELOCITY,
                target_velocity_rad_s=item.value,
                maximum_current_a=joint.maximum_current_a,
            )
        _require(abs(item.value) <= joint.maximum_output_effort_nm, "effort command exceeds admitted limit")
        return hardware.JointCommandIntent(
            **common,
            mode=hardware.CommandMode.OUTPUT_TORQUE,
            target_output_torque_nm=item.value,
            maximum_velocity_rad_s=joint.maximum_velocity_rad_s,
            maximum_current_a=joint.maximum_current_a,
        )

    def write(self, batch: CommandBatch) -> OperationResult:
        if self._state is not ControlLifecycle.ACTIVE:
            return OperationResult(ReturnDisposition.NOT_READY, "write requires active state")
        stale = self._check_generations()
        if stale is not None:
            return stale
        expected = self._expected_generations()
        if (
            (
                batch.simulator_catalog_generation_sha256,
                batch.source_registry_generation_sha256,
                batch.graph_registry_generation_sha256,
            )
            != expected
            or batch.configuration_generation != self._configuration_generation
            or batch.sequence != self._next_batch_sequence
        ):
            return OperationResult(ReturnDisposition.STALE, "batch identity/generation/sequence is stale")
        now = self._clock()
        if not batch.issued_monotonic_ns <= now < batch.deadline_monotonic_ns:
            return OperationResult(ReturnDisposition.TIMEOUT, "batch is early or expired")
        try:
            intents = tuple(self._intent(item, batch) for item in batch.commands)
        except RosControlError as error:
            return OperationResult(ReturnDisposition.INVALID, str(error))
        try:
            for item, intent in zip(batch.commands, intents):
                self._handles[item.joint_name].submit(intent)
        except (hardware.AdmissionDenied, hardware.HardwareApiError) as error:
            self._state = ControlLifecycle.FAULTED
            return OperationResult(ReturnDisposition.FAULT, str(error))
        self._next_batch_sequence += 1
        return OperationResult(ReturnDisposition.SUCCESS, "write accepted")

    @staticmethod
    def _interface_value(signal: hardware.StateSignal) -> InterfaceValue:
        return InterfaceValue(
            signal.value if signal.present else None,
            signal.validity,
            signal.source,
            signal.source_age_ns,
            signal.provenance_refs,
        )

    def read(self) -> ReadResult:
        if self._state is not ControlLifecycle.ACTIVE:
            return ReadResult(ReturnDisposition.NOT_READY, "read requires active state", ())
        stale = self._check_generations()
        if stale is not None:
            return ReadResult(stale.disposition, stale.detail, ())
        states = []
        try:
            for joint in self._descriptor.joints:
                sample = self._handles[joint.joint_name].read_state()
                available = {
                    StateInterface.POSITION: sample.position_rad,
                    StateInterface.VELOCITY: sample.velocity_rad_s,
                    StateInterface.EFFORT: sample.output_effort_nm,
                    StateInterface.QAXIS_CURRENT: sample.qaxis_current_a,
                }
                states.append(
                    JointReadState(
                        joint.joint_name,
                        joint.canonical_actuator_id,
                        sample.sampled_monotonic_ns,
                        sample.received_monotonic_ns,
                        sample.fault_code,
                        tuple(
                            (interface, self._interface_value(available[interface]))
                            for interface in joint.state_interfaces
                        ),
                    )
                )
        except (hardware.AdmissionDenied, hardware.HardwareApiError) as error:
            self._state = ControlLifecycle.FAULTED
            return ReadResult(ReturnDisposition.FAULT, str(error), ())
        return ReadResult(ReturnDisposition.SUCCESS, "read complete", tuple(states))

    def deactivate(self) -> OperationResult:
        if self._state is not ControlLifecycle.ACTIVE:
            return OperationResult(ReturnDisposition.INVALID, "deactivate requires active state")
        try:
            self._session.deactivate()
        except hardware.HardwareApiError as error:
            self._state = ControlLifecycle.FAULTED
            return OperationResult(ReturnDisposition.FAULT, str(error))
        self._handles.clear()
        self._lease = None
        self._state = ControlLifecycle.INACTIVE
        return OperationResult(ReturnDisposition.SUCCESS, "deactivated")

    def error(self, reason: str) -> OperationResult:
        if self._state in {ControlLifecycle.INACTIVE, ControlLifecycle.ACTIVE}:
            try:
                self._session.fault(reason)
            except hardware.HardwareApiError:
                pass
        if self._state not in {ControlLifecycle.UNCONFIGURED, ControlLifecycle.FINALIZED}:
            self._state = ControlLifecycle.FAULTED
        self._handles.clear()
        return OperationResult(ReturnDisposition.FAULT, reason)

    def cleanup(self) -> OperationResult:
        if self._state not in {ControlLifecycle.INACTIVE, ControlLifecycle.FAULTED}:
            return OperationResult(ReturnDisposition.INVALID, "cleanup requires inactive or faulted state")
        try:
            self._session.cleanup()
        except hardware.HardwareApiError as error:
            self._state = ControlLifecycle.FAULTED
            return OperationResult(ReturnDisposition.FAULT, str(error))
        self._handles.clear()
        self._lease = None
        self._session_id = None
        self._configuration_generation = 0
        self._state = ControlLifecycle.UNCONFIGURED
        return OperationResult(ReturnDisposition.SUCCESS, "cleaned up")

    def shutdown(self) -> OperationResult:
        if self._state is not ControlLifecycle.UNCONFIGURED:
            return OperationResult(ReturnDisposition.INVALID, "shutdown requires unconfigured state")
        try:
            self._session.finalize()
        except hardware.HardwareApiError as error:
            return OperationResult(ReturnDisposition.INVALID, str(error))
        self._state = ControlLifecycle.FINALIZED
        return OperationResult(ReturnDisposition.SUCCESS, "finalized")


__all__ = [
    "CommandBatch",
    "CommandInterface",
    "ControlLifecycle",
    "GenerationProvider",
    "InterfaceValue",
    "JointCommandValue",
    "JointInterfaceDescriptor",
    "JointReadState",
    "OperationResult",
    "ReadResult",
    "ReturnDisposition",
    "Ros2ControlCore",
    "RosControlAdmissionDenied",
    "RosControlError",
    "StateInterface",
    "SystemInterfaceDescriptor",
]
