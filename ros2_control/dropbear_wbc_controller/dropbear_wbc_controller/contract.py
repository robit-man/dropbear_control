"""Dependency-free JSON contracts for the Dropbear SONIC/WBC boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, Mapping, Tuple


AUTHORITY = "sil_only"
TOKEN_DIMENSION = 64

# This order is shared with rl/dropbear_ppo.py and the browser USD bindings.
# Policy and transport code must not alphabetize or silently reorder it.
CANONICAL_JOINT_ORDER: Tuple[str, ...] = (
    "left_outer_calf",
    "left_inner_calf",
    "right_inner_calf",
    "right_outer_calf",
    "left_knee",
    "left_hip_pitch",
    "right_hip_pitch",
    "right_knee",
    "left_hip_yaw",
    "left_hip_roll",
    "right_hip_roll",
    "right_hip_yaw",
    "left_shoulder_pitch",
    "left_shoulder_yaw",
    "left_shoulder_roll",
    "left_elbow_pitch",
    "left_wrist_roll",
    "right_shoulder_pitch",
    "right_shoulder_yaw",
    "right_shoulder_roll",
    "right_elbow_pitch",
    "right_wrist_roll",
)
JOINT_COUNT = len(CANONICAL_JOINT_ORDER)


class ContractError(ValueError):
    """A frame is malformed or violates the versioned WBC contract."""


@dataclass(frozen=True)
class JointLimit:
    """Conservative software envelope, not a verified physical limit."""

    lower_rad: float
    upper_rad: float
    max_velocity_rad_s: float

    def __post_init__(self) -> None:
        if not all(
            math.isfinite(value)
            for value in (self.lower_rad, self.upper_rad, self.max_velocity_rad_s)
        ):
            raise ContractError("joint limits must be finite")
        if self.lower_rad >= self.upper_rad:
            raise ContractError("joint lower limit must be less than upper limit")
        if self.max_velocity_rad_s <= 0.0:
            raise ContractError("joint velocity limit must be positive")


# These bounds are deliberately conservative integration/SIL envelopes. They
# must be replaced only after a reviewed, revision-specific calibration and
# limit artifact is admitted by the physical hardware safety authority.
JOINT_LIMITS: Dict[str, JointLimit] = {
    "left_outer_calf": JointLimit(-1.20, 1.20, 3.0),
    "left_inner_calf": JointLimit(-1.20, 1.20, 3.0),
    "right_inner_calf": JointLimit(-1.20, 1.20, 3.0),
    "right_outer_calf": JointLimit(-1.20, 1.20, 3.0),
    # Knee motor coordinate: 0 rad is the 180-degree mechanical lock datum.
    "left_knee": JointLimit(0.0, math.pi, 4.0),
    "left_hip_pitch": JointLimit(-1.40, 1.20, 3.0),
    "right_hip_pitch": JointLimit(-1.40, 1.20, 3.0),
    "right_knee": JointLimit(0.0, math.pi, 4.0),
    "left_hip_yaw": JointLimit(-0.65, 0.65, 2.0),
    "left_hip_roll": JointLimit(-0.60, 0.60, 2.0),
    "right_hip_roll": JointLimit(-0.60, 0.60, 2.0),
    "right_hip_yaw": JointLimit(-0.65, 0.65, 2.0),
    "left_shoulder_pitch": JointLimit(-1.80, 1.80, 3.0),
    "left_shoulder_yaw": JointLimit(-1.20, 1.20, 2.5),
    "left_shoulder_roll": JointLimit(-1.40, 1.40, 2.5),
    "left_elbow_pitch": JointLimit(0.0, 2.62, 2.5),
    "left_wrist_roll": JointLimit(-math.pi, math.pi, 4.0),
    "right_shoulder_pitch": JointLimit(-1.80, 1.80, 3.0),
    "right_shoulder_yaw": JointLimit(-1.20, 1.20, 2.5),
    "right_shoulder_roll": JointLimit(-1.40, 1.40, 2.5),
    "right_elbow_pitch": JointLimit(0.0, 2.62, 2.5),
    "right_wrist_roll": JointLimit(-math.pi, math.pi, 4.0),
}

if tuple(JOINT_LIMITS) != CANONICAL_JOINT_ORDER:
    raise RuntimeError("JOINT_LIMITS must preserve the canonical joint order")


_stand = {name: 0.0 for name in CANONICAL_JOINT_ORDER}
_stand.update(
    {
        "left_knee": 0.36,
        "right_knee": 0.36,
        "left_elbow_pitch": 0.42,
        "right_elbow_pitch": 0.42,
    }
)
STAND_POSE: Tuple[float, ...] = tuple(_stand[name] for name in CANONICAL_JOINT_ORDER)


def _mapping(value: Any, field_name: str = "payload") -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{field_name} must be an object")
    return value


def _required_string(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field_name} must be a non-empty string")
    return value


def _nonnegative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{field_name} must be a non-negative integer")
    return value


def _finite_tuple(
    value: Any,
    field_name: str,
    expected: int,
    *,
    allow_empty: bool = False,
) -> Tuple[float, ...]:
    if allow_empty and (value is None or value == () or value == []):
        return ()
    if not isinstance(value, (list, tuple)) or len(value) != expected:
        raise ContractError(f"{field_name} must contain exactly {expected} values")
    result: Tuple[float, ...] = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ContractError(f"{field_name} must contain only finite values")
    return result


def _joint_order(value: Any) -> Tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ContractError("joint_names must be an array")
    result = tuple(value)
    if result != CANONICAL_JOINT_ORDER:
        raise ContractError(
            "joint_names must exactly match the canonical 22-axis Dropbear order"
        )
    return result


def _schema(payload: Mapping[str, Any], expected: str) -> None:
    if payload.get("schema") != expected:
        raise ContractError(f"schema must be {expected!r}")


@dataclass(frozen=True)
class MotionTokenFrame:
    """A SONIC latent token; it never directly authorizes motor output."""

    SCHEMA: ClassVar[str] = "dropbear-sonic-token-v1"

    session_id: str
    sequence: int
    generated_steady_time_ns: int
    token: Tuple[float, ...]
    source: str = "unknown"
    schema: str = field(default=SCHEMA, init=False)

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ContractError("session_id must be non-empty")
        _nonnegative_int(self.sequence, "sequence")
        _nonnegative_int(self.generated_steady_time_ns, "generated_steady_time_ns")
        object.__setattr__(
            self, "token", _finite_tuple(self.token, "token", TOKEN_DIMENSION)
        )
        if not self.source:
            raise ContractError("source must be non-empty")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "generated_steady_time_ns": self.generated_steady_time_ns,
            "token": list(self.token),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MotionTokenFrame":
        payload = _mapping(value)
        _schema(payload, cls.SCHEMA)
        return cls(
            session_id=_required_string(payload, "session_id"),
            sequence=_nonnegative_int(payload.get("sequence"), "sequence"),
            generated_steady_time_ns=_nonnegative_int(
                payload.get("generated_steady_time_ns"),
                "generated_steady_time_ns",
            ),
            token=_finite_tuple(payload.get("token"), "token", TOKEN_DIMENSION),
            source=_required_string(payload, "source"),
        )


@dataclass(frozen=True)
class JointReferenceFrame:
    """A decoded 50 Hz motor-coordinate reference."""

    SCHEMA: ClassVar[str] = "dropbear-wbc-reference-v1"

    session_id: str
    sequence: int
    generated_steady_time_ns: int
    positions: Tuple[float, ...]
    velocities: Tuple[float, ...] = ()
    joint_names: Tuple[str, ...] = CANONICAL_JOINT_ORDER
    source_token_sequence: int | None = None
    schema: str = field(default=SCHEMA, init=False)

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ContractError("session_id must be non-empty")
        _nonnegative_int(self.sequence, "sequence")
        _nonnegative_int(self.generated_steady_time_ns, "generated_steady_time_ns")
        object.__setattr__(self, "joint_names", _joint_order(self.joint_names))
        object.__setattr__(
            self, "positions", _finite_tuple(self.positions, "positions", JOINT_COUNT)
        )
        object.__setattr__(
            self,
            "velocities",
            _finite_tuple(
                self.velocities, "velocities", JOINT_COUNT, allow_empty=True
            ),
        )
        if self.source_token_sequence is not None:
            _nonnegative_int(self.source_token_sequence, "source_token_sequence")

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "schema": self.schema,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "generated_steady_time_ns": self.generated_steady_time_ns,
            "joint_names": list(self.joint_names),
            "positions": list(self.positions),
        }
        if self.velocities:
            result["velocities"] = list(self.velocities)
        if self.source_token_sequence is not None:
            result["source_token_sequence"] = self.source_token_sequence
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "JointReferenceFrame":
        payload = _mapping(value)
        _schema(payload, cls.SCHEMA)
        source_token_sequence = payload.get("source_token_sequence")
        return cls(
            session_id=_required_string(payload, "session_id"),
            sequence=_nonnegative_int(payload.get("sequence"), "sequence"),
            generated_steady_time_ns=_nonnegative_int(
                payload.get("generated_steady_time_ns"),
                "generated_steady_time_ns",
            ),
            joint_names=_joint_order(payload.get("joint_names")),
            positions=_finite_tuple(payload.get("positions"), "positions", JOINT_COUNT),
            velocities=_finite_tuple(
                payload.get("velocities"),
                "velocities",
                JOINT_COUNT,
                allow_empty=True,
            ),
            source_token_sequence=(
                None
                if source_token_sequence is None
                else _nonnegative_int(
                    source_token_sequence, "source_token_sequence"
                )
            ),
        )


@dataclass(frozen=True)
class RobotStateFrame:
    """Robot feedback consumed by the WBC guard."""

    SCHEMA: ClassVar[str] = "dropbear-wbc-state-v1"

    source_id: str
    sequence: int
    observed_steady_time_ns: int
    positions: Tuple[float, ...]
    velocities: Tuple[float, ...]
    base_quaternion_wxyz: Tuple[float, ...] = (1.0, 0.0, 0.0, 0.0)
    base_angular_velocity_rad_s: Tuple[float, ...] = (0.0, 0.0, 0.0)
    foot_force_n: Tuple[float, ...] = (0.0, 0.0)
    fault_codes: Tuple[str, ...] = ()
    estop: bool = False
    joint_names: Tuple[str, ...] = CANONICAL_JOINT_ORDER
    schema: str = field(default=SCHEMA, init=False)

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ContractError("source_id must be non-empty")
        _nonnegative_int(self.sequence, "sequence")
        _nonnegative_int(self.observed_steady_time_ns, "observed_steady_time_ns")
        object.__setattr__(self, "joint_names", _joint_order(self.joint_names))
        object.__setattr__(
            self, "positions", _finite_tuple(self.positions, "positions", JOINT_COUNT)
        )
        object.__setattr__(
            self, "velocities", _finite_tuple(self.velocities, "velocities", JOINT_COUNT)
        )
        quaternion = _finite_tuple(
            self.base_quaternion_wxyz, "base_quaternion_wxyz", 4
        )
        norm = math.sqrt(sum(component * component for component in quaternion))
        if norm < 0.5 or norm > 1.5:
            raise ContractError("base quaternion norm is outside the 0.5…1.5 guard")
        object.__setattr__(self, "base_quaternion_wxyz", quaternion)
        object.__setattr__(
            self,
            "base_angular_velocity_rad_s",
            _finite_tuple(
                self.base_angular_velocity_rad_s,
                "base_angular_velocity_rad_s",
                3,
            ),
        )
        forces = _finite_tuple(self.foot_force_n, "foot_force_n", 2)
        if any(force < 0.0 for force in forces):
            raise ContractError("foot_force_n cannot contain negative values")
        object.__setattr__(self, "foot_force_n", forces)
        if not isinstance(self.estop, bool):
            raise ContractError("estop must be a boolean")
        if not isinstance(self.fault_codes, (list, tuple)) or not all(
            isinstance(code, str) and code for code in self.fault_codes
        ):
            raise ContractError("fault_codes must contain non-empty strings")
        object.__setattr__(self, "fault_codes", tuple(self.fault_codes))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "source_id": self.source_id,
            "sequence": self.sequence,
            "observed_steady_time_ns": self.observed_steady_time_ns,
            "joint_names": list(self.joint_names),
            "positions": list(self.positions),
            "velocities": list(self.velocities),
            "base_quaternion_wxyz": list(self.base_quaternion_wxyz),
            "base_angular_velocity_rad_s": list(
                self.base_angular_velocity_rad_s
            ),
            "foot_force_n": list(self.foot_force_n),
            "fault_codes": list(self.fault_codes),
            "estop": self.estop,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RobotStateFrame":
        payload = _mapping(value)
        _schema(payload, cls.SCHEMA)
        return cls(
            source_id=_required_string(payload, "source_id"),
            sequence=_nonnegative_int(payload.get("sequence"), "sequence"),
            observed_steady_time_ns=_nonnegative_int(
                payload.get("observed_steady_time_ns"),
                "observed_steady_time_ns",
            ),
            joint_names=_joint_order(payload.get("joint_names")),
            positions=_finite_tuple(payload.get("positions"), "positions", JOINT_COUNT),
            velocities=_finite_tuple(
                payload.get("velocities"), "velocities", JOINT_COUNT
            ),
            base_quaternion_wxyz=_finite_tuple(
                payload.get("base_quaternion_wxyz"),
                "base_quaternion_wxyz",
                4,
            ),
            base_angular_velocity_rad_s=_finite_tuple(
                payload.get("base_angular_velocity_rad_s"),
                "base_angular_velocity_rad_s",
                3,
            ),
            foot_force_n=_finite_tuple(
                payload.get("foot_force_n"), "foot_force_n", 2
            ),
            fault_codes=tuple(payload.get("fault_codes", ())),
            estop=payload.get("estop", False),
        )


@dataclass(frozen=True)
class ActivationRequest:
    """Explicit guarded request to enter the SIL command state machine."""

    SCHEMA: ClassVar[str] = "dropbear-wbc-activation-v1"
    CONFIRMATION: ClassVar[str] = "DROPBEAR_WBC_SIL_GUARDED"

    session_id: str
    sequence: int
    issued_steady_time_ns: int
    guarded_confirmation: str
    authority: str = AUTHORITY
    schema: str = field(default=SCHEMA, init=False)

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ContractError("session_id must be non-empty")
        _nonnegative_int(self.sequence, "sequence")
        _nonnegative_int(self.issued_steady_time_ns, "issued_steady_time_ns")
        if self.guarded_confirmation != self.CONFIRMATION:
            raise ContractError("guarded activation confirmation does not match")
        if self.authority != AUTHORITY:
            raise ContractError(
                f"this package only admits authority={AUTHORITY!r}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "issued_steady_time_ns": self.issued_steady_time_ns,
            "guarded_confirmation": self.guarded_confirmation,
            "authority": self.authority,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ActivationRequest":
        payload = _mapping(value)
        _schema(payload, cls.SCHEMA)
        return cls(
            session_id=_required_string(payload, "session_id"),
            sequence=_nonnegative_int(payload.get("sequence"), "sequence"),
            issued_steady_time_ns=_nonnegative_int(
                payload.get("issued_steady_time_ns"), "issued_steady_time_ns"
            ),
            guarded_confirmation=_required_string(
                payload, "guarded_confirmation"
            ),
            authority=_required_string(payload, "authority"),
        )


@dataclass(frozen=True)
class SafeJointCommand:
    """Guard output; ``command_enabled`` is SIL routing, not hardware authority."""

    SCHEMA: ClassVar[str] = "dropbear-wbc-safe-command-v1"

    output_sequence: int
    computed_steady_time_ns: int
    positions: Tuple[float, ...]
    velocities: Tuple[float, ...]
    mode: str
    command_enabled: bool
    reason: str
    session_id: str | None = None
    source_reference_sequence: int | None = None
    clamped_joints: Tuple[str, ...] = ()
    joint_names: Tuple[str, ...] = CANONICAL_JOINT_ORDER
    authority: str = AUTHORITY
    schema: str = field(default=SCHEMA, init=False)

    def __post_init__(self) -> None:
        _nonnegative_int(self.output_sequence, "output_sequence")
        _nonnegative_int(self.computed_steady_time_ns, "computed_steady_time_ns")
        object.__setattr__(self, "joint_names", _joint_order(self.joint_names))
        object.__setattr__(
            self, "positions", _finite_tuple(self.positions, "positions", JOINT_COUNT)
        )
        object.__setattr__(
            self, "velocities", _finite_tuple(self.velocities, "velocities", JOINT_COUNT)
        )
        if not self.mode or not self.reason:
            raise ContractError("mode and reason must be non-empty")
        if self.authority != AUTHORITY:
            raise ContractError("safe command cannot claim hardware authority")
        if not isinstance(self.command_enabled, bool):
            raise ContractError("command_enabled must be a boolean")
        if self.source_reference_sequence is not None:
            _nonnegative_int(
                self.source_reference_sequence, "source_reference_sequence"
            )
        unknown = set(self.clamped_joints) - set(CANONICAL_JOINT_ORDER)
        if unknown:
            raise ContractError(f"unknown clamped joints: {sorted(unknown)!r}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "authority": self.authority,
            "output_sequence": self.output_sequence,
            "computed_steady_time_ns": self.computed_steady_time_ns,
            "joint_names": list(self.joint_names),
            "positions": list(self.positions),
            "velocities": list(self.velocities),
            "mode": self.mode,
            "command_enabled": self.command_enabled,
            "reason": self.reason,
            "session_id": self.session_id,
            "source_reference_sequence": self.source_reference_sequence,
            "clamped_joints": list(self.clamped_joints),
        }
