"""Fail-closed applicability and evidence registry for MYACTUATOR systems.

Protocol documentation and a vendor catalog are not proof that a command is
safe on a particular drive.  This module keeps those facts separate from an
exact, evidence-backed support tuple.  It intentionally performs no family,
model-name, firmware-version, transport, or control-mode inference.

The registry is policy only: it does not open a transport or command hardware.
Callers must still pass an allowed decision through the independent runtime
safety supervisor before any powered action.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, IntEnum
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple, Union


class SupportRegistryError(ValueError):
    """Base class for registry validation and collision failures."""


class ValidationError(SupportRegistryError):
    """Registry input is ambiguous, incomplete, or internally inconsistent."""


class DuplicateRecordError(SupportRegistryError):
    """An identical record or catalog identity was inserted twice."""


class ConflictingRecordError(SupportRegistryError):
    """A key was reused for a record with different evidence."""


class EvidenceLevel(IntEnum):
    """Explicit evidence stages; comparison never changes a record's stage."""

    CATALOGED = 0
    OFFLINE = 1
    SIL = 2
    BENCH = 3
    HIL = 4
    ROBOT_RELEASE = 5


HARDWARE_EVIDENCE_LEVELS = frozenset(
    {EvidenceLevel.BENCH, EvidenceLevel.HIL, EvidenceLevel.ROBOT_RELEASE}
)


_FORBIDDEN_EXACT_VALUES = frozenset(
    {
        "*",
        "any",
        "all",
        "current",
        "default",
        "latest",
        "n/a",
        "na",
        "none",
        "null",
        "tbd",
        "unknown",
        "unspecified",
        "x",
    }
)
_WILDCARD_CHARACTERS = frozenset("*?[]{}")
_VERSION_X_SEGMENT = re.compile(r"(?:^|[.\-_/])x(?:$|[.\-_/])", re.IGNORECASE)
_NONEXACT_SEGMENT = re.compile(
    r"(?:^|[.\-_/])(?:all|any|current|default|latest|none|null|tbd|unknown|unspecified)"
    r"(?:$|[.\-_/])",
    re.IGNORECASE,
)
_VERSION_RANGE_PREFIX = re.compile(r"^(?:[<>=~^]|\|\|)")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label} must be a non-empty string")
    if value != value.strip():
        raise ValidationError(f"{label} must not contain leading/trailing whitespace")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValidationError(f"{label} must not contain control characters")
    return value


def _require_exact_component(
    value: object,
    label: str,
    *,
    reject_x_version: bool = False,
) -> str:
    text = _require_text(value, label)
    folded = text.casefold()
    if folded in _FORBIDDEN_EXACT_VALUES:
        raise ValidationError(f"{label} must be exact; {text!r} is not an exact value")
    if any(character in _WILDCARD_CHARACTERS for character in text):
        raise ValidationError(f"{label} must not contain wildcard syntax: {text!r}")
    if _NONEXACT_SEGMENT.search(text):
        raise ValidationError(f"{label} must not contain a non-exact segment: {text!r}")
    if reject_x_version and _VERSION_X_SEGMENT.search(text):
        raise ValidationError(f"{label} must not contain an x-version wildcard: {text!r}")
    if reject_x_version and (_VERSION_RANGE_PREFIX.search(text) or "||" in text):
        raise ValidationError(f"{label} must not contain a version range: {text!r}")
    return text


def _require_identifier(value: object, label: str) -> str:
    text = _require_text(value, label)
    if text.casefold() in _FORBIDDEN_EXACT_VALUES:
        raise ValidationError(f"{label} must identify concrete evidence")
    return text


def _require_unique_text_tuple(values: object, label: str) -> Tuple[str, ...]:
    if isinstance(values, str) or not isinstance(values, tuple):
        raise ValidationError(f"{label} must be a tuple of identifiers")
    checked = tuple(_require_identifier(value, f"{label} item") for value in values)
    if not checked:
        raise ValidationError(f"{label} must not be empty")
    if len(set(checked)) != len(checked):
        raise ValidationError(f"{label} must not contain duplicates")
    return checked


def _require_utc(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValidationError(f"{label} must be a timezone-aware UTC datetime")
    if value.utcoffset() != timedelta(0):
        raise ValidationError(f"{label} must be expressed in UTC")
    return value.astimezone(timezone.utc)


def _require_level(value: object, label: str) -> EvidenceLevel:
    if not isinstance(value, EvidenceLevel):
        raise ValidationError(f"{label} must be an EvidenceLevel")
    return value


def _require_hash_tuple(values: object, label: str) -> Tuple["ArtifactHash", ...]:
    if not isinstance(values, tuple):
        raise ValidationError(f"{label} must be a tuple of ArtifactHash values")
    if not values:
        raise ValidationError(f"{label} must not be empty")
    for item in values:
        if not isinstance(item, ArtifactHash):
            raise ValidationError(f"{label} must contain only ArtifactHash values")
    names = tuple(item.artifact_id for item in values)
    if len(set(names)) != len(names):
        raise ValidationError(f"{label} must not repeat an artifact_id")
    return values


def _validate_window(
    valid_from_utc: object,
    stale_after_utc: object,
    valid_until_utc: object,
    label: str,
) -> Tuple[datetime, datetime, datetime]:
    valid_from = _require_utc(valid_from_utc, f"{label}.valid_from_utc")
    stale_after = _require_utc(stale_after_utc, f"{label}.stale_after_utc")
    valid_until = _require_utc(valid_until_utc, f"{label}.valid_until_utc")
    if stale_after < valid_from:
        raise ValidationError(f"{label}.stale_after_utc precedes valid_from_utc")
    if valid_until < stale_after:
        raise ValidationError(f"{label}.valid_until_utc precedes stale_after_utc")
    return valid_from, stale_after, valid_until


@dataclass(frozen=True)
class SupportKey:
    """The indivisible applicability key; every field participates in equality."""

    model: str
    hardware_revision: str
    drive_firmware: str
    protocol_version: str
    transport: str
    control_mode: str

    def __post_init__(self) -> None:
        for name in (
            "model",
            "hardware_revision",
            "drive_firmware",
            "protocol_version",
            "transport",
            "control_mode",
        ):
            object.__setattr__(
                self,
                name,
                _require_exact_component(
                    getattr(self, name),
                    f"SupportKey.{name}",
                    reject_x_version=name
                    in {"hardware_revision", "drive_firmware", "protocol_version"},
                ),
            )


@dataclass(frozen=True)
class ArtifactHash:
    """A named, immutable SHA-256 input to a support claim."""

    artifact_id: str
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "artifact_id", _require_identifier(self.artifact_id, "artifact_id")
        )
        if not isinstance(self.sha256, str) or not _SHA256.fullmatch(self.sha256):
            raise ValidationError("sha256 must contain exactly 64 hexadecimal characters")
        object.__setattr__(self, "sha256", self.sha256.lower())


@dataclass(frozen=True)
class DependencyEvidence:
    """Evidence for a declared dependency of one exact support claim."""

    dependency_id: str
    evidence_level: EvidenceLevel
    required_level: EvidenceLevel
    source_ids: Tuple[str, ...]
    evidence_ids: Tuple[str, ...]
    valid_from_utc: datetime
    stale_after_utc: datetime
    valid_until_utc: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dependency_id",
            _require_identifier(self.dependency_id, "dependency_id"),
        )
        object.__setattr__(
            self,
            "evidence_level",
            _require_level(self.evidence_level, "DependencyEvidence.evidence_level"),
        )
        object.__setattr__(
            self,
            "required_level",
            _require_level(self.required_level, "DependencyEvidence.required_level"),
        )
        object.__setattr__(
            self,
            "source_ids",
            _require_unique_text_tuple(self.source_ids, "DependencyEvidence.source_ids"),
        )
        object.__setattr__(
            self,
            "evidence_ids",
            _require_unique_text_tuple(self.evidence_ids, "DependencyEvidence.evidence_ids"),
        )
        start, stale, end = _validate_window(
            self.valid_from_utc,
            self.stale_after_utc,
            self.valid_until_utc,
            "DependencyEvidence",
        )
        object.__setattr__(self, "valid_from_utc", start)
        object.__setattr__(self, "stale_after_utc", stale)
        object.__setattr__(self, "valid_until_utc", end)


@dataclass(frozen=True)
class SupportRecord:
    """An explicit support claim; the registry never promotes its level."""

    key: SupportKey
    evidence_level: EvidenceLevel
    source_ids: Tuple[str, ...]
    evidence_ids: Tuple[str, ...]
    code_hashes: Tuple[ArtifactHash, ...]
    config_hashes: Tuple[ArtifactHash, ...]
    valid_from_utc: datetime
    stale_after_utc: datetime
    valid_until_utc: datetime
    capabilities: frozenset[str]
    dependency_evidence: Tuple[DependencyEvidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.key, SupportKey):
            raise ValidationError("SupportRecord.key must be a SupportKey")
        object.__setattr__(
            self,
            "evidence_level",
            _require_level(self.evidence_level, "SupportRecord.evidence_level"),
        )
        object.__setattr__(
            self,
            "source_ids",
            _require_unique_text_tuple(self.source_ids, "SupportRecord.source_ids"),
        )
        object.__setattr__(
            self,
            "evidence_ids",
            _require_unique_text_tuple(self.evidence_ids, "SupportRecord.evidence_ids"),
        )
        object.__setattr__(
            self,
            "code_hashes",
            _require_hash_tuple(self.code_hashes, "SupportRecord.code_hashes"),
        )
        object.__setattr__(
            self,
            "config_hashes",
            _require_hash_tuple(self.config_hashes, "SupportRecord.config_hashes"),
        )
        start, stale, end = _validate_window(
            self.valid_from_utc,
            self.stale_after_utc,
            self.valid_until_utc,
            "SupportRecord",
        )
        object.__setattr__(self, "valid_from_utc", start)
        object.__setattr__(self, "stale_after_utc", stale)
        object.__setattr__(self, "valid_until_utc", end)
        if not isinstance(self.capabilities, frozenset) or not self.capabilities:
            raise ValidationError("SupportRecord.capabilities must be a non-empty frozenset")
        checked_capabilities = frozenset(
            _require_exact_component(item, "SupportRecord capability")
            for item in self.capabilities
        )
        object.__setattr__(self, "capabilities", checked_capabilities)
        if not isinstance(self.dependency_evidence, tuple):
            raise ValidationError("SupportRecord.dependency_evidence must be a tuple")
        for dependency in self.dependency_evidence:
            if not isinstance(dependency, DependencyEvidence):
                raise ValidationError(
                    "SupportRecord.dependency_evidence must contain DependencyEvidence values"
                )
        dependency_ids = tuple(item.dependency_id for item in self.dependency_evidence)
        if len(set(dependency_ids)) != len(dependency_ids):
            raise ValidationError("SupportRecord dependency_id values must be unique")


@dataclass(frozen=True)
class CatalogIdentity:
    """A vendor catalog identity, never an applicability or actuation claim."""

    series: str
    model: str
    package_revision: str
    archive_url: str
    source_id: str
    evidence_level: EvidenceLevel = field(
        default=EvidenceLevel.CATALOGED, init=False
    )
    supports_powered_actuation: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "series", _require_exact_component(self.series, "series"))
        object.__setattr__(self, "model", _require_exact_component(self.model, "model"))
        object.__setattr__(
            self,
            "package_revision",
            _require_exact_component(self.package_revision, "package_revision"),
        )
        object.__setattr__(
            self, "source_id", _require_identifier(self.source_id, "source_id")
        )
        url = _require_text(self.archive_url, "archive_url")
        if not url.startswith("https://"):
            raise ValidationError("archive_url must be an HTTPS URL")


@dataclass(frozen=True)
class RegistryPolicy:
    """Authorization policy; the hardware evidence floor cannot be weakened."""

    minimum_powered_evidence: EvidenceLevel = EvidenceLevel.HIL

    def __post_init__(self) -> None:
        level = _require_level(
            self.minimum_powered_evidence,
            "RegistryPolicy.minimum_powered_evidence",
        )
        if level not in HARDWARE_EVIDENCE_LEVELS:
            raise ValidationError(
                "minimum_powered_evidence must be BENCH, HIL, or ROBOT_RELEASE"
            )


class DenialCode(str, Enum):
    NO_EXACT_SUPPORT_RECORD = "no_exact_support_record"
    CATALOG_IDENTITY_ONLY = "catalog_identity_only"
    CAPABILITY_NOT_DECLARED = "capability_not_declared"
    EVIDENCE_NOT_YET_VALID = "evidence_not_yet_valid"
    EVIDENCE_STALE = "evidence_stale"
    EVIDENCE_EXPIRED = "evidence_expired"
    REQUIRED_EVIDENCE_NOT_MET = "required_evidence_not_met"
    POWERED_EVIDENCE_NOT_HARDWARE = "powered_evidence_not_hardware"
    POWERED_EVIDENCE_BELOW_POLICY = "powered_evidence_below_policy"
    POWERED_DEPENDENCY_EVIDENCE_MISSING = "powered_dependency_evidence_missing"
    DEPENDENCY_REQUIRED_EVIDENCE_NOT_MET = "dependency_required_evidence_not_met"
    DEPENDENCY_EVIDENCE_NOT_YET_VALID = "dependency_evidence_not_yet_valid"
    DEPENDENCY_EVIDENCE_STALE = "dependency_evidence_stale"
    DEPENDENCY_EVIDENCE_EXPIRED = "dependency_evidence_expired"


@dataclass(frozen=True)
class DenialReason:
    code: DenialCode
    message: str
    dependency_id: Optional[str] = None


@dataclass(frozen=True)
class SupportDecision:
    """A point-in-time decision with explicit reasons when fail-closed."""

    key: SupportKey
    capability: str
    powered: bool
    required_evidence: EvidenceLevel
    evaluated_at_utc: datetime
    allowed: bool
    evidence_level: Optional[EvidenceLevel]
    denial_reasons: Tuple[DenialReason, ...]

    @property
    def denial_codes(self) -> Tuple[DenialCode, ...]:
        return tuple(reason.code for reason in self.denial_reasons)


CatalogPath = Union[str, Path]


class SupportRegistry:
    """In-memory exact-key registry with collision rejection and safe queries."""

    def __init__(self, policy: Optional[RegistryPolicy] = None) -> None:
        if policy is not None and not isinstance(policy, RegistryPolicy):
            raise ValidationError("policy must be a RegistryPolicy")
        self._policy = policy or RegistryPolicy()
        self._catalog: Dict[str, CatalogIdentity] = {}
        self._records: Dict[SupportKey, SupportRecord] = {}

    @property
    def policy(self) -> RegistryPolicy:
        return self._policy

    @property
    def catalog_identities(self) -> Tuple[CatalogIdentity, ...]:
        return tuple(self._catalog[model] for model in sorted(self._catalog))

    @property
    def support_records(self) -> Tuple[SupportRecord, ...]:
        return tuple(
            self._records[key]
            for key in sorted(
                self._records,
                key=lambda item: (
                    item.model,
                    item.hardware_revision,
                    item.drive_firmware,
                    item.protocol_version,
                    item.transport,
                    item.control_mode,
                ),
            )
        )

    @property
    def catalog_identity_count(self) -> int:
        return len(self._catalog)

    @property
    def support_record_count(self) -> int:
        return len(self._records)

    def add_catalog_identity(self, identity: CatalogIdentity) -> None:
        if not isinstance(identity, CatalogIdentity):
            raise ValidationError("identity must be a CatalogIdentity")
        existing = self._catalog.get(identity.model)
        if existing is None:
            self._catalog[identity.model] = identity
            return
        if existing == identity:
            raise DuplicateRecordError(
                f"duplicate catalog identity for model {identity.model!r}"
            )
        raise ConflictingRecordError(
            f"conflicting catalog identity for model {identity.model!r}"
        )

    def add_support_record(self, record: SupportRecord) -> None:
        if not isinstance(record, SupportRecord):
            raise ValidationError("record must be a SupportRecord")
        existing = self._records.get(record.key)
        if existing is None:
            self._records[record.key] = record
            return
        if existing == record:
            raise DuplicateRecordError(f"duplicate support record for {record.key!r}")
        raise ConflictingRecordError(f"conflicting support record for {record.key!r}")

    def load_catalog_tsv(
        self,
        path: CatalogPath,
        source_id: str = "myactuator-download-catalog",
    ) -> int:
        """Load catalog identities without creating any support records."""

        checked_source = _require_identifier(source_id, "source_id")
        catalog_path = Path(path)
        with catalog_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            required = {"series", "model", "package_revision", "archive_url"}
            headers = set(reader.fieldnames or ())
            if headers != required:
                raise ValidationError(
                    "catalog TSV headers must be exactly: "
                    "series, model, package_revision, archive_url"
                )
            loaded = 0
            for line_number, row in enumerate(reader, start=2):
                try:
                    identity = CatalogIdentity(
                        series=row["series"],
                        model=row["model"],
                        package_revision=row["package_revision"],
                        archive_url=row["archive_url"],
                        source_id=checked_source,
                    )
                    self.add_catalog_identity(identity)
                except SupportRegistryError as exc:
                    raise type(exc)(
                        f"{catalog_path}:{line_number}: {exc}"
                    ) from exc
                loaded += 1
        return loaded

    @classmethod
    def from_catalog_tsv(
        cls,
        path: CatalogPath,
        policy: Optional[RegistryPolicy] = None,
        source_id: str = "myactuator-download-catalog",
    ) -> "SupportRegistry":
        registry = cls(policy=policy)
        registry.load_catalog_tsv(path, source_id=source_id)
        return registry

    def query(
        self,
        key: SupportKey,
        capability: str,
        *,
        powered: bool,
        required_evidence: EvidenceLevel = EvidenceLevel.OFFLINE,
        now_utc: Optional[datetime] = None,
    ) -> SupportDecision:
        """Evaluate one exact tuple without fallback, wildcard, or promotion."""

        if not isinstance(key, SupportKey):
            raise ValidationError("key must be a SupportKey")
        checked_capability = _require_exact_component(capability, "capability")
        if not isinstance(powered, bool):
            raise ValidationError("powered must be a boolean")
        checked_required = _require_level(required_evidence, "required_evidence")
        now = _require_utc(
            now_utc if now_utc is not None else datetime.now(timezone.utc),
            "now_utc",
        )
        record = self._records.get(key)
        if record is None:
            reasons = []
            if key.model in self._catalog:
                reasons.append(
                    DenialReason(
                        DenialCode.CATALOG_IDENTITY_ONLY,
                        "the model is cataloged, but catalog identity is not tuple applicability",
                    )
                )
            reasons.append(
                DenialReason(
                    DenialCode.NO_EXACT_SUPPORT_RECORD,
                    "no support record exists for all six exact tuple fields",
                )
            )
            return SupportDecision(
                key=key,
                capability=checked_capability,
                powered=powered,
                required_evidence=checked_required,
                evaluated_at_utc=now,
                allowed=False,
                evidence_level=None,
                denial_reasons=tuple(reasons),
            )

        reasons = []
        if checked_capability not in record.capabilities:
            reasons.append(
                DenialReason(
                    DenialCode.CAPABILITY_NOT_DECLARED,
                    f"capability {checked_capability!r} is not declared by the exact record",
                )
            )
        if now < record.valid_from_utc:
            reasons.append(
                DenialReason(
                    DenialCode.EVIDENCE_NOT_YET_VALID,
                    "support evidence is not yet valid at the evaluation time",
                )
            )
        if now > record.stale_after_utc:
            reasons.append(
                DenialReason(
                    DenialCode.EVIDENCE_STALE,
                    "support evidence passed its explicit staleness deadline",
                )
            )
        if now > record.valid_until_utc:
            reasons.append(
                DenialReason(
                    DenialCode.EVIDENCE_EXPIRED,
                    "support evidence passed its explicit validity deadline",
                )
            )
        if record.evidence_level < checked_required:
            reasons.append(
                DenialReason(
                    DenialCode.REQUIRED_EVIDENCE_NOT_MET,
                    f"record level {record.evidence_level.name} is below requested "
                    f"{checked_required.name}",
                )
            )
        if powered:
            if record.evidence_level not in HARDWARE_EVIDENCE_LEVELS:
                reasons.append(
                    DenialReason(
                        DenialCode.POWERED_EVIDENCE_NOT_HARDWARE,
                        f"{record.evidence_level.name} is not powered hardware evidence",
                    )
                )
            if record.evidence_level < self._policy.minimum_powered_evidence:
                reasons.append(
                    DenialReason(
                        DenialCode.POWERED_EVIDENCE_BELOW_POLICY,
                        f"record level {record.evidence_level.name} is below powered policy "
                        f"{self._policy.minimum_powered_evidence.name}",
                    )
                )
            if not record.dependency_evidence:
                reasons.append(
                    DenialReason(
                        DenialCode.POWERED_DEPENDENCY_EVIDENCE_MISSING,
                        "powered authorization requires explicit dependency evidence",
                    )
                )

        for dependency in record.dependency_evidence:
            if dependency.evidence_level < dependency.required_level:
                reasons.append(
                    DenialReason(
                        DenialCode.DEPENDENCY_REQUIRED_EVIDENCE_NOT_MET,
                        f"dependency level {dependency.evidence_level.name} is below declared "
                        f"{dependency.required_level.name}",
                        dependency.dependency_id,
                    )
                )
            if now < dependency.valid_from_utc:
                reasons.append(
                    DenialReason(
                        DenialCode.DEPENDENCY_EVIDENCE_NOT_YET_VALID,
                        "dependency evidence is not yet valid",
                        dependency.dependency_id,
                    )
                )
            if now > dependency.stale_after_utc:
                reasons.append(
                    DenialReason(
                        DenialCode.DEPENDENCY_EVIDENCE_STALE,
                        "dependency evidence passed its staleness deadline",
                        dependency.dependency_id,
                    )
                )
            if now > dependency.valid_until_utc:
                reasons.append(
                    DenialReason(
                        DenialCode.DEPENDENCY_EVIDENCE_EXPIRED,
                        "dependency evidence passed its validity deadline",
                        dependency.dependency_id,
                    )
                )

        return SupportDecision(
            key=key,
            capability=checked_capability,
            powered=powered,
            required_evidence=checked_required,
            evaluated_at_utc=now,
            allowed=not reasons,
            evidence_level=record.evidence_level,
            denial_reasons=tuple(reasons),
        )


__all__ = [
    "ArtifactHash",
    "CatalogIdentity",
    "ConflictingRecordError",
    "DenialCode",
    "DenialReason",
    "DependencyEvidence",
    "DuplicateRecordError",
    "EvidenceLevel",
    "HARDWARE_EVIDENCE_LEVELS",
    "RegistryPolicy",
    "SupportDecision",
    "SupportKey",
    "SupportRecord",
    "SupportRegistry",
    "SupportRegistryError",
    "ValidationError",
]
