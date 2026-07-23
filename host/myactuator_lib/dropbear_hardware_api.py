"""Graph-gated Dropbear joint API with offline fakes and no physical default.

This module is a contract boundary. It does not wire the current ESP32 or ROS
runtime and it exposes no native motor bytes, node IDs, raw-effort field, or
implicit backend selection.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from .dropbear_graph import DropbearGraphProjectionSet
from .dropbear_graph_lifecycle_v2 import (
    DropbearGraphLifecycleProjectionSetV2,
)
from .dropbear_readiness import DropbearReadinessRegistry


SHA256 = re.compile(r"^[0-9a-f]{64}$")
GRAPH_DECISION_ID = re.compile(
    r"^(?:graphdecision|graphv2decision)-[0-9a-f]{20}$"
)
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{2,127}$")
CANONICAL_ACTUATOR_IDS = tuple(
    f"actuator-{side}-{joint}"
    for side in ("left", "right")
    for joint in (
        "hip-yaw",
        "hip-roll",
        "hip-pitch",
        "knee",
        "inner-calf",
        "outer-calf",
    )
)


class HardwareApiError(ValueError):
    """A hardware-API identity, lifecycle, intent, or state is invalid."""


class AdmissionDenied(HardwareApiError):
    """Graph/readiness evidence does not permit an API session or handle."""


class PhysicalAdapterUnavailable(HardwareApiError):
    """No concrete physical adapter is present."""


class LifecycleState(str, Enum):
    UNCONFIGURED = "unconfigured"
    INACTIVE = "inactive"
    ACTIVE = "active"
    FAULTED = "faulted"
    FINALIZED = "finalized"


class BackendKind(str, Enum):
    REPLAY = "replay"
    PROTOCOL_EMULATOR = "protocol_emulator"
    SYNTHETIC_PLANT = "synthetic_plant"
    RIGID_BODY_CANDIDATE = "rigid_body_candidate"
    PHYSICAL_ADAPTER = "physical_adapter"


class CommandMode(str, Enum):
    DISABLE = "disable"
    JOINT_POSITION = "joint_position"
    JOINT_VELOCITY = "joint_velocity"
    OUTPUT_TORQUE = "output_torque"


class SignalSource(str, Enum):
    NATIVE_DRIVE = "native_drive"
    EXTERNAL_JOINT_SENSOR = "external_joint_sensor"
    REVIEWED_FUSION = "reviewed_fusion"
    SYNTHETIC_PLANT = "synthetic_plant"
    REPLAY = "replay"
    UNAVAILABLE = "unavailable"


class SignalValidity(str, Enum):
    VALID = "valid"
    STALE = "stale"
    MISSING = "missing"
    FAULTED = "faulted"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HardwareApiError(message)


def _exact_id(value: str, label: str) -> None:
    _require(isinstance(value, str) and bool(IDENTIFIER.fullmatch(value)), f"{label} is invalid")


def _sha256(value: str, label: str) -> None:
    _require(isinstance(value, str) and bool(SHA256.fullmatch(value)), f"{label} is invalid")


def _graph_id(value: str, label: str) -> None:
    _require(
        isinstance(value, str) and bool(GRAPH_DECISION_ID.fullmatch(value)),
        f"{label} is invalid",
    )


def _u64(value: int, label: str, *, positive: bool = False) -> None:
    valid = (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= 0xFFFFFFFFFFFFFFFF
    )
    if positive:
        valid = valid and value > 0
    _require(valid, f"{label} must be {'positive ' if positive else ''}u64")


def _finite(value: float | None, label: str) -> None:
    _require(
        value is not None
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{label} must be finite",
    )


@dataclass(frozen=True)
class BackendIdentity:
    backend_id: str
    backend_kind: BackendKind
    concrete_adapter: bool
    command_capable: bool
    physical_io: bool

    def __post_init__(self) -> None:
        _exact_id(self.backend_id, "backend_id")
        _require(isinstance(self.backend_kind, BackendKind), "backend kind is invalid")
        for value, label in (
            (self.concrete_adapter, "concrete_adapter"),
            (self.command_capable, "command_capable"),
            (self.physical_io, "physical_io"),
        ):
            _require(isinstance(value, bool), f"{label} must be bool")
        physical = self.backend_kind is BackendKind.PHYSICAL_ADAPTER
        _require(
            self.physical_io is physical,
            "physical_io must agree exactly with physical backend kind",
        )
        if self.backend_kind is BackendKind.REPLAY:
            _require(not self.command_capable, "replay backend cannot be command capable")
        if self.concrete_adapter:
            _require(
                physical,
                "concrete_adapter is reserved for physical adapters",
            )


@dataclass(frozen=True)
class AdmissionSnapshot:
    canonical_configuration_digest: str
    candidate_graph_decision_id: str
    accepted_graph_decision_id: str | None
    accepted_graph_sha256: str | None
    source_registry_generation_sha256: str
    graph_registry_generation_sha256: str
    graph_admitted: bool
    ready_actuator_ids: frozenset[str]
    offline_test_only: bool
    blockers: tuple[str, ...]
    physical_motion_authority: bool = False

    def __post_init__(self) -> None:
        _sha256(
            self.canonical_configuration_digest,
            "canonical_configuration_digest",
        )
        _sha256(
            self.source_registry_generation_sha256,
            "source registry generation",
        )
        _sha256(
            self.graph_registry_generation_sha256,
            "graph registry generation",
        )
        _graph_id(self.candidate_graph_decision_id, "candidate graph decision")
        _require(isinstance(self.graph_admitted, bool), "graph_admitted must be bool")
        _require(
            isinstance(self.offline_test_only, bool),
            "offline_test_only must be bool",
        )
        _require(
            isinstance(self.physical_motion_authority, bool),
            "physical_motion_authority must be bool",
        )
        unknown = set(self.ready_actuator_ids) - set(CANONICAL_ACTUATOR_IDS)
        _require(not unknown, f"unknown ready actuator IDs: {sorted(unknown)}")
        _require(
            len(self.blockers) == len(set(self.blockers))
            and all(isinstance(item, str) and item for item in self.blockers),
            "admission blockers must be unique nonempty strings",
        )
        if self.graph_admitted:
            _require(
                self.accepted_graph_decision_id is not None
                and self.accepted_graph_sha256 is not None,
                "admitted graph lacks exact decision identity",
            )
            _graph_id(self.accepted_graph_decision_id, "accepted graph decision")
            _sha256(self.accepted_graph_sha256, "accepted graph digest")
        else:
            _require(
                self.accepted_graph_decision_id is None
                and self.accepted_graph_sha256 is None
                and not self.ready_actuator_ids,
                "denied graph carries accepted identity/readiness",
            )
        if self.offline_test_only:
            _require(
                not self.physical_motion_authority,
                "offline fixture cannot grant physical motion",
            )

    @classmethod
    def load_tracked(cls) -> "AdmissionSnapshot":
        graph = DropbearGraphProjectionSet.load().view("host")
        lifecycle = DropbearGraphLifecycleProjectionSetV2.load()
        _require(
            graph.canonical_configuration_digest
            == lifecycle.canonical_configuration_digest,
            "V1/V2 graph configuration digest disagreement",
        )
        readiness = DropbearReadinessRegistry.load()
        blockers = list(lifecycle.view("host").blockers)
        for blocker in graph.blockers:
            if blocker not in blockers:
                blockers.append(blocker)
        for actuator_id in CANONICAL_ACTUATOR_IDS:
            for blocker in readiness.decision(actuator_id).blockers:
                if blocker not in blockers:
                    blockers.append(blocker)
        return cls(
            canonical_configuration_digest=graph.canonical_configuration_digest,
            candidate_graph_decision_id=graph.candidate_graph_decision_id,
            accepted_graph_decision_id=None,
            accepted_graph_sha256=None,
            source_registry_generation_sha256=(
                lifecycle.source_registry_generation_sha256
            ),
            graph_registry_generation_sha256=(
                lifecycle.graph_registry_generation_sha256
            ),
            graph_admitted=False,
            ready_actuator_ids=frozenset(),
            offline_test_only=False,
            blockers=tuple(blockers),
            physical_motion_authority=False,
        )

    @classmethod
    def synthetic_fixture(
        cls,
        *,
        canonical_configuration_digest: str,
        accepted_graph_decision_id: str,
        accepted_graph_sha256: str,
        source_registry_generation_sha256: str = "d4" * 32,
        graph_registry_generation_sha256: str = "e5" * 32,
        ready_actuator_ids: frozenset[str] = frozenset(CANONICAL_ACTUATOR_IDS),
    ) -> "AdmissionSnapshot":
        return cls(
            canonical_configuration_digest=canonical_configuration_digest,
            candidate_graph_decision_id=accepted_graph_decision_id,
            accepted_graph_decision_id=accepted_graph_decision_id,
            accepted_graph_sha256=accepted_graph_sha256,
            source_registry_generation_sha256=(
                source_registry_generation_sha256
            ),
            graph_registry_generation_sha256=(
                graph_registry_generation_sha256
            ),
            graph_admitted=True,
            ready_actuator_ids=ready_actuator_ids,
            offline_test_only=True,
            blockers=(),
            physical_motion_authority=False,
        )


@dataclass(frozen=True)
class SessionContext:
    canonical_configuration_digest: str
    accepted_graph_decision_id: str
    accepted_graph_sha256: str
    source_registry_generation_sha256: str
    graph_registry_generation_sha256: str
    configuration_generation: int
    session_id: str
    session_owner: str

    def __post_init__(self) -> None:
        _sha256(self.canonical_configuration_digest, "session configuration digest")
        _graph_id(self.accepted_graph_decision_id, "session graph decision")
        _sha256(self.accepted_graph_sha256, "session graph digest")
        _sha256(
            self.source_registry_generation_sha256,
            "session source registry generation",
        )
        _sha256(
            self.graph_registry_generation_sha256,
            "session graph registry generation",
        )
        _u64(self.configuration_generation, "configuration_generation", positive=True)
        _exact_id(self.session_id, "session_id")
        _exact_id(self.session_owner, "session_owner")


@dataclass(frozen=True)
class CommandLease:
    lease_id: str
    lease_owner: str
    lease_sequence: int
    issued_monotonic_ns: int
    expires_monotonic_ns: int

    def __post_init__(self) -> None:
        _exact_id(self.lease_id, "lease_id")
        _exact_id(self.lease_owner, "lease_owner")
        _u64(self.lease_sequence, "lease_sequence", positive=True)
        _u64(self.issued_monotonic_ns, "lease issue time")
        _u64(self.expires_monotonic_ns, "lease expiry time", positive=True)
        _require(
            self.expires_monotonic_ns > self.issued_monotonic_ns,
            "lease expiry must follow issue time",
        )


@dataclass(frozen=True)
class JointCommandIntent:
    canonical_actuator_id: str
    canonical_configuration_digest: str
    accepted_graph_decision_id: str
    session_id: str
    lease_id: str
    lease_sequence: int
    issued_monotonic_ns: int
    deadline_monotonic_ns: int
    mode: CommandMode
    target_position_rad: float | None = None
    target_velocity_rad_s: float | None = None
    target_output_torque_nm: float | None = None
    maximum_velocity_rad_s: float | None = None
    maximum_current_a: float | None = None

    def __post_init__(self) -> None:
        _require(
            self.canonical_actuator_id in CANONICAL_ACTUATOR_IDS,
            "command actuator ID is not exact",
        )
        _sha256(self.canonical_configuration_digest, "command configuration digest")
        _graph_id(self.accepted_graph_decision_id, "command graph decision")
        _exact_id(self.session_id, "command session_id")
        _exact_id(self.lease_id, "command lease_id")
        _u64(self.lease_sequence, "command lease_sequence", positive=True)
        _u64(self.issued_monotonic_ns, "command issue time")
        _u64(self.deadline_monotonic_ns, "command deadline", positive=True)
        _require(
            self.deadline_monotonic_ns > self.issued_monotonic_ns,
            "command deadline must follow issue time",
        )
        _require(isinstance(self.mode, CommandMode), "command mode is invalid")
        target_fields = {
            CommandMode.DISABLE: (),
            CommandMode.JOINT_POSITION: ("target_position_rad",),
            CommandMode.JOINT_VELOCITY: ("target_velocity_rad_s",),
            CommandMode.OUTPUT_TORQUE: ("target_output_torque_nm",),
        }
        required = set(target_fields[self.mode])
        targets = {
            "target_position_rad": self.target_position_rad,
            "target_velocity_rad_s": self.target_velocity_rad_s,
            "target_output_torque_nm": self.target_output_torque_nm,
        }
        for name, value in targets.items():
            if name in required:
                _finite(value, name)
            else:
                _require(value is None, f"{self.mode.value} carries unrelated {name}")
        if self.mode is CommandMode.DISABLE:
            _require(
                self.maximum_velocity_rad_s is None
                and self.maximum_current_a is None,
                "disable intent carries motion bounds",
            )
        else:
            _finite(self.maximum_current_a, "maximum_current_a")
            _require(self.maximum_current_a > 0.0, "maximum_current_a must be positive")
            if self.mode in {
                CommandMode.JOINT_POSITION,
                CommandMode.OUTPUT_TORQUE,
            }:
                _finite(self.maximum_velocity_rad_s, "maximum_velocity_rad_s")
                _require(
                    self.maximum_velocity_rad_s > 0.0,
                    "maximum_velocity_rad_s must be positive",
                )
            else:
                _require(
                    self.maximum_velocity_rad_s is None,
                    "joint_velocity carries unrelated maximum_velocity_rad_s",
                )


@dataclass(frozen=True)
class StateSignal:
    present: bool
    value: float | None
    source: SignalSource
    source_age_ns: int
    validity: SignalValidity
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require(isinstance(self.present, bool), "signal present must be bool")
        _require(isinstance(self.source, SignalSource), "signal source is invalid")
        _require(isinstance(self.validity, SignalValidity), "signal validity is invalid")
        _u64(self.source_age_ns, "signal source age")
        _require(
            len(self.provenance_refs) == len(set(self.provenance_refs))
            and all(isinstance(item, str) and item for item in self.provenance_refs),
            "signal provenance must be unique nonempty strings",
        )
        if self.present:
            _finite(self.value, "signal value")
            _require(
                self.source is not SignalSource.UNAVAILABLE
                and self.validity in {SignalValidity.VALID, SignalValidity.STALE}
                and bool(self.provenance_refs),
                "present signal lacks source/validity/provenance",
            )
        else:
            _require(
                self.value is None
                and self.source is SignalSource.UNAVAILABLE
                and self.validity in {SignalValidity.MISSING, SignalValidity.FAULTED},
                "absent signal carries value/source/valid status",
            )


@dataclass(frozen=True)
class JointStateSample:
    canonical_actuator_id: str
    canonical_configuration_digest: str
    accepted_graph_decision_id: str
    session_id: str
    sampled_monotonic_ns: int
    received_monotonic_ns: int
    position_rad: StateSignal
    velocity_rad_s: StateSignal
    qaxis_current_a: StateSignal
    output_effort_nm: StateSignal
    fault_code: str
    backend_id: str
    physical_motion_authority: bool = False

    def __post_init__(self) -> None:
        _require(
            self.canonical_actuator_id in CANONICAL_ACTUATOR_IDS,
            "state actuator ID is not exact",
        )
        _sha256(self.canonical_configuration_digest, "state configuration digest")
        _graph_id(self.accepted_graph_decision_id, "state graph decision")
        _exact_id(self.session_id, "state session_id")
        _u64(self.sampled_monotonic_ns, "state sample time")
        _u64(self.received_monotonic_ns, "state receive time")
        _require(
            self.received_monotonic_ns >= self.sampled_monotonic_ns,
            "state receive time precedes sample",
        )
        _require(isinstance(self.fault_code, str) and self.fault_code, "fault code missing")
        _exact_id(self.backend_id, "state backend_id")
        _require(
            self.physical_motion_authority is False,
            "state sample cannot grant physical motion authority",
        )


class HardwareBackend(Protocol):
    @property
    def identity(self) -> BackendIdentity: ...

    def configure(self, context: SessionContext) -> None: ...

    def activate(self) -> None: ...

    def submit(self, intent: JointCommandIntent) -> None: ...

    def read_state(self, actuator_id: str) -> JointStateSample: ...

    def cancel_pending(self) -> None: ...

    def deactivate(self) -> None: ...

    def cleanup(self) -> None: ...


class FakeHardwareBackend:
    """Explicit offline fake used to prove lifecycle and identity behavior."""

    def __init__(
        self,
        *,
        backend_id: str = "synthetic-hardware-api-fixture",
        backend_kind: BackendKind = BackendKind.SYNTHETIC_PLANT,
        command_capable: bool = True,
    ) -> None:
        self._identity = BackendIdentity(
            backend_id=backend_id,
            backend_kind=backend_kind,
            concrete_adapter=False,
            command_capable=command_capable,
            physical_io=False,
        )
        self.context: SessionContext | None = None
        self.active = False
        self.commands: list[JointCommandIntent] = []
        self.states: dict[str, JointStateSample] = {}
        self.cancellation_count = 0
        self.fail_operation: str | None = None

    @property
    def identity(self) -> BackendIdentity:
        return self._identity

    def _maybe_fail(self, operation: str) -> None:
        if self.fail_operation == operation:
            raise HardwareApiError(f"injected fake {operation} failure")

    def configure(self, context: SessionContext) -> None:
        self._maybe_fail("configure")
        self.context = context

    def activate(self) -> None:
        self._maybe_fail("activate")
        _require(self.context is not None, "fake backend is not configured")
        self.active = True

    def submit(self, intent: JointCommandIntent) -> None:
        self._maybe_fail("submit")
        _require(self.active, "fake backend is inactive")
        self.commands.append(intent)

    def read_state(self, actuator_id: str) -> JointStateSample:
        self._maybe_fail("read_state")
        _require(self.active, "fake backend is inactive")
        try:
            return self.states[actuator_id]
        except KeyError as error:
            raise HardwareApiError("fake state is unavailable") from error

    def cancel_pending(self) -> None:
        self.cancellation_count += 1

    def deactivate(self) -> None:
        self._maybe_fail("deactivate")
        self.active = False

    def cleanup(self) -> None:
        self._maybe_fail("cleanup")
        self.active = False
        self.context = None


class FailOnlyPhysicalBackend:
    """Named physical placeholder: every operation fails and no I/O exists."""

    def __init__(self) -> None:
        self._identity = BackendIdentity(
            backend_id="physical-adapter-unavailable",
            backend_kind=BackendKind.PHYSICAL_ADAPTER,
            concrete_adapter=False,
            command_capable=False,
            physical_io=True,
        )

    @property
    def identity(self) -> BackendIdentity:
        return self._identity

    @staticmethod
    def _deny() -> None:
        raise PhysicalAdapterUnavailable("no concrete physical adapter is installed")

    def configure(self, context: SessionContext) -> None:
        del context
        self._deny()

    def activate(self) -> None:
        self._deny()

    def submit(self, intent: JointCommandIntent) -> None:
        del intent
        self._deny()

    def read_state(self, actuator_id: str) -> JointStateSample:
        del actuator_id
        self._deny()

    def cancel_pending(self) -> None:
        self._deny()

    def deactivate(self) -> None:
        self._deny()

    def cleanup(self) -> None:
        self._deny()


@dataclass(frozen=True)
class JointHandle:
    _session: "DropbearHardwareSession"
    canonical_actuator_id: str
    lease: CommandLease
    configuration_generation: int
    source_registry_generation_sha256: str
    graph_registry_generation_sha256: str

    def submit(self, intent: JointCommandIntent) -> None:
        self._session._submit(self, intent)

    def read_state(self) -> JointStateSample:
        return self._session._read_state(self)


class DropbearHardwareSession:
    def __init__(
        self,
        *,
        backend: HardwareBackend,
        admission: AdmissionSnapshot,
        monotonic_ns: Callable[[], int],
        authority_generation: Callable[[], tuple[str, str]] | None = None,
    ) -> None:
        _require(callable(monotonic_ns), "monotonic clock must be callable")
        self._backend = backend
        self._admission = admission
        self._clock = monotonic_ns
        self._authority_generation = authority_generation or (
            lambda: (
                admission.source_registry_generation_sha256,
                admission.graph_registry_generation_sha256,
            )
        )
        _require(
            callable(self._authority_generation),
            "authority generation provider must be callable",
        )
        self._state = LifecycleState.UNCONFIGURED
        self._context: SessionContext | None = None
        self._seen_session_ids: set[str] = set()
        self._fault_reason: str | None = None

    @property
    def state(self) -> LifecycleState:
        return self._state

    @property
    def backend_identity(self) -> BackendIdentity:
        return self._backend.identity

    @property
    def fault_reason(self) -> str | None:
        return self._fault_reason

    def _admit_backend(self) -> None:
        identity = self._backend.identity
        if identity.backend_kind is BackendKind.PHYSICAL_ADAPTER:
            if not identity.concrete_adapter:
                raise PhysicalAdapterUnavailable(
                    "physical backend is a fail-only placeholder"
                )
            if self._admission.offline_test_only:
                raise AdmissionDenied(
                    "offline test admission cannot configure physical I/O"
                )
            if not self._admission.physical_motion_authority:
                raise AdmissionDenied("physical motion authority is absent")
        if not self._admission.graph_admitted:
            raise AdmissionDenied(
                "canonical graph is not admitted: "
                + ",".join(self._admission.blockers)
            )

    def _check_authority_generation(self, *, cancel_on_change: bool) -> None:
        try:
            current = self._authority_generation()
            _require(
                isinstance(current, tuple) and len(current) == 2,
                "authority generation provider result is invalid",
            )
            _sha256(current[0], "current source registry generation")
            _sha256(current[1], "current graph registry generation")
        except Exception as error:
            if cancel_on_change and self._state is LifecycleState.ACTIVE:
                self.fault("authority_generation_unavailable")
            raise AdmissionDenied(
                f"authority generation unavailable: {type(error).__name__}"
            ) from error
        expected = (
            self._admission.source_registry_generation_sha256,
            self._admission.graph_registry_generation_sha256,
        )
        if current != expected:
            if cancel_on_change and self._state is LifecycleState.ACTIVE:
                self.fault("authority_generation_changed")
            raise AdmissionDenied(
                "source/graph authority generation changed or was revoked"
            )

    def configure(self, context: SessionContext) -> None:
        _require(
            self._state is LifecycleState.UNCONFIGURED,
            "configure requires unconfigured lifecycle state",
        )
        self._check_authority_generation(cancel_on_change=False)
        self._admit_backend()
        _require(
            context.canonical_configuration_digest
            == self._admission.canonical_configuration_digest
            and context.accepted_graph_decision_id
            == self._admission.accepted_graph_decision_id
            and context.accepted_graph_sha256
            == self._admission.accepted_graph_sha256
            and context.source_registry_generation_sha256
            == self._admission.source_registry_generation_sha256
            and context.graph_registry_generation_sha256
            == self._admission.graph_registry_generation_sha256,
            "session context differs from admitted graph/configuration",
        )
        _require(
            context.session_id not in self._seen_session_ids,
            "session_id reuse is prohibited",
        )
        try:
            self._backend.configure(context)
        except Exception as error:
            self._state = LifecycleState.FAULTED
            self._fault_reason = f"configure_failed:{type(error).__name__}"
            raise
        self._context = context
        self._seen_session_ids.add(context.session_id)
        self._state = LifecycleState.INACTIVE
        self._fault_reason = None

    def activate(self) -> None:
        _require(
            self._state is LifecycleState.INACTIVE,
            "activate requires inactive lifecycle state",
        )
        try:
            self._backend.activate()
        except Exception as error:
            self._state = LifecycleState.FAULTED
            self._fault_reason = f"activate_failed:{type(error).__name__}"
            raise
        self._state = LifecycleState.ACTIVE

    def open_handle(
        self, actuator_id: str, lease: CommandLease
    ) -> JointHandle:
        _require(
            self._state is LifecycleState.ACTIVE,
            "joint handle requires active lifecycle state",
        )
        _require(
            actuator_id in CANONICAL_ACTUATOR_IDS,
            "joint handle actuator ID is not exact",
        )
        if actuator_id not in self._admission.ready_actuator_ids:
            raise AdmissionDenied(f"{actuator_id} is not admitted/ready")
        now = self._clock()
        _u64(now, "current monotonic time")
        _require(
            lease.issued_monotonic_ns <= now < lease.expires_monotonic_ns,
            "lease is not currently valid",
        )
        assert self._context is not None
        return JointHandle(
            self,
            actuator_id,
            lease,
            self._context.configuration_generation,
            self._context.source_registry_generation_sha256,
            self._context.graph_registry_generation_sha256,
        )

    def _validate_handle(self, handle: JointHandle) -> SessionContext:
        _require(
            handle._session is self
            and self._state is LifecycleState.ACTIVE
            and self._context is not None,
            "joint handle is not active in this session",
        )
        self._check_authority_generation(cancel_on_change=True)
        _require(
            handle.configuration_generation
            == self._context.configuration_generation,
            "joint handle configuration generation is stale",
        )
        _require(
            handle.source_registry_generation_sha256
            == self._context.source_registry_generation_sha256
            and handle.graph_registry_generation_sha256
            == self._context.graph_registry_generation_sha256,
            "joint handle authority generation is stale",
        )
        now = self._clock()
        _u64(now, "current monotonic time")
        _require(now < handle.lease.expires_monotonic_ns, "joint handle lease expired")
        return self._context

    def _submit(self, handle: JointHandle, intent: JointCommandIntent) -> None:
        context = self._validate_handle(handle)
        _require(
            self._backend.identity.command_capable,
            "selected backend is not command capable",
        )
        now = self._clock()
        _require(
            intent.canonical_actuator_id == handle.canonical_actuator_id
            and intent.canonical_configuration_digest
            == context.canonical_configuration_digest
            and intent.accepted_graph_decision_id
            == context.accepted_graph_decision_id
            and intent.session_id == context.session_id
            and intent.lease_id == handle.lease.lease_id
            and intent.lease_sequence == handle.lease.lease_sequence,
            "command identity differs from handle/session/lease",
        )
        _require(
            handle.lease.issued_monotonic_ns
            <= intent.issued_monotonic_ns
            <= now
            < intent.deadline_monotonic_ns
            <= handle.lease.expires_monotonic_ns,
            "command timing is outside current lease/deadline",
        )
        try:
            self._backend.submit(intent)
        except Exception as error:
            self.fault(f"submit_failed:{type(error).__name__}")
            raise

    def _read_state(self, handle: JointHandle) -> JointStateSample:
        context = self._validate_handle(handle)
        try:
            sample = self._backend.read_state(handle.canonical_actuator_id)
            _require(
                sample.canonical_actuator_id == handle.canonical_actuator_id
                and sample.canonical_configuration_digest
                == context.canonical_configuration_digest
                and sample.accepted_graph_decision_id
                == context.accepted_graph_decision_id
                and sample.session_id == context.session_id
                and sample.backend_id == self._backend.identity.backend_id,
                "state identity differs from handle/session/backend",
            )
        except Exception as error:
            self.fault(f"read_failed:{type(error).__name__}")
            raise
        return sample

    def fault(self, reason: str) -> None:
        _require(isinstance(reason, str) and reason, "fault reason is required")
        if self._state in {LifecycleState.FINALIZED, LifecycleState.UNCONFIGURED}:
            raise HardwareApiError("cannot fault inactive terminal/unconfigured session")
        try:
            self._backend.cancel_pending()
        finally:
            self._state = LifecycleState.FAULTED
            self._fault_reason = reason

    def deactivate(self) -> None:
        _require(
            self._state is LifecycleState.ACTIVE,
            "deactivate requires active lifecycle state",
        )
        try:
            self._backend.cancel_pending()
            self._backend.deactivate()
        except Exception as error:
            self._state = LifecycleState.FAULTED
            self._fault_reason = f"deactivate_failed:{type(error).__name__}"
            raise
        self._state = LifecycleState.INACTIVE

    def cleanup(self) -> None:
        _require(
            self._state in {LifecycleState.INACTIVE, LifecycleState.FAULTED},
            "cleanup requires inactive or faulted lifecycle state",
        )
        try:
            self._backend.cancel_pending()
            self._backend.cleanup()
        except Exception as error:
            self._state = LifecycleState.FAULTED
            self._fault_reason = f"cleanup_failed:{type(error).__name__}"
            raise
        self._context = None
        self._state = LifecycleState.UNCONFIGURED
        self._fault_reason = None

    def finalize(self) -> None:
        _require(
            self._state is LifecycleState.UNCONFIGURED,
            "finalize requires unconfigured lifecycle state",
        )
        self._state = LifecycleState.FINALIZED


__all__ = [
    "AdmissionDenied",
    "AdmissionSnapshot",
    "BackendIdentity",
    "BackendKind",
    "CANONICAL_ACTUATOR_IDS",
    "CommandLease",
    "CommandMode",
    "DropbearHardwareSession",
    "FailOnlyPhysicalBackend",
    "FakeHardwareBackend",
    "HardwareApiError",
    "JointCommandIntent",
    "JointHandle",
    "JointStateSample",
    "LifecycleState",
    "PhysicalAdapterUnavailable",
    "SessionContext",
    "SignalSource",
    "SignalValidity",
    "StateSignal",
]
