"""Deterministic, transactional composition of multiple V2 actuator plants.

This module is an offline synthetic coordination fixture.  It does not model
Dropbear rigid-body mechanics, a shared electrical bus, exact MYACTUATOR
products, physical I/O or motion authority.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from . import actuator_plant
from . import actuator_plant_v2


SCHEMA_VERSION = "myactuator-multi-actuator-plant-v2/1"
SNAPSHOT_SCHEMA_VERSION = "myactuator-multi-actuator-plant-v2-snapshot/1"
SEED_DERIVATION = "sha256-scene-seed-actuator-v1"
COMMAND_SET_POLICY = "all_declared_actuators_exactly_once"
COMMAND_ATOMICITY_POLICY = "reject_entire_batch_before_mutation"
STEP_ATOMICITY_POLICY = "rollback_entire_step_on_failure"
FAULT_POLICY = "latch_bank_fault_and_clear_all_commands"
EVIDENCE_CLASS = "synthetic-multi-actuator-sil-no-robot-fidelity"
SUBSTITUTION_SCOPE = "offline-multi-actuator-control-tests-only"

SUPPORT_GRANTED = False
EXACT_MODEL_FIDELITY = False
DROPBEAR_CANONICAL = False
MODELS_RIGID_BODY = False
MODELS_SHARED_POWER_BUS = False
PHYSICAL_VALIDATION = False
PHYSICAL_IO = False
MOTION_AUTHORITY = False

MAX_U64 = (1 << 64) - 1
SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{2,127}$")


class MultiActuatorPlantV2Error(ValueError):
    """A scene identity, transaction, snapshot or state is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MultiActuatorPlantV2Error(message)


def _identifier(value: Any, label: str) -> str:
    _require(
        isinstance(value, str) and bool(IDENTIFIER.fullmatch(value)),
        f"{label} must be an exact identifier",
    )
    return value


def _sha256(value: Any, label: str) -> str:
    _require(
        isinstance(value, str) and bool(SHA256.fullmatch(value)),
        f"{label} must be sha256",
    )
    return value


def _u64(value: Any, label: str, *, positive: bool = False) -> int:
    valid = (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= MAX_U64
    )
    if positive:
        valid = valid and value > 0
    _require(valid, f"{label} must be {'positive ' if positive else ''}u64")
    return value


def _finite(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{label} must be finite",
    )
    return float(value)


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


def canonical_json(value: Any) -> bytes:
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
        raise MultiActuatorPlantV2Error(
            "value is not canonically encodable"
        ) from error


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class MultiActuatorV2Member:
    actuator_id: str
    configuration: actuator_plant_v2.PlantV2Configuration

    def validate(self) -> None:
        _identifier(self.actuator_id, "member actuator_id")
        _require(
            isinstance(
                self.configuration,
                actuator_plant_v2.PlantV2Configuration,
            ),
            "member requires a typed V2 configuration",
        )
        try:
            self.configuration.validate()
        except actuator_plant_v2.PlantV2Error as error:
            raise MultiActuatorPlantV2Error(
                f"{self.actuator_id}: V2 configuration is invalid: {error}"
            ) from error


@dataclass(frozen=True)
class MultiActuatorV2Configuration:
    scene_id: str
    members: tuple[MultiActuatorV2Member, ...]
    maximum_aggregate_absolute_command_current_a: float
    command_set_policy: str = COMMAND_SET_POLICY
    command_atomicity_policy: str = COMMAND_ATOMICITY_POLICY
    step_atomicity_policy: str = STEP_ATOMICITY_POLICY
    fault_policy: str = FAULT_POLICY
    seed_derivation: str = SEED_DERIVATION
    evidence_class: str = EVIDENCE_CLASS
    substitution_scope: str = SUBSTITUTION_SCOPE
    support_granted: bool = SUPPORT_GRANTED
    exact_model_fidelity: bool = EXACT_MODEL_FIDELITY
    dropbear_canonical: bool = DROPBEAR_CANONICAL
    models_rigid_body: bool = MODELS_RIGID_BODY
    models_shared_power_bus: bool = MODELS_SHARED_POWER_BUS
    physical_validation: bool = PHYSICAL_VALIDATION
    physical_io: bool = PHYSICAL_IO
    motion_authority: bool = MOTION_AUTHORITY

    def validate(self) -> None:
        _identifier(self.scene_id, "scene_id")
        _require(
            isinstance(self.members, tuple) and bool(self.members),
            "scene members must be a nonempty tuple",
        )
        for member in self.members:
            _require(
                isinstance(member, MultiActuatorV2Member),
                "scene member is not typed",
            )
            member.validate()
        actuator_ids = tuple(member.actuator_id for member in self.members)
        _require(
            actuator_ids == tuple(sorted(actuator_ids))
            and len(actuator_ids) == len(set(actuator_ids)),
            "scene members must be unique and in canonical order",
        )
        budget = _finite(
            self.maximum_aggregate_absolute_command_current_a,
            "aggregate command-current budget",
        )
        _require(budget > 0.0, "aggregate command-current budget must be positive")
        expected_policies = {
            "command_set_policy": COMMAND_SET_POLICY,
            "command_atomicity_policy": COMMAND_ATOMICITY_POLICY,
            "step_atomicity_policy": STEP_ATOMICITY_POLICY,
            "fault_policy": FAULT_POLICY,
            "seed_derivation": SEED_DERIVATION,
            "evidence_class": EVIDENCE_CLASS,
            "substitution_scope": SUBSTITUTION_SCOPE,
        }
        for name, expected in expected_policies.items():
            _require(
                getattr(self, name) == expected,
                f"scene {name} is unsupported",
            )
        for name in (
            "support_granted",
            "exact_model_fidelity",
            "dropbear_canonical",
            "models_rigid_body",
            "models_shared_power_bus",
            "physical_validation",
            "physical_io",
            "motion_authority",
        ):
            _require(
                getattr(self, name) is False,
                f"scene authority promotion: {name}",
            )
        periods = {
            member.configuration.parameters.current_loop_period_s
            for member in self.members
        }
        _require(
            len(periods) == 1,
            "all scene members must have one exact solver period",
        )

    @property
    def actuator_ids(self) -> tuple[str, ...]:
        self.validate()
        return tuple(member.actuator_id for member in self.members)

    @property
    def configuration_sha256(self) -> str:
        self.validate()
        return _digest(
            {
                "schema_version": SCHEMA_VERSION,
                "scene_id": self.scene_id,
                "members": [
                    {
                        "actuator_id": member.actuator_id,
                        "plant_configuration_sha256": (
                            member.configuration.configuration_sha256
                        ),
                    }
                    for member in self.members
                ],
                "maximum_aggregate_absolute_command_current_a": float(
                    self.maximum_aggregate_absolute_command_current_a
                ),
                "command_set_policy": self.command_set_policy,
                "command_atomicity_policy": self.command_atomicity_policy,
                "step_atomicity_policy": self.step_atomicity_policy,
                "fault_policy": self.fault_policy,
                "seed_derivation": self.seed_derivation,
                "evidence_class": self.evidence_class,
                "substitution_scope": self.substitution_scope,
                "support_granted": self.support_granted,
                "exact_model_fidelity": self.exact_model_fidelity,
                "dropbear_canonical": self.dropbear_canonical,
                "models_rigid_body": self.models_rigid_body,
                "models_shared_power_bus": self.models_shared_power_bus,
                "physical_validation": self.physical_validation,
                "physical_io": self.physical_io,
                "motion_authority": self.motion_authority,
                "solver_id": actuator_plant_v2.SOLVER_ID,
            }
        )


@dataclass(frozen=True)
class MultiActuatorV2Command:
    actuator_id: str
    enabled: bool
    target_qaxis_current_a: float


@dataclass(frozen=True)
class MultiActuatorV2CommandBatch:
    scene_configuration_sha256: str
    reset_generation: int
    sequence: int
    issued_step_index: int
    deadline_step_index: int
    commands: tuple[MultiActuatorV2Command, ...]


@dataclass(frozen=True)
class MultiActuatorV2Load:
    actuator_id: str
    output_load_torque_nm: float


@dataclass(frozen=True)
class MultiActuatorV2MemberState:
    actuator_id: str
    plant_configuration_sha256: str
    derived_seed: int
    state: actuator_plant.PlantState
    sample: actuator_plant_v2.PlantV2SensorSample | None
    diagnostics: actuator_plant_v2.PlantV2Diagnostics


@dataclass(frozen=True)
class MultiActuatorV2Step:
    scene_id: str
    scene_configuration_sha256: str
    reset_generation: int
    step_index: int
    next_batch_sequence: int
    fault_latched: bool
    fault_reason: str
    aggregate_absolute_qaxis_current_a: float
    maximum_winding_temperature_k: float
    maximum_case_temperature_k: float
    members: tuple[MultiActuatorV2MemberState, ...]
    evidence_class: str = EVIDENCE_CLASS
    substitution_scope: str = SUBSTITUTION_SCOPE
    support_granted: bool = SUPPORT_GRANTED
    exact_model_fidelity: bool = EXACT_MODEL_FIDELITY
    dropbear_canonical: bool = DROPBEAR_CANONICAL
    models_rigid_body: bool = MODELS_RIGID_BODY
    models_shared_power_bus: bool = MODELS_SHARED_POWER_BUS
    physical_validation: bool = PHYSICAL_VALIDATION
    physical_io: bool = PHYSICAL_IO
    motion_authority: bool = MOTION_AUTHORITY


class DeterministicMultiActuatorPlantV2:
    """Synchronized, transactional bank of deterministic V2 plants."""

    def __init__(
        self,
        configuration: MultiActuatorV2Configuration,
        *,
        seed: int = 0,
    ) -> None:
        _require(
            isinstance(configuration, MultiActuatorV2Configuration),
            "typed multi-actuator V2 configuration is required",
        )
        configuration.validate()
        self.configuration = configuration
        self._members = {
            member.actuator_id: member
            for member in configuration.members
        }
        self._engines: dict[
            str,
            actuator_plant_v2.DeterministicActuatorPlantV2,
        ] = {}
        self._scene_seed = 0
        self._reset_generation = 0
        self._step_index = 0
        self._next_batch_sequence = 1
        self._fault_latched = False
        self._fault_reason = "no-fault"
        self._last_step: MultiActuatorV2Step | None = None
        self.reset(seed=seed)

    @property
    def reset_generation(self) -> int:
        return self._reset_generation

    @property
    def step_index(self) -> int:
        return self._step_index

    @property
    def next_batch_sequence(self) -> int:
        return self._next_batch_sequence

    @property
    def fault_latched(self) -> bool:
        return self._fault_latched

    @property
    def fault_reason(self) -> str:
        return self._fault_reason

    @property
    def last_step(self) -> MultiActuatorV2Step:
        assert self._last_step is not None
        return self._last_step

    def _derive_seed(self, actuator_id: str, scene_seed: int) -> int:
        payload = (
            b"myactuator-multi-actuator-v2-seed\0"
            + self.configuration.configuration_sha256.encode("ascii")
            + b"\0"
            + str(scene_seed).encode("ascii")
            + b"\0"
            + actuator_id.encode("ascii")
        )
        return int.from_bytes(
            hashlib.sha256(payload).digest()[:8],
            byteorder="big",
            signed=False,
        )

    def _new_engines(
        self,
        *,
        scene_seed: int,
    ) -> dict[str, actuator_plant_v2.DeterministicActuatorPlantV2]:
        return {
            member.actuator_id: (
                actuator_plant_v2.DeterministicActuatorPlantV2(
                    member.configuration,
                    seed=self._derive_seed(member.actuator_id, scene_seed),
                )
            )
            for member in self.configuration.members
        }

    def reset(self, *, seed: int = 0) -> MultiActuatorV2Step:
        _u64(seed, "scene seed")
        _require(
            self._reset_generation < MAX_U64,
            "reset generation overflow",
        )
        engines = self._new_engines(scene_seed=seed)
        self._engines = engines
        self._scene_seed = seed
        self._reset_generation += 1
        self._step_index = 0
        self._next_batch_sequence = 1
        self._fault_latched = False
        self._fault_reason = "no-fault"
        self._last_step = self._project(engines)
        return self._last_step

    def _validate_command_batch(
        self,
        batch: MultiActuatorV2CommandBatch,
    ) -> None:
        _require(
            isinstance(batch, MultiActuatorV2CommandBatch),
            "typed multi-actuator command batch is required",
        )
        _require(not self._fault_latched, "bank fault is latched")
        _sha256(
            batch.scene_configuration_sha256,
            "batch scene configuration",
        )
        _require(
            batch.scene_configuration_sha256
            == self.configuration.configuration_sha256,
            "batch scene configuration mismatch",
        )
        _u64(batch.reset_generation, "batch reset generation", positive=True)
        _require(
            batch.reset_generation == self._reset_generation,
            "batch reset generation is stale or future",
        )
        _u64(batch.sequence, "batch sequence", positive=True)
        _require(
            batch.sequence == self._next_batch_sequence,
            "batch sequence is not dense",
        )
        _u64(batch.issued_step_index, "batch issue step")
        _u64(batch.deadline_step_index, "batch deadline step", positive=True)
        _require(
            batch.issued_step_index == self._step_index,
            "batch issue step is stale or future",
        )
        _require(
            batch.deadline_step_index > batch.issued_step_index,
            "batch deadline must follow issue step",
        )
        _require(
            isinstance(batch.commands, tuple),
            "batch commands must be a tuple",
        )
        _require(
            all(
                isinstance(row, MultiActuatorV2Command)
                for row in batch.commands
            ),
            "batch command row is not typed",
        )
        _require(
            tuple(row.actuator_id for row in batch.commands)
            == self.configuration.actuator_ids,
            "batch must contain every actuator exactly once in canonical order",
        )
        aggregate = 0.0
        for row in batch.commands:
            _identifier(row.actuator_id, "batch actuator_id")
            _require(
                isinstance(row.enabled, bool),
                f"{row.actuator_id}: enabled must be bool",
            )
            target = _finite(
                row.target_qaxis_current_a,
                f"{row.actuator_id}: command current",
            )
            member = self._members[row.actuator_id]
            parameters = member.configuration.parameters
            semantics = member.configuration.semantics
            _require(
                row.enabled or target == 0.0,
                f"{row.actuator_id}: disabled target must be zero",
            )
            _require(
                abs(target) <= parameters.maximum_qaxis_current_a,
                f"{row.actuator_id}: target exceeds source current limit",
            )
            _require(
                not (
                    semantics.rotation_direction == "positive"
                    and target < 0.0
                )
                and not (
                    semantics.rotation_direction == "negative"
                    and target > 0.0
                ),
                f"{row.actuator_id}: target exceeds direction semantics",
            )
            if row.enabled:
                aggregate += abs(target)
        _require(
            aggregate
            <= self.configuration.maximum_aggregate_absolute_command_current_a,
            "batch exceeds aggregate command-current budget",
        )

    @staticmethod
    def _restore_engine_snapshots(
        engines: Mapping[
            str,
            actuator_plant_v2.DeterministicActuatorPlantV2,
        ],
        snapshots: Mapping[str, Mapping[str, Any]],
    ) -> None:
        failures: list[str] = []
        for actuator_id, engine in engines.items():
            try:
                engine.restore(snapshots[actuator_id])
            except Exception as error:  # pragma: no cover - catastrophic guard
                failures.append(f"{actuator_id}:{type(error).__name__}")
        if failures:
            raise MultiActuatorPlantV2Error(
                "multi-actuator rollback failed: " + ",".join(failures)
            )

    def submit(self, batch: MultiActuatorV2CommandBatch) -> None:
        self._validate_command_batch(batch)
        snapshots = {
            actuator_id: engine.snapshot()
            for actuator_id, engine in self._engines.items()
        }
        try:
            for row in batch.commands:
                self._engines[row.actuator_id].submit(
                    actuator_plant_v2.PlantV2Command(
                        sequence=batch.sequence,
                        issued_step_index=batch.issued_step_index,
                        enabled=row.enabled,
                        target_qaxis_current_a=(
                            row.target_qaxis_current_a
                            if row.enabled
                            else 0.0
                        ),
                        deadline_step_index=batch.deadline_step_index,
                    )
                )
        except Exception as error:
            self._restore_engine_snapshots(self._engines, snapshots)
            raise MultiActuatorPlantV2Error(
                f"atomic command batch rejected: {error}"
            ) from error
        self._next_batch_sequence += 1
        self._last_step = self._project(self._engines)

    def _validate_loads(
        self,
        loads: tuple[MultiActuatorV2Load, ...],
    ) -> None:
        _require(not self._fault_latched, "bank fault is latched")
        _require(isinstance(loads, tuple), "step loads must be a tuple")
        _require(
            all(isinstance(row, MultiActuatorV2Load) for row in loads),
            "step load row is not typed",
        )
        _require(
            tuple(row.actuator_id for row in loads)
            == self.configuration.actuator_ids,
            "step loads must contain every actuator exactly once in canonical order",
        )
        for row in loads:
            load = _finite(
                row.output_load_torque_nm,
                f"{row.actuator_id}: output load",
            )
            _require(
                abs(load)
                <= self._members[
                    row.actuator_id
                ].configuration.parameters.output_load_torque_bound_nm,
                f"{row.actuator_id}: output load exceeds source bound",
            )

    def advance(
        self,
        loads: tuple[MultiActuatorV2Load, ...],
    ) -> MultiActuatorV2Step:
        self._validate_loads(loads)
        snapshots = {
            actuator_id: engine.snapshot()
            for actuator_id, engine in self._engines.items()
        }
        expected_step = self._step_index + 1
        try:
            for row in loads:
                result = self._engines[row.actuator_id].step(
                    output_load_torque_nm=row.output_load_torque_nm
                )
                _require(
                    result.state.step_index == expected_step,
                    f"{row.actuator_id}: synchronized step drift",
                )
        except Exception as error:
            self._restore_engine_snapshots(self._engines, snapshots)
            raise MultiActuatorPlantV2Error(
                f"atomic synchronized step rejected: {error}"
            ) from error
        self._step_index = expected_step
        thermal = [
            actuator_id
            for actuator_id, engine in self._engines.items()
            if engine.last_step.diagnostics.thermal_shutdown
        ]
        if thermal:
            for engine in self._engines.values():
                engine.clear_commands()
            self._fault_latched = True
            self._fault_reason = f"thermal-shutdown:{thermal[0]}"
        self._last_step = self._project(self._engines)
        return self._last_step

    def zero_loads(self) -> tuple[MultiActuatorV2Load, ...]:
        return tuple(
            MultiActuatorV2Load(actuator_id, 0.0)
            for actuator_id in self.configuration.actuator_ids
        )

    def disabled_batch(
        self,
        *,
        deadline_step_index: int,
    ) -> MultiActuatorV2CommandBatch:
        return MultiActuatorV2CommandBatch(
            scene_configuration_sha256=(
                self.configuration.configuration_sha256
            ),
            reset_generation=self._reset_generation,
            sequence=self._next_batch_sequence,
            issued_step_index=self._step_index,
            deadline_step_index=deadline_step_index,
            commands=tuple(
                MultiActuatorV2Command(actuator_id, False, 0.0)
                for actuator_id in self.configuration.actuator_ids
            ),
        )

    def _project(
        self,
        engines: Mapping[
            str,
            actuator_plant_v2.DeterministicActuatorPlantV2,
        ],
        *,
        scene_seed: int | None = None,
        reset_generation: int | None = None,
        step_index: int | None = None,
        next_batch_sequence: int | None = None,
        fault_latched: bool | None = None,
        fault_reason: str | None = None,
    ) -> MultiActuatorV2Step:
        selected_seed = (
            self._scene_seed if scene_seed is None else scene_seed
        )
        selected_generation = (
            self._reset_generation
            if reset_generation is None
            else reset_generation
        )
        selected_step = self._step_index if step_index is None else step_index
        selected_next = (
            self._next_batch_sequence
            if next_batch_sequence is None
            else next_batch_sequence
        )
        selected_fault = (
            self._fault_latched if fault_latched is None else fault_latched
        )
        selected_reason = (
            self._fault_reason if fault_reason is None else fault_reason
        )
        rows: list[MultiActuatorV2MemberState] = []
        for member in self.configuration.members:
            result = engines[member.actuator_id].last_step
            _require(
                result.state.step_index == selected_step,
                f"{member.actuator_id}: bank/local step mismatch",
            )
            rows.append(
                MultiActuatorV2MemberState(
                    actuator_id=member.actuator_id,
                    plant_configuration_sha256=(
                        member.configuration.configuration_sha256
                    ),
                    derived_seed=self._derive_seed(
                        member.actuator_id,
                        selected_seed,
                    ),
                    state=result.state,
                    sample=result.sample,
                    diagnostics=result.diagnostics,
                )
            )
        _require(bool(rows), "bank projection cannot be empty")
        result = MultiActuatorV2Step(
            scene_id=self.configuration.scene_id,
            scene_configuration_sha256=(
                self.configuration.configuration_sha256
            ),
            reset_generation=selected_generation,
            step_index=selected_step,
            next_batch_sequence=selected_next,
            fault_latched=selected_fault,
            fault_reason=selected_reason,
            aggregate_absolute_qaxis_current_a=sum(
                abs(row.state.qaxis_current_a) for row in rows
            ),
            maximum_winding_temperature_k=max(
                row.state.winding_temperature_k for row in rows
            ),
            maximum_case_temperature_k=max(
                row.state.case_temperature_k for row in rows
            ),
            members=tuple(rows),
        )
        self._validate_projection(result)
        return result

    def _validate_projection(self, value: MultiActuatorV2Step) -> None:
        _require(
            isinstance(value, MultiActuatorV2Step),
            "bank state projection is not typed",
        )
        _require(
            value.scene_id == self.configuration.scene_id
            and value.scene_configuration_sha256
            == self.configuration.configuration_sha256,
            "bank projection scene identity mismatch",
        )
        _u64(value.reset_generation, "projection reset generation", positive=True)
        _u64(value.step_index, "projection step")
        _u64(value.next_batch_sequence, "projection next batch", positive=True)
        _require(
            tuple(row.actuator_id for row in value.members)
            == self.configuration.actuator_ids,
            "bank projection actuator partition mismatch",
        )
        _require(
            value.fault_reason
            == (
                value.fault_reason
                if value.fault_latched
                else "no-fault"
            )
            and (
                not value.fault_latched
                or value.fault_reason.startswith("thermal-shutdown:")
            ),
            "bank projection fault partition is invalid",
        )
        for name in (
            "support_granted",
            "exact_model_fidelity",
            "dropbear_canonical",
            "models_rigid_body",
            "models_shared_power_bus",
            "physical_validation",
            "physical_io",
            "motion_authority",
        ):
            _require(
                getattr(value, name) is False,
                f"bank projection authority promotion: {name}",
            )
        _require(
            value.evidence_class == EVIDENCE_CLASS
            and value.substitution_scope == SUBSTITUTION_SCOPE,
            "bank projection evidence identity mismatch",
        )
        for name in (
            "aggregate_absolute_qaxis_current_a",
            "maximum_winding_temperature_k",
            "maximum_case_temperature_k",
        ):
            _finite(getattr(value, name), f"projection {name}")

    def snapshot(self) -> dict[str, Any]:
        payload = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "scene_id": self.configuration.scene_id,
            "scene_configuration_sha256": (
                self.configuration.configuration_sha256
            ),
            "scene_seed": self._scene_seed,
            "reset_generation": self._reset_generation,
            "step_index": self._step_index,
            "next_batch_sequence": self._next_batch_sequence,
            "fault_latched": self._fault_latched,
            "fault_reason": self._fault_reason,
            "last_step": _plain(self.last_step),
            "actuator_snapshots": [
                {
                    "actuator_id": member.actuator_id,
                    "plant_configuration_sha256": (
                        member.configuration.configuration_sha256
                    ),
                    "derived_seed": self._derive_seed(
                        member.actuator_id,
                        self._scene_seed,
                    ),
                    "plant_snapshot": self._engines[
                        member.actuator_id
                    ].snapshot(),
                }
                for member in self.configuration.members
            ],
            "evidence_class": EVIDENCE_CLASS,
            "substitution_scope": SUBSTITUTION_SCOPE,
            "support_granted": False,
            "exact_model_fidelity": False,
            "dropbear_canonical": False,
            "models_rigid_body": False,
            "models_shared_power_bus": False,
            "physical_validation": False,
            "physical_io": False,
            "motion_authority": False,
        }
        return {**payload, "snapshot_sha256": _digest(payload)}

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        expected = {
            "schema_version",
            "scene_id",
            "scene_configuration_sha256",
            "scene_seed",
            "reset_generation",
            "step_index",
            "next_batch_sequence",
            "fault_latched",
            "fault_reason",
            "last_step",
            "actuator_snapshots",
            "evidence_class",
            "substitution_scope",
            "support_granted",
            "exact_model_fidelity",
            "dropbear_canonical",
            "models_rigid_body",
            "models_shared_power_bus",
            "physical_validation",
            "physical_io",
            "motion_authority",
            "snapshot_sha256",
        }
        _require(
            isinstance(snapshot, Mapping) and set(snapshot) == expected,
            "multi-actuator snapshot field closure drift",
        )
        payload = {
            key: value
            for key, value in snapshot.items()
            if key != "snapshot_sha256"
        }
        _require(
            snapshot["snapshot_sha256"] == _digest(payload),
            "multi-actuator snapshot integrity mismatch",
        )
        _require(
            snapshot["schema_version"] == SNAPSHOT_SCHEMA_VERSION
            and snapshot["scene_id"] == self.configuration.scene_id
            and snapshot["scene_configuration_sha256"]
            == self.configuration.configuration_sha256,
            "multi-actuator snapshot scene identity mismatch",
        )
        for name in (
            "support_granted",
            "exact_model_fidelity",
            "dropbear_canonical",
            "models_rigid_body",
            "models_shared_power_bus",
            "physical_validation",
            "physical_io",
            "motion_authority",
        ):
            _require(
                snapshot[name] is False,
                f"multi-actuator snapshot authority promotion: {name}",
            )
        _require(
            snapshot["evidence_class"] == EVIDENCE_CLASS
            and snapshot["substitution_scope"] == SUBSTITUTION_SCOPE,
            "multi-actuator snapshot evidence identity mismatch",
        )
        scene_seed = _u64(snapshot["scene_seed"], "snapshot scene seed")
        reset_generation = _u64(
            snapshot["reset_generation"],
            "snapshot reset generation",
            positive=True,
        )
        step_index = _u64(snapshot["step_index"], "snapshot step")
        next_batch_sequence = _u64(
            snapshot["next_batch_sequence"],
            "snapshot next batch",
            positive=True,
        )
        _require(
            isinstance(snapshot["fault_latched"], bool)
            and isinstance(snapshot["fault_reason"], str)
            and bool(snapshot["fault_reason"]),
            "snapshot fault state is invalid",
        )
        fault_latched = snapshot["fault_latched"]
        fault_reason = snapshot["fault_reason"]
        _require(
            (not fault_latched and fault_reason == "no-fault")
            or (
                fault_latched
                and fault_reason.startswith("thermal-shutdown:")
                and fault_reason.split(":", 1)[1]
                in self.configuration.actuator_ids
            ),
            "snapshot fault partition is invalid",
        )
        rows = snapshot["actuator_snapshots"]
        _require(
            isinstance(rows, list)
            and all(isinstance(row, Mapping) for row in rows)
            and tuple(row["actuator_id"] for row in rows)
            == self.configuration.actuator_ids,
            "snapshot actuator partition mismatch",
        )
        candidates = self._new_engines(scene_seed=scene_seed)
        for member, row in zip(self.configuration.members, rows):
            _require(
                isinstance(row, Mapping)
                and set(row)
                == {
                    "actuator_id",
                    "plant_configuration_sha256",
                    "derived_seed",
                    "plant_snapshot",
                },
                "snapshot actuator row is not closed",
            )
            _require(
                row["actuator_id"] == member.actuator_id
                and row["plant_configuration_sha256"]
                == member.configuration.configuration_sha256
                and row["derived_seed"]
                == self._derive_seed(member.actuator_id, scene_seed),
                f"{member.actuator_id}: snapshot member identity mismatch",
            )
            try:
                candidates[member.actuator_id].restore(
                    row["plant_snapshot"]
                )
            except actuator_plant_v2.PlantV2Error as error:
                raise MultiActuatorPlantV2Error(
                    f"{member.actuator_id}: snapshot plant rejected: {error}"
                ) from error
            _require(
                candidates[member.actuator_id].state.step_index
                == step_index,
                f"{member.actuator_id}: snapshot step mismatch",
            )
            _require(
                candidates[member.actuator_id].next_command_sequence
                == next_batch_sequence,
                f"{member.actuator_id}: snapshot batch sequence mismatch",
            )

        projection = self._project(
            candidates,
            scene_seed=scene_seed,
            reset_generation=reset_generation,
            step_index=step_index,
            next_batch_sequence=next_batch_sequence,
            fault_latched=fault_latched,
            fault_reason=fault_reason,
        )
        _require(
            _plain(projection) == snapshot["last_step"],
            "snapshot aggregate projection mismatch",
        )
        self._engines = candidates
        self._scene_seed = scene_seed
        self._reset_generation = reset_generation
        self._step_index = step_index
        self._next_batch_sequence = next_batch_sequence
        self._fault_latched = fault_latched
        self._fault_reason = fault_reason
        self._last_step = projection


def deterministic_multi_actuator_trace_sha256(
    configuration: MultiActuatorV2Configuration,
    events: Iterable[
        tuple[
            MultiActuatorV2CommandBatch | None,
            tuple[MultiActuatorV2Load, ...],
        ]
    ],
    *,
    seed: int,
) -> str:
    bank = DeterministicMultiActuatorPlantV2(
        configuration,
        seed=seed,
    )
    digest = hashlib.sha256()
    for batch, loads in events:
        if batch is not None:
            bank.submit(batch)
        step = bank.advance(loads)
        digest.update(
            canonical_json(
                {
                    "batch": _plain(batch),
                    "step": _plain(step),
                }
            )
        )
    return digest.hexdigest()


def clone_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-compatible deep copy for callers and adversarial tests."""

    return copy.deepcopy(dict(snapshot))


__all__ = [
    "COMMAND_ATOMICITY_POLICY",
    "COMMAND_SET_POLICY",
    "DROPBEAR_CANONICAL",
    "EVIDENCE_CLASS",
    "EXACT_MODEL_FIDELITY",
    "FAULT_POLICY",
    "MODELS_RIGID_BODY",
    "MODELS_SHARED_POWER_BUS",
    "MOTION_AUTHORITY",
    "MultiActuatorPlantV2Error",
    "MultiActuatorV2Command",
    "MultiActuatorV2CommandBatch",
    "MultiActuatorV2Configuration",
    "MultiActuatorV2Load",
    "MultiActuatorV2Member",
    "MultiActuatorV2MemberState",
    "MultiActuatorV2Step",
    "PHYSICAL_IO",
    "PHYSICAL_VALIDATION",
    "SCHEMA_VERSION",
    "SEED_DERIVATION",
    "SNAPSHOT_SCHEMA_VERSION",
    "STEP_ATOMICITY_POLICY",
    "SUBSTITUTION_SCOPE",
    "SUPPORT_GRANTED",
    "DeterministicMultiActuatorPlantV2",
    "canonical_json",
    "clone_snapshot",
    "deterministic_multi_actuator_trace_sha256",
]
