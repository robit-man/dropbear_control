"""Host reference for the allocation-free native joint-observation core.

The types and denial ordering intentionally mirror
``firmware/esp32/src/runtime/joint_observation_core``.  This is deterministic
SIL/reference behavior only; it performs no I/O and grants no motion authority.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum


class ObservationSourceKind(IntEnum):
    EXTERNAL_ABSOLUTE = 1
    EXTERNAL_INCREMENTAL = 2
    NATIVE_MOTOR = 3
    NATIVE_OUTPUT = 4
    SYNTHETIC_PLANT = 5


class RawObservationUnit(IntEnum):
    COUNT = 1
    VOLT = 2
    RADIAN = 3
    DEGREE = 4


class CalibrationEvidenceClass(IntEnum):
    SYNTHETIC_FIXTURE = 1
    PHYSICAL_BENCH = 2


class WrapInterval(IntEnum):
    NONE = 0
    ZERO_TO_PERIOD = 1
    CENTERED = 2


class ObservationCode(IntEnum):
    OK = 0
    NULL_OUTPUT = 1
    CALIBRATION_INVALID = 2
    SAMPLE_INVALID = 3
    IDENTITY_MISMATCH = 4
    SOURCE_KIND_MISMATCH = 5
    UNIT_MISMATCH = 6
    EVIDENCE_CLASS_MISMATCH = 7
    CALIBRATION_NOT_YET_VALID = 8
    CALIBRATION_EXPIRED = 9
    SAMPLE_TIME_FUTURE = 10
    RECEIVE_TIME_FUTURE = 11
    TIME_ORDER_INVALID = 12
    SAMPLE_STALE = 13
    RECEIVE_STALE = 14
    SOURCE_FAULT = 15
    SOURCE_QUALITY_INVALID = 16
    SAMPLE_OUTSIDE_CALIBRATION_VALIDITY = 17
    SEQUENCE_REPLAY = 18
    SAMPLE_TIME_REGRESSION = 19
    RECEIVE_TIME_REGRESSION = 20
    CALIBRATION_GENERATION_REGRESSION = 21
    CONVERSION_NONFINITE = 22


@dataclass(frozen=True)
class ConfigIdentity:
    identity: str
    revision: str
    sha256: str


@dataclass(frozen=True)
class CalibrationSnapshot:
    record_id: str
    canonical_joint_name: str
    actuator_id: str
    sensor_id: str
    configuration: ConfigIdentity
    subject_digest: str
    record_digest: str
    generation: int
    valid_from_ns: int
    valid_until_ns: int
    evidence_class: CalibrationEvidenceClass
    source_kind: ObservationSourceKind
    raw_unit: RawObservationUnit
    raw_zero: float
    joint_zero_rad: float
    native_output_zero_rad: float
    raw_to_joint_scale_rad_per_unit: float
    motor_to_joint_sign: int
    output_per_motor_ratio: float
    wrap_enabled: bool
    raw_period: float
    canonical_period_rad: float
    wrap_interval: WrapInterval


@dataclass(frozen=True)
class RawJointObservation:
    canonical_joint_name: str
    actuator_id: str
    sensor_id: str
    configuration: ConfigIdentity
    source_kind: ObservationSourceKind
    raw_unit: RawObservationUnit
    sequence: int
    sample_time_ns: int
    receive_time_ns: int
    raw_value: float
    source_fault: bool
    quality_valid: bool


@dataclass(frozen=True)
class ObservationPolicy:
    maximum_sample_age_ns: int
    maximum_receive_age_ns: int
    required_evidence_class: CalibrationEvidenceClass


@dataclass(frozen=True)
class ConvertedJointObservation:
    canonical_joint_name: str
    actuator_id: str
    sensor_id: str
    configuration: ConfigIdentity
    calibration_record_id: str
    source_kind: ObservationSourceKind
    evidence_class: CalibrationEvidenceClass
    calibration_generation: int
    sequence: int
    sample_time_ns: int
    receive_time_ns: int
    sample_age_ns: int
    receive_age_ns: int
    joint_position_rad: float


@dataclass(frozen=True)
class ConversionResult:
    code: ObservationCode
    observation: ConvertedJointObservation | None


def _text_valid(value: str) -> bool:
    try:
        encoded = value.encode("utf-8")
    except (AttributeError, UnicodeError):
        return False
    return 0 < len(encoded) <= 255


def _digest_valid(value: str) -> bool:
    return len(value) == 64 and value != "0" * 64 and all(c in "0123456789abcdef" for c in value)


def _config_valid(value: ConfigIdentity) -> bool:
    return _text_valid(value.identity) and _text_valid(value.revision) and _digest_valid(value.sha256)


def validate_calibration(value: CalibrationSnapshot) -> ObservationCode:
    numeric = (
        value.raw_zero,
        value.joint_zero_rad,
        value.native_output_zero_rad,
        value.raw_to_joint_scale_rad_per_unit,
        value.output_per_motor_ratio,
    )
    if (
        not all(_text_valid(item) for item in (value.record_id, value.canonical_joint_name, value.actuator_id, value.sensor_id))
        or not _config_valid(value.configuration)
        or not _digest_valid(value.subject_digest)
        or not _digest_valid(value.record_digest)
        or value.generation <= 0
        or value.valid_until_ns <= value.valid_from_ns
        or not isinstance(value.evidence_class, CalibrationEvidenceClass)
        or not isinstance(value.source_kind, ObservationSourceKind)
        or not isinstance(value.raw_unit, RawObservationUnit)
        or not all(math.isfinite(item) for item in numeric)
        or value.raw_to_joint_scale_rad_per_unit == 0.0
        or value.motor_to_joint_sign not in (-1, 1)
        or value.output_per_motor_ratio <= 0.0
    ):
        return ObservationCode.CALIBRATION_INVALID
    if value.wrap_enabled:
        if (
            not math.isfinite(value.raw_period)
            or value.raw_period <= 0.0
            or not math.isfinite(value.canonical_period_rad)
            or value.canonical_period_rad <= 0.0
            or value.wrap_interval not in (WrapInterval.ZERO_TO_PERIOD, WrapInterval.CENTERED)
            or abs(abs(value.raw_to_joint_scale_rad_per_unit) * value.raw_period - value.canonical_period_rad) > 1e-9
        ):
            return ObservationCode.CALIBRATION_INVALID
    elif value.wrap_interval != WrapInterval.NONE or value.raw_period != 0.0 or value.canonical_period_rad != 0.0:
        return ObservationCode.CALIBRATION_INVALID
    return ObservationCode.OK


def convert_joint_observation(
    calibration: CalibrationSnapshot,
    sample: RawJointObservation,
    policy: ObservationPolicy,
    now_ns: int,
) -> ConversionResult:
    if validate_calibration(calibration) != ObservationCode.OK:
        return ConversionResult(ObservationCode.CALIBRATION_INVALID, None)
    if (
        not all(_text_valid(item) for item in (sample.canonical_joint_name, sample.actuator_id, sample.sensor_id))
        or not _config_valid(sample.configuration)
        or not isinstance(sample.source_kind, ObservationSourceKind)
        or not isinstance(sample.raw_unit, RawObservationUnit)
        or sample.sequence <= 0
        or not math.isfinite(sample.raw_value)
        or policy.maximum_sample_age_ns <= 0
        or policy.maximum_receive_age_ns <= 0
        or not isinstance(policy.required_evidence_class, CalibrationEvidenceClass)
    ):
        return ConversionResult(ObservationCode.SAMPLE_INVALID, None)
    if (
        calibration.canonical_joint_name != sample.canonical_joint_name
        or calibration.actuator_id != sample.actuator_id
        or calibration.sensor_id != sample.sensor_id
        or calibration.configuration != sample.configuration
    ):
        return ConversionResult(ObservationCode.IDENTITY_MISMATCH, None)
    if calibration.source_kind != sample.source_kind:
        return ConversionResult(ObservationCode.SOURCE_KIND_MISMATCH, None)
    if calibration.raw_unit != sample.raw_unit:
        return ConversionResult(ObservationCode.UNIT_MISMATCH, None)
    if calibration.evidence_class != policy.required_evidence_class:
        return ConversionResult(ObservationCode.EVIDENCE_CLASS_MISMATCH, None)
    if now_ns < calibration.valid_from_ns:
        return ConversionResult(ObservationCode.CALIBRATION_NOT_YET_VALID, None)
    if now_ns > calibration.valid_until_ns:
        return ConversionResult(ObservationCode.CALIBRATION_EXPIRED, None)
    if sample.sample_time_ns > now_ns:
        return ConversionResult(ObservationCode.SAMPLE_TIME_FUTURE, None)
    if sample.receive_time_ns > now_ns:
        return ConversionResult(ObservationCode.RECEIVE_TIME_FUTURE, None)
    if sample.receive_time_ns < sample.sample_time_ns:
        return ConversionResult(ObservationCode.TIME_ORDER_INVALID, None)
    if not calibration.valid_from_ns <= sample.sample_time_ns <= calibration.valid_until_ns:
        return ConversionResult(ObservationCode.SAMPLE_OUTSIDE_CALIBRATION_VALIDITY, None)
    sample_age = now_ns - sample.sample_time_ns
    receive_age = now_ns - sample.receive_time_ns
    if sample_age > policy.maximum_sample_age_ns:
        return ConversionResult(ObservationCode.SAMPLE_STALE, None)
    if receive_age > policy.maximum_receive_age_ns:
        return ConversionResult(ObservationCode.RECEIVE_STALE, None)
    if sample.source_fault:
        return ConversionResult(ObservationCode.SOURCE_FAULT, None)
    if not sample.quality_valid:
        return ConversionResult(ObservationCode.SOURCE_QUALITY_INVALID, None)

    if sample.source_kind == ObservationSourceKind.NATIVE_MOTOR:
        delta = sample.raw_value - calibration.native_output_zero_rad
        position = calibration.joint_zero_rad + calibration.motor_to_joint_sign * calibration.output_per_motor_ratio * delta
    elif sample.source_kind == ObservationSourceKind.NATIVE_OUTPUT:
        delta = sample.raw_value - calibration.native_output_zero_rad
        position = calibration.joint_zero_rad + calibration.motor_to_joint_sign * delta
    else:
        delta = sample.raw_value - calibration.raw_zero
        if calibration.wrap_enabled:
            delta = math.fmod(delta, calibration.raw_period)
            if delta < 0.0:
                delta += calibration.raw_period
            if calibration.wrap_interval == WrapInterval.CENTERED and delta > calibration.raw_period * 0.5:
                delta -= calibration.raw_period
        position = calibration.joint_zero_rad + calibration.motor_to_joint_sign * calibration.raw_to_joint_scale_rad_per_unit * delta
    if not math.isfinite(position):
        return ConversionResult(ObservationCode.CONVERSION_NONFINITE, None)
    return ConversionResult(
        ObservationCode.OK,
        ConvertedJointObservation(
            sample.canonical_joint_name,
            sample.actuator_id,
            sample.sensor_id,
            sample.configuration,
            calibration.record_id,
            sample.source_kind,
            calibration.evidence_class,
            calibration.generation,
            sample.sequence,
            sample.sample_time_ns,
            sample.receive_time_ns,
            sample_age,
            receive_age,
            position,
        ),
    )


class ObservationStreamGuard:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._last: ConvertedJointObservation | None = None

    @property
    def initialized(self) -> bool:
        return self._last is not None

    def convert(self, calibration: CalibrationSnapshot, sample: RawJointObservation, policy: ObservationPolicy, now_ns: int) -> ConversionResult:
        result = convert_joint_observation(calibration, sample, policy, now_ns)
        if result.code != ObservationCode.OK:
            return result
        assert result.observation is not None
        candidate = result.observation
        previous = self._last
        if previous is not None:
            if (candidate.canonical_joint_name, candidate.actuator_id, candidate.sensor_id, candidate.configuration) != (
                previous.canonical_joint_name, previous.actuator_id, previous.sensor_id, previous.configuration
            ):
                return ConversionResult(ObservationCode.IDENTITY_MISMATCH, None)
            if candidate.calibration_generation < previous.calibration_generation:
                return ConversionResult(ObservationCode.CALIBRATION_GENERATION_REGRESSION, None)
            if candidate.sequence <= previous.sequence:
                return ConversionResult(ObservationCode.SEQUENCE_REPLAY, None)
            if candidate.sample_time_ns < previous.sample_time_ns:
                return ConversionResult(ObservationCode.SAMPLE_TIME_REGRESSION, None)
            if candidate.receive_time_ns < previous.receive_time_ns:
                return ConversionResult(ObservationCode.RECEIVE_TIME_REGRESSION, None)
        self._last = candidate
        return result


class ReconciliationMode(IntEnum):
    EXTERNAL_ONLY = 1
    NATIVE_ONLY = 2
    REQUIRE_BOTH_PREFER_EXTERNAL = 3
    REQUIRE_BOTH_PREFER_NATIVE = 4


class ReconciliationCode(IntEnum):
    OK = 0
    NULL_OUTPUT = 1
    POLICY_INVALID = 2
    EXTERNAL_REQUIRED = 3
    NATIVE_REQUIRED = 4
    OBSERVATION_IDENTITY_MISMATCH = 5
    EVIDENCE_CLASS_MISMATCH = 6
    SENSOR_ALIAS_FORBIDDEN = 7
    DISAGREEMENT_EXCEEDED = 8


@dataclass(frozen=True)
class ReconciliationPolicy:
    canonical_joint_name: str
    actuator_id: str
    external_sensor_id: str
    native_sensor_id: str
    configuration: ConfigIdentity
    generation: int
    mode: ReconciliationMode
    required_evidence_class: CalibrationEvidenceClass
    maximum_disagreement_rad: float


@dataclass(frozen=True)
class ReconciledJointObservation:
    canonical_joint_name: str
    actuator_id: str
    configuration: ConfigIdentity
    policy_generation: int
    mode: ReconciliationMode
    selected_source_kind: ObservationSourceKind
    selected_sensor_id: str
    selected_sample_time_ns: int
    joint_position_rad: float
    external_present: bool
    native_present: bool
    external_position_rad: float
    native_position_rad: float
    disagreement_rad: float


@dataclass(frozen=True)
class ReconciliationResult:
    code: ReconciliationCode
    observation: ReconciledJointObservation | None


def reconcile_joint_observations(policy: ReconciliationPolicy, external: ConvertedJointObservation | None, native: ConvertedJointObservation | None) -> ReconciliationResult:
    if (
        not all(_text_valid(item) for item in (policy.canonical_joint_name, policy.actuator_id, policy.external_sensor_id, policy.native_sensor_id))
        or not _config_valid(policy.configuration)
        or policy.generation <= 0
        or not isinstance(policy.mode, ReconciliationMode)
        or not isinstance(policy.required_evidence_class, CalibrationEvidenceClass)
        or not math.isfinite(policy.maximum_disagreement_rad)
        or policy.maximum_disagreement_rad < 0.0
    ):
        return ReconciliationResult(ReconciliationCode.POLICY_INVALID, None)
    if policy.external_sensor_id == policy.native_sensor_id:
        return ReconciliationResult(ReconciliationCode.SENSOR_ALIAS_FORBIDDEN, None)
    need_external = policy.mode != ReconciliationMode.NATIVE_ONLY
    need_native = policy.mode != ReconciliationMode.EXTERNAL_ONLY
    if need_external and external is None:
        return ReconciliationResult(ReconciliationCode.EXTERNAL_REQUIRED, None)
    if need_native and native is None:
        return ReconciliationResult(ReconciliationCode.NATIVE_REQUIRED, None)
    for value, sensor in ((external, policy.external_sensor_id), (native, policy.native_sensor_id)):
        if value is not None and (value.canonical_joint_name, value.actuator_id, value.sensor_id, value.configuration) != (
            policy.canonical_joint_name, policy.actuator_id, sensor, policy.configuration
        ):
            return ReconciliationResult(ReconciliationCode.OBSERVATION_IDENTITY_MISMATCH, None)
        if value is not None and value.evidence_class != policy.required_evidence_class:
            return ReconciliationResult(ReconciliationCode.EVIDENCE_CLASS_MISMATCH, None)
    disagreement = 0.0
    if external is not None and native is not None:
        disagreement = abs(external.joint_position_rad - native.joint_position_rad)
        if not math.isfinite(disagreement) or disagreement > policy.maximum_disagreement_rad:
            return ReconciliationResult(ReconciliationCode.DISAGREEMENT_EXCEEDED, None)
    selected = native if policy.mode in (ReconciliationMode.NATIVE_ONLY, ReconciliationMode.REQUIRE_BOTH_PREFER_NATIVE) else external
    assert selected is not None
    return ReconciliationResult(
        ReconciliationCode.OK,
        ReconciledJointObservation(
            policy.canonical_joint_name, policy.actuator_id, policy.configuration,
            policy.generation, policy.mode, selected.source_kind, selected.sensor_id,
            selected.sample_time_ns, selected.joint_position_rad,
            external is not None, native is not None,
            external.joint_position_rad if external else 0.0,
            native.joint_position_rad if native else 0.0, disagreement,
        ),
    )


class PositionLimitCode(IntEnum):
    OK = 0
    SNAPSHOT_INVALID = 1
    OBSERVATION_IDENTITY_MISMATCH = 2
    NOT_YET_VALID = 3
    EXPIRED = 4
    BELOW_LOWER = 5
    ABOVE_UPPER = 6


@dataclass(frozen=True)
class PositionLimitSnapshot:
    canonical_joint_name: str
    actuator_id: str
    configuration: ConfigIdentity
    provenance_digest: str
    generation: int
    valid_from_ns: int
    valid_until_ns: int
    has_lower: bool
    has_upper: bool
    lower_rad: float
    upper_rad: float


def check_position_limit(limit: PositionLimitSnapshot, observation: ReconciledJointObservation, now_ns: int) -> PositionLimitCode:
    if (
        not _text_valid(limit.canonical_joint_name)
        or not _text_valid(limit.actuator_id)
        or not _config_valid(limit.configuration)
        or not _digest_valid(limit.provenance_digest)
        or limit.generation <= 0
        or limit.valid_until_ns <= limit.valid_from_ns
        or not (limit.has_lower or limit.has_upper)
        or (limit.has_lower and not math.isfinite(limit.lower_rad))
        or (limit.has_upper and not math.isfinite(limit.upper_rad))
        or (limit.has_lower and limit.has_upper and limit.lower_rad > limit.upper_rad)
    ):
        return PositionLimitCode.SNAPSHOT_INVALID
    if (
        limit.canonical_joint_name != observation.canonical_joint_name
        or limit.actuator_id != observation.actuator_id
        or limit.configuration != observation.configuration
        or not math.isfinite(observation.joint_position_rad)
    ):
        return PositionLimitCode.OBSERVATION_IDENTITY_MISMATCH
    if now_ns < limit.valid_from_ns:
        return PositionLimitCode.NOT_YET_VALID
    if now_ns > limit.valid_until_ns:
        return PositionLimitCode.EXPIRED
    if limit.has_lower and observation.joint_position_rad < limit.lower_rad:
        return PositionLimitCode.BELOW_LOWER
    if limit.has_upper and observation.joint_position_rad > limit.upper_rad:
        return PositionLimitCode.ABOVE_UPPER
    return PositionLimitCode.OK


__all__ = [name for name in globals() if not name.startswith("_")]
