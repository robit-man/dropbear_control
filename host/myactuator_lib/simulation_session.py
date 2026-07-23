"""Deterministic, evidence-aware simulation session.

The session unifies lifecycle, virtual time, identity, reset, command, state,
fault, snapshot and trace semantics.  Engines remain evidence-distinct:
protocol state is not a plant, the synthetic plant is not a product model,
replay is read-only, and no engine in this module performs physical I/O.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, is_dataclass, replace
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Protocol

from . import (
    actuator_plant,
    actuator_plant_v2,
    plant_runtime_adapter,
    plant_runtime_adapter_v2,
    rmd_v44,
    rmd_v44_emulator,
)
from .simulation_runtime import (
    SimulationAdmission,
    SimulationRuntimeCatalog,
    SimulationSelection,
    SimulationUseCase,
)


SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{2,127}$")
MAX_U64 = (1 << 64) - 1
ZERO_SHA256 = "0" * 64


class SimulationSessionError(ValueError):
    """A session identity, transition, operation or engine result is invalid."""


class SimulationRevoked(SimulationSessionError):
    """A live catalog/source/graph generation no longer matches the session."""


class SimulationLifecycle(str, Enum):
    UNCONFIGURED = "unconfigured"
    INACTIVE = "inactive"
    ACTIVE = "active"
    FAULTED = "faulted"
    FINALIZED = "finalized"


class SimulationCommandMode(str, Enum):
    DISABLE = "disable"
    QAXIS_CURRENT = "qaxis_current"
    OUTPUT_VELOCITY = "output_velocity"
    OUTPUT_POSITION = "output_position"


class SignalValidity(str, Enum):
    VALID = "valid"
    STALE = "stale"
    MISSING = "missing"
    FAULTED = "faulted"


class FaultKind(str, Enum):
    COMMAND_REJECTION = "command_rejection"
    STATE_UNAVAILABLE = "state_unavailable"
    BACKEND_FAULT = "backend_fault"


class FaultDisposition(str, Enum):
    TRANSIENT = "transient"
    LATCHED = "latched"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SimulationSessionError(message)


def _u64(value: int, label: str, *, positive: bool = False) -> None:
    valid = (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= MAX_U64
    )
    if positive:
        valid = valid and value > 0
    _require(valid, f"{label} must be {'positive ' if positive else ''}u64")


def _identifier(value: str, label: str) -> None:
    _require(
        isinstance(value, str) and bool(IDENTIFIER.fullmatch(value)),
        f"{label} must be an exact identifier",
    )


def _sha256(value: str, label: str) -> None:
    _require(
        isinstance(value, str) and bool(SHA256.fullmatch(value)),
        f"{label} must be sha256",
    )


def _finite(value: float, label: str) -> None:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{label} must be finite",
    )


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _plain(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _canonical(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                _plain(value),
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SimulationSessionError("value is not canonically encodable") from error


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class EngineIdentity:
    backend_id: str
    backend_kind: str
    use_case: SimulationUseCase
    evidence_class: str
    deterministic_virtual_time: bool
    command_capable: bool
    exact_model_fidelity: bool = False
    physically_validated: bool = False
    physical_io: bool = False

    def __post_init__(self) -> None:
        _identifier(self.backend_id, "engine backend_id")
        _require(
            isinstance(self.backend_kind, str)
            and re.fullmatch(r"[a-z][a-z0-9_]{2,63}", self.backend_kind),
            "engine backend_kind is invalid",
        )
        _require(isinstance(self.use_case, SimulationUseCase), "engine use case is invalid")
        _identifier(self.evidence_class, "engine evidence_class")
        for value, label in (
            (self.deterministic_virtual_time, "deterministic_virtual_time"),
            (self.command_capable, "command_capable"),
            (self.exact_model_fidelity, "exact_model_fidelity"),
            (self.physically_validated, "physically_validated"),
            (self.physical_io, "physical_io"),
        ):
            _require(isinstance(value, bool), f"{label} must be bool")
        _require(not self.physical_io, "offline simulation engine cannot perform physical I/O")
        if self.physically_validated:
            _require(self.exact_model_fidelity, "physical validation requires exact fidelity")


@dataclass(frozen=True)
class ResetRequest:
    seed: int
    expected_initial_state_sha256: str | None = None

    def __post_init__(self) -> None:
        _u64(self.seed, "reset seed")
        if self.expected_initial_state_sha256 is not None:
            _sha256(self.expected_initial_state_sha256, "expected initial state digest")


@dataclass(frozen=True)
class SimulationCommand:
    catalog_generation_sha256: str
    reset_generation: int
    sequence: int
    actuator_id: str
    issued_tick: int
    deadline_tick: int
    mode: SimulationCommandMode
    target_si: float | None
    target_unit: str | None
    maximum_absolute_target_si: float | None

    def __post_init__(self) -> None:
        _sha256(self.catalog_generation_sha256, "command catalog generation")
        _u64(self.reset_generation, "command reset generation", positive=True)
        _u64(self.sequence, "command sequence", positive=True)
        _identifier(self.actuator_id, "command actuator_id")
        _u64(self.issued_tick, "command issue tick")
        _u64(self.deadline_tick, "command deadline tick", positive=True)
        _require(self.deadline_tick > self.issued_tick, "command deadline must follow issue tick")
        _require(isinstance(self.mode, SimulationCommandMode), "command mode is invalid")
        units = {
            SimulationCommandMode.QAXIS_CURRENT: "A",
            SimulationCommandMode.OUTPUT_VELOCITY: "rad/s",
            SimulationCommandMode.OUTPUT_POSITION: "rad",
        }
        if self.mode is SimulationCommandMode.DISABLE:
            _require(
                self.target_si is None
                and self.target_unit is None
                and self.maximum_absolute_target_si is None,
                "disable command carries a target or bound",
            )
        else:
            assert self.mode in units
            _finite(self.target_si, "command target")
            _require(self.target_unit == units[self.mode], "command target unit/mode mismatch")
            _finite(self.maximum_absolute_target_si, "command target bound")
            assert self.maximum_absolute_target_si is not None
            assert self.target_si is not None
            _require(self.maximum_absolute_target_si > 0.0, "command target bound must be positive")
            _require(
                abs(float(self.target_si)) <= float(self.maximum_absolute_target_si),
                "command target exceeds its explicit bound",
            )


@dataclass(frozen=True)
class EngineState:
    actuator_id: str
    sample_tick: int
    position_rad: float | None
    velocity_rad_s: float | None
    qaxis_current_a: float | None
    temperature_k: float | None
    validity: SignalValidity
    source: str
    fault_code: str
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.actuator_id, "engine state actuator_id")
        _u64(self.sample_tick, "engine state sample tick")
        _require(isinstance(self.validity, SignalValidity), "engine state validity is invalid")
        _identifier(self.source, "engine state source")
        _identifier(self.fault_code, "engine state fault_code")
        _require(
            bool(self.provenance_refs)
            and len(self.provenance_refs) == len(set(self.provenance_refs))
            and all(isinstance(item, str) and item for item in self.provenance_refs),
            "engine state provenance must be unique nonempty text",
        )
        values = (
            self.position_rad,
            self.velocity_rad_s,
            self.qaxis_current_a,
            self.temperature_k,
        )
        if self.validity in {SignalValidity.MISSING, SignalValidity.FAULTED}:
            _require(all(value is None for value in values), "invalid state carries numeric values")
        else:
            for value in values:
                if value is not None:
                    _finite(value, "engine state value")


@dataclass(frozen=True)
class SimulationState:
    catalog_generation_sha256: str
    reset_generation: int
    tick: int
    backend_id: str
    model_key: str
    configuration_id: str
    engine_state: EngineState
    exact_model_fidelity: bool
    physically_validated: bool
    physical_io: bool = False

    def __post_init__(self) -> None:
        _sha256(self.catalog_generation_sha256, "state catalog generation")
        _u64(self.reset_generation, "state reset generation", positive=True)
        _u64(self.tick, "state tick")
        _identifier(self.backend_id, "state backend_id")
        _require(isinstance(self.model_key, str) and self.model_key.startswith("model-"), "state model key is invalid")
        _require(
            isinstance(self.configuration_id, str)
            and self.configuration_id.startswith("cadcfg-"),
            "state configuration ID is invalid",
        )
        _require(self.engine_state.sample_tick <= self.tick, "state sample is from the future")
        _require(not self.physical_io, "simulation state cannot grant physical I/O")


@dataclass(frozen=True)
class ScheduledFault:
    fault_id: str
    kind: FaultKind
    actuator_id: str
    start_tick: int
    duration_ticks: int
    disposition: FaultDisposition

    def __post_init__(self) -> None:
        _identifier(self.fault_id, "fault_id")
        _require(isinstance(self.kind, FaultKind), "fault kind is invalid")
        _identifier(self.actuator_id, "fault actuator_id")
        _u64(self.start_tick, "fault start tick", positive=True)
        _u64(self.duration_ticks, "fault duration", positive=True)
        _require(isinstance(self.disposition, FaultDisposition), "fault disposition is invalid")
        _require(
            self.start_tick <= MAX_U64 - self.duration_ticks,
            "fault interval overflows u64",
        )


@dataclass(frozen=True)
class TraceEvent:
    sequence: int
    tick: int
    kind: str
    payload: dict[str, Any]
    previous_sha256: str
    record_sha256: str


@dataclass(frozen=True)
class SimulationSnapshot:
    catalog_generation_sha256: str
    source_registry_generation_sha256: str
    graph_registry_generation_sha256: str
    model_key: str
    configuration_id: str
    backend_id: str
    backend_kind: str
    reset_generation: int
    tick: int
    next_command_sequence: int
    initial_state_sha256: str
    engine_state: dict[str, Any]
    engine_state_sha256: str
    trace_sha256: str
    snapshot_sha256: str


class SimulationEngine(Protocol):
    @property
    def identity(self) -> EngineIdentity: ...

    def configure(self, selection: SimulationSelection) -> None: ...

    def reset(self, request: ResetRequest) -> EngineState: ...

    def submit(self, command: SimulationCommand) -> None: ...

    def advance_one_tick(self) -> None: ...

    def read_state(self) -> EngineState: ...

    def snapshot(self) -> dict[str, Any]: ...

    def restore(self, state: Mapping[str, Any]) -> None: ...

    def cancel_pending(self) -> None: ...

    def cleanup(self) -> None: ...


GenerationProvider = Callable[[], tuple[str, str, str]]


class SimulationSession:
    """One explicitly selected engine governed by fixed virtual ticks."""

    def __init__(
        self,
        *,
        catalog: SimulationRuntimeCatalog,
        selection: SimulationSelection,
        engine: SimulationEngine,
        generation_provider: GenerationProvider | None = None,
    ) -> None:
        admission = catalog.admit(selection)
        admission.require()
        backend = catalog.backend(selection.backend_id, kind=selection.backend_kind)
        self._validate_engine_identity(
            engine.identity, selection, admission, backend
        )
        self._catalog = catalog
        self._selection = selection
        self._admission = admission
        self._engine = engine
        self._generation_provider = generation_provider or (
            lambda: (
                catalog.generation_sha256,
                catalog.source_registry_generation_sha256,
                catalog.graph_registry_generation_sha256,
            )
        )
        _require(callable(self._generation_provider), "generation provider must be callable")
        self._state = SimulationLifecycle.UNCONFIGURED
        self._tick = 0
        self._reset_generation = 0
        self._next_command_sequence = 1
        self._initial_state_sha256 = ZERO_SHA256
        self._fault_reason: str | None = None
        self._faults: dict[str, ScheduledFault] = {}
        self._active_faults: set[str] = set()
        self._events: list[TraceEvent] = []
        self._trace_sha256 = ZERO_SHA256

    @staticmethod
    def _validate_engine_identity(
        identity: EngineIdentity,
        selection: SimulationSelection,
        admission: SimulationAdmission,
        backend: Mapping[str, Any],
    ) -> None:
        _require(identity.backend_id == selection.backend_id, "engine/backend ID mismatch")
        _require(identity.backend_kind == selection.backend_kind, "engine/backend kind mismatch")
        _require(identity.use_case is selection.use_case, "engine/use-case mismatch")
        _require(
            identity.evidence_class == backend["evidence_class"],
            "engine evidence class mismatch",
        )
        _require(
            identity.deterministic_virtual_time
            is backend["deterministic_virtual_time"],
            "engine virtual-time claim mismatch",
        )
        _require(identity.command_capable is admission.command_capable, "engine command capability mismatch")
        _require(
            identity.exact_model_fidelity is admission.exact_model_fidelity,
            "engine exact-fidelity claim mismatch",
        )
        _require(
            identity.physically_validated is admission.physically_validated,
            "engine physical-validation claim mismatch",
        )
        _require(not identity.physical_io and not admission.physical_io, "physical I/O is forbidden")

    @property
    def state(self) -> SimulationLifecycle:
        return self._state

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def reset_generation(self) -> int:
        return self._reset_generation

    @property
    def trace_sha256(self) -> str:
        return self._trace_sha256

    @property
    def fault_reason(self) -> str | None:
        return self._fault_reason

    def trace_context(self) -> dict[str, str]:
        """Return immutable generation context for trace interchange export."""

        return {
            "catalog_generation_sha256": self._catalog.generation_sha256,
            "source_registry_generation_sha256": (
                self._catalog.source_registry_generation_sha256
            ),
            "graph_registry_generation_sha256": (
                self._catalog.graph_registry_generation_sha256
            ),
        }

    def trace(self) -> tuple[TraceEvent, ...]:
        return tuple(copy.deepcopy(self._events))

    def _expected_generations(self) -> tuple[str, str, str]:
        return (
            self._catalog.generation_sha256,
            self._catalog.source_registry_generation_sha256,
            self._catalog.graph_registry_generation_sha256,
        )

    def _check_generations(self, *, fault_on_change: bool) -> None:
        try:
            current = self._generation_provider()
            valid = isinstance(current, tuple) and len(current) == 3
            if valid:
                for value in current:
                    _sha256(value, "current generation")
        except Exception as error:
            if fault_on_change:
                self._fault("generation_provider_unavailable")
            raise SimulationRevoked("generation provider is unavailable") from error
        if not valid or current != self._expected_generations():
            if fault_on_change:
                self._fault("authority_generation_changed")
            raise SimulationRevoked("catalog/source/graph generation changed")

    def _record(self, kind: str, payload: Mapping[str, Any]) -> None:
        _identifier(kind, "trace event kind")
        sequence = len(self._events) + 1
        body = {
            "sequence": sequence,
            "tick": self._tick,
            "kind": kind,
            "payload": _plain(dict(payload)),
            "previous_sha256": self._trace_sha256,
        }
        record_sha256 = _digest(body)
        self._events.append(
            TraceEvent(
                sequence,
                self._tick,
                kind,
                copy.deepcopy(body["payload"]),
                self._trace_sha256,
                record_sha256,
            )
        )
        self._trace_sha256 = record_sha256

    def configure(self, reset: ResetRequest) -> None:
        _require(self._state is SimulationLifecycle.UNCONFIGURED, "configure requires unconfigured state")
        self._check_generations(fault_on_change=False)
        try:
            self._engine.configure(self._selection)
            initial = self._engine.reset(reset)
            _require(initial.sample_tick == 0, "engine reset did not return tick zero")
            initial_sha256 = _digest(initial)
            if reset.expected_initial_state_sha256 is not None:
                _require(
                    initial_sha256 == reset.expected_initial_state_sha256,
                    "initial state digest differs from reset request",
                )
        except Exception:
            self._state = SimulationLifecycle.FAULTED
            self._fault_reason = "configure_failed"
            raise
        self._tick = 0
        self._reset_generation = 1
        self._next_command_sequence = 1
        self._initial_state_sha256 = initial_sha256
        self._faults.clear()
        self._active_faults.clear()
        self._state = SimulationLifecycle.INACTIVE
        self._fault_reason = None
        self._record(
            "configured",
            {
                "seed": reset.seed,
                "reset_generation": self._reset_generation,
                "initial_state_sha256": initial_sha256,
                "selection": self._selection,
                "engine": self._engine.identity,
            },
        )

    def reset(self, request: ResetRequest) -> None:
        _require(self._state is SimulationLifecycle.INACTIVE, "reset requires inactive state")
        self._check_generations(fault_on_change=True)
        initial = self._engine.reset(request)
        _require(initial.sample_tick == 0, "engine reset did not return tick zero")
        initial_sha256 = _digest(initial)
        if request.expected_initial_state_sha256 is not None:
            _require(initial_sha256 == request.expected_initial_state_sha256, "initial state digest mismatch")
        _require(self._reset_generation < MAX_U64, "reset generation exhausted")
        self._tick = 0
        self._reset_generation += 1
        self._next_command_sequence = 1
        self._initial_state_sha256 = initial_sha256
        self._faults.clear()
        self._active_faults.clear()
        self._record(
            "reset",
            {
                "seed": request.seed,
                "reset_generation": self._reset_generation,
                "initial_state_sha256": initial_sha256,
            },
        )

    def activate(self) -> None:
        _require(self._state is SimulationLifecycle.INACTIVE, "activate requires inactive state")
        self._check_generations(fault_on_change=True)
        self._state = SimulationLifecycle.ACTIVE
        self._record("activated", {})

    def schedule_fault(self, fault: ScheduledFault) -> None:
        _require(self._state in {SimulationLifecycle.INACTIVE, SimulationLifecycle.ACTIVE}, "fault scheduling requires configured state")
        self._check_generations(fault_on_change=True)
        _require(fault.fault_id not in self._faults, "fault_id reuse is prohibited")
        _require(fault.start_tick > self._tick, "fault must start in the future")
        self._faults[fault.fault_id] = fault
        self._record("fault-scheduled", {"fault": fault})

    def submit(self, command: SimulationCommand) -> None:
        _require(self._state is SimulationLifecycle.ACTIVE, "command requires active state")
        self._check_generations(fault_on_change=True)
        _require(self._engine.identity.command_capable, "selected engine is read-only")
        _require(command.catalog_generation_sha256 == self._catalog.generation_sha256, "command catalog generation is stale")
        _require(command.reset_generation == self._reset_generation, "command reset generation is stale")
        _require(command.sequence == self._next_command_sequence, "command sequence is not exact")
        _require(command.issued_tick == self._tick, "command issue tick must equal current tick")
        _require(self._tick < command.deadline_tick, "command deadline has expired")
        for fault_id in self._active_faults:
            if self._faults[fault_id].kind is FaultKind.COMMAND_REJECTION:
                self._record("command-denied", {"sequence": command.sequence, "fault_id": fault_id})
                raise SimulationSessionError("scheduled command rejection is active")
        try:
            self._engine.submit(command)
        except Exception:
            self._fault("engine_submit_failed")
            raise
        self._next_command_sequence += 1
        self._record("command-accepted", {"command": command})

    def _update_faults(self) -> None:
        for fault in sorted(self._faults.values(), key=lambda item: (item.start_tick, item.fault_id)):
            if fault.start_tick == self._tick:
                self._active_faults.add(fault.fault_id)
                self._record("fault-started", {"fault": fault})
                if fault.kind is FaultKind.BACKEND_FAULT:
                    self._fault(f"scheduled_backend_fault:{fault.fault_id}")
                    return
            end_tick = fault.start_tick + fault.duration_ticks
            if (
                fault.disposition is FaultDisposition.TRANSIENT
                and fault.fault_id in self._active_faults
                and end_tick == self._tick
            ):
                self._active_faults.remove(fault.fault_id)
                self._record("fault-ended", {"fault_id": fault.fault_id})

    def advance(self, ticks: int = 1) -> None:
        _require(self._state is SimulationLifecycle.ACTIVE, "advance requires active state")
        _u64(ticks, "advance ticks", positive=True)
        _require(self._tick <= MAX_U64 - ticks, "virtual tick overflow")
        for _ in range(ticks):
            self._check_generations(fault_on_change=True)
            self._tick += 1
            self._update_faults()
            if self._state is SimulationLifecycle.FAULTED:
                return
            try:
                self._engine.advance_one_tick()
            except Exception:
                self._fault("engine_advance_failed")
                raise
            self._record("tick-advanced", {})

    def read(self) -> SimulationState:
        _require(self._state is SimulationLifecycle.ACTIVE, "read requires active state")
        self._check_generations(fault_on_change=True)
        unavailable = next(
            (
                fault_id
                for fault_id in sorted(self._active_faults)
                if self._faults[fault_id].kind is FaultKind.STATE_UNAVAILABLE
            ),
            None,
        )
        if unavailable is None:
            try:
                engine_state = self._engine.read_state()
            except Exception:
                self._fault("engine_read_failed")
                raise
            _require(engine_state.sample_tick <= self._tick, "engine state sample tick is from the future")
        else:
            actuator_id = self._faults[unavailable].actuator_id
            engine_state = EngineState(
                actuator_id,
                self._tick,
                None,
                None,
                None,
                None,
                SignalValidity.FAULTED,
                "scheduled-fault",
                "state-unavailable",
                (f"fault:{unavailable}",),
            )
        result = SimulationState(
            self._catalog.generation_sha256,
            self._reset_generation,
            self._tick,
            self._engine.identity.backend_id,
            self._selection.model_key,
            self._selection.configuration_id,
            engine_state,
            self._admission.exact_model_fidelity,
            self._admission.physically_validated,
            False,
        )
        self._record("state-read", {"state": result})
        return result

    def snapshot(self) -> SimulationSnapshot:
        _require(self._state is SimulationLifecycle.INACTIVE, "snapshot requires inactive state")
        self._check_generations(fault_on_change=True)
        engine_state = _plain(self._engine.snapshot())
        _require(isinstance(engine_state, dict), "engine snapshot must be an object")
        engine_digest = _digest(engine_state)
        body = {
            "catalog_generation_sha256": self._catalog.generation_sha256,
            "source_registry_generation_sha256": self._catalog.source_registry_generation_sha256,
            "graph_registry_generation_sha256": self._catalog.graph_registry_generation_sha256,
            "model_key": self._selection.model_key,
            "configuration_id": self._selection.configuration_id,
            "backend_id": self._engine.identity.backend_id,
            "backend_kind": self._engine.identity.backend_kind,
            "reset_generation": self._reset_generation,
            "tick": self._tick,
            "next_command_sequence": self._next_command_sequence,
            "initial_state_sha256": self._initial_state_sha256,
            "engine_state": engine_state,
            "engine_state_sha256": engine_digest,
            "trace_sha256": self._trace_sha256,
        }
        snapshot = SimulationSnapshot(**body, snapshot_sha256=_digest(body))
        self._record("snapshot-created", {"snapshot_sha256": snapshot.snapshot_sha256})
        return snapshot

    def restore(self, snapshot: SimulationSnapshot) -> None:
        _require(self._state is SimulationLifecycle.INACTIVE, "restore requires inactive state")
        self._check_generations(fault_on_change=True)
        body = asdict(snapshot)
        snapshot_digest = body.pop("snapshot_sha256")
        _require(_digest(body) == snapshot_digest, "snapshot digest mismatch")
        _require(_digest(snapshot.engine_state) == snapshot.engine_state_sha256, "engine state digest mismatch")
        expected = (
            self._catalog.generation_sha256,
            self._catalog.source_registry_generation_sha256,
            self._catalog.graph_registry_generation_sha256,
            self._selection.model_key,
            self._selection.configuration_id,
            self._engine.identity.backend_id,
            self._engine.identity.backend_kind,
        )
        actual = (
            snapshot.catalog_generation_sha256,
            snapshot.source_registry_generation_sha256,
            snapshot.graph_registry_generation_sha256,
            snapshot.model_key,
            snapshot.configuration_id,
            snapshot.backend_id,
            snapshot.backend_kind,
        )
        _require(actual == expected, "snapshot identity/generation mismatch")
        self._engine.restore(snapshot.engine_state)
        self._tick = snapshot.tick
        self._reset_generation = snapshot.reset_generation
        self._next_command_sequence = snapshot.next_command_sequence
        self._initial_state_sha256 = snapshot.initial_state_sha256
        self._faults.clear()
        self._active_faults.clear()
        self._record("snapshot-restored", {"snapshot_sha256": snapshot.snapshot_sha256})

    def deactivate(self) -> None:
        _require(self._state is SimulationLifecycle.ACTIVE, "deactivate requires active state")
        self._check_generations(fault_on_change=True)
        self._engine.cancel_pending()
        self._state = SimulationLifecycle.INACTIVE
        self._record("deactivated", {})

    def _fault(self, reason: str) -> None:
        if self._state is SimulationLifecycle.FAULTED:
            return
        try:
            self._engine.cancel_pending()
        finally:
            self._fault_reason = reason
            self._state = SimulationLifecycle.FAULTED
            self._record("session-faulted", {"reason": reason})

    def cleanup(self) -> None:
        _require(self._state in {SimulationLifecycle.INACTIVE, SimulationLifecycle.FAULTED}, "cleanup requires inactive or faulted state")
        self._engine.cancel_pending()
        self._engine.cleanup()
        self._state = SimulationLifecycle.UNCONFIGURED
        self._fault_reason = None
        self._faults.clear()
        self._active_faults.clear()
        self._record("cleaned-up", {})

    def finalize(self) -> None:
        _require(self._state is SimulationLifecycle.UNCONFIGURED, "finalize requires unconfigured state")
        self._state = SimulationLifecycle.FINALIZED
        self._record("finalized", {})


class SyntheticPlantEngine:
    """Adapter for the fixed-step synthetic plant; never an exact model."""

    def __init__(
        self,
        parameter_set: actuator_plant.SyntheticParameterSet,
        *,
        actuator_id: str = "sim-actuator-1",
    ) -> None:
        _identifier(actuator_id, "synthetic actuator_id")
        self._parameter_set = parameter_set
        self._actuator_id = actuator_id
        self._plant = actuator_plant.DeterministicActuatorPlant(parameter_set)
        self._enabled = False
        self._target_current_a = 0.0
        self._configured = False

    @property
    def identity(self) -> EngineIdentity:
        return EngineIdentity(
            "synthetic-electromechanical-fixed-step-v1",
            "synthetic_actuator_plant",
            SimulationUseCase.SYNTHETIC_PLANT_SIL,
            "synthetic-test-equations-no-real-parameter-fidelity",
            True,
            True,
        )

    def configure(self, selection: SimulationSelection) -> None:
        _require(selection.backend_id == self.identity.backend_id, "synthetic selection mismatch")
        self._configured = True

    def reset(self, request: ResetRequest) -> EngineState:
        _require(self._configured, "synthetic engine is not configured")
        del request
        self._plant = actuator_plant.DeterministicActuatorPlant(self._parameter_set)
        self._enabled = False
        self._target_current_a = 0.0
        return self.read_state()

    def submit(self, command: SimulationCommand) -> None:
        if command.mode is SimulationCommandMode.DISABLE:
            self._enabled = False
            self._target_current_a = 0.0
        elif command.mode is SimulationCommandMode.QAXIS_CURRENT:
            assert command.target_si is not None
            self._enabled = True
            self._target_current_a = float(command.target_si)
        else:
            raise SimulationSessionError("synthetic plant adapter supports disable/current only")

    def advance_one_tick(self) -> None:
        self._plant.step(
            actuator_plant.PlantCommand(self._enabled, self._target_current_a)
        )

    def read_state(self) -> EngineState:
        sample = self._plant.last_step.sample
        return EngineState(
            self._actuator_id,
            self._plant.state.step_index,
            sample.output_position_rad,
            sample.output_velocity_rad_s,
            sample.qaxis_current_a,
            sample.winding_temperature_k,
            SignalValidity.VALID,
            "synthetic-plant",
            "no-fault",
            (
                f"parameter-set:{self._parameter_set.identity.parameter_set_id}",
                f"solver:{actuator_plant.SOLVER_ID}",
            ),
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": asdict(self._plant.state),
            "enabled": self._enabled,
            "target_current_a": self._target_current_a,
        }

    def restore(self, state: Mapping[str, Any]) -> None:
        _require(set(state) == {"state", "enabled", "target_current_a"}, "synthetic snapshot is not closed")
        self._plant.reset(actuator_plant.PlantState(**state["state"]))
        _require(isinstance(state["enabled"], bool), "synthetic enabled snapshot is invalid")
        _finite(state["target_current_a"], "synthetic target snapshot")
        self._enabled = state["enabled"]
        self._target_current_a = float(state["target_current_a"])

    def cancel_pending(self) -> None:
        self._enabled = False
        self._target_current_a = 0.0

    def cleanup(self) -> None:
        self.cancel_pending()
        self._configured = False


class SourcedPlantEngine:
    """Exact-tuple sourced plant behind one verified runtime contract."""

    def __init__(
        self,
        executable: plant_runtime_adapter.ExecutablePlantParameterSet,
        *,
        actuator_id: str = "sim-actuator-1",
    ) -> None:
        _require(
            isinstance(
                executable,
                plant_runtime_adapter.ExecutablePlantParameterSet,
            ),
            "typed sourced-plant runtime contract is required",
        )
        _identifier(actuator_id, "sourced actuator_id")
        self._executable = executable
        self._actuator_id = actuator_id
        self._plant = actuator_plant.DeterministicActuatorPlant(executable)
        self._enabled = False
        self._target_current_a = 0.0
        self._configured = False

    @property
    def identity(self) -> EngineIdentity:
        return EngineIdentity(
            self._executable.backend_id,
            "actuator_plant",
            SimulationUseCase.EXACT_MODEL_PLANT_SIL,
            "sil-plant-sourced",
            True,
            True,
            True,
            False,
            False,
        )

    def configure(self, selection: SimulationSelection) -> None:
        applicability = self._executable.applicability_tuple
        _require(
            selection.backend_id == self.identity.backend_id
            and selection.backend_kind == self.identity.backend_kind
            and selection.use_case is self.identity.use_case
            and (selection.series, selection.model)
            == (applicability[0], applicability[1]),
            "sourced-plant selection/contract mismatch",
        )
        self._configured = True

    def reset(self, request: ResetRequest) -> EngineState:
        _require(self._configured, "sourced plant engine is not configured")
        del request
        self._plant = actuator_plant.DeterministicActuatorPlant(
            self._executable
        )
        self._enabled = False
        self._target_current_a = 0.0
        return self.read_state()

    def submit(self, command: SimulationCommand) -> None:
        if command.mode is SimulationCommandMode.DISABLE:
            self._enabled = False
            self._target_current_a = 0.0
            return
        if command.mode is not SimulationCommandMode.QAXIS_CURRENT:
            raise SimulationSessionError(
                "sourced plant adapter v1 supports disable/current only"
            )
        assert command.target_si is not None
        target = float(command.target_si)
        direction = self._executable.guards.rotation_direction
        if (
            (direction == "positive" and target < 0.0)
            or (direction == "negative" and target > 0.0)
        ):
            raise SimulationSessionError(
                "command direction exceeds reviewed execution profile"
            )
        _require(
            abs(target)
            <= self._executable.parameters.maximum_qaxis_current_a,
            "command current exceeds sourced limit",
        )
        self._enabled = True
        self._target_current_a = target

    def advance_one_tick(self) -> None:
        result = self._plant.step(
            actuator_plant.PlantCommand(
                self._enabled,
                self._target_current_a,
                0.0,
            )
        )
        guards = self._executable.guards
        if (
            abs(result.state.rotor_velocity_rad_s)
            > guards.maximum_motor_speed_rad_s
        ):
            raise SimulationSessionError(
                "sourced maximum motor-speed guard exceeded"
            )
        if (
            result.state.case_temperature_k
            > guards.maximum_case_temperature_k
        ):
            raise SimulationSessionError(
                "sourced maximum case-temperature guard exceeded"
            )

    def read_state(self) -> EngineState:
        sample = self._plant.last_step.sample
        return EngineState(
            self._actuator_id,
            self._plant.state.step_index,
            sample.output_position_rad,
            sample.output_velocity_rad_s,
            sample.qaxis_current_a,
            sample.winding_temperature_k,
            SignalValidity.VALID,
            "sourced-plant",
            "no-fault",
            self._executable.provenance_refs,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "contract_id": self._executable.contract_id,
            "state": asdict(self._plant.state),
            "enabled": self._enabled,
            "target_current_a": self._target_current_a,
        }

    def restore(self, state: Mapping[str, Any]) -> None:
        _require(
            set(state)
            == {
                "contract_id",
                "state",
                "enabled",
                "target_current_a",
            },
            "sourced-plant snapshot is not closed",
        )
        _require(
            state["contract_id"] == self._executable.contract_id,
            "sourced-plant snapshot contract mismatch",
        )
        self._plant.reset(actuator_plant.PlantState(**state["state"]))
        _require(
            isinstance(state["enabled"], bool),
            "sourced-plant enabled snapshot is invalid",
        )
        _finite(
            state["target_current_a"],
            "sourced-plant target snapshot",
        )
        self._enabled = state["enabled"]
        self._target_current_a = float(state["target_current_a"])

    def cancel_pending(self) -> None:
        self._enabled = False
        self._target_current_a = 0.0

    def cleanup(self) -> None:
        self.cancel_pending()
        self._configured = False


class SourcedPlantV2Engine:
    """Exact-tuple source-only plant behind one verified V2 contract."""

    def __init__(
        self,
        executable: (
            plant_runtime_adapter_v2.ExecutablePlantV2ParameterSet
        ),
        *,
        actuator_id: str = "sim-actuator-1",
    ) -> None:
        _require(
            isinstance(
                executable,
                plant_runtime_adapter_v2.ExecutablePlantV2ParameterSet,
            ),
            "typed sourced-plant V2 runtime contract is required",
        )
        _identifier(actuator_id, "sourced V2 actuator_id")
        self._executable = executable
        self._actuator_id = actuator_id
        self._plant = actuator_plant_v2.DeterministicActuatorPlantV2(
            executable.configuration
        )
        self._configured = False

    @property
    def identity(self) -> EngineIdentity:
        return EngineIdentity(
            self._executable.backend_id,
            "actuator_plant",
            SimulationUseCase.EXACT_MODEL_PLANT_SIL,
            "sil-plant-sourced",
            True,
            True,
            True,
            False,
            False,
        )

    def configure(self, selection: SimulationSelection) -> None:
        applicability = self._executable.applicability_tuple
        _require(
            selection.backend_id == self.identity.backend_id
            and selection.backend_kind == self.identity.backend_kind
            and selection.use_case is self.identity.use_case
            and (selection.series, selection.model)
            == (applicability[0], applicability[1]),
            "sourced-plant V2 selection/contract mismatch",
        )
        self._configured = True

    def reset(self, request: ResetRequest) -> EngineState:
        _require(
            self._configured,
            "sourced plant V2 engine is not configured",
        )
        self._plant = actuator_plant_v2.DeterministicActuatorPlantV2(
            self._executable.configuration,
            seed=request.seed,
        )
        return self.read_state()

    def submit(self, command: SimulationCommand) -> None:
        _require(
            command.actuator_id == self._actuator_id,
            "sourced-plant V2 actuator mismatch",
        )
        if command.mode is SimulationCommandMode.DISABLE:
            enabled = False
            target = 0.0
        elif command.mode is SimulationCommandMode.QAXIS_CURRENT:
            assert command.target_si is not None
            enabled = True
            target = float(command.target_si)
        else:
            raise SimulationSessionError(
                "sourced plant adapter v2 supports disable/current only"
            )
        try:
            self._plant.submit(
                actuator_plant_v2.PlantV2Command(
                    sequence=command.sequence,
                    issued_step_index=command.issued_tick,
                    enabled=enabled,
                    target_qaxis_current_a=target,
                    deadline_step_index=command.deadline_tick,
                )
            )
        except actuator_plant_v2.PlantV2Error as error:
            raise SimulationSessionError(
                f"sourced plant V2 command rejected: {error}"
            ) from error

    def advance_one_tick(self) -> None:
        try:
            result = self._plant.step(output_load_torque_nm=0.0)
        except actuator_plant_v2.PlantV2Error as error:
            raise SimulationSessionError(
                f"sourced plant V2 advance failed: {error}"
            ) from error
        if result.diagnostics.thermal_shutdown:
            self._plant.clear_commands()
            raise SimulationSessionError(
                "sourced plant V2 thermal shutdown"
            )

    @staticmethod
    def _time_ref(
        label: str,
        value: actuator_plant_v2.PlantV2Time,
    ) -> str:
        return f"{label}:{value.numerator}/{value.denominator}s"

    def read_state(self) -> EngineState:
        sample = self._plant.last_step.sample
        if sample is None:
            return EngineState(
                self._actuator_id,
                self._plant.state.step_index,
                None,
                None,
                None,
                None,
                SignalValidity.MISSING,
                "sourced-plant-v2",
                "feedback-not-yet-delivered",
                (
                    *self._executable.provenance_refs,
                    "feedback:unavailable-before-first-delivery",
                ),
            )
        validity = (
            SignalValidity.VALID
            if sample.source_upper_step_index
            == self._plant.state.step_index
            else SignalValidity.STALE
        )
        delivery = sample.delivery_time
        _require(
            delivery is not None,
            "sourced plant V2 exposed an undelivered sample",
        )
        return EngineState(
            self._actuator_id,
            sample.source_upper_step_index,
            sample.output_position_rad,
            sample.output_velocity_rad_s,
            sample.qaxis_current_a,
            sample.winding_temperature_k,
            validity,
            "sourced-plant-v2",
            "no-fault",
            (
                *self._executable.provenance_refs,
                f"sensor-sample:{sample.sample_sequence}",
                self._time_ref("capture", sample.capture_time),
                self._time_ref("delivery", delivery),
            ),
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "contract_id": self._executable.contract_id,
            "plant_snapshot": self._plant.snapshot(),
        }

    def restore(self, state: Mapping[str, Any]) -> None:
        _require(
            isinstance(state, Mapping)
            and set(state) == {"contract_id", "plant_snapshot"},
            "sourced-plant V2 snapshot is not closed",
        )
        _require(
            state["contract_id"] == self._executable.contract_id,
            "sourced-plant V2 snapshot contract mismatch",
        )
        try:
            self._plant.restore(state["plant_snapshot"])
        except actuator_plant_v2.PlantV2Error as error:
            raise SimulationSessionError(
                f"sourced-plant V2 snapshot rejected: {error}"
            ) from error

    def cancel_pending(self) -> None:
        self._plant.clear_commands()

    def cleanup(self) -> None:
        self.cancel_pending()
        self._configured = False


class ProtocolEmulatorEngine:
    """Adapter for V4.4 protocol state; feedback is independent input state."""

    def __init__(
        self,
        *,
        motor_id: int = 1,
        actuator_id: str = "sim-actuator-1",
        tick_period_us: int = 1_000,
    ) -> None:
        self._motor_id = rmd_v44.validate_motor_id(motor_id)
        _identifier(actuator_id, "protocol actuator_id")
        _u64(tick_period_us, "protocol tick period", positive=True)
        self._actuator_id = actuator_id
        self._tick_period_us = tick_period_us
        self._tick = 0
        self._configured = False
        self._emulator = self._new_emulator(rmd_v44_emulator.NodeState(motor_id, disabled=False))

    @staticmethod
    def _new_emulator(state: rmd_v44_emulator.NodeState) -> rmd_v44_emulator.RmdV44Emulator:
        policy = rmd_v44_emulator.CapabilityPolicy.allow_explicit(
            motion=rmd_v44_emulator.MOTION_COMMANDS,
            brake=rmd_v44_emulator.BRAKE_COMMANDS,
        )
        return rmd_v44_emulator.RmdV44Emulator(
            [state],
            capability_policy=policy,
            admission_callback=lambda _context: True,
        )

    @property
    def identity(self) -> EngineIdentity:
        return EngineIdentity(
            "rmd-v44-protocol-emulator",
            "protocol_emulator",
            SimulationUseCase.PROTOCOL_STATE_SIL,
            "sil-protocol",
            True,
            True,
        )

    def configure(self, selection: SimulationSelection) -> None:
        _require(selection.backend_id == self.identity.backend_id, "protocol selection mismatch")
        self._configured = True

    def reset(self, request: ResetRequest) -> EngineState:
        _require(self._configured, "protocol engine is not configured")
        del request
        self._tick = 0
        self._emulator = self._new_emulator(
            rmd_v44_emulator.NodeState(self._motor_id, disabled=False)
        )
        return self.read_state()

    def submit(self, command: SimulationCommand) -> None:
        if command.mode is SimulationCommandMode.DISABLE:
            frame = rmd_v44.encode_request(self._motor_id, rmd_v44.Command.STOP)
        elif command.mode is SimulationCommandMode.QAXIS_CURRENT:
            frame = rmd_v44.encode_iq_control_amps(self._motor_id, command.target_si)
        elif command.mode is SimulationCommandMode.OUTPUT_VELOCITY:
            assert command.target_si is not None
            frame = rmd_v44.encode_speed_control_dps(
                self._motor_id, math.degrees(float(command.target_si)), 100
            )
        elif command.mode is SimulationCommandMode.OUTPUT_POSITION:
            assert command.target_si is not None
            frame = rmd_v44.encode_absolute_position_degrees(
                self._motor_id,
                math.degrees(float(command.target_si)),
                360,
            )
        else:
            raise SimulationSessionError("unsupported protocol command mode")
        submission = self._emulator.submit(frame)
        _require(submission.accepted, f"protocol emulator rejected command: {submission.reason}")
        self._emulator.poll()

    def advance_one_tick(self) -> None:
        self._emulator.advance_by(self._tick_period_us)
        self._tick += 1

    def read_state(self) -> EngineState:
        state = self._emulator.state(self._motor_id)
        return EngineState(
            self._actuator_id,
            self._tick,
            state.multi_turn_angle_raw * math.pi / 18_000.0,
            state.output_speed_raw * math.pi / 180.0,
            state.iq_raw * 0.01,
            state.motor_temperature_c + 273.15,
            SignalValidity.VALID,
            "protocol-input",
            "drive-error" if state.error_mask else "no-fault",
            (
                f"protocol:{rmd_v44.SOURCE_EDITION}",
                "feedback:independent-input-not-dynamics",
            ),
        )

    def snapshot(self) -> dict[str, Any]:
        state = asdict(self._emulator.state(self._motor_id))
        state["mode"] = int(state["mode"])
        return {"tick": self._tick, "node_state": state}

    def restore(self, state: Mapping[str, Any]) -> None:
        _require(set(state) == {"tick", "node_state"}, "protocol snapshot is not closed")
        _u64(state["tick"], "protocol snapshot tick")
        node = rmd_v44_emulator.NodeState(**state["node_state"])
        _require(node.motor_id == self._motor_id, "protocol snapshot motor mismatch")
        self._emulator = self._new_emulator(node)
        self._emulator.advance_to(int(state["tick"]) * self._tick_period_us)
        self._tick = int(state["tick"])

    def cancel_pending(self) -> None:
        self._emulator.run_until_idle()

    def cleanup(self) -> None:
        self._configured = False


class RecordedReplayEngine:
    """Read-only, fixed-tick replay adapter."""

    def __init__(self, states: Iterable[EngineState]) -> None:
        self._states = tuple(states)
        _require(bool(self._states), "replay requires at least one state")
        _require(
            [state.sample_tick for state in self._states]
            == list(range(len(self._states))),
            "replay sample ticks must be dense from zero",
        )
        actuator_ids = {state.actuator_id for state in self._states}
        _require(len(actuator_ids) == 1, "replay actuator identity changed")
        self._index = 0
        self._configured = False

    @property
    def identity(self) -> EngineIdentity:
        return EngineIdentity(
            "canonical-recorded-state-replay-v1",
            "recorded_replay",
            SimulationUseCase.RECORDED_REPLAY,
            "offline-replay",
            True,
            False,
        )

    def configure(self, selection: SimulationSelection) -> None:
        _require(selection.backend_id == self.identity.backend_id, "replay selection mismatch")
        self._configured = True

    def reset(self, request: ResetRequest) -> EngineState:
        _require(self._configured, "replay engine is not configured")
        del request
        self._index = 0
        return self.read_state()

    def submit(self, command: SimulationCommand) -> None:
        del command
        raise SimulationSessionError("recorded replay is read-only")

    def advance_one_tick(self) -> None:
        _require(self._index + 1 < len(self._states), "replay exhausted")
        self._index += 1

    def read_state(self) -> EngineState:
        return self._states[self._index]

    def snapshot(self) -> dict[str, Any]:
        return {"index": self._index, "corpus_sha256": _digest(self._states)}

    def restore(self, state: Mapping[str, Any]) -> None:
        _require(set(state) == {"index", "corpus_sha256"}, "replay snapshot is not closed")
        _require(state["corpus_sha256"] == _digest(self._states), "replay corpus changed")
        _u64(state["index"], "replay snapshot index")
        _require(state["index"] < len(self._states), "replay snapshot index is outside corpus")
        self._index = int(state["index"])

    def cancel_pending(self) -> None:
        return None

    def cleanup(self) -> None:
        self._configured = False


__all__ = [
    "EngineIdentity",
    "EngineState",
    "FaultDisposition",
    "FaultKind",
    "GenerationProvider",
    "ProtocolEmulatorEngine",
    "RecordedReplayEngine",
    "ResetRequest",
    "ScheduledFault",
    "SignalValidity",
    "SimulationCommand",
    "SimulationCommandMode",
    "SimulationEngine",
    "SimulationLifecycle",
    "SimulationRevoked",
    "SimulationSession",
    "SimulationSessionError",
    "SimulationSnapshot",
    "SimulationState",
    "SourcedPlantEngine",
    "SourcedPlantV2Engine",
    "SyntheticPlantEngine",
    "TraceEvent",
]
