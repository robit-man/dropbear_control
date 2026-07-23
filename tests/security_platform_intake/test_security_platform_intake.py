from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/manage_security_platform_intake.py"
PROFILE = next(
    (ROOT / "assets/myactuator/security_platform/profiles").glob("*.json")
)
STATUS = ROOT / "generated/security_platform_intake/status.json"

spec = importlib.util.spec_from_file_location(
    "security_platform_intake_test_module", TOOL
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class SecurityPlatformIntakeTests(unittest.TestCase):
    def baseline(self):
        return json.loads(PROFILE.read_text())

    def reseal(self, value):
        value["profile_id"] = manager.expected_profile_id(value)
        manager.set_digest(value)
        return value

    def write_profiles(self, root, profiles):
        root.mkdir()
        for profile in profiles:
            (root / f"{profile['profile_id']}.json").write_bytes(
                manager.canonical_bytes(profile)
            )

    def selected_fixture(self, marker="selected"):
        value = self.baseline()
        value["record_state"] = "reviewed_target"
        value["target"] = {
            "target_family": "classic_esp32",
            "installed_asset_id": f"dropbear-controller-{marker}",
            "chip_model": "ESP32-D0WDQ6 synthetic semantic fixture",
            "chip_revision": "reviewed-revision-3-or-later-fixture",
            "secure_boot_revision_compatible": True,
            "efuse_summary_sha256": "91" * 32,
            "flash_encryption_mode": "release",
            "secure_element_part_number": "ATECC608A fixture",
            "secure_element_provisioning_id": f"fixture-provisioning-{marker}",
            "physical_observation_evidence_refs": [
                f"tests/security_platform_intake/physical-{marker}"
            ],
        }
        value["capabilities"].update(
            secure_boot_enabled=True,
            flash_encryption_enabled=True,
            bootloader_anti_rollback_enabled=True,
            nvs_encryption_enabled=True,
            esp_tls_secure_element_enabled=True,
            tls_1_0_enabled=False,
            tls_1_1_enabled=False,
            persistent_security_state_partition_present=True,
        )
        value["partition_layout"]["partitions"].append(
            {
                "name": "secstate",
                "type": "data",
                "subtype": "nvs",
                "offset": 4194304,
                "size": 65536,
                "encrypted": True,
            }
        )
        roots = []
        keys = []
        for index, purpose in enumerate(
            sorted(manager.REQUIRED_KEY_PURPOSES), start=1
        ):
            anchor_id = f"anchor-{purpose.replace('_', '-')}"
            fingerprint = f"{index:02x}" * 32
            roots.append(
                {
                    "anchor_id": anchor_id,
                    "purpose": purpose,
                    "termination_kind": (
                        "hardware_efuse"
                        if purpose == "firmware_release"
                        else (
                            "external_operator_ca"
                            if purpose == "operator_identity_ca"
                            else "offline_release_root"
                        )
                    ),
                    "algorithm": (
                        "rsa_pss_3072_sha256"
                        if purpose == "firmware_release"
                        else (
                            "x509_platform_profile"
                            if purpose
                            in {"device_tls_identity", "operator_identity_ca"}
                            else "ed25519"
                        )
                    ),
                    "public_fingerprint_sha256": fingerprint,
                    "custodian": f"independent-{purpose}-custodian",
                    "rotation_policy_ref": (
                        f"tests/security_platform_intake/rotation-{purpose}"
                    ),
                    "revocation_policy_ref": (
                        f"tests/security_platform_intake/revocation-{purpose}"
                    ),
                    "evidence_refs": [
                        f"tests/security_platform_intake/root-{purpose}"
                    ],
                }
            )
            keys.append(
                {
                    "key_id": f"key-{purpose.replace('_', '-')}",
                    "purpose": purpose,
                    "anchor_id": anchor_id,
                    "public_fingerprint_sha256": fingerprint,
                    "private_key_location_class": (
                        "secure_element_nonexportable"
                        if purpose == "device_tls_identity"
                        else (
                            "external_identity_provider"
                            if purpose == "operator_identity_ca"
                            else (
                                "device_efuse_nonexportable"
                                if purpose == "firmware_release"
                                else "offline_hsm_or_signing_service"
                            )
                        )
                    ),
                    "provisioning_state": "provisioned_and_reviewed",
                    "evidence_refs": [
                        f"tests/security_platform_intake/key-{purpose}"
                    ],
                }
            )
        value["trust_anchors"] = roots
        value["key_assignments"] = keys
        value["adapter_bindings"] = {
            "authenticated_transport_adapter_id": "fixture-mtls-v1",
            "signed_artifact_verifier_adapter_id": "fixture-verifier-v1",
            "persistent_replay_store_adapter_id": "fixture-replay-store-v1",
            "durable_audit_sink_adapter_id": "fixture-audit-sink-v1",
            "ota_installer_adapter_id": "fixture-ota-installer-v1",
        }
        value["selection"] = {
            "requested": True,
            "reviewer_id": f"independent-security-reviewer-{marker}",
            "organization_or_team": "external-security-review-team",
            "independence_attested": True,
            "reviewed_at": "2026-07-23T21:00:00Z",
            "review_evidence_refs": [
                f"tests/security_platform_intake/review-{marker}"
            ],
        }
        value["blockers"] = []
        return self.reseal(value)

    def build_case(self, profiles):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "profiles"
            self.write_profiles(root, profiles)
            return manager.build(root, verify_installed=False)

    def test_tracked_profile_and_status_bind_exact_installed_sources(self):
        profile = self.baseline()
        manager.validate_profile(profile)
        value = manager.build()
        self.assertEqual(value, json.loads(STATUS.read_text()))
        self.assertEqual(1, value["summary"]["profile_count"])
        self.assertEqual(0, value["summary"]["reviewed_target_profile_count"])
        self.assertEqual(0, value["summary"]["selected_profile_count"])
        self.assertEqual(0, value["summary"]["trust_anchor_count"])
        self.assertEqual(0, value["summary"]["key_assignment_count"])
        self.assertEqual(0, value["summary"]["private_key_material_count"])
        self.assertIsNone(value["selected_profile_id"])
        self.assertTrue(value["observed_capabilities"]["legacy_tls_enabled"])
        self.assertFalse(value["selected_capabilities"]["legacy_tls_enabled"])
        for key in (
            "secure_boot_enabled",
            "flash_encryption_enabled",
            "bootloader_anti_rollback_enabled",
            "nvs_encryption_enabled",
            "authenticated_transport_adapter_present",
            "signed_artifact_verifier_adapter_present",
            "persistent_replay_adapter_present",
            "durable_audit_adapter_present",
            "ota_installer_adapter_present",
        ):
            self.assertFalse(value["observed_capabilities"][key], key)
        self.assertFalse(value["support_granted"])
        self.assertFalse(value["physical_motion_authority"])
        self.assertFalse(value["physical_io_enabled"])

    def test_synthetic_complete_review_is_positive_capable_but_nonphysical(self):
        value = self.build_case([self.selected_fixture()])
        self.assertEqual(1, value["summary"]["selected_profile_count"])
        self.assertIsNotNone(value["selected_profile_id"])
        self.assertEqual(7, value["summary"]["trust_anchor_count"])
        self.assertEqual(7, value["summary"]["key_assignment_count"])
        self.assertFalse(value["selected_capabilities"]["legacy_tls_enabled"])
        self.assertTrue(value["selected_capabilities"]["secure_boot_enabled"])
        self.assertTrue(
            value["selected_capabilities"][
                "authenticated_transport_adapter_present"
            ]
        )
        self.assertFalse(value["support_granted"])
        self.assertFalse(value["physical_motion_authority"])
        self.assertFalse(value["physical_io_enabled"])

    def test_boolean_promotion_without_reviewed_target_denies(self):
        value = self.baseline()
        value["selection"]["requested"] = True
        self.reseal(value)
        with self.assertRaises(manager.SecurityPlatformIntakeError):
            manager.validate_profile(value, verify_installed=False)

    def test_selection_requires_physical_efuse_and_every_adapter(self):
        mutations = [
            lambda value: value["target"].update(efuse_summary_sha256=None),
            lambda value: value["target"].update(
                secure_boot_revision_compatible=False
            ),
            lambda value: value["target"].update(
                physical_observation_evidence_refs=[]
            ),
            lambda value: value["adapter_bindings"].update(
                authenticated_transport_adapter_id=None
            ),
            lambda value: value["capabilities"].update(
                persistent_security_state_partition_present=False
            ),
            lambda value: value["capabilities"].update(tls_1_0_enabled=True),
        ]
        for mutation in mutations:
            value = self.selected_fixture("required")
            mutation(value)
            self.reseal(value)
            with self.assertRaises(manager.SecurityPlatformIntakeError):
                manager.validate_profile(value, verify_installed=False)

    def test_key_purposes_are_complete_distinct_and_root_terminated(self):
        mutations = [
            lambda value: value["key_assignments"].pop(),
            lambda value: value["key_assignments"][1].update(
                public_fingerprint_sha256=value["key_assignments"][0][
                    "public_fingerprint_sha256"
                ]
            ),
            lambda value: value["key_assignments"][1].update(
                purpose=value["key_assignments"][0]["purpose"]
            ),
            lambda value: value["key_assignments"][0].update(
                anchor_id="anchor-unknown"
            ),
            lambda value: value["trust_anchors"][1].update(
                public_fingerprint_sha256=value["trust_anchors"][0][
                    "public_fingerprint_sha256"
                ]
            ),
            lambda value: next(
                row
                for row in value["trust_anchors"]
                if row["purpose"] == "firmware_release"
            ).update(termination_kind="offline_release_root"),
            lambda value: value["capabilities"].update(
                esp_tls_secure_element_enabled=False
            ),
        ]
        for mutation in mutations:
            value = self.selected_fixture("keys")
            mutation(value)
            self.reseal(value)
            with self.assertRaises(manager.SecurityPlatformIntakeError):
                manager.validate_profile(value, verify_installed=False)

    def test_private_secret_and_credential_fields_deny(self):
        for field in ("private_key_pem", "secret_value", "credential_token"):
            value = self.baseline()
            value[field] = "forbidden"
            self.reseal(value)
            with self.assertRaises(manager.SecurityPlatformIntakeError):
                manager.validate_profile(value, verify_installed=False)

    def test_automation_review_and_multiple_selection_deny(self):
        value = self.selected_fixture("review")
        value["selection"]["reviewer_id"] = "codex-automated-reviewer"
        self.reseal(value)
        with self.assertRaises(manager.SecurityPlatformIntakeError):
            manager.validate_profile(value, verify_installed=False)

        first = self.selected_fixture("one")
        second = self.selected_fixture("two")
        with self.assertRaises(manager.SecurityPlatformIntakeError):
            self.build_case([first, second])

    def test_component_hash_capability_partition_and_project_drift_deny(self):
        mutations = [
            lambda value: value["toolchain"]["components"][0].update(
                sha256="00" * 32
            ),
            lambda value: value["capabilities"].update(secure_boot_enabled=True),
            lambda value: value["partition_layout"]["partitions"][0].update(
                size=1
            ),
            lambda value: value["project"].update(
                platformio_project_sha256="00" * 32
            ),
        ]
        for mutation in mutations:
            value = self.baseline()
            mutation(value)
            self.reseal(value)
            with self.assertRaises(manager.SecurityPlatformIntakeError):
                manager.validate_profile(value)

    def test_platformio_home_drift_is_detected_without_absolute_path_output(self):
        profile = self.baseline()
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            for component in profile["toolchain"]["components"]:
                source = manager.component_path(
                    component, manager.platformio_home()
                )
                target = manager.component_path(component, home)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            manager.validate_profile(profile, home=home)
            target = manager.component_path(
                profile["toolchain"]["components"][0], home
            )
            target.write_bytes(target.read_bytes() + b"\n")
            with self.assertRaises(manager.SecurityPlatformIntakeError) as error:
                manager.validate_profile(profile, home=home)
            self.assertNotIn(str(home), str(error.exception))

    def test_schema_status_tamper_atomic_preservation_and_cli_check_deny(self):
        baseline = json.loads(STATUS.read_text())
        changed = copy.deepcopy(baseline)
        changed["summary"]["private_key_material_count"] = 1
        self.assertTrue(
            list(
                Draft202012Validator(
                    json.loads(manager.STATUS_SCHEMA.read_text())
                ).iter_errors(changed)
            )
        )
        changed = copy.deepcopy(baseline)
        changed["profiles"][0]["selected"] = True
        changed["integrity"]["record_sha256"] = manager.status_digest(changed)
        with self.assertRaises(manager.SecurityPlatformIntakeError):
            manager.validate_status(changed)

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "status.json"
            destination.write_text("preserve-me")
            with mock.patch.object(os, "replace", side_effect=OSError("fault")):
                with self.assertRaises(OSError):
                    manager.atomic_write(destination, baseline)
            self.assertEqual("preserve-me", destination.read_text())

        result = subprocess.run(
            [sys.executable, str(TOOL), "--check"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("profiles=1 reviewed=0 selected=0", result.stdout)
        self.assertIn("private_material=0", result.stdout)
        self.assertNotIn(str(Path.home()), result.stdout)


if __name__ == "__main__":
    unittest.main()
