#!/usr/bin/env python3
"""Validate exact ESP32 security profiles and emit a fail-closed intake status."""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
PROFILE_SCHEMA = ROOT / "schemas/security-platform-profile.schema.json"
STATUS_SCHEMA = ROOT / "schemas/security-platform-intake-status.schema.json"
PROFILES = ROOT / "assets/myactuator/security_platform/profiles"
STATUS = ROOT / "generated/security_platform_intake/status.json"
PLATFORMIO_PROJECT = ROOT / "firmware/esp32/platformio.ini"
EXPECTED_COMPONENT_IDS = {
    "platform_espressif32",
    "framework_arduinoespressif32",
    "esp_idf_version_header",
    "esp32_sdkconfig",
    "default_partition_table",
}
REQUIRED_KEY_PURPOSES = {
    "firmware_release",
    "config_release",
    "calibration_release",
    "evidence_release",
    "device_tls_identity",
    "operator_identity_ca",
    "audit_seal",
}
FORBIDDEN_FIELD_TOKENS = {
    "private_key",
    "secret",
    "credential",
    "password",
    "passphrase",
    "token",
    "key_material",
    "pem",
}
AUTOMATION_IDENTIFIERS = (
    "automated",
    "automation",
    "codex",
    "generator",
    "same-agent",
    "self-review",
    "language-model",
    " llm",
)


class SecurityPlatformIntakeError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SecurityPlatformIntakeError(message)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SecurityPlatformIntakeError(f"cannot read {path}: {error}") from error
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def schema_validate(value: dict[str, Any], path: Path, label: str) -> None:
    schema = load(path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise SecurityPlatformIntakeError(
            f"{label} schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def identity_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload.pop("profile_id", None)
    payload.pop("integrity", None)
    return canonical_bytes(payload)


def expected_profile_id(value: dict[str, Any]) -> str:
    return "securityprofile-" + sha_bytes(identity_payload(value))[:20]


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def recursive_field_names(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            names.add(key.casefold())
            names.update(recursive_field_names(child))
    elif isinstance(value, list):
        for child in value:
            names.update(recursive_field_names(child))
    return names


def reject_secret_fields(value: dict[str, Any]) -> None:
    names = recursive_field_names(value)
    found = sorted(
        name
        for name in names
        if any(token in name for token in FORBIDDEN_FIELD_TOKENS)
        and name
        not in {
            "private_key_location_class",
            "private_key_material_count",
        }
    )
    if found:
        raise SecurityPlatformIntakeError(
            f"secret/private material field forbidden: {found[0]}"
        )


def platformio_home(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    configured = os.environ.get("PLATFORMIO_HOME_DIR")
    return (
        Path(configured).expanduser().resolve()
        if configured
        else (Path.home() / ".platformio").resolve()
    )


def component_map(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    components = value["toolchain"]["components"]
    by_id = {row["component_id"]: row for row in components}
    require(
        set(by_id) == EXPECTED_COMPONENT_IDS and len(by_id) == len(components),
        "security profile toolchain component set/uniqueness drift",
    )
    return by_id


def component_path(component: dict[str, Any], home: Path) -> Path:
    relative = Path(component["platformio_home_relative_path"])
    require(
        not relative.is_absolute() and ".." not in relative.parts,
        "security profile component path escapes PlatformIO home",
    )
    path = (home / relative).resolve()
    try:
        path.relative_to(home.resolve())
    except ValueError as error:
        raise SecurityPlatformIntakeError(
            "security profile component path escapes PlatformIO home"
        ) from error
    return path


def parse_sdkconfig(raw: bytes) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for line in raw.decode("utf-8").splitlines():
        if match := re.fullmatch(r"(CONFIG_[A-Z0-9_]+)=y", line):
            flags[match.group(1)] = True
        elif match := re.fullmatch(
            r"# (CONFIG_[A-Z0-9_]+) is not set", line
        ):
            flags[match.group(1)] = False
    return flags


def enabled(flags: dict[str, bool], *names: str) -> bool:
    return any(flags.get(name, False) for name in names)


def parse_partitions(raw: bytes) -> list[dict[str, Any]]:
    text = "\n".join(
        line for line in raw.decode("utf-8").splitlines() if not line.startswith("#")
    )
    rows: list[dict[str, Any]] = []
    previous_end = 0
    for fields in csv.reader(io.StringIO(text), skipinitialspace=True):
        if not fields or not fields[0].strip():
            continue
        require(len(fields) >= 5, "partition table row is incomplete")
        name, kind, subtype, offset_text, size_text = (
            field.strip() for field in fields[:5]
        )
        offset = int(offset_text, 0) if offset_text else previous_end
        size = int(size_text, 0)
        flags = fields[5].strip() if len(fields) > 5 else ""
        rows.append(
            {
                "name": name,
                "type": kind,
                "subtype": subtype,
                "offset": offset,
                "size": size,
                "encrypted": "encrypted" in flags.split(":"),
            }
        )
        previous_end = offset + size
    return rows


def observed_capabilities(
    sdkconfig: bytes, partitions: list[dict[str, Any]]
) -> dict[str, bool]:
    flags = parse_sdkconfig(sdkconfig)
    names = {row["name"] for row in partitions}
    subtypes = {row["subtype"] for row in partitions}
    return {
        "secure_boot_enabled": enabled(
            flags,
            "CONFIG_SECURE_BOOT",
            "CONFIG_SECURE_BOOT_ENABLED",
            "CONFIG_SECURE_BOOT_V2_ENABLED",
        ),
        "flash_encryption_enabled": enabled(
            flags,
            "CONFIG_SECURE_FLASH_ENC_ENABLED",
            "CONFIG_FLASH_ENCRYPTION_ENABLED",
        ),
        "bootloader_anti_rollback_enabled": enabled(
            flags, "CONFIG_BOOTLOADER_APP_ANTI_ROLLBACK"
        ),
        "application_rollback_enabled": enabled(
            flags, "CONFIG_APP_ROLLBACK_ENABLE"
        ),
        "nvs_encryption_enabled": enabled(
            flags, "CONFIG_NVS_ENCRYPTION", "CONFIG_NVS_ENCRYPTION_ENABLED"
        ),
        "esp_tls_mbedtls_enabled": enabled(
            flags, "CONFIG_ESP_TLS_USING_MBEDTLS"
        ),
        "esp_tls_secure_element_enabled": enabled(
            flags, "CONFIG_ESP_TLS_USE_SECURE_ELEMENT"
        ),
        "mbedtls_certificate_bundle_enabled": enabled(
            flags, "CONFIG_MBEDTLS_CERTIFICATE_BUNDLE"
        ),
        "tls_1_0_enabled": enabled(flags, "CONFIG_MBEDTLS_SSL_PROTO_TLS1"),
        "tls_1_1_enabled": enabled(flags, "CONFIG_MBEDTLS_SSL_PROTO_TLS1_1"),
        "tls_1_2_enabled": enabled(flags, "CONFIG_MBEDTLS_SSL_PROTO_TLS1_2"),
        "tls_1_3_enabled": enabled(flags, "CONFIG_MBEDTLS_SSL_PROTO_TLS1_3"),
        "ota_ab_slots_present": {"ota_0", "ota_1"}.issubset(subtypes),
        "coredump_partition_present": "coredump" in names,
        "persistent_security_state_partition_present": any(
            row["name"] in {"security", "secstate", "security_state"}
            for row in partitions
        ),
    }


def verify_installed_profile(
    value: dict[str, Any], home: Path | None = None
) -> None:
    home = platformio_home(home)
    by_id = component_map(value)
    payloads: dict[str, bytes] = {}
    for component_id, component in by_id.items():
        path = component_path(component, home)
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise SecurityPlatformIntakeError(
                f"installed security component unavailable: {component_id}: {error}"
            ) from error
        require(
            sha_bytes(raw) == component["sha256"],
            f"installed security component hash drift: {component_id}",
        )
        payloads[component_id] = raw
    require(
        sha_bytes(PLATFORMIO_PROJECT.read_bytes())
        == value["project"]["platformio_project_sha256"],
        "security profile PlatformIO project hash drift",
    )
    partitions = parse_partitions(payloads["default_partition_table"])
    require(
        partitions == value["partition_layout"]["partitions"],
        "security profile partition layout drift",
    )
    observed = observed_capabilities(payloads["esp32_sdkconfig"], partitions)
    require(
        observed == value["capabilities"],
        "security profile sdkconfig/partition capability drift",
    )
    platform_package = json.loads(payloads["platform_espressif32"])
    framework_package = json.loads(payloads["framework_arduinoespressif32"])
    require(
        by_id["platform_espressif32"]["version"]
        == str(platform_package["version"])
        and by_id["framework_arduinoespressif32"]["version"]
        == str(framework_package["version"]),
        "security profile package version drift",
    )
    header = payloads["esp_idf_version_header"].decode("utf-8")
    version_parts = []
    for name in ("MAJOR", "MINOR", "PATCH"):
        match = re.search(
            rf"^#define ESP_IDF_VERSION_{name}\s+(\d+)\s*$",
            header,
            re.MULTILINE,
        )
        require(match is not None, "cannot parse installed ESP-IDF version")
        version_parts.append(match.group(1))
    require(
        by_id["esp_idf_version_header"]["version"] == ".".join(version_parts),
        "security profile ESP-IDF version drift",
    )


def validate_key_topology(value: dict[str, Any]) -> None:
    anchors = value["trust_anchors"]
    keys = value["key_assignments"]
    anchor_ids = [row["anchor_id"] for row in anchors]
    key_ids = [row["key_id"] for row in keys]
    purposes = [row["purpose"] for row in keys]
    fingerprints = [row["public_fingerprint_sha256"] for row in keys]
    anchor_fingerprints = [
        row["public_fingerprint_sha256"] for row in anchors
    ]
    require(
        len(anchor_ids) == len(set(anchor_ids)),
        "security trust anchor IDs are not unique",
    )
    require(len(key_ids) == len(set(key_ids)), "security key IDs are not unique")
    require(
        len(purposes) == len(set(purposes)),
        "security key purpose is assigned more than once",
    )
    require(
        len(fingerprints) == len(set(fingerprints)),
        "security key material is reused across purposes",
    )
    require(
        len(anchor_fingerprints) == len(set(anchor_fingerprints)),
        "security trust anchor material is reused across purposes",
    )
    by_anchor = {row["anchor_id"]: row for row in anchors}
    for assignment in keys:
        require(
            assignment["anchor_id"] in by_anchor,
            "security key assignment references unknown trust anchor",
        )
        anchor = by_anchor[assignment["anchor_id"]]
        require(
            anchor["purpose"] == assignment["purpose"],
            "security key/anchor purpose mismatch",
        )


def selection_admissible(value: dict[str, Any]) -> bool:
    selection = value["selection"]
    if not selection["requested"]:
        return False
    require(
        value["record_state"] == "reviewed_target",
        "security profile selection requires reviewed target state",
    )
    identity = (
        f"{selection['reviewer_id'] or ''} "
        f"{selection['organization_or_team'] or ''}"
    ).casefold()
    require(
        selection["reviewer_id"] is not None
        and selection["organization_or_team"] is not None
        and selection["independence_attested"] is True
        and selection["reviewed_at"] is not None
        and selection["review_evidence_refs"]
        and not any(token in identity for token in AUTOMATION_IDENTIFIERS),
        "security profile selection lacks independent human review",
    )
    reviewed = dt.datetime.fromisoformat(
        selection["reviewed_at"].replace("Z", "+00:00")
    )
    require(
        reviewed.tzinfo is not None
        and reviewed.utcoffset() == dt.timedelta(0),
        "security profile review time is not UTC",
    )
    target = value["target"]
    require(
        target["installed_asset_id"] is not None
        and target["chip_model"] is not None
        and target["chip_revision"] is not None
        and target["secure_boot_revision_compatible"] is True
        and target["efuse_summary_sha256"] is not None
        and target["flash_encryption_mode"] == "release"
        and target["physical_observation_evidence_refs"],
        "security profile selection lacks exact physical/eFuse evidence",
    )
    capabilities = value["capabilities"]
    require(
        capabilities["secure_boot_enabled"]
        and capabilities["flash_encryption_enabled"]
        and capabilities["bootloader_anti_rollback_enabled"]
        and capabilities["nvs_encryption_enabled"]
        and capabilities["esp_tls_mbedtls_enabled"]
        and capabilities["tls_1_2_enabled"]
        and not capabilities["tls_1_0_enabled"]
        and not capabilities["tls_1_1_enabled"]
        and capabilities["ota_ab_slots_present"]
        and capabilities["persistent_security_state_partition_present"],
        "security profile selection lacks required protected capabilities",
    )
    adapters = value["adapter_bindings"]
    require(
        all(adapter is not None for adapter in adapters.values()),
        "security profile selection lacks concrete adapter bindings",
    )
    require(
        {row["purpose"] for row in value["trust_anchors"]}
        == REQUIRED_KEY_PURPOSES
        and {row["purpose"] for row in value["key_assignments"]}
        == REQUIRED_KEY_PURPOSES
        and all(
            row["provisioning_state"] == "provisioned_and_reviewed"
            for row in value["key_assignments"]
        ),
        "security profile selection lacks separated provisioned key purposes",
    )
    firmware_anchor = next(
        row
        for row in value["trust_anchors"]
        if row["purpose"] == "firmware_release"
    )
    require(
        firmware_anchor["termination_kind"] == "hardware_efuse"
        and firmware_anchor["algorithm"] == "rsa_pss_3072_sha256",
        "classic ESP32 firmware root must terminate at reviewed Secure Boot V2 eFuse",
    )
    device_identity = next(
        row
        for row in value["key_assignments"]
        if row["purpose"] == "device_tls_identity"
    )
    if (
        device_identity["private_key_location_class"]
        == "secure_element_nonexportable"
    ):
        require(
            capabilities["esp_tls_secure_element_enabled"]
            and target["secure_element_part_number"] is not None
            and target["secure_element_provisioning_id"] is not None,
            "secure-element device identity lacks enabled/provisioned target evidence",
        )
    require(
        not value["blockers"],
        "security profile with unresolved blockers cannot be selected",
    )
    return True


def validate_profile(
    value: dict[str, Any],
    *,
    verify_installed: bool = True,
    home: Path | None = None,
) -> None:
    reject_secret_fields(value)
    schema_validate(value, PROFILE_SCHEMA, "security platform profile")
    require(
        value["profile_id"] == expected_profile_id(value)
        and value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "security platform profile ID/digest mismatch",
    )
    require(
        value["project"]["platformio_project_sha256"]
        == sha_bytes(PLATFORMIO_PROJECT.read_bytes()),
        "security platform profile project source drift",
    )
    component_map(value)
    validate_key_topology(value)
    selection = value["selection"]
    if not selection["requested"]:
        require(
            selection["reviewer_id"] is None
            and selection["organization_or_team"] is None
            and selection["independence_attested"] is False
            and selection["reviewed_at"] is None
            and not selection["review_evidence_refs"],
            "unrequested security profile carries selection review claims",
        )
    if value["record_state"] == "observed_offline":
        require(
            not selection["requested"]
            and all(
                value["target"][field] is None
                for field in (
                    "installed_asset_id",
                    "chip_model",
                    "chip_revision",
                    "secure_boot_revision_compatible",
                    "efuse_summary_sha256",
                    "flash_encryption_mode",
                    "secure_element_part_number",
                    "secure_element_provisioning_id",
                )
            )
            and not value["target"]["physical_observation_evidence_refs"]
            and not value["trust_anchors"]
            and not value["key_assignments"]
            and all(
                adapter is None for adapter in value["adapter_bindings"].values()
            ),
            "offline observation profile claims target/root/key/adapter evidence",
        )
    if selection["requested"]:
        selection_admissible(value)
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False
        and value["physical_io_enabled"] is False,
        "security platform profile grants support/motion/I/O",
    )
    if verify_installed:
        verify_installed_profile(value, home)


def owned_files(directory: Path) -> list[Path]:
    require(directory.is_dir(), "security platform profile directory missing")
    files = sorted(path for path in directory.iterdir() if path.is_file())
    require(
        files and all(path.suffix == ".json" for path in files),
        "security platform profile inventory empty or contains non-JSON file",
    )
    return files


def path_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return f"synthetic-fixture/profiles/{path.name}"


def status_digest(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return sha_bytes(canonical_bytes(payload))


def empty_selected_capabilities() -> dict[str, bool]:
    return {
        "secure_boot_enabled": False,
        "flash_encryption_enabled": False,
        "bootloader_anti_rollback_enabled": False,
        "nvs_encryption_enabled": False,
        "legacy_tls_enabled": False,
        "authenticated_transport_adapter_present": False,
        "signed_artifact_verifier_adapter_present": False,
        "persistent_replay_adapter_present": False,
        "durable_audit_adapter_present": False,
        "ota_installer_adapter_present": False,
    }


def build(
    profiles_root: Path = PROFILES,
    *,
    verify_installed: bool = True,
    home: Path | None = None,
) -> dict[str, Any]:
    profiles: list[tuple[dict[str, Any], Path, bool]] = []
    ids: set[str] = set()
    for path in owned_files(profiles_root):
        profile = load(path)
        validate_profile(
            profile, verify_installed=verify_installed, home=home
        )
        require(
            path.name == f"{profile['profile_id']}.json",
            "security platform profile filename/ID mismatch",
        )
        require(
            profile["profile_id"] not in ids,
            "duplicate security platform profile ID",
        )
        ids.add(profile["profile_id"])
        selected = selection_admissible(profile)
        profiles.append((profile, path, selected))
    profiles.sort(key=lambda row: row[0]["profile_id"])
    selected_rows = [row for row in profiles if row[2]]
    require(
        len(selected_rows) <= 1,
        "multiple security platform profiles request selection",
    )
    entries = [
        {
            "profile_id": profile["profile_id"],
            "path": path_label(path),
            "sha256": sha_bytes(canonical_bytes(profile)),
            "record_state": profile["record_state"],
            "board_id": profile["project"]["board_id"],
            "platform_target": profile["project"]["platform_target"],
            "selection_requested": profile["selection"]["requested"],
            "selected": selected,
        }
        for profile, path, selected in profiles
    ]
    selected_profile = selected_rows[0][0] if selected_rows else None
    selected_capabilities = empty_selected_capabilities()
    if selected_profile is not None:
        capabilities = selected_profile["capabilities"]
        adapters = selected_profile["adapter_bindings"]
        selected_capabilities = {
            "secure_boot_enabled": capabilities["secure_boot_enabled"],
            "flash_encryption_enabled": capabilities[
                "flash_encryption_enabled"
            ],
            "bootloader_anti_rollback_enabled": capabilities[
                "bootloader_anti_rollback_enabled"
            ],
            "nvs_encryption_enabled": capabilities["nvs_encryption_enabled"],
            "legacy_tls_enabled": (
                capabilities["tls_1_0_enabled"]
                or capabilities["tls_1_1_enabled"]
            ),
            "authenticated_transport_adapter_present": (
                adapters["authenticated_transport_adapter_id"] is not None
            ),
            "signed_artifact_verifier_adapter_present": (
                adapters["signed_artifact_verifier_adapter_id"] is not None
            ),
            "persistent_replay_adapter_present": (
                adapters["persistent_replay_store_adapter_id"] is not None
            ),
            "durable_audit_adapter_present": (
                adapters["durable_audit_sink_adapter_id"] is not None
            ),
            "ota_installer_adapter_present": (
                adapters["ota_installer_adapter_id"] is not None
            ),
        }
    observed_capabilities = {
        "secure_boot_enabled": any(
            profile["capabilities"]["secure_boot_enabled"]
            for profile, _, _ in profiles
        ),
        "flash_encryption_enabled": any(
            profile["capabilities"]["flash_encryption_enabled"]
            for profile, _, _ in profiles
        ),
        "bootloader_anti_rollback_enabled": any(
            profile["capabilities"]["bootloader_anti_rollback_enabled"]
            for profile, _, _ in profiles
        ),
        "nvs_encryption_enabled": any(
            profile["capabilities"]["nvs_encryption_enabled"]
            for profile, _, _ in profiles
        ),
        "legacy_tls_enabled": any(
            profile["capabilities"]["tls_1_0_enabled"]
            or profile["capabilities"]["tls_1_1_enabled"]
            for profile, _, _ in profiles
        ),
        "authenticated_transport_adapter_present": any(
            profile["adapter_bindings"][
                "authenticated_transport_adapter_id"
            ]
            is not None
            for profile, _, _ in profiles
        ),
        "signed_artifact_verifier_adapter_present": any(
            profile["adapter_bindings"][
                "signed_artifact_verifier_adapter_id"
            ]
            is not None
            for profile, _, _ in profiles
        ),
        "persistent_replay_adapter_present": any(
            profile["adapter_bindings"][
                "persistent_replay_store_adapter_id"
            ]
            is not None
            for profile, _, _ in profiles
        ),
        "durable_audit_adapter_present": any(
            profile["adapter_bindings"]["durable_audit_sink_adapter_id"]
            is not None
            for profile, _, _ in profiles
        ),
        "ota_installer_adapter_present": any(
            profile["adapter_bindings"]["ota_installer_adapter_id"]
            is not None
            for profile, _, _ in profiles
        ),
    }
    blockers = (
        []
        if selected_profile is not None
        else sorted(
            {
                blocker
                for profile, _, _ in profiles
                for blocker in profile["blockers"]
            }
            | {
                "exact_installed_board_chip_revision_and_efuse_evidence_missing",
                "independently_reviewed_security_profile_selection_missing",
                "separated_trust_anchors_and_key_assignments_missing",
                "authenticated_transport_and_signed_artifact_adapters_missing",
                "persistent_replay_and_durable_audit_adapters_missing",
                "physical_authorization_missing",
            }
        )
    )
    value = {
        "schema_version": "security-platform-intake-status/1",
        "artifact_id": "dropbear-security-platform-intake-status",
        "authority": "source_bound_profile_inventory_only",
        "source": {
            "profile_schema_path": PROFILE_SCHEMA.relative_to(ROOT).as_posix(),
            "profile_schema_sha256": sha_bytes(PROFILE_SCHEMA.read_bytes()),
            "status_schema_path": STATUS_SCHEMA.relative_to(ROOT).as_posix(),
            "status_schema_sha256": sha_bytes(STATUS_SCHEMA.read_bytes()),
        },
        "profiles": entries,
        "selected_profile_id": (
            selected_profile["profile_id"] if selected_profile else None
        ),
        "summary": {
            "profile_count": len(profiles),
            "observed_offline_profile_count": sum(
                profile["record_state"] == "observed_offline"
                for profile, _, _ in profiles
            ),
            "reviewed_target_profile_count": sum(
                profile["record_state"] == "reviewed_target"
                for profile, _, _ in profiles
            ),
            "selected_profile_count": len(selected_rows),
            "trust_anchor_count": sum(
                len(profile["trust_anchors"])
                for profile, _, _ in profiles
            ),
            "key_assignment_count": sum(
                len(profile["key_assignments"])
                for profile, _, _ in profiles
            ),
            "private_key_material_count": 0,
        },
        "observed_capabilities": observed_capabilities,
        "selected_capabilities": selected_capabilities,
        "blockers": blockers,
        "support_granted": False,
        "physical_motion_authority": False,
        "physical_io_enabled": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    value["integrity"]["record_sha256"] = status_digest(value)
    validate_status(value)
    return value


def validate_status(value: dict[str, Any]) -> None:
    reject_secret_fields(value)
    schema_validate(value, STATUS_SCHEMA, "security platform intake status")
    require(
        value["source"]
        == {
            "profile_schema_path": PROFILE_SCHEMA.relative_to(ROOT).as_posix(),
            "profile_schema_sha256": sha_bytes(PROFILE_SCHEMA.read_bytes()),
            "status_schema_path": STATUS_SCHEMA.relative_to(ROOT).as_posix(),
            "status_schema_sha256": sha_bytes(STATUS_SCHEMA.read_bytes()),
        }
        and value["integrity"]["record_sha256"] == status_digest(value),
        "security platform intake source/status digest drift",
    )
    entries = value["profiles"]
    selected = [row for row in entries if row["selected"]]
    require(
        len({row["profile_id"] for row in entries}) == len(entries)
        and len(selected) <= 1
        and value["selected_profile_id"]
        == (selected[0]["profile_id"] if selected else None),
        "security platform intake selection drift",
    )
    expected_counts = {
        "profile_count": len(entries),
        "observed_offline_profile_count": sum(
            row["record_state"] == "observed_offline" for row in entries
        ),
        "reviewed_target_profile_count": sum(
            row["record_state"] == "reviewed_target" for row in entries
        ),
        "selected_profile_count": len(selected),
    }
    require(
        all(value["summary"][key] == count for key, count in expected_counts.items())
        and value["summary"]["private_key_material_count"] == 0,
        "security platform intake summary drift",
    )
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False
        and value["physical_io_enabled"] is False,
        "security platform intake grants support/motion/I/O",
    )


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def generate() -> dict[str, Any]:
    value = build()
    atomic_write(STATUS, value)
    return value


def check() -> dict[str, Any]:
    value = build()
    require(
        STATUS.is_file() and STATUS.read_bytes() == canonical_bytes(value),
        "tracked security platform intake status drift",
    )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--validate-profile", type=Path)
    args = parser.parse_args()
    if args.validate_profile:
        validate_profile(load(args.validate_profile.resolve()))
        print("SECURITY_PLATFORM_PROFILE_OK support=false motion=false io=false")
        return 0
    value = generate() if args.generate else check()
    summary = value["summary"]
    capabilities = value["observed_capabilities"]
    print(
        "SECURITY_PLATFORM_INTAKE_OK "
        f"profiles={summary['profile_count']} "
        f"reviewed={summary['reviewed_target_profile_count']} "
        f"selected={summary['selected_profile_count']} "
        f"anchors={summary['trust_anchor_count']} "
        f"keys={summary['key_assignment_count']} "
        f"legacy_tls={str(capabilities['legacy_tls_enabled']).lower()} "
        "private_material=0 support=false motion=false io=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        KeyError,
        OSError,
        SecurityPlatformIntakeError,
        TypeError,
        ValueError,
    ) as error:
        print(f"security platform intake failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
