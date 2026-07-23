"""Fail-closed admission of reviewed MYACTUATOR CAD runtime artifacts.

This module is deliberately independent of ROS and CAD engines.  It turns the
generated runtime registry into one small trust boundary shared by host, ROS
adapters and simulators.  A caller must provide the exact geometry
configuration ID *and* its series/model identity.  Source STEP files,
candidate/review material, procedural URIs and artifacts whose bytes or hash
have changed are never returned as runtime assets.

CAD admission is geometry evidence only.  It does not imply physical motor,
protocol, plant, controller, firmware or Dropbear motion support.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


REGISTRY_VERSION = "myactuator-cad-runtime-asset-registry/1"
ACCEPTED_REVIEW_STATES = frozenset({"accepted_local", "accepted_redistributable"})
ARTIFACT_NAMES = (
    "housing_step",
    "output_step",
    "housing_glb",
    "output_glb",
    "collision_glb",
)
_STEP_NAMES = frozenset({"housing_step", "output_step"})
_FORBIDDEN_PATH_PARTS = frozenset(
    {
        "candidate_exports",
        "review_packets",
        "flattened_review_packets",
        "review_workbenches",
    }
)


class CadRegistryError(ValueError):
    """The registry itself violates the fail-closed consumer contract."""


class CadAdmissionReason(str, Enum):
    ALLOWED_LOCAL = "allowed_local"
    INVALID_SELECTION = "invalid_selection"
    CONFIGURATION_NOT_FOUND = "configuration_not_found"
    CONFIGURATION_IDENTITY_MISMATCH = "configuration_identity_mismatch"
    SELECTOR_NOT_REVIEWED = "selector_not_reviewed"
    CANDIDATE_NOT_REVIEWED = "candidate_not_reviewed"
    CONFIGURATION_NOT_ACCEPTED = "configuration_not_accepted"
    ACCEPTED_ARTIFACTS_UNAVAILABLE = "accepted_artifacts_unavailable"
    SOURCE_ASSET_FORBIDDEN = "source_asset_forbidden"
    CANDIDATE_ASSET_FORBIDDEN = "candidate_asset_forbidden"
    ARTIFACT_PATH_INVALID = "artifact_path_invalid"
    ARTIFACT_MISSING_OR_CHANGED = "artifact_missing_or_changed"
    DROPBEAR_VIEW_IDENTITY_MISMATCH = "dropbear_view_identity_mismatch"
    DROPBEAR_JOINT_NOT_FOUND = "dropbear_joint_not_found"
    DROPBEAR_BINDING_UNVERIFIED = "dropbear_binding_unverified"
    DROPBEAR_ASSET_NOT_FOUND = "dropbear_asset_not_found"
    DROPBEAR_ASSET_MISMATCH = "dropbear_asset_mismatch"


@dataclass(frozen=True, slots=True)
class CadAssetSelection:
    """Exact geometry identity supplied by a canonical configuration owner."""

    series: str
    model: str
    configuration_id: str


@dataclass(frozen=True, slots=True)
class VerifiedCadArtifact:
    """A hash/size-bound artifact; consumers should call ``read_verified``."""

    name: str
    path: Path
    sha256: str
    bytes: int

    def read_verified(self) -> bytes:
        """Read and reverify at point of use, avoiding trust in an old check."""

        try:
            payload = self.path.read_bytes()
        except OSError as error:
            raise CadRegistryError(f"{self.name}: artifact cannot be read: {error}") from error
        actual = hashlib.sha256(payload).hexdigest()
        if len(payload) != self.bytes or actual != self.sha256:
            raise CadRegistryError(
                f"{self.name}: artifact changed after admission "
                f"(expected bytes={self.bytes} sha256={self.sha256}, "
                f"actual bytes={len(payload)} sha256={actual})"
            )
        return payload


@dataclass(frozen=True, slots=True)
class AdmittedCadAssetSet:
    """The five reviewed local artifacts for one exact configuration."""

    selection: CadAssetSelection
    review_status: str
    canonical_variant_id: str
    artifacts: tuple[VerifiedCadArtifact, ...]

    def artifact(self, name: str) -> VerifiedCadArtifact:
        for artifact in self.artifacts:
            if artifact.name == name:
                return artifact
        raise KeyError(name)


@dataclass(frozen=True, slots=True)
class CadAdmission:
    allowed: bool
    reason: CadAdmissionReason
    detail: str
    assets: AdmittedCadAssetSet | None = None
    dropbear_joint_name: str | None = None
    dropbear_asset_id: str | None = None


def _deny(
    reason: CadAdmissionReason,
    detail: str,
    *,
    joint_name: str | None = None,
    asset_id: str | None = None,
) -> CadAdmission:
    return CadAdmission(False, reason, detail, None, joint_name, asset_id)


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CadRegistryError(f"{context} must be an object")
    return value


def _sequence(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise CadRegistryError(f"{context} must be an array")
    return value


class RuntimeCadAssetRegistry:
    """Validated exact-selector view of the canonical local registry."""

    def __init__(self, registry: Mapping[str, Any], *, asset_root: Path) -> None:
        self._registry = _mapping(registry, "registry")
        self._asset_root = Path(asset_root).resolve()
        self._configurations: dict[str, Mapping[str, Any]] = {}
        self._source_by_id: dict[str, Mapping[str, Any]] = {}
        self._validate_registry()

    @classmethod
    def from_path(
        cls, registry_path: Path, *, asset_root: Path
    ) -> "RuntimeCadAssetRegistry":
        path = Path(registry_path)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CadRegistryError(f"cannot load CAD runtime registry {path}: {error}") from error
        return cls(value, asset_root=asset_root)

    @property
    def configuration_count(self) -> int:
        return len(self._configurations)

    def _validate_registry(self) -> None:
        registry = self._registry
        if registry.get("schema_version") != REGISTRY_VERSION:
            raise CadRegistryError("CAD runtime registry schema version mismatch")
        policy = _mapping(registry.get("policy"), "policy")
        required_policy = (
            "exact_configuration_required",
            "accepted_local_may_load_only_locally",
            "accepted_redistributable_required_for_browser",
            "source_step_is_never_runtime_asset",
            "candidate_is_never_runtime_asset",
            "artifact_hash_verification_required",
            "plant_parameters_are_separate",
        )
        if any(policy.get(name) is not True for name in required_policy):
            raise CadRegistryError("CAD runtime registry weakens a required policy")

        sources = _sequence(registry.get("source_variants"), "source_variants")
        for index, value in enumerate(sources):
            item = _mapping(value, f"source_variants/{index}")
            variant_id = item.get("variant_id")
            if not _is_nonempty_string(variant_id) or variant_id in self._source_by_id:
                raise CadRegistryError("source variant IDs must be unique non-empty strings")
            if item.get("source_step_is_runtime_asset") is not False:
                raise CadRegistryError(f"{variant_id}: source STEP was promoted to runtime")
            digest = item.get("step_sha256")
            if not isinstance(digest, str) or len(digest) != 64:
                raise CadRegistryError(f"{variant_id}: invalid source SHA-256")
            self._source_by_id[variant_id] = item

        configurations = _sequence(registry.get("configurations"), "configurations")
        seen_exact: set[tuple[str, str, str]] = set()
        for index, value in enumerate(configurations):
            item = _mapping(value, f"configurations/{index}")
            configuration_id = item.get("configuration_id")
            series = item.get("series")
            model = item.get("model")
            if not all(_is_nonempty_string(part) for part in (configuration_id, series, model)):
                raise CadRegistryError(f"configurations/{index}: incomplete exact identity")
            exact = (series, model, configuration_id)
            if configuration_id in self._configurations or exact in seen_exact:
                raise CadRegistryError(f"duplicate CAD configuration {configuration_id}")
            seen_exact.add(exact)
            self._configurations[configuration_id] = item

            variant_ids = _sequence(item.get("source_variant_ids"), f"{configuration_id}/source_variant_ids")
            if not variant_ids or len(set(variant_ids)) != len(variant_ids):
                raise CadRegistryError(f"{configuration_id}: source variants must be non-empty and unique")
            if any(variant_id not in self._source_by_id for variant_id in variant_ids):
                raise CadRegistryError(f"{configuration_id}: unknown source variant")
            for variant_id in variant_ids:
                source = self._source_by_id[variant_id]
                if source.get("series") != series or source.get("model") != model:
                    raise CadRegistryError(f"{configuration_id}: source identity mismatch")

            candidates = _sequence(item.get("candidate_reports"), f"{configuration_id}/candidate_reports")
            if any(
                not isinstance(candidate, Mapping)
                or candidate.get("accepted_asset") is not False
                or candidate.get("support_granted") is not False
                for candidate in candidates
            ):
                raise CadRegistryError(f"{configuration_id}: candidate report was promoted")

            accepted = item.get("review_status") in ACCEPTED_REVIEW_STATES
            loadable = item.get("local_runtime_loadable") is True
            assets = item.get("local_assets")
            if loadable and (not accepted or not isinstance(assets, Mapping)):
                raise CadRegistryError(f"{configuration_id}: local-loadable state exceeds review evidence")
            if not loadable and assets is not None:
                raise CadRegistryError(f"{configuration_id}: unloadable configuration leaks local assets")
            if item.get("browser_loadable") is True and not (
                item.get("review_status") == "accepted_redistributable" and loadable
            ):
                raise CadRegistryError(f"{configuration_id}: browser state exceeds redistribution evidence")

        summary = _mapping(registry.get("summary"), "summary")
        expected_counts = {
            "source_variants": len(sources),
            "geometry_configurations": len(configurations),
            "accepted_configurations": sum(
                item.get("review_status") in ACCEPTED_REVIEW_STATES
                for item in self._configurations.values()
            ),
            "local_runtime_loadable_configurations": sum(
                item.get("local_runtime_loadable") is True
                for item in self._configurations.values()
            ),
            "browser_loadable_configurations": sum(
                item.get("browser_loadable") is True
                for item in self._configurations.values()
            ),
            "candidate_reports": sum(
                len(item.get("candidate_reports", []))
                for item in self._configurations.values()
            ),
        }
        for name, expected in expected_counts.items():
            if summary.get(name) != expected:
                raise CadRegistryError(f"summary/{name} does not match registry records")

        dropbear = _mapping(registry.get("dropbear"), "dropbear")
        if not _is_nonempty_string(dropbear.get("configuration_id")):
            raise CadRegistryError("dropbear/configuration_id is missing")
        digest = dropbear.get("configuration_digest")
        if not isinstance(digest, str) or len(digest) != 64:
            raise CadRegistryError("dropbear/configuration_digest is invalid")

    def admit(self, selection: CadAssetSelection) -> CadAdmission:
        if not isinstance(selection, CadAssetSelection) or not all(
            _is_nonempty_string(part)
            for part in (selection.series, selection.model, selection.configuration_id)
        ):
            return _deny(CadAdmissionReason.INVALID_SELECTION, "exact series/model/configuration ID is required")
        item = self._configurations.get(selection.configuration_id)
        if item is None:
            return _deny(
                CadAdmissionReason.CONFIGURATION_NOT_FOUND,
                f"unknown exact CAD configuration {selection.configuration_id!r}",
            )
        if item.get("series") != selection.series or item.get("model") != selection.model:
            return _deny(
                CadAdmissionReason.CONFIGURATION_IDENTITY_MISMATCH,
                "configuration ID does not match the supplied series/model; family fallback is forbidden",
            )
        if item.get("selector_status") != "reviewed":
            if item.get("candidate_reports"):
                return _deny(
                    CadAdmissionReason.CANDIDATE_NOT_REVIEWED,
                    "real CAD candidate exists but has no independent accepted decision",
                )
            return _deny(CadAdmissionReason.SELECTOR_NOT_REVIEWED, "exact geometry selector is not reviewed")
        if item.get("review_status") not in ACCEPTED_REVIEW_STATES:
            if item.get("candidate_reports"):
                return _deny(
                    CadAdmissionReason.CANDIDATE_NOT_REVIEWED,
                    "candidate evidence cannot be used as a released runtime asset",
                )
            return _deny(
                CadAdmissionReason.CONFIGURATION_NOT_ACCEPTED,
                f"configuration review state is {item.get('review_status')!r}",
            )
        canonical_id = item.get("canonical_variant_id")
        if canonical_id not in item.get("source_variant_ids", ()):
            return _deny(
                CadAdmissionReason.ACCEPTED_ARTIFACTS_UNAVAILABLE,
                "accepted configuration has no valid canonical source variant",
            )
        raw_assets = item.get("local_assets")
        if item.get("local_runtime_loadable") is not True or not isinstance(raw_assets, Mapping):
            return _deny(
                CadAdmissionReason.ACCEPTED_ARTIFACTS_UNAVAILABLE,
                "accepted configuration has no verified local artifact set",
            )

        artifacts: list[VerifiedCadArtifact] = []
        source_hashes = {source["step_sha256"] for source in self._source_by_id.values()}
        for name in ARTIFACT_NAMES:
            record = raw_assets.get(name)
            if not isinstance(record, Mapping):
                return _deny(
                    CadAdmissionReason.ACCEPTED_ARTIFACTS_UNAVAILABLE,
                    f"missing runtime artifact {name}",
                )
            checked = self._admit_artifact(name, record, source_hashes)
            if isinstance(checked, CadAdmission):
                return checked
            artifacts.append(checked)

        return CadAdmission(
            True,
            CadAdmissionReason.ALLOWED_LOCAL,
            "exact reviewed local CAD artifacts passed path, size and SHA-256 checks",
            AdmittedCadAssetSet(
                selection=selection,
                review_status=str(item["review_status"]),
                canonical_variant_id=str(canonical_id),
                artifacts=tuple(artifacts),
            ),
        )

    def _admit_artifact(
        self,
        name: str,
        record: Mapping[str, Any],
        source_hashes: set[str],
    ) -> VerifiedCadArtifact | CadAdmission:
        relative = record.get("path")
        digest = record.get("sha256")
        size = record.get("bytes")
        if not _is_nonempty_string(relative) or "\\" in relative or "://" in relative:
            return _deny(CadAdmissionReason.ARTIFACT_PATH_INVALID, f"{name}: path must be a relative local POSIX path")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            return _deny(CadAdmissionReason.ARTIFACT_PATH_INVALID, f"{name}: path traversal or absolute path is forbidden")
        if any(part in _FORBIDDEN_PATH_PARTS for part in pure.parts):
            return _deny(CadAdmissionReason.CANDIDATE_ASSET_FORBIDDEN, f"{name}: candidate/review paths are not runtime assets")
        expected_suffixes = {".step", ".stp"} if name in _STEP_NAMES else {".glb"}
        if pure.suffix.lower() not in expected_suffixes:
            return _deny(CadAdmissionReason.ARTIFACT_PATH_INVALID, f"{name}: unexpected artifact file type")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            return _deny(CadAdmissionReason.ARTIFACT_PATH_INVALID, f"{name}: invalid SHA-256")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            return _deny(CadAdmissionReason.ARTIFACT_PATH_INVALID, f"{name}: invalid byte count")
        if name in _STEP_NAMES and digest in source_hashes:
            return _deny(CadAdmissionReason.SOURCE_ASSET_FORBIDDEN, f"{name}: vendor source STEP cannot be a runtime artifact")
        path = (self._asset_root / Path(*pure.parts)).resolve()
        try:
            path.relative_to(self._asset_root)
        except ValueError:
            return _deny(CadAdmissionReason.ARTIFACT_PATH_INVALID, f"{name}: resolved path escapes asset root")
        try:
            payload = path.read_bytes()
        except OSError:
            return _deny(CadAdmissionReason.ARTIFACT_MISSING_OR_CHANGED, f"{name}: artifact is missing or unreadable")
        actual = hashlib.sha256(payload).hexdigest()
        if len(payload) != size or actual != digest:
            return _deny(
                CadAdmissionReason.ARTIFACT_MISSING_OR_CHANGED,
                f"{name}: size/SHA-256 does not match the reviewed registry",
            )
        return VerifiedCadArtifact(name, path, digest, size)

    def admit_dropbear_joint(
        self,
        selection: CadAssetSelection,
        dropbear_view: Mapping[str, Any],
        canonical_joint_name: str,
    ) -> CadAdmission:
        """Admit an exact asset set and verify one Dropbear joint binding.

        Dropbear's V1 schema does not carry a geometry configuration ID.  The
        caller therefore supplies ``selection`` explicitly; the binding may
        only constrain that exact choice further.
        """

        if not _is_nonempty_string(canonical_joint_name):
            return _deny(CadAdmissionReason.DROPBEAR_JOINT_NOT_FOUND, "canonical joint name is required")
        try:
            view = _mapping(dropbear_view, "Dropbear view")
            registry = _mapping(view.get("registry", view), "Dropbear registry")
        except CadRegistryError as error:
            return _deny(CadAdmissionReason.DROPBEAR_VIEW_IDENTITY_MISMATCH, str(error), joint_name=canonical_joint_name)
        expected = _mapping(self._registry.get("dropbear"), "dropbear")
        identity = view.get("generated_identity", {})
        if view.get("registry") is not None:
            if not isinstance(identity, Mapping) or (
                identity.get("configuration_id") != expected.get("configuration_id")
                or identity.get("canonical_digest") != expected.get("configuration_digest")
            ):
                return _deny(
                    CadAdmissionReason.DROPBEAR_VIEW_IDENTITY_MISMATCH,
                    "Dropbear generated view does not match the registry-bound configuration",
                    joint_name=canonical_joint_name,
                )
        else:
            integrity = registry.get("configuration_integrity", {})
            if (
                registry.get("configuration_id") != expected.get("configuration_id")
                or not isinstance(integrity, Mapping)
                or integrity.get("digest") != expected.get("configuration_digest")
            ):
                return _deny(
                    CadAdmissionReason.DROPBEAR_VIEW_IDENTITY_MISMATCH,
                    "Dropbear registry identity does not match the CAD runtime registry",
                    joint_name=canonical_joint_name,
                )

        joints = registry.get("joints")
        if not isinstance(joints, list):
            return _deny(CadAdmissionReason.DROPBEAR_JOINT_NOT_FOUND, "Dropbear joints are unavailable", joint_name=canonical_joint_name)
        matches = [joint for joint in joints if isinstance(joint, Mapping) and joint.get("canonical_name") == canonical_joint_name]
        if len(matches) != 1:
            return _deny(CadAdmissionReason.DROPBEAR_JOINT_NOT_FOUND, "exactly one canonical Dropbear joint is required", joint_name=canonical_joint_name)
        joint = matches[0]
        binding = joint.get("cad_binding")
        if not isinstance(binding, Mapping):
            return _deny(CadAdmissionReason.DROPBEAR_BINDING_UNVERIFIED, "joint CAD binding is absent", joint_name=canonical_joint_name)
        asset_id = binding.get("asset_id")
        vector_fields = (binding.get("joint_origin_xyz_m"), binding.get("joint_axis_xyz"))
        if (
            binding.get("status") != "verified"
            or not _is_nonempty_string(asset_id)
            or not _is_nonempty_string(binding.get("housing_member"))
            or not _is_nonempty_string(binding.get("output_member"))
            or not all(self._finite_vector3(value) for value in vector_fields)
            or not math.isclose(
                math.sqrt(sum(float(value) ** 2 for value in vector_fields[1])),
                1.0,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
        ):
            return _deny(
                CadAdmissionReason.DROPBEAR_BINDING_UNVERIFIED,
                "joint CAD binding lacks verified member/origin/unit-axis evidence",
                joint_name=canonical_joint_name,
                asset_id=asset_id if isinstance(asset_id, str) else None,
            )
        cad_assets = registry.get("cad_assets")
        if not isinstance(cad_assets, list):
            return _deny(CadAdmissionReason.DROPBEAR_ASSET_NOT_FOUND, "Dropbear CAD asset registry is absent", joint_name=canonical_joint_name, asset_id=asset_id)
        assets = [asset for asset in cad_assets if isinstance(asset, Mapping) and asset.get("asset_id") == asset_id]
        if len(assets) != 1:
            return _deny(CadAdmissionReason.DROPBEAR_ASSET_NOT_FOUND, "binding does not resolve to exactly one Dropbear CAD asset", joint_name=canonical_joint_name, asset_id=asset_id)
        asset = assets[0]
        item = self._configurations.get(selection.configuration_id)
        canonical_id = item.get("canonical_variant_id") if item is not None else None
        source = self._source_by_id.get(canonical_id) if isinstance(canonical_id, str) else None
        bound_ids = expected.get("bound_cad_asset_ids", [])
        if (
            asset_id not in bound_ids
            or asset.get("review_status") != "verified"
            or asset.get("model") != selection.model
            or source is None
            or asset.get("source_step_sha256") != source.get("step_sha256")
            or asset.get("housing_member") != binding.get("housing_member")
            or asset.get("output_member") != binding.get("output_member")
        ):
            return _deny(
                CadAdmissionReason.DROPBEAR_ASSET_MISMATCH,
                "Dropbear binding does not match the exact canonical reviewed CAD source/members",
                joint_name=canonical_joint_name,
                asset_id=asset_id,
            )
        admission = self.admit(selection)
        return CadAdmission(
            admission.allowed,
            admission.reason,
            admission.detail,
            admission.assets,
            canonical_joint_name,
            asset_id,
        )

    @staticmethod
    def _finite_vector3(value: Any) -> bool:
        return (
            isinstance(value, list)
            and len(value) == 3
            and all(isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item) for item in value)
        )


__all__ = [
    "ARTIFACT_NAMES",
    "AdmittedCadAssetSet",
    "CadAdmission",
    "CadAdmissionReason",
    "CadAssetSelection",
    "CadRegistryError",
    "RuntimeCadAssetRegistry",
    "VerifiedCadArtifact",
]
