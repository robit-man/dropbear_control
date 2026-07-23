from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/audit_claim_surfaces.py"
POLICY = ROOT / "tools/claim-surface-policy.json"
SCHEMA = ROOT / "schemas/myactuator-claim-surface-report.schema.json"
OUTPUT = ROOT / "generated/myactuator/claim_surface/report.json"

spec = importlib.util.spec_from_file_location("claim_surface_audit_test_module", TOOL)
assert spec is not None and spec.loader is not None
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


class ClaimSurfaceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = json.loads(OUTPUT.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def fixture_root(self) -> tempfile.TemporaryDirectory[str]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        for relative in (
            "tools/claim-surface-policy.json",
            "tools/audit_claim_surfaces.py",
            "schemas/myactuator-claim-surface-report.schema.json",
        ):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        policy = json.loads((root / "tools/claim-surface-policy.json").read_text())
        for item in policy["roots"]:
            path = root / item["path"]
            if path.suffix:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("Explicitly unsupported baseline.\\n", encoding="utf-8")
            else:
                path.mkdir(parents=True, exist_ok=True)
        return temporary

    def add_text(self, root: Path, relative: str, text: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def findings_for(self, relative: str, text: str) -> list[dict[str, str]]:
        with self.fixture_root() as temporary:
            root = Path(temporary)
            self.add_text(root, relative, text)
            return audit.audit(root, root / "tools/claim-surface-policy.json")[
                "findings"
            ]

    def test_tracked_report_schema_digest_scope_and_zero_authority(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.value)
        audit.validate(copy.deepcopy(self.value))
        self.assertEqual(20, self.value["scope"]["root_count"])
        self.assertEqual(4, self.value["scope"]["excluded_path_count"])
        self.assertEqual(12, self.value["summary"]["lexical_rule_count"] + self.value["summary"]["structured_rule_count"])
        self.assertEqual([], self.value["findings"])
        self.assertEqual(0, self.value["summary"]["exception_count"])
        self.assertTrue(self.value["summary"]["passed"])
        self.assertFalse(self.value["support_granted"])
        self.assertFalse(self.value["physical_motion_authority"])
        self.assertFalse(self.value["physical_action_permitted"])

    def test_report_sources_and_binary_assets_are_sorted_hash_bound_and_complete(self) -> None:
        scanned = self.value["scanned_sources"]
        binaries = self.value["binary_assets"]
        self.assertEqual(sorted(item["path"] for item in scanned), [item["path"] for item in scanned])
        self.assertEqual(sorted(item["path"] for item in binaries), [item["path"] for item in binaries])
        self.assertEqual(len(scanned), self.value["summary"]["scanned_file_count"])
        self.assertEqual(len(binaries), self.value["summary"]["binary_asset_count"])
        self.assertTrue(all(len(item["sha256"]) == 64 for item in scanned + binaries))
        self.assertEqual(
            self.value["scope"]["source_manifest_sha256"],
            audit.manifest_digest(scanned, binaries),
        )

    def test_family_and_series_promotions_are_rejected(self) -> None:
        samples = (
            "All MYACTUATOR motors are supported.",
            "This API supports the complete RMD-X family.",
            "RMD-X has family-wide compatibility.",
            "Every actuator model is now validated.",
        )
        for text in samples:
            with self.subTest(text=text):
                self.assertTrue(self.findings_for("docs/probe.md", text))

    def test_acquisition_build_and_simulation_promotions_are_rejected(self) -> None:
        samples = (
            "The downloaded STEP therefore means the motor is supported.",
            "The imported CAD model is now validated.",
            "The build passed, so the robot is production ready.",
            "The offline gate proves the hardware is validated.",
            "SIL therefore establishes the robot as hardware ready.",
            "The simulator proves the actuator is physically validated.",
        )
        for text in samples:
            with self.subTest(text=text):
                self.assertTrue(self.findings_for("README.md", text))

    def test_direct_physical_and_unconditional_claims_are_rejected(self) -> None:
        samples = (
            "Dropbear is motion-ready.",
            "This motor is validated for production.",
            "The project has complete robot support.",
            "The controller is HIL validated.",
        )
        for text in samples:
            with self.subTest(text=text):
                self.assertTrue(self.findings_for("web/probe.js", text))

    def test_explicit_denials_remain_legal_but_contradictory_new_clause_fails(self) -> None:
        safe = (
            "No family-wide support is claimed.",
            "The build does not establish hardware validation.",
            "Simulation is not physical validation.",
            "The robot is not motion-ready.",
            "Downloaded CAD is unavailable for production support.",
        )
        for text in safe:
            with self.subTest(text=text):
                self.assertEqual([], self.findings_for("docs/probe.md", text))
        findings = self.findings_for(
            "docs/probe.md",
            "The STEP was not validated; all motors are supported.",
        )
        self.assertTrue(findings)

    def test_structured_true_nonzero_and_status_promotions_are_rejected(self) -> None:
        samples = (
            {"support_granted": True},
            {"exact_model_simulation_ready_count": 1},
            {"motor_status": "production_ready"},
        )
        for value in samples:
            with self.subTest(value=value), self.fixture_root() as temporary:
                root = Path(temporary)
                path = root / "generated/probe.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value), encoding="utf-8")
                findings = audit.audit(
                    root, root / "tools/claim-surface-policy.json"
                )["findings"]
                self.assertTrue(findings)

    def test_policy_cannot_drop_root_exclusion_reason_or_binary_binding(self) -> None:
        mutations = []
        base = json.loads(POLICY.read_text(encoding="utf-8"))
        missing_root = copy.deepcopy(base)
        missing_root["roots"].pop()
        mutations.append(missing_root)
        extra_exclusion = copy.deepcopy(base)
        extra_exclusion["excluded_paths"].append(
            {"path": "docs", "reason": "Hide public claims from the verifier entirely."}
        )
        mutations.append(extra_exclusion)
        weak_reason = copy.deepcopy(base)
        weak_reason["excluded_paths"][0]["reason"] = "self"
        mutations.append(weak_reason)
        missing_binary = copy.deepcopy(base)
        missing_binary["binary_suffixes"].pop()
        mutations.append(missing_binary)
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(
                audit.ClaimSurfaceError
            ):
                audit.validate_policy(value)

    def test_symlink_non_utf8_and_unknown_json_fail_closed(self) -> None:
        with self.fixture_root() as temporary:
            root = Path(temporary)
            outside = root / "outside.txt"
            outside.write_text("all motors are supported", encoding="utf-8")
            link = root / "docs/link.md"
            link.symlink_to(outside)
            with self.assertRaises(audit.ClaimSurfaceError):
                audit.audit(root, root / "tools/claim-surface-policy.json")
        with self.fixture_root() as temporary:
            root = Path(temporary)
            (root / "docs/raw.dat").write_bytes(b"\xff\xfe")
            with self.assertRaises(audit.ClaimSurfaceError):
                audit.audit(root, root / "tools/claim-surface-policy.json")
        with self.fixture_root() as temporary:
            root = Path(temporary)
            (root / "generated/bad.json").write_text("{", encoding="utf-8")
            with self.assertRaises(audit.ClaimSurfaceError):
                audit.audit(root, root / "tools/claim-surface-policy.json")

    def test_tamper_and_findings_cannot_validate_as_passing_report(self) -> None:
        mutations = []
        digest = copy.deepcopy(self.value)
        digest["integrity"]["record_sha256"] = "0" * 64
        mutations.append(digest)
        authority = copy.deepcopy(self.value)
        authority["support_granted"] = True
        audit.set_digest(authority)
        mutations.append(authority)
        source = copy.deepcopy(self.value)
        source["scanned_sources"][0]["sha256"] = "0" * 64
        audit.set_digest(source)
        mutations.append(source)
        for value in mutations:
            with self.subTest(), self.assertRaises(audit.ClaimSurfaceError):
                audit.validate(value)


if __name__ == "__main__":
    unittest.main()
